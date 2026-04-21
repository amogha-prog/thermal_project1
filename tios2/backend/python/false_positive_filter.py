"""
TIOS False Positive Filter — Detection Validation

Filters out false positive hotspot detections using:
  1. Temporal persistence — hotspot must appear in multiple consecutive frames
  2. Spatial consistency — hotspot must not jump erratically between frames
  3. Thermal noise check — filters out sensor noise patterns
  4. Edge artifact check — ignores detections at frame edges (lens artifacts)

Usage:
    fp_filter = FalsePositiveFilter()
    valid_detections = fp_filter.filter(raw_detections)
"""

import time
import logging
import math
from collections import deque
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class TrackedHotspot:
    """Tracks a hotspot across multiple frames for persistence validation."""

    def __init__(self, detection, first_seen: float):
        self.cx = detection.cx
        self.cy = detection.cy
        self.max_temp = detection.max_temp
        self.first_seen = first_seen
        self.last_seen = first_seen
        self.frame_count = 1
        self.temp_history: deque = deque(maxlen=30)  # Last 30 frames
        self.position_history: deque = deque(maxlen=30)
        self.temp_history.append(detection.max_temp)
        self.position_history.append((detection.cx, detection.cy))
        self.validated = False

    def update(self, detection, timestamp: float):
        """Update tracked hotspot with a new matching detection."""
        self.cx = detection.cx
        self.cy = detection.cy
        self.max_temp = detection.max_temp
        self.last_seen = timestamp
        self.frame_count += 1
        self.temp_history.append(detection.max_temp)
        self.position_history.append((detection.cx, detection.cy))

    @property
    def age(self) -> float:
        """How long this hotspot has been tracked (seconds)."""
        return self.last_seen - self.first_seen

    @property
    def temp_variance(self) -> float:
        """Temperature variance over recent frames."""
        if len(self.temp_history) < 2:
            return 0.0
        temps = list(self.temp_history)
        mean = sum(temps) / len(temps)
        return sum((t - mean) ** 2 for t in temps) / len(temps)

    @property
    def spatial_stability(self) -> float:
        """How stable the position is (lower = more stable). Returns avg frame-to-frame distance."""
        if len(self.position_history) < 2:
            return 0.0
        positions = list(self.position_history)
        total_dist = 0.0
        for i in range(1, len(positions)):
            dx = positions[i][0] - positions[i - 1][0]
            dy = positions[i][1] - positions[i - 1][1]
            total_dist += math.sqrt(dx * dx + dy * dy)
        return total_dist / (len(positions) - 1)


class FalsePositiveFilter:
    """
    Filters false positive detections using multi-frame analysis.
    
    A detection is considered valid when:
    1. It has appeared in at least `min_persistence_frames` consecutive frames
    2. Its position hasn't jumped more than `max_spatial_jump` between frames
    3. Its temperature variance isn't too high (not sensor noise)
    4. It's not at the frame edge (lens artifact zone)
    """

    def __init__(
        self,
        min_persistence_frames: int = 3,
        min_persistence_time: float = 0.5,  # seconds
        max_spatial_jump: float = 0.15,      # normalized (0-1) max distance per frame
        max_temp_variance: float = 50.0,     # °C² — very noisy if above this
        edge_margin: float = 0.03,           # ignore detections within 3% of frame edge
        match_distance_threshold: float = 0.08,  # max distance to match same hotspot
        stale_timeout: float = 2.0,          # seconds before unmatched track is removed
    ):
        self.min_persistence_frames = min_persistence_frames
        self.min_persistence_time = min_persistence_time
        self.max_spatial_jump = max_spatial_jump
        self.max_temp_variance = max_temp_variance
        self.edge_margin = edge_margin
        self.match_distance_threshold = match_distance_threshold
        self.stale_timeout = stale_timeout

        self._tracked: Dict[int, TrackedHotspot] = {}
        self._next_track_id = 0
        self._total_filtered = 0
        self._total_passed = 0

    def _is_edge_artifact(self, detection) -> bool:
        """Check if detection is near the frame edge (lens artifact zone)."""
        m = self.edge_margin
        return (
            detection.cx < m or detection.cx > (1 - m) or
            detection.cy < m or detection.cy > (1 - m)
        )

    def _find_matching_track(self, detection) -> Optional[int]:
        """Find the closest existing track for a new detection."""
        best_id = None
        best_dist = float("inf")
        now = time.time()

        for track_id, track in self._tracked.items():
            # Skip stale tracks
            if now - track.last_seen > self.stale_timeout:
                continue

            dx = detection.cx - track.cx
            dy = detection.cy - track.cy
            dist = math.sqrt(dx * dx + dy * dy)

            if dist < self.match_distance_threshold and dist < best_dist:
                best_dist = dist
                best_id = track_id

        return best_id

    def _cleanup_stale_tracks(self):
        """Remove tracks that haven't been seen recently."""
        now = time.time()
        stale_ids = [
            tid for tid, track in self._tracked.items()
            if now - track.last_seen > self.stale_timeout
        ]
        for tid in stale_ids:
            del self._tracked[tid]

    def filter(self, detections: list) -> list:
        """
        Filter detections, returning only those that pass validation.
        
        Args:
            detections: Raw detections from HotspotDetector / ThermalClassifier
            
        Returns:
            List of validated detections (same type as input)
        """
        now = time.time()
        valid = []
        matched_tracks = set()

        for det in detections:
            # 1. Edge artifact check
            if self._is_edge_artifact(det):
                self._total_filtered += 1
                continue

            # 2. Find or create track
            track_id = self._find_matching_track(det)

            if track_id is not None:
                # Update existing track
                track = self._tracked[track_id]
                
                # Spatial jump check
                dx = det.cx - track.cx
                dy = det.cy - track.cy
                jump = math.sqrt(dx * dx + dy * dy)
                
                if jump > self.max_spatial_jump:
                    # Too far — treat as a new detection, not the same hotspot
                    self._next_track_id += 1
                    self._tracked[self._next_track_id] = TrackedHotspot(det, now)
                    matched_tracks.add(self._next_track_id)
                    continue

                track.update(det, now)
                matched_tracks.add(track_id)

                # 3. Check persistence
                if (track.frame_count >= self.min_persistence_frames and
                    track.age >= self.min_persistence_time):
                    
                    # 4. Temperature variance check
                    if track.temp_variance > self.max_temp_variance:
                        self._total_filtered += 1
                        continue

                    track.validated = True
                    valid.append(det)
                    self._total_passed += 1
                # Not yet persistent enough — skip but keep tracking

            else:
                # New detection — start tracking
                self._next_track_id += 1
                self._tracked[self._next_track_id] = TrackedHotspot(det, now)
                matched_tracks.add(self._next_track_id)

        # Cleanup old tracks
        self._cleanup_stale_tracks()

        return valid

    def get_stats(self) -> dict:
        """Return filter statistics."""
        validated_tracks = sum(1 for t in self._tracked.values() if t.validated)
        return {
            "active_tracks": len(self._tracked),
            "validated_tracks": validated_tracks,
            "total_filtered": self._total_filtered,
            "total_passed": self._total_passed,
            "filter_rate": round(
                self._total_filtered / max(1, self._total_filtered + self._total_passed) * 100, 1
            ),
        }

    def reset(self):
        """Reset all tracking state."""
        self._tracked.clear()
        self._next_track_id = 0
        self._total_filtered = 0
        self._total_passed = 0


if __name__ == "__main__":
    from hotspot_detector import Detection
    import random

    logging.basicConfig(level=logging.INFO)
    fp_filter = FalsePositiveFilter(min_persistence_frames=3)

    # Simulate 10 frames
    print("Simulating detection filtering over 10 frames...")
    for frame_idx in range(10):
        # Persistent real hotspot (appears every frame, stable position)
        real = Detection(
            id=frame_idx * 10 + 1,
            cx=0.5 + random.gauss(0, 0.005),
            cy=0.4 + random.gauss(0, 0.005),
            max_temp=55.0 + random.gauss(0, 1.5),
            min_temp=40.0,
            avg_temp=48.0,
            area=1200,
            confidence=0.85,
        )

        # Noisy false positive (random position each frame)
        noise = Detection(
            id=frame_idx * 10 + 2,
            cx=random.random(),
            cy=random.random(),
            max_temp=38.0 + random.gauss(0, 5.0),
            min_temp=30.0,
            avg_temp=35.0,
            area=200,
            confidence=0.3,
        )

        results = fp_filter.filter([real, noise])
        print(f"  Frame {frame_idx + 1}: {len(results)} valid detections")

        time.sleep(0.15)

    print(f"\nFilter stats: {fp_filter.get_stats()}")
