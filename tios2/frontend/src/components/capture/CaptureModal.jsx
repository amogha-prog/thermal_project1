/**
 * CaptureModal — full-screen detail view for a single capture
 *
 * Shows thermal + RGB images with all telemetry metadata.
 * "SAVE IMAGES" button downloads thermal + RGB as JPEG files
 * directly to the user's local machine — no server involved.
 */

import React from 'react';
import { useTIOSStore }        from '../../store/useTIOSStore';
import { saveAllImagesLocally } from '../../utils/captureEngine';

export default function CaptureModal({ captureId, onClose }) {
  const captures = useTIOSStore((s) => s.captures);
  const cap      = captures.find((c) => c.id === captureId);
  if (!cap) return null;

  const handleSaveImages = () => {
    saveAllImagesLocally(cap);
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-bg2 border border-border rounded-lg max-w-2xl w-full overflow-hidden animate-fadeIn"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 bg-bg border-b border-border">
          <div className="flex items-center gap-3">
            <span className="font-mono text-sm text-accent font-bold">{cap.id}</span>
            <span className="font-mono text-xs text-muted">{cap.dateStr} · {cap.timeStr} IST</span>
            <span className={`font-mono text-[10px] px-2 py-0.5 rounded-sm ${cap.telemetry?.armed ? 'bg-thermal/20 text-thermal' : 'bg-dim text-muted'}`}>
              {cap.telemetry?.armed ? 'ARMED' : 'DISARMED'}
            </span>
          </div>
          <button onClick={onClose} className="text-muted hover:text-white transition-colors text-xl leading-none px-1">✕</button>
        </div>

        {/* Dual images */}
        <div className="grid grid-cols-2 gap-px bg-border">
          {[
            { src: cap.images?.thermal, label: 'THERMAL', badgeBg: 'bg-thermal' },
            { src: cap.images?.rgb,     label: 'RGB',     badgeBg: 'bg-green-600' },
          ].map(({ src, label, badgeBg }) => (
            <div key={label} className="relative bg-bg3">
              {src ? (
                <img src={src} alt={label} className="w-full h-44 object-cover" />
              ) : (
                <div className="w-full h-44 flex items-center justify-center text-muted text-sm">
                  No image
                </div>
              )}
              <span className={`absolute top-2 left-2 ${badgeBg} text-white font-mono text-[10px] px-2 py-0.5 rounded-sm font-bold tracking-wider`}>
                {label}
              </span>
            </div>
          ))}
        </div>

        {/* Metadata grid */}
        <div className="grid grid-cols-4 gap-px bg-border">
          {[
            { label: 'LAT',    value: parseFloat(cap.location?.lat || 0).toFixed(6), unit: '°N' },
            { label: 'LON',    value: parseFloat(cap.location?.lon || 0).toFixed(6), unit: '°E' },
            { label: 'ALT',    value: parseFloat(cap.location?.alt || 0).toFixed(1), unit: 'm' },
            { label: 'HDG',    value: parseFloat(cap.telemetry?.heading || 0).toFixed(0), unit: '°' },
            { label: 'MAX °C', value: parseFloat(cap.telemetry?.maxTemp || 0).toFixed(1), unit: '°C', color: 'text-thermal' },
            { label: 'MIN °C', value: parseFloat(cap.telemetry?.minTemp || 0).toFixed(1), unit: '°C' },
            { label: 'AVG °C', value: parseFloat(cap.telemetry?.avgTemp || 0).toFixed(1), unit: '°C' },
            { label: 'BAT',    value: parseFloat(cap.telemetry?.battery || 0).toFixed(0), unit: '%', color: 'text-green-400' },
          ].map(({ label, value, unit, color = 'text-[#e2eaf4]' }) => (
            <div key={label} className="bg-bg2 p-3">
              <div className="font-mono text-[9px] text-muted tracking-widest">{label}</div>
              <div className={`font-mono text-sm font-bold mt-0.5 ${color}`}>
                {value}
                <span className="text-muted text-[9px] ml-0.5 font-normal">{unit}</span>
              </div>
            </div>
          ))}
        </div>

        {/* Footer — save + close */}
        <div className="px-4 py-3 bg-bg border-t border-border flex items-center justify-between gap-3">
          <span className="font-mono text-[10px] text-muted truncate">
            {cap.telemetry?.flightMode} · {cap.telemetry?.satellites} SVs · {cap.missionId}
          </span>
          <div className="flex gap-2 shrink-0">
            {/* Download thermal + RGB images to local machine */}
            <button
              onClick={handleSaveImages}
              className="px-4 py-1.5 rounded border border-accent text-accent text-xs font-mono font-bold hover:bg-accent/10 transition-colors"
            >
              ↓ SAVE IMAGES
            </button>
            <button
              onClick={onClose}
              className="px-4 py-1.5 text-xs border border-border text-muted rounded hover:text-white hover:border-muted transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
