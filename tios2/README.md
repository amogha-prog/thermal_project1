# TIOS — Thermal Inspection Operating System
### No Database · All Files Saved Locally

---

## How storage works

| What                        | Where it goes                              |
|-----------------------------|--------------------------------------------|
| Capture data (session)      | React memory (Zustand) — lost on refresh   |
| Individual JPEG images      | Your Downloads folder (browser download)   |
| PDF inspection report       | Your Downloads folder (browser download)   |
| Nothing                     | No server, no database, no cloud           |

---

## Project structure

```
tios/
├── package.json                  ← root scripts
│
├── backend/
│   ├── .env                      ← configure MAVLink + RTSP here
│   └── src/
│       ├── server.js             ← Express + Socket.io (telemetry only)
│       ├── mavlink/
│       │   └── mavlinkParser.js  ← UDP / serial / simulation
│       └── stream/
│           └── streamRelay.js    ← RTSP → FFmpeg → WebSocket
│
└── frontend/
    ├── .env                      ← backend URL (change for field use)
    └── src/
        ├── App.jsx               ← root layout + capture/PDF logic
        ├── store/
        │   └── useTIOSStore.js   ← all state (Zustand)
        ├── hooks/
        │   └── useSocket.js      ← Socket.io telemetry sync
        ├── utils/
        │   ├── captureEngine.js  ← grab frame + build capture unit + local save
        │   └── pdfGenerator.js   ← jsPDF report → browser download
        └── components/
            ├── TopBar.jsx
            ├── ScanBar.jsx
            ├── ToastContainer.jsx
            ├── video/VideoPanel.jsx
            ├── telemetry/TelemetrySidebar.jsx
            └── capture/CaptureModal.jsx
```

---

## Quick start (3 steps)

### Step 1 — Install Node.js
Download from https://nodejs.org (LTS version)
Verify: open terminal → `node --version`

### Step 2 — Install dependencies
```bash
cd tios
npm run install:all
```

### Step 3 — Run
```bash
npm run dev
```
Open http://localhost:5173

---

## Buttons explained

| Button         | What it does                                                    |
|----------------|-----------------------------------------------------------------|
| ● CAPTURE      | Grabs both video frames + GPS + all telemetry at that exact ms  |
| ↓ IMAGES       | Downloads thermal + RGB of the latest capture as JPEG files     |
| ↓ PDF REPORT   | Builds a full A4 inspection report → saves to your Downloads    |
| SWAP           | Swaps the thermal and RGB panels                                |
| Click thumbnail| Opens full detail modal for any capture                         |
| SAVE IMAGES    | (In modal) downloads that specific capture's images             |

---

## Connecting a real drone

**Step 1** — Set RTSP stream URLs in `backend/.env`:
```env
THERMAL_RTSP_URL=rtsp://192.168.1.100:554/thermal
RGB_RTSP_URL=rtsp://192.168.1.100:554/rgb
```

**Step 2** — Set MAVLink connection in `backend/.env`:
```env
# For WiFi/UDP (Mission Planner, QGroundControl):
MAVLINK_CONNECTION=udp
MAVLINK_UDP_PORT=14550

# For USB/serial:
MAVLINK_CONNECTION=serial
MAVLINK_SERIAL_PORT=/dev/ttyUSB0
MAVLINK_BAUD_RATE=57600
```

**Step 3** — Turn off simulation in `frontend/src/App.jsx`:
```js
const DEMO_MODE = false;
```

**Step 4** — Install FFmpeg (needed for video relay):
- Windows: https://ffmpeg.org/download.html → add to PATH
- Mac: `brew install ffmpeg`
- Linux: `sudo apt install ffmpeg`

---

## Field deployment (no internet, local Wi-Fi hotspot)

1. Run the backend on a Raspberry Pi or laptop
2. Create a Wi-Fi hotspot on that device
3. Update `frontend/.env`:
   ```
   VITE_BACKEND_URL=http://192.168.x.x:4000
   VITE_THERMAL_WS_URL=ws://192.168.x.x:9999
   VITE_RGB_WS_URL=ws://192.168.x.x:9998
   ```
4. Build the frontend: `npm run build`
5. Add to `backend/src/server.js` to serve the built frontend:
   ```js
   const path = require('path');
   app.use(express.static(path.join(__dirname, '../../frontend/dist')));
   ```
6. Run `npm start` on the Pi — connect tablet/phone to the hotspot
7. Open `http://192.168.x.x:4000` on any device

---

## Common errors

| Error                              | Fix                                                   |
|------------------------------------|-------------------------------------------------------|
| `node: command not found`          | Install Node.js from nodejs.org                       |
| `Cannot find module 'socket.io'`   | Run `cd backend && npm install`                       |
| `Cannot find module 'react'`       | Run `cd frontend && npm install`                      |
| Port 4000 already in use           | Change `PORT=4001` in `backend/.env`                  |
| Video not showing (live mode)      | Check RTSP URLs, ensure FFmpeg is installed           |
| PDF empty / no images              | Press CAPTURE first, then generate PDF                |
