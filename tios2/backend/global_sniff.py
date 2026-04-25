import socket
import struct

def capture_ethernet():
    print("Sniffing all UDP traffic on Ethernet adapter (192.168.144.200)...")
    # On Windows, to sniff all UDP, we can use a raw socket if we have admin
    # Or just bind to multiple common ports
    ports = [14550, 14551, 14555, 14556, 18570, 8001]
    socks = []
    for p in ports:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.bind(("0.0.0.0", p))
            s.settimeout(2)
            socks.append((s, p))
            print(f"Listening on port {p}")
        except:
            print(f"Could not bind to port {p}")

    print("\nSending 'WakeUp' to drone IPs...")
    pinger = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for ip in ["192.168.144.10", "192.168.144.11"]:
        for p in [14550, 14555]:
            pinger.sendto(b'WakeUp\x00', (ip, p))
    
    print("\nWaiting for any data (10 seconds)...")
    start = time.time()
    import time
    while time.time() - start < 10:
        for s, p in socks:
            try:
                data, addr = s.recvfrom(1024)
                print(f"!!! RECEIVED on Port {p} from {addr}: {data[:16].hex()}")
            except socket.timeout:
                pass
    
    for s, p in socks: s.close()

if __name__ == "__main__":
    capture_ethernet()
