"""
TIOS Auto Capture — Intelligent Auto-Capture on Anomaly Detection

Automatically captures thermal + RGB frames when anomalies are detected.
Configurable trigger thresholds, cooldown periods, and capture limits.

Sends capture events to the TIOS Node.js backend via UDP for real-time
integration with the web dashboard.

Usage:
    auto_cap = AutoCapture(output_dir="./captures")
    auto_cap.evaluate(classified_detections, thermal_frame, rgb_frame)
"""

import os
import cv2
import json
import time
import socket
import logging
import threading
from datetime import datetime
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class AutoCapture:
    """
    Automated capture engine for thermal inspection.
    
    Triggers a capture when:
    - A detection exceeds the severity threshold (WARNING or CRITICAL by default)
    - The cooldown period has elapsed since the last capture
    - The maximum captures per session hasn't been reached
    
    Saves thermal and RGB frames as JPEG files with metadata JSON sidecar.
    Sends capture event via UDP to the Node.js backend.
    """

    def __init__(
        self,
        output_dir: str = "./captures",
        severity_trigger: str = "WARNING",       # Minimum severity to trigger
        temp_trigger: float = 50.0,              # Minimum temp to trigger (absolute)
        cooldown_seconds: float = 5.0,           # Min time between captures
        max_captures: int = 500,                  # Max captures per session
        backend_host: str = "127.0.0.1",
        backend_port: int = 14560,               # UDP port for sending events to Node.js
        save_images: bool = True,
        notify_backend: bool = True,
    ):
        self.output_dir = output_dir
        self.severity_trigger = severity_trigger
        self.temp_trigger = temp_trigger
        self.cooldown_seconds = cooldown_seconds
        self.max_captures = max_captures
        self.backend_host = backend_host
        self.backend_port = backend_port
        self.save_images = save_images
        self.notify_backend = notify_backend

        self._capture_count = 0
        self._last_capture_time = 0.0
        self._session_start = datetime.now()
        self._socket: Optional[socket.socket] = None
        self._geotag_socket: Optional[socket.socket] = None
        self.geotag_addr = ("127.0.0.1", 14557)

        # Severity ordering for comparisons
        self._severity_rank = {
            "NORMAL": 0, "ELEVATED": 1, "WARNING": 2, "CRITICAL": 3
        }

        # Create output directory
        if self.save_images:
            os.makedirs(self.output_dir, exist_ok=True)

        # Setup UDP socket for backend notification
        if self.notify_backend:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def _should_trigger(self, detections: list) -> bool:
        """Check if any detection meets the trigger criteria."""
        if self._capture_count >= self.max_captures:
            return False

        now = time.monotonic()
        if now - self._last_capture_time < self.cooldown_seconds:
            return False

        trigger_rank = self._severity_rank.get(self.severity_trigger, 2)

        for det in detections:
            severity = getattr(det, "severity", "NORMAL")
            det_rank = self._severity_rank.get(severity, 0)
            max_temp = getattr(det, "max_temp", 0)

            if det_rank >= trigger_rank or max_temp >= self.temp_trigger:
                return True

        return False

    def _save_capture(
        self,
        thermal_frame: Optional[np.ndarray],
        rgb_frame: Optional[np.ndarray],
        detections: list,
    ) -> dict:
        """Save capture frames and metadata to disk."""
        self._capture_count += 1
        mono_now = time.monotonic()
        wall_now = time.time()
        self._last_capture_time = mono_now

        timestamp = datetime.now()
        cap_id = f"AUTO-{self._capture_count:04d}"
        date_str = timestamp.strftime("%Y%m%d_%H%M%S")
        base_name = f"{cap_id}_{date_str}"

        capture_info = {
            "id": cap_id,
            "timestamp": timestamp.isoformat(),
            "capture_number": self._capture_count,
            "detections": [],
            "images": {},
            "geotag": self._query_geotag(mono_now)
        }

        if self.save_images:
            # Save thermal frame
            if thermal_frame is not None:
                thermal_path = os.path.join(self.output_dir, f"{base_name}_thermal.jpg")
                cv2.imwrite(thermal_path, thermal_frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                capture_info["images"]["thermal"] = thermal_path
                logger.info(f"[AutoCapture] Saved thermal: {thermal_path}")

            # Save RGB frame
            if rgb_frame is not None:
                rgb_path = os.path.join(self.output_dir, f"{base_name}_rgb.jpg")
                cv2.imwrite(rgb_path, rgb_frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                capture_info["images"]["rgb"] = rgb_path

            # Save detection metadata
            for det in detections:
                if hasattr(det, "to_dict"):
                    capture_info["detections"].append(det.to_dict())
                elif hasattr(det, "__dict__"):
                    capture_info["detections"].append(vars(det))

            meta_path = os.path.join(self.output_dir, f"{base_name}_meta.json")
            with open(meta_path, "w") as f:
                json.dump(capture_info, f, indent=2, default=str)

        return capture_info

    def _query_geotag(self, mono_t: float) -> dict:
        """Query the drone_bridge for interpolated telemetry at capture time."""
        if not self._geotag_socket:
            self._geotag_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._geotag_socket.settimeout(0.2)
        
        try:
            query = {"type": "geotag_query", "mono_t": mono_t}
            self._geotag_socket.sendto(json.dumps(query).encode(), self.geotag_addr)
            data, _ = self._geotag_socket.recvfrom(2048)
            return json.loads(data.decode())
        except Exception as e:
            logger.warning(f"[AutoCapture] Geotag query failed: {e}")
            return {"status": "error", "message": str(e)}

    def _notify_backend(self, capture_info: dict):
        """Send capture event to Node.js backend via UDP."""
        if not self._socket:
            return

        try:
            event = {
                "type": "auto_capture",
                "id": capture_info["id"],
                "timestamp": capture_info["timestamp"],
                "capture_number": capture_info["capture_number"],
                "detection_count": len(capture_info.get("detections", [])),
                "max_temp": max(
                    (d.get("max_temp", 0) for d in capture_info.get("detections", [])),
                    default=0
                ),
                "severity": max(
                    (d.get("severity", "NORMAL") for d in capture_info.get("detections", [])),
                    key=lambda s: self._severity_rank.get(s, 0),
                    default="NORMAL"
                ),
            }

            msg = json.dumps(event).encode("utf-8")
            self._socket.sendto(msg, (self.backend_host, self.backend_port))
            logger.debug(f"[AutoCapture] Backend notified: {event['id']}")
        except Exception as e:
            logger.error(f"[AutoCapture] Backend notification failed: {e}")

    def evaluate(
        self,
        detections: list,
        thermal_frame: Optional[np.ndarray] = None,
        rgb_frame: Optional[np.ndarray] = None,
    ) -> Optional[dict]:
        """
        Evaluate detections and auto-capture if trigger conditions are met.
        
        Args:
            detections:     ClassifiedDetection list from the classifier
            thermal_frame:  Current thermal camera frame
            rgb_frame:      Current RGB camera frame
            
        Returns:
            Capture info dict if a capture was triggered, None otherwise
        """
        if not self._should_trigger(detections):
            return None

        logger.info(f"[AutoCapture] Triggered! (capture #{self._capture_count + 1})")

        capture_info = self._save_capture(thermal_frame, rgb_frame, detections)

        if self.notify_backend:
            self._notify_backend(capture_info)

        return capture_info

    def get_status(self) -> dict:
        """Return auto-capture status."""
        return {
            "enabled": True,
            "capture_count": self._capture_count,
            "max_captures": self.max_captures,
            "cooldown_seconds": self.cooldown_seconds,
            "severity_trigger": self.severity_trigger,
            "temp_trigger": self.temp_trigger,
            "last_capture_time": self._last_capture_time,
            "session_start": self._session_start.isoformat(),
        }

    def close(self):
        """Clean up resources."""
        if self._socket:
            self._socket.close()
            self._socket = None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    
    from hotspot_detector import Detection
    from classifier import ClassifiedDetection

    ac = AutoCapture(
        output_dir="./test_captures",
        severity_trigger="WARNING",
        cooldown_seconds=1.0,
        notify_backend=False,  # Don't send UDP in test
    )

    # Simulate detections
    det = ClassifiedDetection(
        id=1, x=100, y=100, w=50, h=40,
        max_temp=65.0, severity="WARNING",
        anomaly_type="ELECTRICAL",
    )

    # Create a dummy thermal frame
    frame = np.random.randint(0, 255, (480, 640), dtype=np.uint8)

    result = ac.evaluate([det], thermal_frame=frame)
    if result:
        print(f"Capture triggered: {result['id']}")
    else:
        print("No capture triggered")

    print(f"Status: {ac.get_status()}")
    ac.close()
