"""
drone_bridge.py — MAVLink → TIOS UDP Bridge
---------------------------------------------
Reads real MAVLink telemetry forwarded by Mission Planner / QGroundControl
on UDP port 14550, converts it to JSON, and forwards it to the TIOS backend
on UDP port 14555.

Run:
    python drone_bridge.py

Requirements:
    pip install pymavlink
"""

import socket
import json
import time
import sys
from pymavlink import mavutil

# ── Config ────────────────────────────────────────────────────────────────────
MAVLINK_LISTEN  = 'udpin:0.0.0.0:14550'   # Where MP/QGC sends MAVLink
TIOS_HOST       = '127.0.0.1'             # TIOS backend host
TIOS_PORT       = 14555                   # TIOS backend UDP port
HEARTBEAT_TIMEOUT = 8                     # Seconds before declaring link lost
RECONNECT_DELAY   = 5                     # Seconds between reconnect attempts

# ── UDP socket to TIOS backend ────────────────────────────────────────────────
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
tios_addr = (TIOS_HOST, TIOS_PORT)

def fresh_telemetry():
    return {
        "lat": 0, "lon": 0, "alt": 0,
        "roll": 0, "pitch": 0, "yaw": 0,
        "battery_voltage": 0,
        "speed": 0, "climb": 0,
        "armed": False, "mode": 0,
        "satellites": 0, "fix_type": 0
    }

def send(telemetry):
    try:
        sock.sendto(json.dumps(telemetry).encode(), tios_addr)
    except Exception as e:
        print(f"[Bridge] Send error: {e}")

def run_bridge():
    """Main bridge loop with automatic reconnection."""
    while True:
        master = None
        telemetry = fresh_telemetry()
        
        # ── Connect ──────────────────────────────────────────────────────────
        try:
            print(f"\n[Bridge] Waiting for MAVLink heartbeat on port 14550...")
            master = mavutil.mavlink_connection(MAVLINK_LISTEN)
            master.wait_heartbeat(timeout=HEARTBEAT_TIMEOUT)
            sysid  = master.target_system
            compid = master.target_component
            print(f"[Bridge] ✓ Connected! SysID={sysid} CompID={compid}")
            print(f"[Bridge] Forwarding telemetry → {TIOS_HOST}:{TIOS_PORT}\n")
        except Exception as e:
            print(f"[Bridge] ✗ No drone detected ({e}). Retrying in {RECONNECT_DELAY}s...")
            time.sleep(RECONNECT_DELAY)
            continue

        # ── Receive loop ──────────────────────────────────────────────────────
        last_heartbeat = time.time()
        while True:
            try:
                msg = master.recv_match(blocking=True, timeout=2)
                
                # ── Link watchdog: if no heartbeat for N seconds, reconnect ──
                if time.time() - last_heartbeat > HEARTBEAT_TIMEOUT * 2:
                    print("[Bridge] ✗ Link lost (heartbeat timeout). Reconnecting...")
                    break

                if not msg:
                    continue

                mtype = msg.get_type()

                if mtype == 'HEARTBEAT':
                    last_heartbeat = time.time()
                    telemetry["armed"] = bool(
                        msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
                    )
                    telemetry["mode"] = msg.custom_mode

                elif mtype == 'GLOBAL_POSITION_INT':
                    telemetry["lat"] = msg.lat / 1e7
                    telemetry["lon"] = msg.lon / 1e7
                    telemetry["alt"] = msg.relative_alt / 1000.0
                    # Send on every GPS update (10 Hz)
                    send(telemetry)

                elif mtype == 'ATTITUDE':
                    telemetry["roll"]  = msg.roll    # radians — backend converts
                    telemetry["pitch"] = msg.pitch
                    telemetry["yaw"]   = msg.yaw

                elif mtype == 'VFR_HUD':
                    telemetry["speed"] = msg.groundspeed
                    telemetry["climb"] = msg.climb

                elif mtype == 'BATTERY_STATUS':
                    if msg.voltages and msg.voltages[0] != 65535:
                        telemetry["battery_voltage"] = msg.voltages[0] / 1000.0

                elif mtype == 'SYS_STATUS':
                    # Fallback voltage from SYS_STATUS if BATTERY_STATUS not available
                    if telemetry["battery_voltage"] == 0 and msg.voltage_battery != 65535:
                        telemetry["battery_voltage"] = msg.voltage_battery / 1000.0

                elif mtype == 'GPS_RAW_INT':
                    telemetry["satellites"] = msg.satellites_visible
                    telemetry["fix_type"]   = msg.fix_type

            except KeyboardInterrupt:
                print("\n[Bridge] Stopped by user.")
                sock.close()
                sys.exit(0)
            except Exception as e:
                print(f"[Bridge] Receive error: {e}. Reconnecting...")
                break

        # Small pause before reconnect attempt
        time.sleep(RECONNECT_DELAY)

if __name__ == '__main__':
    print("=" * 50)
    print("  TIOS MAVLink Bridge")
    print("  MAVLink UDP:14550  →  TIOS UDP:14555")
    print("  Press Ctrl+C to stop")
    print("=" * 50)
    run_bridge()
