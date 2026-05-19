import re

file_path = r"d:\aeroluna thermal project\tios2\frontend\src\components\video\VideoPanel.jsx"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Replace the label logic in drawDetections
# The old code:
#     // Temperature label
#     const label = `${det.max_temp?.toFixed(1)}°C`;
#     const sevLabel = det.label || det.severity || '';
#     ...
#     // Severity badge
#     if (sevLabel && (det.severity === 'CRITICAL' || det.severity === 'WARNING')) { ... }

new_label_logic = """
    // Object type label
    const label = (det.label || det.severity || 'OBJECT').toUpperCase();
    ctx.font = 'bold 9px "Space Mono",monospace';
    const tw = ctx.measureText(label).width;
    ctx.fillStyle = color;
    ctx.globalAlpha = 0.85;
    ctx.fillRect(dx, dy - 16, tw + 6, 14);
    ctx.globalAlpha = 1;
    ctx.fillStyle = '#000';
    ctx.fillText(label, dx + 3, dy - 5);
"""

# Regex to find the Temperature label to Severity badge block
pattern_labels = re.compile(r"// Temperature label.*?ctx\.restore\(\);", re.DOTALL)
content = pattern_labels.sub(new_label_logic.strip() + "\n\n    ctx.restore();", content)


# 2. Remove drawDetections from the RGB (!isThermal) block in useWebcam
# The old code:
#       if (!isThermal) {
#         // RGB Passthrough
#         ctx.drawImage(img, 0, 0, W, H);
#         drawDetections(ctx, W, H, detectionsRef.current);
#         drawLabel(ctx, '● RGB WEBCAM', 6, H - 6, 9);
#       }

pattern_rgb = re.compile(r"if \(!isThermal\) \{\s*// RGB Passthrough\s*ctx\.drawImage\(img, 0, 0, W, H\);\s*drawDetections\(ctx, W, H, detectionsRef\.current\);\s*drawLabel\(ctx, '● RGB WEBCAM', 6, H - 6, 9\);\s*\}", re.DOTALL)

new_rgb = """if (!isThermal) {
        // RGB Passthrough
        ctx.drawImage(img, 0, 0, W, H);
        // Only drawing detections in thermal view per user request
        drawLabel(ctx, '● RGB WEBCAM', 6, H - 6, 9);
      }"""

content = pattern_rgb.sub(new_rgb, content)

# 3. Just in case they are running useRtspStream, ensure it's also not drawing on RGB
# but useRtspStream had:
#       } else {
#          // Ordinary RGB feed overlay
#          drawLabel(ctx, '● LIVE STREAM', 6, H - 6, 9);
#          drawCrosshair(ctx, W/2, H/2, 'NADIR');
#       }
# which already doesn't call drawDetections!

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Successfully applied thermal-only tracker and species label fixes.")
