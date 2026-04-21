/**
 * TIOS Global Store (Zustand)
 *
 * All capture data lives here in React memory for the session.
 * Nothing is sent to a server or database.
 * Images are saved to the user's local machine via browser download.
 */

import { create } from 'zustand';

const DEFAULT_TELEMETRY = {
  lat: 14.454500,  lon: 75.909180, // Start at Test Field to avoid path jumps
  alt: 0,          relAlt: 0,
  speed: 0,        climbRate: 0,   heading: 0,
  roll: 0,         pitch: 0,       yaw: 0,
  battery: 100,    voltage: 0,     current: 0,
  maxTemp: 0,      minTemp: 0,     avgTemp: 0,
  flightMode: 'UNKNOWN',
  armed: false,
  fixType: 0,      satellites: 0,
  timestamp: null,
};

export const useTIOSStore = create((set, get) => ({

  // ── Telemetry (updated live from Socket.io) ───────────────────────────────
  telemetry: { ...DEFAULT_TELEMETRY },
  flightPath: [], // Array of [lat, lon] points
  updateTelemetry: (data) => set((s) => {
    const newTelemetry = { ...s.telemetry, ...data };
    const lastPoint = s.flightPath[s.flightPath.length - 1];
    const newPoint = [newTelemetry.lat, newTelemetry.lon];

    // Jump detection: Reset path if distance moved > ~1km (roughly 0.01 deg)
    // This handles simulation mode changes or large GPS glitches
    if (lastPoint) {
      const dist = Math.sqrt(
        Math.pow(lastPoint[0] - newPoint[0], 2) + 
        Math.pow(lastPoint[1] - newPoint[1], 2)
      );
      if (dist > 0.01) {
        return { telemetry: newTelemetry, flightPath: [newPoint] };
      }
    }

    // Normal movement: Only add to path if moved more than ~0.5m
    const moved = !lastPoint || 
      Math.abs(lastPoint[0] - newPoint[0]) > 0.000005 || 
      Math.abs(lastPoint[1] - newPoint[1]) > 0.000005;

    return { 
      telemetry: newTelemetry,
      flightPath: moved ? [...s.flightPath, newPoint] : s.flightPath
    };
  }),

  // ── Connection status ─────────────────────────────────────────────────────
  connected: false,
  setConnected: (v) => set({ connected: v }),

  // ── Mission info ──────────────────────────────────────────────────────────
  missionId:   `INS-${new Date().toISOString().slice(0, 10).replace(/-/g, '')}-001`,
  missionName: 'Inspection Mission',
  operatorName: 'Field Operator',
  setMissionId:    (v) => set({ missionId: v }),
  setMissionName:  (v) => set({ missionName: v }),
  setOperatorName: (v) => set({ operatorName: v }),

  // ── Captures (stored in React memory only — no server/DB) ────────────────
  captures: [],
  addCapture:    (cap) => set((s) => ({ captures: [...s.captures, cap] })),
  removeCapture: (id)  => set((s) => ({ captures: s.captures.filter((c) => c.id !== id) })),
  clearCaptures: ()    => set({ captures: [] }),

  // ── UI state ──────────────────────────────────────────────────────────────
  activeTab: 'dashboard', // 'dashboard' or 'map'
  videoMode:       'demo', // 'demo' | 'webcam' | 'live'
  feedsSwapped:    false,
  selectedCapture: null,
  setActiveTab: (tab) => set({ activeTab: tab }),
  setVideoMode: (mode) => set({ videoMode: mode }),
  toggleFeedsSwapped:  ()  => set((s) => ({ feedsSwapped: !s.feedsSwapped })),
  setSelectedCapture:  (id) => set({ selectedCapture: id }),

  // ── Python Pipeline State ─────────────────────────────────────────────────
  detections: [],        // Current frame's validated detections
  pipelineStatus: {
    connected: false,
    running: false,
    fps: 0,
    framesProcessed: 0,
    totalDetections: 0,
    severityCounts: { NORMAL: 0, ELEVATED: 0, WARNING: 0, CRITICAL: 0 },
    hottestEver: 0,
  },
  updateDetections: (data) => set({
    detections: data.detections || [],
  }),
  updatePipelineStatus: (status) => set({ pipelineStatus: { ...status } }),

  // ── Toast notifications ───────────────────────────────────────────────────
  toasts: [],
  addToast: (message, type = 'info') => {
    const id = Date.now();
    set((s) => ({ toasts: [...s.toasts, { id, message, type }] }));
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), 2800);
  },
}));
