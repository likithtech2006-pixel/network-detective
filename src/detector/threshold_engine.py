"""Static threshold evaluation engine for network telemetry metrics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from src.core.config import ThresholdConfig, get_settings
from src.core.models import FaultType
from src.utils.logger import logger


@dataclass
class ThresholdViolation:
    """Represents a breached metric threshold during telemetry evaluation."""

    node_id: str
    violation_type: FaultType
    severity: str  # 'warn' | 'critical'
    current_value: float
    threshold_value: float

    def to_dict(self) -> dict[str, Any]:
        """Convert dataclass fields to a standard dictionary."""
        d = asdict(self)
        d["violation_type"] = self.violation_type.value
        return d


class ThresholdEngine:
    """Evaluates telemetry data against defined operational warning and critical thresholds."""

    def __init__(
        self,
        config: ThresholdConfig | None = None,
        latency_warn: float | None = None,
        latency_critical: float | None = None,
        loss_warn: float | None = None,
        loss_critical: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        """Initialize ThresholdEngine with thresholds from config or explicit overrides.

        Args:
            config: ThresholdConfig instance. Defaults to get_settings().thresholds.
            latency_warn: Warning latency threshold in ms.
            latency_critical: Critical latency threshold in ms.
            loss_warn: Warning packet loss percentage (0-100).
            loss_critical: Critical packet loss percentage (0-100).
            max_retries: Max consecutive probe failures before declaring NODE_DOWN.
        """
        cfg = config or get_settings().thresholds

        self.latency_warn = float(latency_warn if latency_warn is not None else cfg.latency_warn_ms)
        self.latency_critical = float(
            latency_critical if latency_critical is not None else cfg.latency_critical_ms
        )
        self.loss_warn = float(loss_warn if loss_warn is not None else cfg.packet_loss_warn_pct)
        self.loss_critical = float(
            loss_critical if loss_critical is not None else cfg.packet_loss_critical_pct
        )
        self.max_retries = int(max_retries if max_retries is not None else cfg.max_retries)

    def check(
        self,
        node_id: str,
        latency_ms: float,
        packet_loss_pct: float,
        reachable: bool,
        consecutive_failures: int = 0,
    ) -> list[ThresholdViolation]:
        """Evaluate telemetry values against warning and critical thresholds.

        Args:
            node_id: Monitored node identifier.
            latency_ms: Measured round-trip latency in milliseconds.
            packet_loss_pct: Measured packet loss percentage (0-100).
            reachable: Whether the host responded to ping probes.
            consecutive_failures: Count of consecutive failed probe rounds.

        Returns:
            List of detected ThresholdViolation instances.
        """
        violations: list[ThresholdViolation] = []

        # 1. Reachability & Node Down check
        if not reachable:
            if consecutive_failures >= self.max_retries:
                violations.append(
                    ThresholdViolation(
                        node_id=node_id,
                        violation_type=FaultType.NODE_DOWN,
                        severity="critical",
                        current_value=float(consecutive_failures),
                        threshold_value=float(self.max_retries),
                    )
                )
                logger.warning(
                    "Threshold violation: NODE_DOWN on '{}' (failures={}/{})",
                    node_id,
                    consecutive_failures,
                    self.max_retries,
                )
                return violations

        # 2. Latency checks (only when host is reachable and latency is valid)
        if reachable and latency_ms >= 0:
            if latency_ms >= self.latency_critical:
                violations.append(
                    ThresholdViolation(
                        node_id=node_id,
                        violation_type=FaultType.HIGH_LATENCY,
                        severity="critical",
                        current_value=round(latency_ms, 2),
                        threshold_value=self.latency_critical,
                    )
                )
            elif latency_ms >= self.latency_warn:
                violations.append(
                    ThresholdViolation(
                        node_id=node_id,
                        violation_type=FaultType.HIGH_LATENCY,
                        severity="warn",
                        current_value=round(latency_ms, 2),
                        threshold_value=self.latency_warn,
                    )
                )

        # 3. Packet Loss checks
        if packet_loss_pct >= self.loss_critical:
            violations.append(
                ThresholdViolation(
                    node_id=node_id,
                    violation_type=FaultType.PACKET_LOSS,
                    severity="critical",
                    current_value=round(packet_loss_pct, 2),
                    threshold_value=self.loss_critical,
                )
            )
        elif packet_loss_pct >= self.loss_warn:
            violations.append(
                ThresholdViolation(
                    node_id=node_id,
                    violation_type=FaultType.PACKET_LOSS,
                    severity="warn",
                    current_value=round(packet_loss_pct, 2),
                    threshold_value=self.loss_warn,
                )
            )

        return violations
