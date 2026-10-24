import asyncio
import pytest
import networkx as nx

from src.core.events import EventBus, FAULT_DETECTED, HEALING_COMPLETE
from src.core.models import (
    ActionResult,
    ActionType,
    FaultType,
    Incident,
    IncidentStatus,
)
from src.healer.path_finder import PathFinder
from src.healer.route_manager import RouteManager
from src.healer.traffic_redirector import TrafficRedirector
from src.healer.self_healer import SelfHealer


@pytest.fixture
def sample_topology() -> nx.Graph:
    """Creates a sample 5-node topology graph for routing tests:
    
    router-a ---1--- router-b ---2--- switch-c ---2--- server-e
       |                |                 |
       5                3                 2
       |                |                 |
    server-d -----------+-----------------+
    """
    g = nx.Graph()
    nodes = ["router-a", "router-b", "switch-c", "server-d", "server-e"]
    for n in nodes:
        g.add_node(n, status="up")

    g.add_edge("router-a", "router-b", weight=1.0, bandwidth_mbps=1000.0)
    g.add_edge("router-b", "switch-c", weight=2.0, bandwidth_mbps=100.0)
    g.add_edge("router-b", "server-d", weight=3.0, bandwidth_mbps=100.0)
    g.add_edge("switch-c", "server-d", weight=2.0, bandwidth_mbps=100.0)
    g.add_edge("switch-c", "server-e", weight=2.0, bandwidth_mbps=100.0)
    g.add_edge("router-a", "server-d", weight=5.0, bandwidth_mbps=100.0)
    return g


def test_path_finder_shortest_path(sample_topology: nx.Graph) -> None:
    pf = PathFinder()
    
    # Normal shortest path from router-a to switch-c: router-a -> router-b -> switch-c (cost: 3.0)
    path = pf.find_shortest_path(sample_topology, "router-a", "switch-c")
    assert path == ["router-a", "router-b", "switch-c"]

    # If edge router-b <-> switch-c is excluded:
    # Alternate: router-a -> router-b -> server-d -> switch-c (cost: 1 + 3 + 2 = 6.0)
    alt_path = pf.find_shortest_path(
        sample_topology,
        "router-a",
        "switch-c",
        excluded_edges=[("router-b", "switch-c")],
    )
    assert alt_path == ["router-a", "router-b", "server-d", "switch-c"]

    # If router-b is excluded:
    # Alternate: router-a -> server-d -> switch-c (cost: 5 + 2 = 7.0)
    alt_path_node = pf.find_shortest_path(
        sample_topology,
        "router-a",
        "switch-c",
        excluded_nodes=["router-b"],
    )
    assert alt_path_node == ["router-a", "server-d", "switch-c"]


def test_path_finder_k_shortest_paths(sample_topology: nx.Graph) -> None:
    pf = PathFinder()
    paths = pf.find_k_shortest_paths(sample_topology, "router-a", "server-e", k=3)
    assert len(paths) >= 2
    assert paths[0] == ["router-a", "router-b", "switch-c", "server-e"]
    for p in paths:
        assert p[0] == "router-a"
        assert p[-1] == "server-e"


def test_path_finder_cost_and_component_search(sample_topology: nx.Graph) -> None:
    pf = PathFinder()
    cost = pf.compute_path_cost(sample_topology, ["router-a", "router-b", "switch-c"])
    assert cost == 3.0

    affected = pf.get_all_paths_through_component(sample_topology, "switch-c")
    assert len(affected) > 0


def test_route_manager(sample_topology: nx.Graph) -> None:
    rm = RouteManager()
    rm.set_initial_routes_from_graph(sample_topology)

    route = rm.get_current_route("router-a", "server-e")
    assert route == ["router-a", "router-b", "switch-c", "server-e"]

    # Apply reroute
    new_path = ["router-a", "server-d", "switch-c", "server-e"]
    rm.apply_route("router-a", "server-e", new_path)
    assert rm.get_current_route("router-a", "server-e") == new_path

    # Check affected routes
    affected = rm.get_affected_routes("server-d")
    assert ("router-a", "server-e") in affected

    # Rollback
    rm.rollback_route("router-a", "server-e", ["router-a", "router-b", "switch-c", "server-e"])
    assert rm.get_current_route("router-a", "server-e") == ["router-a", "router-b", "switch-c", "server-e"]


def test_traffic_redirector() -> None:
    async def _test() -> None:
        rm = RouteManager()
        redirector = TrafficRedirector(rm, simulation_mode=True)

        result = await redirector.redirect(
            "router-a",
            "switch-c",
            ["router-a", "router-b", "switch-c"],
            ["router-a", "server-d", "switch-c"],
        )
        assert result.success is True
        assert result.new_path == ["router-a", "server-d", "switch-c"]
        assert rm.get_current_route("router-a", "switch-c") == ["router-a", "server-d", "switch-c"]

    asyncio.run(_test())


def test_self_healer_event_flow(sample_topology: nx.Graph) -> None:
    async def _test() -> None:
        bus = EventBus()
        rm = RouteManager()
        rm.set_initial_routes_from_graph(sample_topology)
        pf = PathFinder()
        redirector = TrafficRedirector(rm, simulation_mode=True)

        healer = SelfHealer(
            path_finder=pf,
            route_manager=rm,
            traffic_redirector=redirector,
            event_bus=bus,
            topology=sample_topology,
        )

        completed_events: list[dict] = []

        async def on_healing_complete(data: dict) -> None:
            completed_events.append(data)

        bus.subscribe(HEALING_COMPLETE, on_healing_complete)

        incident = Incident(
            id=101,
            fault_type=FaultType.LINK_DOWN,
            affected_component="link-router-b-switch-c",
            status=IncidentStatus.DETECTED,
            source_node="router-b",
            target_node="switch-c",
        )

        await bus.publish(FAULT_DETECTED, {"incident": incident, "diagnosis": None})

        assert len(completed_events) == 1
        event_data = completed_events[0]
        assert event_data["incident"].status == IncidentStatus.HEALING
        assert event_data["healing_action"].result == ActionResult.SUCCESS
        assert event_data["healing_action"].action_type == ActionType.REROUTE

    asyncio.run(_test())

