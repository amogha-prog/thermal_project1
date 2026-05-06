import cv2
import threading
import numpy as np

# C12 RTSP addresses (from manual, page 7)
THERMAL_URL  = "rtsp://192.168.144.108:555/stream=2"
VISIBLE_URL  = "rtsp://192.168.144.108:554/stream=1"

class C12StreamReader:
    def __init__(self):
        self.thermal_frame  = None
        self.visible_frame  = None
        self.running        = False
        self._t_lock        = threading.Lock()
        self._v_lock        = threading.Lock()

    def _read_stream(self, url, attr, lock):
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # keep latency low
        while self.running:
            ret, frame = cap.read()
            if not ret:
                continue
            with lock:
                setattr(self, attr, frame)
        cap.release()

    def start(self):
        self.running = True
        threading.Thread(
            target=self._read_stream,
            args=(THERMAL_URL, "thermal_frame", self._t_lock),
            daemon=True).start()
        threading.Thread(
            target=self._read_stream,
            args=(VISIBLE_URL, "visible_frame", self._v_lock),
            daemon=True).start()

    def get_thermal(self):
        with self._t_lock:
            return self.thermal_frame.copy() if self.thermal_frame is not None else None

    def get_visible(self):
        with self._v_lock:
            return self.visible_frame.copy() if self.visible_frame is not None else None

    def stop(self):
        self.running = False