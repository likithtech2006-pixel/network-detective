"""Metrics collection and rolling-window statistics for network telemetry."""

from __future__ import annotations

import statistics
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from src.core.models import Database, Metric, get_database
from src.utils.logger import logger


class MetricsCollector:
    """Collects, aggregates, and stores real-time telemetry metrics per network component."""

    def __init__(self, window_size: int = 60, db: Database | None = None) -> None:
        """Initialize MetricsCollector with in-memory deques and database access.

        Args:
            window_size: Maximum rolling history samples per component (default: 60).
            db: Optional Database manager instance. Falls back to get_database().
        """
        self.window_size = max(1, window_size)
        self._db = db or get_database()
        self._node_windows: dict[str, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=self.window_size)
        )
        self._link_windows: dict[str, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=self.window_size)
        )

    async def record_metric(
        self,
        node_id: str,
        latency_ms: float,
        packet_loss_pct: float,
        jitter_ms: float,
        link_id: str | None = None,
    ) -> dict[str, Any]:
        """Record telemetry metric sample in in-memory window and persist to database.

        Args:
            node_id: Monitored node identifier.
            latency_ms: Measured round-trip latency in milliseconds.
            packet_loss_pct: Measured packet loss percentage (0.0 to 100.0).
            jitter_ms: Calculated packet delay variation in milliseconds.
            link_id: Optional network link identifier.

        Returns:
            Dictionary containing the recorded metric record.
        """
        sample = {
            "node_id": node_id,
            "link_id": link_id,
            "latency_ms": round(float(latency_ms), 2),
            "packet_loss_pct": round(float(packet_loss_pct), 2),
            "jitter_ms": round(float(jitter_ms), 2),
            "recorded_at": datetime.now(timezone.utc),
        }

        # 1. Update in-memory rolling window
        self._node_windows[node_id].append(sample)
        if link_id:
            self._link_windows[link_id].append(sample)

        # 2. Persist to database asynchronously
        try:
            async with self._db.session_factory() as session:
                metric_row = Metric(
                    node_id=node_id,
                    link_id=link_id,
                    latency_ms=sample["latency_ms"],
                    packet_loss_pct=sample["packet_loss_pct"],
                    jitter_ms=sample["jitter_ms"],
                    recorded_at=sample["recorded_at"],
                )
                session.add(metric_row)
                await session.commit()
        except Exception as exc:
            # We don't want database transient errors to break real-time polling
            logger.warning("Could not persist metric for node '{}' to DB: {}", node_id, exc)

        return sample

    def get_rolling_stats(self, node_id: str) -> dict[str, float | int]:
        """Compute summary statistics over the rolling window for a node.

        Args:
            node_id: Monitored node identifier.

        Returns:
            Dictionary containing avg_latency, avg_loss, avg_jitter, and sample_count.
        """
        samples = list(self._node_windows.get(node_id, []))
        sample_count = len(samples)

        if sample_count == 0:
            return {
                "avg_latency": 0.0,
                "avg_loss": 0.0,
                "avg_jitter": 0.0,
                "sample_count": 0,
            }

        latencies = [s["latency_ms"] for s in samples]
        losses = [s["packet_loss_pct"] for s in samples]
        jitters = [s["jitter_ms"] for s in samples]

        return {
            "avg_latency": round(statistics.mean(latencies), 2),
            "avg_loss": round(statistics.mean(losses), 2),
            "avg_jitter": round(statistics.mean(jitters), 2),
            "sample_count": sample_count,
        }

    def get_metrics_history(self, node_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Retrieve recent in-memory telemetry samples for a given node.

        Args:
            node_id: Identifier of the node.
            limit: Maximum number of recent samples to return.

        Returns:
            List of metric sample dictionaries ordered chronologically.
        """
        samples = list(self._node_windows.get(node_id, []))
        if not samples:
            return []

        sliced = samples[-limit:]
        return [
            {
                "node_id": s["node_id"],
                "link_id": s["link_id"],
                "latency_ms": s["latency_ms"],
                "packet_loss_pct": s["packet_loss_pct"],
                "jitter_ms": s["jitter_ms"],
                "recorded_at": s["recorded_at"].isoformat()
                if isinstance(s["recorded_at"], datetime)
                else str(s["recorded_at"]),
            }
            for s in sliced
        ]

    async def get_db_metrics_history(self, node_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Query persistent telemetry metrics directly from the database.

        Args:
            node_id: Identifier of the node.
            limit: Maximum number of historical records to query.

        Returns:
            List of Metric dictionaries sorted ascending by timestamp.
        """
        try:
            async with self._db.session_factory() as session:
                stmt = (
                    select(Metric)
                    .where(Metric.node_id == node_id)
                    .order_by(Metric.recorded_at.desc())
                    .limit(limit)
                )
                res = await session.execute(stmt)
                records = list(res.scalars().all())
                records.reverse()
                return [r.to_dict() for r in records]
        except Exception as exc:
            logger.warning("Database query failed in get_db_metrics_history: {}", exc)
            return self.get_metrics_history(node_id=node_id, limit=limit)

    def clear(self) -> None:
        """Clear all in-memory rolling windows."""
        self._node_windows.clear()
        self._link_windows.clear()
