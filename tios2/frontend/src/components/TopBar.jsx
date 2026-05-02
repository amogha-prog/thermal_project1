import React, { useEffect, useState } from 'react';
import { useTIOSStore } from '../store/useTIOSStore';

export default function TopBar({ onCapture, onSaveImages, onGeneratePDF, onExportCSV, captureCount }) {
  const connected  = useTIOSStore((s) => s.connected);
  const missionId  = useTIOSStore((s) => s.missionId);
  const toggleSwap = useTIOSStore((s) => s.toggleFeedsSwapped);
  const videoMode  = useTIOSStore((s) => s.videoMode);
  const setVideoMode = useTIOSStore((s) => s.setVideoMode);
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
    <div className="flex flex-col md:flex-row items-center justify-between gap-2 md:gap-4 px-2 md:px-4 py-2 md:h-14 glass-panel border-b border-white/5 shrink-0 z-50">
      {/* Left Group */}
      <div className="flex items-center gap-2 md:gap-4 w-full md:w-auto justify-between md:justify-start">
        {/* Logo */}
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 flex-shrink-0 rounded bg-gradient-to-br from-accent to-blue-600 flex items-center justify-center shadow-glow">
            <div className="w-2.5 h-2.5 bg-bg rounded-sm" />
          </div>
          <span className="font-mono text-[14px] md:text-[16px] font-bold tracking-[2px] md:tracking-[4px] text-white">
            TI<span className="text-thermal">OS</span>
          </span>
        </div>

        <div className="w-px h-6 bg-white/10 hidden md:block" />

        {/* Connection */}
        <div className="flex items-center gap-1.5 md:gap-2 bg-black/20 px-2 md:px-3 py-1 md:py-1.5 rounded-full border border-white/5">
          <span className={`w-1.5 h-1.5 md:w-2 md:h-2 rounded-full shrink-0 ${connected ? 'bg-green-500 shadow-[0_0_8px_#22c55e]' : 'bg-red-500'} animate-pulse`} />
          <span className={`font-mono text-[9px] md:text-[11px] font-bold tracking-widest ${connected ? 'text-green-400' : 'text-red-400'}`}>
            {connected ? 'LINK ACTIVE' : 'DISCONNECTED'}
          </span>
        </div>
        
        <span className="font-mono text-[9px] md:text-[11px] text-muted ml-0 md:ml-2">{clock} IST</span>
      </div>

      {/* Right Group (Controls) */}
      <div className="flex flex-wrap items-center gap-1.5 md:gap-3 justify-center md:justify-end w-full md:w-auto mt-1 md:mt-0">
        <span className="font-mono text-[11px] text-muted hidden lg:block">MISSION ID: <span className="text-white">{missionId}</span></span>

        <select
          value={videoMode}
          onChange={(e) => setVideoMode(e.target.value)}
          className="px-2 sm:px-3 py-1.5 ml-0 sm:ml-2 rounded border border-white/10 bg-black/40 text-white text-[10px] sm:text-[11px] font-mono outline-none cursor-pointer hover:bg-black/60 transition-colors"
        >
          <option value="webcam">WEBCAM</option>
          <option value="live">LIVE RTSP</option>
        </select>

        <button
          onClick={toggleSwap}
          className="px-2 sm:px-4 py-1.5 rounded border-2 border-thermal/60 text-thermal font-mono text-[10px] sm:text-[11px] font-bold hover:bg-thermal/10 transition-colors"
        >
          SWAP FEEDS
        </button>

        {/* CAPTURE — grabs frame + telemetry at this exact ms */}
        <button
          onClick={onCapture}
          className="px-3 sm:px-5 py-1.5 rounded bg-gradient-to-r from-thermal to-orange-600 text-white font-mono text-[11px] sm:text-[12px] font-bold tracking-widest hover:shadow-glow-thermal active:scale-95 transition-all shadow-lg"
        >
          ● CAPTURE
        </button>

        <div className="w-px h-6 bg-white/10 hidden sm:block mx-1" />

        {/* SAVE IMAGES */}
        <button
          onClick={onSaveImages}
          disabled={captureCount === 0}
          className="px-2 sm:px-3 py-1.5 rounded bg-white/5 border border-white/10 text-white text-[10px] sm:text-[11px] font-mono font-bold hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
          title="Download latest capture images"
        >
          ↓ IMG
        </button>

        {/* EXPORT CSV */}
        <button
          onClick={onExportCSV}
          disabled={captureCount === 0}
          className="px-2 sm:px-3 py-1.5 rounded bg-white/5 border border-white/10 text-white text-[10px] sm:text-[11px] font-mono font-bold hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
          title="Export CSV data"
        >
          ↓ CSV
        </button>

        {/* GENERATE PDF */}
        <button
          onClick={onGeneratePDF}
          disabled={captureCount === 0}
          className="px-3 sm:px-5 py-1.5 rounded bg-gradient-to-r from-blue-600 to-indigo-600 text-white font-bold font-mono tracking-widest text-[10px] sm:text-[11px] hover:shadow-glow disabled:opacity-30 disabled:cursor-not-allowed transition-all flex items-center gap-1 sm:gap-2"
        >
          ↓ REPORT
          {captureCount > 0 && (
            <span className="bg-black/30 text-white rounded-full px-1.5 sm:px-2 py-0.5 text-[9px] sm:text-[10px]">
              {captureCount}
            </span>
          )}
        </button>
      </div>
    </div>
  );
}
