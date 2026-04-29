"""
drone_bridge.py — SkyDroid H12 MAVLink -> TIOS Telemetry Bridge
----------------------------------------------------------------
Architecture:
  1. GPS time tags every incoming telemetry packet (lat, lon, alt, heading)
     and stores them in a rolling TelemetryBuffer.
  2. System time (time.time()) tags every photo capture.
  3. At capture time, forward/backward interpolation finds the closest
     telemetry points and blends them to produce a precise GPS location
     for the exact capture instant.
  4. The GPS<->System clock offset is tracked via a stable monotonic
     reference so the Sync Δ converges to <100ms.

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
import threading
import collections
from datetime import datetime, timedelta, timezone
from pymavlink import mavutil

# ── Config ────────────────────────────────────────────────────────────────────
SKYDROID_IP   = '192.168.144.11'
TIOS_HOST     = '127.0.0.1'
TIOS_PORT     = 14556
GEOTAG_PORT   = 14557        # UDP query port for geotag requests from auto_capture
SEND_HZ       = 10
SEND_INTERVAL = 1.0 / SEND_HZ
HB_TIMEOUT    = 20
RECONNECT     = 3
BUFFER_SIZE   = 200     # rolling buffer: ~20 seconds at 10 Hz

IST_OFFSET = timedelta(hours=5, minutes=30)

SOURCES = [
    'udpin:0.0.0.0:14555',
    'udpin:0.0.0.0:14550',
]

# ── TIOS output socket ────────────────────────────────────────────────────────
tios_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
tios_addr = (TIOS_HOST, TIOS_PORT)


# ── Telemetry Buffer ──────────────────────────────────────────────────────────
class TelemetryBuffer:
    """
    Stores timestamped telemetry snapshots tagged with GPS time.
    Used for forward/backward interpolation at capture time.
    
    Each entry: { 'gps_t': float, 'lat': float, 'lon': float,
                  'alt_msl': float, 'alt_agl': float,
                  'heading': float, 'roll': float, 'pitch': float,
                  'ground_speed': float }
    """
    def __init__(self, maxlen=BUFFER_SIZE):
        self._buf = collections.deque(maxlen=maxlen)

    def push(self, gps_t: float, snapshot: dict):
        self._buf.append({'gps_t': gps_t, **snapshot})

    def interpolate(self, query_gps_t: float) -> dict:
        """
        Forward/backward interpolation.
        Finds the two entries surrounding query_gps_t and linearly
        interpolates all numeric fields. If only one side is available,
        uses the nearest single point (extrapolation limit = 1.0s).
        """
        buf = list(self._buf)
        if not buf:
            return {}

        # Find surrounding pair
        before = None
        after  = None
        for entry in buf:
            if entry['gps_t'] <= query_gps_t:
                before = entry
            elif entry['gps_t'] > query_gps_t and after is None:
                after = entry
                break

        if before is None and after is None:
            return {}

        # If we have both, interpolate. If only one, use nearest if within 1s.
        if before is None:
            return after if abs(after['gps_t'] - query_gps_t) < 1.0 else {}
        if after is None:
            return before if abs(before['gps_t'] - query_gps_t) < 1.0 else {}

        # Linear interpolation
        span = after['gps_t'] - before['gps_t']
        if span <= 0:
            return before

        t_frac = (query_gps_t - before['gps_t']) / span

        result = {}
        # Interpolate all numeric fields
        fields = [
            'lat', 'lon', 'alt_msl', 'alt_agl',
            'roll', 'pitch', 'heading', 'ground_speed',
            'vx', 'vy', 'vz', 'climb', 'heading_autopilot', 'cog',
            'battery_voltage', 'battery_pct'
        ]
        
        for f in fields:
            a = before.get(f)
            b = after.get(f)
            if a is None or b is None:
                result[f] = a if a is not None else b
                continue

            # Circular heading handling (0-360)
            if f in ['heading', 'heading_autopilot', 'cog']:
                diff = b - a
                if diff > 180:  diff -= 360
                if diff < -180: diff += 360
                val = (a + diff * t_frac) % 360
            else:
                val = a + (b - a) * t_frac
            
            # Precision formatting
            if f in ['lat', 'lon']:
                result[f] = round(val, 7)
            else:
                result[f] = round(val, 3)

        result['interp_frac'] = round(t_frac, 4)
        result['before_gps_t'] = before['gps_t']
        result['after_gps_t']  = after['gps_t']
        return result

    def nearest(self, query_gps_t: float) -> dict:
        """Fallback: return the single nearest sample within 2.0s."""
        buf = list(self._buf)
        if not buf:
            return {}
        best = min(buf, key=lambda e: abs(e['gps_t'] - query_gps_t))
        if abs(best['gps_t'] - query_gps_t) > 2.0:
            return {}
        return best


# Global buffer — accessible by the capture handler
tel_buffer = TelemetryBuffer()


# ── Time synchronization ──────────────────────────────────────────────────────
class TimeSync:
    """
    Tracks the GPS<->monotonic offset using a Kalman-style filter.
    Provides stable conversion between system monotonic time and GPS time.
    """
    def __init__(self):
        self._offset      = None   # gps_unix - mono_now
        self._boot_offset = None   # gps_unix - drone_boot_ms/1000
        self._offset_var  = 1e6    # variance
        self._proc_noise  = 1e-6

    def update(self, gps_unix: float, mono_now: float, boot_ms: float = None):
        raw_offset = gps_unix - mono_now
        
        if boot_ms is not None:
            self._boot_offset = gps_unix - (boot_ms / 1000.0)

        if self._offset is None:
            self._offset     = raw_offset
            self._offset_var = 0.001
            return

        # Kalman update
        self._offset_var += self._proc_noise
        meas_noise = 0.010   # 10ms jitter tolerance
        K = self._offset_var / (self._offset_var + meas_noise)
        innovation = raw_offset - self._offset

        if abs(innovation) > 1.0:
            self._offset     = raw_offset
            self._offset_var = 0.001
        else:
            self._offset     = self._offset + K * innovation
            self._offset_var = (1 - K) * self._offset_var

    def mono_to_gps(self, mono: float) -> float:
        """Convert ground monotonic timestamp to GPS unix time."""
        if self._offset is None:
            return time.time()
        return mono + self._offset

    def boot_to_gps(self, boot_ms: float) -> float:
        """Convert drone boot_ms to GPS unix time (more stable)."""
        if self._boot_offset is None:
            return self.gps_now()
        return (boot_ms / 1000.0) + self._boot_offset

    def gps_now(self) -> float:
        """Best estimate of GPS unix time right now on ground."""
        return self.mono_to_gps(time.monotonic())

    def wall_to_gps(self, wall_t: float) -> float:
        """Convert system wall time to GPS time by bridging via current monotonic time."""
        # wall_t - time.time() is the delta to now.
        # gps_now() + (wall_t - time.time()) is the estimated gps time of wall_t
        return self.gps_now() + (wall_t - time.time())

    @property
    def offset(self):
        return self._offset


time_sync = TimeSync()


# ── Capture geo-tagger ────────────────────────────────────────────────────────
def geotagged_capture(capture_sys_t: float) -> dict:
    """
    Given the system time of a capture event, return interpolated
    GPS location data.

    Steps:
      1. Convert capture system time -> GPS time using time_sync.
      2. Interpolate telemetry buffer at that GPS time.
      3. Return merged result.
    """
    capture_gps_t = time_sync.wall_to_gps(capture_sys_t)

    # Try interpolation first
    interp = tel_buffer.interpolate(capture_gps_t)
    if not interp:
        # Fallback to nearest sample
        interp = tel_buffer.nearest(capture_gps_t)

    capture_dt = datetime.fromtimestamp(capture_sys_t, timezone.utc)
    gps_dt     = datetime.fromtimestamp(capture_gps_t, timezone.utc)

    return {
        'capture_system_time_utc': capture_dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
        'capture_system_time_ist': (capture_dt + IST_OFFSET).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
        'capture_gps_time_utc':    gps_dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
        'capture_gps_time_ist':    (gps_dt + IST_OFFSET).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
        'sync_offset_sec':         round(time_sync.offset or 0, 4),
        **interp
    }


# ── Geotag query server ──────────────────────────────────────────────────────
def geotag_query_server():
    """
    Background UDP server that responds to geotag queries from auto_capture.py.
    
    Query format (JSON):
        {"type": "geotag_query", "sys_t": <float>}
    
    Response format (JSON):
        {"lat": .., "lon": .., "alt_msl": .., "alt_agl": .., "heading": ..,
         "roll": .., "pitch": .., "ground_speed": ..,
         "capture_gps_time_utc": .., "sync_offset_sec": ..,
         "interp_frac": .., "status": "ok" | "no_data"}
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('127.0.0.1', GEOTAG_PORT))
    sock.settimeout(1.0)
    print(f"[GeoTag] Query server listening on port {GEOTAG_PORT}")

    while True:
        try:
            data, addr = sock.recvfrom(256)
            req = json.loads(data.decode())
            if req.get('type') == 'geotag_query':
                sys_t  = float(req['sys_t'])
                result = geotagged_capture(sys_t)
                if result:
                    result['status'] = 'ok'
                else:
                    result = {'status': 'no_data'}
                sock.sendto(json.dumps(result).encode(), addr)
        except socket.timeout:
            continue
        except Exception as e:
            print(f"[GeoTag] Query error: {e}")


# ── Helpers ───────────────────────────────────────────────────────────────────
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
        "gps_datetime_utc": "", "gps_datetime_ist": "",
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
    except Exception as e:
        print(f"[{ts()}] {source} failed: {type(e).__name__}: {e}")
        return None


# ── Main loop ─────────────────────────────────────────────────────────────────
def run():
    source_idx = 0
    while True:
        source = SOURCES[source_idx % len(SOURCES)]
        master = try_connect(source)

        if master is None:
            source_idx += 1
            print(f"[{ts()}] Retrying in {RECONNECT}s ...")
            time.sleep(RECONNECT)
            continue

        tel        = fresh_telemetry()
        ground_alt = None
        alpha      = 0.9
        last_send  = 0
        last_hb    = time.monotonic()
        packets    = 0

        print(f"[{ts()}] Streaming telemetry -> {TIOS_HOST}:{TIOS_PORT} ...")

        while True:
            try:
                mono_now = time.monotonic()

                # System time display
                now_utc = datetime.now(timezone.utc)
                tel["system_datetime_utc"] = now_utc.strftime('%Y-%m-%d %H:%M:%S')
                tel["system_datetime_ist"] = (now_utc + IST_OFFSET).strftime('%Y-%m-%d %H:%M:%S')

                # Heartbeat watchdog
                if mono_now - last_hb > HB_TIMEOUT * 2:
                    print(f"[{ts()}] Watchdog: lost heartbeat. Reconnecting...")
                    break

                msg = master.recv_match(blocking=True, timeout=0.05)
                if not msg:
                    continue

                mtype = msg.get_type()
                packets += 1

                # ── Current GPS time estimate ─────────────────────────────────────────
                # Use boot_ms if available for precise intra-packet timing
                msg_boot_ms = getattr(msg, 'time_boot_ms', None)
                if msg_boot_ms:
                    gps_t = time_sync.boot_to_gps(msg_boot_ms)
                else:
                    gps_t = time_sync.gps_now()

                if mtype == 'HEARTBEAT':
                    last_hb = mono_now
                    tel["armed"] = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                    tel["mode"]  = COPTER_MODES.get(msg.custom_mode, f"MODE_{msg.custom_mode}")

                elif mtype == 'GLOBAL_POSITION_INT':
                    tel["lat"]     = msg.lat / 1e7
                    tel["lon"]     = msg.lon / 1e7
                    tel["alt_msl"] = msg.alt / 1000.0

                    agl = msg.relative_alt / 1000.0
                    if mono_now - last_send < 10:
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

                    # Push detailed snapshot for interpolation
                    tel_buffer.push(gps_t, {
                        'lat':              tel["lat"],
                        'lon':              tel["lon"],
                        'alt_msl':          tel["alt_msl"],
                        'alt_agl':          tel["alt_agl"],
                        'vx':               tel["vx"],
                        'vy':               tel["vy"],
                        'vz':               tel["vz"],
                        'climb':            tel["climb"],
                        'ground_speed':     tel["ground_speed"],
                        'roll':             tel["roll"],
                        'pitch':            tel["pitch"],
                        'heading':          tel["heading_body"],
                        'heading_autopilot': tel["heading_autopilot"],
                        'cog':              tel["cog"],
                        'battery_voltage':  tel["battery_voltage"],
                        'battery_pct':      tel["battery_pct"],
                    })

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
                        gps_val = msg.time_unix_usec / 1e6
                        boot_val = msg.time_boot_ms
                        # Update sync between Ground Monotonic and Drone GPS
                        time_sync.update(gps_val, mono_now, boot_val)

                        # GPS time display
                        calc_gps_t = time_sync.gps_now()
                        tel["time_sync_error_sec"] = round(time.time() - calc_gps_t, 6)

                        gps_dt = datetime.fromtimestamp(calc_gps_t, timezone.utc)
                        tel["gps_datetime_utc"] = gps_dt.strftime('%Y-%m-%d %H:%M:%S')
                        tel["gps_datetime_ist"] = (gps_dt + IST_OFFSET).strftime('%Y-%m-%d %H:%M:%S')

                # ── Send at 10 Hz ─────────────────────────────────────────────
                now = time.monotonic()
                if now - last_send >= SEND_INTERVAL:
                    send_telemetry(tel)
                    last_send = now
                    if packets % 100 == 0:
                        sync = tel.get('time_sync_error_sec', 0) or 0
                        print(f"[{ts()}] OK | mode={tel['mode']} armed={tel['armed']} "
                              f"lat={tel['lat']:.5f} lon={tel['lon']:.5f} "
                              f"agl={tel['alt_agl']:.1f}m spd={tel['ground_speed']:.1f}m/s "
                              f"bat={tel['battery_voltage']:.1f}V sync={sync*1000:.0f}ms")

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
    print("  SkyDroid H12 MAVLink Bridge -> TIOS Telemetry")
    print(f"  Controller: {SKYDROID_IP}  |  Backend: {TIOS_HOST}:{TIOS_PORT}")
    print(f"  GeoTag Query: UDP 127.0.0.1:{GEOTAG_PORT}")
    print("=" * 60)

    # Start the geotag query server in a background daemon thread
    t = threading.Thread(target=geotag_query_server, daemon=True)
    t.start()

    run()
