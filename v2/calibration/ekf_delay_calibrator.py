"""
ekf_delay_calibrator.py
───────────────────────
Offline tool to empirically find the optimal EKF_DELAY value.

Usage
─────
1.  Collect a flight log where you record GPS timestamps, positions (lat/lon),
    and NED velocities (vx, vy in m/s) — e.g. from GLOBAL_POSITION_INT.

2.  Build `positions`, `velocities`, and `timestamps` lists from the log,
    then call sweep_ekf_delay().

3.  The printed best_delay is the value to set in frame_tagger.py:
        EKF_DELAY = <best_delay>

Method
──────
For each consecutive pair of GPS samples (t1→t2), the EKF was reporting the
state for time (t1 - ekf_delay).  We predict where the drone would be at t2
using:

    predicted_lat/lon = pos_at_t1 + vel_at_t1 * (t2 - t1 - ekf_delay)

Then compare to the *actual* GPS position at t2.  The ekf_delay that minimises
this forward-prediction error is the empirically correct value.
"""

import math
import numpy as np

# ── Earth radius for flat-earth NED approximation ──────────────────────────────
R_EARTH = 6_378_137.0  # metres


def latlon_to_ned(lat, lon, anchor_lat, anchor_lon):
    """Convert lat/lon to local NED (North, East) offset in metres."""
    d_lat = math.radians(lat - anchor_lat)
    d_lon = math.radians(lon - anchor_lon)
    n = d_lat * R_EARTH
    e = d_lon * R_EARTH * math.cos(math.radians(anchor_lat))
    return n, e


def ned_to_latlon(n, e, anchor_lat, anchor_lon):
    d_lat = n / R_EARTH
    d_lon = e / (R_EARTH * math.cos(math.radians(anchor_lat)))
    return anchor_lat + math.degrees(d_lat), anchor_lon + math.degrees(d_lon)


def prediction_error_m(lat1, lon1, vx, vy, lat2, lon2, effective_dt):
    """
    Predict position after `effective_dt` seconds using constant-velocity
    kinematics, then return the error (metres) against the actual position.
    """
    pred_n = vx * effective_dt
    pred_e = vy * effective_dt
    pred_lat, pred_lon = ned_to_latlon(pred_n, pred_e, lat1, lon1)

    # Distance between predicted and actual in NED metres
    dn, de = latlon_to_ned(lat2, lon2, pred_lat, pred_lon)
    return math.sqrt(dn * dn + de * de)


def compute_mean_error(positions, velocities, timestamps, ekf_delay):
    """
    Args
    ────
    positions   : list of (lat, lon) floats
    velocities  : list of (vx, vy) floats  [m/s, NED]
    timestamps  : list of float  [seconds, same epoch as drone time]
    ekf_delay   : float  [seconds] — candidate value to evaluate

    Returns
    ───────
    float : mean forward-prediction error in metres across all sample pairs
    """
    errors = []
    for i in range(len(positions) - 1):
        lat1, lon1 = positions[i]
        lat2, lon2 = positions[i + 1]
        vx, vy = velocities[i]
        t1, t2 = timestamps[i], timestamps[i + 1]

        dt = t2 - t1
        if dt <= 0:
            continue

        # The effective time step the prediction must cover is dt minus the
        # EKF delay, because the EKF position at t1 already represents the
        # drone state from (t1 - ekf_delay).
        effective_dt = dt - ekf_delay

        # Skip pairs where the delay exceeds the sample interval
        if effective_dt <= 0:
            continue

        # Skip implausible velocities
        speed = math.sqrt(vx * vx + vy * vy)
        if speed > 15.0:
            continue

        err = prediction_error_m(lat1, lon1, vx, vy, lat2, lon2, effective_dt)
        errors.append(err)

    if not errors:
        return float("inf")
    return float(np.mean(errors))


def sweep_ekf_delay(positions, velocities, timestamps,
                    delay_min=0.02, delay_max=0.25, step=0.005):
    """
    Sweep EKF_DELAY candidates and return the value with minimum mean error.

    Args
    ────
    positions   : list of (lat, lon)
    velocities  : list of (vx, vy) in m/s NED
    timestamps  : list of float seconds (drone-time epoch)
    delay_min   : float  minimum delay to test (s)
    delay_max   : float  maximum delay to test (s)
    step        : float  resolution of sweep (s)

    Returns
    ───────
    best_delay  : float  optimal EKF_DELAY in seconds
    best_error  : float  mean prediction error at best_delay in metres
    results     : list of (delay, mean_error) for all candidates
    """
    candidates = np.arange(delay_min, delay_max + step / 2, step)
    results = []

    print(f"\n{'EKF_DELAY (ms)':>16}  {'Mean Error (m)':>16}")
    print("─" * 36)

    for delay in candidates:
        mean_err = compute_mean_error(positions, velocities, timestamps, delay)
        results.append((float(delay), mean_err))
        print(f"{delay * 1000:>14.1f} ms  {mean_err:>14.4f} m")

    best_delay, best_error = min(results, key=lambda x: x[1])

    print(f"\n✅ Best EKF_DELAY: {best_delay * 1000:.1f} ms  "
          f"(mean error = {best_error * 100:.1f} cm)")
    print(f"   → Set EKF_DELAY = {best_delay:.3f} in frame_tagger.py")

    return best_delay, best_error, results


# ── Example: plug in your logged data below and run this file directly ──────────
if __name__ == "__main__":
    # Replace these with real data from your flight log.
    # Each entry corresponds to one GLOBAL_POSITION_INT message.
    example_positions = [
        (12.9716, 77.5946),
        (12.9717, 77.5947),
        (12.9718, 77.5948),
        (12.9720, 77.5950),
    ]
    example_velocities = [
        (1.2, 0.8),   # vx, vy in m/s (NED)
        (1.3, 0.9),
        (1.1, 1.0),
        (1.2, 1.1),
    ]
    example_timestamps = [
        1_700_000_000.000,
        1_700_000_000.100,
        1_700_000_000.200,
        1_700_000_000.300,
    ]

    sweep_ekf_delay(example_positions, example_velocities, example_timestamps)
