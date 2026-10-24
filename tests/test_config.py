"""Tests for src.core.config Settings and YAML loader."""

from src.core.config import (
    LinkConfig,
    NetworkConfig,
    NodeConfig,
    ThresholdConfig,
    get_settings,
)


def test_get_settings_loads_successfully() -> None:
    settings = get_settings(reload=True)
    assert settings.app_name == "Network Detective & Self-Healing Network"
    assert settings.polling_interval_sec == 5
    assert settings.thresholds.latency_warn_ms == 100.0
    assert settings.thresholds.latency_critical_ms == 200.0
    assert settings.thresholds.packet_loss_warn_pct == 5.0
    assert settings.thresholds.packet_loss_critical_pct == 10.0
    assert settings.thresholds.ping_timeout_sec == 3.0
    assert settings.thresholds.max_retries == 3


def test_topology_loaded_from_yaml() -> None:
    settings = get_settings()
    assert len(settings.topology.nodes) == 5
    assert len(settings.topology.links) == 6

    node_ids = {n.id for n in settings.topology.nodes}
    assert "router-a" in node_ids
    assert "router-b" in node_ids
    assert "switch-c" in node_ids
    assert "server-d" in node_ids
    assert "server-e" in node_ids

    # Check a specific link
    link_ab = next(l for l in settings.topology.links if l.source == "router-a" and l.target == "router-b")
    assert link_ab.weight == 1.0
    assert link_ab.bandwidth_mbps == 1000.0


def test_models_direct_instantiation() -> None:
    node = NodeConfig(id="node-1", name="Node 1", ip_address="10.0.0.1", node_type="server")
    assert node.id == "node-1"

    link = LinkConfig(source="node-1", target="node-2", weight=2.5, bandwidth_mbps=100.0)
    assert link.id == "link-node-1-node-2"
    assert link.weight == 2.5

    net = NetworkConfig(nodes=[node], links=[link])
    assert len(net.nodes) == 1
    assert len(net.links) == 1
