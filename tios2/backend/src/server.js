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

const { startMAVLink }     = require('./mavlink/mavlinkParser');
const { startStreamRelay } = require('./stream/streamRelay');

// ─── App Setup ───────────────────────────────────────────────────────────────
const app    = express();
const server = http.createServer(app);
const io     = new Server(server, {
  cors: {
    origin: process.env.FRONTEND_URL || 'http://localhost:5173',
    methods: ['GET', 'POST']
  }
});

app.use(cors({ origin: process.env.FRONTEND_URL || 'http://localhost:5173' }));
app.use(express.json());

// ─── Health check ────────────────────────────────────────────────────────────
app.get('/api/health', (req, res) => {
  res.json({
    status: 'ok',
    timestamp: new Date().toISOString(),
    mode: process.env.MAVLINK_CONNECTION || 'simulation',
    version: '2.0.0'
  });
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
