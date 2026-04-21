/**
 * TIOS Python Bridge — Receives detection data from the Python pipeline
 *
 * The Python thermal analysis pipeline sends detection results and status
 * updates via UDP on port 14560. This module listens for those messages
 * and broadcasts them to all connected frontend clients via Socket.io.
 *
 * Message types:
 *   - "detections"     → hotspot detection results (per-frame)
 *   - "pipeline_status" → pipeline health and stats
 *   - "auto_capture"   → auto-capture event notification
 */

const dgram = require('dgram');

function startPythonBridge(io) {
  const port = parseInt(process.env.PYTHON_BRIDGE_PORT || '14560');
  const host = process.env.PYTHON_BRIDGE_HOST || '0.0.0.0';
  const socket = dgram.createSocket('udp4');

  // Pipeline state — maintained server-side, sent to clients
  let pipelineStatus = {
    connected: false,
    lastSeen: null,
    running: false,
    fps: 0,
    framesProcessed: 0,
    totalDetections: 0,
    severityCounts: { NORMAL: 0, ELEVATED: 0, WARNING: 0, CRITICAL: 0 },
    hottestEver: 0,
  };

  let lastDetections = [];
  let connectionTimeout = null;

  // Mark pipeline as disconnected if no data for 5 seconds
  function resetConnectionTimeout() {
    if (connectionTimeout) clearTimeout(connectionTimeout);
    connectionTimeout = setTimeout(() => {
      if (pipelineStatus.connected) {
        pipelineStatus.connected = false;
        pipelineStatus.running = false;
        io.emit('pipeline_status', pipelineStatus);
        console.log('[PythonBridge] Pipeline disconnected (timeout)');
      }
    }, 5000);
  }

  socket.on('message', (msg) => {
    try {
      const data = JSON.parse(msg.toString().trim());
      const type = data.type;

      // Mark as connected
      if (!pipelineStatus.connected) {
        pipelineStatus.connected = true;
        console.log('[PythonBridge] Python pipeline connected!');
      }
      pipelineStatus.lastSeen = new Date().toISOString();
      resetConnectionTimeout();

      if (type === 'detections') {
        // ── Hotspot detection results ─────────────────────────────────
        lastDetections = data.detections || [];
        
        // Broadcast to all frontend clients
        io.emit('detections', {
          detections: lastDetections,
          frameStats: data.frame_stats || {},
          count: data.count || 0,
          timestamp: data.timestamp,
        });

        // Log significant detections
        const critical = lastDetections.filter(d => d.severity === 'CRITICAL');
        const warning = lastDetections.filter(d => d.severity === 'WARNING');
        if (critical.length > 0) {
          console.log(`[PythonBridge] ⚠️  ${critical.length} CRITICAL detection(s)!`);
        }
        if (warning.length > 0 && Math.random() > 0.9) {
          console.log(`[PythonBridge] ${warning.length} WARNING detection(s)`);
        }

      } else if (type === 'pipeline_status') {
        // ── Pipeline health update ───────────────────────────────────
        const p = data.pipeline || {};
        pipelineStatus.running = p.running || false;
        pipelineStatus.fps = p.avg_fps || 0;
        pipelineStatus.framesProcessed = p.frames_processed || 0;
        pipelineStatus.totalDetections = p.total_detections || 0;
        pipelineStatus.severityCounts = p.severity_counts || pipelineStatus.severityCounts;
        pipelineStatus.hottestEver = p.hottest_ever || 0;

        io.emit('pipeline_status', pipelineStatus);

      } else if (type === 'auto_capture') {
        // ── Auto-capture event ───────────────────────────────────────
        io.emit('auto_capture', {
          id: data.id,
          timestamp: data.timestamp,
          captureNumber: data.capture_number,
          detectionCount: data.detection_count,
          maxTemp: data.max_temp,
          severity: data.severity,
        });
        console.log(`[PythonBridge] Auto-capture: ${data.id} (${data.severity})`);
      }

    } catch (err) {
      // Silently ignore malformed packets
    }
  });

  socket.on('error', (err) => {
    console.error('[PythonBridge] Socket error:', err.message);
  });

  socket.bind(port, host, () => {
    console.log(`[PythonBridge] Listening on ${host}:${port} for Python pipeline data`);
  });

  // Provide status endpoint
  global.getPipelineStatus = () => ({
    ...pipelineStatus,
    activeDetections: lastDetections.length,
    detections: lastDetections.slice(0, 10), // Last 10 detections
  });

  return socket;
}

module.exports = { startPythonBridge };
