/**
 * VideoPanel — thermal camera viewport
 *
 * DEMO mode : animated FLIR-style person-detection simulation
 * LIVE mode : webcam + thermal palette + auto-range + hot-spot tracking
 *
 * Temperature: fully auto-ranged per frame (no fixed limits)
 * Palettes   : Ironbow | Rainbow | Inferno | Lava | Blue (brand)
 */

import React, { useEffect, useRef, useState, forwardRef, useCallback } from 'react';
import { useTIOSStore } from '../../store/useTIOSStore';

// ── Palette LUT builder ────────────────────────────────────────────────────────
function buildLUT(stops) {
  const r = new Uint8ClampedArray(256);
  const g = new Uint8ClampedArray(256);
  const b = new Uint8ClampedArray(256);
  for (let i = 0; i < 256; i++) {
    const v = i / 255;
    let s = 0;
    while (s < stops.length - 2 && v > stops[s + 1][0]) s++;
    const span = stops[s + 1][0] - stops[s][0];
    const t = span < 1e-9 ? 0 : (v - stops[s][0]) / span;
    r[i] = Math.round(stops[s][1] + (stops[s+1][1] - stops[s][1]) * t);
    g[i] = Math.round(stops[s][2] + (stops[s+1][2] - stops[s][2]) * t);
    b[i] = Math.round(stops[s][3] + (stops[s+1][3] - stops[s][3]) * t);
  }
  return { r, g, b };
}

const PALETTES = {
  whitehot: {
    name: 'White Hot', label: 'W-HT', accent: '#ffffff',
    lut: buildLUT([[0, 0, 0, 0], [1.0, 255, 255, 255]]),
  },
  blackhot: {
    name: 'Black Hot', label: 'B-HT', accent: '#555555',
    lut: buildLUT([[0, 255, 255, 255], [1.0, 0, 0, 0]]),
  },
  ironbow: {
    name: 'Ironbow', label: 'IRON', accent: '#ff8c42',
    lut: buildLUT([
      [0,   5,   0,   45 ], [0.15, 60,  0,   140], [0.35, 180, 10,  120],
      [0.55, 235, 30,  10 ], [0.80, 255, 160, 0  ], [1.0,  255, 255, 220],
    ]),
  },
  rainbow: {
    name: 'Rainbow', label: 'RNBW', accent: '#00e5ff',
    lut: buildLUT([
      [0,    0,   0,   255], [0.25, 0,   255, 255], [0.50, 0,   255, 0  ],
      [0.75, 255, 255, 0  ], [1.0,  255, 0,   0  ],
    ]),
  },
  lava: {
    name: 'Lava', label: 'LAVA', accent: '#ffcc00',
    lut: buildLUT([
      [0,    0,   0,   0  ], [0.25, 80,  0,   0  ], [0.55, 225, 20,  0  ],
      [0.82, 255, 160, 0  ], [1.0,  255, 255, 180],
    ]),
  },
  arctic: {
    name: 'Arctic', label: 'ARCT', accent: '#00d4ff',
    lut: buildLUT([
      [0,    255, 255, 255], [0.22, 0,   255, 255], [0.48, 0,   110, 255],
      [0.78, 140, 0,   255], [1.0,  10,  0,   25],
    ]),
  },
  brand: {
    name: 'Blue', label: 'BLUE', accent: '#4B6FBF',
    lut: buildLUT([[0, 238, 245, 255], [0.5, 75, 111, 191], [1.0, 8, 31, 96]]),
  },
};

const PALETTE_KEYS = Object.keys(PALETTES);

// ── Temp → RGB ─────────────────────────────────────────────────────────────────
function applyLUT(luma, lut) {
  return [lut.r[luma], lut.g[luma], lut.b[luma]];
}
function lumaToTemp(luma, minT, maxT) {
  return minT + (luma / 255) * (maxT - minT);
}

// (tracking removed)

// ── Draw helpers (always white text + dark backing) ────────────────────────────
function drawLabel(ctx, text, x, y, fs = 9, bold = true) {
  ctx.save();
  ctx.font = `${bold ? 'bold ' : ''}${fs}px "JetBrains Mono",monospace`;
  const tw = ctx.measureText(text).width;
  ctx.fillStyle = 'rgba(15, 23, 42, 0.75)'; // Darker glass bg
  ctx.fillRect(x - 3, y - fs - 3, tw + 9, fs + 7);
  ctx.fillStyle = '#00e5ff'; // Cyber cyan text
  ctx.fillText(text, x + 1, y);
  ctx.restore();
}

function drawCrosshair(ctx, x, y, label) {
  ctx.save();
  const cs = 12;
  ctx.strokeStyle = 'rgba(0, 229, 255, 0.9)'; // Cyan glow
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  ctx.moveTo(x-cs,y); ctx.lineTo(x-4,y);
  ctx.moveTo(x+4,y);  ctx.lineTo(x+cs,y);
  ctx.moveTo(x,y-cs); ctx.lineTo(x,y-4);
  ctx.moveTo(x,y+4);  ctx.lineTo(x,y+cs);
  ctx.stroke();
  ctx.beginPath(); ctx.arc(x,y, 2, 0, Math.PI*2); ctx.fill(); // Center dot
  drawLabel(ctx, label, x+cs+4, y+4, 10);
  ctx.restore();
}

function drawLegend(ctx, W, H, lut, minT, maxT) {
  const bw = 12, bh = Math.floor(H * 0.52);
  const bx = W - 36, by = Math.floor((H - bh) / 2);
  for (let row = 0; row < bh; row++) {
    const luma = Math.round(255 - (row / bh) * 255);
    ctx.fillStyle = `rgb(${lut.r[luma]},${lut.g[luma]},${lut.b[luma]})`;
    ctx.fillRect(bx, by+row, bw, 1);
  }
  ctx.strokeStyle = 'rgba(0, 229, 255, 0.4)';
  ctx.lineWidth = 1;
  ctx.strokeRect(bx, by, bw, bh);

  ctx.font = 'bold 8.5px "JetBrains Mono",monospace';
  [[maxT, 0],[Math.round((minT+maxT)/2), 0.5],[minT, 1]].forEach(([t, frac]) => {
    const ty = by + frac * bh;
    const lbl = `${t.toFixed(0)}°C`;
    const tw = ctx.measureText(lbl).width;
    ctx.fillStyle = 'rgba(15, 23, 42, 0.7)';
    ctx.fillRect(bx - tw - 8, ty - 6, tw + 8, 12);
    ctx.fillStyle = '#00e5ff';
    ctx.textAlign = 'right';
    ctx.fillText(lbl, bx - 4, ty + 3);
  });
  ctx.textAlign = 'left';
}

// ── Detection overlay ────────────────────────────────────────────────────────────
function drawDetections(ctx, W, H, detections) {
  if (!detections || detections.length === 0) return;

  detections.forEach((det) => {
    // Map normalized center + size back to canvas coordinates
    const cx = det.cx * W;
    const cy = det.cy * H;
    // Detection may have pixel coords or normalized. Handle both.
    let dx, dy, dw, dh;
    if (det.x !== undefined && det.w !== undefined && det.x > 1) {
      // Pixel-based coords from Python (scale from detection frame to canvas)
      const scaleX = W / 640;
      const scaleY = H / 480;
      dx = det.x * scaleX;
      dy = det.y * scaleY;
      dw = det.w * scaleX;
      dh = det.h * scaleY;
    } else {
      // Normalized — use center
      dw = Math.max(30, W * 0.08);
      dh = Math.max(30, H * 0.08);
      dx = cx - dw / 2;
      dy = cy - dh / 2;
    }

    // Severity color
    const colors = {
      CRITICAL: '#ff2020',
      WARNING:  '#ff8c00',
      ELEVATED: '#ffd700',
      NORMAL:   '#00e5ff',
    };
    const color = colors[det.severity] || colors.NORMAL;

    // Draw animated bounding box
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.shadowColor = color;
    ctx.shadowBlur = 8;
    ctx.strokeRect(dx, dy, dw, dh);
    ctx.shadowBlur = 0;

    // Corner brackets (tactical look)
    const cs = Math.min(10, dw / 4);
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.moveTo(dx, dy + cs); ctx.lineTo(dx, dy); ctx.lineTo(dx + cs, dy);
    ctx.moveTo(dx + dw - cs, dy); ctx.lineTo(dx + dw, dy); ctx.lineTo(dx + dw, dy + cs);
    ctx.moveTo(dx + dw, dy + dh - cs); ctx.lineTo(dx + dw, dy + dh); ctx.lineTo(dx + dw - cs, dy + dh);
    ctx.moveTo(dx + cs, dy + dh); ctx.lineTo(dx, dy + dh); ctx.lineTo(dx, dy + dh - cs);
    ctx.stroke();

    // Temperature label
    const label = `${det.max_temp?.toFixed(1)}°C`;
    const sevLabel = det.label || det.severity || '';
    ctx.font = 'bold 9px "Space Mono",monospace';
    const tw = ctx.measureText(label).width;
    ctx.fillStyle = color;
    ctx.globalAlpha = 0.85;
    ctx.fillRect(dx, dy - 16, tw + 6, 14);
    ctx.globalAlpha = 1;
    ctx.fillStyle = '#000';
    ctx.fillText(label, dx + 3, dy - 5);

    // Severity badge
    if (sevLabel && (det.severity === 'CRITICAL' || det.severity === 'WARNING')) {
      const sw = ctx.measureText(sevLabel).width;
      ctx.fillStyle = color;
      ctx.globalAlpha = 0.85;
      ctx.fillRect(dx + dw - sw - 6, dy + dh + 2, sw + 6, 12);
      ctx.globalAlpha = 1;
      ctx.fillStyle = '#000';
      ctx.font = 'bold 8px "Space Mono",monospace';
      ctx.fillText(sevLabel, dx + dw - sw - 3, dy + dh + 11);
    }

    ctx.restore();
  });
}





// ── DEMO simulation ────────────────────────────────────────────────────────────
function useThermalSim(canvasRef, active, paletteKey, detections) {
  const rafRef = useRef(null);
  const t0     = useRef(0);
  const paletteRef = useRef(PALETTES[paletteKey]?.lut ?? PALETTES.ironbow.lut);
  const detectionsRef = useRef(detections);

  useEffect(() => {
    paletteRef.current = PALETTES[paletteKey]?.lut ?? PALETTES.ironbow.lut;
    detectionsRef.current = detections;
  }, [paletteKey, detections]);

  const people = useRef([
    { x:0.12, y:0.58, bw:0.072, bh:0.32, temp:36.8, ph:0.0 },
    { x:0.28, y:0.56, bw:0.060, bh:0.29, temp:37.5, ph:1.1 },
    { x:0.47, y:0.55, bw:0.068, bh:0.30, temp:36.5, ph:2.3 },
    { x:0.63, y:0.57, bw:0.055, bh:0.27, temp:37.2, ph:0.7 },
    { x:0.77, y:0.56, bw:0.050, bh:0.25, temp:36.9, ph:1.8 },
    { x:0.90, y:0.54, bw:0.040, bh:0.22, temp:37.1, ph:3.1 },
  ]);

  useEffect(() => {
    if (!active) { cancelAnimationFrame(rafRef.current); return; }
    t0.current = performance.now();
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    // Requested range: up to 100 degree
    const minT = 20, maxT = 100;

    let lastDraw = 0;

    const draw = (ts) => {
      rafRef.current = requestAnimationFrame(draw);
      if (ts - lastDraw < 50) return; // Cap at 20 FPS
      lastDraw = ts;

      const dt = (ts - t0.current) / 1000;
      const W  = canvas.width, H = canvas.height;
      if (!W || !H) return;

      const sw = Math.max(1, Math.ceil(W/4)), sh = Math.max(1, Math.ceil(H/4));
      const img = ctx.createImageData(sw, sh);
      const d   = img.data;
      const lut = paletteRef.current;

      for (let py = 0; py < sh; py++) {
        for (let px = 0; px < sw; px++) {
          const nx = px/sw, ny = py/sh;
          let temp = 22 + ny*3 + Math.sin(nx*6+dt*.05)*.8 + Math.cos(ny*4-dt*.04)*.6;
          if (nx>.50 && nx<.90 && ny>.08 && ny<.44) temp += 3.5 + Math.sin(nx*14+dt*.02)*.5;
          if (nx>.02 && nx<.24 && ny>.10 && ny<.42) temp += 2.5;

          people.current.forEach(p => {
            const pcx = p.x + Math.sin(dt*.07+p.ph)*.007;
            const dx  = (nx-pcx)/(p.bw*.88);
            const dy  = (ny-p.y )/(p.bh*.55);
            const d2  = dx*dx + dy*dy;
            if (d2 < 1.8) {
              const falloff = Math.exp(-d2*2.0);
              const hd      = ny < p.y ? .6 : 0;
              temp += (p.temp - 22 + hd) * falloff + Math.sin(dt*.4+p.ph)*.15*falloff;
            }
          });

          const luma = Math.max(0, Math.min(255, Math.round((temp-minT)/(maxT-minT)*255)));
          const [r,g,b] = applyLUT(luma, lut);
          const idx = (py*sw+px)*4;
          d[idx]=r; d[idx+1]=g; d[idx+2]=b; d[idx+3]=255;
        }
      }

      const off = document.createElement('canvas');
      off.width=sw; off.height=sh;
      off.getContext('2d').putImageData(img, 0, 0);
      ctx.imageSmoothingEnabled=true; ctx.imageSmoothingQuality='high';
      ctx.drawImage(off, 0, 0, W, H);

      // Scan-line
      ctx.fillStyle='rgba(0,0,0,0.02)';
      for (let sy=0; sy<H; sy+=2) ctx.fillRect(0,sy,W,1);

      // Centre crosshair with ambient temperature
      drawCrosshair(ctx, W/2, H/2, `${(22+Math.sin(dt*.2)*.5).toFixed(1)}°C`);
      drawLegend(ctx, W, H, lut, minT, maxT);
      drawDetections(ctx, W, H, detectionsRef.current);
      drawLabel(ctx, `${(dt%60).toFixed(0).padStart(2,'0')}s`, 6, H-6, 8, false);
    };
    rafRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(rafRef.current);
  }, [active]); // Removed paletteKey and detections ref to preserve stream!
}

// ── RGB simulation ─────────────────────────────────────────────────────────────
function useRgbSim(canvasRef, active) {
  const rafRef = useRef(null);
  const t0     = useRef(0);

  useEffect(() => {
    if (!active) { cancelAnimationFrame(rafRef.current); return; }
    t0.current = performance.now();
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    const draw = (ts) => {
      const dt = (ts-t0.current)/1000;
      const W = canvas.width, H = canvas.height;
      if (!W||!H) { rafRef.current=requestAnimationFrame(draw); return; }

      const sky=ctx.createLinearGradient(0,0,0,H*.4);
      sky.addColorStop(0,'#1a2535'); sky.addColorStop(1,'#2a3a50');
      ctx.fillStyle=sky; ctx.fillRect(0,0,W,H*.4);
      ctx.fillStyle='#2a3520'; ctx.fillRect(0,H*.4,W,H*.6);

      [[.15,.5,.08,.25],[.3,.5,.06,.35],[.55,.5,.07,.28],[.7,.5,.09,.22],[.82,.5,.05,.32]]
        .forEach(([x,y,w,h])=>{ ctx.fillStyle='#3a4555'; ctx.fillRect(x*W,H*(y-h),w*W,h*H); });

      const cx=W*.5+Math.sin(dt*.2)*W*.02, cy=H*.45+Math.cos(dt*.15)*H*.015;
      ctx.strokeStyle='rgba(0,212,255,0.6)'; ctx.lineWidth=1;
      ctx.beginPath(); ctx.moveTo(cx-20,cy); ctx.lineTo(cx+20,cy); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(cx,cy-20); ctx.lineTo(cx,cy+20); ctx.stroke();
      ctx.beginPath(); ctx.arc(cx,cy,12,0,Math.PI*2); ctx.stroke();
      ctx.fillStyle='rgba(0,212,255,0.85)'; ctx.font='9px "Space Mono",monospace';
      ctx.fillText('NADIR', cx+16, cy-4);
      rafRef.current=requestAnimationFrame(draw);
    };
    rafRef.current=requestAnimationFrame(draw);
    return ()=>cancelAnimationFrame(rafRef.current);
  }, [active]);
}

// ── RTSP Stream relay (via JSMpeg WebSocket) ───────────────────────────────────
function useRtspStream(canvasRef, active, isThermal, paletteKey, detections) {
  const playerRef = useRef(null);
  const paletteRef = useRef(PALETTES[paletteKey]?.lut ?? PALETTES.ironbow.lut);
  const detectionsRef = useRef(detections);

  useEffect(() => {
    paletteRef.current = PALETTES[paletteKey]?.lut ?? PALETTES.ironbow.lut;
    detectionsRef.current = detections;
  }, [paletteKey, detections]);

  useEffect(() => {
    if (!active || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx    = canvas.getContext('2d', { willReadFrequently: isThermal });
    const port   = isThermal ? 9999 : 9998;
    const url    = `ws://${window.location.hostname}:${port}`;

    let smoothMin = 0, smoothMax = 255;

    // JSMpeg config
    const hiddenCanvas = document.createElement('canvas');

    // JSMpeg decoded frame handler
    const onFrame = () => {
      const lut = paletteRef.current;
      const W = canvas.width, H = canvas.height;
      if (!W || !H || !hiddenCanvas.width || !hiddenCanvas.height) return;

      // Draw original frame (MPEG1) to canvas
      ctx.drawImage(hiddenCanvas, 0, 0, W, H);

      if (isThermal) {
        // FAST ZERO-ALLOCATION SINGLE-PASS PIXEL MANIPULATION
        const frame = ctx.getImageData(0, 0, W, H);
        const d = frame.data;
        const pixelCount = W * H;
        let rawMin = 255, rawMax = 0;
        const span = Math.max(1, smoothMax - smoothMin);
        
        let cLuma = 0;
        const cx = Math.floor(W / 2), cy = Math.floor(H / 2);
        const cIdx = cy * W + cx;

        for (let i = 0; i < pixelCount; i++) {
          const bi = i * 4;
          // Approximate luma quickly
          const l = (d[bi] * 77 + d[bi+1] * 150 + d[bi+2] * 29) >> 8;
          if (l < rawMin) rawMin = l;
          if (l > rawMax) rawMax = l;
          if (i === cIdx) cLuma = l;

          // Apply palette mapped to previous frame bounds mapping
          const norm = Math.max(0, Math.min(255, Math.round(((l - smoothMin) / span) * 255)));
          d[bi]   = lut.r[norm];
          d[bi+1] = lut.g[norm];
          d[bi+2] = lut.b[norm];
        }

        smoothMin = smoothMin * 0.85 + rawMin * 0.15;
        smoothMax = smoothMax * 0.85 + rawMax * 0.15;
        
        ctx.putImageData(frame, 0, 0);

        // Scan-line & Legends
        ctx.fillStyle = 'rgba(0,0,0,0.02)';
        for (let sy = 0; sy < H; sy += 2) ctx.fillRect(0, sy, W, 1);

        const tel = useTIOSStore.getState().telemetry;
        let cTempText = "0.0";
        if (tel && tel.maxTemp !== undefined) {
           cTempText = Math.max(20, tel.maxTemp).toFixed(1);
        } else {
           const minT = 20, maxT = 100;
           const cNorm = Math.round(((cLuma - smoothMin) / span) * 255);
           cTempText = (minT + (cNorm / 255) * (maxT - minT)).toFixed(1);
        }

        drawCrosshair(ctx, cx, cy, `${cTempText}°C`);
        drawLegend(ctx, W, H, lut, 20, 100);
        drawDetections(ctx, W, H, detectionsRef.current);
        drawLabel(ctx, '● LIVE STREAM', 6, H - 6, 9);
      } else {
         // Ordinary RGB feed overlay
         drawLabel(ctx, '● LIVE STREAM', 6, H - 6, 9);
         drawCrosshair(ctx, W/2, H/2, 'NADIR');
      }
    };

    // Note: window.JSMpeg is available from the script tag in index.html
    if (window.JSMpeg) {
      playerRef.current = new window.JSMpeg.Player(url, {
        canvas: hiddenCanvas, // Decode to hidden canvas
        onVideoDecode: () => onFrame(),
        disableWebAssembly: false,
        videoBufferSize: 1024 * 1024,
        audio: false
      });
    } else {
      console.error('[Stream] JSMpeg not found. Ensure /jsmpeg.min.js is in public/ and linked in index.html');
    }

    return () => {
      if (playerRef.current) {
        try {
          if (typeof playerRef.current.destroy === 'function') {
            playerRef.current.destroy();
          }
          playerRef.current = null;
        } catch (e) {
          console.warn('[Stream] Error destroying player:', e);
        }
      }
    };
  }, [active, isThermal]); // Palette + detections refs used safely!
}


// ── Webcam Stream (for mobile/testing) ──────────────────────────────────────────
function useWebcam(canvasRef, active, isThermal, paletteKey, detections) {
  const videoRef = useRef(null);
  const rafRef = useRef(null);
  const paletteRef = useRef(PALETTES[paletteKey]?.lut ?? PALETTES.ironbow.lut);
  const detectionsRef = useRef(detections);
  // Face detector ref — initialized once, reused every frame
  const faceDetectorRef = useRef(null);
  // Stable list of face-derived detections updated at ~10fps
  const faceDetectionsRef = useRef([]);
  const lastFaceDetectTime = useRef(0);

  useEffect(() => {
    paletteRef.current = PALETTES[paletteKey]?.lut ?? PALETTES.ironbow.lut;
    detectionsRef.current = detections;
  }, [paletteKey, detections]);

  useEffect(() => {
    if (!active || !canvasRef.current) return;

    const video = document.createElement('video');
    video.setAttribute('playsinline', '');
    video.setAttribute('autoplay', '');
    video.muted = true;
    videoRef.current = video;

    const hiddenCanvas = document.createElement('canvas');;
    const hiddenCtx = hiddenCanvas.getContext('2d', { willReadFrequently: true });

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d', { willReadFrequently: isThermal });

    let smoothMin = 0, smoothMax = 255;
    let localActive = true;

    // Initialize FaceDetector (Chrome 74+ / Edge) — graceful fallback otherwise
    if ('FaceDetector' in window && !faceDetectorRef.current) {
      try {
        faceDetectorRef.current = new window.FaceDetector({
          fastMode: true,
          maxDetectedFaces: 8,
        });
      } catch (e) {
        faceDetectorRef.current = null;
      }
    }

    const startCamera = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } }
        });
        video.srcObject = stream;

        video.onloadedmetadata = () => {
          video.play();

          const drawFrame = (ts) => {
            if (!localActive) return;
            rafRef.current = requestAnimationFrame(drawFrame);

            const W = canvas.width;
            const H = canvas.height;
            if (!W || !H || video.readyState !== video.HAVE_ENOUGH_DATA) return;
            const lut = paletteRef.current;

            if (!isThermal) {
              // ── RGB passthrough ──
              ctx.drawImage(video, 0, 0, W, H);
            } else {
              // ── Thermal rendering — process at 320×240 for performance ──
              const procW = 320, procH = 240;
              hiddenCanvas.width  = procW;
              hiddenCanvas.height = procH;
              hiddenCtx.drawImage(video, 0, 0, procW, procH);

              const frame     = hiddenCtx.getImageData(0, 0, procW, procH);
              const d         = frame.data;
              const pixelCount = procW * procH;
              let rawMin = 255, rawMax = 0;
              const span = Math.max(1, smoothMax - smoothMin);

              // Centre-pixel luma for crosshair temperature
              const cIdx = (Math.floor(procH / 2) * procW + Math.floor(procW / 2)) * 4;
              const cLuma = (d[cIdx] * 77 + d[cIdx+1] * 150 + d[cIdx+2] * 29) >> 8;

              // Single-pass: compute luma → track range → apply palette
              for (let i = 0; i < pixelCount; i++) {
                const bi = i << 2;
                const l = (d[bi] * 77 + d[bi+1] * 150 + d[bi+2] * 29) >> 8;
                if (l < rawMin) rawMin = l;
                if (l > rawMax) rawMax = l;
                const norm = Math.max(0, Math.min(255, Math.round(((l - smoothMin) / span) * 255)));
                d[bi]   = lut.r[norm];
                d[bi+1] = lut.g[norm];
                d[bi+2] = lut.b[norm];
              }

              smoothMin = smoothMin * 0.85 + rawMin * 0.15;
              smoothMax = smoothMax * 0.85 + rawMax * 0.15;

              hiddenCtx.putImageData(frame, 0, 0);
              ctx.drawImage(hiddenCanvas, 0, 0, W, H);

              // Scanline overlay (subtle CRT effect)
              ctx.fillStyle = 'rgba(0,0,0,0.02)';
              for (let sy = 0; sy < H; sy += 2) ctx.fillRect(0, sy, W, 1);

              // ── Centre temperature label ──
              const minT = 20, maxT = 100;
              const cNorm  = Math.round(((cLuma - smoothMin) / span) * 255);
              const cTempText = (minT + (Math.max(0, Math.min(255, cNorm)) / 255) * (maxT - minT)).toFixed(1);

              // ── Async Face Detection at ~10 fps ──
              if (faceDetectorRef.current && (ts - lastFaceDetectTime.current > 100)) {
                lastFaceDetectTime.current = ts;
                faceDetectorRef.current.detect(video)
                  .then((faces) => {
                    // Map face bounding boxes → detection objects with realistic body temps
                    faceDetectionsRef.current = faces.map((face) => {
                      const bb = face.boundingBox;
                      // Normalise to 0-1
                      const vw = video.videoWidth  || W;
                      const vh = video.videoHeight || H;
                      const cx = (bb.x + bb.width  / 2) / vw;
                      const cy = (bb.y + bb.height / 2) / vh;
                      const fw = bb.width  / vw;
                      const fh = bb.height / vh;
                      // Realistic face temperature: 35.5 – 37.5 °C with slight jitter
                      const temp = 35.5 + Math.random() * 2.0;
                      return {
                        cx, cy,
                        w: Math.max(fw, 0.08),
                        h: Math.max(fh, 0.10),
                        max_temp: parseFloat(temp.toFixed(1)),
                        severity: 'WARNING',
                        label: 'HUMAN',
                      };
                    });
                  })
                  .catch(() => { /* silence errors on unsupported frames */ });
              }

              // Draw detections: prefer FaceDetector results; fall back to Python pipeline
              const detsToDraw = faceDetectionsRef.current.length > 0
                ? faceDetectionsRef.current
                : detectionsRef.current;

              drawCrosshair(ctx, W / 2, H / 2, `${cTempText}°C`);
              drawLegend(ctx, W, H, lut, minT, maxT);
              drawDetections(ctx, W, H, detsToDraw);
            }

            // Timestamp label
            const now = new Date();
            const timeStr = `${now.getHours().toString().padStart(2,'0')}:${now.getMinutes().toString().padStart(2,'0')}:${now.getSeconds().toString().padStart(2,'0')}`;
            drawLabel(ctx, timeStr, 6, H - 6, 8, false);
          };

          rafRef.current = requestAnimationFrame(drawFrame);
        };
      } catch (err) {
        console.error('Error accessing camera:', err);
      }
    };

    startCamera();

    return () => {
      localActive = false;
      cancelAnimationFrame(rafRef.current);
      if (video.srcObject) {
        video.srcObject.getTracks().forEach((t) => t.stop());
        video.srcObject = null;
      }
      videoRef.current = null;
      faceDetectionsRef.current = [];
    };
  }, [active, isThermal]);
}


// ── VideoPanel component ───────────────────────────────────────────────────────
const VideoPanel = forwardRef(function VideoPanel({ type }, canvasRef) {
  const containerRef = useRef(null);
  const isThermal    = type === 'thermal';
  const detections   = useTIOSStore((s) => s.detections);

  // State
  const [paletteIdx, setPaletteIdx] = useState(0);
  const paletteKey   = PALETTE_KEYS[paletteIdx];
  const paletteDef   = PALETTES[paletteKey];
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Zoom/Pan State
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const isDragging = useRef(false);
  const lastMouse = useRef({ x: 0, y: 0 });

  const cyclePalette = useCallback(() => setPaletteIdx(i => (i+1) % PALETTE_KEYS.length), []);

  useEffect(() => {
    if (typeof ResizeObserver === 'undefined') return;
    const obs = new ResizeObserver(() => {
      if (canvasRef.current && containerRef.current) {
        canvasRef.current.width  = containerRef.current.clientWidth;
        canvasRef.current.height = containerRef.current.clientHeight;
      }
    });
    if (containerRef.current) obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, [isFullscreen, canvasRef]);

  const videoMode = useTIOSStore((s) => s.videoMode);

  useThermalSim(canvasRef,  videoMode === 'demo' && isThermal,  paletteKey, isThermal ? detections : []);
  useRgbSim(canvasRef,      videoMode === 'demo' && !isThermal);
  
  useRtspStream(canvasRef, videoMode === 'live',  isThermal,   paletteKey, detections);
  
  useWebcam(canvasRef, videoMode === 'webcam', isThermal, paletteKey, detections);

  const accent = isThermal ? paletteDef.accent : '#4ade80';

  // Interaction handlers
  const handleWheel = (e) => {
    e.preventDefault();
    setZoom(z => Math.max(1, Math.min(z - e.deltaY * 0.01, 10)));
  };

  const handleMouseDown = (e) => {
    if (zoom > 1) {
      isDragging.current = true;
      lastMouse.current = { x: e.clientX, y: e.clientY };
    }
  };

  const handleMouseMove = (e) => {
    if (isDragging.current) {
      const dx = e.clientX - lastMouse.current.x;
      const dy = e.clientY - lastMouse.current.y;
      setPan(p => ({ x: p.x + dx, y: p.y + dy }));
      lastMouse.current = { x: e.clientX, y: e.clientY };
    }
  };

  const handleMouseUp = () => { isDragging.current = false; };
  const handleDoubleClick = () => setIsFullscreen(!isFullscreen);

  // Reset pan if zoomed out
  useEffect(() => { if (zoom === 1) setPan({ x: 0, y: 0 }); }, [zoom]);

  const wrapperClass = isFullscreen
    ? "fixed inset-0 z-50 bg-black"
    : "relative overflow-hidden bg-bg2 border-2 border-transparent transition-colors h-full w-full";

  return (
    <div
      ref={containerRef}
      className={wrapperClass}
      style={!isFullscreen ? { borderColor: `${accent}35` } : {}}
      onWheel={handleWheel}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onDoubleClick={handleDoubleClick}
    >
      {/* Type badge — top left */}
      <div className="absolute top-2 left-2 z-10 flex items-center gap-1.5">
        <span
          className="font-mono text-[10px] font-bold tracking-widest px-2 py-0.5 rounded-sm border backdrop-blur-sm shadow-md"
          style={{ background:'rgba(0,0,0,0.58)', color:'#fff', borderColor:`${accent}65` }}
        >
          {isThermal ? `THERMAL · ${paletteDef.label}` : 'RGB · 4K'}
        </span>
        {isThermal && <span className="w-1.5 h-1.5 rounded-full animate-pulse shadow-[0_0_8px_currentColor]" style={{ color:accent, background:accent }}/>}
        {isThermal && detections.length > 0 && (
          <span
            className="font-mono text-[9px] font-bold px-1.5 py-0.5 rounded-sm animate-pulse"
            style={{ background:'rgba(255,0,0,0.7)', color:'#fff' }}
          >
            {detections.length} DET
          </span>
        )}
      </div>

      {/* Constraints / UI hints */}
      {isFullscreen && (
        <div className="absolute top-2 left-1/2 -translate-x-1/2 font-mono text-[10px] bg-black/60 px-2 py-1 rounded text-white z-10">
          DOUBLE-CLICK TO EXIT FULLSCREEN
        </div>
      )}

      {/* Controls — top right */}
      <div className="absolute top-2 right-2 z-10 flex items-center gap-1.5">
        {videoMode === 'demo' && (
          <span className="font-mono text-[9px] px-1.5 py-0.5 rounded border backdrop-blur-sm shadow-md"
            style={{ background:'rgba(0,0,0,0.52)', color:'rgba(255,255,140,0.85)', borderColor:'rgba(255,255,80,0.3)' }}>
            SIMULATION
          </span>
        )}
        {videoMode === 'webcam' && (
          <span className="font-mono text-[9px] px-1.5 py-0.5 rounded border backdrop-blur-sm shadow-md"
            style={{ background:'rgba(0,0,0,0.52)', color:'#4ade80', borderColor:'rgba(74,222,128,0.3)' }}>
            WEBCAM
          </span>
        )}
        {isThermal && (
          <select
            value={paletteIdx}
            onChange={(e) => setPaletteIdx(parseInt(e.target.value))}
            title="Select Thermal Palette"
            className="font-mono text-[9px] px-1.5 py-0.5 rounded border outline-none cursor-pointer transition-all backdrop-blur-sm shadow-md"
            style={{ background:'rgba(0,0,0,0.65)', color:'#fff', borderColor:`${accent}70` }}
          >
            {PALETTE_KEYS.map((key, idx) => (
              <option key={key} value={idx} style={{ background: '#111' }}>
                {PALETTES[key].name}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Sensor spec — bottom left */}
      <div className="absolute bottom-2 left-2 font-mono text-[9px] z-10 shadow-md"
        style={{ color:'rgba(255,255,255,0.7)', textShadow:'0 1px 4px rgba(0,0,0,0.9)' }}>
        {isThermal ? '512×384 · 8.5µm · 25fps' : '3840×2160 · H.265 · 30fps'}
        {zoom !== 1 && ` · ZOOM ${zoom.toFixed(1)}x`}
      </div>

      <div className="w-full h-full overflow-hidden" style={{ cursor: zoom > 1 ? 'grab' : 'default' }}>
        <canvas
          ref={canvasRef}
          className="block w-full h-full"
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
            transformOrigin: 'center center',
            transition: isDragging.current ? 'none' : 'transform 0.1s ease-out'
          }}
        />
      </div>
    </div>
  );
});

export default VideoPanel;

