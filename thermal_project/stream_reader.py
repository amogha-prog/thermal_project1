"""
TIOS Stream Reader — Thermal & RGB Camera Interface

Reads frames from RTSP, USB cameras, or video files using OpenCV.
Provides thread-safe frame access for the thermal analysis pipeline.

Usage:
    reader = StreamReader(source="rtsp://192.168.144.108:555/stream=2")
    reader.start()
    frame = reader.read()   # returns latest frame (numpy array)
    reader.stop()
"""

import cv2
import time
import threading
import logging
import numpy as np
from typing import Optional, Callable, Tuple

logger = logging.getLogger(__name__)


class StreamReader:
    """Thread-safe video stream reader with auto-reconnection."""

    def __init__(
        self,
        source: str = "rtsp://192.168.144.108:555/stream=2",
        name: str = "thermal",
        resolution: Optional[Tuple[int, int]] = None,
        fps_limit: int = 25,
        reconnect_delay: float = 3.0,
        on_frame: Optional[Callable] = None,
    ):
        """
        Args:
            source:          RTSP URL, device index (0,1,..), or video file path
            name:            Stream identifier ('thermal' or 'rgb')
            resolution:      Optional (width, height) to resize frames
            fps_limit:       Max frames per second to process
            reconnect_delay: Seconds to wait before reconnecting on failure
            on_frame:        Optional callback invoked with each new frame
        """
        self.source = source
        self.name = name
        self.resolution = resolution
        self.fps_limit = fps_limit
        self.reconnect_delay = reconnect_delay
        self.on_frame = on_frame

        self._cap: Optional[cv2.VideoCapture] = None
        self._frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._frame_count = 0
        self._fps = 0.0
        self._last_fps_time = time.time()
        self._last_fps_count = 0
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def frame_count(self) -> int:
        return self._frame_count

    @property
    def fps(self) -> float:
        return self._fps

    def _open(self) -> bool:
        """Open the video capture source."""
        try:
            # Parse source — integer means USB camera index
            src = int(self.source) if self.source.isdigit() else self.source
            
            self._cap = cv2.VideoCapture(src)
            
            # RTSP-specific optimizations
            if isinstance(src, str) and src.startswith("rtsp"):
                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                # Use TCP for more reliable RTSP
                self._cap = cv2.VideoCapture(src, cv2.CAP_FFMPEG)
                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            if not self._cap.isOpened():
                logger.warning(f"[{self.name}] Failed to open: {self.source}")
                return False

            # Get native resolution
            w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            native_fps = self._cap.get(cv2.CAP_PROP_FPS)
            logger.info(f"[{self.name}] Opened {self.source} — {w}x{h} @ {native_fps:.1f}fps")
            
            self._connected = True
            return True

        except Exception as e:
            logger.error(f"[{self.name}] Open error: {e}")
            return False

    def _read_loop(self):
        """Main capture loop running in a background thread."""
        frame_interval = 1.0 / self.fps_limit if self.fps_limit > 0 else 0

        while self._running:
            # Connect if not connected
            if not self._connected or self._cap is None or not self._cap.isOpened():
                self._connected = False
                if self._cap:
                    self._cap.release()
                logger.info(f"[{self.name}] Connecting to {self.source}...")
                if not self._open():
                    time.sleep(self.reconnect_delay)
                    continue

            loop_start = time.time()

            ret, frame = self._cap.read()
            if not ret or frame is None:
                logger.warning(f"[{self.name}] Frame grab failed — reconnecting...")
                self._connected = False
                time.sleep(self.reconnect_delay)
                continue

            # Resize if requested
            if self.resolution:
                frame = cv2.resize(frame, self.resolution, interpolation=cv2.INTER_LINEAR)

            # Update frame atomically
            with self._lock:
                self._frame = frame
                self._frame_count += 1

            # Invoke callback
            if self.on_frame:
                try:
                    self.on_frame(frame.copy(), self.name)
                except Exception as e:
                    logger.error(f"[{self.name}] Callback error: {e}")

            # FPS calculation (update every second)
            now = time.time()
            if now - self._last_fps_time >= 1.0:
                self._fps = (self._frame_count - self._last_fps_count) / (now - self._last_fps_time)
                self._last_fps_time = now
                self._last_fps_count = self._frame_count

            # Rate-limit
            elapsed = time.time() - loop_start
            if elapsed < frame_interval:
                time.sleep(frame_interval - elapsed)

        # Cleanup
        if self._cap:
            self._cap.release()
        self._connected = False
        logger.info(f"[{self.name}] Stream stopped")

    def start(self):
        """Start the capture thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True, name=f"stream-{self.name}")
        self._thread.start()
        logger.info(f"[{self.name}] Capture thread started")

    def stop(self):
        """Stop the capture thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info(f"[{self.name}] Capture thread stopped")

    def read(self) -> Optional[np.ndarray]:
        """Get the latest frame (thread-safe). Returns None if no frame available."""
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def read_gray(self) -> Optional[np.ndarray]:
        """Get the latest frame as grayscale."""
        frame = self.read()
        if frame is None:
            return None
        if len(frame.shape) == 3:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return frame

    def get_status(self) -> dict:
        """Return current stream status."""
        return {
            "name": self.name,
            "source": self.source,
            "connected": self._connected,
            "running": self._running,
            "frame_count": self._frame_count,
            "fps": round(self._fps, 1),
        }


class DualStreamReader:
    """Manages both thermal and RGB camera streams."""

    def __init__(
        self,
        thermal_source: str = "rtsp://192.168.144.108:555/stream=2",
        rgb_source: str = "rtsp://192.168.144.108:554/stream=1",
        thermal_res: Optional[Tuple[int, int]] = (640, 480),
        rgb_res: Optional[Tuple[int, int]] = (1280, 720),
        on_thermal_frame: Optional[Callable] = None,
        on_rgb_frame: Optional[Callable] = None,
    ):
        self.thermal = StreamReader(
            source=thermal_source,
            name="thermal",
            resolution=thermal_res,
            fps_limit=25,
            on_frame=on_thermal_frame,
        )
        self.rgb = StreamReader(
            source=rgb_source,
            name="rgb",
            resolution=rgb_res,
            fps_limit=30,
            on_frame=on_rgb_frame,
        )

    def start(self):
        self.thermal.start()
        self.rgb.start()

    def stop(self):
        self.thermal.stop()
        self.rgb.stop()

    def get_status(self) -> dict:
        return {
            "thermal": self.thermal.get_status(),
            "rgb": self.rgb.get_status(),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    
    # Quick test — reads from default thermal RTSP URL
    reader = StreamReader(source="0", name="test-cam", resolution=(640, 480))
    reader.start()
    
    try:
        while True:
            frame = reader.read()
            if frame is not None:
                cv2.imshow("Stream Test", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            time.sleep(0.03)
    except KeyboardInterrupt:
        pass
    finally:
        reader.stop()
        cv2.destroyAllWindows()
