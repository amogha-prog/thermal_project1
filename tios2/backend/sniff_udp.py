import socket
import time

def sniff(port):
    print(f"Sniffing on port {port} for 5 seconds...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5)
    try:
        sock.bind(("0.0.0.0", port))
        data, addr = sock.recvfrom(1024)
        print(f"SUCCESS! Received {len(data)} bytes from {addr} on port {port}")
        print(f"Hex: {data[:10].hex()}")
        return True
    except socket.timeout:
        print(f"Timeout on port {port}")
        return False
    except Exception as e:
        print(f"Error on port {port}: {e}")
        return False
    finally:
        sock.close()

if __name__ == "__main__":
    for p in [14550, 14555]:
        sniff(p)
