import os, json, glob, threading
from flask import Flask, render_template_string, jsonify, send_file
from datetime import datetime

# Install: pip install flask
# Run:     python dashboard.py
# Open:    http://localhost:5000  on any browser on the same network

CAPTURES_DIR = "captures"
app          = Flask(__name__)

HTML = """
<!DOCTYPE html><html><head>
<meta charset="utf-8">
<title>C12 Thermal Detection Dashboard</title>
<meta http-equiv="refresh" content="4">
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:system-ui,sans-serif;background:#0f0f0f;color:#e0e0e0;padding:1rem}
  h1{font-size:18px;font-weight:500;margin-bottom:1rem;color:#fff}
  .stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:1.5rem}
  .stat{background:#1a1a1a;border:0.5px solid #2a2a2a;border-radius:10px;padding:12px 16px}
  .stat-label{font-size:11px;color:#888;margin-bottom:4px}
  .stat-val{font-size:22px;font-weight:500;color:#fff}
  .stat-val.human{color:#4ade80}.stat-val.animal{color:#facc15}.stat-val.vehicle{color:#60a5fa}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
  .card{background:#1a1a1a;border:0.5px solid #2a2a2a;border-radius:10px;overflow:hidden}
  .card img{width:100%;display:block;aspect-ratio:4/3;object-fit:cover}
  .card-body{padding:10px 12px}
  .card-label{font-size:13px;font-weight:500;margin-bottom:4px}
  .card-label.human{color:#4ade80}.card-label.animal{color:#facc15}.card-label.vehicle{color:#60a5fa}
  .card-meta{font-size:11px;color:#666;line-height:1.6}
  .conf{display:inline-block;font-size:10px;padding:1px 7px;border-radius:4px;background:#2a2a2a;margin-left:6px}
  .empty{color:#555;font-size:14px;padding:2rem 0}
</style></head><body>
<h1>C12 Thermal Detection — Live Review</h1>
<div class="stats">
  <div class="stat"><div class="stat-label">Total captures</div>
    <div class="stat-val">{{ total }}</div></div>
  <div class="stat"><div class="stat-label">Humans</div>
    <div class="stat-val human">{{ counts.human }}</div></div>
  <div class="stat"><div class="stat-label">Animals</div>
    <div class="stat-val animal">{{ counts.animal }}</div></div>
  <div class="stat"><div class="stat-label">Vehicles</div>
    <div class="stat-val vehicle">{{ counts.vehicle }}</div></div>
</div>
<div class="grid">
{% if captures %}
  {% for c in captures %}
  <div class="card">
    <img src="/img/{{ c.thermal_file }}" alt="thermal">
    <div class="card-body">
      <div class="card-label {{ c.target_class }}">
        {{ c.target_class|upper }}
        <span class="conf">{{ (c.confidence*100)|round|int }}%</span>
      </div>
      <div class="card-meta">
        {{ c.timestamp_utc[:19].replace('T',' ') }} UTC<br>
        {% if c.gps %}
        GPS {{ c.gps.lat|round(5) }}, {{ c.gps.lon|round(5) }}<br>
        Alt {{ c.gps.rel_alt_m|round(1) }} m<br>
        {% endif %}
        Peak intensity: {{ c.peak_intensity }}<br>
        Blob area: {{ c.blob_area_px }} px
      </div>
    </div>
  </div>
  {% endfor %}
{% else %}
  <p class="empty">No captures yet — detections will appear here automatically.</p>
{% endif %}
</div>
</body></html>
"""

def load_captures(limit=50):
    files = sorted(
        glob.glob(os.path.join(CAPTURES_DIR, "*_meta.json")),
        reverse=True)[:limit]
    caps, counts = [], {"human":0,"animal":0,"vehicle":0}
    for f in files:
        with open(f) as fh:
            m = json.load(fh)
        caps.append(m)
        label = m.get("target_class","")
        if label in counts:
            counts[label] += 1
    return caps, counts

@app.route("/")
def index():
    caps, counts = load_captures()
    all_files    = glob.glob(os.path.join(CAPTURES_DIR, "*_meta.json"))
    return render_template_string(HTML,
        captures=caps, counts=counts, total=len(all_files))

@app.route("/img/<filename>")
def serve_image(filename):
    path = os.path.join(CAPTURES_DIR, filename)
    if os.path.exists(path):
        return send_file(path, mimetype="image/jpeg")
    return "Not found", 404

@app.route("/api/captures")
def api_captures():
    caps, counts = load_captures()
    return jsonify({"captures": caps, "counts": counts})

def start_dashboard(port=5000):
    # Call this from main.py to run dashboard in background
    t = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port,
                               debug=False, use_reloader=False),
        daemon=True)
    t.start()
    print(f"[DASHBOARD] Running at http://0.0.0.0:{port}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)