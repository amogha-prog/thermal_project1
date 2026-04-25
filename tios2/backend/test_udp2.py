import socket
import time

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    sock.bind(("0.0.0.0", 14550))
    print("Bound to 14550. Sending a wake up ping to SIYI...")
    # Send a dummy packet to wake up the router
    sock.sendto(b'WakeUp\x00', ("192.168.144.11", 14550))
    sock.sendto(b'WakeUp\x00', ("192.168.144.12", 14550))
    
    # Now listen
    sock.settimeout(5.0)
    data, addr = sock.recvfrom(1024)
    print(f"SUCCESS! Received {len(data)} bytes from {addr}!")
except Exception as e:
    print(f"Error: {e}")
finally:
    sock.close()
