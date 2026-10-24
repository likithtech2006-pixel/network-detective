"""Fault classification combining static threshold violations and statistical anomalies."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from src.core.models import FaultType, LinkStatus, NodeStatus
from src.detector.anomaly_detector import AnomalyResult
from src.detector.threshold_engine import ThresholdViolation
from src.utils.logger import logger


@dataclass
class Fault:
    """Classified network fault requiring diagnosis and remediation."""

    fault_type: FaultType
    affected_component: str
    severity: str  # 'warn' | 'critical'
    confidence: float  # 0.0 to 1.0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert dataclass fields to a standard dictionary."""
        d = asdict(self)
        d["fault_type"] = self.fault_type.value
        return d


# Priority ranking for sorting classified faults (lower rank = higher priority)
FAULT_PRIORITY: dict[FaultType, int] = {
    FaultType.NODE_DOWN: 1,
    FaultType.LINK_DOWN: 2,
    FaultType.HIGH_LATENCY: 3,
    FaultType.PACKET_LOSS: 4,
    FaultType.LINK_DEGRADED: 5,
}


class FaultClassifier:
    """Aggregates threshold breaches, anomaly scores, and component statuses into actionable faults."""

    def __init__(self) -> None:
        """Initialize FaultClassifier."""
        pass

    def classify(
        self,
        violations: list[ThresholdViolation],
        anomalies: list[AnomalyResult],
        node_status: str | NodeStatus = "up",
        link_statuses: dict[str, str | LinkStatus] | None = None,
        node_id: str | None = None,
    ) -> list[Fault]:
        """Classify and prioritize network faults from raw detection inputs.

        Combines static threshold breaches with statistical Z-score anomalies,
        ranking faults by severity and component criticality.

        Args:
            violations: List of threshold violations from ThresholdEngine.
            anomalies: List of anomaly results from AnomalyDetector.
            node_status: Current operational status of the primary node.
            link_statuses: Optional mapping of link IDs to their current status.
            node_id: Optional fallback node identifier if not in violations.

        Returns:
            Sorted list of Fault instances ordered by priority.
        """
        raw_faults: list[Fault] = []
        node_stat_str = node_status.value if isinstance(node_status, NodeStatus) else str(node_status).lower()
        links_map = link_statuses or {}

        # Resolve primary node ID
        primary_node = node_id or (violations[0].node_id if violations else "unknown")

        # Set of anomalous metric names
        anomaly_metric_map = {a.metric_name: a for a in anomalies if a.is_anomaly}

        # 1. Evaluate NODE_DOWN condition
        node_down_violation = next((v for v in violations if v.violation_type == FaultType.NODE_DOWN), None)
        if node_stat_str == NodeStatus.DOWN.value or node_down_violation:
            confidence = 0.99 if (node_stat_str == NodeStatus.DOWN.value and node_down_violation) else 0.92
            raw_faults.append(
                Fault(
                    fault_type=FaultType.NODE_DOWN,
                    affected_component=node_down_violation.node_id if node_down_violation else primary_node,
                    severity="critical",
                    confidence=confidence,
                    details={
                        "node_status": node_stat_str,
                        "consecutive_failures": node_down_violation.current_value if node_down_violation else 0,
                        "threshold": node_down_violation.threshold_value if node_down_violation else 0,
                    },
                )
            )

        # 2. Evaluate LINK_DOWN and LINK_DEGRADED from link statuses
        for link_id_key, l_status in links_map.items():
            l_stat_str = l_status.value if isinstance(l_status, LinkStatus) else str(l_status).lower()
            if l_stat_str == LinkStatus.DOWN.value:
                raw_faults.append(
                    Fault(
                        fault_type=FaultType.LINK_DOWN,
                        affected_component=link_id_key,
                        severity="critical",
                        confidence=0.95,
                        details={"link_status": l_stat_str},
                    )
                )
            elif l_stat_str == LinkStatus.DEGRADED.value:
                raw_faults.append(
                    Fault(
                        fault_type=FaultType.LINK_DEGRADED,
                        affected_component=link_id_key,
                        severity="warn",
                        confidence=0.80,
                        details={"link_status": l_stat_str},
                    )
                )

        # 3. Evaluate Metric Violations (HIGH_LATENCY & PACKET_LOSS)
        for v in violations:
            if v.violation_type in (FaultType.NODE_DOWN, FaultType.LINK_DOWN):
                continue  # Handled above

            # Check if corroborated by statistical anomaly
            metric_key = "latency" if v.violation_type == FaultType.HIGH_LATENCY else "packet_loss"
            matching_anomaly = next(
                (a for name, a in anomaly_metric_map.items() if metric_key in name.lower()),
                None,
            )

            if matching_anomaly:
                # Corroborated: higher confidence
                confidence = 0.95 if v.severity == "critical" else 0.88
            else:
                confidence = 0.85 if v.severity == "critical" else 0.75

            raw_faults.append(
                Fault(
                    fault_type=v.violation_type,
                    affected_component=v.node_id,
                    severity=v.severity,
                    confidence=confidence,
                    details={
                        "current_value": v.current_value,
                        "threshold_value": v.threshold_value,
                        "corroborated_by_anomaly": matching_anomaly is not None,
                        "anomaly_z_score": matching_anomaly.z_score if matching_anomaly else None,
                    },
                )
            )

        # 4. Evaluate Early Anomaly Warnings (Anomalous without static threshold breach)
        handled_fault_types = {f.fault_type for f in raw_faults}
        for name, anom in anomaly_metric_map.items():
            if "latency" in name.lower() and FaultType.HIGH_LATENCY not in handled_fault_types:
                conf = min(0.85, 0.65 + anom.z_score * 0.05)
                raw_faults.append(
                    Fault(
                        fault_type=FaultType.HIGH_LATENCY,
                        affected_component=primary_node,
                        severity="warn",
                        confidence=round(conf, 2),
                        details={
                            "reason": "Statistical anomaly detected before threshold breach",
                            "z_score": anom.z_score,
                            "mean": anom.mean,
                            "stdev": anom.stdev,
                            "value": anom.value,
                        },
                    )
                )
            elif "loss" in name.lower() and FaultType.PACKET_LOSS not in handled_fault_types:
                conf = min(0.85, 0.65 + anom.z_score * 0.05)
                raw_faults.append(
                    Fault(
                        fault_type=FaultType.PACKET_LOSS,
                        affected_component=primary_node,
                        severity="warn",
                        confidence=round(conf, 2),
                        details={
                            "reason": "Statistical anomaly detected before threshold breach",
                            "z_score": anom.z_score,
                            "mean": anom.mean,
                            "stdev": anom.stdev,
                            "value": anom.value,
                        },
                    )
                )

        # 5. Deduplicate and keep maximum severity & confidence per component + type
        unique_faults: dict[tuple[FaultType, str], Fault] = {}
        for fault in raw_faults:
            key = (fault.fault_type, fault.affected_component)
            if key not in unique_faults:
                unique_faults[key] = fault
            else:
                existing = unique_faults[key]
                # Keep critical severity over warn
                if fault.severity == "critical":
                    existing.severity = "critical"
                existing.confidence = max(existing.confidence, fault.confidence)
                existing.details.update(fault.details)

        sorted_faults = sorted(
            unique_faults.values(),
            key=lambda f: (
                FAULT_PRIORITY.get(f.fault_type, 99),
                0 if f.severity == "critical" else 1,
                -f.confidence,
            ),
        )

        if sorted_faults:
            logger.debug(
                "Classified {} fault(s) on '{}': {}",
                len(sorted_faults),
                primary_node,
                [f.fault_type.value for f in sorted_faults],
            )

        return sorted_faults
