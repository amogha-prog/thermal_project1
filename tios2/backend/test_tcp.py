import socket
import time

def test_tcp(ip, port):
    print(f"Attempting to connect to {ip}:{port} via TCP...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    try:
        sock.connect((ip, port))
        print(f"SUCCESS! Connected to {ip}:{port} (TCP)")
        print("Waiting for data...")
        data = sock.recv(1024)
        print(f"Received {len(data)} bytes")
        print(f"Hex: {data[:20].hex()}")
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False
    finally:
        sock.close()

if __name__ == "__main__":
    test_tcp("192.168.144.10", 8520)
    test_tcp("192.168.144.11", 8520)
