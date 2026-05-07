# TIOS v2 — Thermal Inspection Operating System

> **No Database · All Files Saved Locally · v2 Geotag Engine**

---

## Table of Contents

1. [How Storage Works](#how-storage-works)
2. [Project Structure](#project-structure)
3. [Quick Start](#quick-start)
4. [Connecting a Real Drone](#connecting-a-real-drone)
5. [v2 Geotag Engine](#v2-geotag-engine)
6. [MAVLink Bridge (drone_bridge.py)](#mavlink-bridge-drone_bridgepy)
7. [Port Map](#port-map)
8. [Configuration & Tuning](#configuration--tuning)
9. [UI Buttons](#ui-buttons)
10. [Field Deployment](#field-deployment)
11. [Common Errors](#common-errors)

---

## How Storage Works

| What | Where it goes |
|---|---|
| Capture data (session) | React memory (Zustand) — lost on browser refresh |
| Individual JPEG images | Your Downloads folder (browser download API) |
| PDF inspection report | Your Downloads folder (browser download API) |
| Nothing | No server, no database, no cloud |

---

## Project Structure

```
tios2/
├── package.json                      ← root scripts (install:all, dev)
│
├── backend/
│   ├── .env                          ← MAVLink + RTSP + port config
│   ├── drone_bridge.py               ★ PRIMARY MAVLink bridge (v2 engine)
│   ├── wake_drone.py                 ← Controller wake-up tool
│   ├── debug_udp.py                  ← Raw MAVLink packet inspector
│   │
│   ├── src/
│   │   ├── server.js                 ← Express + Socket.io server
│   │   ├── mavlink/
│   │   │   └── mavlinkParser.js      ← simulation / udp / serial / lan modes
│   │   ├── stream/
│   │   │   └── streamRelay.js        ← RTSP → FFmpeg → WebSocket
│   │   └── python/
│   │       └── pythonBridge.js       ← detection UDP receiver (port 14560)
│   │
│   └── python/
│       ├── main.py                   ← ML pipeline orchestrator
│       ├── hotspot_detector.py       ← thermal anomaly detection
│       ├── classifier.py             ← YOLO11 inference + severity
│       ├── false_positive_filter.py  ← persistence + spatial validation
│       ├── auto_capture.py           ← anomaly-triggered capture + geotag
│       ├── stream_reader.py          ← dual RTSP ingestion
│       ├── generate_report.py        ← FPDF2 PDF report generator
│       └── gps_mavlink.py            ← standalone bridge (legacy, not used)
│
└── frontend/
    ├── .env                          ← VITE_BACKEND_URL
    └── src/
        ├── App.jsx                   ← root layout + capture/PDF logic
        ├── store/
        │   └── useTIOSStore.js       ← all global state (Zustand)
        ├── hooks/
        │   └── useSocket.js          ← Socket.io telemetry sync
        ├── utils/
        │   ├── captureEngine.js      ← frame grab + capture unit builder
        │   └── pdfGenerator.js       ← jsPDF report → browser download
        └── components/
            ├── TopBar.jsx
            ├── ScanBar.jsx
            ├── ToastContainer.jsx
            ├── video/VideoPanel.jsx
            ├── telemetry/TelemetrySidebar.jsx
            └── capture/CaptureModal.jsx
```

---

## Quick Start

### Step 1 — Install Node.js
Download from https://nodejs.org (LTS version).  
Verify: `node --version`

### Step 2 — Install all dependencies
```bash
cd tios2
npm run install:all
```

### Step 3 — Install Python dependencies
```bash
pip install pymavlink fpdf2 opencv-python numpy ultralytics
```

### Step 4 — Run (two terminals)
```bash
# Terminal 1 — Backend
cd tios2/backend
npm run dev

# Terminal 2 — Frontend
cd tios2/frontend
npm run dev
```
Open **http://localhost:5173**

### Step 5 — Start MAVLink geotag bridge (third terminal)
```bash
cd tios2/backend
python drone_bridge.py
```

---

## Connecting a Real Drone

### Step 1 — Set RTSP URLs in `backend/.env`
```env
THERMAL_RTSP_URL=rtsp://192.168.144.108:555/stream=2
RGB_RTSP_URL=rtsp://192.168.144.108:554/stream=1
```

### Step 2 — Set MAVLink connection in `backend/.env`
```env
# SkyDroid H12 / Herelink / any LAN relay → use drone_bridge.py
MAVLINK_CONNECTION=lan
LAN_UDP_PORT=14556

# Direct UDP (Mission Planner / QGroundControl relay)
MAVLINK_CONNECTION=udp
MAVLINK_UDP_PORT=14550

# Serial
MAVLINK_CONNECTION=serial
MAVLINK_SERIAL_PORT=COM3
MAVLINK_BAUD_RATE=57600
```

### Step 3 — Install FFmpeg
- Windows: https://ffmpeg.org/download.html → add to PATH
- Mac: `brew install ffmpeg`
- Linux: `sudo apt install ffmpeg`

### Step 4 — Run drone_bridge.py
```bash
# Default (150ms camera latency):
python drone_bridge.py

# Custom camera latency:
$env:VIDEO_LATENCY = "0.120"
python drone_bridge.py
```

---

## v2 Geotag Engine

The geotag system in `drone_bridge.py` is powered by the `v2/` modules.

### How it works

```
GLOBAL_POSITION_INT → GPSBuffer.add(boot_to_utc(boot_ms), snapshot)
ATTITUDE            → AttitudeBuffer.add(boot_to_utc(boot_ms), snapshot)
SYSTEM_TIME         → TimeSync.update(gps_unix, boot_ms)

On capture:
  frame_time  = to_drone_time(monotonic − VIDEO_LATENCY)
  query_time  = frame_time − EKF_DELAY
  pos         = GPSBuffer.interpolate(query_time)      ← NED kinematic
  att         = AttitudeBuffer.interpolate(query_time) ← angle-safe
  → metadata dict
```

### Time rule
> Every geotag timestamp uses `monotonic → GPS epoch`. Never `time.time()`.

### Geotag guards (capture blocked if):
1. GPS buffer < 10 samples — *warmup period*
2. Sync not locked OR SYSTEM_TIME age > 2 s
3. Frame time outside GPS data range ± 100 ms

### Geotag metadata output
```python
{
  "timestamp": { "utc", "ist", "epoch", "query_epoch" },
  "position":  { "lat", "lon", "alt_msl", "alt_agl" },
  "velocity":  { "vx", "vy", "vz", "ground_speed" },   # m/s NED
  "attitude":  { "roll", "pitch", "yaw" },               # radians
  "heading":   { "body", "autopilot", "cog" },           # degrees
  "battery":   { "voltage" },
}
```

### EKF Delay Calibration (first-time setup)
```bash
# Run offline with flight log data:
cd v2
python calibration/ekf_delay_calibrator.py
# → Prints best EKF_DELAY value
# → Update EKF_DELAY in v2/frame_tagger.py
```

---

## MAVLink Bridge (drone_bridge.py)

### Startup sequence
1. Tries `udpin:0.0.0.0:14550`, then `:14555` — rotates on failure
2. Requests `SYSTEM_TIME` stream at 1 Hz from FC
3. If no SYSTEM_TIME after 5 s → wall-clock bootstrap
4. Streams telemetry JSON to Node.js at 25 Hz (UDP :14556)
5. Geotag query server (UDP :14557) answers `auto_capture.py` queries

### Health output (every 3 s)
```
[13:35:24] DATA RATES | GPS: 10.0 Hz (Age: 0.3s) | Attitude: 50.0 Hz (Age: 0.1s)
[13:35:24] SYNC | Offset: 1778046456097.6 ms | Locked: True | Drift: 0.05 ms/s | EKF_DELAY: 100 ms | VIDEO_LATENCY: 150 ms
```

### Healthy values

| Field | Healthy | Action if unhealthy |
|---|---|---|
| GPS Hz | ≥ 5 Hz | Check MAVLink stream rates on FC |
| Attitude Hz | ≥ 10 Hz | Check `SR_EXTRA1` stream rate |
| Locked | `True` | Wait for SYSTEM_TIME or check GPS fix |
| Drift | < 1.0 ms/s | Check GPS antenna, RF interference |

---

## Port Map

| Port | Protocol | Direction | Purpose |
|---|---|---|---|
| 14550 | UDP | FC → Bridge | MAVLink (primary) |
| 14555 | UDP | FC → Bridge | MAVLink (fallback) |
| 14556 | UDP | Bridge → Node | Telemetry JSON @ 25 Hz |
| 14557 | UDP | auto_capture ↔ Bridge | Geotag query/response |
| 14560 | UDP | Python pipeline → Node | Detection events |
| 4000 | HTTP/WS | Node → Browser | REST + Socket.io |
| 5173 | HTTP | Vite → Browser | React dev server |

---

## Configuration & Tuning

### Runtime
```bash
VIDEO_LATENCY=0.120 python drone_bridge.py
```

| Variable | Default | Description |
|---|---|---|
| `VIDEO_LATENCY` | `0.150` | Camera pipeline lag (s) |

### Compile-time (`v2/frame_tagger.py`)
| Constant | Default | Description |
|---|---|---|
| `EKF_DELAY` | `0.10` s | FC EKF output latency — calibrate before flight |

### GPS Buffer tuning (`v2/buffers.py`)
| Constant | Default |
|---|---|
| `MAX_SPEED` | 8.0 m/s |
| `SOFT_SPEED` | 5.0 m/s |
| `MAX_ACCEL` | 5.0 m/s² |
| `MAX_ANCHOR_DIST` | 10.0 m |
| `max_gap` | 0.35 s |

---

## UI Buttons

| Button | What it does |
|---|---|
| ● CAPTURE | Grabs both video frames + GPS + all telemetry at that exact moment |
| ↓ IMAGES | Downloads thermal + RGB of the latest capture as JPEG |
| ↓ PDF REPORT | Builds full A4 inspection report → saves to Downloads |
| SWAP | Swaps thermal and RGB panels |
| Click thumbnail | Opens full detail modal for any capture |
| SAVE IMAGES (modal) | Downloads that specific capture's images |

---

## Field Deployment (no internet, local Wi-Fi)

1. Run backend on a Raspberry Pi or laptop
2. Create a Wi-Fi hotspot on that device
3. Update `frontend/.env`:
   ```
   VITE_BACKEND_URL=http://192.168.x.x:4000
   VITE_THERMAL_WS_URL=ws://192.168.x.x:9999
   VITE_RGB_WS_URL=ws://192.168.x.x:9998
   ```
4. Build the frontend: `npm run build`
5. Serve from backend by adding to `server.js`:
   ```js
   app.use(express.static(path.join(__dirname, '../../frontend/dist')));
   ```
6. Run `npm start` on device — connect tablet/phone to hotspot
7. Open `http://192.168.x.x:4000`

---

## Common Errors

| Error | Fix |
|---|---|
| `node: command not found` | Install Node.js from nodejs.org |
| `Cannot find module 'socket.io'` | `cd backend && npm install` |
| `Cannot find module 'react'` | `cd frontend && npm install` |
| `ModuleNotFoundError: pymavlink` | `pip install pymavlink` |
| Port 4000 already in use | Set `PORT=4001` in `backend/.env` |
| Video not showing (live mode) | Check RTSP URLs, ensure FFmpeg is installed |
| PDF empty / no images | Press CAPTURE first, then generate PDF |
| `Warmup: only N GPS samples` | Wait ~1 s after bridge connects |
| `Sync unstable — locked=False` | Enable SYSTEM_TIME on FC, check GPS fix |
| `Port busy (WinError 10013)` | Close QGroundControl / Mission Planner first |
| `WARNING SYSTEM_TIME stale` | GPS stream dropped — check antenna / reconnect |
