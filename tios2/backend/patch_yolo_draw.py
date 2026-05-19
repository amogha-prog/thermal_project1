import re

file_path = r"d:\aeroluna thermal project\tios2\frontend\src\components\video\VideoPanel.jsx"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# I want to rewrite the entire drawDetections function to exactly match the YOLO test script formatting
# GREEN border, GREEN solid background for text, Black text

new_draw_detections = """// ── Detection overlay ────────────────────────────────────────────────────────────
function drawDetections(ctx, W, H, detections) {
  if (!detections || detections.length === 0) return;

  detections.forEach((det) => {
    let dx, dy, dw, dh;
    if (det.is_scaled) {
      dx = det.x; dy = det.y; dw = det.w; dh = det.h;
    } else {
      const scaleX = W / 640;
      const scaleY = H / 480;
      dx = (det.x || 0) * scaleX;
      dy = (det.y || 0) * scaleY;
      dw = (det.w || 0) * scaleX;
      dh = (det.h || 0) * scaleY;
    }

    const color = '#00ff00'; // Pure Green, exactly like the test script!

    ctx.save();
    
    // 1. Draw Bounding Box (simple 2px rectangle)
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.strokeRect(dx, dy, dw, dh);

    // 2. Draw Label
    const conf = det.confidence ? Math.round(det.confidence * 100) : 0;
    const label = `ID:${det.id || 0} ${det.label || 'object'} [${conf}%]`;
    
    ctx.font = 'bold 11px "Segoe UI", sans-serif';
    const tw = ctx.measureText(label).width;
    const th = 14; // text height approx
    
    // Solid green background for text
    ctx.fillStyle = color;
    ctx.fillRect(dx, dy - th - 4, tw + 6, th + 4);
    
    // Black text
    ctx.fillStyle = '#000000';
    ctx.fillText(label, dx + 3, dy - 4);

    ctx.restore();
  });
}"""

pattern = re.compile(r"// ── Detection overlay ────────────────────────────────────────────────────────────\nfunction drawDetections\(ctx, W, H, detections\).*?}\n\n\n\n\n\n// ──", re.DOTALL)

if pattern.search(content):
    content = pattern.sub(new_draw_detections + "\n\n\n\n\n\n// ──", content)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Successfully patched VideoPanel.jsx to use Green YOLO tracker format")
else:
    print("Failed to find drawDetections block")
