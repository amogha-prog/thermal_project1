import socket
import time

def raw_sniff():
    print("Binding to 0.0.0.0:14550...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 14550))
    
    print("Sending pings to 192.168.144.10...")
    for _ in range(3):
        sock.sendto(b'WakeUp\x00', ("192.168.144.10", 14550))
        time.sleep(1)
        
    print("Listening for packets...")
    sock.settimeout(5)
    try:
        data, addr = sock.recvfrom(1024)
        print(f"SUCCESS! Received {len(data)} bytes from {addr}")
        print(f"Bytes (hex): {data[:20].hex()}")
    except socket.timeout:
        print("FAILED: No packets received.")
    finally:
        sock.close()

if __name__ == "__main__":
    raw_sniff()
