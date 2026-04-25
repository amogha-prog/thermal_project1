import socket
import sys

# ── Drone TCP source ────────────────────────────────────────────
DRONE_IP   = '192.168.144.11'
DRONE_PORT = 8520

# ── This laptop's IP (data will be forwarded here) ──────────────
TARGET_IP   = '192.168.144.200'
TARGET_PORT = 14550

# ────────────────────────────────────────────────────────────────
tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

try:
    print(f"🔌 Connecting to drone at TCP {DRONE_IP}:{DRONE_PORT} ...")
    tcp_sock.connect((DRONE_IP, DRONE_PORT))
    print(f"✅ Connected! Forwarding → UDP {TARGET_IP}:{TARGET_PORT}")
    print("   (Press Ctrl+C to stop)\n")

    while True:
        data = tcp_sock.recv(4096)
        if not data:
            print("⚠️  Connection closed by drone.")
            break
        udp_sock.sendto(data, (TARGET_IP, TARGET_PORT))

except ConnectionRefusedError:
    print("❌ Could not connect to drone. Is it powered on?")
    sys.exit(1)
except KeyboardInterrupt:
    print("\n🛑 Stopped.")
finally:
    tcp_sock.close()
    udp_sock.close()
