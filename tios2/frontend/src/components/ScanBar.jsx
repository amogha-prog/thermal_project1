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
  const tel          = useTIOSStore((s) => s.telemetry);

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
    <div className="flex items-center gap-3 px-4 h-[52px] bg-bg2 border-t border-border shrink-0">
      <span className="font-mono text-[10px] text-muted whitespace-nowrap">THERMAL SCAN</span>

      <div ref={containerRef} className="flex-1 h-7 border border-border rounded overflow-hidden bg-bg3">
        <canvas ref={canvasRef} height={28} className="w-full h-full block" />
      </div>

      {/* Live flight readouts */}
      <div className="flex gap-4 shrink-0">
        {[
          { label: 'SPD', value: `${parseFloat(tel.speed     || 0).toFixed(1)} m/s` },
          { label: 'CLB', value: `${parseFloat(tel.climbRate || 0).toFixed(1)} m/s` },
          { label: 'HDG', value: `${parseFloat(tel.heading   || 0).toFixed(0)}°`    },
          { label: 'PWR', value: `${parseFloat(tel.voltage   || 0).toFixed(1)} V`   },
        ].map(({ label, value }) => (
          <div key={label} className="text-center">
            <div className="font-mono text-[8px] text-muted tracking-widest">{label}</div>
            <div className="font-mono text-[11px] text-accent font-bold leading-tight">{value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
