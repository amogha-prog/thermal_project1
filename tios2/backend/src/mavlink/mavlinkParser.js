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
  // GPS
  lat: 0, lon: 0,
  alt: 0,           // AGL (primary display)
  altMsl: 0,        // above mean sea level
  altAgl: 0,        // above ground level (calibrated)

  // Speed
  speed: 0,         // ground speed (m/s)
  climbRate: 0,     // vertical speed (m/s)
  vx: 0, vy: 0, vz: 0, // NED velocity components (m/s)

  // Attitude (degrees)
  roll: 0, pitch: 0, yaw: 0,

  // Heading
  heading: 0,              // primary display (body yaw)
  headingBody: 0,          // from ATTITUDE message
  headingAutopilot: 0,     // from VFR_HUD
  cog: 0,                  // course over ground from GPS

  // Battery
  voltage: 0,
  battery: 0,              // percentage
  current: 0,

  // Thermal temps (filled by Python pipeline)
  maxTemp: 0, minTemp: 0, avgTemp: 0,

  // Status
  flightMode: 'UNKNOWN',
  armed: false,
  fixType: 0,
  satellites: 0,

  // Timestamps
  systemDatetimeUtc: '',
  systemDatetimeIst: '',
  gpsDatetimeUtc: '',
  gpsDatetimeIst: '',
  timeSyncErrorSec: null,

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
  socket.on('message', (buf) => {
    if (Math.random() > 0.95) {
        const magic = buf[0].toString(16).toUpperCase();
        console.log(`[MAVLink:DEBUG] Received ${buf.length} bytes | Magic: 0x${magic} | Hex: ${buf.slice(0, 10).toString('hex')}`);
    }
    m.parse(buf);
  });
  socket.bind(port, host, () => {
    console.log(`[MAVLink] UDP listening on ${host}:${port} — Waiting for drone...`);
    
    // Many drone data links (like SIYI/Herelink) require the GCS to send a packet
    // first so the router knows our IP address and starts routing telemetry.
    try { socket.setBroadcast(true); } catch(e) {}
    
    const ping = Buffer.from('WakeUp\x00');
    const sendPings = () => {
      socket.send(ping, 0, ping.length, 14550, '192.168.144.11', () => {});
      socket.send(ping, 0, ping.length, 14550, '192.168.144.12', () => {});
      socket.send(ping, 0, ping.length, 14550, '255.255.255.255', () => {});
    };
    
    sendPings();
    setInterval(sendPings, 5000); // keep route alive
  });

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
    // Log heartbeat every time to see if we get them!
    console.log(`[MAVLink] Heartbeat detected | Armed: ${telemetry.armed} | Mode ID: ${msg.custom_mode}`);
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

// ─── LAN connection (JSON over UDP from drone_bridge.py) ───────────────────────────
function openLAN() {
  const socket = dgram.createSocket('udp4');
  const port   = parseInt(process.env.LAN_UDP_PORT || '14555');
  const host   = process.env.LAN_UDP_HOST || '0.0.0.0';

  socket.on('message', (msg) => {
    try {
      const data = JSON.parse(msg.toString().trim());

      // GPS
      if (data.lat     !== undefined) telemetry.lat    = parseFloat(data.lat);
      if (data.lon     !== undefined) telemetry.lon    = parseFloat(data.lon);
      if (data.alt_agl !== undefined) telemetry.alt    = parseFloat(data.alt_agl); // primary display
      if (data.alt_agl !== undefined) telemetry.altAgl = parseFloat(data.alt_agl);
      if (data.alt_msl !== undefined) telemetry.altMsl = parseFloat(data.alt_msl);

      // Attitude — drone_bridge.py sends DEGREES already
      if (data.roll  !== undefined) telemetry.roll  = parseFloat(data.roll);
      if (data.pitch !== undefined) telemetry.pitch = parseFloat(data.pitch);
      if (data.yaw   !== undefined) telemetry.yaw   = parseFloat(data.yaw);

      // Heading
      if (data.heading_body      !== undefined) {
        telemetry.heading      = parseFloat(data.heading_body);
        telemetry.headingBody  = parseFloat(data.heading_body);
      }
      if (data.heading_autopilot !== undefined) telemetry.headingAutopilot = parseFloat(data.heading_autopilot);
      if (data.cog               !== undefined) telemetry.cog              = parseFloat(data.cog);

      // Speed
      if (data.ground_speed !== undefined) telemetry.speed     = parseFloat(data.ground_speed);
      if (data.climb        !== undefined) telemetry.climbRate = parseFloat(data.climb);
      if (data.vx           !== undefined) telemetry.vx        = parseFloat(data.vx);
      if (data.vy           !== undefined) telemetry.vy        = parseFloat(data.vy);
      if (data.vz           !== undefined) telemetry.vz        = parseFloat(data.vz);

      // Battery
      if (data.battery_voltage !== undefined) telemetry.voltage = parseFloat(data.battery_voltage);
      if (data.battery_pct     !== undefined) {
        telemetry.battery = parseFloat(data.battery_pct);
      } else if (data.battery_voltage !== undefined) {
        const v = parseFloat(data.battery_voltage);
        telemetry.battery = Math.max(0, Math.min(100, ((v - 19) / (25.2 - 19)) * 100));
      }

      // GPS status
      if (data.satellites !== undefined) telemetry.satellites = parseInt(data.satellites);
      if (data.fix_type   !== undefined) telemetry.fixType    = parseInt(data.fix_type);

      // Flight state
      if (data.armed !== undefined) telemetry.armed      = !!data.armed;
      if (data.mode  !== undefined) telemetry.flightMode = String(data.mode);

      // Timestamps
      if (data.system_datetime_utc !== undefined) telemetry.systemDatetimeUtc = data.system_datetime_utc;
      if (data.system_datetime_ist !== undefined) telemetry.systemDatetimeIst = data.system_datetime_ist;
      if (data.gps_datetime_utc    !== undefined) telemetry.gpsDatetimeUtc    = data.gps_datetime_utc;
      if (data.gps_datetime_ist    !== undefined) telemetry.gpsDatetimeIst    = data.gps_datetime_ist;
      if (data.time_sync_error_sec !== undefined) telemetry.timeSyncErrorSec  = data.time_sync_error_sec;

      // Thermal (from Python pipeline)
      if (data.maxTemp !== undefined) telemetry.maxTemp = parseFloat(data.maxTemp);
      if (data.minTemp !== undefined) telemetry.minTemp = parseFloat(data.minTemp);
      if (data.avgTemp !== undefined) telemetry.avgTemp = parseFloat(data.avgTemp);

    } catch (err) {
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
