import socket
import time
from pymavlink import mavutil

def wake_drone():
    # H12 / SkyDroid typically uses these IPs
    target_ips = ["192.168.144.11", "192.168.144.10"]
    target_ports = [14550, 14555]
    
    print("=== SkyDroid MAVLink WakeUp Tool ===")
    print(f"Pinging IPs: {target_ips} on ports {target_ports}")
    
    # Create a MAVLink object to generate standard heartbeat packets
    # We use source_system=255 (standard for a ground station)
    mav = mavutil.mavlink_connection('udpout:127.0.0.1:0', source_system=255)
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Send Heartbeat and Request Data Stream multiple times
    for _ in range(5):
        for ip in target_ips:
            for port in target_ports:
                # 1. Send "WakeUp" text (some SkyDroid hardware looks for this)
                sock.sendto(b'WakeUp\x00', (ip, port))
                
                # 2. Send MAVLink Heartbeat (Standard)
                # type=GCS, autopilot=GENERIC
                msg = mav.mav.heartbeat_encode(
                    mavutil.mavlink.MAV_TYPE_GCS,
                    mavutil.mavlink.MAV_AUTOPILOT_GENERIC,
                    0, 0, 0
                )
                sock.sendto(msg.get_msgbuf(), (ip, port))
                
                # 3. Request Data Stream (Standard MAVLink)
                # Request all streams at 10Hz
                msg_stream = mav.mav.request_data_stream_encode(
                    1, 1, # target_system, target_component
                    mavutil.mavlink.MAV_DATA_STREAM_ALL,
                    10, # 10 Hz
                    1   # Start
                )
                sock.sendto(msg_stream.get_msgbuf(), (ip, port))
                
        print(".", end="", flush=True)
        time.sleep(1)
    
    print("\n\nWakeUp signals sent. Please check if telemetry is now appearing.")
    print("If not, ensure your SkyDroid H12 App -> 'UDP Output' is set to:")
    print("  IP: 192.168.144.200  Port: 14555")
    
    sock.close()

if __name__ == "__main__":
    wake_drone()
