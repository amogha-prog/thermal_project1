from pymavlink import mavutil
import time

def test_conn(conn_str):
    print(f"Testing {conn_str}...")
    try:
        master = mavutil.mavlink_connection(conn_str)
        msg = master.wait_heartbeat(timeout=3.0)
        if msg:
            print(f"SUCCESS on {conn_str}!! Heartbeat received: {master.target_system}")
            return True
        else:
            print(f"Timeout on {conn_str}")
    except Exception as e:
        print(f"Error on {conn_str}: {e}")
    return False

test_conn('udpout:192.168.144.11:14550')
test_conn('udpout:192.168.144.12:14550')
test_conn('udpout:192.168.144.11:14552')
test_conn('udpout:192.168.144.108:14550')
