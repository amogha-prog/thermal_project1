import os
os.environ['MAVLINK20'] = '1'
from pymavlink import mavutil
import time

def debug_mav():
    print("Starting MAVLink debug sniffer on 14550...")
    # Try connecting to the specific drone IP actively
    master = mavutil.mavlink_connection('udpout:192.168.144.10:14550')
    
    print("Sending heartbeat to wake up drone...")
    master.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
    
    print("Waiting for messages...")
    start = time.time()
    while time.time() - start < 15:
        msg = master.recv_match(blocking=True, timeout=1.0)
        if msg:
            print(f"RECEIVED: {msg.get_type()}")
        else:
            # Try sending another heartbeat if nothing received
            master.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)

if __name__ == "__main__":
    debug_mav()
