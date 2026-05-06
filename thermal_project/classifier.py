import cv2
import numpy as np

# Install: pip install ultralytics
# Model:   yolov8n.pt  (pretrained) — retrain on FLIR ADAS thermal dataset
#          for best thermal accuracy use: yolov8n-thermal.pt (community)
# Download FLIR dataset: https://www.flir.com/oem/adas/adas-dataset-form/

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False

CONFIDENCE_THRESHOLD = 0.50

# Map YOLO COCO class IDs to your 3 target categories
HUMAN_IDS   = {0}               # person
ANIMAL_IDS  = {14,15,16,17,18,19,20,21,22,23}  # bird,cat,dog,horse,sheep,cow,elephant,bear,zebra
VEHICLE_IDS = {2,3,5,7}         # car, motorcycle, bus, truck

class TargetClassifier:
    def __init__(self, model_path="yolov8n.pt"):
        if YOLO_AVAILABLE:
            self.model = YOLO(model_path)
        else:
            self.model = None
            print("[WARN] ultralytics not installed — using heuristic classifier")

    def _heuristic_classify(self, blob, thermal_crop):
        # Fallback when YOLO unavailable: classify by blob shape + size
        x, y, w, h = blob["bbox"]
        area = blob["area"]
        ar   = w / h if h > 0 else 1
        # Humans: taller than wide, medium area
        if ar < 0.8 and 80 < area < 1200:
            return "human", 0.6
        # Vehicles: much wider than tall, large area
        if ar > 1.5 and area > 600:
            return "vehicle", 0.55
        return "animal", 0.5

    def classify(self, blob, thermal_frame, visible_frame):
        x, y, w, h     = blob["bbox"]
        thermal_crop   = thermal_frame[y:y+h, x:x+w]

        if not YOLO_AVAILABLE or self.model is None:
            label, conf = self._heuristic_classify(blob, thermal_crop)
            return label, conf

        # Run YOLO on the visible-light crop (higher res, better for YOLO)
        # Scale bbox from thermal (384x288) to visible (1280x720)
        sx = 1280 / 384
        sy = 720  / 288
        vx, vy = int(x*sx), int(y*sy)
        vw, vh = int(w*sx), int(h*sy)
        vis_crop = visible_frame[vy:vy+vh, vx:vx+vw]

        results = self.model(vis_crop, verbose=False)
        for r in results:
            for box in r.boxes:
                cid  = int(box.cls)
                conf = float(box.conf)
                if conf < CONFIDENCE_THRESHOLD:
                    continue
                if cid in HUMAN_IDS:
                    return "human", conf
                if cid in ANIMAL_IDS:
                    return "animal", conf
                if cid in VEHICLE_IDS:
                    return "vehicle", conf
        return "unknown", 0.0