import time


class TimeSync:
    def __init__(self):
        self.offset = None
        self.last_update_mono = None

        # NEW: boot → UTC mapping
        self.boot_to_utc_offset = None

        # tuning
        self.alpha_fast = 0.3
        self.alpha_slow = 0.05
        self.stable_threshold = 0.15  # Increased to allow for 150ms of network jitter
        self.max_jump = 0.5

        self.is_locked = False

        # ── Drift monitoring ──────────────────────────────────────────────────
        self.offset_drift_rate = 0.0   # seconds of drift per second of elapsed time
        self._is_bootstrapped  = False  # True after wall-clock bootstrap; cleared by real GPS

    def update(self, gps_time_unix, boot_time_ms=None):
        mono = time.monotonic()
        new_offset = gps_time_unix - mono

        # ── Bootstrap transition ─────────────────────────────────────────────────
        # When running in wall-clock bootstrap mode the first real SYSTEM_TIME
        # may differ by several seconds (PC clock skew + GPS vs UTC offsets).
        # max_jump would reject it, keeping the wrong offset forever.
        # Instead, treat it as a forced re-initialisation and accept it verbatim.
        if self._is_bootstrapped:
            correction_ms = (new_offset - self.offset) * 1000
            print(f"\u2705 TimeSync: GPS SYSTEM_TIME received — overriding wall-clock bootstrap "
                  f"(correction: {correction_ms:+.0f} ms)")
            self.offset = new_offset
            self.last_update_mono = mono
            self._is_bootstrapped = False
            if boot_time_ms is not None:
                boot_time_s = boot_time_ms / 1000.0
                self.boot_to_utc_offset = gps_time_unix - boot_time_s
            return   # skip normal sync on this tick; next update will lock normally

        # ── Drift monitoring (only when offset came from real GPS) ──────────────
        # Skip during bootstrap mode: delta/growing_dt gives a meaningless rate.
        if self.offset is not None and self.last_update_mono is not None:
            dt_since_update = mono - self.last_update_mono
            if dt_since_update > 0:
                delta_offset = abs(new_offset - self.offset)
                self.offset_drift_rate = delta_offset / dt_since_update
                if delta_offset > 0.010:  # 10 ms threshold
                    print(f"\u26a0\ufe0f Time sync drift: {delta_offset*1000:.1f} ms "
                          f"(rate: {self.offset_drift_rate*1000:.2f} ms/s)")

        # --- normal offset sync ---
        if self.offset is None:
            self.offset = new_offset
            self.last_update_mono = mono
        else:
            if abs(new_offset - self.offset) < self.max_jump:
                error = abs(new_offset - self.offset)

                if error > self.stable_threshold:
                    alpha = self.alpha_fast
                    self.is_locked = False
                else:
                    alpha = self.alpha_slow
                    self.is_locked = True

                self.offset = (1 - alpha) * self.offset + alpha * new_offset
                self.last_update_mono = mono

        # --- NEW: boot → UTC mapping ---
        if boot_time_ms is not None:
            boot_time = boot_time_ms / 1000.0
            self.boot_to_utc_offset = gps_time_unix - boot_time

    def bootstrap_wall_clock(self, latest_boot_ms=None):
        """
        Fallback initialisation using the system wall clock.
        Called when SYSTEM_TIME has not been received within a timeout.
        Only runs once — real SYSTEM_TIME updates will refine from here.
        """
        mono = time.monotonic()
        wall = time.time()

        if self.offset is None:
            self.offset = wall - mono
            self.last_update_mono = mono
            self._is_bootstrapped = True   # flag: offset is from wall clock, not GPS
            print("⚠️ TimeSync: offset bootstrapped from wall clock (SYSTEM_TIME not received)")

        if self.boot_to_utc_offset is None and latest_boot_ms is not None:
            boot_time_s = latest_boot_ms / 1000.0
            self.boot_to_utc_offset = wall - boot_time_s
            print("⚠️ TimeSync: boot→UTC offset bootstrapped from wall clock")

    def boot_to_utc(self, boot_time):
        if self.boot_to_utc_offset is None:
            return None
        return boot_time + self.boot_to_utc_offset

    def to_drone_time(self, mono_time):
        if self.offset is None:
            return None
        return mono_time + self.offset

    def now(self):
        return self.to_drone_time(time.monotonic())

    def get_sync_status(self):
        last_update_age = (
            time.monotonic() - self.last_update_mono
            if self.last_update_mono is not None
            else float('inf')
        )
        return {
            "locked": self.is_locked,
            "last_update_age": last_update_age,
            "offset_drift_rate": self.offset_drift_rate,
        }

    def get_offset(self):
        return self.offset
