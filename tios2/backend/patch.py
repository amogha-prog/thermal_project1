import re

file_path = r"d:\aeroluna thermal project\tios2\frontend\src\components\video\VideoPanel.jsx"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# The useWebcam function starts with "// ── Webcam Stream (for mobile/testing)" or similar
# and ends right before "// ── VideoPanel component"

pattern = re.compile(r"(// ── Webcam Stream.*?)(?=\n// ── VideoPanel component)", re.DOTALL)

new_useWebcam = """// ── Webcam Stream (for mobile/testing TF Object Detection) ──────────────────
function useWebcam(canvasRef, active, isThermal, paletteKey, detections) {
  const rafRef = React.useRef(null);
  
  React.useEffect(() => {
    if (!active || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    
    // Connect to the new Python Flask API for TF Object Detection
    const baseUrl = `http://${window.location.hostname}:5000`;
    const streamUrl = isThermal ? `${baseUrl}/video_feed/thermal` : `${baseUrl}/video_feed/webcam`;
    
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.src = `${streamUrl}?t=${Date.now()}`;
    
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
      if (!W || !H) return;
      
      if (img.complete && img.naturalWidth > 0) {
        ctx.drawImage(img, 0, 0, W, H);
        
        ctx.fillStyle = 'rgba(0,0,0,0.02)';
        for (let sy = 0; sy < H; sy += 2) ctx.fillRect(0, sy, W, 1);
        
        // drawLabel is available in VideoPanel scope
        drawLabel(ctx, isThermal ? '● TF THERMAL' : '● TF WEBCAM', 6, H - 6, 9);
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

if pattern.search(content):
    new_content = pattern.sub(new_useWebcam, content)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Successfully patched VideoPanel.jsx")
else:
    print("Could not find useWebcam function in VideoPanel.jsx")
