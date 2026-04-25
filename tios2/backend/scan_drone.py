import socket
import threading

DRONE_IP = '192.168.144.11'
PORTS = [14550, 14551, 14552, 5760, 5761, 8520, 18570]
TIMEOUT = 5

results = []

def listen_udp(port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', port))
        s.settimeout(TIMEOUT)
        data, addr = s.recvfrom(4096)
        results.append("[OK]  UDP:%d  <- got %d bytes from %s:%d" % (port, len(data), addr[0], addr[1]))
        s.close()
    except socket.timeout:
        results.append("[--]  UDP:%d  -- no data (timeout)" % port)
    except OSError as e:
        results.append("[!!]  UDP:%d  -- %s" % (port, e))

print("Listening on UDP ports %s for %ds each...\n" % (PORTS, TIMEOUT))

threads = [threading.Thread(target=listen_udp, args=(p,)) for p in PORTS]
for t in threads:
    t.start()
for t in threads:
    t.join()

print("\n-- UDP Results --")
for r in results:
    print(r)

print("\n-- TCP Quick Check --")
for port in [8520, 5760, 5761, 14550]:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect((DRONE_IP, port))
        print("[OK]  TCP:%d  <- OPEN!" % port)
        s.close()
    except Exception as e:
        print("[--]  TCP:%d  <- %s: %s" % (port, type(e).__name__, e))
