# 🛸 Aeroluna Thermal Project

**TIOS — Thermal Inspection Operating System**  
A real-time drone-based thermal inspection platform built for aerial surveillance, human/vehicle detection, and mission reporting.

---

## 📁 Project Structure

```
aeroluna thermal project/
├── tios2/                  # Main web application (React + Node.js)
│   ├── frontend/           # React + Vite frontend (port 5173)
│   └── backend/            # Node.js + Socket.io backend (port 4000)
├── thermal_project/        # Python thermal processing scripts
│   ├── dashboard.py        # Thermal dashboard GUI
│   ├── auto_capture.py     # Auto frame capture logic
│   ├── classifier.py       # YOLO-based thermal classifier
│   ├── train_yolo.py       # YOLO model training script
│   ├── gps_mavlink.py      # MAVLink GPS integration
│   └── stream_reader.py    # RTSP stream reader
└── ultralytics-main/       # YOLO11 (Ultralytics) source
```

---

## 🚀 Quick Start

### Prerequisites
- **Node.js** v18+
- **Python** 3.9+
- **FFmpeg** (for RTSP video streaming)
- **npm**

---

### 1. Start the Backend

```bash
cd tios2/backend
npm install
npm run dev
```

Backend runs on **http://localhost:4000**

---

### 2. Start the Frontend

```bash
cd tios2/frontend
npm install
npm run dev
```

Frontend runs on **https://localhost:5173**

> ⚠️ The frontend uses HTTPS (self-signed cert via `@vitejs/plugin-basic-ssl`). Accept the browser warning on first launch.

---

### 3. (Optional) Start the Drone Bridge

For live MAVLink drone telemetry:

```bash
cd tios2/backend
python drone_bridge.py
```

---

## ⚙️ Configuration

### Backend — `tios2/backend/.env`

```env
PORT=4000
FRONTEND_URL=http://localhost:5173

# RTSP streams (leave blank for simulation mode)
THERMAL_RTSP_URL=rtsp://192.168.144.108:555/stream=2
RGB_RTSP_URL=rtsp://192.168.144.108:554/stream=1

# MAVLink: simulation | udp | lan | serial
MAVLINK_CONNECTION=lan
LAN_UDP_PORT=14555

# FFmpeg path
FFMPEG_PATH=C:\path\to\ffmpeg.exe
```

### Frontend — `tios2/frontend/.env`

```env
VITE_BACKEND_URL=http://localhost:4000
VITE_THERMAL_WS_URL=ws://localhost:9999
VITE_RGB_WS_URL=ws://localhost:9998
```

---

## 🔧 Features

| Feature | Description |
|---|---|
| 🌡️ **Dual Video Panels** | Live Thermal + RGB camera feeds side-by-side |
| 📡 **Telemetry Dashboard** | Real-time GPS, altitude, speed, battery via MAVLink |
| 📸 **Frame Capture** | One-click capture of both thermal + RGB frames with telemetry snapshot |
| 🗺️ **Offline Map** | Leaflet map with capture location pins |
| 📄 **PDF Report** | Auto-generated inspection report from all captures |
| 📊 **CSV Export** | Export all capture metadata as CSV |
| 🤖 **YOLO11 Detection** | Real-time human/vehicle detection via Python pipeline |
| 📱 **Mobile Support** | Responsive layout with mobile telemetry drawer |

---

## 🧠 YOLO / ML Pipeline

```bash
cd thermal_project

# Train YOLO model
python train_yolo.py

# Run classifier on thermal frames
python classifier.py

# Auto-capture from stream
python auto_capture.py
```

The Python pipeline sends detections to the Node.js backend via UDP (port 14560), which broadcasts them to the frontend via Socket.io.

---

## 🐛 Troubleshooting

### TIOS not opening?

1. Make sure backend is running: `cd tios2/backend && npm run dev`
2. Make sure frontend is running: `cd tios2/frontend && npm run dev`
3. Open the URL shown in the frontend terminal (e.g. `https://localhost:5173`)
4. Accept the self-signed certificate warning in your browser

### Port already in use?

Kill stale Node processes:
```powershell
Get-Process node | Stop-Process -Force
```

Then restart both servers.

### Video not showing?

- Set your RTSP URLs in `tios2/backend/.env`
- Ensure FFmpeg is installed and its path is correct in `.env`
- Leave RTSP URLs blank to run in **simulation mode**

---

## 📦 Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, Tailwind CSS, Leaflet |
| Backend | Node.js, Express, Socket.io |
| ML / Vision | YOLO11 (Ultralytics), OpenCV |
| Video | FFmpeg, RTSP, WebSocket |
| Telemetry | MAVLink, UDP |
| Reporting | jsPDF, Python PDF generation |

---

## 👨‍💻 Author

**Aeroluna** — Thermal Inspection Platform  
GitHub: [amogha-prog/thermal_project](https://github.com/amogha-prog/thermal_project)

---

## 📜 License

MIT License — Open for research and development use.
