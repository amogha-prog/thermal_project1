"""
TIOS Main — Thermal Inspection Pipeline Orchestrator

Starts and coordinates all components of the thermal analysis pipeline:
  1. Stream Reader — captures thermal & RGB frames
  2. Hotspot Detector — finds temperature anomalies
  3. Classifier — assigns severity and type
  4. False Positive Filter — validates detections
  5. Auto Capture — saves frames on anomaly detection
  6. Dashboard — reports status to Node.js backend

Sends real-time detection results to the TIOS Node.js backend
via UDP on port 14560, which broadcasts them to the web frontend.

Usage:
    python main.py                                    # Defaults (simulation)
    python main.py --thermal-source rtsp://...        # With camera
    python main.py --thermal-source 0 --rgb-source 1  # USB cameras
"""

import os
import sys
import json
import time
import socket
import signal
import logging
import argparse
import threading
from datetime import datetime
from typing import Optional

import numpy as np

# Add parent dir to path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stream_reader import StreamReader, DualStreamReader
from hotspot_detector import HotspotDetector
from classifier import ThermalClassifier
from false_positive_filter import FalsePositiveFilter
from auto_capture import AutoCapture
from dashboard import PipelineDashboard

logger = logging.getLogger(__name__)


class ThermalPipeline:
    """
    Main thermal inspection pipeline.
    
    Coordinates frame acquisition, analysis, and reporting.
    Sends detection results to the TIOS Node.js backend via UDP.
    """

    def __init__(
        self,
        thermal_source: str = "rtsp://192.168.144.108:555/stream=2",
        rgb_source: str = "rtsp://192.168.144.108:554/stream=1",
        yolo_model: Optional[str] = None,
        backend_host: str = "127.0.0.1",
        backend_port: int = 14560,
        capture_dir: str = "./captures",
        detection_threshold: float = 35.0,
        auto_capture_severity: str = "WARNING",
        simulation: bool = False,
    ):
        self.backend_host = backend_host
        self.backend_port = backend_port
        self.simulation = simulation
        self._running = False
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # ── Components ──────────────────────────────────────────────────────
        if not simulation:
            self.streams = DualStreamReader(
                thermal_source=thermal_source,
                rgb_source=rgb_source,
                thermal_res=(640, 480),
                rgb_res=(1280, 720),
            )
        else:
            self.streams = None

        self.detector = HotspotDetector(
            threshold_temp=detection_threshold,
            yolo_model_path=yolo_model,
        )

        self.classifier = ThermalClassifier()

        self.fp_filter = FalsePositiveFilter(
            min_persistence_frames=3,
            min_persistence_time=0.5,
        )

        self.auto_capture = AutoCapture(
            output_dir=capture_dir,
            severity_trigger=auto_capture_severity,
            backend_host=backend_host,
            backend_port=backend_port,
        )

        self.dashboard = PipelineDashboard(
            backend_host=backend_host,
            backend_port=backend_port,
        )

        # Stats
        self._frame_times = []
        self._process_count = 0

    def _generate_simulation_frame(self) -> np.ndarray:
        """Generate a synthetic thermal frame for testing without a camera."""
        t = time.time()
        frame = np.zeros((480, 640), dtype=np.uint8)
        
        # Background ambient (~22°C → pixel ~60)
        frame[:] = 60

        # Add some structure (walls, objects)
        frame[50:200, 400:600] = 85   # Warm wall section
        frame[250:400, 50:250] = 75   # Equipment block

        # Moving hotspot (simulates a thermal anomaly)
        cx = int(320 + 100 * np.sin(t * 0.3))
        cy = int(240 + 60 * np.cos(t * 0.4))
        cv2_imported = True
        try:
            import cv2
            cv2.circle(frame, (cx, cy), 25, 200, -1)
            # Secondary hotspot  
            cv2.circle(frame, (450, 150), 20, 180, -1)
            # Random noise hotspot (false positive candidate)
            if np.random.random() > 0.7:
                rx, ry = np.random.randint(0, 640), np.random.randint(0, 480)
                cv2.circle(frame, (rx, ry), 8, 190, -1)
            # Blur for realism
            frame = cv2.GaussianBlur(frame, (5, 5), 0)
        except ImportError:
            cv2_imported = False
            # Fallback without OpenCV
            y_grid, x_grid = np.ogrid[:480, :640]
            mask = (x_grid - cx)**2 + (y_grid - cy)**2 < 25**2
            frame[mask] = 200
            mask2 = (x_grid - 450)**2 + (y_grid - 150)**2 < 20**2
            frame[mask2] = 180

        # Add noise
        noise = np.random.randint(-3, 4, frame.shape, dtype=np.int16)
        frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        return frame

    def _send_detections(self, detections: list, frame_stats: dict):
        """Send detection results to Node.js backend via UDP."""
        try:
            payload = {
                "type": "detections",
                "timestamp": datetime.now().isoformat(),
                "frame_stats": frame_stats,
                "detections": [
                    d.to_dict() if hasattr(d, "to_dict") else vars(d)
                    for d in detections
                ],
                "count": len(detections),
            }
            msg = json.dumps(payload, default=str).encode("utf-8")
            self._socket.sendto(msg, (self.backend_host, self.backend_port))
        except Exception as e:
            logger.error(f"[Pipeline] Failed to send detections: {e}")

    def _process_frame(self, thermal_frame: np.ndarray, rgb_frame: Optional[np.ndarray] = None):
        """Process a single thermal frame through the full pipeline."""
        t0 = time.time()
        self._process_count += 1

        # 1. Get frame-level temperature stats
        frame_stats = self.detector.get_frame_stats(thermal_frame)

        # 2. Detect hotspots
        raw_detections = self.detector.detect(thermal_frame)

        # 3. Classify detections
        if raw_detections:
            classified = self.classifier.classify(raw_detections, frame_stats)
        else:
            classified = []

        # 4. Filter false positives
        if classified:
            validated = self.fp_filter.filter(classified)
        else:
            validated = []

        # 5. Auto-capture if needed
        if validated:
            self.auto_capture.evaluate(validated, thermal_frame, rgb_frame)

        # 6. Send results to backend
        self._send_detections(validated, frame_stats)

        # 7. Update dashboard
        elapsed = time.time() - t0
        fps = 1.0 / max(elapsed, 0.001)
        self.dashboard.update(
            detections=validated,
            frame_stats=frame_stats,
            streams_status=self.streams.get_status() if self.streams else {"simulation": True},
            capture_status=self.auto_capture.get_status(),
            filter_stats=self.fp_filter.get_stats(),
            fps=fps,
        )

        return validated

    def run(self):
        """Main pipeline loop."""
        self._running = True

        # Start camera streams
        if self.streams:
            self.streams.start()
            logger.info("[Pipeline] Camera streams started")
        else:
            logger.info("[Pipeline] Running in SIMULATION mode")

        logger.info("[Pipeline] ═══════════════════════════════════════")
        logger.info("[Pipeline]  TIOS Thermal Pipeline — RUNNING")
        logger.info(f"[Pipeline]  Sending to {self.backend_host}:{self.backend_port}")
        logger.info("[Pipeline] ═══════════════════════════════════════")

        frame_interval = 1.0 / 25  # 25 FPS target
        log_interval = 10.0  # Log summary every 10 seconds
        last_log = time.time()

        while self._running:
            loop_start = time.time()

            # Get frame
            if self.streams:
                thermal_frame = self.streams.thermal.read_gray()
                rgb_frame = self.streams.rgb.read()
            else:
                thermal_frame = self._generate_simulation_frame()
                rgb_frame = None

            if thermal_frame is None:
                time.sleep(0.1)
                continue

            # Process
            validated = self._process_frame(thermal_frame, rgb_frame)

            # Periodic logging
            if time.time() - last_log >= log_interval:
                self.dashboard.log_summary()
                filter_stats = self.fp_filter.get_stats()
                logger.info(f"[Filter] {filter_stats}")
                last_log = time.time()

            # Rate-limit
            elapsed = time.time() - loop_start
            if elapsed < frame_interval:
                time.sleep(frame_interval - elapsed)

        # Cleanup
        if self.streams:
            self.streams.stop()
        self.auto_capture.close()
        self.dashboard.close()
        self._socket.close()
        logger.info("[Pipeline] Shutdown complete")

    def stop(self):
        """Stop the pipeline."""
        self._running = False
        logger.info("[Pipeline] Stopping...")


def main():
    parser = argparse.ArgumentParser(description="TIOS Thermal Inspection Pipeline")
    parser.add_argument("--thermal-source", default="rtsp://192.168.144.108:555/stream=2",
                        help="Thermal camera source (RTSP URL, device index, or file)")
    parser.add_argument("--rgb-source", default="rtsp://192.168.144.108:554/stream=1",
                        help="RGB camera source")
    parser.add_argument("--yolo-model", default="yolo11n.pt",
                        help="Path to YOLO .pt model file")
    parser.add_argument("--backend-host", default="127.0.0.1",
                        help="Node.js backend host")
    parser.add_argument("--backend-port", type=int, default=14560,
                        help="Node.js backend UDP port for detections")
    parser.add_argument("--capture-dir", default="./captures",
                        help="Directory for auto-captured images")
    parser.add_argument("--threshold", type=float, default=35.0,
                        help="Detection temperature threshold (°C)")
    parser.add_argument("--auto-capture", default="WARNING",
                        choices=["NORMAL", "ELEVATED", "WARNING", "CRITICAL"],
                        help="Auto-capture severity trigger level")
    parser.add_argument("--simulation", action="store_true",
                        help="Run with simulated thermal data (no camera needed)")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    pipeline = ThermalPipeline(
        thermal_source=args.thermal_source,
        rgb_source=args.rgb_source,
        yolo_model=args.yolo_model,
        backend_host=args.backend_host,
        backend_port=args.backend_port,
        capture_dir=args.capture_dir,
        detection_threshold=args.threshold,
        auto_capture_severity=args.auto_capture,
        simulation=args.simulation,
    )

    # Graceful shutdown on Ctrl+C
    def signal_handler(sig, frame):
        pipeline.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    pipeline.run()


if __name__ == "__main__":
    main()
