"""
TIOS GPS MAVLink Bridge — Flight Controller Telemetry

Connects to the drone's flight controller via MAVLink (UDP or serial)
and sends parsed telemetry as JSON to the TIOS Node.js backend
on port 14555 via UDP.

This bridges the Python/MAVLink world with the Node.js/Socket.io world.

Usage:
    python gps_mavlink.py                     # Uses UDP port 14550
    python gps_mavlink.py --serial COM3       # Uses serial port
    python gps_mavlink.py --target-port 14555 # Sends to custom port
"""

import os
os.environ['MAVLINK20'] = '1'
import json
import math
import time
import socket
import logging
import argparse
import threading
from typing import Optional

logger = logging.getLogger(__name__)


# ArduPilot Copter Flight Modes
COPTER_MODES = {
    0: "STABILIZE", 1: "ACRO", 2: "ALT_HOLD", 3: "AUTO",
    4: "GUIDED", 5: "LOITER", 6: "RTL", 7: "CIRCLE",
    8: "POSITION", 9: "LAND", 10: "OF_LOITER", 11: "DRIFT",
    13: "SPORT", 14: "FLIP", 15: "AUTOTUNE", 16: "POSHOLD",
    17: "BRAKE", 18: "THROW", 19: "AVOID_ADSB", 20: "GUIDED_NOGPS",
    21: "SMART_RTL", 22: "FLOWHOLD", 23: "FOLLOW", 24: "ZIGZAG",
    25: "SYSTEMID", 26: "AUTOROTATE", 27: "AUTO_RTL",
}


class MAVLinkBridge:
    """
    Bridges MAVLink telemetry from the flight controller to the Node.js backend.
    
    Parses key MAVLink messages:
    - GLOBAL_POSITION_INT: GPS coordinates, altitude
    - ATTITUDE: Roll, pitch, yaw
    - VFR_HUD: Speed, climb rate, heading
    - SYS_STATUS: Battery voltage, current
    - BATTERY_STATUS: Detailed battery info
    - HEARTBEAT: Armed state, flight mode
    - GPS_RAW_INT: Satellite count, fix type
    """

    def __init__(
        self,
        mavlink_host: str = "0.0.0.0",
        mavlink_port: int = 14550,
        serial_port: Optional[str] = None,
        baud_rate: int = 57600,
        target_host: str = "127.0.0.1",
        target_port: int = 14555,
        send_rate: float = 10.0,  # Hz
    ):
        self.mavlink_host = mavlink_host
        self.mavlink_port = mavlink_port
        self.serial_port = serial_port
        self.baud_rate = baud_rate
        self.target_host = target_host
        self.target_port = target_port
        self.send_rate = send_rate

        self._running = False
        self._connected = False
        self._target_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Telemetry state
        self.telemetry = {
            "lat": 0.0, "lon": 0.0,
            "alt": 0.0, "relative_alt": 0.0,
            "speed": 0.0, "climb": 0.0,
            "heading": 0,
            "roll": 0.0, "pitch": 0.0, "yaw": 0.0,
            "battery_voltage": 0.0, "battery_remaining": 0,
            "current": 0.0,
            "armed": False,
            "mode": 0,
            "fix_type": 0, "satellites": 0,
        }

    def _send_to_backend(self):
        """Send current telemetry as JSON to Node.js backend via UDP."""
        try:
            msg = json.dumps(self.telemetry).encode("utf-8")
            self._target_socket.sendto(msg, (self.target_host, self.target_port))
        except Exception as e:
            logger.error(f"[MAVLink] Send error: {e}")

    def _run_udp(self):
        """Connect via UDP and parse MAVLink messages."""
        try:
            from pymavlink import mavutil
        except ImportError:
            logger.error("[MAVLink] pymavlink not installed. Run: pip install pymavlink")
            return

        connection_str = f"udpin:{self.mavlink_host}:{self.mavlink_port}"
        logger.info(f"[MAVLink] Connecting UDP: {connection_str}")

        try:
            self.mav_connection = mavutil.mavlink_connection(connection_str)
            mav = self.mav_connection
            logger.info("[MAVLink] Waiting for heartbeat...")
            mav.wait_heartbeat(timeout=30)
            logger.info(f"[MAVLink] Connected! System {mav.target_system}, Component {mav.target_component}")
            self._connected = True
        except Exception as e:
            logger.error(f"[MAVLink] Connection failed: {e}")
            return

        self._parse_loop(mav)

    def _run_serial(self):
        """Connect via serial port and parse MAVLink messages."""
        try:
            from pymavlink import mavutil
        except ImportError:
            logger.error("[MAVLink] pymavlink not installed. Run: pip install pymavlink")
            return

        connection_str = self.serial_port
        logger.info(f"[MAVLink] Connecting Serial: {connection_str} @ {self.baud_rate}")

        try:
            mav = mavutil.mavlink_connection(connection_str, baud=self.baud_rate)
            logger.info("[MAVLink] Waiting for heartbeat...")
            mav.wait_heartbeat(timeout=30)
            logger.info(f"[MAVLink] Connected! System {mav.target_system}")
            self._connected = True
        except Exception as e:
            logger.error(f"[MAVLink] Serial connection failed: {e}")
            return

        self._parse_loop(mav)

    def _parse_loop(self, mav):
        """Main parsing loop — reads MAVLink messages and updates telemetry."""
        send_interval = 1.0 / self.send_rate
        last_send = 0

        while self._running:
            try:
                msg = mav.recv_match(blocking=True, timeout=1.0)
                if msg is None:
                    continue

                msg_type = msg.get_type()

                if msg_type == "GLOBAL_POSITION_INT":
                    self.telemetry["lat"] = msg.lat / 1e7
                    self.telemetry["lon"] = msg.lon / 1e7
                    self.telemetry["alt"] = msg.relative_alt / 1000.0
                    self.telemetry["relative_alt"] = msg.relative_alt / 1000.0

                elif msg_type == "ATTITUDE":
                    self.telemetry["roll"] = msg.roll
                    self.telemetry["pitch"] = msg.pitch
                    self.telemetry["yaw"] = msg.yaw

                elif msg_type == "VFR_HUD":
                    self.telemetry["speed"] = msg.groundspeed
                    self.telemetry["climb"] = msg.climb
                    self.telemetry["heading"] = msg.heading

                elif msg_type == "SYS_STATUS":
                    self.telemetry["battery_voltage"] = msg.voltage_battery / 1000.0
                    self.telemetry["current"] = msg.current_battery / 100.0
                    self.telemetry["battery_remaining"] = msg.battery_remaining

                elif msg_type == "BATTERY_STATUS":
                    if msg.voltages[0] != 65535:
                        self.telemetry["battery_voltage"] = msg.voltages[0] / 1000.0

                elif msg_type == "HEARTBEAT":
                    self.telemetry["armed"] = bool(msg.base_mode & 128)
                    self.telemetry["mode"] = msg.custom_mode

                elif msg_type == "GPS_RAW_INT":
                    self.telemetry["fix_type"] = msg.fix_type
                    self.telemetry["satellites"] = msg.satellites_visible

                # Send to backend at configured rate
                now = time.time()
                if now - last_send >= send_interval:
                    self._send_to_backend()
                    last_send = now

            except Exception as e:
                logger.error(f"[MAVLink] Parse error: {e}")
                time.sleep(0.1)

    def start(self):
        """Start the MAVLink bridge in a background thread."""
        self._running = True
        if self.serial_port:
            thread = threading.Thread(target=self._run_serial, daemon=True, name="mavlink-serial")
        else:
            thread = threading.Thread(target=self._run_udp, daemon=True, name="mavlink-udp")
        thread.start()
        logger.info("[MAVLink] Bridge started")
        
        # SIYI/Herelink wakeup ping logic — MUST send from the same port we listen on
        def wakeup_pings():
            while self._running:
                if hasattr(self, 'mav_connection') and self.mav_connection.port:
                    try:
                        # Pack a real MAVLink GCS Heartbeat
                        # This is what Mission Planner sends to 'wake up' the telemetry stream
                        hb = self.mav_connection.mav.heartbeat_encode(
                            mavutil.mavlink.MAV_TYPE_GCS, 
                            mavutil.mavlink.MAV_AUTOPILOT_INVALID, 
                            0, 0, 0
                        )
                        ping_data = hb.pack(self.mav_connection.mav)
                        
                        sock = self.mav_connection.port
                        # Target the actual drone IP discovered (192.168.144.10)
                        for ip in ["192.168.144.10", "192.168.144.11", "192.168.144.12"]:
                            for p in [14550, 14555]:
                                try:
                                    # 1. Send Heartbeat (to tell router we are here)
                                    sock.sendto(ping_data, (ip, p))
                                    
                                    # 2. Send Request Data Stream (to tell FC to send data)
                                    # Target system/comp 1,1 is usually safe for ArduPilot/PX4
                                    req = self.mav_connection.mav.request_data_stream_encode(
                                        1, 1, 
                                        mavutil.mavlink.MAV_DATA_STREAM_ALL,
                                        10, 1 # 10 Hz, Start
                                    )
                                    sock.sendto(req.pack(self.mav_connection.mav), (ip, p))
                                except: pass
                        try:
                            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                            for p in [14550, 14555]:
                                sock.sendto(ping_data, ("255.255.255.255", p))
                        except: pass
                    except Exception as e:
                        logger.debug(f"Ping error: {e}")
                time.sleep(5)

        pinger = threading.Thread(target=wakeup_pings, daemon=True, name="mavlink-pinger")
        pinger.start()

        # Also start the periodic sender (ensures data flows even between MAVLink messages)
        def periodic_send():
            while self._running:
                self._send_to_backend()
                time.sleep(1.0 / self.send_rate)

        sender = threading.Thread(target=periodic_send, daemon=True, name="mavlink-sender")
        sender.start()

    def stop(self):
        """Stop the bridge."""
        self._running = False
        self._connected = False
        logger.info("[MAVLink] Bridge stopped")

    def get_status(self) -> dict:
        """Return bridge status."""
        return {
            "connected": self._connected,
            "running": self._running,
            "mode": COPTER_MODES.get(self.telemetry["mode"], f"MODE_{self.telemetry['mode']}"),
            "armed": self.telemetry["armed"],
            "lat": self.telemetry["lat"],
            "lon": self.telemetry["lon"],
            "alt": self.telemetry["alt"],
            "satellites": self.telemetry["satellites"],
            "voltage": self.telemetry["battery_voltage"],
        }


def main():
    parser = argparse.ArgumentParser(description="TIOS MAVLink Bridge")
    parser.add_argument("--host", default="0.0.0.0", help="MAVLink listen host")
    parser.add_argument("--port", type=int, default=14550, help="MAVLink UDP port")
    parser.add_argument("--serial", default=None, help="Serial port (e.g. COM3, /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=57600, help="Serial baud rate")
    parser.add_argument("--target-host", default="127.0.0.1", help="Node.js backend host")
    parser.add_argument("--target-port", type=int, default=14555, help="Node.js backend UDP port")
    parser.add_argument("--rate", type=float, default=10.0, help="Send rate in Hz")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
    )

    bridge = MAVLinkBridge(
        mavlink_host=args.host,
        mavlink_port=args.port,
        serial_port=args.serial,
        baud_rate=args.baud,
        target_host=args.target_host,
        target_port=args.target_port,
        send_rate=args.rate,
    )

    bridge.start()

    try:
        while True:
            time.sleep(5)
            status = bridge.get_status()
            logger.info(f"[Status] {status['mode']} | Armed: {status['armed']} | "
                        f"GPS: {status['lat']:.6f},{status['lon']:.6f} | "
                        f"Alt: {status['alt']:.1f}m | Sats: {status['satellites']} | "
                        f"Voltage: {status['voltage']:.1f}V")
    except KeyboardInterrupt:
        bridge.stop()
        print("\n[MAVLink] Bridge shutdown complete")


if __name__ == "__main__":
    main()
