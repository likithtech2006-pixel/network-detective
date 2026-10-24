"""Statistical anomaly detection using rolling-window Z-score calculations."""

from __future__ import annotations

import statistics
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from typing import Any

from src.utils.logger import logger


@dataclass
class AnomalyResult:
    """Outcome of statistical anomaly evaluation for a single metric sample."""

    is_anomaly: bool
    z_score: float
    mean: float
    stdev: float
    value: float
    metric_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert dataclass fields to a standard dictionary."""
        return asdict(self)


class AnomalyDetector:
    """Detects metric outliers using rolling Z-scores against a baseline distribution."""

    def __init__(
        self,
        window_size: int = 30,
        z_threshold: float = 2.5,
        min_samples: int = 5,
    ) -> None:
        """Initialize AnomalyDetector.

        Args:
            window_size: Number of past observations kept in rolling history (default: 30).
            z_threshold: Number of standard deviations above which a point is anomalous (default: 2.5).
            min_samples: Minimum observations required before evaluating anomalies (default: 5).
        """
        self.window_size = max(5, window_size)
        self.z_threshold = float(z_threshold)
        self.min_samples = max(2, min_samples)

        # Structure: _windows[node_id][metric_name] = deque(maxlen=window_size)
        self._windows: dict[str, dict[str, deque[float]]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=self.window_size))
        )

    def check(self, node_id: str, metric_name: str, value: float) -> AnomalyResult:
        """Evaluate if the provided telemetry value represents a statistical anomaly.

        Compares the current sample against the historical distribution of previous
        measurements before appending the new sample to the rolling window.

        Args:
            node_id: Monitored node ID.
            metric_name: Name of metric ('latency_ms', 'packet_loss_pct', etc.).
            value: Current numerical observation.

        Returns:
            AnomalyResult indicating whether an anomaly was detected and its Z-score.
        """
        val = float(value)
        history = list(self._windows[node_id][metric_name])

        if len(history) < self.min_samples:
            # Baseline is still warming up
            self._windows[node_id][metric_name].append(val)
            return AnomalyResult(
                is_anomaly=False,
                z_score=0.0,
                mean=round(val, 2),
                stdev=0.0,
                value=round(val, 2),
                metric_name=metric_name,
            )

        mean_val = statistics.mean(history)
        stdev_val = statistics.stdev(history)

        if stdev_val < 1e-4:
            # Constant history: if sudden delta exists, flag or assign zero score
            delta = abs(val - mean_val)
            if delta > 5.0 and delta > (mean_val * 0.5):
                z_score = 3.0  # Synthetic anomaly score when variance was near zero
                is_anomaly = True
            else:
                z_score = 0.0
                is_anomaly = False
        else:
            z_score = abs(val - mean_val) / stdev_val
            is_anomaly = z_score >= self.z_threshold

        if is_anomaly:
            logger.warning(
                "Anomaly detected for '{}' [{}]: val={:.2f}, baseline={:.2f}±{:.2f}, z={:.2f}",
                node_id,
                metric_name,
                val,
                mean_val,
                stdev_val,
                z_score,
            )

        # Append observation to rolling window after evaluation
        self._windows[node_id][metric_name].append(val)

        return AnomalyResult(
            is_anomaly=is_anomaly,
            z_score=round(z_score, 2),
            mean=round(mean_val, 2),
            stdev=round(stdev_val, 2),
            value=round(val, 2),
            metric_name=metric_name,
        )

    def get_baseline(self, node_id: str, metric_name: str) -> dict[str, float]:
        """Return the current baseline mean, stdev, and sample count for a node metric.

        Args:
            node_id: Node identifier.
            metric_name: Metric name.

        Returns:
            Dictionary with mean, stdev, and count.
        """
        history = list(self._windows[node_id][metric_name])
        if len(history) < 2:
            return {
                "mean": round(history[0], 2) if history else 0.0,
                "stdev": 0.0,
                "sample_count": len(history),
            }

        return {
            "mean": round(statistics.mean(history), 2),
            "stdev": round(statistics.stdev(history), 2),
            "sample_count": len(history),
        }

    def reset(self, node_id: str | None = None) -> None:
        """Reset historical windows for a specific node or all nodes."""
        if node_id is None:
            self._windows.clear()
        elif node_id in self._windows:
            del self._windows[node_id]
