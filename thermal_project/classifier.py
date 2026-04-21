"""
TIOS Classifier — Thermal Anomaly Classification

Classifies hotspot detections by:
  - Severity level (NORMAL, ELEVATED, WARNING, CRITICAL)
  - Anomaly type (electrical, mechanical, solar, insulation, unknown)
  - Priority for operator attention

Uses configurable temperature thresholds and spatial heuristics
to reduce workload on the field operator.

Usage:
    classifier = ThermalClassifier()
    classified = classifier.classify(detections, frame_stats)
"""

import time
import logging
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class Severity(Enum):
    """Thermal anomaly severity levels (IEC 62446 / NFPA 70B aligned)."""
    NORMAL   = "NORMAL"
    ELEVATED = "ELEVATED"
    WARNING  = "WARNING"
    CRITICAL = "CRITICAL"


class AnomalyType(Enum):
    """Categories of thermal anomaly."""
    ELECTRICAL   = "ELECTRICAL"     # Loose connection, overloaded circuit
    MECHANICAL   = "MECHANICAL"     # Bearing, motor, friction
    SOLAR_PANEL  = "SOLAR_PANEL"    # Cell defect, bypass diode, string fault
    INSULATION   = "INSULATION"     # Missing/degraded insulation
    PIPE_LEAK    = "PIPE_LEAK"      # Steam/fluid leak
    FIRE_RISK    = "FIRE_RISK"      # Imminent fire hazard
    UNKNOWN      = "UNKNOWN"


@dataclass
class ClassifiedDetection:
    """A detection enriched with classification metadata."""
    # Original detection fields
    id: int = 0
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0
    cx: float = 0.0
    cy: float = 0.0
    max_temp: float = 0.0
    min_temp: float = 0.0
    avg_temp: float = 0.0
    area: int = 0
    confidence: float = 0.0
    source: str = "cv"
    label: str = "hotspot"
    timestamp: float = 0.0

    # Classification fields
    severity: str = "NORMAL"
    anomaly_type: str = "UNKNOWN"
    priority: int = 0             # 0=lowest, 100=highest
    delta_t: float = 0.0         # Temperature rise above ambient
    recommendation: str = ""
    needs_action: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class ThermalClassifier:
    """
    Classifies thermal detections into severity levels and anomaly types.
    
    Temperature thresholds (configurable):
        NORMAL:   < ambient + 10°C
        ELEVATED: ambient + 10°C  to  ambient + 25°C
        WARNING:  ambient + 25°C  to  ambient + 40°C
        CRITICAL: > ambient + 40°C
    
    These follow common industrial inspection standards where
    delta-T (rise above ambient) determines severity.
    """

    def __init__(
        self,
        ambient_temp: float = 25.0,
        elevated_delta: float = 10.0,
        warning_delta: float = 25.0,
        critical_delta: float = 40.0,
        # Absolute fallback thresholds
        absolute_warning: float = 60.0,
        absolute_critical: float = 80.0,
    ):
        self.ambient_temp = ambient_temp
        self.elevated_delta = elevated_delta
        self.warning_delta = warning_delta
        self.critical_delta = critical_delta
        self.absolute_warning = absolute_warning
        self.absolute_critical = absolute_critical

        self._classification_count = 0

    def _determine_severity(self, max_temp: float, avg_temp: float) -> Severity:
        """Determine severity based on delta-T and absolute temperature."""
        delta_t = max_temp - self.ambient_temp

        # Absolute thresholds take priority
        if max_temp >= self.absolute_critical:
            return Severity.CRITICAL
        if max_temp >= self.absolute_warning:
            return Severity.WARNING

        # Delta-T based classification
        if delta_t >= self.critical_delta:
            return Severity.CRITICAL
        elif delta_t >= self.warning_delta:
            return Severity.WARNING
        elif delta_t >= self.elevated_delta:
            return Severity.ELEVATED
        else:
            return Severity.NORMAL

    def _determine_type(self, detection, frame_stats: Optional[dict] = None) -> AnomalyType:
        """
        Infer anomaly type from spatial and thermal characteristics.
        
        Heuristics:
        - Small, intense hotspot → likely ELECTRICAL (loose connection)
        - Large, diffuse hotspot → likely INSULATION
        - Very high temp (>100°C) → FIRE_RISK
        - Rectangular, uniform → SOLAR_PANEL
        - Moderate, elongated → MECHANICAL / PIPE_LEAK
        """
        max_t = detection.max_temp
        area = detection.area
        aspect = detection.w / max(detection.h, 1)

        # Fire risk overrides everything
        if max_t > 100:
            return AnomalyType.FIRE_RISK

        # Small and intense → electrical
        if area < 2000 and max_t > 50:
            return AnomalyType.ELECTRICAL

        # Rectangular shape → solar panel defect
        if 0.6 < aspect < 1.8 and area > 3000 and max_t < 60:
            return AnomalyType.SOLAR_PANEL

        # Large diffuse area → insulation
        if area > 5000 and (max_t - detection.min_temp) < 10:
            return AnomalyType.INSULATION

        # Elongated shape → pipe or mechanical
        if aspect > 2.5 or aspect < 0.4:
            return AnomalyType.PIPE_LEAK if max_t < 60 else AnomalyType.MECHANICAL

        # Moderate temperature, medium area → mechanical
        if 40 < max_t < 70 and 1000 < area < 5000:
            return AnomalyType.MECHANICAL

        return AnomalyType.UNKNOWN

    def _get_recommendation(self, severity: Severity, anomaly_type: AnomalyType) -> str:
        """Generate operator recommendation based on classification."""
        recommendations = {
            (Severity.CRITICAL, AnomalyType.FIRE_RISK):
                "IMMEDIATE ACTION: Potential fire hazard. Shut down equipment and investigate.",
            (Severity.CRITICAL, AnomalyType.ELECTRICAL):
                "URGENT: Critical electrical fault. De-energize circuit and inspect connections.",
            (Severity.CRITICAL, AnomalyType.MECHANICAL):
                "URGENT: Critical mechanical failure. Stop equipment immediately.",
            (Severity.WARNING, AnomalyType.ELECTRICAL):
                "Schedule electrical inspection within 24 hours. Check for loose/corroded connections.",
            (Severity.WARNING, AnomalyType.SOLAR_PANEL):
                "Solar panel defect detected. Schedule replacement during next maintenance window.",
            (Severity.WARNING, AnomalyType.INSULATION):
                "Insulation degradation detected. Plan remediation to prevent energy loss.",
            (Severity.WARNING, AnomalyType.MECHANICAL):
                "Mechanical component running hot. Inspect bearings, lubrication, and alignment.",
            (Severity.ELEVATED, AnomalyType.ELECTRICAL):
                "Monitor electrical connection. Re-inspect during next scheduled maintenance.",
            (Severity.ELEVATED, AnomalyType.SOLAR_PANEL):
                "Minor solar panel anomaly. Monitor during next inspection cycle.",
        }

        key = (severity, anomaly_type)
        if key in recommendations:
            return recommendations[key]

        # Generic recommendations by severity
        generic = {
            Severity.CRITICAL: "IMMEDIATE ACTION REQUIRED. Investigate and remediate.",
            Severity.WARNING:  "Schedule inspection within 1 week.",
            Severity.ELEVATED: "Monitor — re-inspect next cycle.",
            Severity.NORMAL:   "No action required.",
        }
        return generic.get(severity, "No action required.")

    def _compute_priority(self, severity: Severity, max_temp: float, confidence: float) -> int:
        """Compute operator priority score (0-100)."""
        base = {
            Severity.CRITICAL: 80,
            Severity.WARNING:  50,
            Severity.ELEVATED: 25,
            Severity.NORMAL:   5,
        }.get(severity, 0)

        # Boost by temperature (max +10)
        temp_boost = min(10, max(0, (max_temp - 50) / 5))
        # Boost by confidence (max +10)
        conf_boost = confidence * 10

        return min(100, int(base + temp_boost + conf_boost))

    def classify(self, detections: list, frame_stats: Optional[dict] = None) -> List[ClassifiedDetection]:
        """
        Classify a list of raw detections.
        
        Args:
            detections:   List of Detection objects from HotspotDetector
            frame_stats:  Optional frame-level temperature stats
            
        Returns:
            List of ClassifiedDetection with severity, type, priority, and recommendations
        """
        # Update ambient estimate from frame stats if available
        if frame_stats and "avg_temp" in frame_stats:
            # Use frame avg as rough ambient estimate
            self.ambient_temp = max(15.0, frame_stats["avg_temp"] - 3.0)

        classified = []
        for det in detections:
            severity = self._determine_severity(det.max_temp, det.avg_temp)
            anomaly_type = self._determine_type(det, frame_stats)
            delta_t = det.max_temp - self.ambient_temp
            priority = self._compute_priority(severity, det.max_temp, det.confidence)
            recommendation = self._get_recommendation(severity, anomaly_type)

            self._classification_count += 1

            cd = ClassifiedDetection(
                # Copy detection fields
                id=det.id,
                x=det.x, y=det.y, w=det.w, h=det.h,
                cx=det.cx, cy=det.cy,
                max_temp=det.max_temp,
                min_temp=det.min_temp,
                avg_temp=det.avg_temp,
                area=det.area,
                confidence=det.confidence,
                source=det.source,
                label=det.label,
                timestamp=det.timestamp,
                # Classification fields
                severity=severity.value,
                anomaly_type=anomaly_type.value,
                priority=priority,
                delta_t=round(delta_t, 1),
                recommendation=recommendation,
                needs_action=severity in (Severity.WARNING, Severity.CRITICAL),
            )
            classified.append(cd)

        # Sort by priority (highest first)
        classified.sort(key=lambda c: c.priority, reverse=True)
        return classified

    def get_summary(self, classified: List[ClassifiedDetection]) -> dict:
        """Generate a summary of all classified detections."""
        counts = {s.value: 0 for s in Severity}
        for c in classified:
            counts[c.severity] = counts.get(c.severity, 0) + 1

        hottest = max((c.max_temp for c in classified), default=0)
        action_required = any(c.needs_action for c in classified)

        return {
            "total_detections": len(classified),
            "severity_counts": counts,
            "hottest_temp": round(hottest, 1),
            "action_required": action_required,
            "ambient_estimate": round(self.ambient_temp, 1),
            "classifications_total": self._classification_count,
        }


if __name__ == "__main__":
    from hotspot_detector import Detection
    
    # Test with mock detections
    test_detections = [
        Detection(id=1, x=100, y=100, w=50, h=40, max_temp=42.5, min_temp=35.0, avg_temp=38.5,
                  area=1800, confidence=0.85, source="cv"),
        Detection(id=2, x=300, y=200, w=30, h=35, max_temp=78.3, min_temp=55.0, avg_temp=65.0,
                  area=900, confidence=0.92, source="cv"),
        Detection(id=3, x=400, y=300, w=100, h=80, max_temp=55.0, min_temp=40.0, avg_temp=48.0,
                  area=7200, confidence=0.70, source="cv"),
    ]
    
    classifier = ThermalClassifier(ambient_temp=25.0)
    classified = classifier.classify(test_detections)
    
    for c in classified:
        print(f"[{c.severity:>8}] {c.anomaly_type:>12} | {c.max_temp:.1f}°C | ΔT={c.delta_t:.1f}°C | P={c.priority}")
        print(f"           → {c.recommendation}")
    
    summary = classifier.get_summary(classified)
    print(f"\nSummary: {summary}")
