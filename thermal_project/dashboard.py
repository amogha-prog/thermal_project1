"""
TIOS Dashboard — Python Pipeline Status Dashboard

Provides a minimal CLI/logging dashboard for the Python thermal analysis pipeline.
Sends real-time pipeline status and detection summaries to the Node.js backend
via UDP, where the web dashboard displays them.

This module is NOT a web server — the React frontend in tios2/frontend is the
primary dashboard. This module reports Python-side status to it.

Usage:
    dashboard = PipelineDashboard()
    dashboard.update(detections, frame_stats, pipeline_status)
"""

import json
import time
import socket
import logging
from datetime import datetime
from typing import Optional, Dict, List
from collections import deque

logger = logging.getLogger(__name__)


class PipelineDashboard:
    """
    Reports Python pipeline status to the Node.js backend.
    
    Sends periodic updates containing:
    - Pipeline health (running, fps, uptime)
    - Detection summary (counts, hottest temp, severity breakdown)
    - Frame processing stats
    - Auto-capture status
    """

    def __init__(
        self,
        backend_host: str = "127.0.0.1",
        backend_port: int = 14560,
        report_interval: float = 1.0,  # Send status every N seconds
    ):
        self.backend_host = backend_host
        self.backend_port = backend_port
        self.report_interval = report_interval

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._start_time = time.time()
        self._last_report = 0.0
        self._frame_count = 0
        self._detection_count = 0
        self._fps_history: deque = deque(maxlen=60)  # 1 minute of FPS samples
        self._temp_history: deque = deque(maxlen=300)  # 5 minutes of max temps

        # Live aggregates
        self._severity_counts = {"NORMAL": 0, "ELEVATED": 0, "WARNING": 0, "CRITICAL": 0}
        self._hottest_ever = 0.0
        self._last_detections: list = []

    def update(
        self,
        detections: list = None,
        frame_stats: dict = None,
        streams_status: dict = None,
        capture_status: dict = None,
        filter_stats: dict = None,
        fps: float = 0.0,
    ):
        """
        Update dashboard with latest pipeline data.
        Call this every frame or at a regular interval.
        """
        self._frame_count += 1

        if fps > 0:
            self._fps_history.append(fps)

        if frame_stats and "max_temp" in frame_stats:
            self._temp_history.append(frame_stats["max_temp"])
            if frame_stats["max_temp"] > self._hottest_ever:
                self._hottest_ever = frame_stats["max_temp"]

        if detections:
            self._detection_count += len(detections)
            self._last_detections = detections
            for det in detections:
                severity = getattr(det, "severity", "NORMAL") if hasattr(det, "severity") else "NORMAL"
                if severity in self._severity_counts:
                    self._severity_counts[severity] += 1

        # Send report at configured interval
        now = time.time()
        if now - self._last_report >= self.report_interval:
            self._send_report(frame_stats, streams_status, capture_status, filter_stats)
            self._last_report = now

    def _send_report(
        self,
        frame_stats: dict = None,
        streams_status: dict = None,
        capture_status: dict = None,
        filter_stats: dict = None,
    ):
        """Send pipeline status report to Node.js backend."""
        now = time.time()
        uptime = now - self._start_time

        avg_fps = sum(self._fps_history) / max(1, len(self._fps_history)) if self._fps_history else 0

        report = {
            "type": "pipeline_status",
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": round(uptime, 1),
            "pipeline": {
                "running": True,
                "frames_processed": self._frame_count,
                "avg_fps": round(avg_fps, 1),
                "total_detections": self._detection_count,
                "severity_counts": dict(self._severity_counts),
                "hottest_ever": round(self._hottest_ever, 1),
            },
            "frame": frame_stats or {},
            "streams": streams_status or {},
            "capture": capture_status or {},
            "filter": filter_stats or {},
            "active_detections": len(self._last_detections),
        }

        try:
            msg = json.dumps(report).encode("utf-8")
            self._socket.sendto(msg, (self.backend_host, self.backend_port))
        except Exception as e:
            logger.error(f"[Dashboard] Send error: {e}")

    def log_summary(self):
        """Print a summary to the console."""
        uptime = time.time() - self._start_time
        avg_fps = sum(self._fps_history) / max(1, len(self._fps_history)) if self._fps_history else 0

        logger.info(
            f"[Pipeline] Uptime: {uptime:.0f}s | "
            f"Frames: {self._frame_count} | "
            f"FPS: {avg_fps:.1f} | "
            f"Detections: {self._detection_count} | "
            f"Hottest: {self._hottest_ever:.1f}°C"
        )

    def get_status(self) -> dict:
        """Get current pipeline status as a dict."""
        now = time.time()
        avg_fps = sum(self._fps_history) / max(1, len(self._fps_history)) if self._fps_history else 0

        return {
            "running": True,
            "uptime": round(now - self._start_time, 1),
            "frames": self._frame_count,
            "fps": round(avg_fps, 1),
            "detections": self._detection_count,
            "severity_counts": dict(self._severity_counts),
            "hottest_ever": round(self._hottest_ever, 1),
        }

    def close(self):
        """Clean up resources."""
        if self._socket:
            self._socket.close()
            self._socket = None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    dashboard = PipelineDashboard(report_interval=2.0)

    # Simulate pipeline updates
    for i in range(20):
        dashboard.update(
            frame_stats={"max_temp": 35.0 + i * 0.5, "min_temp": 20.0, "avg_temp": 28.0},
            fps=24.5,
        )
        time.sleep(0.5)
        if i % 5 == 0:
            dashboard.log_summary()

    dashboard.close()
    print("Dashboard test complete")
