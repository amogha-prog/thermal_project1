/**
 * TIOS MAVLink Parser
 *
 * Connects to the flight controller via UDP, serial, or runs in
 * simulation mode when no drone is connected.
 *
 * Broadcasts telemetry to all Socket.io clients every 100ms.
 *
 * Set MAVLINK_CONNECTION in backend/.env:
 *   simulation  → fake data, no drone needed (default)
 *   udp         → receives from Mission Planner / QGroundControl on UDP port 14550
 *   serial      → direct USB/UART connection
 */

const dgram   = require('dgram');

// Telemetry state — updated by parser, broadcast by interval
let telemetry = {
  lat: 0,           lon: 0,           // Start at 0,0 to clearly show when real GPS fix arrives
  alt: 0,           relAlt: 0,
  speed: 0,         climbRate: 0,     heading: 0,
  roll: 0,          pitch: 0,         yaw: 0,
  battery: 100,     voltage: 0,       current: 0,
  maxTemp: 0,       minTemp: 0,       avgTemp: 0,
  flightMode: 'UNKNOWN',
  armed: false,
  fixType: 0,       satellites: 0,
  timestamp: null,
};

function startMAVLink(io) {
  const mode = process.env.MAVLINK_CONNECTION || 'simulation';

  if (mode === 'simulation') {
    simulateFlight();
  } else if (mode === 'udp') {
    openUDP();
  } else if (mode === 'serial') {
    openSerial();
  } else if (mode === 'lan') {
    openLAN();
  }

  // Broadcast telemetry to all clients at 10Hz
  setInterval(() => {
    telemetry.timestamp     = new Date().toISOString();
    global.latestTelemetry  = { ...telemetry };
    io.emit('telemetry', global.latestTelemetry);
  }, 100);
}

// ─── UDP connection ───────────────────────────────────────────────────────────
function openUDP() {
  // Requires 'mavlink' npm package: npm install mavlink
  let mav;
  try {
    mav = require('mavlink');
  } catch {
    console.warn('[MAVLink] mavlink package not installed. Falling back to simulation.');
    simulateFlight();
    return;
  }

  const m      = new mav(1, 1);
  const socket = dgram.createSocket('udp4');
  const port   = parseInt(process.env.MAVLINK_UDP_PORT || '14550');
  const host   = process.env.MAVLINK_UDP_HOST || '0.0.0.0';

  // Attachment: Listen for packets immediately
  socket.on('message', (buf) => m.parse(buf));
  socket.bind(port, host, () => console.log(`[MAVLink] UDP listening on ${host}:${port} — Waiting for drone...`));

  // Protocol events
  m.on('GLOBAL_POSITION_INT', (msg) => {
    telemetry.lat     = msg.lat / 1e7;
    telemetry.lon     = msg.lon / 1e7;
    // Prefer relative_alt for ground clearance, but assign to alt for display
    telemetry.alt     = msg.relative_alt / 1000; 
    telemetry.heading = msg.hdg / 100;
  });

  m.on('ATTITUDE', (msg) => {
    telemetry.roll  = (msg.roll  * 180) / Math.PI;
    telemetry.pitch = (msg.pitch * 180) / Math.PI;
    telemetry.yaw   = (msg.yaw   * 180) / Math.PI;
  });

  m.on('VFR_HUD', (msg) => {
    telemetry.speed     = msg.groundspeed;
    telemetry.climbRate = msg.climb;
  });

  m.on('SYS_STATUS', (msg) => {
    telemetry.battery = msg.battery_remaining;
    telemetry.voltage = msg.voltage_battery / 1000;
  });

  m.on('BATTERY_STATUS', (msg) => {
    // Mirroring Python script logic for battery
    if (msg.voltages && msg.voltages[0] !== 65535) {
      telemetry.voltage = msg.voltages[0] / 1000.0;
    }
  });

  m.on('HEARTBEAT', (msg) => {
    telemetry.armed = !!(msg.base_mode & 128);
    // Log heartbeat once every few seconds to show connection is alive
    if (Math.random() > 0.95) {
      console.log(`[MAVLink] Heartbeat detected | Armed: ${telemetry.armed} | Mode ID: ${msg.custom_mode}`);
    }
  });

  m.on('NAMED_VALUE_FLOAT', (msg) => {
    if (msg.name === 'TEMP_MAX') telemetry.maxTemp = msg.value;
    if (msg.name === 'TEMP_MIN') telemetry.minTemp = msg.value;
    if (msg.name === 'TEMP_AVG') telemetry.avgTemp = msg.value;
  });
}

// ─── Serial connection ────────────────────────────────────────────────────────
function openSerial() {
  let SerialPort, mav;
  try {
    SerialPort = require('serialport').SerialPort;
    mav        = require('mavlink');
  } catch {
    console.warn('[MAVLink] serialport or mavlink not installed. Falling back to simulation.');
    simulateFlight();
    return;
  }

  const m      = new mav(1, 1);
  const port   = process.env.MAVLINK_SERIAL_PORT || '/dev/ttyUSB0';
  const baud   = parseInt(process.env.MAVLINK_BAUD_RATE || '57600');
  const serial = new SerialPort({ path: port, baudRate: baud });

  serial.on('data',  (buf) => m.parse(buf));
  serial.on('open',  ()    => console.log(`[MAVLink] Serial open: ${port} @ ${baud}`));
  serial.on('error', (err) => {
    console.warn('[MAVLink] Serial error:', err.message, '— falling back to simulation');
    simulateFlight();
  });
}

// ─── Simulation (no drone) ────────────────────────────────────────────────────
function simulateFlight() {
  console.log('[MAVLink] SIMULATION MODE — generating static realistic telemetry');
  let t = 0;
  setInterval(() => {
    t += 0.1;
    // Base coordinates (Test Field area) with tiny jitter to keep UI live
    telemetry.lat        = 14.454500 + (Math.sin(t) * 0.000001);
    telemetry.lon        = 75.909180 + (Math.cos(t) * 0.000001);
    telemetry.alt        = 50.0 + (Math.sin(t * 0.5) * 0.1);
    telemetry.speed      = 0.0 + Math.abs(Math.sin(t) * 0.1);
    telemetry.climbRate  = 0.0 + (Math.sin(t) * 0.02);
    telemetry.battery    = 98.4;
    telemetry.voltage    = 24.2;
    telemetry.roll       = 0.0 + (Math.sin(t * 1.5) * 0.2);
    telemetry.pitch      = 0.0 + (Math.cos(t * 1.2) * 0.2);
    telemetry.yaw        = 45.0 + (Math.sin(t * 0.2) * 0.5);
    telemetry.heading    = telemetry.yaw;
    telemetry.maxTemp    = 42.5;
    telemetry.minTemp    = 22.1;
    telemetry.avgTemp    = 34.8;
    telemetry.armed      = true;
    telemetry.fixType    = 3; // 3 = 3D Fix
    telemetry.satellites = 14;
    telemetry.flightMode = 'LOITER';
  }, 100);
}

// ─── LAN connection (JSON over UDP) ──────────────────────────────────────────
function openLAN() {
  const socket = dgram.createSocket('udp4');
  const port   = parseInt(process.env.LAN_UDP_PORT || '14555');
  const host   = process.env.LAN_UDP_HOST || '0.0.0.0';

  console.log(`[LAN] Starting listener on ${host}:${port}...`);

  socket.on('message', (msg) => {
    try {
      const raw = msg.toString().trim();
      console.log(`[LAN] Raw Packet: ${raw}`); // DEBUG: Log raw packet to see if data is arriving
      
      // Basic cleanup for Python-style dict strings (single quotes to double quotes)
      const cleanJson = raw.replace(/'/g, '"');
      const data = JSON.parse(cleanJson);

      // Map fields (choosing specific data as requested)
      if (data.lat !== undefined) telemetry.lat = parseFloat(data.lat);
      if (data.lon !== undefined) telemetry.lon = parseFloat(data.lon);
      if (data.alt !== undefined) telemetry.alt = parseFloat(data.alt);

      // Attitude (Assumed radians -> degrees)
      if (data.roll  !== undefined) telemetry.roll  = (parseFloat(data.roll)  * 180) / Math.PI;
      if (data.pitch !== undefined) telemetry.pitch = (parseFloat(data.pitch) * 180) / Math.PI;
      if (data.yaw   !== undefined) {
        let yawDeg = (parseFloat(data.yaw) * 180) / Math.PI;
        telemetry.yaw     = yawDeg;
        telemetry.heading = (yawDeg + 360) % 360; // Normalize 0-360
      }

      // Battery
      if (data.battery_voltage !== undefined) {
        telemetry.voltage = parseFloat(data.battery_voltage);
        // Estimate % based on 6S voltage (22.8V ~ 100%, 19V ~ 0%)
        let v = telemetry.voltage;
        telemetry.battery = Math.max(0, Math.min(100, ((v - 19) / (25.2 - 19)) * 100));
      }

      // Speeds
      if (data.speed !== undefined) telemetry.speed = parseFloat(data.speed);
      if (data.climb !== undefined) telemetry.climbRate = parseFloat(data.climb);

      // Status & GPS
      if (data.armed !== undefined)      telemetry.armed      = !!data.armed;
      if (data.satellites !== undefined) telemetry.satellites = parseInt(data.satellites);
      if (data.fix_type !== undefined)   telemetry.fixType    = parseInt(data.fix_type);

      // Flight Mode
      if (data.mode !== undefined) {
        // Map ArduPilot Copter modes
        const modes = {
          0:'STABILIZE', 1:'ACRO', 2:'ALT_HOLD', 3:'AUTO', 4:'GUIDED', 
          5:'LOITER', 6:'RTL', 7:'CIRCLE', 9:'LAND', 11:'DRIFT', 
          13:'SPORT', 14:'FLIP', 15:'AUTOTUNE', 16:'POSHOLD', 
          17:'BRAKE', 18:'THROW', 19:'AVOID_ADSB', 20:'GUIDED_NOGPS', 
          21:'SMART_RTL', 22:'FLOWHOLD', 23:'FOLLOW', 24:'ZIGZAG', 
          25:'SYSTEMID', 26:'AUTOROTATE', 27:'AUTO_RTL'
        };
        telemetry.flightMode = modes[data.mode] || `MODE_${data.mode}`;
      }

    } catch (err) {
      // If parsing fails, it might be a partial packet or wrong format
      // console.warn('[LAN] Parse error:', err.message);
    }
  });

  socket.on('error', (err) => {
    console.error('[LAN] Socket error:', err);
  });

  socket.bind(port, host, () => {
    console.log(`[LAN] UDP listening on ${host}:${port} — Feed JSON strings now`);
  });
}

/**
 * COPTER MODES
 */
const COPTER_MODES = {
  0:'STABILIZE',5:'LOITER',3:'AUTO',6:'RTL',9:'LAND',16:'POSHOLD',
};

module.exports = { startMAVLink };
