import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    sock.bind(("0.0.0.0", 14550))
    print("Bound to 14550 successfully. Waiting for packets...")
    sock.settimeout(5.0)
    data, addr = sock.recvfrom(1024)
    print(f"Received {len(data)} bytes from {addr}!")
except socket.timeout:
    print("No packets received on 14550 in 5 seconds.")
except OSError as e:
    print(f"Failed to bind: {e}")
except Exception as e:
    print(f"Error: {e}")
finally:
    sock.close()
