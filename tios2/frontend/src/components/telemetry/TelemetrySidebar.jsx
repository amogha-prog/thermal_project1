/**
 * TelemetrySidebar — right panel
 * Live telemetry cards, GPS, artificial horizon, detection alerts, capture list
 */

import React, { useEffect, useRef } from 'react';
import { useTIOSStore } from '../../store/useTIOSStore';

// ── Artificial Horizon ────────────────────────────────────────────────────────
function ArtificialHorizon({ roll, pitch }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx  = canvas.getContext('2d');
    const W    = canvas.width;
    const H    = canvas.height;
    const rRad = ((roll  || 0) * Math.PI) / 180;
    const pPx  = (pitch || 0) * (H / 45);

    ctx.clearRect(0, 0, W, H);
    ctx.save();
    ctx.translate(W / 2, H / 2);
    ctx.rotate(rRad);

    // Sky
    ctx.fillStyle = '#1a3a5a';
    ctx.fillRect(-W, -H + pPx, W * 2, H);
    // Ground
    ctx.fillStyle = '#2a3520';
    ctx.fillRect(-W, pPx, W * 2, H);
    // Horizon line
    ctx.strokeStyle = 'rgba(255,255,255,0.4)';
    ctx.lineWidth   = 1;
    ctx.beginPath();
    ctx.moveTo(-W / 2, pPx);
    ctx.lineTo(W / 2, pPx);
    ctx.stroke();

    ctx.restore();

    // Fixed crosshair (doesn't rotate)
    ctx.strokeStyle = 'rgba(255,200,50,0.85)';
    ctx.lineWidth   = 1.5;
    ctx.beginPath(); ctx.moveTo(W/2 - 20, H/2); ctx.lineTo(W/2 - 8,  H/2); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(W/2 + 8,  H/2); ctx.lineTo(W/2 + 20, H/2); ctx.stroke();
    ctx.fillStyle = 'rgba(255,200,50,0.85)';
    ctx.beginPath(); ctx.arc(W/2, H/2, 2.5, 0, Math.PI * 2); ctx.fill();
  }, [roll, pitch]);

  return (
    <canvas
      ref={canvasRef}
      width={232}
      height={56}
      className="w-full rounded border border-border"
      style={{ background: '#1a2130' }}
    />
  );
}

// ── Telemetry card ────────────────────────────────────────────────────────────
function TelCard({ label, value, unit, color = 'text-[#e2eaf4]' }) {
  return (
    <div className="bg-panel border border-border rounded p-2">
      <div className="font-mono text-[9px] tracking-widest text-muted uppercase">{label}</div>
      <div className={`font-mono text-[15px] font-bold mt-0.5 ${color} leading-tight`}>
        {value}
        <span className="text-muted text-[9px] ml-0.5 font-normal">{unit}</span>
      </div>
    </div>
  );
}

// ── Detection alert row ───────────────────────────────────────────────────────
function DetectionRow({ det }) {
  const sevColors = {
    CRITICAL: 'border-red-500/60 bg-red-900/30 text-red-300',
    WARNING:  'border-amber-500/50 bg-amber-900/25 text-amber-300',
    ELEVATED: 'border-yellow-500/40 bg-yellow-900/20 text-yellow-200',
    NORMAL:   'border-border bg-panel text-muted',
  };
  const sevStyle = sevColors[det.severity] || sevColors.NORMAL;

  return (
    <div className={`flex items-center gap-2 p-1.5 rounded border transition-all ${sevStyle}`}>
      <div className="flex-1 min-w-0">
        <div className="flex justify-between items-center">
          <span className="font-mono text-[10px] font-bold">
            {det.max_temp?.toFixed(1)}°C
          </span>
          <span className="font-mono text-[8px] uppercase tracking-wider opacity-80">
            {det.severity}
          </span>
        </div>
        <div className="font-mono text-[8px] opacity-60 truncate mt-0.5">
          {det.anomaly_type || det.label} · {det.source?.toUpperCase()} · Δ{det.delta_t?.toFixed(0)}°C
        </div>
      </div>
    </div>
  );
}

// ── Capture list item ─────────────────────────────────────────────────────────
function CaptureRow({ cap, onSelect }) {
  return (
    <div
      onClick={() => onSelect(cap.id)}
      className="flex gap-2 items-center p-2 bg-panel border border-border rounded cursor-pointer hover:border-accent transition-colors group"
    >
      {cap.thumbnails?.thermal ? (
        <img
          src={cap.thumbnails.thermal}
          alt="thumb"
          className="w-9 h-[26px] rounded object-cover shrink-0 border border-border"
        />
      ) : (
        <div className="w-9 h-[26px] rounded bg-dim shrink-0" />
      )}
      <div className="flex-1 min-w-0">
        <div className="font-mono text-[9px] text-accent group-hover:text-white transition-colors">
          {cap.id} · {parseFloat(cap.telemetry?.maxTemp || 0).toFixed(1)}°C
        </div>
        <div className="text-[9px] text-muted truncate">
          {parseFloat(cap.location?.lat || 0).toFixed(5)}, {parseFloat(cap.location?.lon || 0).toFixed(5)}
        </div>
      </div>
      <div className="font-mono text-[9px] text-muted shrink-0">{cap.timeStr}</div>
    </div>
  );
}

// ── Main sidebar ──────────────────────────────────────────────────────────────
export default function TelemetrySidebar({ onSelectCapture, onShowBrowser, mobileOpen, onCloseMobile }) {
  const tel             = useTIOSStore((s) => s.telemetry);
  const captures        = useTIOSStore((s) => s.captures);
  const clearCaptures   = useTIOSStore((s) => s.clearCaptures);
  const addToast        = useTIOSStore((s) => s.addToast);
  const detections      = useTIOSStore((s) => s.detections);
  const pipelineStatus  = useTIOSStore((s) => s.pipelineStatus);

  const handleReset = () => {
    if (!captures.length) return;
    clearCaptures();
    addToast('All captures cleared', 'info');
  };

  const battColor =
    tel.voltage < 19.0 ? 'text-thermal' : // Critical low for 6S (< 19V per user)
    tel.voltage < 22.8 ? 'text-warn'    : // Warning for 6S (< 22.8V per user)
    'text-green-400';

  const criticalCount = detections.filter(d => d.severity === 'CRITICAL').length;
  const warningCount  = detections.filter(d => d.severity === 'WARNING').length;

  return (
    <>
      {/* Mobile backdrop */}
      {mobileOpen && (
        <div className="fixed inset-0 bg-black/60 z-[1100] lg:hidden" onClick={onCloseMobile} />
      )}
      <div className={`
        flex flex-col bg-bg2 border-l border-border overflow-y-auto w-[260px] shrink-0
        fixed right-0 top-0 bottom-0 z-[1101] transition-transform duration-300 ease-in-out
        lg:static lg:translate-x-0 lg:z-auto
        ${mobileOpen ? 'translate-x-0' : 'translate-x-full'}
      `}>

      {/* Mobile close button */}
      <button
        onClick={onCloseMobile}
        className="lg:hidden absolute top-2 right-2 z-10 w-8 h-8 flex items-center justify-center
                   rounded-full bg-white/10 text-white/70 hover:bg-white/20 hover:text-white transition-all"
      >
        ✕
      </button>



      {/* ── Live Detections ──────────────────────────────────────────────── */}
      {detections.length > 0 && (
        <div className="p-3 border-b border-border">
          <div className="font-mono text-[10px] tracking-[2px] text-muted uppercase mb-2 flex items-center gap-2">
            Live Detections
            <span className="bg-thermal text-white font-mono text-[9px] px-1.5 rounded-full leading-none py-0.5">
              {detections.length}
            </span>
            {criticalCount > 0 && (
              <span className="bg-red-600 text-white font-mono text-[8px] px-1.5 rounded-full leading-none py-0.5 animate-pulse">
                {criticalCount} CRIT
              </span>
            )}
          </div>
          <div className="flex flex-col gap-1 max-h-[120px] overflow-y-auto">
            {detections.slice(0, 5).map((det, i) => (
              <DetectionRow key={`det-${i}`} det={det} />
            ))}
          </div>
        </div>
      )}

      {/* ── Telemetry cards ─────────────────────────────────────────────── */}
      <div className="p-3 border-b border-border">
        <div className="font-mono text-[10px] tracking-[2px] text-muted uppercase mb-2">
          Flight Data
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          <TelCard label="Battery"      value={parseFloat(tel.voltage    || 0).toFixed(1)} unit="V"   color={battColor} />
          <TelCard label="Speed"        value={parseFloat(tel.speed      || 0).toFixed(1)} unit="m/s" color="text-green-400" />
        </div>
      </div>

      {/* ── Velocity (NED) ─────────────────────────────────────────────── */}
      <div className="p-3 border-b border-border">
        <div className="font-mono text-[10px] tracking-[2px] text-muted uppercase mb-1.5">
          Velocity (NED)
        </div>
        <div className="bg-panel border border-border rounded p-2 font-mono text-[10px] space-y-1">
          {[
            ['Vx (N)', `${parseFloat(tel.vx || 0).toFixed(2)} m/s`],
            ['Vy (E)', `${parseFloat(tel.vy || 0).toFixed(2)} m/s`],
            ['Vz (D)', `${parseFloat(tel.vz || 0).toFixed(2)} m/s`],
            ['Ground', `${parseFloat(tel.speed || 0).toFixed(2)} m/s`],
          ].map(([k, v]) => (
            <div key={k} className="flex justify-between">
              <span className="text-muted">{k}</span>
              <span className="text-accent">{v}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Attitude ─────────────────────────────────────────────────────── */}
      <div className="p-3 border-b border-border">
        <div className="font-mono text-[10px] tracking-[2px] text-muted uppercase mb-2">
          Attitude
        </div>
        <ArtificialHorizon roll={tel.roll} pitch={tel.pitch} />
        <div className="flex justify-between mt-1.5 font-mono text-[9px] text-muted">
          <span>R {(tel.roll  || 0).toFixed(2)}°</span>
          <span>P {(tel.pitch || 0).toFixed(2)}°</span>
          <span>Y {(tel.yaw   || 0).toFixed(1)}°</span>
        </div>
      </div>

      {/* ── GPS ─────────────────────────────────────────────────────────── */}
      <div className="p-3 border-b border-border">
        <div className="font-mono text-[10px] tracking-[2px] text-muted uppercase mb-1.5 flex items-center gap-2">
          GPS Position
          <span className={`text-[8px] px-1.5 py-0.5 rounded font-mono ${
            tel.fixType >= 3 ? 'bg-green-700/40 text-green-300' :
            tel.fixType >= 2 ? 'bg-yellow-700/40 text-yellow-300' :
            'bg-red-700/40 text-red-300'
          }`}>
            FIX {tel.fixType || 0} · {tel.satellites || 0} SAT
          </span>
        </div>
        <div className="bg-panel border border-border rounded p-2 font-mono text-[10px] space-y-1.5">
          {[
            ['LAT',     parseFloat(tel.lat || 0).toFixed(7)],
            ['LON',     parseFloat(tel.lon || 0).toFixed(7)],
            ['AGL',     `${parseFloat(tel.altAgl || tel.alt || 0).toFixed(2)} m`],
            ['MSL',     `${parseFloat(tel.altMsl || 0).toFixed(2)} m`],
          ].map(([k, v]) => (
            <div key={k} className="flex justify-between">
              <span className="text-muted">{k}</span>
              <span className="text-accent">{v}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Heading ──────────────────────────────────────────────────────── */}
      <div className="p-3 border-b border-border">
        <div className="font-mono text-[10px] tracking-[2px] text-muted uppercase mb-1.5">
          Heading
        </div>
        <div className="bg-panel border border-border rounded p-2 font-mono text-[10px] space-y-1.5">
          {[
            ['Body (Yaw)',   `${parseFloat(tel.headingBody      || tel.heading || 0).toFixed(1)}°`],
            ['Autopilot',   `${parseFloat(tel.headingAutopilot || 0).toFixed(1)}°`],
            ['COG (GPS)',    `${parseFloat(tel.cog              || 0).toFixed(1)}°`],
          ].map(([k, v]) => (
            <div key={k} className="flex justify-between">
              <span className="text-muted">{k}</span>
              <span className="text-[#e2eaf4]">{v}</span>
            </div>
          ))}
        </div>
      </div>



      {/* ── Timestamps ───────────────────────────────────────────────────── */}
      <div className="p-3 border-b border-border">
        <div className="font-mono text-[10px] tracking-[2px] text-muted uppercase mb-1.5">
          Time (IST)
        </div>
        <div className="bg-panel border border-border rounded p-2 font-mono text-[9px] space-y-1.5">
          <div className="flex justify-between">
            <span className="text-muted">System</span>
            <span className="text-[#e2eaf4]">{tel.systemDatetimeIst || '—'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted">GPS</span>
            <span className="text-accent">{tel.gpsDatetimeIst || '—'}</span>
          </div>
          {tel.timeSyncErrorSec !== null && (
            <div className="flex justify-between mt-0.5">
              <span className="text-muted">Sync Δ</span>
              <span className={`${Math.abs(tel.timeSyncErrorSec) > 0.5 ? 'text-warn' : 'text-green-400'}`}>
                {tel.timeSyncErrorSec > 0 ? '+' : ''}{parseFloat(tel.timeSyncErrorSec || 0).toFixed(3)}s
              </span>
            </div>
          )}
        </div>
      </div>

      {/* ── Captures list ────────────────────────────────────────────────── */}
      <div className="p-3 flex-1 flex flex-col">
        <div className="font-mono text-[10px] tracking-[2px] text-muted uppercase mb-2 flex items-center gap-2">
          Captures
          {captures.length > 0 && (
            <span className="bg-thermal text-white font-mono text-[10px] px-1.5 rounded-full leading-none py-0.5">
              {captures.length}
            </span>
          )}
          {captures.length > 0 && (
            <div className="ml-auto flex gap-1">
              <button
                onClick={onShowBrowser}
                className="font-mono text-[9px] px-2 py-0.5 rounded border border-accent/30
                           text-accent hover:bg-accent/10 hover:text-white
                           transition-all duration-150 active:scale-95 flex items-center gap-1"
              >
                ▤ Browse
              </button>
              <button
                onClick={handleReset}
                title="Clear all captured images"
                className="font-mono text-[9px] px-2 py-0.5 rounded border border-red-500/30
                           text-red-400/70 bg-red-500/10 hover:bg-red-500/20 hover:text-red-300
                           transition-all duration-150 hover:scale-105 active:scale-95 flex items-center gap-1"
              >
                <span>↺</span>
              </button>
            </div>
          )}
        </div>

        {captures.length === 0 ? (
          <p className="text-[11px] text-muted text-center py-6 leading-relaxed">
            No captures yet.<br />
            Press <span className="text-thermal font-bold">● CAPTURE</span> to begin.
          </p>
        ) : (
          <div className="flex flex-col gap-1.5 overflow-y-auto flex-1">
            {[...captures].reverse().map((cap) => (
              <CaptureRow key={cap.id} cap={cap} onSelect={onSelectCapture} />
            ))}
          </div>
        )}
      </div>
    </div>
    </>
  );
}
