/**
 * TIOS Capture Engine — Local Only
 *
 * Everything is saved to the user's local machine.
 * No server calls, no database.
 *
 * captureFrame()         → grabs canvas frame as base64 JPEG
 * captureThumbnail()     → small version for the sidebar list
 * buildCaptureUnit()     → assembles the complete capture object
 * saveImageLocally()     → triggers a browser download of a single image
 * saveAllImagesLocally() → downloads thermal + RGB as separate files
 */

const THUMB_W = 240;
const THUMB_H = 180;

/**
 * captureFrame — grab current video frame from canvas as base64 JPEG
 */
export function captureFrame(canvasRef, quality = 0.93) {
  const canvas = canvasRef?.current;
  if (!canvas) return null;
  try {
    return canvas.toDataURL('image/jpeg', quality);
  } catch (err) {
    console.error('[Capture] captureFrame error:', err);
    return null;
  }
}

/**
 * captureThumbnail — small version for sidebar display
 */
export function captureThumbnail(canvasRef) {
  const canvas = canvasRef?.current;
  if (!canvas) return null;
  const thumb = document.createElement('canvas');
  thumb.width  = THUMB_W;
  thumb.height = THUMB_H;
  thumb.getContext('2d').drawImage(canvas, 0, 0, THUMB_W, THUMB_H);
  return thumb.toDataURL('image/jpeg', 0.75);
}

/**
 * buildCaptureUnit — assemble the complete capture object.
 * All fields are frozen at the exact millisecond of the button press.
 *
 * Timestamps: GPS time from drone telemetry is used when available.
 * Falls back to system clock only if no GPS fix exists.
 */
export function buildCaptureUnit({ thermalFrame, rgbFrame, thermalThumb, rgbThumb, telemetry, missionId, index }) {
  // ── Resolve timestamp source: prefer GPS time from drone ──────────────────
  // telemetry.gpsDatetimeUtc is set by drone_bridge.py from SYSTEM_TIME MAVLink msg
  const gpsUtcStr = telemetry?.gpsDatetimeUtc;   // e.g. "2026-05-02 10:13:30" (UTC)

  let captureDate;
  let timeSource; // 'gps' | 'system'

  if (gpsUtcStr && gpsUtcStr.length > 0) {
    // Parse the UTC string from the drone bridge (format: "YYYY-MM-DD HH:MM:SS")
    const parsed = new Date(gpsUtcStr.replace(' ', 'T') + 'Z');
    if (!isNaN(parsed.getTime())) {
      captureDate = parsed;
      timeSource  = 'gps';
    }
  }

  if (!captureDate) {
    // No GPS time — fall back to system clock
    captureDate = new Date();
    timeSource  = 'system';
  }

  // Format IST display string (UTC+5:30)
  const istFormatter = new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour:   '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  });
  const istDateFormatter = new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    day: '2-digit', month: 'short', year: 'numeric',
  });

  return {
    id:        `CAP-${String(index).padStart(3, '0')}`,
    timestamp: captureDate.toISOString(),           // always UTC ISO
    timeStr:   istFormatter.format(captureDate),    // IST HH:MM:SS for display
    dateStr:   istDateFormatter.format(captureDate),// IST date for display
    timeSource,                                     // 'gps' or 'system' — shown in UI/PDF
    missionId,

    // GPS + flight data frozen at capture moment
    location: {
      lat: telemetry.lat,
      lon: telemetry.lon,
      alt: telemetry.alt,
    },
    telemetry: {
      maxTemp:    telemetry.maxTemp,
      minTemp:    telemetry.minTemp,
      avgTemp:    telemetry.avgTemp,
      speed:      telemetry.speed,
      battery:    telemetry.battery,
      roll:       telemetry.roll,
      pitch:      telemetry.pitch,
      yaw:        telemetry.yaw,
      heading:    telemetry.heading,
      flightMode: telemetry.flightMode,
      satellites: telemetry.satellites,
      voltage:    telemetry.voltage,
      armed:      telemetry.armed,
    },

    // Full-resolution images (used in PDF)
    images: { thermal: thermalFrame, rgb: rgbFrame },

    // Thumbnails (used in sidebar UI — much smaller in memory)
    thumbnails: { thermal: thermalThumb, rgb: rgbThumb },

    notes: '',
  };
}

/**
 * saveImageLocally
 * Triggers a browser download of a single base64 image.
 *
 * @param {string} dataUrl   — base64 image data URL
 * @param {string} filename  — e.g. "CAP-001_thermal.jpg"
 */
export function saveImageLocally(dataUrl, filename) {
  if (!dataUrl) return;
  const link    = document.createElement('a');
  link.href     = dataUrl;
  link.download = filename;
  link.click();
}

/**
 * saveAllImagesLocally
 * Downloads thermal + RGB images for a capture as separate files.
 * Files go to the browser's default Downloads folder.
 *
 * @param {object} capture — capture unit from buildCaptureUnit
 */
export function saveAllImagesLocally(capture) {
  const base = `${capture.missionId}_${capture.id}`;

  // Small delay between downloads so browser doesn't block them
  saveImageLocally(capture.images.thermal, `${base}_thermal.jpg`);
  setTimeout(() => saveImageLocally(capture.images.rgb, `${base}_rgb.jpg`), 300);
}
