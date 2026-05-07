import math
from datetime import datetime, UTC, timedelta

IST_OFFSET = timedelta(hours=5, minutes=30)

# ── EKF Delay ──────────────────────────────────────────────────────────────────
# The EKF position output is delayed relative to real time. Subtracting this
# value aligns the camera-capture time with the correct past state in the buffer.
# Starting value: 100 ms (typical for ArduPilot / PX4).
# Tuning: if tagged position appears ahead of actual → reduce this value.
#          if tagged position appears behind actual  → increase this value.
EKF_DELAY = 0.10  # seconds


def tag_frame(frame_time, gps_buffer, attitude_buffer):
    """
    Tag a frame using DRONE TIME (frame_time must be in drone time domain).

    Args:
        frame_time (float): Drone time in float seconds (aligned using TimeSync).
        gps_buffer (GPSBuffer): Buffer with drone-timestamped GPS telemetry.
        attitude_buffer (AttitudeBuffer): Buffer with drone-timestamped Attitude.

    Returns:
        dict: Structured metadata for the frame, or None on failure.
    """

    # Apply EKF delay: query the buffer at the time the EKF was reporting,
    # which corresponds to a slightly earlier real-world position.
    query_time = frame_time - EKF_DELAY   # float seconds — no unit mixing

    # ── Interpolate using drone time (CRITICAL) ─────────────────────────────────
    pos = gps_buffer.interpolate(query_time)
    att = attitude_buffer.interpolate(query_time)

    if pos is None:
        print("⚠️ Frame dropped: no GPS data at query_time")
        return None

    if att is None:
        print("⚠️ Attitude data stale")

    # ── Convert drone time → UTC / IST ─────────────────────────────────────────
    utc_dt = datetime.fromtimestamp(frame_time, UTC)   # keep display as frame time
    ist_dt  = utc_dt + IST_OFFSET

    # ── Heading (deg) from yaw (rad) ───────────────────────────────────────────
    heading_body = None
    if att and att.get("yaw") is not None:
        heading_body = math.degrees(att["yaw"]) % 360

    return {
        # 🕒 TIME
        "timestamp": {
            "utc":   utc_dt.strftime("%Y-%m-%d %H:%M:%S.%f"),
            "ist":   ist_dt.strftime("%Y-%m-%d %H:%M:%S.%f"),
            "epoch": frame_time,          # raw drone-aligned timestamp (float s)
            "query_epoch": query_time,    # EKF-corrected query time (float s)
        },

        # 📍 POSITION
        "position": {
            "lat":     pos.get("lat"),
            "lon":     pos.get("lon"),
            "alt_msl": pos.get("alt_msl"),
            "alt_agl": pos.get("alt_agl"),
        },

        # 🚀 VELOCITY
        "velocity": {
            "vx":           pos.get("vx"),
            "vy":           pos.get("vy"),
            "vz":           pos.get("vz"),
            "ground_speed": pos.get("ground_speed"),
        },

        # 🧭 ATTITUDE
        "attitude": {
            "roll":  att.get("roll")  if att else None,
            "pitch": att.get("pitch") if att else None,
            "yaw":   att.get("yaw")   if att else None,
        },

        # 🧭 HEADING
        "heading": {
            "body":      heading_body,
            "autopilot": pos.get("heading_autopilot"),
            "cog":       pos.get("cog"),
        },

        # 🔋 BATTERY
        "battery": {
            "voltage": pos.get("battery_voltage"),
        },
    }
