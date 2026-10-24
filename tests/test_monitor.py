"""Unit and integration tests for the Monitor module."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.core.events import EventBus, EventType
from src.core.models import LinkStatus, NodeStatus
from src.monitor.metrics_collector import MetricsCollector
from src.monitor.network_monitor import NetworkMonitor
from src.monitor.ping_probe import PingProbe, PingResult
from src.monitor.tcp_probe import TcpProbe
from src.monitor.topology_builder import TopologyBuilder, set_topology


def test_ping_result_dataclass() -> None:
    """Verify PingResult creation and dictionary serialization."""
    res = PingResult(
        host="192.168.1.1",
        reachable=True,
        avg_latency_ms=12.5,
        packet_loss_pct=0.0,
        min_latency_ms=10.0,
        max_latency_ms=15.0,
        jitter_ms=2.5,
    )
    d = res.to_dict()
    assert d["host"] == "192.168.1.1"
    assert d["reachable"] is True
    assert d["avg_latency_ms"] == 12.5
    assert d["jitter_ms"] == 2.5


def test_ping_probe_mocked() -> None:
    """Test PingProbe statistics calculation across multiple mock pings."""
    async def _test() -> None:
        probe = PingProbe(default_timeout=1.0, default_count=3)

        with patch.object(
            probe,
            "_ping_single",
            side_effect=[(True, 10.0), (True, 20.0), (False, None)],
        ):
            result = await probe.probe("10.0.0.1")
            assert result.host == "10.0.0.1"
            assert result.reachable is True
            assert result.avg_latency_ms == 15.0
            assert result.min_latency_ms == 10.0
            assert result.max_latency_ms == 20.0
            assert result.packet_loss_pct == pytest.approx(33.33, rel=1e-2)
            assert result.jitter_ms == 10.0

    asyncio.run(_test())


def test_ping_probe_all_failed() -> None:
    """Test PingProbe when all ICMP packets fail."""
    async def _test() -> None:
        probe = PingProbe(default_timeout=1.0, default_count=3)

        with patch.object(probe, "_ping_single", return_value=(False, None)):
            result = await probe.probe("10.0.0.99")
            assert result.reachable is False
            assert result.avg_latency_ms is None
            assert result.packet_loss_pct == 100.0
            assert result.jitter_ms == 0.0

    asyncio.run(_test())


def test_tcp_probe_reachable() -> None:
    """Test TcpProbe connecting to a simulated port."""
    async def _test() -> None:
        probe = TcpProbe(default_timeout=1.0)
        mock_writer = AsyncMock()

        with patch("asyncio.open_connection", return_value=(AsyncMock(), mock_writer)):
            result = await probe.probe("127.0.0.1", port=80)
            assert result.reachable is True
            assert result.response_time_ms is not None
            assert result.port == 80

    asyncio.run(_test())


def test_tcp_probe_unreachable() -> None:
    """Test TcpProbe failing on an unreachable port."""
    async def _test() -> None:
        probe = TcpProbe(default_timeout=0.2)
        with patch("asyncio.open_connection", side_effect=asyncio.TimeoutError()):
            result = await probe.probe("127.0.0.1", port=65530)
            assert result.reachable is False
            assert result.response_time_ms is None

    asyncio.run(_test())


def test_metrics_collector() -> None:
    """Test MetricsCollector rolling window and statistics."""
    async def _test() -> None:
        collector = MetricsCollector(window_size=5)

        await collector.record_metric("node-1", latency_ms=10.0, packet_loss_pct=0.0, jitter_ms=1.0)
        await collector.record_metric("node-1", latency_ms=20.0, packet_loss_pct=0.0, jitter_ms=2.0)
        await collector.record_metric("node-1", latency_ms=30.0, packet_loss_pct=6.0, jitter_ms=3.0)

        stats = collector.get_rolling_stats("node-1")
        assert stats["sample_count"] == 3
        assert stats["avg_latency"] == 20.0
        assert stats["avg_loss"] == 2.0
        assert stats["avg_jitter"] == 2.0

        history = collector.get_metrics_history("node-1", limit=2)
        assert len(history) == 2
        assert history[-1]["latency_ms"] == 30.0

    asyncio.run(_test())


def test_topology_builder() -> None:
    """Test building and updating NetworkX topology graphs."""
    builder = TopologyBuilder()
    raw_cfg = {
        "nodes": [
            {"id": "n1", "name": "Node 1", "ip": "10.0.0.1", "node_type": "router"},
            {"id": "n2", "name": "Node 2", "ip": "10.0.0.2", "node_type": "server"},
        ],
        "links": [
            {"source": "n1", "target": "n2", "weight": 2.0, "bandwidth_mbps": 1000},
        ],
    }

    graph = builder.build_from_config(raw_cfg)
    assert graph.number_of_nodes() == 2
    assert graph.number_of_edges() == 1
    assert graph.nodes["n1"]["status"] == "up"

    # Test status updates
    builder.update_node_status(graph, "n1", NodeStatus.DOWN)
    assert graph.nodes["n1"]["status"] == "down"

    builder.update_link_status(graph, "n1", "n2", LinkStatus.DEGRADED)
    assert graph["n1"]["n2"]["status"] == "degraded"

    builder.update_link_weight(graph, "n1", "n2", latency_ms=50.0)
    assert graph["n1"]["n2"]["weight"] == 5.0
    assert graph["n1"]["n2"]["latency_ms"] == 50.0

    # Snapshot test
    snapshot = builder.get_topology_snapshot(graph)
    assert snapshot["summary"]["total_nodes"] == 2
    assert snapshot["summary"]["down_nodes"] == 1


def test_network_monitor_poll() -> None:
    """Test NetworkMonitor polling cycle and event publication."""
    async def _test() -> None:
        bus = EventBus()
        events_received: list[dict] = []

        async def on_metric(data: dict) -> None:
            events_received.append(data)

        bus.subscribe(EventType.METRIC_RECORDED, on_metric)

        builder = TopologyBuilder()
        graph = builder.build_from_config()
        set_topology(graph)

        monitor = NetworkMonitor(event_bus_instance=bus, topology_builder=builder)

        with patch.object(
            monitor.ping_probe,
            "probe",
            return_value=PingResult(
                host="192.168.1.1",
                reachable=True,
                avg_latency_ms=15.0,
                packet_loss_pct=0.0,
                min_latency_ms=14.0,
                max_latency_ms=16.0,
                jitter_ms=1.0,
            ),
        ):
            results = await monitor.poll_all_nodes()
            assert len(results) > 0
            assert len(events_received) == len(results)
            assert results[0].status == NodeStatus.UP

    asyncio.run(_test())
