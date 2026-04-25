import socket
import time

def wake_and_sniff(port):
    print(f"Waking up drone on port {port}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("0.0.0.0", port))
    
    ping = b'WakeUp\x00'
    # SIYI / Herelink often respond to heartbeats or just any packet
    for _ in range(5):
        sock.sendto(ping, ("192.168.144.11", 14550))
        sock.sendto(ping, ("192.168.144.12", 14550))
        sock.sendto(ping, ("255.255.255.255", 14550))
        time.sleep(1)

    print("Listening for 10 seconds...")
    sock.settimeout(10)
    try:
        while True:
            data, addr = sock.recvfrom(1024)
            print(f"RECEIVED: {len(data)} bytes from {addr}")
            if data[0] in [0xFE, 0xFD]:
                print(f"  MAVLink Version: {'2.0' if data[0] == 0xFD else '1.0'}")
    except socket.timeout:
        print("Done listening.")
    finally:
        sock.close()

if __name__ == "__main__":
    wake_and_sniff(14550)
