import cv2
import numpy as np
import time
import os
import json
import socket
import threading
from flask import Flask, Response
from flask_cors import CORS

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PB_FILE = os.path.join(SCRIPT_DIR, 'ssd_mobilenet_v2_coco_2018_03_29', 'frozen_inference_graph.pb')
PBTXT_FILE = os.path.join(SCRIPT_DIR, 'ssd_mobilenet_v2_coco_2018_03_29.pbtxt')

print("Loading TensorFlow Object Detection Model via OpenCV DNN...")
net = cv2.dnn.readNetFromTensorflow(PB_FILE, PBTXT_FILE)
net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

CLASSES = {
    1: 'person', 2: 'bicycle', 3: 'car', 4: 'motorcycle', 5: 'airplane',
    6: 'bus', 7: 'train', 8: 'truck', 9: 'boat', 10: 'traffic light',
    16: 'bird', 17: 'cat', 18: 'dog', 19: 'horse', 20: 'sheep', 21: 'cow',
}

app = Flask(__name__)
CORS(app)

UDP_IP = "127.0.0.1"
UDP_PORT = 14560
udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

class Camera:
    def __init__(self):
        # We use a single camera instance to serve both webapp panels without crashing Windows
        self.cap = cv2.VideoCapture(0 + cv2.CAP_DSHOW if os.name == 'nt' else 0)
        self.frame = None
        self.lock = threading.Lock()
        self.running = True
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
                
            # Run TF Object Detection
            blob = cv2.dnn.blobFromImage(frame, size=(300, 300), swapRB=True, crop=False)
            net.setInput(blob)
            detections_out = net.forward()
            
            height, width, _ = frame.shape
            detected_objects = []
            
            for i in range(detections_out.shape[2]):
                score = float(detections_out[0, 0, i, 2])
                if score >= 0.4:
                    class_id = int(detections_out[0, 0, i, 1])
                    label = CLASSES.get(class_id, f'Obj:{class_id}')
                    
                    xmin = float(detections_out[0, 0, i, 3] * width)
                    ymin = float(detections_out[0, 0, i, 4] * height)
                    xmax = float(detections_out[0, 0, i, 5] * width)
                    ymax = float(detections_out[0, 0, i, 6] * height)
                    
                    detected_objects.append({
                        "severity": "CRITICAL" if label == 'person' else "NORMAL",
                        "label": label,
                        "x": xmin, "y": ymin, "w": xmax - xmin, "h": ymax - ymin,
                        "max_temp": 37.0 if label == 'person' else 25.0,
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
                
            # We DO NOT draw bounding boxes onto the raw image here!
            # The webapp must receive the raw frame so it can apply the thermal LUT!
            # The webapp will dynamically draw the UDP bounding boxes ON TOP of the thermal feed.
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
        time.sleep(0.03) # ~30fps stream

@app.route('/video_feed/webcam')
def video_feed_webcam():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/video_feed/thermal')
def video_feed_thermal():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    print("===========================================================")
    print("TensorFlow Object Detection API Running on port 5000")
    print("Streaming UDP Detections to WebApp Backend on port 14560")
    print("===========================================================")
    app.run(host='0.0.0.0', port=5000, threaded=True)
