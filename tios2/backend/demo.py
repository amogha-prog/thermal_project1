from pymavlink import mavutil
import time
from datetime import datetime, timedelta, UTC


# IST offset
IST_OFFSET = timedelta(hours=5, minutes=30)


# Connect MAVLink (reads from drone_bridge.py local relay on :14556)
master = mavutil.mavlink_connection('udpin:0.0.0.0:14556')
master.wait_heartbeat()
print("Connected")


# Telemetry state
telemetry = {
    "lat": None,
    "lon": None,
    "alt": None,
    "alt_msl": None,
    "alt_agl": None,
    "vx": None,
    "vy": None,
    "vz": None,
    "ground_speed": None,
    "roll": None,
    "pitch": None,
    "yaw": None,
    "battery_voltage": None,
    "system_timestamp_utc": None,
    "system_datetime_utc": None,
    "system_datetime_ist": None,
    "gps_timestamp_utc": None,
    "gps_datetime_utc": None,
    "gps_datetime_ist": None,
    "heading_body": None,
    "heading_autopilot": None,
    "cog": None
}


time_offset = None
last_print = 0


# 🔥 NEW: for update rate check
prev_gps = None


# -------- ALTITUDE STABILIZATION --------
start_time = time.time()
ground_alt = None
alpha = 0.9


while True:


    # -------- SYSTEM TIME --------
    if time_offset is not None:
        system_time = time.time() + time_offset
    else:
        system_time = time.time()


    telemetry["system_timestamp_utc"] = system_time


    now_utc = datetime.now(UTC)
    telemetry["system_datetime_utc"] = now_utc.strftime('%Y-%m-%d %H:%M:%S')
    telemetry["system_datetime_ist"] = (now_utc + IST_OFFSET).strftime('%Y-%m-%d %H:%M:%S')


    # -------- MAVLINK READ --------
    msg = master.recv_match(blocking=True, timeout=0.05)


    if msg:
        msg_type = msg.get_type()


        if msg_type == 'GLOBAL_POSITION_INT':
            telemetry["lat"] = msg.lat / 1e7
            telemetry["lon"] = msg.lon / 1e7
            telemetry["alt_msl"] = msg.alt / 1000


            current_agl = msg.relative_alt / 1000


            # -------- STARTUP DELAY --------
            if time.time() - start_time < 10:
                telemetry["alt_agl"] = current_agl
            else:
                # -------- GROUND CALIBRATION --------
                if ground_alt is None and telemetry["ground_speed"] is not None:
                    if telemetry["ground_speed"] < 0.1:
                        ground_alt = current_agl


                # -------- APPLY CORRECTION --------
                if ground_alt is not None:
                    corrected_agl = current_agl - ground_alt
                else:
                    corrected_agl = current_agl


                # -------- LOW PASS FILTER --------
                if telemetry.get("alt_agl") is None:
                    telemetry["alt_agl"] = corrected_agl
                else:
                    telemetry["alt_agl"] = alpha * telemetry["alt_agl"] + (1 - alpha) * corrected_agl


            # -------- VELOCITY --------
            vx = msg.vx / 100
            vy = msg.vy / 100
            vz = msg.vz / 100


            telemetry["vx"] = vx
            telemetry["vy"] = vy
            telemetry["vz"] = vz


            telemetry["ground_speed"] = (vx**2 + vy**2) ** 0.5


        elif msg_type == 'ATTITUDE':
            telemetry["roll"] = msg.roll
            telemetry["pitch"] = msg.pitch
            telemetry["yaw"] = msg.yaw
            # -------- BODY HEADING --------
            heading_body = msg.yaw * (180 / 3.141592653589793)
            if heading_body < 0:
               heading_body += 360


            telemetry["heading_body"] = heading_body


        elif msg_type == 'BATTERY_STATUS':
            if msg.voltages[0] not in (0, 65535):
                telemetry["battery_voltage"] = msg.voltages[0] / 1000.0


        elif msg_type == 'GPS_RAW_INT':
            print(f"[GPS STATUS] Fix: {msg.fix_type}, Satellites: {msg.satellites_visible}")
                # -------- COG (movement direction) --------
            if msg.cog != 65535:
                telemetry["cog"] = msg.cog / 100


        elif msg_type == 'VFR_HUD':
                telemetry["heading_autopilot"] = msg.heading


        elif msg_type == 'SYSTEM_TIME':
            if msg.time_unix_usec > 0:


                print(f"[RAW GPS TIME] {msg.time_unix_usec}")


                gps_time = msg.time_unix_usec / 1e6


                if prev_gps is not None:
                    print(f"[ΔGPS] {gps_time - prev_gps:.3f} sec")
                prev_gps = gps_time


                print(f"[RAW SYSTEM] {time.time()}")
                print(f"[GPS TIME ] {gps_time}")


                new_offset = gps_time - system_time
               #new_offset=  gps_time - time.time()


                if time_offset is None:
                    time_offset = new_offset
                else:
                    time_offset = 0.7 * time_offset + 0.3 * new_offset


                telemetry["gps_timestamp_utc"] = gps_time


                gps_dt_utc = datetime.fromtimestamp(gps_time, UTC)
                telemetry["gps_datetime_utc"] = gps_dt_utc.strftime('%Y-%m-%d %H:%M:%S')
                telemetry["gps_datetime_ist"] = (gps_dt_utc + IST_OFFSET).strftime('%Y-%m-%d %H:%M:%S')


    # -------- CLEAN OUTPUT --------
    if telemetry["lat"] is not None and time.time() - last_print > 0.5:


        delay = None
        if telemetry["gps_timestamp_utc"]:
            delay = telemetry["system_timestamp_utc"] - telemetry["gps_timestamp_utc"]
        telemetry["heading"] = {
    "body": telemetry.get("heading_body"),
    "autopilot": telemetry.get("heading_autopilot"),
    "cog": telemetry.get("cog")
}    


        print("\n" + "="*50)
        print("🚁 DRONE TELEMETRY")
        print("="*50)


        print(f"📍 GPS:")
        print(f"   Lat: {telemetry['lat']:.7f}")
        print(f"   Lon: {telemetry['lon']:.7f}")
        print(f"   Alt (MSL): {telemetry['alt_msl']:.2f} m")
        print(f"   Alt (AGL): {telemetry['alt_agl']:.2f} m")


        print(f"\n🧭 ATTITUDE:")
        print(f"   Roll : {telemetry['roll']:.4f}")
        print(f"   Pitch: {telemetry['pitch']:.4f}")
        print(f"   Yaw  : {telemetry['yaw']:.4f}")
        print(f"\n🧭 HEADING:")
        print(f"   Body       : {telemetry['heading_body']}")
        print(f"   Autopilot  : {telemetry.get('heading_autopilot')}")
        print(f"   COG        : {telemetry.get('cog')}")


        print(f"\n🚀 SPEED:")
        print(f"   Vx: {telemetry['vx']:.2f} m/s")
        print(f"   Vy: {telemetry['vy']:.2f} m/s")
        print(f"   Vz: {telemetry['vz']:.2f} m/s")
        print(f"   Ground Speed: {telemetry['ground_speed']:.2f} m/s")


        print(f"\n🔋 BATTERY:")
        print(f"   Voltage: {telemetry['battery_voltage']} V")


        print(f"\n⏱ SYSTEM TIME:")
        print(f"   UTC: {telemetry['system_datetime_utc']}")
        print(f"   IST: {telemetry['system_datetime_ist']}")


        print(f"\n🛰 GPS TIME:")
        print(f"   UTC: {telemetry['gps_datetime_utc']}")
        print(f"   IST: {telemetry['gps_datetime_ist']}")


        if delay is not None:
            print(f"\n⚡ TIME SYNC ERROR: {delay:.6f} sec")


        print(f"""
🔍 CHECK:
GPS Time     : {telemetry["gps_datetime_utc"]}
System Time  : {telemetry["system_datetime_utc"]}
Raw Offset   : {delay}
""")


        print("="*50)


        last_print = time.time()


