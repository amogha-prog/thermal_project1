/**
 * TIOS Backend — Simple Server (No Database)
 *
 * All captured images and PDFs are saved directly to the
 * user's local machine by the browser's download API.
 *
 * This server only does two things:
 *   1. Parses MAVLink telemetry and broadcasts it via Socket.io
 *   2. Relays RTSP drone video streams to the browser via WebSocket
 */

require('dotenv').config();
const express    = require('express');
const http       = require('http');
const { Server } = require('socket.io');
const cors       = require('cors');
const path       = require('path');
const { exec }   = require('child_process');
const fs         = require('fs');

const { startMAVLink }      = require('./mavlink/mavlinkParser');
const { startStreamRelay }  = require('./stream/streamRelay');
const { startPythonBridge } = require('./python/pythonBridge');

// ─── App Setup ───────────────────────────────────────────────────────────────
const app    = express();
const server = http.createServer(app);
// Allow any localhost port (handles Vite using 5174/5175 when 5173 is busy)
const allowedOrigin = (origin, callback) => {
  if (!origin || /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin)) {
    callback(null, true);
  } else {
    callback(new Error('CORS not allowed: ' + origin));
  }
};

const io     = new Server(server, {
  cors: {
    origin: allowedOrigin,
    methods: ['GET', 'POST']
  }
});

app.use(cors({ origin: allowedOrigin }));
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ limit: '50mb', extended: true }));

// ─── Health check ────────────────────────────────────────────────────────────
app.get('/api/health', (req, res) => {
  res.json({
    status: 'ok',
    timestamp: new Date().toISOString(),
    mode: process.env.MAVLINK_CONNECTION || 'simulation',
    version: '2.0.0',
    pipeline: global.getPipelineStatus ? global.getPipelineStatus() : { connected: false },
  });
});

// ─── Pipeline status endpoint ────────────────────────────────────────────────
app.get('/api/pipeline', (req, res) => {
  res.json(global.getPipelineStatus ? global.getPipelineStatus() : { connected: false });
});

// ─── Generate PDF Report endpoint ───────────────────────────────────────────
app.post('/api/report/generate', (req, res) => {
  const { captures, missionId } = req.body;
  if (!captures || captures.length === 0) {
    return res.status(400).json({ error: 'No captures provided' });
  }

  const pythonDir = path.join(__dirname, '../python');
  const tempDir = path.join(pythonDir, 'temp_captures');
  const reportScript = 'generate_report.py';
  const outFile = path.join(pythonDir, 'C12_Thermal_Detection_Report.pdf');

  // Create clean temp directory
  if (fs.existsSync(tempDir)) {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
  fs.mkdirSync(tempDir, { recursive: true });

  try {
    captures.forEach((cap, idx) => {
      const b_thermal = cap.images.thermal.replace(/^data:image\/\w+;base64,/, "");
      const b_rgb = cap.images.rgb.replace(/^data:image\/\w+;base64,/, "");
      
      const t_file = `CAP-${idx}_thermal.jpg`;
      const v_file = `CAP-${idx}_visible.jpg`;
      
      fs.writeFileSync(path.join(tempDir, t_file), b_thermal, 'base64');
      fs.writeFileSync(path.join(tempDir, v_file), b_rgb, 'base64');

      const meta = {
        target_class: cap.telemetry.flightMode === 'auto' ? 'vehicle' : 'unknown',
        confidence: cap.telemetry.maxTemp > 50 ? 0.95 : 0.70,
        gps: {
          lat: parseFloat(cap.location.lat) || 0,
          lon: parseFloat(cap.location.lon) || 0,
          rel_alt_m: parseFloat(cap.location.alt) || 0,
          hdg_deg: parseFloat(cap.telemetry.heading) || 0,
          satellites: cap.telemetry.satellites || 0,
          hdop: cap.telemetry.hdop || 1.0,
          roll_deg: parseFloat(cap.telemetry.roll) || 0,
          pitch_deg: parseFloat(cap.telemetry.pitch) || 0,
          yaw_deg: parseFloat(cap.telemetry.yaw) || 0
        },
        bbox_xywh: [120, 80, 50, 90],
        blob_area_px: 4500,
        eccentricity: 0.5,
        peak_intensity: parseFloat(cap.telemetry.maxTemp) || 0,
        mean_intensity: parseFloat(cap.telemetry.avgTemp) || 0,
        palette: "blackhot",
        timestamp_utc: cap.timestamp,   // GPS-sourced ISO UTC timestamp
        time_source: cap.timeSource || 'system',  // 'gps' or 'system'
        thermal_file: t_file,
        visible_file: v_file
      };
      
      // We force severity target_class based on temp for demo styling
      if (meta.peak_intensity > 70) meta.target_class = 'human';
      else if (meta.peak_intensity > 50) meta.target_class = 'vehicle';
      else meta.target_class = 'animal';

      fs.writeFileSync(path.join(tempDir, `CAP-${idx}_meta.json`), JSON.stringify(meta, null, 2));
    });

    // Run python generate_report.py --captures temp_captures --out report.pdf
    console.log(`[API] Generating PDF Report for ${captures.length} captures...`);
    exec(`python ${reportScript} --captures temp_captures`, { cwd: pythonDir }, (error, stdout, stderr) => {
      if (error) {
        console.error('[API] Error generating report:', error);
        console.error(stderr);
        return res.status(500).json({ error: 'Failed to generate PDF report' });
      }
      
      console.log('[API] Report generated successfully.');
      if (fs.existsSync(outFile)) {
        res.download(outFile, 'C12_Thermal_Detection_Report.pdf', () => {
          // Cleanup after download
          if (fs.existsSync(tempDir)) fs.rmSync(tempDir, { recursive: true, force: true });
        });
      } else {
        res.status(404).json({ error: 'PDF file was not created by python script' });
      }
    });
  } catch (err) {
    console.error('Error preparing captures:', err);
    res.status(500).json({ error: 'Error preparing captures for PDF' });
  }
});

app.get('/', (req, res) => {
  res.send(`
    <body style="font-family: sans-serif; padding: 2rem; background: #111; color: #fff;">
      <h1>TIOS Backend is Running</h1>
      <p>Please open the frontend at <a href="http://localhost:5173" style="color: #61dafb;">http://localhost:5173</a></p>
    </body>
  `);
});

// ─── Socket.io ───────────────────────────────────────────────────────────────
io.on('connection', (socket) => {
  console.log(`[Socket] Client connected: ${socket.id}`);

  // Send the latest telemetry snapshot immediately on connect
  if (global.latestTelemetry) {
    socket.emit('telemetry', global.latestTelemetry);
  }

  socket.on('disconnect', () => {
    console.log(`[Socket] Client disconnected: ${socket.id}`);
  });
});

global.io               = io;
global.latestTelemetry  = null;

// ─── Boot ────────────────────────────────────────────────────────────────────
async function boot() {
  try {
    // Start MAVLink telemetry parser
    startMAVLink(io);
    console.log('[MAVLink] Parser started — mode:', process.env.MAVLINK_CONNECTION || 'simulation');

    // Start RTSP → WebSocket video relay (skipped if no RTSP URLs set)
    startStreamRelay();

    // Start Python pipeline bridge (receives detections via UDP)
    startPythonBridge(io);
    console.log('[PythonBridge] Detection bridge started — port:', process.env.PYTHON_BRIDGE_PORT || '14560');

    const PORT = process.env.PORT || 4000;
    
    server.on('error', (err) => {
      if (err.code === 'EADDRINUSE') {
        console.error(`\n[Fatal] Port ${PORT} is already in use. Please close other instances of the backend.`);
      } else {
        console.error(`\n[Fatal] Server error:`, err);
      }
      process.exit(1);
    });

    server.listen(PORT, () => {
      console.log('\n╔══════════════════════════════════════════╗');
      console.log(`║  TIOS Backend running on port ${PORT}       ║`);
      console.log(`║  No database — all data saved locally    ║`);
      console.log(`║  Open http://localhost:5173              ║`);
      console.log('╚══════════════════════════════════════════╝\n');
    });
  } catch (err) {
    console.error('[Boot] Fatal error:', err);
    process.exit(1);
  }
}

boot();
