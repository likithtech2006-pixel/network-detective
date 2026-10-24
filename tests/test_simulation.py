"""Tests for src.simulation module: VirtualNetwork and FailureInjector."""

import asyncio

from src.core.events import EventBus, FAULT_DETECTED
from src.core.models import FaultType, LinkStatus, NodeStatus
from src.simulation.failure_injector import FailureInjector
from src.simulation.virtual_network import SimulatedResponse, VirtualNetwork


def test_virtual_network_basic_lifecycle() -> None:
    custom_config = {
        "nodes": [
            {"id": "n1", "name": "Node 1", "ip_address": "10.0.0.1", "node_type": "router"},
            {"id": "n2", "name": "Node 2", "ip_address": "10.0.0.2", "node_type": "switch"},
        ],
        "links": [
            {"source": "n1", "target": "n2", "weight": 2.5, "bandwidth_mbps": 1000.0},
        ],
    }

    vnet = VirtualNetwork(custom_config)

    # Initial state should be UP
    resp1 = vnet.get_node_response("n1")
    assert resp1.reachable is True
    assert resp1.status == "up"

    # Query by IP
    resp_ip = vnet.get_node_response("10.0.0.2")
    assert resp_ip.reachable is True
    assert resp_ip.status == "up"

    # Test Link response
    link_resp = vnet.get_link_response("n1", "n2")
    assert link_resp.reachable is True
    assert link_resp.status == "up"

    # Set node down
    vnet.set_node_status("n1", NodeStatus.DOWN)
    resp_down = vnet.get_node_response("n1")
    assert resp_down.reachable is False
    assert resp_down.packet_loss_pct == 100.0

    # Set link down
    vnet.set_link_status("n1", "n2", LinkStatus.DOWN)
    link_down = vnet.get_link_response("n1", "n2")
    assert link_down.reachable is False
    assert link_down.packet_loss_pct == 100.0

    # Reset
    vnet.reset()
    assert vnet.get_node_response("n1").reachable is True
    assert vnet.get_link_response("n1", "n2").reachable is True


def test_virtual_network_degradation() -> None:
    vnet = VirtualNetwork()
    # Inject latency & loss
    vnet.inject_latency("router-a", 350.0)
    vnet.inject_packet_loss("router-a", 25.0)

    resp = vnet.get_node_response("router-a")
    assert resp.reachable is True
    assert resp.latency_ms == 350.0
    assert resp.packet_loss_pct == 25.0
    assert resp.status == "degraded"


def test_failure_injector_workflow() -> None:
    async def _test() -> None:
        bus = EventBus()
        vnet = VirtualNetwork()
        injector = FailureInjector(virtual_network=vnet, event_bus=bus)

        events: list[dict] = []

        async def on_fault(data: dict) -> None:
            events.append(data)

        bus.subscribe(FAULT_DETECTED, on_fault)

        # 1. Inject node failure
        await injector.inject_node_failure("router-b")
        assert vnet.get_node_response("router-b").reachable is False
        assert len(events) == 1
        assert events[0]["incident"].fault_type == FaultType.NODE_DOWN
        assert events[0]["incident"].affected_component == "router-b"

        # 2. Recover node
        await injector.recover_node("router-b")
        assert vnet.get_node_response("router-b").reachable is True

        # 3. Inject link failure
        await injector.inject_link_failure("router-b", "switch-c")
        assert vnet.get_link_response("router-b", "switch-c").reachable is False
        assert len(events) == 2
        assert events[1]["incident"].fault_type == FaultType.LINK_DOWN

        # 4. Check history log
        history = injector.get_history()
        assert len(history) >= 2

    asyncio.run(_test())
