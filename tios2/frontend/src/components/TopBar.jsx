import React, { useEffect, useState } from 'react';
import { useTIOSStore } from '../store/useTIOSStore';

export default function TopBar({ onCapture, onSaveImages, onGeneratePDF, onExportCSV, captureCount }) {
  const connected  = useTIOSStore((s) => s.connected);
  const missionId  = useTIOSStore((s) => s.missionId);
  const toggleSwap = useTIOSStore((s) => s.toggleFeedsSwapped);
  const [clock, setClock] = useState('');

  useEffect(() => {
    const tick = () => setClock(new Intl.DateTimeFormat('en-IN', {
      timeZone: 'Asia/Kolkata',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    }).format(new Date()));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="flex items-center gap-4 px-4 h-11 bg-bg2 border-b border-border shrink-0">
      {/* Logo */}
      <span className="font-mono text-[15px] font-bold tracking-[3px] text-accent">
        TI<span className="text-thermal">OS</span>
      </span>

      {/* Connection */}
      <span className={`w-[7px] h-[7px] rounded-full shrink-0 ${connected ? 'bg-green-500 shadow-[0_0_6px_#22c55e]' : 'bg-red-500'} animate-pulse`} />
      <span className={`font-mono text-[11px] tracking-widest ${connected ? 'text-green-500' : 'text-red-400'}`}>
        {connected ? 'LIVE · DRONE-01' : 'DISCONNECTED'}
      </span>

      <div className="w-px h-5 bg-border" />
      <span className="font-mono text-[11px] text-muted">{clock} IST</span>

      <div className="ml-auto flex items-center gap-2">
        <span className="font-mono text-[11px] text-muted hidden sm:block">MISSION: {missionId}</span>

        <button
          onClick={toggleSwap}
          className="px-3 py-1 rounded border border-thermal text-thermal text-[11px] font-mono hover:bg-thermal/10 transition-colors"
        >
          SWAP
        </button>

        {/* CAPTURE — grabs frame + telemetry at this exact ms */}
        <button
          onClick={onCapture}
          className="px-4 py-1.5 rounded bg-thermal text-white font-mono text-[11px] font-bold tracking-widest hover:bg-red-500 active:scale-95 transition-all"
        >
          ● CAPTURE
        </button>

        {/* SAVE IMAGES — downloads thermal + RGB as JPEGs locally */}
        <button
          onClick={onSaveImages}
          disabled={captureCount === 0}
          className="px-3 py-1.5 rounded border border-accent text-accent text-[11px] font-mono font-bold hover:bg-accent/10 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
          title="Download latest capture images as JPEG files"
        >
          ↓ IMAGES
        </button>

        {/* EXPORT CSV — downloads all capture data to a CSV spreadsheet */}
        <button
          onClick={onExportCSV}
          disabled={captureCount === 0}
          className="px-3 py-1.5 rounded border border-[#2e7d32] text-[#4caf50] text-[11px] font-mono font-bold hover:bg-[#2e7d32]/20 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
          title="Export CSV data"
        >
          ↓ CSV
        </button>

        {/* GENERATE PDF — builds and downloads report locally */}
        <button
          onClick={onGeneratePDF}
          disabled={captureCount === 0}
          className="px-4 py-1.5 rounded bg-indigo-600 text-white font-bold text-[11px] hover:bg-indigo-500 disabled:opacity-30 disabled:cursor-not-allowed transition-all flex items-center gap-2"
        >
          ↓ PDF REPORT
          {captureCount > 0 && (
            <span className="bg-thermal text-white rounded-full px-1.5 font-mono text-[10px]">
              {captureCount}
            </span>
          )}
        </button>
      </div>
    </div>
  );
}
