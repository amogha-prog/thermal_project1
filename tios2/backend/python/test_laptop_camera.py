import cv2
import time
import logging
import os
import sys

# Ensure local modules can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hotspot_detector import HotspotDetector

def draw_tracker(frame, detections):
    vis = frame.copy()
    for det in detections:
        # Only draw YOLO tracking objects
        if det.source != "yolo":
            continue
            
        color = (0, 255, 0) # Green for objects

        # Bounding box
        cv2.rectangle(vis, (det.x, det.y), (det.x + det.w, det.y + det.h), color, 2)

        # Label with Tracker ID and Class Name (no temperature)
        label = f"ID:{det.id} {det.label} [{det.confidence:.0%}]"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(vis, (det.x, det.y - th - 8), (det.x + tw + 4, det.y), color, -1)
        cv2.putText(vis, label, (det.x + 2, det.y - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

    return vis

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger("CameraTest")

    # 1. Initialize OpenCV VideoCapture with DirectShow (fixes camera issues on Windows)
    logger.info("Initializing laptop camera (device 0) using DirectShow...")
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    
    if not cap.isOpened():
        # Fallback to standard 0 if DSHOW fails
        logger.warning("DirectShow failed, trying standard backend...")
        cap = cv2.VideoCapture(0)
        
    if not cap.isOpened():
        logger.error("Failed to connect to the laptop camera. Please check permissions or device manager.")
        return

    # Try setting resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # 2. Initialize HotspotDetector
    logger.info("Initializing Object Detector...")
    yolo_model_path = os.path.join(os.path.dirname(__file__), "yolo11n.pt")
    
    detector = HotspotDetector(
        threshold_temp=100.0, # Set very high so CV Hotspot doesn't trigger on regular lights
        yolo_model_path=yolo_model_path if os.path.exists(yolo_model_path) else None,
        yolo_confidence=0.4
    )

    logger.info("Starting detection loop. Press 'q' to quit.")

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                logger.warning("Failed to grab frame. Retrying...")
                time.sleep(0.1)
                continue

            # Run the detection pipeline
            detections = detector.detect(frame)

            # Draw the custom tracker bounding boxes (no temperature)
            vis_frame = draw_tracker(frame, detections)

            # Display the result in an OpenCV window
            cv2.imshow("TIOS Object Tracking - Laptop Camera", vis_frame)

            # Exit if 'q' is pressed
            if cv2.waitKey(1) & 0xFF == ord('q'):
                logger.info("'q' pressed, exiting...")
                break

    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    finally:
        logger.info("Cleaning up...")
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
