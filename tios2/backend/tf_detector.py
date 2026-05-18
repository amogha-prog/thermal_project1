import cv2
import numpy as np
import time
import os
import sys
import json
import socket
import threading
from flask import Flask, Response
from flask_cors import CORS

# Ensure local modules can be imported
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from python.hotspot_detector import HotspotDetector

app = Flask(__name__)
CORS(app)

UDP_IP = "127.0.0.1"
UDP_PORT = 14560
udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Living organisms — flag as CRITICAL severity in thermal view
WARM_CLASSES = {
    'person', 'bird', 'cat', 'dog', 'horse', 'sheep',
    'cow', 'elephant', 'bear', 'zebra', 'giraffe'
}


def estimate_temp(frame, x, y, w, h):
    """Estimate temperature from pixel luma inside the bounding box.
    Maps luma 0–255 → 20°C – 45°C (simulated thermal scale).
    On a real thermal camera this would come from raw 16-bit pixel values.
    """
    H, W = frame.shape[:2]
    x1, y1 = max(0, int(x)),    max(0, int(y))
    x2, y2 = min(W, int(x + w)), min(H, int(y + h))
    if x2 <= x1 or y2 <= y1:
        return 30.0
    roi  = frame[y1:y2, x1:x2]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    luma = float(np.mean(gray))
    temp = 20.0 + (luma / 255.0) * 25.0   # 20°C – 45°C
    return round(temp, 1)


class Camera:
    def __init__(self):
        self.cap     = cv2.VideoCapture(0 + cv2.CAP_DSHOW if os.name == 'nt' else 0)
        self.frame   = None
        self.lock    = threading.Lock()
        self.running = True

        yolo_model_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../yolo11n.pt")
        )
        print(f"Loading YOLO Model from: {yolo_model_path}")
        self.detector = HotspotDetector(
            threshold_temp=100.0,
            yolo_model_path=yolo_model_path if os.path.exists(yolo_model_path) else None,
            yolo_confidence=0.25,
        )

        self.thread        = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def _capture_loop(self):
        frame_count = 0
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.1)
                continue

            # Run YOLO tracking (returns Detection dataclasses with tracker IDs)
            detections_out = self.detector.detect(frame)

            detected_objects = []
            for det in detections_out:
                if det.source != "yolo":
                    continue
                label    = getattr(det, 'label', 'unknown')
                max_temp = estimate_temp(frame, det.x, det.y, det.w, det.h)
                severity = "CRITICAL" if label in WARM_CLASSES else "NORMAL"
                detected_objects.append({
                    "id":         getattr(det, 'id', 0),
                    "label":      label,
                    "confidence": getattr(det, 'confidence', 0.0),
                    "x":          det.x,
                    "y":          det.y,
                    "w":          det.w,
                    "h":          det.h,
                    "max_temp":   max_temp,   # ← shown in telemetry sidebar
                    "severity":   severity,
                    "is_scaled":  False,
                })

            # Broadcast detections → Node.js → Socket.io → React telemetry sidebar
            frame_count += 1
            payload = {
                "type":        "detections",
                "detections":  detected_objects,
                "frame_stats": {},
                "count":       frame_count,
                "timestamp":   int(time.time() * 1000),
            }
            try:
                udp_sock.sendto(json.dumps(payload).encode(), (UDP_IP, UDP_PORT))
            except Exception:
                pass

            # Store raw frame (no bounding boxes painted) so the frontend
            # can apply its thermal palette LUT before drawing tracker overlays
            _, buf = cv2.imencode('.jpg', frame)
            if buf is not None:
                with self.lock:
                    self.frame = buf.tobytes()

            time.sleep(0.01)

    def get_frame(self):
        with self.lock:
            return self.frame


camera = Camera()


def gen_frames():
    while True:
        frame = camera.get_frame()
        if frame is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        time.sleep(0.03)


@app.route('/api/snapshot')
def api_snapshot():
    frame = camera.get_frame()
    if frame is None:
        return Response('', status=204)
    return Response(frame, mimetype='image/jpeg')


@app.route('/video_feed/webcam')
def video_feed_webcam():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/video_feed/thermal')
def video_feed_thermal():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


if __name__ == '__main__':
    print("===========================================================")
    print("YOLO Object Tracking API Running on port 5000")
    print("Streaming UDP Detections (with temperature) to port 14560")
    print("===========================================================")
    app.run(host='0.0.0.0', port=5000, threaded=True)
