"""
drone_bridge.py — SkyDroid H12 MAVLink -> TIOS Telemetry Bridge
----------------------------------------------------------------
Connects to the SkyDroid H12 controller (192.168.144.11) via TCP:8520,
parses full MAVLink telemetry, and forwards JSON to the TIOS Node.js
backend on UDP port 14555 at 10 Hz.

Fallback: if TCP:8520 is unavailable, also tries UDP on common ports.

Run:
    python drone_bridge.py

Requirements:
    pip install pymavlink
"""

import socket
import json
import time
import sys
import math
from datetime import datetime, timedelta, timezone
from pymavlink import mavutil

# ── Config ────────────────────────────────────────────────────────────────────
SKYDROID_IP   = '192.168.144.11'
TIOS_HOST     = '127.0.0.1'
TIOS_PORT     = 14556        # JSON output to Node.js (changed to avoid conflict with 14555 input)
SEND_HZ       = 10           # telemetry send rate
SEND_INTERVAL = 1.0 / SEND_HZ
HB_TIMEOUT    = 20           # heartbeat wait timeout (s)
RECONNECT     = 3            # seconds between reconnect attempts

IST_OFFSET = timedelta(hours=5, minutes=30)

# ── Connection candidates (tried in order) ────────────────────────────────────
# H12 broadcasts MAVLink UDP — no TCP needed
SOURCES = [
    f'udpin:0.0.0.0:14555',    # Primary — H12 sends MAVLink to this port
    f'udpin:0.0.0.0:14550',    # Fallback
    f'udpin:0.0.0.0:14551',
    f'udpin:0.0.0.0:18570',
]

# ── TIOS output socket ────────────────────────────────────────────────────────
tios_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
tios_addr = (TIOS_HOST, TIOS_PORT)

# ── Telemetry state ───────────────────────────────────────────────────────────
def fresh_telemetry():
    return {
        # GPS
        "lat": 0.0,
        "lon": 0.0,
        "alt_msl": 0.0,
        "alt_agl": 0.0,
        # Speed
        "vx": 0.0,
        "vy": 0.0,
        "vz": 0.0,
        "ground_speed": 0.0,
        "climb": 0.0,
        # Attitude (degrees)
        "roll": 0.0,
        "pitch": 0.0,
        "yaw": 0.0,
        # Heading
        "heading_body": 0.0,
        "heading_autopilot": 0.0,
        "cog": 0.0,
        # Battery
        "battery_voltage": 0.0,
        "battery_pct": 0.0,
        # GPS status
        "satellites": 0,
        "fix_type": 0,
        # Flight state
        "armed": False,
        "mode": "UNKNOWN",
        # Time
        "system_datetime_utc": "",
        "system_datetime_ist": "",
        "gps_datetime_utc": "",
        "gps_datetime_ist": "",
        "time_sync_error_sec": None,
        # Thermal (filled by thermal pipeline if running)
        "maxTemp": 0.0,
        "minTemp": 0.0,
        "avgTemp": 0.0,
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
    """Attempt MAVLink connection. Returns master object or None."""
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
    except Exception as e:
        print(f"[{ts()}] {source} failed: {type(e).__name__}: {e}")
        return None

def run():
    source_idx = 0
    while True:
        source = SOURCES[source_idx % len(SOURCES)]
        master = try_connect(source)

        if master is None:
            # Rotate to next source on failure
            source_idx += 1
            print(f"[{ts()}] Retrying in {RECONNECT}s ...")
            time.sleep(RECONNECT)
            continue

        # ── Successfully connected — start receive loop ────────────────────────
        tel           = fresh_telemetry()
        time_offset   = None
        ground_alt    = None
        start_time    = time.time()
        alpha         = 0.9
        last_send     = 0
        last_hb       = time.time()
        packets       = 0

        print(f"[{ts()}] Streaming telemetry -> {TIOS_HOST}:{TIOS_PORT} ...")

        while True:
            try:
                # ── System time ──────────────────────────────────────────────
                sys_time = time.time() + (time_offset or 0)
                now_utc  = datetime.now(timezone.utc)
                tel["system_datetime_utc"] = now_utc.strftime('%Y-%m-%d %H:%M:%S')
                tel["system_datetime_ist"] = (now_utc + IST_OFFSET).strftime('%Y-%m-%d %H:%M:%S')

                # ── Heartbeat watchdog ────────────────────────────────────────
                if time.time() - last_hb > HB_TIMEOUT * 2:
                    print(f"[{ts()}] Watchdog: lost heartbeat. Reconnecting...")
                    break

                msg = master.recv_match(blocking=True, timeout=0.05)
                if not msg:
                    continue

                mtype = msg.get_type()
                packets += 1

                if mtype == 'HEARTBEAT':
                    last_hb = time.time()
                    tel["armed"] = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                    tel["mode"]  = COPTER_MODES.get(msg.custom_mode, f"MODE_{msg.custom_mode}")

                elif mtype == 'GLOBAL_POSITION_INT':
                    tel["lat"]     = msg.lat / 1e7
                    tel["lon"]     = msg.lon / 1e7
                    tel["alt_msl"] = msg.alt / 1000.0

                    agl = msg.relative_alt / 1000.0
                    if time.time() - start_time < 10:
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
                    tel["vx"] = vx
                    tel["vy"] = vy
                    tel["vz"] = vz
                    tel["ground_speed"] = math.sqrt(vx**2 + vy**2)

                elif mtype == 'ATTITUDE':
                    tel["roll"]  = math.degrees(msg.roll)
                    tel["pitch"] = math.degrees(msg.pitch)
                    tel["yaw"]   = math.degrees(msg.yaw)
                    hb = math.degrees(msg.yaw)
                    tel["heading_body"] = hb + 360 if hb < 0 else hb

                elif mtype == 'VFR_HUD':
                    tel["heading_autopilot"] = msg.heading
                    tel["climb"]             = msg.climb

                elif mtype == 'GPS_RAW_INT':
                    tel["satellites"] = msg.satellites_visible
                    tel["fix_type"]   = msg.fix_type
                    if msg.cog != 65535:
                        tel["cog"] = msg.cog / 100.0

                elif mtype == 'BATTERY_STATUS':
                    if msg.voltages and msg.voltages[0] not in (0, 65535):
                        v = msg.voltages[0] / 1000.0
                        tel["battery_voltage"] = v
                        tel["battery_pct"] = max(0.0, min(100.0, ((v - 19) / (25.2 - 19)) * 100))

                elif mtype == 'SYS_STATUS':
                    if tel["battery_voltage"] == 0 and msg.voltage_battery not in (0, 65535):
                        v = msg.voltage_battery / 1000.0
                        tel["battery_voltage"] = v
                        tel["battery_pct"] = max(0.0, min(100.0, ((v - 19) / (25.2 - 19)) * 100))

                elif mtype == 'SYSTEM_TIME':
                    if msg.time_unix_usec > 0:
                        gps_t = msg.time_unix_usec / 1e6
                        new_off = gps_t - sys_time
                        time_offset = new_off if time_offset is None else 0.7 * time_offset + 0.3 * new_off
                        tel["time_sync_error_sec"] = round(sys_time - gps_t, 6)
                        gps_dt = datetime.fromtimestamp(gps_t, timezone.utc)
                        tel["gps_datetime_utc"] = gps_dt.strftime('%Y-%m-%d %H:%M:%S')
                        tel["gps_datetime_ist"] = (gps_dt + IST_OFFSET).strftime('%Y-%m-%d %H:%M:%S')

                # ── Send at 10 Hz ─────────────────────────────────────────────
                now = time.time()
                if now - last_send >= SEND_INTERVAL:
                    send_telemetry(tel)
                    last_send = now
                    if packets % 100 == 0:
                        print(f"[{ts()}] OK | mode={tel['mode']} armed={tel['armed']} "
                              f"lat={tel['lat']:.5f} lon={tel['lon']:.5f} "
                              f"agl={tel['alt_agl']:.1f}m spd={tel['ground_speed']:.1f}m/s "
                              f"bat={tel['battery_voltage']:.1f}V")

            except KeyboardInterrupt:
                print(f"\n[{ts()}] Stopped.")
                tios_sock.close()
                sys.exit(0)
            except Exception as e:
                print(f"[{ts()}] Receive error: {e}")
                time.sleep(0.5)
                break

        # Lost connection — stay on same source, retry
        print(f"[{ts()}] Connection lost. Retrying in {RECONNECT}s ...")
        time.sleep(RECONNECT)

if __name__ == '__main__':
    print("=" * 60)
    print("  SkyDroid H12 MAVLink Bridge -> TIOS Telemetry")
    print(f"  Controller: {SKYDROID_IP}  |  Backend: {TIOS_HOST}:{TIOS_PORT}")
    print("=" * 60)
    run()
