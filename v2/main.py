import os
import uuid
from time_sync import TimeSync
from buffers import GPSBuffer, AttitudeBuffer
from frame_tagger import tag_frame, EKF_DELAY
from pymavlink import mavutil
import time
from datetime import datetime, timedelta, UTC

IST_OFFSET = timedelta(hours=5, minutes=30)

# ✅ MOVE FUNCTION HERE (GLOBAL SCOPE)


def to_ist_string(epoch_time):
    if epoch_time is None:
        return "N/A"
    utc_dt = datetime.fromtimestamp(epoch_time, UTC)
    ist_dt = utc_dt + IST_OFFSET
    return ist_dt.strftime("%H:%M:%S.%f")


# ---------------- INIT ----------------
time_sync = TimeSync()
gps_buffer = GPSBuffer()
attitude_buffer = AttitudeBuffer()

att_missing_count = 0

# -------- RATE MONITOR --------
msg_count = {}
msg_last_time = {}
msg_rate = {}

last_print = time.monotonic()
last_rate_print = time.monotonic()
start_time = time.monotonic()
last_frame_time = 0
last_click_mono = 0
VIDEO_LATENCY = float(os.getenv("VIDEO_LATENCY", "0.150"))  # runtime-tunable
last_seen_boot_ms = None   # most recent time_boot_ms from any MAVLink message


def safe(v, fmt=None):
    if v is None:
        return "N/A"
    try:
        return format(v, fmt) if fmt else str(v)
    except Exception:
        return str(v)


# Connect MAVLink
master = mavutil.mavlink_connection('udpin:0.0.0.0:14550')
master.wait_heartbeat()
print("✅ Connected")

# ── Request SYSTEM_TIME at 1 Hz ──────────────────────────────────────────────
# SYSTEM_TIME is NOT streamed by default on many FCs. Without it TimeSync
# has no GPS-epoch reference and every downstream timestamp fails.
try:
    master.mav.command_long_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
        0,                                           # confirmation
        mavutil.mavlink.MAVLINK_MSG_ID_SYSTEM_TIME,  # msg ID = 2
        1_000_000,                                   # interval µs → 1 Hz
        0, 0, 0, 0, 0,
    )
    print("📡 Requested SYSTEM_TIME stream at 1 Hz")
except Exception as e:
    print(f"⚠️ Could not request SYSTEM_TIME stream: {e}")

# Telemetry state
telemetry = {
    "lat": None,
    "lon": None,
    "alt_msl": None,
    "alt_agl": None,
    "vx": None,
    "vy": None,
    "vz": None,
    "ground_speed": None,
    "roll": None,
    "pitch": None,
    "yaw": None,
    "battery_voltage": None,
    "heading_body": None,
    "heading_autopilot": None,
    "cog": None
}

prev_gps = None
ground_alt = None
alpha = 0.9


def capture_frame(frame_mono_time):
    global last_frame_time

    frame_time = time_sync.to_drone_time(frame_mono_time - VIDEO_LATENCY)
    status = time_sync.get_sync_status()

    if frame_time is None or not status["locked"] or status["last_update_age"] > 2.0:
        print("⚠️ Time sync unstable")
        return None

    offset = time_sync.get_offset()
    if offset is None:
        print("⚠️ Offset not initialized")
        return None

    if abs((time_sync.now() - frame_time) - VIDEO_LATENCY) > 0.3:
        print("⚠️ Frame timing abnormal")

    if not gps_buffer.times:
        print("⚠️ No GPS timestamps")
        return None

    if len(gps_buffer.buffer) < 10:
        print("⚠️ Not enough GPS data")
        return None

    TOL = 0.1
    if frame_time > gps_buffer.times[-1] + TOL:
        print("⚠️ Frame ahead of GPS data")
        return None

    if frame_time < gps_buffer.times[0] - TOL:
        print("⚠️ Frame behind oldest GPS data")
        return None

    if last_frame_time and abs(frame_time - last_frame_time) < 1.0:
        return None

    frame_id = str(uuid.uuid4())[:8]

    try:
        metadata = tag_frame(frame_time, gps_buffer, attitude_buffer)
    except Exception as e:
        print(f"❌ Error tagging frame (likely bad timestamp): {e}")
        return None

    if metadata is None:
        return None

    print("\n📸 FRAME CAPTURED")
    print(f"Frame ID: {frame_id}")
    print(f"Capture Time (UTC epoch): {frame_time:.6f}")

    gps_delta = getattr(gps_buffer, "last_delta", None)
    att_delta = getattr(attitude_buffer, "last_delta", None)
    if gps_delta is not None and att_delta is not None:
        print(f"Δ gps interp: {gps_delta * 1000:.2f} ms")
        print(f"Δ att interp: {att_delta * 1000:.2f} ms")

    print(metadata)

    last_frame_time = frame_time
    return metadata


# ---------------- LOOP ----------------
while True:

    try:
        msg = master.recv_match(blocking=False)
    except Exception as e:
        # Catch internal pymavlink parsing errors from garbled UDP packets
        continue

    if msg:
        msg_type = msg.get_type()
        now = time.monotonic()

        # ================================
        # 🔍 HUMAN READABLE TIMESTAMP DEBUG (IST)
        # ================================
        recv_time = now  # reuse now — avoids a second syscall and sub-ms drift

        boot_time = None
        utc_time = None

        # Extract timestamps
        if hasattr(msg, "time_boot_ms") and msg.time_boot_ms > 0:
            boot_time = msg.time_boot_ms / 1000.0
            last_seen_boot_ms = msg.time_boot_ms  # track for wall-clock bootstrap

        if hasattr(msg, "time_unix_usec") and msg.time_unix_usec > 0:
            utc_time = msg.time_unix_usec / 1e6

        boot_to_utc = None
        if boot_time is not None:
            boot_to_utc = time_sync.boot_to_utc(boot_time)

         # Convert monotonic → UTC → IST
        recv_utc = time_sync.to_drone_time(recv_time)
        recv_ist = to_ist_string(recv_utc)

        utc_ist = to_ist_string(utc_time)
        boot_ist = to_ist_string(boot_to_utc)

        local_sync_utc = time_sync.now()
        local_sync_ist = to_ist_string(local_sync_utc)

       # print("\n⏱ TIMESTAMP DEBUG (IST) ---------------------")
       # Only print important messages
        # if msg_type in ["SYSTEM_TIME", "GLOBAL_POSITION_INT", "ATTITUDE"]:
        #     print("\n⏱ TIMESTAMP DEBUG (IST) ---------------------")
        #     print(f"Message: {msg_type}")

        # if boot_time is not None:
        #     print(f"Boot Time: {boot_time:.3f} s")

        # print(f"Drone UTC → IST: {utc_ist}")
        # print(f"Boot→UTC → IST: {boot_ist}")
        # print(f"Receive Time → IST: {recv_ist}")
        # print(f"Local Sync Time → IST: {local_sync_ist}")

        # if boot_to_utc is not None and utc_time is not None:
        #     print(
        #         f"Δ (boot_to_utc - utc): {(boot_to_utc - utc_time)*1000:.2f} ms")

        # if boot_to_utc is not None and local_sync_utc is not None:
        #     print(
        #         f"Δ (local_sync - boot_to_utc): {(local_sync_utc - boot_to_utc)*1000:.2f} ms")

        # if boot_to_utc is not None and recv_utc is not None:
        #     print(
        #         f"Δ (receive - boot): {(recv_utc - boot_to_utc)*1000:.2f} ms")

        # print("---------------------------------------------")

        # -------- RATE MONITOR --------
        if msg_type not in msg_count:
            msg_count[msg_type] = 0
            msg_last_time[msg_type] = now
            msg_rate[msg_type] = 0

        msg_count[msg_type] += 1

        elapsed = now - msg_last_time[msg_type]
        if elapsed >= 1.0:
            msg_rate[msg_type] = msg_count[msg_type] / elapsed
            msg_count[msg_type] = 0
            msg_last_time[msg_type] = now

        # -------- GPS POSITION --------
        if msg_type == 'GLOBAL_POSITION_INT':
            telemetry["lat"] = msg.lat / 1e7
            telemetry["lon"] = msg.lon / 1e7
            telemetry["alt_msl"] = msg.alt / 1000

            current_agl = msg.relative_alt / 1000

            if time.monotonic() - start_time < 10:
                telemetry["alt_agl"] = current_agl
            else:
                if ground_alt is None and telemetry["ground_speed"] is not None:
                    if telemetry["ground_speed"] < 0.1:
                        ground_alt = current_agl

                corrected_agl = current_agl - ground_alt if ground_alt else current_agl

                if telemetry["alt_agl"] is None:
                    telemetry["alt_agl"] = corrected_agl
                else:
                    telemetry["alt_agl"] = alpha * \
                        telemetry["alt_agl"] + (1 - alpha) * corrected_agl

            vx = msg.vx / 100
            vy = msg.vy / 100
            vz = msg.vz / 100

            telemetry["vx"] = vx
            telemetry["vy"] = vy
            telemetry["vz"] = vz
            telemetry["ground_speed"] = (vx**2 + vy**2) ** 0.5

            if hasattr(msg, "time_boot_ms") and msg.time_boot_ms > 0:
                boot_time = msg.time_boot_ms / 1000.0
                gps_time = time_sync.boot_to_utc(boot_time)

                if gps_time is not None:
                    # gps_buffer.add(gps_time, telemetry)
                    gps_buffer.add(gps_time, {
                        "lat": telemetry["lat"],
                        "lon": telemetry["lon"],
                        "alt_msl": telemetry["alt_msl"],
                        "alt_agl": telemetry["alt_agl"],

                        "vx": telemetry["vx"],
                        "vy": telemetry["vy"],
                        "vz": telemetry["vz"],
                        "ground_speed": telemetry["ground_speed"],

                        "battery_voltage": telemetry["battery_voltage"],
                        "heading_autopilot": telemetry["heading_autopilot"],
                        "cog": telemetry["cog"]
                    })

        elif msg_type == 'ATTITUDE':
            telemetry["roll"] = msg.roll
            telemetry["pitch"] = msg.pitch
            telemetry["yaw"] = msg.yaw

            att_time = None
            if hasattr(msg, "time_boot_ms") and msg.time_boot_ms > 0:
                boot_time = msg.time_boot_ms / 1000.0
                att_time = time_sync.boot_to_utc(boot_time)

            if att_time is None:
                att_time = time_sync.now()
                att_missing_count += 1
                if att_missing_count % 10 == 0:
                    print("⚠️ Frequent ATTITUDE timestamp fallback (SYSTEM_TIME not yet received)")
                if att_missing_count > 50 and att_missing_count % 50 == 0:
                    print("❌ ATTITUDE timestamps unreliable — check SYSTEM_TIME stream")

            if att_time is not None:
                attitude_buffer.add(att_time, {
                    "roll": msg.roll,
                    "pitch": msg.pitch,
                    "yaw": msg.yaw
                })

        elif msg_type == 'BATTERY_STATUS':
            if msg.voltages[0] not in (0, 65535):
                telemetry["battery_voltage"] = msg.voltages[0] / 1000.0

        elif msg_type == 'GPS_RAW_INT':
            # print(f"[GPS] Fix: {msg.fix_type}, Sats: {msg.satellites_visible}")
            if msg.cog != 65535:
                telemetry["cog"] = msg.cog / 100

        elif msg_type == 'VFR_HUD':
            telemetry["heading_autopilot"] = msg.heading

        elif msg_type == 'SYSTEM_TIME':
            if msg.time_unix_usec > 0:
                gps_time_unix = msg.time_unix_usec / 1e6
                boot_time_ms = getattr(msg, "time_boot_ms", None)
                time_sync.update(gps_time_unix, boot_time_ms)

    # -------- WALL-CLOCK BOOTSTRAP (if SYSTEM_TIME never arrives) --------
    # After 5 s with no SYSTEM_TIME the system would be entirely blocked.
    # Bootstrap from wall clock so GPS/attitude buffers can accept data.
    # Accuracy: wall-clock is within ~50 ms of GPS time — acceptable for
    # geotag startup; real SYSTEM_TIME will refine it once the stream starts.
    if time_sync.offset is None and time.monotonic() - start_time > 5.0:
        time_sync.bootstrap_wall_clock(last_seen_boot_ms)

    # -------- EVENT: SIMULATED USER CLICK --------
    current_mono = time.monotonic()
    if current_mono - last_click_mono >= 2.0:
        # NOTE: running in module scope, so no 'global' needed here
        last_click_mono = current_mono
        capture_frame(current_mono)

    # -------- PRINT LOOP --------
    if telemetry["lat"] and (time.monotonic() - last_print > 0.5):

        current_sync_time = time_sync.now()

        if current_sync_time:
            utc_dt = datetime.fromtimestamp(current_sync_time, UTC)
            ist_dt = utc_dt + IST_OFFSET

            # print("🚁 DRONE TELEMETRY")
            # print(
            #     f"📍 Lat: {safe(telemetry['lat'], '.7f')}, Lon: {safe(telemetry['lon'], '.7f')}")
            # print(
            #     f"Alt MSL: {safe(telemetry['alt_msl'], '.2f')} m | AGL: {safe(telemetry['alt_agl'], '.2f')} m")
            # print(
            #     f"\n🧭 Roll: {safe(telemetry['roll'], '.4f')}, Pitch: {safe(telemetry['pitch'], '.4f')}, Yaw: {safe(telemetry['yaw'], '.4f')}")
            # print(f"\n🚀 Speed: {safe(telemetry['ground_speed'], '.2f')} m/s")
            # print(f"\n🔋 Battery: {safe(telemetry['battery_voltage'])} V")
            # print(f"\n⏱ TIME: IST: {ist_dt}")
            pass

        last_print = time.monotonic()

    if time.monotonic() - last_rate_print >= 3.0:
        now_time = time.monotonic()

        gps_rate = msg_rate.get('GLOBAL_POSITION_INT', 0.0)
        gps_age = now_time - msg_last_time.get('GLOBAL_POSITION_INT', now_time)
        if gps_age > 2.0:
            gps_rate = 0.0

        att_rate = msg_rate.get('ATTITUDE', 0.0)
        att_age = now_time - msg_last_time.get('ATTITUDE', now_time)
        if att_age > 2.0:
            att_rate = 0.0

        print(f"📡 DATA RATES | GPS: {gps_rate:.1f} Hz (Age: {gps_age:.1f}s) | Attitude: {att_rate:.1f} Hz (Age: {att_age:.1f}s)")

        # -------- SYNC HEALTH --------
        sync_status = time_sync.get_sync_status()
        offset_ms = (time_sync.get_offset() or 0.0) * 1000
        drift_rate_ms = sync_status.get("offset_drift_rate", 0.0) * 1000
        update_age = sync_status["last_update_age"]
        print(f"\U0001f551 SYNC   | Offset: {offset_ms:.1f} ms | Locked: {sync_status['locked']} | "
              f"Drift: {drift_rate_ms:.2f} ms/s | EKF_DELAY: {EKF_DELAY*1000:.0f} ms | "
              f"VIDEO_LATENCY: {VIDEO_LATENCY*1000:.0f} ms")
        if update_age > 2.0:
            print(f"\u26a0\ufe0f SYSTEM_TIME stale: {update_age:.1f}s since last update")

        last_rate_print = time.monotonic()
