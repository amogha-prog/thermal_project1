"""
drone_bridge.py — SkyDroid H12 MAVLink → TIOS Telemetry Bridge  (v2)
---------------------------------------------------------------------
Architecture:
  1. TimeSync  — converts time.monotonic() → GPS UTC epoch using SYSTEM_TIME
                 messages. Falls back to wall clock after 5 s if no GPS time.
  2. GPSBuffer — sorted ring buffer (200 entries) with midpoint-anchored NED
                 kinematic interpolation. Stores every GLOBAL_POSITION_INT.
  3. AttitudeBuffer — sorted ring buffer with angle-safe interpolation.
                 Stores every ATTITUDE message.
  4. At capture time, geotagged_capture() queries both buffers at
     (capture_time − EKF_DELAY) to get the drone's physical position/attitude
     at the exact frame instant.
  5. Telemetry JSON is broadcast to TIOS Node.js backend at 25 Hz over UDP
     (same port/format as before — no frontend changes required).
  6. Geotag query server (UDP 14557) answers requests from auto_capture.py
     with the structured metadata dict from tag_frame().

Run:
    python drone_bridge.py

Requirements:
    pip install pymavlink
"""

import os
import sys
import json
import math
import time
import bisect
import socket
import threading
import collections
from datetime import datetime, timedelta, timezone, UTC
from pymavlink import mavutil

# ── Add local v2 modules to path ──────────────────────────────────────────────
_HERE    = os.path.dirname(os.path.abspath(__file__))
_V2_DIR  = os.path.join(_HERE, '..', '..', 'v2')  # d:\aeroluna thermal project\v2
sys.path.insert(0, _V2_DIR)

from time_sync import TimeSync
from buffers   import GPSBuffer, AttitudeBuffer
from frame_tagger import tag_frame, EKF_DELAY

# ── Config ────────────────────────────────────────────────────────────────────
SKYDROID_IP   = '192.168.144.11'
TIOS_HOST     = '127.0.0.1'
TIOS_PORT     = 14556
GEOTAG_PORT   = 14557        # UDP query port for geotag requests from auto_capture
SEND_HZ       = 25
SEND_INTERVAL = 1.0 / SEND_HZ
HB_TIMEOUT    = 20
RECONNECT     = 3
VIDEO_LATENCY = float(os.getenv('VIDEO_LATENCY', '0.150'))   # camera pipeline lag (s)

IST_OFFSET = timedelta(hours=5, minutes=30)

SOURCES = [
    'udpin:0.0.0.0:14550',
    'udpin:0.0.0.0:14555',
]

# ── TIOS output socket ────────────────────────────────────────────────────────
tios_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
tios_addr = (TIOS_HOST, TIOS_PORT)

# ── v2 core objects ───────────────────────────────────────────────────────────
time_sync       = TimeSync()
gps_buffer      = GPSBuffer()
attitude_buffer = AttitudeBuffer()

# ── Mutable telemetry snapshot (for TIOS dashboard) ──────────────────────────
def fresh_telemetry():
    return {
        "lat": 0.0, "lon": 0.0, "alt_msl": 0.0, "alt_agl": 0.0,
        "vx": 0.0, "vy": 0.0, "vz": 0.0,
        "ground_speed": 0.0, "climb": 0.0,
        "roll": 0.0, "pitch": 0.0, "yaw": 0.0,
        "heading_body": 0.0, "heading_autopilot": 0.0, "cog": 0.0,
        "battery_voltage": 0.0, "battery_pct": 0.0,
        "satellites": 0, "fix_type": 0,
        "armed": False, "mode": "UNKNOWN",
        "system_datetime_utc": "", "system_datetime_ist": "",
        "gps_datetime_utc": "",   "gps_datetime_ist": "",
        "time_sync_error_sec": None,
        "maxTemp": 0.0, "minTemp": 0.0, "avgTemp": 0.0,
    }

COPTER_MODES = {
    0:'STABILIZE', 1:'ACRO', 2:'ALT_HOLD', 3:'AUTO', 4:'GUIDED',
    5:'LOITER', 6:'RTL', 7:'CIRCLE', 9:'LAND', 11:'DRIFT',
    13:'SPORT', 14:'FLIP', 15:'AUTOTUNE', 16:'POSHOLD',
    17:'BRAKE', 18:'THROW', 19:'AVOID_ADSB', 20:'GUIDED_NOGPS',
    21:'SMART_RTL', 22:'FLOWHOLD', 23:'FOLLOW', 24:'ZIGZAG',
}

def send_telemetry(tel):
    try:
        tios_sock.sendto(json.dumps(tel).encode(), tios_addr)
    except Exception:
        pass

def ts():
    return time.strftime('%H:%M:%S')

def try_connect(source):
    try:
        print(f"[{ts()}] Trying {source} ...")
        master = mavutil.mavlink_connection(source)
        hb = master.wait_heartbeat(timeout=HB_TIMEOUT)
        if hb:
            print(f"[{ts()}] CONNECTED via {source}  "
                  f"(sysid={master.target_system}, compid={master.target_component})")
            return master
        else:
            print(f"[{ts()}] No heartbeat on {source} (timeout {HB_TIMEOUT}s)")
            return None
    except PermissionError:
        print(f"[{ts()}] {source} SKIPPED — port busy (WinError 10013). Is QGC running?")
        return None
    except Exception as e:
        print(f"[{ts()}] {source} failed: {type(e).__name__}: {e}")
        return None


# ── Geotag capture ────────────────────────────────────────────────────────────
def geotagged_capture(capture_sys_t: float, capture_mono_t: float = None) -> dict:
    """
    Return interpolated GPS+attitude metadata for the exact moment a photo was captured.

    Uses the v2 tag_frame() pipeline:
      - frame_time = GPS-epoch timestamp of the capture instant
      - Queries gps_buffer and attitude_buffer at (frame_time − EKF_DELAY)
      - Returns the full structured metadata dict (or {} on failure)

    Args:
        capture_sys_t  : system wall-clock time of capture (time.time())
        capture_mono_t : time.monotonic() at capture (preferred — no epoch error)
    """
    # ── Convert capture time to drone time (GPS epoch) ─────────────────────
    if capture_mono_t is not None:
        frame_time = time_sync.to_drone_time(capture_mono_t - VIDEO_LATENCY)
    else:
        # Fallback: convert wall time → monotonic → drone time
        # wall_delta = capture_sys_t - time.time() (how far in the past the capture was)
        approx_mono = time.monotonic() + (capture_sys_t - time.time())
        frame_time  = time_sync.to_drone_time(approx_mono - VIDEO_LATENCY)

    if frame_time is None:
        return {}

    # ── Guard 1: GPS buffer warmup — need ≥ 10 samples for reliable interp ──────
    if len(gps_buffer.buffer) < 10:
        print(f"[GeoTag] Warmup: only {len(gps_buffer.buffer)} GPS samples (need 10)")
        return {}

    # ── Guard 2: Sync must be locked and SYSTEM_TIME must be fresh ───────────────
    _sync_st = time_sync.get_sync_status()
    if not _sync_st["locked"] or _sync_st["last_update_age"] > 2.0:
        print(f"[GeoTag] Sync unstable — locked={_sync_st['locked']} age={_sync_st['last_update_age']:.1f}s")
        return {}

    # ── Guard 3: frame_time must be within GPS data range ±100 ms ────────────────
    if gps_buffer.times:
        TOL = 0.1
        if frame_time > gps_buffer.times[-1] + TOL:
            print("[GeoTag] Frame ahead of GPS data")
            return {}
        if frame_time < gps_buffer.times[0] - TOL:
            print("[GeoTag] Frame behind oldest GPS data")
            return {}

    try:
        metadata = tag_frame(frame_time, gps_buffer, attitude_buffer)
    except Exception as e:
        print(f"[GeoTag] tag_frame error: {e}")
        metadata = None

    if metadata is None:
        return {}

    # ── Flatten to match the legacy format auto_capture.py expects ─────────
    pos = metadata.get("position", {})
    vel = metadata.get("velocity", {})
    att = metadata.get("attitude", {})
    hdg = metadata.get("heading", {})
    ts_ = metadata.get("timestamp", {})

    capture_dt = datetime.fromtimestamp(capture_sys_t, timezone.utc)

    return {
        # Legacy fields (auto_capture.py reads these)
        "lat":                     pos.get("lat"),
        "lon":                     pos.get("lon"),
        "alt_msl":                 pos.get("alt_msl"),
        "alt_agl":                 pos.get("alt_agl"),
        "heading":                 hdg.get("body"),
        "roll":                    math.degrees(att.get("roll") or 0) if att.get("roll") is not None else None,
        "pitch":                   math.degrees(att.get("pitch") or 0) if att.get("pitch") is not None else None,
        "yaw":                     math.degrees(att.get("yaw") or 0) if att.get("yaw") is not None else None,
        "ground_speed":            vel.get("ground_speed"),
        "vx":                      vel.get("vx"),
        "vy":                      vel.get("vy"),
        "vz":                      vel.get("vz"),
        "heading_autopilot":       hdg.get("autopilot"),
        "cog":                     hdg.get("cog"),
        # Timestamp fields
        "capture_system_time_utc": capture_dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
        "capture_system_time_ist": (capture_dt + IST_OFFSET).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
        "capture_gps_time_utc":    ts_.get("utc"),
        "capture_gps_time_ist":    ts_.get("ist"),
        "sync_offset_sec":         round(time_sync.get_offset() or 0, 4),
        "path":                    "mono" if capture_mono_t is not None else "wall",
        # v2 extended fields
        "ekf_delay_s":             EKF_DELAY,
        "video_latency_s":         VIDEO_LATENCY,
        "frame_epoch":             ts_.get("epoch"),
        "query_epoch":             ts_.get("query_epoch"),
        "battery_voltage":         metadata.get("battery", {}).get("voltage"),
    }


# ── Geotag query server ──────────────────────────────────────────────────────
def geotag_query_server():
    """
    Background UDP server that responds to geotag queries from auto_capture.py.

    Query format (JSON):
        {"type": "geotag_query", "sys_t": <float>}          ← wall-clock time
        {"type": "geotag_query", "sys_t": <float>, "mono_t": <float>}  ← preferred

    Response: flattened metadata dict (see geotagged_capture) + "status" field.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('127.0.0.1', GEOTAG_PORT))
    sock.settimeout(1.0)
    print(f"[GeoTag] Query server listening on port {GEOTAG_PORT}")

    while True:
        try:
            data, addr = sock.recvfrom(512)
            req = json.loads(data.decode())
            if req.get('type') == 'geotag_query':
                sys_t  = float(req['sys_t'])
                mono_t = float(req['mono_t']) if 'mono_t' in req else None
                result = geotagged_capture(sys_t, mono_t)
                result['status'] = 'ok' if result else 'no_data'
                if not result:
                    result = {'status': 'no_data'}
                sock.sendto(json.dumps(result).encode(), addr)
        except socket.timeout:
            continue
        except Exception as e:
            print(f"[GeoTag] Query error: {e}")


# ── Main loop ─────────────────────────────────────────────────────────────────
def run():
    source_idx     = 0
    start_time     = time.monotonic()
    last_seen_boot = None   # most recent time_boot_ms from any message

    while True:
        source = SOURCES[source_idx % len(SOURCES)]
        master = try_connect(source)

        if master is None:
            source_idx += 1
            print(f"[{ts()}] Retrying in {RECONNECT}s ...")
            time.sleep(RECONNECT)
            continue

        # ── Request SYSTEM_TIME at 1 Hz ──────────────────────────────────────
        try:
            master.mav.command_long_send(
                master.target_system,
                master.target_component,
                mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
                0,
                mavutil.mavlink.MAVLINK_MSG_ID_SYSTEM_TIME,   # msg ID = 2
                1_000_000,                                     # interval µs → 1 Hz
                0, 0, 0, 0, 0,
            )
            print(f"[{ts()}] 📡 Requested SYSTEM_TIME stream at 1 Hz")
        except Exception as e:
            print(f"[{ts()}] ⚠️ Could not request SYSTEM_TIME: {e}")

        tel        = fresh_telemetry()
        ground_alt = None
        alpha      = 0.9
        last_send  = 0
        last_hb    = time.monotonic()
        packets    = 0
        att_missing_count = 0

        # ── Rate monitor (mirrors v2/main.py health block) ────────────────────
        msg_count        = {}
        msg_last_time_map = {}
        msg_rate         = {}
        last_rate_print  = time.monotonic()

        print(f"[{ts()}] Streaming telemetry → {TIOS_HOST}:{TIOS_PORT} ...")

        while True:
            try:
                mono_now = time.monotonic()

                # Heartbeat watchdog
                if mono_now - last_hb > HB_TIMEOUT * 2:
                    print(f"[{ts()}] Watchdog: lost heartbeat. Reconnecting...")
                    break

                msg = master.recv_match(blocking=True, timeout=0.05)
                recv_mono = time.monotonic()   # tag arrival immediately
                if not msg:
                    # ── Wall-clock bootstrap if SYSTEM_TIME never arrives ─────
                    if time_sync.offset is None and mono_now - start_time > 5.0:
                        time_sync.bootstrap_wall_clock(last_seen_boot)
                    continue

                mtype = msg.get_type()
                packets += 1

                # ── Rate monitor update ───────────────────────────────────────
                if mtype not in msg_count:
                    msg_count[mtype]         = 0
                    msg_last_time_map[mtype] = recv_mono
                    msg_rate[mtype]          = 0.0
                msg_count[mtype] += 1
                _elapsed = recv_mono - msg_last_time_map[mtype]
                if _elapsed >= 1.0:
                    msg_rate[mtype]          = msg_count[mtype] / _elapsed
                    msg_count[mtype]         = 0
                    msg_last_time_map[mtype] = recv_mono

                # Track latest boot_ms for wall-clock bootstrap
                mb = getattr(msg, 'time_boot_ms', None)
                if mb and mb > 0:
                    last_seen_boot = mb

                # ── Wall-clock bootstrap check ────────────────────────────────
                if time_sync.offset is None and mono_now - start_time > 5.0:
                    time_sync.bootstrap_wall_clock(last_seen_boot)

                # ── HEARTBEAT ─────────────────────────────────────────────────
                if mtype == 'HEARTBEAT':
                    last_hb = mono_now
                    tel["armed"] = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                    tel["mode"]  = COPTER_MODES.get(msg.custom_mode, f"MODE_{msg.custom_mode}")

                # ── GPS POSITION ──────────────────────────────────────────────
                elif mtype == 'GLOBAL_POSITION_INT':
                    tel["lat"]     = msg.lat / 1e7
                    tel["lon"]     = msg.lon / 1e7
                    tel["alt_msl"] = msg.alt / 1000.0

                    agl = msg.relative_alt / 1000.0
                    if mono_now - start_time < 10:
                        tel["alt_agl"] = agl
                    else:
                        if ground_alt is None and tel["ground_speed"] < 0.1:
                            ground_alt = agl
                        corrected = agl - (ground_alt or 0)
                        tel["alt_agl"] = (alpha * tel["alt_agl"] + (1 - alpha) * corrected
                                          if tel["alt_agl"] != 0.0 else corrected)

                    vx = msg.vx / 100.0
                    vy = msg.vy / 100.0
                    vz = msg.vz / 100.0
                    tel["vx"]           = vx
                    tel["vy"]           = vy
                    tel["vz"]           = vz
                    tel["ground_speed"] = math.sqrt(vx**2 + vy**2)

                    # ── Feed GPSBuffer ────────────────────────────────────────
                    boot_ms = getattr(msg, 'time_boot_ms', None)
                    if boot_ms and boot_ms > 0:
                        gps_t = time_sync.boot_to_utc(boot_ms / 1000.0)
                    else:
                        gps_t = time_sync.to_drone_time(recv_mono)

                    if gps_t is not None:
                        gps_buffer.add(gps_t, {
                            "lat":              tel["lat"],
                            "lon":              tel["lon"],
                            "alt_msl":          tel["alt_msl"],
                            "alt_agl":          tel["alt_agl"],
                            "vx":               tel["vx"],
                            "vy":               tel["vy"],
                            "vz":               tel["vz"],
                            "ground_speed":     tel["ground_speed"],
                            "battery_voltage":  tel["battery_voltage"],
                            "heading_autopilot":tel["heading_autopilot"],
                            "cog":              tel["cog"],
                        })

                # ── ATTITUDE ──────────────────────────────────────────────────
                elif mtype == 'ATTITUDE':
                    tel["roll"]  = math.degrees(msg.roll)
                    tel["pitch"] = math.degrees(msg.pitch)
                    tel["yaw"]   = math.degrees(msg.yaw)
                    hb_deg = tel["yaw"]
                    tel["heading_body"] = hb_deg % 360

                    # ── Feed AttitudeBuffer ───────────────────────────────────
                    boot_ms = getattr(msg, 'time_boot_ms', None)
                    if boot_ms and boot_ms > 0:
                        att_t = time_sync.boot_to_utc(boot_ms / 1000.0)
                    else:
                        att_t = time_sync.now()
                        att_missing_count += 1
                        if att_missing_count % 50 == 0:
                            print(f"[{ts()}] ⚠️ ATTITUDE timestamps unreliable — check SYSTEM_TIME")

                    if att_t is not None:
                        attitude_buffer.add(att_t, {
                            "roll":  msg.roll,     # radians — buffer stores raw radians
                            "pitch": msg.pitch,
                            "yaw":   msg.yaw,
                        })

                # ── VFR_HUD ───────────────────────────────────────────────────
                elif mtype == 'VFR_HUD':
                    tel["heading_autopilot"] = msg.heading
                    tel["climb"]             = msg.climb

                # ── GPS_RAW_INT ───────────────────────────────────────────────
                elif mtype == 'GPS_RAW_INT':
                    tel["satellites"] = msg.satellites_visible
                    tel["fix_type"]   = msg.fix_type
                    if msg.cog != 65535:
                        tel["cog"] = msg.cog / 100.0

                # ── BATTERY_STATUS ────────────────────────────────────────────
                elif mtype == 'BATTERY_STATUS':
                    try:
                        voltages = list(msg.voltages) if msg.voltages is not None else []
                        if voltages and voltages[0] not in (0, 65535):
                            v = voltages[0] / 1000.0
                            tel["battery_voltage"] = v
                            tel["battery_pct"] = max(0.0, min(100.0, ((v - 19) / (25.2 - 19)) * 100))
                    except Exception:
                        pass

                # ── SYS_STATUS ────────────────────────────────────────────────
                elif mtype == 'SYS_STATUS':
                    if tel["battery_voltage"] == 0 and msg.voltage_battery not in (0, 65535):
                        v = msg.voltage_battery / 1000.0
                        tel["battery_voltage"] = v
                        tel["battery_pct"] = max(0.0, min(100.0, ((v - 19) / (25.2 - 19)) * 100))

                # ── SYSTEM_TIME ───────────────────────────────────────────────
                elif mtype == 'SYSTEM_TIME':
                    if msg.time_unix_usec > 0:
                        gps_val  = msg.time_unix_usec / 1e6
                        boot_val = getattr(msg, 'time_boot_ms', None)
                        time_sync.update(gps_val, boot_val)

                        # Real sync error for dashboard
                        calc_gps_t = time_sync.now()
                        if calc_gps_t:
                            tel["time_sync_error_sec"] = round(time.time() - calc_gps_t, 4)
                            gps_dt = datetime.fromtimestamp(calc_gps_t, timezone.utc)
                            tel["gps_datetime_utc"] = gps_dt.strftime('%Y-%m-%d %H:%M:%S')
                            tel["gps_datetime_ist"] = (gps_dt + IST_OFFSET).strftime('%Y-%m-%d %H:%M:%S')

                # ── Send at 25 Hz ─────────────────────────────────────────────
                now = time.monotonic()
                if now - last_send >= SEND_INTERVAL:
                    now_utc = datetime.now(timezone.utc)
                    tel["system_datetime_utc"] = now_utc.strftime('%Y-%m-%d %H:%M:%S')
                    tel["system_datetime_ist"] = (now_utc + IST_OFFSET).strftime('%Y-%m-%d %H:%M:%S')
                    send_telemetry(tel)
                    last_send = now
                    if packets % 100 == 0:
                        sync_status = time_sync.get_sync_status()
                        drift_ms    = sync_status.get("offset_drift_rate", 0) * 1000
                        sync_err    = tel.get('time_sync_error_sec') or 0
                        print(f"[{ts()}] OK | mode={tel['mode']} armed={tel['armed']} "
                              f"lat={tel['lat']:.5f} lon={tel['lon']:.5f} "
                              f"agl={tel['alt_agl']:.1f}m spd={tel['ground_speed']:.1f}m/s "
                              f"bat={tel['battery_voltage']:.1f}V "
                              f"sync_err={sync_err:.3f}s drift={drift_ms:.2f}ms/s "
                              f"locked={sync_status['locked']}")

                # ── Health print every 3 s (mirrors v2/main.py) ───────────────
                if now - last_rate_print >= 3.0:
                    _gps_hz  = msg_rate.get('GLOBAL_POSITION_INT', 0.0)
                    _gps_age = now - msg_last_time_map.get('GLOBAL_POSITION_INT', now)
                    if _gps_age > 2.0:
                        _gps_hz = 0.0
                    _att_hz  = msg_rate.get('ATTITUDE', 0.0)
                    _att_age = now - msg_last_time_map.get('ATTITUDE', now)
                    if _att_age > 2.0:
                        _att_hz = 0.0
                    print(f"\n[{ts()}] DATA RATES | GPS: {_gps_hz:.1f} Hz (Age: {_gps_age:.1f}s) | "
                          f"Attitude: {_att_hz:.1f} Hz (Age: {_att_age:.1f}s)")
                    _sst        = time_sync.get_sync_status()
                    _offset_ms  = (time_sync.get_offset() or 0.0) * 1000
                    _drift_ms   = _sst.get("offset_drift_rate", 0.0) * 1000
                    _update_age = _sst["last_update_age"]
                    print(f"[{ts()}] SYNC | Offset: {_offset_ms:.1f} ms | Locked: {_sst['locked']} | "
                          f"Drift: {_drift_ms:.2f} ms/s | EKF_DELAY: {EKF_DELAY*1000:.0f} ms | "
                          f"VIDEO_LATENCY: {VIDEO_LATENCY*1000:.0f} ms")
                    if _update_age > 2.0:
                        print(f"[{ts()}] WARNING SYSTEM_TIME stale: {_update_age:.1f}s since last update")
                    last_rate_print = now

            except KeyboardInterrupt:
                print(f"\n[{ts()}] Stopped.")
                tios_sock.close()
                sys.exit(0)
            except Exception as e:
                print(f"[{ts()}] Receive error: {e}")
                time.sleep(0.5)
                break

        print(f"[{ts()}] Connection lost. Retrying in {RECONNECT}s ...")
        time.sleep(RECONNECT)


if __name__ == '__main__':
    print("=" * 60)
    print("  SkyDroid H12 MAVLink Bridge → TIOS Telemetry  (v2)")
    print(f"  Controller: {SKYDROID_IP}  |  Backend: {TIOS_HOST}:{TIOS_PORT}")
    print(f"  GeoTag Query: UDP 127.0.0.1:{GEOTAG_PORT}")
    print(f"  EKF_DELAY: {EKF_DELAY * 1000:.0f} ms  |  VIDEO_LATENCY: {VIDEO_LATENCY * 1000:.0f} ms")
    print("=" * 60)

    # Start geotag query server in daemon thread
    t = threading.Thread(target=geotag_query_server, daemon=True)
    t.start()

    run()
