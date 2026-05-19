# Aeroluna Thermal Project (TIOS2)

Welcome to the **Aeroluna Thermal Project**, featuring the next-generation **TIOS2 (Thermal Imaging Operations System)**. This project provides a robust, high-performance web application designed for real-time thermal object detection, advanced telemetry synchronization, and precision drone geotagging.

## 🚀 Key Features

*   **Real-Time Object Detection & Tracking**: Features a high-performance detection pipeline utilizing both YOLO and TensorFlow MobileNet SSD models to accurately track and identify targets (e.g., animals, distinct heat signatures).
*   **Dynamic Telemetry Dashboard**: A completely redesigned React-based UI (TIOS2 Frontend) that bridges live video feeds with real-time drone metrics, attitude data, and telemetry synchronization via UDP.
*   **Advanced Drone Geotagging**: Sub-100ms precision geotagging system syncing system clocks with GPS time, allowing for extremely accurate thermal and RGB photo captures.
*   **Comprehensive PDF Reporting**: Automatically generates professional flight and capture reports embedding high-resolution imagery, Google Maps location links, UTC/Local synchronized timestamps, and target classification metadata.
*   **Dual Camera Support**: Includes a Python-based backend that effectively parses live RTSP thermal feeds alongside localized webcam inputs, supporting advanced palettes like "White Hot" and "Black Hot".

## 📁 Repository Structure

*   `tios2/`: Contains the complete TIOS2 Web Application.
    *   `frontend/`: The React + Vite interface offering dynamic tracking, mapping, and telemetry visualization.
    *   `backend/`: The Flask and Node.js-powered relay servers handling video streams, MAVLink parsing, and AI inference via Python.
*   `tensorflow-master/`: Complete TensorFlow source mapping, included for deep system integration, custom op building, and ensuring local dependency alignment for the edge computing environment.

## ⚙️ Getting Started

### Prerequisites
*   Node.js (v16+)
*   Python (3.8+)
*   FFmpeg (for RTSP video stream relays)

### Installation & Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/amogha-prog/thermal_project1.git
    cd thermal_project1
    ```

2.  **Start the Backend:**
    ```bash
    cd tios2/backend
    pip install -r requirements.txt
    npm install
    npm start
    ```

3.  **Start the Frontend:**
    ```bash
    cd ../frontend
    npm install
    npm run dev
    ```

## 🧠 AI Detection System

The backend employs a hybridized AI framework leveraging `tf_detector.py` and `patch_yolo_draw.py` to draw precise bounding boxes with continuous ID tracking. It also calculates luma-based temperature estimations for bounding boxes over thermal streams.

## 🗺️ Geotagging & Telemetry

The TIOS2 platform communicates with the drone via MAVLink. The `drone_bridge.py` and associated TimeSync buffers align drone attitude, GPS coordinates, and capture commands perfectly to guarantee the telemetry aligns with the exact frame the thermal snapshot was taken.

---
*Developed by amogh-aero.*
