/**
 * TIOS PDF Generator — Premium Inspection Report
 *
 * Beautiful A4 report with:
 *  • Bold cover page with mission summary cards
 *  • Per-capture detail pages with image pairs + full telemetry
 *  • Thermal severity indicator bar
 *  • Clean typography, colored section headers, alternating row tables
 *
 * All rendering happens in-browser. No server involved.
 */

import { jsPDF } from 'jspdf';
import 'jspdf-autotable';

// ── Design System — Brand Palette Only ───────────────────────────────────────
// #EEF5FF  light blue  (backgrounds, card fills, alternating rows)
// #4B6FBF  mid  blue   (accents, section headers, badges)
// #081F60  dark navy   (primary header, dark cards, strong text)
const LIGHT  = [238, 245, 255];   // #EEF5FF
const MID    = [75,  111, 191];   // #4B6FBF
const DARK   = [8,   31,  96 ];   // #081F60
const WHITE  = [255, 255, 255];

const C = {
  // Backgrounds
  pageBg:    LIGHT,
  headerBg:  DARK,
  cardBg:    WHITE,
  sectionBg: LIGHT,
  darkCard:  DARK,

  // Brand
  brand:     MID,
  brandDim:  DARK,
  thermal:   DARK,   // used for "hot" labels — kept navy for mono palette
  thermalLt: MID,
  green:     MID,    // mapped to mid-blue
  warn:      MID,    // mapped to mid-blue
  purple:    DARK,

  // Text
  textDark:  DARK,
  textMid:   MID,
  textLight: MID,
  white:     WHITE,

  // Lines
  border:    LIGHT,
  borderDk:  MID,
};

const PW   = 210;    // A4 width mm
const PH   = 297;    // A4 height mm
const M    = 13;     // margin
const CW   = PW - M * 2;

// ── Offscreen Canvas Helpers ─────────────────────────────────────────────────
function buildMapImage(captures, w, h) {
  const canvas = document.createElement('canvas');
  canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext('2d');
  
  // Clean dark map background
  ctx.fillStyle = '#ebf2fb'; // very light blue
  ctx.fillRect(0, 0, w, h);
  
  // Grid lines
  ctx.strokeStyle = '#d6e4f3';
  ctx.lineWidth = 1;
  for (let x = 0; x < w; x += 15) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke(); }
  for (let y = 0; y < h; y += 15) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke(); }

  // Draw points
  if (captures.length) {
    const lats = captures.map(c => parseFloat(c.location?.lat || 0));
    const lons = captures.map(c => parseFloat(c.location?.lon || 0));
    const minLat = Math.min(...lats), maxLat = Math.max(...lats);
    const minLon = Math.min(...lons), maxLon = Math.max(...lons);
    
    // add padding margin
    const pad = 20;
    const latSpan = (maxLat - minLat) || 0.001;
    const lonSpan = (maxLon - minLon) || 0.001;

    captures.forEach((c) => {
      const lat = parseFloat(c.location?.lat || 0);
      const lon = parseFloat(c.location?.lon || 0);
      const temp = parseFloat(c.telemetry?.maxTemp || 0);
      const fill = temp > 70 ? '#081F60' : temp > 50 ? '#4B6FBF' : '#a0b9e8';

      // Map to padded X/Y
      const px = pad + ((lon - minLon) / lonSpan) * (w - 2 * pad);
      const py = h - (pad + ((lat - minLat) / latSpan) * (h - 2 * pad));

      // Draw pin
      ctx.fillStyle = fill;
      ctx.beginPath(); ctx.arc(px, py, 6, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5; ctx.stroke();
    });
  }

  return canvas.toDataURL('image/png', 0.8);
}

function buildPieChartImage(critical, warning, elevated, normal, w, h) {
  const canvas = document.createElement('canvas');
  canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext('2d');
  
  const total = critical + warning + elevated + normal;
  if (total === 0) return null;

  const cx = w/2, cy = h/2, radius = Math.min(cx, cy) - 10;
  
  const data = [
    { val: critical, color: '#081F60' }, // Dark Navy
    { val: warning,  color: '#4B6FBF' }, // Mid Blue
    { val: elevated, color: '#8faee8' }, 
    { val: normal,   color: '#cfdef5' }  
  ];

  let startAngle = -0.5 * Math.PI;
  data.forEach(slice => {
    if (slice.val === 0) return;
    const sliceAngle = (slice.val / total) * 2 * Math.PI;
    
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, radius, startAngle, startAngle + sliceAngle);
    ctx.closePath();
    ctx.fillStyle = slice.color;
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = '#fff';
    ctx.stroke();

    startAngle += sliceAngle;
  });

  return canvas.toDataURL('image/png', 0.8);
}

// ── Low-level helpers ─────────────────────────────────────────────────────────
const mk = (doc) => {
  const fill   = (...c) => doc.setFillColor(...(c.length === 1 ? c[0] : c));
  const draw   = (...c) => doc.setDrawColor(...(c.length === 1 ? c[0] : c));
  const txt    = (...c) => doc.setTextColor(...(c.length === 1 ? c[0] : c));
  const bold   = (sz)   => { doc.setFontSize(sz); doc.setFont('helvetica', 'bold');   };
  const normal = (sz)   => { doc.setFontSize(sz); doc.setFont('helvetica', 'normal'); };
  const italic = (sz)   => { doc.setFontSize(sz); doc.setFont('helvetica', 'italic'); };

  const hline = (y, col = C.border, lw = 0.25) => {
    draw(col); doc.setLineWidth(lw); doc.line(M, y, PW - M, y);
  };

  /** Small pill badge */
  const pill = (x, y, label, bg, fg = C.white, r = 1.2) => {
    bold(5.5);
    const tw = doc.getTextWidth(label) + 5;
    fill(bg); doc.roundedRect(x, y - 3.8, tw, 5.2, r, r, 'F');
    txt(fg);  doc.text(label, x + 2.5, y);
    return x + tw + 2;
  };

  /** Solid left-border section header */
  const sectionHeader = (x, y, w, label, col, bgCol = C.sectionBg) => {
    // Background band
    fill(bgCol); doc.rect(x, y, w, 7.5, 'F');
    // Left accent stripe
    fill(col);   doc.rect(x, y, 2.2, 7.5, 'F');
    bold(7); txt(col);
    doc.text(label, x + 5, y + 5.3);
  };

  /** Rounded card outline */
  const card = (x, y, w, h, bg = C.cardBg) => {
    fill(bg); doc.roundedRect(x, y, w, h, 2, 2, 'F');
    draw(C.border); doc.setLineWidth(0.2);
    doc.roundedRect(x, y, w, h, 2, 2, 'S');
  };

  /** Two-column key/value row inside a card */
  const kv = (x, y, key, value, unit = '', valCol = C.textDark) => {
    // Label
    normal(6); txt(C.textMid);   doc.text(key, x, y);
    // Value (bold, larger)
    bold(9);   txt(valCol);      doc.text(value, x, y + 6);
    // Unit — measure at the bold size first, then switch to small
    const vw = doc.getTextWidth(value);
    normal(6); txt(C.textMid);   doc.text(unit, x + vw + 1.5, y + 6);
  };

  return { fill, draw, txt, bold, normal, italic, hline, pill, sectionHeader, card, kv };
};

// ── Thermal severity bar — brand palette gradient (#EEF5FF → #4B6FBF → #081F60)
function thermalBar(doc, h, x, y, w, tempVal, minT = 0, maxT = 110) {
  const fraction = Math.max(0, Math.min(1, (tempVal - minT) / (maxT - minT)));

  // Gradient: LIGHT → MID → DARK  (cool side left, hot side right)
  const steps = 60;
  for (let i = 0; i < steps; i++) {
    const f = i / steps;
    let r, g, b;
    if (f < 0.5) {
      // #EEF5FF → #4B6FBF
      const t = f * 2;
      r = Math.round(238 + (75  - 238) * t);
      g = Math.round(245 + (111 - 245) * t);
      b = Math.round(255 + (191 - 255) * t);
    } else {
      // #4B6FBF → #081F60
      const t = (f - 0.5) * 2;
      r = Math.round(75  + (8   - 75 ) * t);
      g = Math.round(111 + (31  - 111) * t);
      b = Math.round(191 + (96  - 191) * t);
    }
    doc.setFillColor(r, g, b);
    doc.rect(x + (i / steps) * w, y, w / steps + 0.5, h, 'F');
  }

  // Marker needle
  const nx = x + fraction * w;
  doc.setFillColor(...DARK);
  doc.triangle(nx - 1.5, y - 0.5, nx + 1.5, y - 0.5, nx, y + h + 2, 'F');

  // Labels
  doc.setFontSize(6); doc.setFont('helvetica', 'normal');
  doc.setTextColor(...MID);
  doc.text(`${minT}°C`, x, y + h + 4.5);
  doc.text(`${maxT}°C`, x + w - 5, y + h + 4.5);
  const lbl = `${tempVal.toFixed(1)}°C`;
  doc.setFont('helvetica', 'bold');
  doc.setTextColor(...DARK);
  doc.text(lbl, Math.min(nx - 3, x + w - 12), y - 2.5);
}

// ── Cover page ────────────────────────────────────────────────────────────────
function drawCover(doc, h, captures, meta, genDate) {
  const { fill, draw, txt, bold, normal, italic, hline, pill, card } = h;

  // ── Full header block ──────────────────────────────────────────────────────
  fill(C.headerBg); doc.rect(0, 0, PW, 70, 'F');

  // Decorative diagonal stripe (dark)
  doc.setFillColor(255, 255, 255, 0.03);
  doc.setFillColor(16, 26, 50);
  doc.rect(0, 0, PW, 70, 'F');

  // Top accent line
  fill(C.brand); doc.rect(0, 0, PW, 1.5, 'F');

  // TIOS wordmark
  bold(32); txt(C.brand);
  doc.text('TIOS', M, 24);

  // Tagline
  normal(8.5); txt(C.textLight);
  doc.text('Thermal Inspection Operating System', M, 31);

  // Accent underbar beneath "TIOS"
  fill(C.brand); doc.rect(M, 26.5, 34, 0.8, 'F');

  // Vertical divider
  fill(C.brandDim); doc.rect(M + 56, 15, 0.4, 22, 'F');

  // Mission name
  bold(17); txt(C.white);
  doc.text(meta.missionName.toUpperCase(), M + 62, 24);

  // Mission metadata pills
  let bx = M + 62;
  bx = pill(bx, 31, `ID: ${meta.missionId}`,         C.darkCard, C.brand);
  bx = pill(bx, 31, meta.operatorName,                C.darkCard, C.textLight);

  // Generated timestamp (top-right)
  normal(7); txt(C.textLight);
  doc.text(`Generated: ${genDate}`, PW - M - doc.getTextWidth(`Generated: ${genDate}`) - 1, 31);

  // ── Decorative dots cluster (top-right corner) ─────────────────────────────
  [[PW - 20, 12], [PW - 16, 8], [PW - 12, 14], [PW - 23, 7]].forEach(([dx, dy]) => {
    fill(C.brand); doc.circle(dx, dy, 1.2, 'F');
    doc.setFillColor(0, 190, 230, 0.3);
  });

  // ── Summary stat cards ─────────────────────────────────────────────────────
  const maxTempAll = Math.max(...captures.map((c) => parseFloat(c.telemetry?.maxTemp || 0)));
  const avgTempAll = captures.reduce((a, c) => a + parseFloat(c.telemetry?.maxTemp || 0), 0) / captures.length;
  const duration   = captures.length > 1
    ? fmtDuration(captures[0].timestamp, captures[captures.length - 1].timestamp)
    : '—';

  const stats = [
    { icon: '▣', label: 'TOTAL CAPTURES', value: String(captures.length),          unit: 'frames',  col: C.brand    },
    { icon: '◉', label: 'PEAK TEMPERATURE', value: maxTempAll.toFixed(1),          unit: '°C',      col: C.thermal  },
    { icon: '◈', label: 'AVERAGE TEMP',     value: avgTempAll.toFixed(1),          unit: '°C',      col: C.warn     },
    { icon: '◷', label: 'MISSION DURATION', value: duration,                       unit: '',        col: C.green    },
  ];

  const sw = (CW - 9) / 4;
  let sy = 78;
  stats.forEach((s, i) => {
    const sx = M + i * (sw + 3);
    // Card
    fill(C.cardBg); doc.roundedRect(sx, sy, sw, 34, 2.5, 2.5, 'F');
    draw(C.border); doc.setLineWidth(0.2); doc.roundedRect(sx, sy, sw, 34, 2.5, 2.5, 'S');
    // Top accent bar
    fill(s.col); doc.roundedRect(sx, sy, sw, 4, 2, 2, 'F');
    doc.rect(sx, sy + 2, sw, 2, 'F');
    // Label
    normal(6); txt(C.textMid); doc.text(s.label, sx + 4, sy + 12);
    // Value
    bold(14); txt(s.col);
    doc.text(s.value, sx + 4, sy + 23);
    // Unit
    normal(6.5); txt(C.textMid); doc.text(s.unit, sx + 4, sy + 29);
  });

  sy += 42;

  // ── Survey extent card ─────────────────────────────────────────────────────
  const lats = captures.map((c) => parseFloat(c.location?.lat || 0));
  const lons = captures.map((c) => parseFloat(c.location?.lon || 0));
  const alts = captures.map((c) => parseFloat(c.location?.alt || 0));

  fill(C.cardBg); doc.roundedRect(M, sy, CW, 28, 2, 2, 'F');
  draw(C.border); doc.setLineWidth(0.2); doc.roundedRect(M, sy, CW, 28, 2, 2, 'S');

  // Left accent
  fill(C.brand); doc.roundedRect(M, sy, 2.5, 28, 2, 2, 'F');
  doc.rect(M + 1, sy, 1.5, 28, 'F');

    bold(7.5); txt(C.textDark); doc.text('SURVEY EXTENT & AREA COVERAGE', M + 7, sy + 7);
    hline(sy + 10, C.border, 0.15);
  
    // Map bounds table (left)
    const extRows = [
      ['Latitude Range',  `${Math.min(...lats).toFixed(6)} °N  →  ${Math.max(...lats).toFixed(6)} °N`],
      ['Longitude Range', `${Math.min(...lons).toFixed(6)} °E  →  ${Math.max(...lons).toFixed(6)} °E`],
      ['Altitude Range',  `${Math.min(...alts).toFixed(1)} m  →  ${Math.max(...alts).toFixed(1)} m AGL`],
    ];
    extRows.forEach(([k, v], i) => {
      normal(7); txt(C.textMid);  doc.text(k + ' :', M + 7, sy + 15 + i * 5);
      bold(7);   txt(C.textDark); doc.text(v, M + 36, sy + 15 + i * 5);
    });
  
    // Satellite/Plot Map (right)
    try {
      const mapImg = buildMapImage(captures, 400, 150);
      doc.addImage(mapImg, 'PNG', PW - M - 70, sy + 3, 68, 22);
      // Map border
      draw(C.borderDk); doc.setLineWidth(0.2);
      doc.roundedRect(PW - M - 70, sy + 3, 68, 22, 1, 1, 'S');
    } catch(e) { console.error('Map draw failed', e); }
  
    sy += 34;

  // ── Summary table header ───────────────────────────────────────────────────
  bold(8); txt(C.textDark); doc.text('CAPTURE SUMMARY', M, sy + 6);
  fill(C.brand); doc.rect(M, sy + 8, 22, 0.6, 'F');
  normal(7); txt(C.textMid); doc.text('All captured frames with location and thermal data', M, sy + 13);

  sy += 17;

  // ── Summary table ─────────────────────────────────────────────────────────
  doc.autoTable({
    head: [['#  ID', 'Time', 'Latitude', 'Longitude', 'Alt (m)', 'Max Temp', 'Battery', 'Mode']],
    body: captures.map((cap, i) => [
      cap.id,
      cap.timeStr || '—',
      parseFloat(cap.location?.lat || 0).toFixed(5),
      parseFloat(cap.location?.lon || 0).toFixed(5),
      parseFloat(cap.location?.alt || 0).toFixed(1),
      parseFloat(cap.telemetry?.maxTemp || 0).toFixed(1) + ' °C',
      parseFloat(cap.telemetry?.voltage || 0).toFixed(1) + ' V',
      cap.telemetry?.flightMode || '—',
    ]),
    startY: sy,
    margin: { left: M, right: M },
    styles: {
      fontSize: 7.5,
      cellPadding: 3,
      textColor: C.textDark,
      valign: 'middle',
    },
    headStyles: {
      fillColor: C.headerBg,
      textColor: C.white,
      fontStyle: 'bold',
      fontSize: 7,
      cellPadding: 3.5,
    },
    alternateRowStyles: { fillColor: [243, 247, 255] },
    columnStyles: {
      0: { fontStyle: 'bold', textColor: C.brand,    cellWidth: 22 },
      5: { fontStyle: 'bold', textColor: C.thermal },
      6: { textColor: C.green },
    },
    tableLineColor: C.border,
    tableLineWidth: 0.15,
  });
}

// ── Detail page (one per capture) ─────────────────────────────────────────────
function drawDetailPage(doc, h, cap, idx, total) {
  const { fill, draw, txt, bold, normal, italic, hline, pill, sectionHeader, card, kv } = h;

  let y = 0;

  // ── Header strip ────────────────────────────────────────────────────────────
  fill(C.headerBg); doc.rect(0, 0, PW, 17, 'F');
  fill(C.brand);    doc.rect(0, 0, PW, 1.2, 'F');   // top brand line

  bold(11.5); txt(C.brand);
  doc.text(cap.id, M, 11);

  const capW = doc.getTextWidth(cap.id);
  normal(7.5); txt(C.textLight);
  doc.text(`${cap.dateStr || ''}  ${cap.timeStr || ''} IST`, M + capW + 4, 11);

  // Right-side badges
  let bx = PW - M - 2;
  const batt = parseFloat(cap.telemetry?.voltage || 0);
  bx = pill(bx - (doc.getTextWidth(`BAT ${batt.toFixed(1)}V`) + 7), 11,
    `BAT ${batt.toFixed(1)}V`,
    batt < 19.0 ? C.thermal : (batt < 22.8 ? C.warn : C.green)
  );
  const armed = cap.telemetry?.armed;
  bx = pill(bx - (doc.getTextWidth(armed ? 'ARMED' : 'SAFE') + 7), 11,
    armed ? 'ARMED' : 'SAFE',
    armed ? C.thermal : C.brandDim
  );
  pill(bx - (doc.getTextWidth(cap.telemetry?.flightMode || 'UNK') + 7), 11,
    cap.telemetry?.flightMode || 'UNKNOWN', C.darkCard, C.brand
  );

  y = 20;

  // ── Images row ─────────────────────────────────────────────────────────────
  const imgH = 58;
  const imgW = (CW - 4) / 2;

  [
    { src: cap.images?.thermal, label: 'THERMAL CAMERA', sub: 'LWIR · 512×384', col: C.thermal },
    { src: cap.images?.rgb,     label: 'RGB CAMERA',     sub: '4K · H.265',     col: C.green   },
  ].forEach((cfg, i) => {
    const ix = M + i * (imgW + 4);

    // Image placeholder / actual image
    fill([12, 20, 38]); doc.roundedRect(ix, y, imgW, imgH, 2, 2, 'F');
    draw(C.borderDk); doc.setLineWidth(0.4); doc.roundedRect(ix, y, imgW, imgH, 2, 2, 'S');

    if (cfg.src) {
      try {
        doc.addImage(cfg.src, 'JPEG', ix, y, imgW, imgH);
      } catch {
        normal(7); txt(C.textLight);
        doc.text('Image data unavailable', ix + 10, y + imgH / 2);
      }
    } else {
      normal(7); txt(C.textLight);
      doc.text('No image captured', ix + 10, y + imgH / 2);
    }

    // Label pill overlay on image
    fill(cfg.col); doc.rect(ix, y, imgW * 0.48, 7, 'F');
    bold(5.5); txt(C.white); doc.text(cfg.label, ix + 2.5, y + 4.5);
    fill(C.darkCard); doc.rect(ix + imgW * 0.48, y, imgW - imgW * 0.48, 7, 'F');
    normal(5.5); txt(C.textLight); doc.text(cfg.sub, ix + imgW * 0.48 + 2.5, y + 4.5);
  });

  y += imgH + 3;

  // ── Thermal severity bar ───────────────────────────────────────────────────
  const maxT = parseFloat(cap.telemetry?.maxTemp || 25);

  // Section header band (full width, brand light bg)
  sectionHeader(M, y, CW, 'THERMAL SEVERITY INDICATOR', C.brand, C.sectionBg);
  y += 10;   // below header band

  // Gradient bar — sits in its own row with room for needle + temp label above
  thermalBar(doc, 6, M + 4, y + 6, CW - 8, maxT, 15, 95);
  // Bar occupies: 6 (bar height) + 2 (needle below) + 5 (labels) = 13 below y+6
  // Temp label drawn 2.5mm above bar = y+3.5

  // Severity badge — sits to the LEFT of the bar, vertically centred on the bar
  const sev = maxT > 85
    ? ['CRITICAL', DARK]
    : maxT > 65
    ? ['WARNING',  MID]
    : maxT > 45
    ? ['ELEVATED', MID]
    : ['NORMAL',   MID];
  const sevW = doc.getTextWidth(sev[0]);
  bold(6); txt(WHITE);
  fill(sev[1]); doc.roundedRect(M + 4, y + 4, sevW + 8, 7, 1.5, 1.5, 'F');
  bold(6.5); txt(WHITE); doc.text(sev[0], M + 8, y + 9);

  y += 28;   // clear bar (6) + needle (2) + labels (5) + badge (7) + gap

  // ── Three info panels — all headers drawn FIRST, then all cards ─────────────
  const panelW = (CW - 4) / 3;
  const cardH  = 50;   // height per card — enough for 4 rows × ~11mm each
  const gap    = 2;    // gap between panels
  const gpsX   = M;
  const tpX    = M + panelW + gap;
  const fpX    = M + (panelW + gap) * 2;

  // ── Draw all three section headers at same y ────────────────────────────
  sectionHeader(gpsX, y,        panelW, 'GPS COORDINATES', C.brand,   C.sectionBg);
  sectionHeader(tpX,  y,        panelW, 'THERMAL DATA',    C.brand,   C.sectionBg);
  sectionHeader(fpX,  y,        panelW, 'FLIGHT DATA',     C.brand,   C.sectionBg);
  y += 8;   // header height

  // ── Draw all three cards at same y ─────────────────────────────────────
  card(gpsX, y, panelW, cardH);
  card(tpX,  y, panelW, cardH);
  card(fpX,  y, panelW, cardH);

  // Row spacing inside each card
  const rowH = 11;   // px between kv rows
  const padT = 5;    // top padding inside card

  // GPS data
  const gpsData = [
    ['Latitude',  parseFloat(cap.location?.lat || 0).toFixed(6), '°N',   C.textDark],
    ['Longitude', parseFloat(cap.location?.lon || 0).toFixed(6), '°E',   C.textDark],
    ['Altitude',  parseFloat(cap.location?.alt || 0).toFixed(1), 'm AGL', C.brand  ],
    ['Heading',   parseFloat(cap.telemetry?.heading || 0).toFixed(0), '°', C.textDark],
  ];
  gpsData.forEach(([k, v, u, vc], i) =>
    kv(gpsX + 4, y + padT + i * rowH, k, v, u, vc));

  // Thermal data
  const thermalData = [
    ['Max Temp', parseFloat(cap.telemetry?.maxTemp  || 0).toFixed(1), '°C', DARK],
    ['Min Temp', parseFloat(cap.telemetry?.minTemp  || 0).toFixed(1), '°C', MID ],
    ['Avg Temp', parseFloat(cap.telemetry?.avgTemp  || 0).toFixed(1), '°C', MID ],
    ['Battery',  parseFloat(cap.telemetry?.voltage  || 0).toFixed(1), 'V',
      parseFloat(cap.telemetry?.voltage || 0) < 19.0 ? DARK : MID],
  ];
  thermalData.forEach(([k, v, u, vc], i) =>
    kv(tpX + 4, y + padT + i * rowH, k, v, u, vc));

  // Flight data
  const flightData = [
    ['Speed',      parseFloat(cap.telemetry?.speed      || 0).toFixed(1), 'm/s', MID ],
    ['Roll',       parseFloat(cap.telemetry?.roll       || 0).toFixed(1), '°',   DARK],
    ['Pitch',      parseFloat(cap.telemetry?.pitch      || 0).toFixed(1), '°',   DARK],
    ['Satellites', String(cap.telemetry?.satellites     || 0),             'SVs', MID ],
  ];
  flightData.forEach(([k, v, u, vc], i) =>
    kv(fpX + 4, y + padT + i * rowH, k, v, u, vc));

  y += cardH + 5;

  // ── Capture metadata strip ─────────────────────────────────────────────────
  fill(C.sectionBg); doc.roundedRect(M, y, CW, 12, 1.5, 1.5, 'F');
  draw(C.border); doc.setLineWidth(0.15); doc.roundedRect(M, y, CW, 12, 1.5, 1.5, 'S');

  bold(6.5); txt(C.brand);
  doc.text('CAPTURE RECORD', M + 4, y + 5);
  normal(6.5); txt(C.textMid);
  const metaStr = `ID: ${cap.id}   ·   Mission: ${cap.missionId || '—'}   ·   Timestamp: ${cap.timestamp || '—'}`;
  doc.text(metaStr, M + 4, y + 10);

  y += 16;

  // ── Notes ─────────────────────────────────────────────────────────────────
  if (cap.notes) {
    fill([255, 251, 235]); doc.roundedRect(M, y, CW, 12, 1.5, 1.5, 'F');
    fill(C.warn); doc.rect(M, y, 2.2, 12, 'F');
    bold(7); txt(C.warn); doc.text('NOTES', M + 5, y + 5);
    normal(7); txt(C.textDark);
    const wrapped = doc.splitTextToSize(cap.notes, CW - 20);
    doc.text(wrapped[0], M + 5, y + 10);
    y += 16;
  }

  // ── Footer ─────────────────────────────────────────────────────────────────
  fill(C.headerBg); doc.rect(0, PH - 10, PW, 10, 'F');
  fill(C.brand);    doc.rect(0, PH - 10, PW, 0.8, 'F');
  normal(6); txt(C.textLight);
  doc.text('TIOS  ·  Thermal Inspection Operating System  ·  CONFIDENTIAL', M, PH - 4);
  bold(6); txt(C.brand);
  doc.text(`Capture ${idx + 1} of ${total}  ·  Page ${idx + 3}`, PW - M - 38, PH - 4);
}

// ── Severity Summary Page ─────────────────────────────────────────────────────
function drawSeveritySummary(doc, h, captures, genDate) {
  const { fill, txt, bold, normal, hline, sectionHeader, card } = h;
  
  // Track severity buckets
  let critical = 0, warning = 0, elevated = 0, normalC = 0;
  captures.forEach(c => {
    const t = parseFloat(c.telemetry?.maxTemp || 0);
    if (t > 85) critical++;
    else if (t > 65) warning++;
    else if (t > 45) elevated++;
    else normalC++;
  });

  // Header band
  fill(C.headerBg); doc.rect(0, 0, PW, 25, 'F');
  fill(C.brand);    doc.rect(0, 0, PW, 1.5, 'F');
  bold(16); txt(C.white); doc.text('SEVERITY SUMMARY', M, 15);
  normal(8); txt(C.textLight); doc.text('Analysis of all recorded thermal anomalies', M, 20);

  let y = 35;
  sectionHeader(M, y, CW, 'SEVERITY DISTRIBUTION', C.brand, C.sectionBg);
  y += 12;

  // Pie chart + labels area
  card(M, y, CW, 70);
  
  try {
    const pieImg = buildPieChartImage(critical, warning, elevated, normalC, 400, 400);
    if (pieImg) {
      doc.addImage(pieImg, 'PNG', M + 20, y + 5, 60, 60);
    }
  } catch(e) { console.error('Pie draw failed', e); }

  // Legend and Stats next to Pie
  const lx = M + 100;
  let ly = y + 15;
  const total = captures.length;

  const leg = [
    { label: 'CRITICAL (>85°C)',   count: critical, col: C.darkCard },
    { label: 'WARNING (>65°C)',    count: warning,  col: C.brand },
    { label: 'ELEVATED (>45°C)',   count: elevated, col: [143, 174, 232] },
    { label: 'NORMAL',             count: normalC,  col: [207, 222, 245] },
  ];

  leg.forEach(l => {
    // color box
    fill(l.col); doc.roundedRect(lx, ly, 5, 5, 1, 1, 'F');
    // text
    bold(8); txt(C.textDark); doc.text(l.label, lx + 8, ly + 4);
    // count
    normal(8); txt(C.textMid); doc.text(`${l.count} captures (${Math.round((l.count/total)*100)}%)`, lx + 50, ly + 4);
    ly += 10;
  });

  y += 85;

  sectionHeader(M, y, CW, 'RECOMMENDED ACTIONS', C.brand, C.sectionBg);
  y += 10;
  card(M, y, CW, 30);
  
  bold(8); txt(C.textDark);
  if (critical > 0) {
    doc.text('IMMEDIATE ATTENTION REQUIRED', M + 5, y + 8);
    normal(8); txt(C.textMid);
    doc.text(`Identified ${critical} critical anomalies exceeding 85°C. Recommend halting target operation until physical inspection is complete.`, M + 5, y + 14, { maxWidth: CW - 10});
  } else if (warning > 0) {
    doc.text('SCHEDULED MAINTENANCE ADVISED', M + 5, y + 8);
    normal(8); txt(C.textMid);
    doc.text(`Identified ${warning} thermal warnings exceeding 65°C. Recommend scheduling preventative maintenance.`, M + 5, y + 14, { maxWidth: CW - 10});
  } else {
    doc.text('ALL SYSTEMS NOMINAL', M + 5, y + 8);
    normal(8); txt(C.textMid);
    doc.text('No critical or warning thermal anomalies detected. Continue standard operations.', M + 5, y + 14, { maxWidth: CW - 10});
  }

  // Footer
  fill(C.headerBg); doc.rect(0, PH - 10, PW, 10, 'F');
  fill(C.brand);    doc.rect(0, PH - 10, PW, 0.8, 'F');
  normal(6); txt(C.textLight);
  doc.text('TIOS  ·  Thermal Inspection Operating System  ·  CONFIDENTIAL', M, PH - 4);
  bold(6); txt(C.brand);
  doc.text(`Page 2 of ${captures.length + 2}`, PW - M - 18, PH - 4);
}

// ── Main export ────────────────────────────────────────────────────────────────
export async function generateInspectionReport(captures, meta = {}) {
  if (!captures?.length) throw new Error('No captures to export');

  const {
    missionId    = 'UNKNOWN',
    missionName  = 'Inspection Mission',
    operatorName = 'TIOS Field System',
  } = meta;

  const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
  const genDate = new Date().toLocaleString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });

  const h = mk(doc);

  // ── Cover page ─────────────────────────────────────────────────────────────
  // Light page background
  h.fill(C.pageBg); doc.rect(0, 0, PW, PH, 'F');
  drawCover(doc, h, captures, { missionId, missionName, operatorName }, genDate);

  // Cover footer
  h.fill(C.headerBg); doc.rect(0, PH - 10, PW, 10, 'F');
  h.fill(C.brand);    doc.rect(0, PH - 10, PW, 0.8, 'F');
  h.normal(6); h.txt(C.textLight);
  doc.text('TIOS  ·  Thermal Inspection Operating System  ·  CONFIDENTIAL', M, PH - 4);
  h.bold(6); h.txt(C.brand);
  doc.text(`Page 1 of ${captures.length + 1}`, PW - M - 18, PH - 4);

  // ── Detail pages ──────────────────────────────────────────────────────────
  // Page 2 is Severity Summary
  doc.addPage();
  h.fill(C.pageBg); doc.rect(0, 0, PW, PH, 'F');
  drawSeveritySummary(doc, h, captures, genDate);

  // Pages 3+ are details
  captures.forEach((cap, idx) => {
    doc.addPage();
    h.fill(C.pageBg); doc.rect(0, 0, PW, PH, 'F');
    drawDetailPage(doc, h, cap, idx, captures.length);
  });

  // ── Save ──────────────────────────────────────────────────────────────────
  const sn = String(captures.length).padStart(3, '0');
  const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  const filename = `INSP_SN${sn}_${missionId}_${ts}.pdf`;
  doc.save(filename);
  return filename;
}

// ── Utility ───────────────────────────────────────────────────────────────────
function fmtDuration(isoA, isoB) {
  const ms = new Date(isoB) - new Date(isoA);
  if (isNaN(ms) || ms < 0) return '—';
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const h = Math.floor(m / 60);
  if (h > 0) return `${h}h ${m % 60}m`;
  if (m > 0) return `${m}m ${s % 60}s`;
  return `${s}s`;
}
