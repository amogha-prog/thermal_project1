<div align="center">
  <img src="https://img.icons8.com/color/150/000000/drone-with-camera.png" alt="Drone Icon" width="100"/>

  # 🚁 Aeroluna Thermal Project
  **Next-Generation TIOS2 (Thermal Imaging Operations System)**

  *A robust, high-performance web application designed for real-time thermal object detection, advanced telemetry synchronization, and precision drone geotagging.*

  <p align="center">
    <img src="https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" alt="React" />
    <img src="https://img.shields.io/badge/Node.js-339933?style=for-the-badge&logo=nodedotjs&logoColor=white" alt="Node.js" />
    <img src="https://img.shields.io/badge/Python-FFD43B?style=for-the-badge&logo=python&logoColor=blue" alt="Python" />
    <img src="https://img.shields.io/badge/TensorFlow-FF6F00?style=for-the-badge&logo=tensorflow&logoColor=white" alt="TensorFlow" />
    <img src="https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white" alt="Flask" />
  </p>
</div>

---

## 🌟 Key Features

| Feature | Description |
| :--- | :--- |
| 🎯 **Real-Time Tracking** | High-performance detection pipeline utilizing **YOLO** and **TensorFlow MobileNet SSD** models to accurately track and identify targets (e.g., animals, distinct heat signatures). |
| 📊 **Dynamic Dashboard** | A beautifully redesigned React-based UI that bridges live video feeds with real-time drone metrics, attitude data, and telemetry synchronization via UDP. |
| 📍 **Precision Geotagging** | Sub-100ms precision geotagging system syncing system clocks with GPS time, allowing for extremely accurate thermal and RGB photo captures. |
| 📄 **Automated PDF Reports** | Automatically generates professional flight reports embedding high-resolution imagery, Google Maps links, synchronized timestamps, and target classification metadata. |
| 🎥 **Dual Camera Support** | Python backend effectively parses live RTSP thermal feeds alongside localized webcam inputs, supporting palettes like **"White Hot"** and **"Black Hot"**. |

---

## 📂 Repository Structure

```text
📦 thermal_project1
 ┣ 📂 tios2/                     # Complete TIOS2 Web Application
 ┃ ┣ 📂 frontend/                # React + Vite interface (UI, Maps, Telemetry)
 ┃ ┗ 📂 backend/                 # Flask & Node.js relay servers (Video Streams, MAVLink, AI)
 ┗ 📂 tensorflow-master/         # Complete TensorFlow source mapping for edge environments
```

---

## 🚀 Getting Started

### 📋 Prerequisites

Ensure you have the following installed on your machine:
- **Node.js** (v16 or higher)
- **Python** (3.8 or higher)
- **FFmpeg** (Required for RTSP video stream relays)

### 🛠️ Installation & Setup

**1. Clone the repository:**
```bash
git clone https://github.com/amogha-prog/thermal_project1.git
cd thermal_project1
```

**2. Start the Backend Server:**
```bash
cd tios2/backend
pip install -r requirements.txt
npm install
npm start
```

**3. Start the Frontend Dashboard:**
```bash
cd ../frontend
npm install
npm run dev
```

---

## 🧠 Technical Deep-Dive

### AI Detection System
The backend employs a hybridized AI framework leveraging `tf_detector.py` and `patch_yolo_draw.py`. This system draws precise bounding boxes with continuous ID tracking and calculates **luma-based temperature estimations** directly over thermal streams.

### Geotagging & Telemetry Bridge
The TIOS2 platform communicates with the drone via MAVLink. The `drone_bridge.py` and associated TimeSync buffers perfectly align drone attitude, GPS coordinates, and capture commands. This guarantees that the telemetry matches the *exact microsecond* the thermal snapshot was taken.

---

<div align="center">
  <b>Developed with ❤️ by <a href="https://github.com/amogh-aero">amogh-aero</a></b>
</div>
