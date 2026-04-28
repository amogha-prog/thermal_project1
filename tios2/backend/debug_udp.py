import socket

def debug_udp():
    PORT = 14555
    # Bind to 0.0.0.0 (all interfaces)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    try:
        sock.bind(('0.0.0.0', PORT))
        print(f"=== Raw UDP Sniffer ===")
        print(f"Listening for ANY data on port {PORT}...")
        print("If no data appears here, the data is not reaching your computer.")
        
        sock.settimeout(10.0) # 10 second wait
        
        while True:
            try:
                data, addr = sock.recvfrom(2048)
                print(f"[{addr}] Received {len(data)} bytes: {data[:20].hex()}...")
            except socket.timeout:
                print("--- Still waiting for data (nothing received in 10s) ---")
                
    except Exception as e:
        print(f"Error binding to port {PORT}: {e}")
        print("Check if another program (like the drone_bridge) is already using this port.")
    finally:
        sock.close()

if __name__ == "__main__":
    debug_udp()
