"""SLA metric validation engine enforcing post-remediation performance thresholds."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.core.config import ThresholdConfig, get_settings
from src.utils.logger import logger


@dataclass
class ValidationResult:
    """Evaluation verdict of network telemetry metrics against SLA thresholds."""

    passed: bool
    latency_ok: bool
    loss_ok: bool
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize ValidationResult to dictionary."""
        return {
            "passed": self.passed,
            "latency_ok": self.latency_ok,
            "loss_ok": self.loss_ok,
            "details": self.details,
        }


class ValidationEngine:
    """Verifies that post-remediation performance metrics comply with SLA requirements.

    Applies a grace period multiplier (e.g., 1.5x of critical fault thresholds)
    to allow the newly established route to stabilize without premature flapping
    or immediate re-alerting.
    """

    def __init__(self, grace_multiplier: float = 1.5) -> None:
        """Initialize ValidationEngine.

        Args:
            grace_multiplier: Multiplier applied to critical thresholds to account
                              for post-healing routing convergence (default: 1.5x).
        """
        self.grace_multiplier = max(1.0, grace_multiplier)

    def validate_metrics(
        self,
        latency_ms: float,
        packet_loss_pct: float,
        thresholds: dict[str, Any] | ThresholdConfig | None = None,
    ) -> ValidationResult:
        """Evaluate measured latency and packet loss against operational thresholds.

        Args:
            latency_ms: Measured round-trip latency in milliseconds.
            packet_loss_pct: Measured packet loss percentage (0.0 to 100.0).
            thresholds: Optional custom thresholds dictionary or ThresholdConfig object.
                        If None, uses application defaults from get_settings().

        Returns:
            ValidationResult with boolean flags and detailed threshold comparisons.
        """
        # Resolve thresholds
        if thresholds is None:
            settings = get_settings()
            crit_latency = settings.thresholds.latency_critical_ms
            crit_loss = settings.thresholds.packet_loss_critical_pct
            warn_latency = settings.thresholds.latency_warn_ms
            warn_loss = settings.thresholds.packet_loss_warn_pct
        elif isinstance(thresholds, ThresholdConfig):
            crit_latency = thresholds.latency_critical_ms
            crit_loss = thresholds.packet_loss_critical_pct
            warn_latency = thresholds.latency_warn_ms
            warn_loss = thresholds.packet_loss_warn_pct
        elif isinstance(thresholds, dict):
            crit_latency = float(thresholds.get("latency_critical_ms", 200.0))
            crit_loss = float(thresholds.get("packet_loss_critical_pct", 10.0))
            warn_latency = float(thresholds.get("latency_warn_ms", 100.0))
            warn_loss = float(thresholds.get("packet_loss_warn_pct", 5.0))
        else:
            crit_latency = 200.0
            crit_loss = 10.0
            warn_latency = 100.0
            warn_loss = 5.0

        # Apply grace period leniency for post-healing stabilization
        allowed_latency = crit_latency * self.grace_multiplier
        allowed_loss = crit_loss * self.grace_multiplier

        latency_ok = latency_ms <= allowed_latency
        loss_ok = packet_loss_pct <= allowed_loss
        passed = latency_ok and loss_ok

        details = {
            "measured_latency_ms": round(latency_ms, 2),
            "allowed_latency_ms": round(allowed_latency, 2),
            "base_critical_latency_ms": crit_latency,
            "measured_packet_loss_pct": round(packet_loss_pct, 2),
            "allowed_packet_loss_pct": round(allowed_loss, 2),
            "base_critical_loss_pct": crit_loss,
            "grace_multiplier": self.grace_multiplier,
            "latency_within_warn": latency_ms <= warn_latency,
            "loss_within_warn": packet_loss_pct <= warn_loss,
        }

        if passed:
            logger.info(
                "Metric validation PASSED: latency={:.2f}ms (limit={:.2f}ms), loss={:.2f}% (limit={:.2f}%)",
                latency_ms,
                allowed_latency,
                packet_loss_pct,
                allowed_loss,
            )
        else:
            logger.warning(
                "Metric validation FAILED: latency_ok={}, loss_ok={}, details={}",
                latency_ok,
                loss_ok,
                details,
            )

        return ValidationResult(
            passed=passed,
            latency_ok=latency_ok,
            loss_ok=loss_ok,
            details=details,
        )


__all__ = ["ValidationEngine", "ValidationResult"]
