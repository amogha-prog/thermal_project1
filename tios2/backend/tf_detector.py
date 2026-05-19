import cv2
import numpy as np
import time
import os
from flask import Flask, Response
from flask_cors import CORS

# Get the absolute path to the directory containing this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Path to the TensorFlow model files
PB_FILE = os.path.join(SCRIPT_DIR, 'ssd_mobilenet_v2_coco_2018_03_29', 'frozen_inference_graph.pb')
PBTXT_FILE = os.path.join(SCRIPT_DIR, 'ssd_mobilenet_v2_coco_2018_03_29.pbtxt')

if not os.path.exists(PB_FILE) or not os.path.exists(PBTXT_FILE):
    print("====================================================================")
    print("ERROR: TensorFlow model files not found.")
    print("Please make sure the frozen_inference_graph.pb and .pbtxt files are present.")
    print("====================================================================")
    import sys
    sys.exit(1)

print("Loading TensorFlow Object Detection Model via OpenCV DNN...")
net = cv2.dnn.readNetFromTensorflow(PB_FILE, PBTXT_FILE)
net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
print("Model loaded successfully!")

# COCO Dataset class mapping (SSD MobileNet V2 returns class indices 1-90)
CLASSES = {
    1: 'person', 2: 'bicycle', 3: 'car', 4: 'motorcycle', 5: 'airplane',
    6: 'bus', 7: 'train', 8: 'truck', 9: 'boat', 10: 'traffic light',
    16: 'bird', 17: 'cat', 18: 'dog', 19: 'horse', 20: 'sheep', 21: 'cow',
}

def draw_detections(frame, detections, min_score=0.4):
    """Draws bounding boxes and labels on the frame from DNN detection results."""
    height, width, _ = frame.shape
    
    for i in range(detections.shape[2]):
        score = detections[0, 0, i, 2]
        if score >= min_score:
            class_id = int(detections[0, 0, i, 1])
            label = CLASSES.get(class_id, f'Obj:{class_id}')
            score_percent = int(score * 100)
            
            xmin = int(detections[0, 0, i, 3] * width)
            ymin = int(detections[0, 0, i, 4] * height)
            xmax = int(detections[0, 0, i, 5] * width)
            ymax = int(detections[0, 0, i, 6] * height)
            
            color = (0, 0, 255) if label == 'person' else (0, 255, 0)
            cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), color, 2)
            cv2.putText(frame, f"{label} {score_percent}%", (xmin, ymin - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    return frame

app = Flask(__name__)
CORS(app)

def run_detection_stream(source, is_rtsp=False):
    cap = cv2.VideoCapture(source)
    if is_rtsp:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
    prev_time = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            if is_rtsp:
                time.sleep(1)
                cap = cv2.VideoCapture(source)
                continue
            else:
                break
                
        blob = cv2.dnn.blobFromImage(frame, size=(300, 300), swapRB=True, crop=False)
        net.setInput(blob)
        detections = net.forward()
        output_frame = draw_detections(frame, detections)
        
        curr_time = time.time()
        if curr_time - prev_time > 0:
            fps = 1 / (curr_time - prev_time)
            cv2.putText(output_frame, f"TF FPS: {fps:.1f}", (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 0), 2)
        prev_time = curr_time
        
        ret, buffer = cv2.imencode('.jpg', output_frame)
        if ret:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

@app.route('/video_feed/webcam')
def video_feed_webcam():
    source = 0 + cv2.CAP_DSHOW if os.name == 'nt' else 0
    return Response(run_detection_stream(source, False), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/video_feed/thermal')
def video_feed_thermal():
    url = os.environ.get('THERMAL_RTSP_URL', 'rtsp://192.168.144.25:8554/main.264')
    return Response(run_detection_stream(url, True), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    print("===========================================================")
    print("TensorFlow Object Detection API Running on port 5000")
    print("Webcam stream: http://localhost:5000/video_feed/webcam")
    print("Thermal stream: http://localhost:5000/video_feed/thermal")
    print("===========================================================")
    app.run(host='0.0.0.0', port=5000, threaded=True)
