import os, json, glob, argparse, io, math
from datetime import datetime, timezone
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
import numpy as np
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, Image as RLImage, PageBreak
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

# ── Brand colours ────────────────────────────────────────────────────────────
C_PALE   = colors.HexColor("#EEF5FF")   # Pale Blue (Dashboard BG)
C_MID    = colors.HexColor("#4B6FBF")   # Medium Blue (Dashboard Accent)
C_DARK   = colors.HexColor("#081F60")   # Dark Navy (Dashboard Header/Logo BG)
C_WHITE  = colors.white
C_GRAY   = colors.HexColor("#64748B")   # Slate 500
C_LGRAY  = colors.HexColor("#E2E8F0")   # Slate 200
C_SUCCESS= colors.HexColor("#10B981")   # Emerald 500
C_WARN   = colors.HexColor("#F59E0B")   # Amber 500
C_INFO   = colors.HexColor("#3B82F6")   # Blue 500
C_ACCENT = colors.HexColor("#4B6FBF")   # Using MID as accent

def find_logo(names):
    # Try multiple possible locations and multiple filenames
    bases = [
        os.path.dirname(__file__),
        os.getcwd(),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")),
        os.path.abspath(os.path.join(os.getcwd(), "thermal_project")),
    ]
    if isinstance(names, str): names = [names]
    
    for b in bases:
        for name in names:
            # Check direct
            p = os.path.join(b, name)
            if os.path.exists(p): return p
            # Check in thermal_project folder
            p = os.path.join(b, "thermal_project", name)
            if os.path.exists(p): return p
    return None

# Use the removebg PNGs as requested, fallback to jpeg
LOGO_VERTICAL = find_logo(["Vertical_Logo_white-removebg-preview.png", "Vertical_Logo_white.jpeg"])
LOGO_SQUARE   = find_logo(["Square_logo_white-removebg-preview.png", "Square_logo_white.jpeg"])

TARGET_COLORS = {
    "human"  : colors.HexColor("#10B981"),
    "animal" : colors.HexColor("#F59E0B"),
    "vehicle": colors.HexColor("#3B82F6"),
}

TARGET_ICONS = {"human": "H", "animal": "A", "vehicle": "V"}

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm

CAPTURES_DIR = "captures"
OUT_FILE     = "C12_Thermal_Detection_Report.pdf"

# ── Style helpers ─────────────────────────────────────────────────────────────
def S(name, **kw):
    defaults = dict(fontName="Helvetica", fontSize=10,
                    textColor=C_DARK, leading=14, spaceAfter=0)
    defaults.update(kw)
    return ParagraphStyle(name, **defaults)

STYLES = {
    "title"      : S("title",   fontName="Helvetica-Bold", fontSize=22,
                     textColor=C_WHITE,  leading=28, alignment=TA_LEFT),
    "subtitle"   : S("sub",     fontName="Helvetica",      fontSize=11,
                     textColor=C_PALE,   leading=15, alignment=TA_LEFT),
    "section"    : S("section", fontName="Helvetica-Bold", fontSize=13,
                     textColor=C_DARK,   leading=18, spaceBefore=8),
    "label"      : S("label",   fontName="Helvetica-Bold", fontSize=8,
                     textColor=C_GRAY,   leading=11, spaceAfter=1),
    "value"      : S("value",   fontName="Helvetica",      fontSize=10,
                     textColor=C_DARK,   leading=14),
    "value_bold" : S("vbold",   fontName="Helvetica-Bold", fontSize=10,
                     textColor=C_DARK,   leading=14),
    "caption"    : S("caption", fontName="Helvetica",      fontSize=8,
                     textColor=C_GRAY,   leading=11, alignment=TA_CENTER),
    "small"      : S("small",   fontName="Helvetica",      fontSize=8,
                     textColor=C_GRAY,   leading=11),
    "tag_human"  : S("th", fontName="Helvetica-Bold", fontSize=9,
                     textColor=C_WHITE, backColor=TARGET_COLORS["human"],
                     borderPadding=(2,6,2,6), leading=13),
    "body"       : S("body",    fontName="Helvetica",      fontSize=9,
                     textColor=C_DARK,   leading=13),
    "map_link"   : S("maplnk",  fontName="Helvetica-Bold", fontSize=9,
                     textColor=C_MID,    leading=13),
}

# ── Canvas callbacks ──────────────────────────────────────────────────────────
class ReportCanvas:
    """Adds header bar and footer to every page."""
    def __init__(self, mission_id, total_pages_ref):
        self.mission_id = mission_id
        self.tpr        = total_pages_ref

    def on_page(self, canv, doc):
        canv.saveState()
        w = PAGE_W

        # ── top bar ──────────────────────────────────────────────────────────
        canv.setFillColor(C_DARK)
        canv.rect(0, PAGE_H - 15*mm, w, 15*mm, fill=1, stroke=0)

        canv.setFillColor(C_MID)
        canv.rect(0, PAGE_H - 17*mm, w, 2*mm, fill=1, stroke=0)

        # Logo in Header (using Square Logo)
        if LOGO_SQUARE:
            try:
                # Slightly larger and vertically centered in the 15mm bar
                canv.drawImage(LOGO_SQUARE, MARGIN - 2*mm, PAGE_H - 13.5*mm, width=12*mm, height=12*mm, preserveAspectRatio=True)
            except Exception as e:
                print(f"[ERROR] Header Logo failed: {e}")

        canv.setFont("Helvetica-Bold", 10)
        canv.setFillColor(C_WHITE)
        header_text_x = MARGIN + 14*mm if LOGO_SQUARE else MARGIN
        canv.drawString(header_text_x, PAGE_H - 9*mm, "SKYDROID C12  |  THERMAL DETECTION REPORT")

        canv.setFont("Helvetica", 8)
        canv.setFillColor(C_PALE)
        canv.drawRightString(w - MARGIN, PAGE_H - 9*mm,
            f"Mission: {self.mission_id}")

        # ── footer ───────────────────────────────────────────────────────────
        canv.setFillColor(C_DARK)
        canv.rect(0, 0, w, 10*mm, fill=1, stroke=0)

        canv.setFillColor(C_MID)
        canv.rect(0, 10*mm, w, 0.5*mm, fill=1, stroke=0)

        canv.setFont("Helvetica", 7.5)
        canv.setFillColor(C_PALE)
        canv.drawString(MARGIN, 3.5*mm,
            "Generated by TIOS Thermal Detection System  |  Confidential")
        canv.drawRightString(w - MARGIN, 3.5*mm,
            f"Page {doc.page}")

        # ── watermark ────────────────────────────────────────────────────────
        canv.saveState()
        canv.setFont("Helvetica-Bold", 60)
        canv.setFillColorRGB(0.5, 0.5, 0.5, alpha=0.03)
        canv.translate(PAGE_W/2, PAGE_H/2)
        canv.rotate(45)
        canv.drawCentredString(0, 0, "AEROLUNA")
        canv.restoreState()

        canv.restoreState()


# ── Data loader ───────────────────────────────────────────────────────────────
def load_captures(captures_dir):
    files = sorted(glob.glob(os.path.join(captures_dir, "*_meta.json")))
    caps  = []
    for f in files:
        with open(f) as fh:
            m = json.load(fh)
        m["_dir"] = captures_dir
        caps.append(m)
    return caps


# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt_ts(ts_str):
    try:
        dt = datetime.fromisoformat(ts_str)
        return dt.strftime("%d %b %Y  %H:%M:%S UTC")
    except Exception:
        return ts_str

def conf_bar_cell(conf):
    pct    = round(conf * 100)
    filled = round(pct / 10)
    bar    = "█" * filled + "░" * (10 - filled)
    return f"{bar}  {pct}%"

def target_badge(label):
    col  = TARGET_COLORS.get(label, C_GRAY)
    icon = TARGET_ICONS.get(label, "?")
    return label.upper()

def image_path(meta, kind):
    key  = f"{kind}_file"
    name = meta.get(key, "")
    path = os.path.join(meta["_dir"], name)
    return path if os.path.exists(path) else None

def stat_row(label, value, unit=""):
    return [
        Paragraph(label, STYLES["label"]),
        Paragraph(f"{value} {unit}".strip(), STYLES["value_bold"]),
    ]


# ── Cover page ────────────────────────────────────────────────────────────────
def cover_page(canv, caps, mission_id):
    w, h = PAGE_W, PAGE_H

    # Deep Midnight Gradient Background
    canv.setFillColor(C_DARK)
    canv.rect(0, 0, w, h, fill=1, stroke=0)
    
    # Tech Grid - more subtle and refined
    canv.setStrokeColorRGB(1, 1, 1, alpha=0.03)
    canv.setLineWidth(0.15)
    grid_size = 8*mm
    for x in range(0, int(w), int(grid_size)):
        canv.line(x, 0, x, h)
    for y in range(0, int(h), int(grid_size)):
        canv.line(0, y, w, y)

    # Glowing Circles / Depth effect
    canv.setFillColorRGB(1, 1, 1, alpha=0.02)
    canv.circle(w * 0.5, h * 0.8, 120*mm, fill=1, stroke=0)
    canv.circle(w * 0.1, h * 0.2, 80*mm, fill=1, stroke=0)

    # Logo on Cover (Vertical) - centered and large
    if LOGO_VERTICAL:
        try:
            logo_w = 70*mm
            canv.drawImage(LOGO_VERTICAL, (w - logo_w) / 2, h - 80*mm, width=logo_w, height=60*mm, preserveAspectRatio=True)
        except Exception as e:
            print(f"[ERROR] Cover Logo failed: {e}")

    # Main Title Area - Centered
    canv.setFont("Helvetica-Bold", 42)
    canv.setFillColor(C_WHITE)
    canv.drawCentredString(w/2, h * 0.58, "THERMAL DETECTION")

    canv.setFont("Helvetica-Bold", 32)
    canv.setFillColor(C_ACCENT)
    canv.drawCentredString(w/2, h * 0.52, "MISSION REPORT")

    # Divider
    canv.setStrokeColor(C_MID)
    canv.setLineWidth(1)
    canv.line(w/2 - 40*mm, h * 0.49, w/2 + 40*mm, h * 0.49)

    # Subtitle / Features
    canv.setFont("Helvetica-Bold", 12)
    canv.setFillColor(C_WHITE)
    canv.drawCentredString(w/2, h * 0.45,
        "AUTOMATED HOTSPOT DETECTION  •  AI CLASSIFICATION  •  GEO-INTELLIGENCE")
        
    # Mission Info Box - Centered and Styled
    box_w = 120*mm
    box_h = 45*mm
    box_x = (w - box_w) / 2
    box_y = h * 0.18
    
    # Glassy Box
    canv.setFillColorRGB(1, 1, 1, alpha=0.05)
    canv.roundRect(box_x, box_y, box_w, box_h, 6, fill=1, stroke=0)
    canv.setStrokeColorRGB(1, 1, 1, alpha=0.1)
    canv.roundRect(box_x, box_y, box_w, box_h, 6, fill=0, stroke=1)

    # Mission Info Text
    tx = box_x + 15*mm
    ty = box_y + box_h - 12*mm
    
    canv.setFont("Helvetica-Bold", 10)
    canv.setFillColor(C_ACCENT)
    canv.drawString(tx, ty, "MISSION ID")
    canv.setFont("Helvetica", 11)
    canv.setFillColor(C_WHITE)
    canv.drawString(tx + 45*mm, ty, mission_id)
    
    ty -= 8*mm
    if caps:
        ts_first = fmt_ts(caps[0]["timestamp_utc"])
        ts_last  = fmt_ts(caps[-1]["timestamp_utc"])
        
        canv.setFont("Helvetica-Bold", 10)
        canv.setFillColor(C_ACCENT)
        canv.drawString(tx, ty, "START TIME")
        canv.setFont("Helvetica", 11)
        canv.setFillColor(C_WHITE)
        canv.drawString(tx + 45*mm, ty, ts_first)
        
        ty -= 8*mm
        canv.setFont("Helvetica-Bold", 10)
        canv.setFillColor(C_ACCENT)
        canv.drawString(tx, ty, "END TIME")
        canv.setFont("Helvetica", 11)
        canv.setFillColor(C_WHITE)
        canv.drawString(tx + 45*mm, ty, ts_last)
        
        ty -= 8*mm
        canv.setFont("Helvetica-Bold", 10)
        canv.setFillColor(C_ACCENT)
        canv.drawString(tx, ty, "TOTAL DETECTIONS")
        canv.setFont("Helvetica", 11)
        canv.setFillColor(C_WHITE)
        canv.drawString(tx + 45*mm, ty, str(len(caps)))

    # Footer stripe with sensor specs
    canv.setFillColor(C_DARK)
    canv.rect(0, 10*mm, w, 15*mm, fill=1, stroke=0)
    canv.setFillColor(C_MID)
    canv.rect(0, 25*mm, w, 0.5*mm, fill=1, stroke=0)
    
    specs = ["FLIR LWIR 384×288", "2K RGB OPTICAL", "GPS/GLONASS/RTK", "AI INFERENCE ENGINE"]
    canv.setFont("Helvetica-Bold", 8)
    canv.setFillColor(C_GRAY)
    canv.drawCentredString(w/2, 16*mm, "  |  ".join(specs))

    canv.showPage()



# ── GPS Map Plot ─────────────────────────────────────────────────────────────
def generate_gps_map(caps, width_px=900, height_px=540) -> io.BytesIO:
    """
    Renders a styled GPS scatter-map of all detections.
    Returns a BytesIO PNG buffer ready for embedding in the PDF.
    """
    gps_caps = [c for c in caps if c.get("gps") and
                c["gps"].get("lat") and c["gps"].get("lon")]
    if not gps_caps:
        return None

    lats   = [c["gps"]["lat"] for c in gps_caps]
    lons   = [c["gps"]["lon"] for c in gps_caps]
    alts   = [c["gps"].get("rel_alt_m", 0) for c in gps_caps]
    labels = [c.get("target_class", "unknown") for c in gps_caps]
    confs  = [c.get("confidence", 0.5) for c in gps_caps]
    times  = list(range(len(gps_caps)))

    # ── color map per label ───────────────────────────────────────────────────
    MCOLORS = {
        "human"  : "#1D9E75",
        "animal" : "#EF9F27",
        "vehicle": "#378ADD",
        "unknown": "#7A8DB3",
    }

    BG      = "#081F60"
    GRID_C  = "#1a3580"
    TEXT_C  = "#EEF5FF"
    ACC_C   = "#4B6FBF"

    dpi = 100
    fig, axes = plt.subplots(
        1, 2,
        figsize=(width_px/dpi, height_px/dpi),
        dpi=dpi,
        gridspec_kw={"width_ratios": [2.2, 1]}
    )
    fig.patch.set_facecolor(BG)

    # ════════════════════════════════════════════════════════
    # LEFT PANEL — Main GPS scatter map
    # ════════════════════════════════════════════════════════
    ax = axes[0]
    ax.set_facecolor("#0b2470")

    # Padding around points
    lat_pad = max((max(lats) - min(lats)) * 0.25, 0.0002)
    lon_pad = max((max(lons) - min(lons)) * 0.25, 0.0002)
    ax.set_xlim(min(lons) - lon_pad, max(lons) + lon_pad)
    ax.set_ylim(min(lats) - lat_pad, max(lats) + lat_pad)

    # Grid
    ax.grid(True, color=GRID_C, linewidth=0.6, linestyle="--", alpha=0.7)
    ax.set_axisbelow(True)

    # Flight path line
    ax.plot(lons, lats,
            color=ACC_C, linewidth=1.2, linestyle="--",
            alpha=0.55, zorder=2)

    # Direction arrows along path
    for i in range(len(lons) - 1):
        mx = (lons[i] + lons[i+1]) / 2
        my = (lats[i] + lats[i+1]) / 2
        dx = lons[i+1] - lons[i]
        dy = lats[i+1] - lats[i]
        ax.annotate("", xy=(mx+dx*0.001, my+dy*0.001), xytext=(mx, my),
                    arrowprops=dict(arrowstyle="->", color=ACC_C,
                                   lw=1.0, alpha=0.55))

    # START marker
    ax.plot(lons[0], lats[0], marker="s", markersize=9,
            color="#4B6FBF", zorder=6,
            markeredgecolor=TEXT_C, markeredgewidth=0.8)
    ax.text(lons[0], lats[0] + lat_pad*0.12, "START",
            color=TEXT_C, fontsize=6.5, ha="center", fontweight="bold",
            path_effects=[pe.withStroke(linewidth=2, foreground=BG)])

    # END marker
    ax.plot(lons[-1], lats[-1], marker="D", markersize=9,
            color="#EF9F27", zorder=6,
            markeredgecolor=TEXT_C, markeredgewidth=0.8)
    ax.text(lons[-1], lats[-1] - lat_pad*0.18, "END",
            color=TEXT_C, fontsize=6.5, ha="center", fontweight="bold",
            path_effects=[pe.withStroke(linewidth=2, foreground=BG)])

    # Detection scatter points
    for i, (lon, lat, lbl, conf, alt) in enumerate(
            zip(lons, lats, labels, confs, alts)):
        col   = MCOLORS.get(lbl, MCOLORS["unknown"])
        size  = 80 + conf * 120          # bigger = more confident
        alpha = 0.55 + conf * 0.35

        # Glow ring
        ax.scatter(lon, lat, s=size*2.8, color=col,
                   alpha=0.18, zorder=3, linewidths=0)
        # Main dot
        ax.scatter(lon, lat, s=size, color=col,
                   alpha=alpha, zorder=4,
                   edgecolors=TEXT_C, linewidths=0.6)

        # Event number label
        ax.text(lon, lat, str(i+1),
                color=TEXT_C, fontsize=6, ha="center", va="center",
                fontweight="bold", zorder=5,
                path_effects=[pe.withStroke(linewidth=1.5, foreground=col)])

        # Alt label above point
        ax.text(lon, lat + lat_pad * 0.14,
                f"{alt:.0f}m",
                color=TEXT_C, fontsize=5.5, ha="center",
                alpha=0.8, zorder=5,
                path_effects=[pe.withStroke(linewidth=1.5, foreground=BG)])

    # Axis labels & ticks
    ax.set_xlabel("Longitude", color=TEXT_C, fontsize=8, labelpad=4)
    ax.set_ylabel("Latitude",  color=TEXT_C, fontsize=8, labelpad=4)
    ax.tick_params(colors=TEXT_C, labelsize=6.5)
    for spine in ax.spines.values():
        spine.set_edgecolor(ACC_C)
        spine.set_linewidth(0.6)

    # Legend
    patches = [
        mpatches.Patch(color=MCOLORS["human"],   label="Human"),
        mpatches.Patch(color=MCOLORS["animal"],  label="Animal"),
        mpatches.Patch(color=MCOLORS["vehicle"], label="Vehicle"),
    ]
    leg = ax.legend(handles=patches, loc="lower right",
                    facecolor="#0f2d80", edgecolor=ACC_C,
                    labelcolor=TEXT_C, fontsize=7,
                    framealpha=0.85, borderpad=0.6)

    ax.set_title("Detection GPS Map  —  Flight Path & Events",
                 color=TEXT_C, fontsize=9, fontweight="bold", pad=8)

    # ════════════════════════════════════════════════════════
    # RIGHT PANEL — Altitude profile + confidence bar chart
    # ════════════════════════════════════════════════════════
    ax2 = axes[1]
    ax2.set_facecolor("#0b2470")

    # Altitude profile (area fill)
    t_axis = list(range(len(gps_caps)))
    ax2.fill_between(t_axis, alts, alpha=0.25, color=ACC_C, zorder=1)
    ax2.plot(t_axis, alts, color=ACC_C, linewidth=1.5,
             marker="o", markersize=4,
             markerfacecolor=TEXT_C, markeredgecolor=ACC_C,
             zorder=3)

    # Colour each point by target class
    for i, (alt, lbl) in enumerate(zip(alts, labels)):
        ax2.plot(i, alt, "o", markersize=6,
                 color=MCOLORS.get(lbl, MCOLORS["unknown"]),
                 zorder=4, markeredgecolor=TEXT_C, markeredgewidth=0.5)

    ax2.set_xlabel("Event #", color=TEXT_C, fontsize=7, labelpad=3)
    ax2.set_ylabel("Altitude AGL (m)", color=TEXT_C, fontsize=7, labelpad=3)
    ax2.set_xticks(t_axis)
    ax2.set_xticklabels([str(i+1) for i in t_axis])
    ax2.tick_params(colors=TEXT_C, labelsize=6)
    ax2.grid(True, color=GRID_C, linewidth=0.5, linestyle=":", alpha=0.6)
    ax2.set_axisbelow(True)
    for spine in ax2.spines.values():
        spine.set_edgecolor(ACC_C)
        spine.set_linewidth(0.5)
    ax2.set_title("Altitude Profile", color=TEXT_C,
                  fontsize=8, fontweight="bold", pad=6)

    # Confidence mini-bars below altitude panel
    divider_y = min(alts) - (max(alts) - min(alts)) * 0.55
    ax2.axhline(divider_y, color=ACC_C, linewidth=0.4, linestyle="--", alpha=0.4)

    fig.tight_layout(pad=1.2, w_pad=1.4)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi,
                facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


# ── Confidence Timeline Chart ─────────────────────────────────────────────────
def generate_confidence_chart(caps, width_px=900, height_px=260) -> io.BytesIO:
    """
    Horizontal bar chart: each detection event with confidence %,
    coloured by target class. Includes time axis.
    """
    BG    = "#081F60"
    ACC_C = "#4B6FBF"
    TEXT_C= "#EEF5FF"
    GRID_C= "#1a3580"
    MCOLORS = {
        "human"  : "#1D9E75",
        "animal" : "#EF9F27",
        "vehicle": "#378ADD",
        "unknown": "#7A8DB3",
    }

    dpi = 100
    fig, ax = plt.subplots(figsize=(width_px/dpi, height_px/dpi), dpi=dpi)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor("#0b2470")

    n = len(caps)
    y_pos  = list(range(n))
    confs  = [c.get("confidence", 0) * 100 for c in caps]
    labels = [c.get("target_class", "unknown") for c in caps]
    bar_colors = [MCOLORS.get(l, MCOLORS["unknown"]) for l in labels]

    # Background full bar (100%)
    ax.barh(y_pos, [100]*n, height=0.55,
            color="#1a3580", alpha=0.5, zorder=1)

    # Confidence bars
    bars = ax.barh(y_pos, confs, height=0.55,
                   color=bar_colors, alpha=0.85,
                   zorder=2)

    # Value labels at end of bars
    for i, (bar, conf, lbl) in enumerate(zip(bars, confs, labels)):
        ax.text(min(conf + 1.5, 97), i,
                f"{conf:.0f}%",
                va="center", ha="left",
                color=TEXT_C, fontsize=7, fontweight="bold")
        ax.text(-1, i,
                f"#{i+1} {lbl.upper()}",
                va="center", ha="right",
                color=TEXT_C, fontsize=6.5, alpha=0.85)

    ax.set_xlim(-18, 108)
    ax.set_ylim(-0.6, n - 0.4)
    ax.set_xlabel("Confidence (%)", color=TEXT_C, fontsize=7)
    ax.set_yticks([])
    ax.tick_params(axis="x", colors=TEXT_C, labelsize=6.5)
    ax.grid(True, axis="x", color=GRID_C, linewidth=0.5,
            linestyle=":", alpha=0.7)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_edgecolor(ACC_C)
        spine.set_linewidth(0.5)
    ax.set_title("Detection Confidence by Event",
                 color=TEXT_C, fontsize=8, fontweight="bold", pad=6)

    # Threshold line at 50%
    ax.axvline(50, color="#EF9F27", linewidth=0.8,
               linestyle="--", alpha=0.6, zorder=3)
    ax.text(51, n - 0.3, "50% threshold",
            color="#EF9F27", fontsize=6, alpha=0.7)

    fig.tight_layout(pad=0.8)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi,
                facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def summary_section(story, caps):
    # GPS bounding box
    gps_entries = [c["gps"] for c in caps if c.get("gps")]
    if gps_entries:
        lats = [g["lat"] for g in gps_entries]
        lons = [g["lon"] for g in gps_entries]
        alts = [g.get("rel_alt_m", 0) for g in gps_entries]

        story.append(Paragraph("Area Coverage", STYLES["section"]))
        story.append(HRFlowable(width="100%", thickness=0.5,
                                 color=C_MID, spaceAfter=8))

        gps_rows = [
            ["Parameter", "Value", "Parameter", "Value"],
            ["Min Latitude",  f"{min(lats):.6f}°",
             "Max Latitude",  f"{max(lats):.6f}°"],
            ["Min Longitude", f"{min(lons):.6f}°",
             "Max Longitude", f"{max(lons):.6f}°"],
            ["Min Altitude",  f"{min(alts):.1f} m",
             "Max Altitude",  f"{max(alts):.1f} m"],
            ["Avg Altitude",  f"{sum(alts)/len(alts):.1f} m",
             "Total Events",  str(len(caps))],
        ]
        gt = Table(gps_rows, colWidths=[(PAGE_W-2*MARGIN)/4]*4)
        gt.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0), C_DARK),
            ("TEXTCOLOR",     (0,0), (-1,0), C_WHITE),
            ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",      (0,0), (-1,-1), 9),
            ("ALIGN",         (1,0), (-1,-1), "CENTER"),
            ("ALIGN",         (0,0), (0,-1),  "LEFT"),
            ("LEFTPADDING",   (0,0), (0,-1),  8),
            ("LEFTPADDING",   (2,0), (2,-1),  8),
            ("TOPPADDING",    (0,0), (-1,-1), 8),
            ("BOTTOMPADDING", (0,0), (-1,-1), 8),
            ("BACKGROUND",    (0,1), (-1,1), C_WHITE),
            ("BACKGROUND",    (0,2), (-1,2), C_PALE),
            ("BACKGROUND",    (0,3), (-1,3), C_WHITE),
            ("BACKGROUND",    (0,4), (-1,4), C_PALE),
            ("GRID",          (0,0), (-1,-1), 0.5, C_LGRAY),
            ("LINEBELOW",     (0,0), (-1,0), 2, C_MID),
            ("FONTNAME",      (0,1), (0,-1), "Helvetica-Bold"),
            ("FONTNAME",      (2,1), (2,-1), "Helvetica-Bold"),
            ("TEXTCOLOR",     (0,1), (0,-1), C_GRAY),
            ("TEXTCOLOR",     (2,1), (2,-1), C_GRAY),
        ]))
        story.append(gt)
        story.append(Spacer(1, 12))

    # ── GPS Map ───────────────────────────────────────────────────────────────
    story.append(Paragraph("GPS Detection Map", STYLES["section"]))
    story.append(HRFlowable(width="100%", thickness=0.5,
                             color=C_MID, spaceAfter=8))

    map_buf = generate_gps_map(caps)
    if map_buf:
        usable_w = PAGE_W - 2 * MARGIN
        map_img  = RLImage(map_buf,
                           width=usable_w,
                           height=usable_w * (540/900))
        # Framed container
        map_table = Table([[map_img]],
                          colWidths=[usable_w])
        map_table.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), C_DARK),
            ("LEFTPADDING",   (0,0), (-1,-1), 0),
            ("RIGHTPADDING",  (0,0), (-1,-1), 0),
            ("TOPPADDING",    (0,0), (-1,-1), 0),
            ("BOTTOMPADDING", (0,0), (-1,-1), 0),
            ("BOX",           (0,0), (-1,-1), 0.8, C_MID),
        ]))
        story.append(map_table)
        story.append(Paragraph(
            "<b>How to Interpret This Map:</b> The map displays the drone's flight path as a dashed line. "
            "Each numbered point corresponds to an isolated thermal detection event. The expanded size of the dot "
            "reflects the AI's confidence in the detection. Green indicates Humans, Amber indicates Animals, "
            "and Blue indicates Vehicles. Use this map to quickly locate areas of high thermal activity and trace the patrol route.",
            STYLES["body"]))
        story.append(Spacer(1, 10))

    story.append(Spacer(1, 6))

    story.append(PageBreak())


# ── Single capture card ───────────────────────────────────────────────────────
def capture_card(story, meta, idx):
    label   = meta.get("target_class", "unknown")
    conf    = meta.get("confidence", 0)
    gps     = meta.get("gps") or {}
    bbox    = meta.get("bbox_xywh", [0,0,0,0])
    tc      = TARGET_COLORS.get(label, C_GRAY)
    usable_w = PAGE_W - 2*MARGIN

    # ── card header bar ───────────────────────────────────────────────────────
    time_source = meta.get("time_source", "system")
    ts_label    = "⏱ GPS" if time_source == "gps" else "⚠ SYS"
    
    # Priority: use GPS timestamp if available, otherwise fallback to UTC string
    raw_ts = meta.get("gps_timestamp_utc") or meta.get("timestamp_utc", "")
    ts_text = (
        f'{fmt_ts(raw_ts)} '
        f'<font color="{"#10B981" if time_source == "gps" else "#F59E0B"}">'
        f'[{ts_label}]</font>'
    )

    header_data = [[
        Paragraph(f"EVENT #{idx:02d}", S("dh",
            fontName="Helvetica-Bold", fontSize=11, textColor=C_WHITE)),
        Paragraph(label.upper(), S("dl",
            fontName="Helvetica-Bold", fontSize=11, textColor=tc)),
        Paragraph(ts_text, S("dt",
            fontName="Helvetica", fontSize=10, textColor=C_PALE,
            alignment=TA_RIGHT)),
    ]]
    hw = usable_w / 3
    ht = Table(header_data, colWidths=[hw, hw, hw])
    ht.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_DARK),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING",   (0,0), (0,-1),  15),
        ("ALIGN",         (1,0), (1,-1),  "CENTER"),
        ("ALIGN",         (2,0), (2,-1),  "RIGHT"),
        ("RIGHTPADDING",  (2,0), (2,-1),  15),
        ("LINEBELOW",     (0,0), (-1,0),  2, C_MID),
    ]))
    story.append(KeepTogether([ht]))

    # ── images row ────────────────────────────────────────────────────────────
    img_w   = (usable_w - 6) / 2
    img_h   = img_w * (288/384)

    t_path = image_path(meta, "thermal")
    v_path = image_path(meta, "visible")

    def make_img_cell(path, caption_text):
        if path and os.path.exists(path):
            try:
                img = RLImage(path, width=img_w, height=img_h)
                return [img, Paragraph(caption_text, STYLES["caption"])]
            except Exception:
                pass
        placeholder = Paragraph(f"[{caption_text}]", STYLES["caption"])
        return [Spacer(img_w, img_h), placeholder]

    t_cell = make_img_cell(t_path, "Thermal (IR)  384×288  8–14µm")
    v_cell = make_img_cell(v_path, "Visible Light  2K  100° FOV")

    img_table = Table(
        [[t_cell[0], v_cell[0]],
         [t_cell[1], v_cell[1]]],
        colWidths=[img_w, img_w],
        rowHeights=[img_h, 14]
    )
    img_table.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_DARK),
        ("ALIGN",         (0,0), (-1,-1), "CENTER"),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("BOTTOMPADDING", (0,1), (-1,1),  6),
        ("TOPPADDING",    (0,1), (-1,1),  4),
        ("COLPADDING",    (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
        ("RIGHTPADDING",  (0,0), (-1,-1), 4),
        ("BOX",           (0,0), (-1,-1), 0.5, C_DARK),
    ]))
    story.append(img_table)
    story.append(Spacer(1, 4))

    # ── info panels ───────────────────────────────────────────────────────────
    x, y, bw_p, bh_p = bbox

    # Confidence visual bar
    conf_pct = round(conf * 100)
    filled   = round(conf_pct / 10)
    bar      = "I" * filled + "." * (10 - filled)

    detection_data = [
        [Paragraph("DETECTION DETAILS", S("ph", fontName="Helvetica-Bold",
                   fontSize=8, textColor=C_WHITE)), ""],
        [Paragraph("Class",        STYLES["label"]),
         Paragraph(label.upper(),  S("cv", fontName="Helvetica-Bold",
                   fontSize=10, textColor=tc))],
        [Paragraph("Confidence",   STYLES["label"]),
         Paragraph(f"{conf_pct}%", S("cv2", fontName="Helvetica-Bold",
                   fontSize=10, textColor=C_DARK))],
        [Paragraph("Bounding Box", STYLES["label"]),
         Paragraph(f"x={x} y={y}  w={bw_p} h={bh_p} px",
                   STYLES["value"])],
        [Paragraph("Blob Area",    STYLES["label"]),
         Paragraph(f"{meta.get('blob_area_px', 0):,} px²", STYLES["value"])],
        [Paragraph("Eccentricity", STYLES["label"]),
         Paragraph(str(meta.get("eccentricity", "—")), STYLES["value"])],
        [Paragraph("Palette",      STYLES["label"]),
         Paragraph(meta.get("palette", "—").title(), STYLES["value"])],
    ]

    # ── Build Google Maps link for this capture ───────────────────────────────
    lat_val = gps.get("lat")
    lon_val = gps.get("lon")
    if lat_val and lon_val:
        maps_url  = f"https://www.google.com/maps?q={lat_val:.6f},{lon_val:.6f}&z=18"
        maps_cell = Paragraph(
            f'<a href="{maps_url}" color="#0EA5E9"><b>&#128205; View on Google Maps →</b></a>',
            STYLES["map_link"]
        )
    else:
        maps_cell = Paragraph("No GPS fix", STYLES["small"])

    gps_data = [
        [Paragraph("GPS &amp; FLIGHT DATA", S("ph2", fontName="Helvetica-Bold",
                   fontSize=8, textColor=C_WHITE)), ""],
        [Paragraph("Latitude",   STYLES["label"]),
         Paragraph(f"{lat_val:.6f}°" if lat_val else "N/A",
                   STYLES["value"])],
        [Paragraph("Longitude",  STYLES["label"]),
         Paragraph(f"{lon_val:.6f}°" if lon_val else "N/A",
                   STYLES["value"])],
        [Paragraph("Altitude (AGL)", STYLES["label"]),
         Paragraph(f"{gps.get('rel_alt_m', 0):.1f} m", STYLES["value"])],
        [Paragraph("Heading",    STYLES["label"]),
         Paragraph(f"{gps.get('hdg_deg', 0):.1f}°",    STYLES["value"])],
        [Paragraph("Satellites", STYLES["label"]),
         Paragraph(str(gps.get("satellites", "—")),     STYLES["value"])],
        [Paragraph("HDOP",       STYLES["label"]),
         Paragraph(str(gps.get("hdop", "—")),           STYLES["value"])],
        [Paragraph("Roll / Pitch", STYLES["label"]),
         Paragraph(f"{gps.get('roll_deg',0):.1f}° / {gps.get('pitch_deg',0):.1f}°",
                   STYLES["value"])],
        [Paragraph("Yaw",        STYLES["label"]),
         Paragraph(f"{gps.get('yaw_deg', 0):.1f}°",    STYLES["value"])],
        # ── Google Maps clickable link row ────────────────────────────────────
        [Paragraph("Location Link", STYLES["label"]),
         maps_cell],
    ]

    panel_w = (usable_w - 4) / 2

    gt = Table(gps_data, colWidths=[panel_w*0.4, panel_w*0.6])
    gt.setStyle(TableStyle([
        # Header row
        ("BACKGROUND",    (0,0), (-1,0), C_DARK),
        ("SPAN",          (0,0), (-1,0)),
        ("TEXTCOLOR",     (0,0), (-1,0), C_WHITE),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("TOPPADDING",    (0,0), (-1,0), 6),
        ("BOTTOMPADDING", (0,0), (-1,0), 6),
        ("LEFTPADDING",   (0,0), (-1,0), 10),
        
        # Data rows alignment
        ("ALIGN",         (1,1), (1,-1), "LEFT"),  # Change to LEFT as requested for better flow
        ("LEFTPADDING",   (1,1), (1,-1), 15),
        
        # Alternate backgrounds
        ("BACKGROUND",    (0,1), (-1,-1), colors.white),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [C_PALE, colors.white]),
        
        # Grid and borders
        ("GRID",          (0,1), (-1,-1), 0.5, C_LGRAY),
        ("LINEBELOW",     (0,0), (-1,0),  2, C_MID),
        ("BOX",           (0,0), (-1,-1), 0.5, C_DARK),
        
        # Text styles
        ("FONTNAME",      (0,1), (0,-1), "Helvetica-Bold"),
        ("TEXTCOLOR",     (0,1), (0,-1), C_GRAY),
        ("FONTSIZE",      (0,1), (-1,-1), 9),
    ]))

    panels = Table([[gt]], colWidths=[panel_w*2],
                   spaceAfter=0)
    panels.setStyle(TableStyle([
        ("VALIGN",       (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING",   (0,0), (-1,-1), 0),
        ("BOTTOMPADDING",(0,0), (-1,-1), 0),
    ]))
    story.append(panels)
    story.append(PageBreak())


# ── Main builder ──────────────────────────────────────────────────────────────
def build_report(captures_dir=CAPTURES_DIR, out_file=OUT_FILE):
    caps = load_captures(captures_dir)
    if not caps:
        print(f"[WARN] No captures found in '{captures_dir}'")
        return

    mission_id = datetime.now(timezone.utc).strftime("MSN-%Y%m%d-%H%M")
    rc         = ReportCanvas(mission_id, [0])

    # ── Draw cover on raw canvas first ───────────────────────────────────────
    from reportlab.pdfgen import canvas as pdfcanvas

    cover_buf = io.BytesIO()
    cv = pdfcanvas.Canvas(cover_buf, pagesize=A4)
    cover_page(cv, caps, mission_id)
    cv.save()
    cover_buf.seek(0)

    # ── Build story pages ─────────────────────────────────────────────────────
    story_buf = io.BytesIO()
    doc = SimpleDocTemplate(
        story_buf,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=16*mm, bottomMargin=14*mm,
    )

    story = []
    summary_section(story, caps)

    story.append(Paragraph("Capture Log", STYLES["section"]))
    story.append(HRFlowable(width="100%", thickness=0.5,
                             color=C_MID, spaceAfter=10))

    for i, meta in enumerate(caps, 1):
        capture_card(story, meta, i)

    doc.build(story,
              onFirstPage=rc.on_page,
              onLaterPages=rc.on_page)
    story_buf.seek(0)

    # ── Merge cover + story ───────────────────────────────────────────────────
    from pypdf import PdfWriter, PdfReader

    writer = PdfWriter()
    cover_reader = PdfReader(cover_buf)
    story_reader = PdfReader(story_buf)

    for page in cover_reader.pages:
        writer.add_page(page)
    for page in story_reader.pages:
        writer.add_page(page)

    writer.add_metadata({
        "/Title":   "C12 Thermal Detection Report",
        "/Author":  "Skydroid C12 Detection System",
        "/Subject": f"Mission {mission_id}",
        "/Creator": "C12 Auto-Capture Pipeline",
    })

    with open(out_file, "wb") as f:
        writer.write(f)

    print(f"[REPORT] Generated: {out_file}  ({len(caps)} captures, "
          f"{len(writer.pages)} pages)")
    return out_file


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--captures", default=CAPTURES_DIR)
    ap.add_argument("--out",      default=OUT_FILE)
    args = ap.parse_args()
    build_report(args.captures, args.out)
