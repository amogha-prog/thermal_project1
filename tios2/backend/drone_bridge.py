"""
drone_bridge.py — MAVLink → TIOS UDP Bridge (Full Telemetry)
--------------------------------------------------------------
Reads real MAVLink telemetry from Mission Planner / QGroundControl
on UDP port 14550, converts ALL fields to JSON, and forwards to
the TIOS backend on UDP port 14555 at 10 Hz.

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
MAVLINK_LISTEN    = 'udpin:0.0.0.0:14550'
TIOS_HOST         = '127.0.0.1'
TIOS_PORT         = 14555
SEND_INTERVAL     = 0.1       # 10 Hz
HEARTBEAT_TIMEOUT = 16        # seconds before reconnect
RECONNECT_DELAY   = 5

IST_OFFSET = timedelta(hours=5, minutes=30)

# ── UDP socket ────────────────────────────────────────────────────────────────
sock      = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
tios_addr = (TIOS_HOST, TIOS_PORT)

# ── Telemetry state ───────────────────────────────────────────────────────────
def fresh_telemetry():
    return {
        # GPS
        "lat": 0.0,
        "lon": 0.0,
        "alt_msl": 0.0,      # altitude above mean sea level (m)
        "alt_agl": 0.0,      # altitude above ground level (m)

        # Speed
        "vx": 0.0,           # North velocity (m/s)
        "vy": 0.0,           # East velocity (m/s)
        "vz": 0.0,           # Down velocity (m/s)
        "ground_speed": 0.0, # horizontal speed (m/s)
        "climb": 0.0,        # vertical speed from VFR_HUD (m/s)

        # Attitude (degrees)
        "roll": 0.0,
        "pitch": 0.0,
        "yaw": 0.0,

        # Heading
        "heading_body": 0.0,       # from ATTITUDE yaw (degrees 0-360)
        "heading_autopilot": 0.0,  # from VFR_HUD (degrees)
        "cog": 0.0,                # Course Over Ground from GPS_RAW_INT (degrees)

        # Battery
        "battery_voltage": 0.0,
        "battery_pct": 0.0,

        # GPS status
        "satellites": 0,
        "fix_type": 0,

        # ARM / MODE
        "armed": False,
        "mode": "UNKNOWN",

        # Timestamps
        "system_datetime_utc": "",
        "system_datetime_ist": "",
        "gps_datetime_utc": "",
        "gps_datetime_ist": "",
        "time_sync_error_sec": None,

        # Thermal temps (filled by Python pipeline if running)
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

def send(telemetry):
    try:
        sock.sendto(json.dumps(telemetry).encode(), tios_addr)
    except Exception:
        pass

def run_bridge():
    while True:
        master        = None
        tel           = fresh_telemetry()
        time_offset   = None
        ground_alt    = None
        start_time    = time.time()
        alpha         = 0.9          # AGL low-pass filter coefficient
        last_send     = 0

        # ── Connect ───────────────────────────────────────────────────────────
        try:
            master = mavutil.mavlink_connection(MAVLINK_LISTEN)
            master.wait_heartbeat(timeout=HEARTBEAT_TIMEOUT)
        except Exception:
            time.sleep(RECONNECT_DELAY)
            continue

        # ── Receive loop ──────────────────────────────────────────────────────
        last_heartbeat = time.time()

        while True:
            try:
                # ── System time ───────────────────────────────────────────────
                if time_offset is not None:
                    system_time = time.time() + time_offset
                else:
                    system_time = time.time()

                now_utc = datetime.now(timezone.utc)
                tel["system_datetime_utc"] = now_utc.strftime('%Y-%m-%d %H:%M:%S')
                tel["system_datetime_ist"] = (now_utc + IST_OFFSET).strftime('%Y-%m-%d %H:%M:%S')

                # ── Heartbeat watchdog ────────────────────────────────────────
                if time.time() - last_heartbeat > HEARTBEAT_TIMEOUT * 2:
                    break

                msg = master.recv_match(blocking=True, timeout=0.05)

                if msg:
                    mtype = msg.get_type()

                    if mtype == 'HEARTBEAT':
                        last_heartbeat = time.time()
                        tel["armed"] = bool(
                            msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
                        )
                        tel["mode"] = COPTER_MODES.get(msg.custom_mode, f"MODE_{msg.custom_mode}")

                    elif mtype == 'GLOBAL_POSITION_INT':
                        tel["lat"]     = msg.lat / 1e7
                        tel["lon"]     = msg.lon / 1e7
                        tel["alt_msl"] = msg.alt / 1000.0

                        current_agl = msg.relative_alt / 1000.0

                        # AGL calibration + low-pass filter
                        if time.time() - start_time < 10:
                            tel["alt_agl"] = current_agl
                        else:
                            if ground_alt is None and tel["ground_speed"] < 0.1:
                                ground_alt = current_agl
                            corrected = current_agl - (ground_alt or 0)
                            if tel["alt_agl"] == 0.0:
                                tel["alt_agl"] = corrected
                            else:
                                tel["alt_agl"] = alpha * tel["alt_agl"] + (1 - alpha) * corrected

                        vx = msg.vx / 100.0
                        vy = msg.vy / 100.0
                        vz = msg.vz / 100.0
                        tel["vx"] = vx
                        tel["vy"] = vy
                        tel["vz"] = vz
                        tel["ground_speed"] = math.sqrt(vx**2 + vy**2)

                    elif mtype == 'ATTITUDE':
                        # Convert radians → degrees
                        tel["roll"]  = math.degrees(msg.roll)
                        tel["pitch"] = math.degrees(msg.pitch)
                        tel["yaw"]   = math.degrees(msg.yaw)

                        heading_body = math.degrees(msg.yaw)
                        if heading_body < 0:
                            heading_body += 360
                        tel["heading_body"] = heading_body

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
                            # Estimate % for 6S (22.2 V nominal, 25.2 V full, 19 V empty)
                            tel["battery_pct"] = max(0.0, min(100.0, ((v - 19) / (25.2 - 19)) * 100))

                    elif mtype == 'SYS_STATUS':
                        if tel["battery_voltage"] == 0 and msg.voltage_battery not in (0, 65535):
                            v = msg.voltage_battery / 1000.0
                            tel["battery_voltage"] = v
                            tel["battery_pct"]     = max(0.0, min(100.0, ((v - 19) / (25.2 - 19)) * 100))

                    elif mtype == 'SYSTEM_TIME':
                        if msg.time_unix_usec > 0:
                            gps_time = msg.time_unix_usec / 1e6

                            # Smooth time offset between GPS and system clock
                            new_offset = gps_time - system_time
                            if time_offset is None:
                                time_offset = new_offset
                            else:
                                time_offset = 0.7 * time_offset + 0.3 * new_offset

                            tel["time_sync_error_sec"] = round(system_time - gps_time, 6)

                            gps_dt_utc = datetime.fromtimestamp(gps_time, timezone.utc)
                            tel["gps_datetime_utc"] = gps_dt_utc.strftime('%Y-%m-%d %H:%M:%S')
                            tel["gps_datetime_ist"] = (gps_dt_utc + IST_OFFSET).strftime('%Y-%m-%d %H:%M:%S')

                # ── Send at 10 Hz ──────────────────────────────────────────────
                now = time.time()
                if now - last_send >= SEND_INTERVAL and tel["lat"] != 0.0:
                    send(tel)
                    last_send = now

            except KeyboardInterrupt:
                sock.close()
                sys.exit(0)
            except Exception:
                break

        time.sleep(RECONNECT_DELAY)

if __name__ == '__main__':
    run_bridge()
