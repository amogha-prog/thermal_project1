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
 */
export function buildCaptureUnit({ thermalFrame, rgbFrame, thermalThumb, rgbThumb, telemetry, missionId, index }) {
  const now = new Date();
  return {
    id:        `CAP-${String(index).padStart(3, '0')}`,
    timestamp: now.toISOString(),
    timeStr:   now.toTimeString().slice(0, 8),
    dateStr:   now.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }),
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
