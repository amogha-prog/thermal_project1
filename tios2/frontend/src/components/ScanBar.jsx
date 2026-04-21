/**
 * ScanBar — bottom bar with live thermal intensity histogram
 */

import React, { useEffect, useRef } from 'react';
import { useTIOSStore } from '../store/useTIOSStore';

export default function ScanBar() {
  const canvasRef    = useRef(null);
  const containerRef = useRef(null);
  const dataRef      = useRef(new Array(300).fill(0).map(() => Math.random() * 20 + 5));
  const rafRef       = useRef(null);
  const tel            = useTIOSStore((s) => s.telemetry);
  const detections     = useTIOSStore((s) => s.detections);
  const pipelineStatus = useTIOSStore((s) => s.pipelineStatus);

  // Resize canvas to container
  useEffect(() => {
    const obs = new ResizeObserver(() => {
      if (canvasRef.current && containerRef.current) {
        canvasRef.current.width  = containerRef.current.clientWidth;
        canvasRef.current.height = 28;
      }
    });
    if (containerRef.current) obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, []);

  // Animated histogram
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    const draw = () => {
      dataRef.current.shift();
      const base  = tel.maxTemp || 22;
      const spike = Math.random() > 0.94 ? Math.random() * 20 : 0;
      dataRef.current.push(base + spike + (Math.random() - 0.5) * 4);

      const W = canvas.width, H = canvas.height;
      ctx.clearRect(0, 0, W, H);
      const bw = W / dataRef.current.length;

      dataRef.current.forEach((v, i) => {
        const norm = Math.min(1, (v - 15) / 60);
        ctx.fillStyle = `rgba(${Math.round(norm * 255)},${Math.round((1 - norm) * 150)},50,0.75)`;
        const bh = Math.max(1, v * 0.43);
        ctx.fillRect(i * bw, H - bh, bw - 0.3, bh);
      });

      rafRef.current = requestAnimationFrame(draw);
    };

    rafRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(rafRef.current);
  }, [tel.maxTemp]);

  return (
    <div className="flex items-center gap-4 px-4 h-14 glass-panel border-t border-white/5 shrink-0 z-50">
      <div className="flex flex-col">
        <span className="font-mono text-[9px] text-accent font-bold tracking-widest uppercase">Thermal Scan</span>
        <span className="font-mono text-[8px] text-white/50 tracking-wider">INTENSITY HISTOGRAM</span>
      </div>

      <div ref={containerRef} className="flex-1 h-8 border border-white/10 rounded overflow-hidden bg-black/40 shadow-inner">
        <canvas ref={canvasRef} height={32} className="w-full h-full block opacity-90" />
      </div>

      {/* Live flight readouts */}
      <div className="flex gap-4 shrink-0 bg-black/20 px-4 py-1.5 rounded-full border border-white/5">
        {[
          { label: 'SPD', value: `${parseFloat(tel.speed     || 0).toFixed(1)} m/s` },
          { label: 'CLB', value: `${parseFloat(tel.climbRate || 0).toFixed(1)} m/s` },
          { label: 'HDG', value: `${parseFloat(tel.heading   || 0).toFixed(0)}°`    },
          { label: 'PWR', value: `${parseFloat(tel.voltage   || 0).toFixed(1)} V`   },
        ].map(({ label, value }) => (
          <div key={label} className="text-center w-12 flex flex-col justify-center">
            <div className="font-mono text-[8px] text-white/50 tracking-widest mb-0.5">{label}</div>
            <div className="font-mono text-[11px] text-accent font-bold leading-none">{value}</div>
          </div>
        ))}

        <div className="w-px h-6 bg-white/10 mx-1" />

        {/* Detection counter */}
        <div className="text-center w-10 flex flex-col justify-center">
          <div className="font-mono text-[8px] text-white/50 tracking-widest mb-0.5">DETS</div>
          <div className={`font-mono text-[11px] font-bold leading-none ${
            detections.length > 0 ? 'text-thermal shadow-glow-thermal' : 'text-accent'
          }`}>
            {detections.length}
          </div>
        </div>

        <div className="w-px h-6 bg-white/10 mx-1" />

        {/* Pipeline indicator */}
        <div className="text-center w-12 flex flex-col justify-center">
          <div className="font-mono text-[8px] text-white/50 tracking-widest mb-0.5">PIPE</div>
          <div className={`font-mono text-[11px] font-bold leading-none ${
            pipelineStatus.connected ? 'text-green-400' : 'text-white/30'
          }`}>
            {pipelineStatus.connected ? 'ACTIVE' : 'OFF'}
          </div>
        </div>
      </div>
    </div>
  );
}
