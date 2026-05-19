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

class Camera:
    def __init__(self):
        self.cap = cv2.VideoCapture(0 + cv2.CAP_DSHOW if os.name == 'nt' else 0)
        self.frame = None
        self.lock = threading.Lock()
        self.running = True
        
        yolo_model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../yolo11n.pt"))
        print(f"Loading YOLO Model from: {yolo_model_path}")
        self.detector = HotspotDetector(
            threshold_temp=100.0, 
            yolo_model_path=yolo_model_path if os.path.exists(yolo_model_path) else None,
            yolo_confidence=0.4
        )
        
        self.thread = threading.Thread(target=self._capture_loop)
        self.thread.daemon = True
        self.thread.start()
        
    def _capture_loop(self):
        frame_count = 0
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.1)
                continue
                
            # Run YOLO Tracking
            # HotspotDetector returns a list of Detection dataclasses
            # It internally calls self._yolo_model.track(...) so IDs are preserved
            detections_out = self.detector.detect(frame)
            
            detected_objects = []
            for det in detections_out:
                if det.source == "yolo":
                    detected_objects.append({
                        "id": getattr(det, 'id', 0),
                        "label": getattr(det, 'label', 'unknown'),
                        "confidence": getattr(det, 'confidence', 0.0),
                        "x": det.x, "y": det.y, "w": det.w, "h": det.h,
                        "is_scaled": True
                    })
            
            # Broadcast detections to the WebApp via UDP
            frame_count += 1
            payload = {
                "type": "detections",
                "detections": detected_objects,
                "frame_stats": {},
                "count": frame_count,
                "timestamp": int(time.time() * 1000)
            }
            try:
                udp_sock.sendto(json.dumps(payload).encode('utf-8'), (UDP_IP, UDP_PORT))
            except:
                pass
                
            # Yield raw frame so frontend can apply thermal palette
            ret, buffer = cv2.imencode('.jpg', frame)
            if ret:
                with self.lock:
                    self.frame = buffer.tobytes()
                    
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

@app.route('/video_feed/webcam')
def video_feed_webcam():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/video_feed/thermal')
def video_feed_thermal():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    print("===========================================================")
    print("YOLO Object Tracking API Running on port 5000")
    print("Streaming UDP Detections to WebApp Backend on port 14560")
    print("===========================================================")
    app.run(host='0.0.0.0', port=5000, threaded=True)
