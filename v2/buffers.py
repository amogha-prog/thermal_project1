import bisect
import math

# ── Earth radius for flat-earth NED approximation ──────────────────────────────
R_EARTH = 6378137.0  # metres


# ── Coordinate helpers ──────────────────────────────────────────────────────────

def latlon_to_ned(lat, lon, anchor_lat, anchor_lon):
    """Convert lat/lon to local NED (North, East) offsets from an anchor point."""
    lat_rad = math.radians(lat)
    d_lat = math.radians(lat - anchor_lat)
    d_lon = math.radians(lon - anchor_lon)
    n = d_lat * R_EARTH
    e = d_lon * R_EARTH * math.cos(math.radians(anchor_lat))
    return n, e


def ned_to_latlon(n, e, anchor_lat, anchor_lon):
    """Convert NED offsets back to lat/lon relative to an anchor point."""
    d_lat = n / R_EARTH
    d_lon = e / (R_EARTH * math.cos(math.radians(anchor_lat)))
    return anchor_lat + math.degrees(d_lat), anchor_lon + math.degrees(d_lon)


def _distance_m(lat1, lon1, lat2, lon2):
    """Flat-earth distance in metres between two lat/lon points."""
    n, e = latlon_to_ned(lat2, lon2, lat1, lon1)
    return math.sqrt(n * n + e * e)


def _norm2(vx, vy):
    return math.sqrt(vx * vx + vy * vy)


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


# ── Base buffer ─────────────────────────────────────────────────────────────────

class BaseBuffer:
    def __init__(self, size=200):
        self.buffer = []
        self.times = []
        self.size = size
        self.max_gap = 0.5   # seconds; overridden by subclasses
        self.last_delta = None  # seconds to nearest sample, set after each call

    def add(self, t, telemetry):
        """Insert a timestamped telemetry snapshot in sorted order."""
        idx = bisect.bisect_left(self.times, t)
        self.times.insert(idx, t)
        self.buffer.insert(idx, {"time": t, "data": telemetry.copy()})
        if len(self.buffer) > self.size:
            self.buffer.pop(0)
            self.times.pop(0)

    # ── Angle-safe scalar interpolation helpers ─────────────────────────────────
    def _interp(self, a, b, r):
        if a is None or b is None:
            return a
        return a + r * (b - a)

    def _interp_angle_deg(self, a, b, r):
        if a is None or b is None:
            return a
        diff = (b - a + 180) % 360 - 180
        return (a + r * diff) % 360

    def _interp_angle_rad(self, a, b, r):
        if a is None or b is None:
            return a
        diff = (b - a + math.pi) % (2 * math.pi) - math.pi
        result = a + r * diff
        return (result + math.pi) % (2 * math.pi) - math.pi

    # ── Core lookup (shared by both subclasses) ─────────────────────────────────
    def _lookup_bracket(self, t):
        """
        Return (p1, p2) surrounding t, or None if not bracketed within max_gap.
        Also updates self.last_delta.
        """
        self.last_delta = None
        if not self.times:
            return None

        idx = bisect.bisect_left(self.times, t)

        if idx == 0:
            if abs(t - self.times[0]) > self.max_gap:
                return None
            self.last_delta = abs(t - self.times[0])
            return (self.buffer[0], self.buffer[0])  # same node, extrapolation edge

        if idx == len(self.times):
            if abs(t - self.times[-1]) > self.max_gap:
                return None
            self.last_delta = abs(t - self.times[-1])
            return (self.buffer[-1], self.buffer[-1])  # same node, extrapolation edge

        p1 = self.buffer[idx - 1]
        p2 = self.buffer[idx]

        if (p2["time"] - p1["time"]) > self.max_gap:
            return None

        nearest = p1 if abs(t - p1["time"]) < abs(t - p2["time"]) else p2
        self.last_delta = abs(t - nearest["time"])
        return (p1, p2)

    # Subclasses override this
    def _do_interpolate(self, t, p1, p2):
        raise NotImplementedError

    def interpolate(self, t):
        result = self._lookup_bracket(t)
        if result is None:
            return None
        p1, p2 = result
        if p1 is p2:
            return p1["data"]
        return self._do_interpolate(t, p1, p2)


# ── Attitude buffer ─────────────────────────────────────────────────────────────

class AttitudeBuffer(BaseBuffer):
    def __init__(self, size=200):
        super().__init__(size)
        self.max_gap = 0.15  # 30 Hz nominal

    def _do_interpolate(self, t, p1, p2):
        d1, d2 = p1["data"], p2["data"]
        t1, t2 = p1["time"], p2["time"]
        if t2 <= t1:
            return d1
        ratio = (t - t1) / (t2 - t1)
        return {
            "roll":  self._interp(d1.get("roll"),  d2.get("roll"),  ratio),
            "pitch": self._interp(d1.get("pitch"), d2.get("pitch"), ratio),
            "yaw":   self._interp_angle_rad(d1.get("yaw"), d2.get("yaw"), ratio),
        }


# ── GPS buffer with kinematic interpolation ─────────────────────────────────────

class GPSBuffer(BaseBuffer):
    """
    Velocity-aware GPS interpolation with:
      - Midpoint-anchored NED kinematics
      - Adaptive linear/kinematic blending
      - Soft + hard velocity and acceleration sanity gates
      - Bounded forward extrapolation
      - Anchor glitch guard
    """

    # ── Tuning constants ────────────────────────────────────────────────────────
    MAX_SPEED  = 8.0    # m/s  – hard reject above this
    SOFT_SPEED = 5.0    # m/s  – reduce kinematic weight above this
    MAX_DV     = 4.0    # m/s  – reject if |V2-V1| exceeds this
    MAX_ACCEL  = 5.0    # m/s² – hard reject / no extrapolation above this
    SOFT_ACCEL = 3.0    # m/s² – reduce kinematic weight above this
    MAX_ANCHOR_DIST = 10.0   # m   – fallback to linear if P1–P2 gap > this

    def __init__(self, size=200):
        super().__init__(size)
        self.max_gap = 0.35  # 10 Hz with RF jitter

    # ── Public entry point ──────────────────────────────────────────────────────
    def interpolate(self, t):
        self.last_delta = None
        if not self.times:
            return None

        idx = bisect.bisect_left(self.times, t)

        # ── Before first sample ─────────────────────────────────────────────────
        if idx == 0:
            if abs(t - self.times[0]) > self.max_gap:
                return None
            self.last_delta = abs(t - self.times[0])
            return self.buffer[0]["data"]

        # ── After last sample → bounded forward extrapolation ───────────────────
        if idx == len(self.times):
            if len(self.times) < 2:
                if abs(t - self.times[-1]) > self.max_gap:
                    return None
                self.last_delta = abs(t - self.times[-1])
                return self.buffer[-1]["data"]

            p1 = self.buffer[-2]
            p2 = self.buffer[-1]
            dt_extrap = t - p2["time"]

            if dt_extrap < 0 or dt_extrap > self.max_gap:
                return None
            self.last_delta = dt_extrap
            return self._extrapolate(t, p1, p2)

        # ── Normal bracketed interpolation ──────────────────────────────────────
        p1 = self.buffer[idx - 1]
        p2 = self.buffer[idx]
        t1, t2 = p1["time"], p2["time"]

        if (t2 - t1) > self.max_gap:
            return None

        nearest = p1 if abs(t - t1) < abs(t - t2) else p2
        self.last_delta = abs(t - nearest["time"])

        if t2 <= t1:          # out-of-order guard
            return p1["data"]

        return self._do_interpolate(t, p1, p2)

    # ── Forward extrapolation ───────────────────────────────────────────────────
    def _extrapolate(self, t, p1, p2):
        d1, d2 = p1["data"], p2["data"]
        t1, t2 = p1["time"], p2["time"]
        if t2 <= t1:
            return d2

        dt = t2 - t1
        dt_extrap = t - t2

        v2x = d2.get("vx", 0) or 0
        v2y = d2.get("vy", 0) or 0
        v1x = d1.get("vx", 0) or 0
        v1y = d1.get("vy", 0) or 0

        speed = _norm2(v2x, v2y)
        ax = (v2x - v1x) / dt
        ay = (v2y - v1y) / dt
        accel = _norm2(ax, ay)

        # Guard: reject if any threshold exceeded (OR logic)
        if dt_extrap > 0.1 or speed > 6.0 or accel > self.MAX_ACCEL:
            return d2  # safe fallback – last known point

        anchor_lat = d2.get("lat")
        anchor_lon = d2.get("lon")
        if anchor_lat is None or anchor_lon is None:
            return d2

        n = v2x * dt_extrap
        e = v2y * dt_extrap
        new_lat, new_lon = ned_to_latlon(n, e, anchor_lat, anchor_lon)

        extrapolated = d2.copy()
        extrapolated["lat"] = new_lat
        extrapolated["lon"] = new_lon
        if d1.get("alt_msl") is not None and d2.get("alt_msl") is not None:
            extrapolated["alt_msl"] = d2["alt_msl"] + (d2["alt_msl"] - d1["alt_msl"]) / dt * dt_extrap
        if d1.get("alt_agl") is not None and d2.get("alt_agl") is not None:
            extrapolated["alt_agl"] = d2["alt_agl"] + (d2["alt_agl"] - d1["alt_agl"]) / dt * dt_extrap
        return extrapolated

    # ── Bracketed kinematic interpolation ───────────────────────────────────────
    def _do_interpolate(self, t, p1, p2):
        d1, d2 = p1["data"], p2["data"]
        t1, t2 = p1["time"], p2["time"]
        dt = t2 - t1
        ratio = (t - t1) / dt

        # ── Linear baseline (always computed as fallback) ───────────────────────
        def lin():
            return {
                "lat":              self._interp(d1.get("lat"),              d2.get("lat"),              ratio),
                "lon":              self._interp(d1.get("lon"),              d2.get("lon"),              ratio),
                "alt_msl":          self._interp(d1.get("alt_msl"),          d2.get("alt_msl"),          ratio),
                "alt_agl":          self._interp(d1.get("alt_agl"),          d2.get("alt_agl"),          ratio),
                "vx":               self._interp(d1.get("vx"),               d2.get("vx"),               ratio),
                "vy":               self._interp(d1.get("vy"),               d2.get("vy"),               ratio),
                "vz":               self._interp(d1.get("vz"),               d2.get("vz"),               ratio),
                "ground_speed":     self._interp(d1.get("ground_speed"),     d2.get("ground_speed"),     ratio),
                "battery_voltage":  self._interp(d1.get("battery_voltage"),  d2.get("battery_voltage"),  ratio),
                "heading_autopilot":self._interp_angle_deg(d1.get("heading_autopilot"), d2.get("heading_autopilot"), ratio),
                "cog":              self._interp_angle_deg(d1.get("cog"),    d2.get("cog"),              ratio),
            }

        lat1, lon1 = d1.get("lat"), d1.get("lon")
        lat2, lon2 = d2.get("lat"), d2.get("lon")
        if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
            return lin()

        # ── Anchor glitch guard ─────────────────────────────────────────────────
        dist = _distance_m(lat1, lon1, lat2, lon2)
        if dist > self.MAX_ANCHOR_DIST:
            return lin()

        # ── Velocity / acceleration extraction ──────────────────────────────────
        v1x = d1.get("vx", 0) or 0;  v1y = d1.get("vy", 0) or 0
        v2x = d2.get("vx", 0) or 0;  v2y = d2.get("vy", 0) or 0

        speed1 = _norm2(v1x, v1y)
        speed2 = _norm2(v2x, v2y)
        dv     = _norm2(v2x - v1x, v2y - v1y)

        ax = (v2x - v1x) / dt
        ay = (v2y - v1y) / dt
        accel = _norm2(ax, ay)

        # ── Hard sanity gates – fall back to pure linear ────────────────────────
        if speed1 > self.MAX_SPEED or speed2 > self.MAX_SPEED:
            return lin()
        if dv > self.MAX_DV:
            return lin()
        if accel > self.MAX_ACCEL:
            return lin()

        # ── Compute adaptive kinematic weight ───────────────────────────────────
        weight_accel = _clamp(accel / 3.0, 0.2, 0.8)

        # Soft speed gate
        if speed1 > self.SOFT_SPEED or speed2 > self.SOFT_SPEED:
            weight_accel *= 0.5

        # Soft accel gate
        if accel > self.SOFT_ACCEL:
            weight_accel *= 0.5

        # Temporal consistency: small dt → noisy derivative
        if dt < 0.05:
            weight_accel *= 0.5

        # Large dt → unreliable acceleration estimate
        if dt > 0.1:
            weight_accel *= 0.5

        # ── Midpoint-anchored NED kinematic model ────────────────────────────────
        anchor_lat = (lat1 + lat2) / 2.0
        anchor_lon = (lon1 + lon2) / 2.0

        n1, e1 = latlon_to_ned(lat1, lon1, anchor_lat, anchor_lon)
        n2, e2 = latlon_to_ned(lat2, lon2, anchor_lat, anchor_lon)

        p_mid_n = (n1 + n2) / 2.0
        p_mid_e = (e1 + e2) / 2.0

        v_mid_x = (v1x + v2x) / 2.0
        v_mid_y = (v1y + v2y) / 2.0

        t_mid  = (t1 + t2) / 2.0
        dt_mid = t - t_mid

        kin_n = p_mid_n + v_mid_x * dt_mid + 0.5 * ax * dt_mid * dt_mid
        kin_e = p_mid_e + v_mid_y * dt_mid + 0.5 * ay * dt_mid * dt_mid
        kin_lat, kin_lon = ned_to_latlon(kin_n, kin_e, anchor_lat, anchor_lon)

        # ── Adaptive blend of linear and kinematic position ──────────────────────
        result = lin()
        result["lat"] = (1.0 - weight_accel) * result["lat"] + weight_accel * kin_lat
        result["lon"] = (1.0 - weight_accel) * result["lon"] + weight_accel * kin_lon
        return result
