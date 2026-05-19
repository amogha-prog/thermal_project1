import re
import sys

file_path = r"d:\aeroluna thermal project\tios2\frontend\src\components\video\VideoPanel.jsx"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# I want to restore the old useWebcam but using Image instead of video element.
# The previous original useWebcam had face detector logic. We can just simplify it:

new_useWebcam = """// ── Webcam Stream (Python MJPEG + UDP Detections) ─────────────────────────────
function useWebcam(canvasRef, active, isThermal, paletteKey, detections) {
  const rafRef = React.useRef(null);
  const paletteRef = React.useRef(PALETTES[paletteKey]?.lut ?? PALETTES.ironbow.lut);
  const detectionsRef = React.useRef(detections);

  React.useEffect(() => {
    paletteRef.current = PALETTES[paletteKey]?.lut ?? PALETTES.ironbow.lut;
    detectionsRef.current = detections;
  }, [paletteKey, detections]);

  React.useEffect(() => {
    if (!active || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d', { willReadFrequently: isThermal });
    
    // Hidden canvas for processing thermal luma
    const hiddenCanvas = document.createElement('canvas');
    const hiddenCtx = hiddenCanvas.getContext('2d', { willReadFrequently: true });

    // Stream raw webcam from Python
    const baseUrl = `http://${window.location.hostname}:5000`;
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.src = `${baseUrl}/video_feed/webcam?t=${Date.now()}`;

    let smoothMin = 80, smoothMax = 200;
    let localActive = true;

    const drawFrame = () => {
      if (!localActive) return;
      rafRef.current = requestAnimationFrame(drawFrame);

      const parent = canvas.parentElement;
      if (parent) {
        const pw = parent.clientWidth;
        const ph = parent.clientHeight;
        if (pw > 0 && ph > 0 && (canvas.width !== pw || canvas.height !== ph)) {
          canvas.width  = pw;
          canvas.height = ph;
        }
      }

      const W = canvas.width, H = canvas.height;
      if (!W || !H || !img.complete || img.naturalWidth === 0) return;

      const lut = paletteRef.current;

      if (!isThermal) {
        // RGB Passthrough
        ctx.drawImage(img, 0, 0, W, H);
        drawDetections(ctx, W, H, detectionsRef.current);
        drawLabel(ctx, '● RGB WEBCAM', 6, H - 6, 9);
      } else {
        // Thermal Processing
        const procW = 320, procH = 240;
        hiddenCanvas.width  = procW;
        hiddenCanvas.height = procH;
        hiddenCtx.drawImage(img, 0, 0, procW, procH);

        const frame = hiddenCtx.getImageData(0, 0, procW, procH);
        const d = frame.data;
        const pixelCount = procW * procH;
        let rawMin = 255, rawMax = 0;
        const span = Math.max(1, smoothMax - smoothMin);

        for (let i = 0; i < pixelCount; i++) {
          const bi = i << 2;
          const l  = (d[bi] * 77 + d[bi+1] * 150 + d[bi+2] * 29) >> 8;
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

        ctx.fillStyle = 'rgba(0,0,0,0.02)';
        for (let sy = 0; sy < H; sy += 2) ctx.fillRect(0, sy, W, 1);

        drawDetections(ctx, W, H, detectionsRef.current);
        drawLabel(ctx, '● THERMAL WEBCAM', 6, H - 6, 9);
      }
    };

    rafRef.current = requestAnimationFrame(drawFrame);

    return () => {
      localActive = false;
      cancelAnimationFrame(rafRef.current);
      img.src = '';
    };
  }, [active, isThermal]);
}
"""

pattern = re.compile(r"(// ── Webcam Stream.*?)(?=\n// ── VideoPanel component)", re.DOTALL)
if pattern.search(content):
    new_content = pattern.sub(new_useWebcam, content)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Successfully patched VideoPanel.jsx to use native Thermal processing with MJPEG!")
else:
    print("Failed to find useWebcam block")
