# 🛸 Aeroluna Thermal Project

**TIOS — Thermal Inspection Operating System**  
A real-time drone-based thermal inspection platform built for aerial surveillance, human/vehicle detection, and mission reporting.

---

## 📁 Project Structure

```
aeroluna thermal project/
├── tios2/                  # Main web application
│   ├── frontend/           # React + Vite frontend (port 5173)
│   └── backend/            # Node.js + Socket.io backend (port 4000)
│       ├── python/         # ML Pipeline & Thermal Analysis
│       │   ├── main.py     # Main thermal processing entry point
│       │   ├── hotspot_detector.py # Thermal hotspot detection logic
│       │   ├── generate_report.py  # PDF Inspection Report generator
│       │   └── classifier.py # YOLO11 thermal object detection
│       ├── drone_bridge.py # MAVLink UDP bridge
│       ├── wake_drone.py   # Telemetry request tool
│       └── debug_udp.py    # MAVLink packet inspector
├── captures/               # Synced thermal/RGB image captures
└── yolo11n.pt              # Base YOLO detection model
```

---

## 🚀 Quick Start

### 1. Start the Backend
```bash
cd tios2/backend
npm run dev
```

### 2. Start the Frontend
```bash
cd tios2/frontend
npm run dev
```

### 3. Initialize Telemetry
If the drone telemetry is not flowing (e.g., SkyDroid/Herelink), use the wake-up tool:
```bash
cd tios2/backend
python wake_drone.py
```

---

## 🔧 Features

| Feature | Description |
|---|---|
| 🌡️ **Dual Video Panels** | Live Thermal + RGB camera feeds side-by-side |
| 📡 **Telemetry Dashboard** | Real-time GPS, altitude, speed, battery via MAVLink |
| 📸 **Auto-Capture** | Intelligent frame capture based on detection confidence |
| 🗺️ **Interactive Map** | Leaflet map with real-time drone positioning and capture pins |
| 📄 **Automated PDF** | Professional inspection reports with thermal overlays and GPS metadata |
| 🤖 **YOLO11 Detection** | State-of-the-art human/vehicle detection for thermal streams |
| 🛠️ **Telemetry Tools** | Built-in scripts for waking drone streams and debugging UDP packets |

---

## 🧠 ML / Vision Pipeline

The Python pipeline (`tios2/backend/python/main.py`) handles:
1. **RTSP Ingestion**: Pulling frames from dual cameras.
2. **Detection**: YOLO11 inference for object identification.
3. **Hotspot Analysis**: Identifying temperature anomalies in thermal frames.
4. **Data Sync**: Sending detections and status to Node.js via UDP port 14560.

---

## 🐛 Troubleshooting & Debugging

### Telemetry Issues?
1. **Check UDP Port**: Ensure your drone/controller is sending MAVLink to the correct port (default 14555).
2. **Wake the Stream**: Some controllers require a request signal. Run `python tios2/backend/wake_drone.py`.
3. **Inspect Packets**: Run `python tios2/backend/debug_udp.py` to see raw MAVLink data flowing into the system.

### Report Generation
Reports are saved in `tios2/backend/python/captures/`. Ensure you have the required Python libraries installed:
```bash
pip install -r tios2/backend/python/requirements.txt
```

---

## 📦 Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, Tailwind CSS, Leaflet |
| Backend | Node.js, Express, Socket.io |
| ML / Vision | YOLO11 (Ultralytics), OpenCV, NumPy |
| Video | FFmpeg, RTSP, WebSocket |
| Telemetry | MAVLink (pymavlink), UDP |
| Reporting | FPDF2 (Python-based PDF generation) |

---

## 👨‍💻 Author

**Aeroluna** — Thermal Inspection Platform  
GitHub: [amogha-prog/thermal_project1](https://github.com/amogha-prog/thermal_project1)

---

## 📜 License

MIT License — Includes third-party library acknowledgments in [LICENSE-THIRD-PARTY.md](tios2/LICENSE-THIRD-PARTY.md).
