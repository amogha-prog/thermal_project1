import socket
import json
from pymavlink import mavutil
import time

# Bridge configuration
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
tios_addr = ("127.0.0.1", 14555)

def connect_drone():
    while True:
        try:
            print(f"WAITING: Searching for Drone heartbeat on port 14550...")
            master = mavutil.mavlink_connection('udpin:0.0.0.0:14550')
            # Wait for heartbeat with a 5-second timeout
            master.wait_heartbeat(timeout=5)
            print("SUCCESS: Connected! Forwarding to TIOS Dashboard on port 14555...")
            return master
        except Exception:
            print("OFFLINE: No drone detected. Retrying in 5 seconds...")
            time.sleep(5)

master = connect_drone()

telemetry = {
    "lat": 0,
    "lon": 0,
    "alt": 0,
    "roll": 0,
    "pitch": 0,
    "yaw": 0,
    "battery_voltage": 0,
    "speed": 0,
    "climb": 0,
    "armed": False,
    "mode": 0,
    "satellites": 0,
    "fix_type": 0
}

while True:
    msg = master.recv_match(blocking=True)
    if not msg:
        continue
    
    mtype = msg.get_type()

    if mtype == 'GLOBAL_POSITION_INT':
        telemetry["lat"] = msg.lat / 1e7
        telemetry["lon"] = msg.lon / 1e7
        telemetry["alt"] = msg.relative_alt / 1000
    elif mtype == 'ATTITUDE':
        telemetry["roll"] = msg.roll
        telemetry["pitch"] = msg.pitch
        telemetry["yaw"] = msg.yaw
    elif mtype == 'VFR_HUD':
        telemetry["speed"] = msg.groundspeed
        telemetry["climb"] = msg.climb
    elif mtype == 'BATTERY_STATUS':
        if msg.voltages[0] != 65535:
            telemetry["battery_voltage"] = msg.voltages[0] / 1000.0
    elif mtype == 'HEARTBEAT':
        telemetry["armed"] = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        telemetry["mode"] = msg.custom_mode
    elif mtype == 'GPS_RAW_INT':
        telemetry["satellites"] = msg.satellites_visible
        telemetry["fix_type"] = msg.fix_type

    # Forward data as soon as we have a position update
    if mtype == 'GLOBAL_POSITION_INT':
        try:
            sock.sendto(json.dumps(telemetry).encode(), tios_addr)
        except Exception as e:
            print(f"Error forwarding data: {e}")
