/**
 * TelemetrySidebar — right panel
 * Live telemetry cards, GPS, artificial horizon, capture list
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
export default function TelemetrySidebar({ onSelectCapture, onShowBrowser }) {
  const tel           = useTIOSStore((s) => s.telemetry);
  const captures      = useTIOSStore((s) => s.captures);
  const clearCaptures = useTIOSStore((s) => s.clearCaptures);
  const addToast      = useTIOSStore((s) => s.addToast);

  const handleReset = () => {
    if (!captures.length) return;
    clearCaptures();
    addToast('All captures cleared', 'info');
  };

  const battColor =
    tel.voltage < 19.0 ? 'text-thermal' : // Critical low for 6S (< 19V per user)
    tel.voltage < 22.8 ? 'text-warn'    : // Warning for 6S (< 22.8V per user)
    'text-green-400';

  return (
    <div className="flex flex-col bg-bg2 border-l border-border overflow-y-auto w-[260px] shrink-0">

      {/* ── Telemetry cards ─────────────────────────────────────────────── */}
      <div className="p-3 border-b border-border">
        <div className="font-mono text-[10px] tracking-[2px] text-muted uppercase mb-2">
          Telemetry
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          <TelCard label="Max Temp" value={parseFloat(tel.maxTemp  || 0).toFixed(1)} unit="°C"  color="text-thermal" />
          <TelCard label="Altitude" value={parseFloat(tel.alt      || 0).toFixed(1)} unit="m"   color="text-accent"  />
          <TelCard label="Speed"    value={parseFloat(tel.speed    || 0).toFixed(1)} unit="m/s" color="text-green-400" />
          <TelCard label="Battery"  value={parseFloat(tel.voltage  || 0).toFixed(1)} unit="V"   color={battColor} />
          <TelCard label="Heading"  value={parseFloat(tel.heading  || 0).toFixed(0)} unit="°" />
        </div>
      </div>

      {/* ── GPS ─────────────────────────────────────────────────────────── */}
      <div className="p-3 border-b border-border">
        <div className="font-mono text-[10px] tracking-[2px] text-muted uppercase mb-2">
          GPS Position
        </div>
        <div className="bg-panel border border-border rounded p-2 font-mono text-[10px] space-y-1.5">
          {[
            ['LAT', parseFloat(tel.lat || 0).toFixed(6)],
            ['LON', parseFloat(tel.lon || 0).toFixed(6)],
            ['ALT', `${parseFloat(tel.alt || 0).toFixed(1)} m`],
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
          <span>R {(tel.roll  || 0).toFixed(1)}°</span>
          <span>P {(tel.pitch || 0).toFixed(1)}°</span>
          <span>Y {(tel.yaw   || 0).toFixed(0)}°</span>
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
  );
}
