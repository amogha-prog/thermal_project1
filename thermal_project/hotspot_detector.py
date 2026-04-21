"""
TIOS Hotspot Detector — Thermal Anomaly Detection

Detects hotspots in thermal camera frames using:
  1. Classical CV: Adaptive thresholding + contour analysis
  2. YOLO (optional): Custom-trained model for thermal anomaly detection

Returns list of Detection objects with bounding boxes and temperature data.

Usage:
    detector = HotspotDetector()
    detections = detector.detect(thermal_frame)
"""

import cv2
import numpy as np
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class Detection:
    """A single hotspot detection."""
    id: int = 0
    x: int = 0            # bbox top-left x
    y: int = 0            # bbox top-left y
    w: int = 0            # bbox width
    h: int = 0            # bbox height
    cx: float = 0.0       # center x (normalized 0-1)
    cy: float = 0.0       # center y (normalized 0-1)
    max_temp: float = 0.0
    min_temp: float = 0.0
    avg_temp: float = 0.0
    area: int = 0         # pixel area
    confidence: float = 0.0
    source: str = "cv"    # "cv" or "yolo"
    label: str = "hotspot"
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


class HotspotDetector:
    """
    Detects thermal hotspots using classical CV and/or YOLO.
    
    Temperature mapping:
    - The thermal camera outputs grayscale where brightness ∝ temperature.
    - We map pixel intensity (0-255) to a configurable temperature range.
    - Default range: 15°C (black) → 45°C (white) — typical for structural inspection.
    """

    def __init__(
        self,
        temp_min: float = 15.0,
        temp_max: float = 45.0,
        threshold_temp: float = 35.0,
        min_area: int = 100,
        max_area: int = 50000,
        blur_kernel: int = 5,
        yolo_model_path: Optional[str] = None,
        yolo_confidence: float = 0.5,
    ):
        """
        Args:
            temp_min:        Temperature corresponding to pixel value 0
            temp_max:        Temperature corresponding to pixel value 255
            threshold_temp:  Minimum temperature to consider as a hotspot
            min_area:        Minimum contour area in pixels
            max_area:        Maximum contour area in pixels
            blur_kernel:     Gaussian blur kernel size (must be odd)
            yolo_model_path: Path to YOLO .pt model (optional)
            yolo_confidence: YOLO detection confidence threshold
        """
        self.temp_min = temp_min
        self.temp_max = temp_max
        self.threshold_temp = threshold_temp
        self.min_area = min_area
        self.max_area = max_area
        self.blur_kernel = blur_kernel
        self.yolo_confidence = yolo_confidence

        self._detection_id = 0
        self._yolo_model = None

        # Try to load YOLO model
        if yolo_model_path:
            self._load_yolo(yolo_model_path)

    def _load_yolo(self, model_path: str):
        """Load YOLO model for thermal anomaly detection."""
        try:
            from ultralytics import YOLO
            import os
            if os.path.exists(model_path) and os.path.getsize(model_path) > 0:
                self._yolo_model = YOLO(model_path)
                logger.info(f"[Detector] YOLO model loaded: {model_path}")
            else:
                logger.warning(f"[Detector] YOLO model not found or empty: {model_path}")
        except ImportError:
            logger.warning("[Detector] ultralytics not installed — YOLO disabled")
        except Exception as e:
            logger.error(f"[Detector] Failed to load YOLO: {e}")

    def _pixel_to_temp(self, pixel_value: float) -> float:
        """Convert pixel intensity (0-255) to temperature."""
        return self.temp_min + (pixel_value / 255.0) * (self.temp_max - self.temp_min)

    def _temp_to_pixel(self, temp: float) -> int:
        """Convert temperature to pixel intensity (0-255)."""
        return int(np.clip(
            (temp - self.temp_min) / (self.temp_max - self.temp_min) * 255,
            0, 255
        ))

    def _get_region_temps(self, gray: np.ndarray, x: int, y: int, w: int, h: int) -> Tuple[float, float, float]:
        """Get max, min, avg temperature for a bounding box region."""
        region = gray[y:y+h, x:x+w]
        if region.size == 0:
            return 0.0, 0.0, 0.0
        return (
            self._pixel_to_temp(float(np.max(region))),
            self._pixel_to_temp(float(np.min(region))),
            self._pixel_to_temp(float(np.mean(region))),
        )

    def detect_cv(self, frame: np.ndarray) -> List[Detection]:
        """
        Classical CV-based hotspot detection.
        
        Pipeline:
        1. Convert to grayscale
        2. Gaussian blur to reduce noise
        3. Threshold at the configured temperature
        4. Find contours
        5. Filter by area and compute temperatures
        """
        # To grayscale
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame.copy()

        H, W = gray.shape[:2]

        # Blur to reduce thermal noise
        blurred = cv2.GaussianBlur(gray, (self.blur_kernel, self.blur_kernel), 0)

        # Threshold at the hotspot temperature
        thresh_value = self._temp_to_pixel(self.threshold_temp)
        _, binary = cv2.threshold(blurred, thresh_value, 255, cv2.THRESH_BINARY)

        # Morphological cleanup
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)

        # Find contours
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        detections = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self.min_area or area > self.max_area:
                continue

            x, y, w, h = cv2.boundingRect(contour)
            max_t, min_t, avg_t = self._get_region_temps(gray, x, y, w, h)

            # Only keep if max temp exceeds threshold
            if max_t < self.threshold_temp:
                continue

            self._detection_id += 1

            # Confidence based on how much it exceeds the threshold
            temp_range = self.temp_max - self.threshold_temp
            confidence = min(1.0, (max_t - self.threshold_temp) / max(temp_range, 1.0))

            detections.append(Detection(
                id=self._detection_id,
                x=x, y=y, w=w, h=h,
                cx=round((x + w / 2) / W, 4),
                cy=round((y + h / 2) / H, 4),
                max_temp=round(max_t, 1),
                min_temp=round(min_t, 1),
                avg_temp=round(avg_t, 1),
                area=area,
                confidence=round(confidence, 3),
                source="cv",
                label="hotspot",
                timestamp=time.time(),
            ))

        # Sort by max temperature (hottest first)
        detections.sort(key=lambda d: d.max_temp, reverse=True)
        return detections

    def detect_yolo(self, frame: np.ndarray) -> List[Detection]:
        """YOLO-based hotspot detection (if model is available)."""
        if self._yolo_model is None:
            return []

        try:
            results = self._yolo_model.predict(
                frame,
                conf=self.yolo_confidence,
                verbose=False,
                device="cpu",
            )

            if len(frame.shape) == 3:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            else:
                gray = frame.copy()

            H, W = gray.shape[:2]
            detections = []

            for result in results:
                for box in result.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    w, h = x2 - x1, y2 - y1
                    conf = float(box.conf[0])
                    cls = int(box.cls[0])
                    label = result.names.get(cls, "anomaly")

                    max_t, min_t, avg_t = self._get_region_temps(gray, x1, y1, w, h)
                    self._detection_id += 1

                    detections.append(Detection(
                        id=self._detection_id,
                        x=x1, y=y1, w=w, h=h,
                        cx=round((x1 + w / 2) / W, 4),
                        cy=round((y1 + h / 2) / H, 4),
                        max_temp=round(max_t, 1),
                        min_temp=round(min_t, 1),
                        avg_temp=round(avg_t, 1),
                        area=w * h,
                        confidence=round(conf, 3),
                        source="yolo",
                        label=label,
                        timestamp=time.time(),
                    ))

            return detections
        except Exception as e:
            logger.error(f"[Detector] YOLO inference error: {e}")
            return []

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Run detection on a frame.
        Uses YOLO if available, otherwise falls back to classical CV.
        If both are available, merges results with NMS.
        """
        cv_dets = self.detect_cv(frame)
        yolo_dets = self.detect_yolo(frame)

        if not yolo_dets:
            return cv_dets
        if not cv_dets:
            return yolo_dets

        # Merge: prefer YOLO detections, add non-overlapping CV detections
        merged = list(yolo_dets)
        for cd in cv_dets:
            overlaps = False
            for yd in yolo_dets:
                iou = self._compute_iou(cd, yd)
                if iou > 0.3:
                    overlaps = True
                    break
            if not overlaps:
                merged.append(cd)

        merged.sort(key=lambda d: d.max_temp, reverse=True)
        return merged

    @staticmethod
    def _compute_iou(a: Detection, b: Detection) -> float:
        """Compute Intersection over Union of two detections."""
        x1 = max(a.x, b.x)
        y1 = max(a.y, b.y)
        x2 = min(a.x + a.w, b.x + b.w)
        y2 = min(a.y + a.h, b.y + b.h)

        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area_a = a.w * a.h
        area_b = b.w * b.h
        union = area_a + area_b - inter

        return inter / union if union > 0 else 0.0

    def draw_detections(self, frame: np.ndarray, detections: List[Detection]) -> np.ndarray:
        """Draw detection bounding boxes and labels on a frame (for debug/display)."""
        vis = frame.copy()
        for det in detections:
            # Color by severity
            if det.max_temp > 70:
                color = (0, 0, 255)     # Red — Critical
            elif det.max_temp > 50:
                color = (0, 165, 255)   # Orange — Warning
            elif det.max_temp > 35:
                color = (0, 255, 255)   # Yellow — Elevated
            else:
                color = (0, 255, 0)     # Green — Normal

            # Bounding box
            cv2.rectangle(vis, (det.x, det.y), (det.x + det.w, det.y + det.h), color, 2)

            # Label
            label = f"{det.max_temp:.1f}C [{det.confidence:.0%}]"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            cv2.rectangle(vis, (det.x, det.y - th - 8), (det.x + tw + 4, det.y), color, -1)
            cv2.putText(vis, label, (det.x + 2, det.y - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

        return vis

    def get_frame_stats(self, frame: np.ndarray) -> dict:
        """Get overall temperature statistics for a frame."""
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame.copy()

        return {
            "max_temp": round(self._pixel_to_temp(float(np.max(gray))), 1),
            "min_temp": round(self._pixel_to_temp(float(np.min(gray))), 1),
            "avg_temp": round(self._pixel_to_temp(float(np.mean(gray))), 1),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test with a synthetic thermal image
    img = np.zeros((480, 640), dtype=np.uint8)
    img[:] = 80  # Background ~24°C
    
    # Add some "hotspots"
    cv2.circle(img, (200, 150), 30, 220, -1)   # ~41°C
    cv2.circle(img, (400, 300), 25, 250, -1)    # ~44°C
    cv2.rectangle(img, (100, 350), (180, 420), 200, -1)  # ~39°C
    
    # Blur slightly to simulate real thermal
    img = cv2.GaussianBlur(img, (7, 7), 0)
    
    detector = HotspotDetector(threshold_temp=35.0)
    detections = detector.detect(img)
    
    print(f"Found {len(detections)} hotspots:")
    for d in detections:
        print(f"  [{d.id}] {d.max_temp:.1f}°C @ ({d.x},{d.y}) {d.w}x{d.h} conf={d.confidence:.1%}")
    
    stats = detector.get_frame_stats(img)
    print(f"Frame stats: {stats}")
