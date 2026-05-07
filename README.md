# 🛸 Aeroluna Thermal Project

**TIOS v2 — Thermal Inspection Operating System**  
A real-time drone-based thermal inspection platform with high-precision GPS geotagging, live MAVLink telemetry, thermal anomaly detection, and automated PDF/CSV mission reporting.

---

## 📁 Project Structure

```
aeroluna thermal project/
├── tios2/                          # Main TIOS web application
│   ├── frontend/                   # React + Vite UI  (port 5173)
│   └── backend/                    # Node.js + Socket.io backend  (port 4000)
│       ├── src/
│       │   ├── server.js           # Express + Socket.io server
│       │   ├── mavlink/
│       │   │   └── mavlinkParser.js  # UDP / serial / LAN / simulation
│       │   ├── stream/
│       │   │   └── streamRelay.js  # RTSP → FFmpeg → WebSocket relay
│       │   └── python/
│       │       └── pythonBridge.js # Detection UDP receiver
│       ├── python/                 # ML + thermal analysis pipeline
│       │   ├── main.py             # Pipeline orchestrator
│       │   ├── hotspot_detector.py # Thermal anomaly detection
│       │   ├── classifier.py       # YOLO11 classification
│       │   ├── auto_capture.py     # Auto-capture on anomaly trigger
│       │   ├── stream_reader.py    # Dual RTSP ingestion
│       │   ├── false_positive_filter.py
│       │   ├── generate_report.py  # PDF report generator (FPDF2)
│       │   └── gps_mavlink.py      # Standalone MAVLink bridge (legacy)
│       ├── drone_bridge.py         # ★ PRIMARY MAVLink bridge (v2 engine)
│       ├── wake_drone.py           # Controller wake-up tool
│       └── debug_udp.py            # Raw MAVLink packet inspector
│
├── v2/                             # ★ High-precision geotag engine
│   ├── main.py                     # Standalone v2 entry point (testing)
│   ├── time_sync.py                # GPS ↔ monotonic clock synchronisation
│   ├── buffers.py                  # Kinematic ring buffers (GPS + Attitude)
│   ├── frame_tagger.py             # Per-frame metadata assembler
│   └── calibration/
│       └── ekf_delay_calibrator.py # Offline EKF delay sweep tool
│
├── captures/                       # Mission capture images
└── yolo11n.pt                      # Base YOLO11 detection model
```

---

## 🚀 Quick Start

### 1. Install dependencies
```bash
cd tios2
npm run install:all
```

### 2. Start the system (two terminals)
```bash
# Terminal 1 — Backend
cd tios2/backend
npm run dev

# Terminal 2 — Frontend
cd tios2/frontend
npm run dev
```

Open **http://localhost:5173**

### 3. Start the MAVLink geotag bridge (third terminal)
```bash
cd tios2/backend
python drone_bridge.py
```

> If your drone controller needs a wake-up signal first:
> ```bash
> python wake_drone.py
> ```

---

## 🌐 Architecture Overview

```
Flight Controller (ArduPilot / PX4)
        │  MAVLink over UDP :14550 / :14555
        ▼
  drone_bridge.py  (v2 engine)
        │
        ├─ SYSTEM_TIME ──────► TimeSync
        │                      monotonic → GPS epoch offset
        │                      EMA lock, drift monitor, wall-clock bootstrap
        │
        ├─ GLOBAL_POSITION_INT ► GPSBuffer (200-entry ring)
        │                        Midpoint-anchored NED kinematic interpolation
        │                        Adaptive linear/kinematic blend
        │
        ├─ ATTITUDE ──────────► AttitudeBuffer (200-entry ring)
        │                        Shortest-path angular interpolation (rad)
        │
        ├─ Telemetry JSON @ 25 Hz ──► Node.js backend (UDP :14556)
        │                              └─► Socket.io → React dashboard
        │
        └─ Geotag query server (UDP :14557) ◄── auto_capture.py
                    frame_time − EKF_DELAY
                    frame_time − VIDEO_LATENCY
                    → tag_frame() → metadata dict
```

---

## ⚙️ v2 Geotag Engine (core innovation)

The `v2/` module provides the high-precision geotagging system used by `drone_bridge.py`.

### Time Domain Rule
> **Every geotag-critical timestamp is `monotonic → GPS epoch`. Never `time.time()`.**

| Timestamp use | Method | Precision |
|---|---|---|
| GPS buffer entries | `boot_to_utc(boot_ms)` | ±1 ms |
| Attitude buffer entries | `boot_to_utc(boot_ms)` | ±1 ms |
| Frame capture time | `to_drone_time(mono − VIDEO_LATENCY)` | ±2 ms |
| Buffer query time | `frame_time − EKF_DELAY` | ±1 ms |
| Bootstrap (fallback) | `time.time()` once only | ±50–500 ms |

### v2 Modules

#### `time_sync.py` — `TimeSync`
- Converts `time.monotonic()` to GPS UTC epoch via SYSTEM_TIME messages
- Two EMA rates: `alpha_fast=0.3` (pull-in) → `alpha_slow=0.05` (locked)
- **Lock threshold:** 150 ms error
- **Drift monitor:** logs if offset shifts > 10 ms between updates
- **Wall-clock bootstrap:** if SYSTEM_TIME not received within 5 s, uses `time.time()` as approximation; first real GPS message auto-overrides it
- **`boot_to_utc_offset`:** separate mapping for FC boot-relative timestamps

#### `buffers.py` — `GPSBuffer` + `AttitudeBuffer`
- **`BaseBuffer`:** `bisect`-sorted O(log n) insert, handles out-of-order packets
- **`AttitudeBuffer`:** `max_gap=150 ms`, angle-safe interpolation (shortest-path yaw in radians)
- **`GPSBuffer`:** Full kinematic model:

| Execution path | Condition | Method |
|---|---|---|
| Before first sample | `t < times[0]` | Return nearest (bounded by `max_gap`) |
| After last sample | `t > times[-1]`, `dt ≤ 100 ms`, `speed ≤ 6 m/s` | Forward extrapolation with velocity |
| Bracketed | Normal | Midpoint-anchored NED kinematic + adaptive blend |

**Hard gates** (fall back to linear): speed > 8 m/s · ΔV > 4 m/s · accel > 5 m/s² · anchor dist > 10 m  
**Soft gates** (reduce kinematic weight): speed > 5 m/s · accel > 3 m/s² · dt < 50 ms · dt > 100 ms

#### `frame_tagger.py` — `tag_frame()`
- **`EKF_DELAY = 0.10 s`** — subtracts FC EKF output latency before querying buffers
- Returns structured metadata dict per frame:

```python
{
  "timestamp": { "utc", "ist", "epoch", "query_epoch" },
  "position":  { "lat", "lon", "alt_msl", "alt_agl" },
  "velocity":  { "vx", "vy", "vz", "ground_speed" },   # m/s NED
  "attitude":  { "roll", "pitch", "yaw" },               # radians
  "heading":   { "body", "autopilot", "cog" },           # degrees
  "battery":   { "voltage" },                            # volts
}
```

#### `calibration/ekf_delay_calibrator.py`
- Offline tool: sweeps `EKF_DELAY` from 20–250 ms in 5 ms steps
- For each candidate: computes mean forward-prediction error (m) against logged GPS data
- Prints results table + best delay → update `EKF_DELAY` in `frame_tagger.py`

---

## 🔌 Port Map

| Port | Protocol | Direction | Purpose |
|---|---|---|---|
| 14550 | UDP | FC → Bridge | MAVLink from drone (primary) |
| 14555 | UDP | FC → Bridge | MAVLink from drone (fallback) |
| 14556 | UDP | Bridge → Node | Telemetry JSON @ 25 Hz |
| 14557 | UDP | auto_capture → Bridge | Geotag query/response |
| 14560 | UDP | Python pipeline → Node | Detection events |
| 4000 | HTTP/WS | Node → Browser | REST API + Socket.io |
| 5173 | HTTP | Vite → Browser | React dev server |

---

## 🔧 Configuration

### Runtime (environment variables)
```bash
# Camera pipeline lag — tune per camera with LED-flash measurement
VIDEO_LATENCY=0.120 python drone_bridge.py
```

| Variable | Default | Description |
|---|---|---|
| `VIDEO_LATENCY` | `0.150` | Camera pipeline lag in seconds |

### Compile-time constants

**`v2/frame_tagger.py`**
| Constant | Default | Description |
|---|---|---|
| `EKF_DELAY` | `0.10` s | FC EKF output latency — calibrate with `ekf_delay_calibrator.py` |

**`v2/buffers.py` — GPSBuffer**
| Constant | Default | Description |
|---|---|---|
| `MAX_SPEED` | `8.0` m/s | Hard reject kinematic above this |
| `SOFT_SPEED` | `5.0` m/s | Reduce kinematic weight above this |
| `MAX_DV` | `4.0` m/s | Reject if velocity step exceeds this |
| `MAX_ACCEL` | `5.0` m/s² | Hard reject above this acceleration |
| `SOFT_ACCEL` | `3.0` m/s² | Reduce kinematic weight above this |
| `MAX_ANCHOR_DIST` | `10.0` m | Fall back to linear if P1–P2 gap exceeds this |
| `max_gap` | `0.35` s | Maximum allowed sample gap |

**`v2/time_sync.py` — TimeSync**
| Parameter | Default | Description |
|---|---|---|
| `alpha_fast` | `0.3` | EMA rate when unlocked |
| `alpha_slow` | `0.05` | EMA rate when locked |
| `stable_threshold` | `0.15` s | Error below this → locked |
| `max_jump` | `0.5` s | Reject GPS updates larger than this |

---

## 📡 drone_bridge.py — Health Output

Every 3 seconds:
```
[13:35:24] DATA RATES | GPS: 10.0 Hz (Age: 0.3s) | Attitude: 50.0 Hz (Age: 0.1s)
[13:35:24] SYNC | Offset: 1778046456097.6 ms | Locked: True | Drift: 0.05 ms/s | EKF_DELAY: 100 ms | VIDEO_LATENCY: 150 ms
[13:35:24] WARNING SYSTEM_TIME stale: 3.2s  ← only if age > 2s
```

Every 100 packets:
```
[13:35:24] OK | mode=LOITER armed=True lat=12.97150 lon=77.59460 agl=45.2m spd=2.1m/s bat=24.1V sync_err=0.002s drift=0.05ms/s locked=True
```

**Geotag guards** — capture blocked if:
- GPS buffer < 10 samples (warmup)
- Sync not locked OR SYSTEM_TIME age > 2 s
- Frame time outside GPS data range ± 100 ms

---

## 🔋 Pre-Flight Checklist

```
🔴 REQUIRED
  □ Calibrate EKF_DELAY
        cd v2
        python -c "from calibration.ekf_delay_calibrator import sweep_ekf_delay; ..."
        Update EKF_DELAY in v2/frame_tagger.py

  □ Measure VIDEO_LATENCY for your camera
        Method: LED flash → find frame → measure offset
        Set:    VIDEO_LATENCY=0.XXX python drone_bridge.py

🟠 RECOMMENDED
  □ Confirm "Locked: True" within 10 s of connect
  □ GPS Hz ≥ 5 Hz, Attitude Hz ≥ 10 Hz in health output
  □ Drift < 1.0 ms/s during 5-minute ground test
  □ IST timestamp matches your watch to < 1 s

🟢 PRODUCTION
  □ Set MAVLINK_CONNECTION=lan in backend/.env
  □ Ensure SYSTEM_TIME stream is enabled on FC (SR_EXTRA stream rate)
```

---

## 🤖 ML / Vision Pipeline

The Python pipeline (`backend/python/main.py`) runs alongside the bridge:

1. **RTSP Ingestion** — dual camera frames from thermal + RGB
2. **Hotspot Detection** — temperature anomaly detection + YOLO11 inference
3. **Classification** — severity (`NORMAL / ELEVATED / WARNING / CRITICAL`)
4. **False Positive Filter** — persistence + spatial validation
5. **Auto Capture** — triggers `auto_capture.py` → geotag query → saves metadata
6. **Dashboard Sync** — sends detections via UDP :14560 → Node.js → Socket.io → UI

---

## 🐛 Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Warmup: only N GPS samples` | Buffer hasn't filled yet | Wait ~1 s after telemetry starts |
| `Sync unstable — locked=False` | SYSTEM_TIME not streaming | Enable SYSTEM_TIME on FC; check SR_EXTRA rate |
| `Frame ahead of GPS data` | Large VIDEO_LATENCY value | Reduce `VIDEO_LATENCY` |
| GPS Hz = 0.0 | No GLOBAL_POSITION_INT messages | Check MAVLink connection, port |
| `WARNING SYSTEM_TIME stale` | GPS stream dropped | Check antenna, reconnect drone |
| Drift > 1.0 ms/s | GPS clock instability | Check GPS antenna, RF interference |
| `Port busy (WinError 10013)` | QGC/MP already on port | Close QGC or change SOURCES in `drone_bridge.py` |
| Video not showing | FFmpeg missing or wrong RTSP URL | Install FFmpeg, check `.env` URLs |
| PDF empty | No captures in session | Press CAPTURE at least once |

---

## 📦 Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, Zustand, Leaflet, Socket.io-client |
| Backend | Node.js, Express, Socket.io, FFmpeg |
| Geotag Engine | Python 3.10+, pymavlink, custom v2 modules |
| ML / Vision | YOLO11 (Ultralytics), OpenCV, NumPy |
| Reporting | FPDF2 (Python), jsPDF (browser PDF) |
| Video | FFmpeg, RTSP, WebSocket |
| Telemetry | MAVLink (pymavlink), UDP |

---

## 🔗 Key Files Quick Reference

| File | Role |
|---|---|
| `tios2/backend/drone_bridge.py` | **Primary** MAVLink bridge — imports v2 engine, serves geotag queries |
| `v2/time_sync.py` | GPS↔monotonic sync with EMA, lock, drift, bootstrap |
| `v2/buffers.py` | `GPSBuffer` (NED kinematic) + `AttitudeBuffer` (angle-safe) |
| `v2/frame_tagger.py` | `tag_frame()` — assembles metadata dict with EKF delay compensation |
| `v2/calibration/ekf_delay_calibrator.py` | Offline tool — find optimal `EKF_DELAY` |
| `tios2/backend/src/server.js` | Express + Socket.io server, PDF report endpoint |
| `tios2/backend/src/mavlink/mavlinkParser.js` | Node.js MAVLink modes (simulation / udp / serial / lan) |
| `tios2/backend/python/auto_capture.py` | Anomaly-triggered capture → geotag query → metadata save |
| `tios2/backend/python/generate_report.py` | FPDF2 PDF report generator |

---

## 👨‍💻 Author

**Aeroluna** — Thermal Inspection Platform  
GitHub: [amogha-prog/thermal_project1](https://github.com/amogha-prog/thermal_project1)

---

## 📜 License

MIT License — see [LICENSE-THIRD-PARTY.md](tios2/LICENSE-THIRD-PARTY.md) for third-party acknowledgments.
