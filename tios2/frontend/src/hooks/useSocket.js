/**
 * useSocket — connects to backend Socket.io and syncs telemetry + detections to store.
 * Call once at the top of App.jsx.
 */

import { useEffect } from 'react';
import { io } from 'socket.io-client';
import { useTIOSStore } from '../store/useTIOSStore';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || `http://${window.location.hostname}:4000`;

export function useSocket() {
  const updateTelemetry      = useTIOSStore((s) => s.updateTelemetry);
  const setConnected         = useTIOSStore((s) => s.setConnected);
  const addToast             = useTIOSStore((s) => s.addToast);
  const updateDetections     = useTIOSStore((s) => s.updateDetections);
  const updatePipelineStatus = useTIOSStore((s) => s.updatePipelineStatus);

  useEffect(() => {
    const socket = io(BACKEND_URL, {
      transports: ['websocket', 'polling'],
      reconnectionDelay: 1000,
    });

    socket.on('connect',    ()       => { setConnected(true);  addToast('Backend connected', 'success'); });
    socket.on('disconnect', ()       => { setConnected(false); addToast('Disconnected from backend', 'warn'); });
    socket.on('telemetry',  (data)   => updateTelemetry(data));

    // Python pipeline events
    socket.on('detections',      (data) => updateDetections(data));
    socket.on('pipeline_status', (data) => updatePipelineStatus(data));
    socket.on('auto_capture',    (data) => {
      addToast(`Auto-captured: ${data.id} (${data.severity})`, data.severity === 'CRITICAL' ? 'error' : 'warn');
    });

    return () => socket.disconnect();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
