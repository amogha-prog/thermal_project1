/**
 * TIOS Stream Relay
 * RTSP drone video → FFmpeg → WebSocket → Browser (JSMpeg)
 * Skipped automatically if RTSP URLs are not set in .env
 */

const { spawn }  = require('child_process');
const WebSocket  = require('ws');
const http       = require('http');

function startStreamRelay() {
  const thermalRtsp = process.env.THERMAL_RTSP_URL;
  const rgbRtsp     = process.env.RGB_RTSP_URL;

  if (!thermalRtsp || !rgbRtsp) {
    console.log('[Stream] No RTSP URLs configured — video relay disabled.');
    console.log('[Stream] App will run with simulation canvases.');
    console.log('[Stream] To enable: set THERMAL_RTSP_URL and RGB_RTSP_URL in backend/.env');
    return;
  }

  createRelay('thermal', thermalRtsp, parseInt(process.env.THERMAL_WS_PORT || '9999'));
  createRelay('rgb',     rgbRtsp,     parseInt(process.env.RGB_WS_PORT     || '9998'));
}

function createRelay(name, rtspUrl, wsPort) {
  const server = http.createServer();
  const clients = new Set();

  server.on('error', (err) => {
    if (err.code === 'EADDRINUSE') {
      console.warn(`[Stream:${name}] Port ${wsPort} in use — skipping video relay. Kill old process or change port.`);
    } else {
      console.error(`[Stream:${name}] Server error:`, err.message);
    }
  });

  server.listen(wsPort, () => {
    console.log(`[Stream:${name}] WebSocket on ws://localhost:${wsPort}`);

    const wss = new WebSocket.Server({ server });

    wss.on('error', (err) => {
      console.error(`[Stream:${name}] WS error:`, err.message);
    });

    wss.on('connection', (ws) => {
      clients.add(ws);
      console.log(`[Stream:${name}] Client connected (Total: ${clients.size})`);
      ws.on('close', () => {
        clients.delete(ws);
        console.log(`[Stream:${name}] Client disconnected (Total: ${clients.size})`);
      });
    });

    spawnFFmpeg(name, rtspUrl, clients);
  });
}

function spawnFFmpeg(name, rtspUrl, clients, retry = 0) {
  const res  = name === 'thermal' ? '640x480'  : '1280x720';
  const br   = name === 'thermal' ? '600k'     : '1500k';

  const ffmpegBin = process.env.FFMPEG_PATH || 'ffmpeg';

  const transport = retry % 2 === 0 ? 'udp' : 'tcp';
  console.log(`[FFmpeg:${name}] Connecting to: ${rtspUrl} (Transport: ${transport})`);

  const ff = spawn(ffmpegBin, [
    '-rtsp_transport', transport,
    '-fflags', 'nobuffer+genpts+discardcorrupt',
    '-flags', 'low_delay',
    '-analyzeduration', '0',
    '-probesize', '32',
    '-max_delay', '0',
    '-i', rtspUrl,
    '-f', 'mpegts',
    '-codec:v', 'mpeg1video',
    '-b:v', br,
    '-r', '25',
    '-s', res,
    '-bf', '0',
    '-muxdelay', '0.001',
    '-err_detect', 'ignore_err',
    '-an',
    'pipe:1',
  ], { stdio: ['ignore', 'pipe', 'pipe'] });

  ff.stdout.on('data', (chunk) => {
    clients.forEach((ws) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(chunk, { binary: true });
      }
    });
  });

  // CRITICAL: Log FFmpeg stderr to identify the "Access denied" or "Timed out" errors
  ff.stderr.on('data', (data) => {
    const msg = data.toString();
    // Only log errors or connection messages to avoid flooding
    if (msg.includes('Error') || msg.includes('Failed') || msg.includes('Server returned')) {
       console.error(`[FFmpeg:${name}] Error: ${msg.trim()}`);
    }
  });

  ff.on('close', (code) => {
    const delay = Math.min(3000 * (retry + 1), 30000);
    console.warn(`[FFmpeg:${name}] Exited (${code}). Retrying in ${delay}ms`);
    
    // If it keeps failing, try UDP transport as a fallback
    setTimeout(() => spawnFFmpeg(name, rtspUrl, clients, retry + 1), delay);
  });
}

module.exports = { startStreamRelay };
