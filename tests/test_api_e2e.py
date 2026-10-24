"""End-to-end tests: the real FastAPI app, health monitor and healing loop, driven over HTTP.

The app runs against a temporary database with a fast probe interval, so each scenario
goes through detection, diagnosis, rerouting and verification exactly as in the demo.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterator
from typing import Any

import ping3
import pytest
from fastapi.testclient import TestClient

import src.api.routes.simulator as simulator_routes
import src.core.models as models
import src.monitor.topology_builder as topology_builder
from src.core.config import get_settings


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    """Start the app with an isolated database and fast monitoring."""
    db_path = tmp_path_factory.mktemp("e2e") / "e2e.db"
    overrides = {
        "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}",
        "MONITOR_INTERVAL_SEC": "0.1",
        "VERIFICATION_DELAY_SEC": "0.2",
    }
    saved = {key: os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    get_settings.cache_clear()
    models._database_instance = None
    topology_builder._current_topology = None
    simulator_routes._virtual_network = None
    simulator_routes._failure_injector = None

    from src.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client

    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    get_settings.cache_clear()
    models._database_instance = None
    topology_builder._current_topology = None
    simulator_routes._virtual_network = None
    simulator_routes._failure_injector = None


def wait_for(check: Callable[[], Any], timeout: float = 8.0) -> Any:
    """Poll until check() returns something truthy, or fail after the timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.05)
    raise AssertionError("condition not met in time")


KNOWN: set[str] = set()


def finished_incident(client: TestClient, component: str) -> dict[str, Any] | None:
    """This test's incident for a component, once healing has reached a final state."""
    for incident in client.get("/api/incidents").json():
        if incident["affected_component"] == component and incident["id"] not in KNOWN:
            return incident if incident["status"] in ("verified", "escalated") else None
    return None


def link_status(client: TestClient, link_id: str) -> str:
    links = client.get("/api/topology").json()["links"]
    return next(link["status"] for link in links if link["id"] == link_id)


@pytest.fixture(autouse=True)
def healthy_network(client: TestClient) -> None:
    """Every test starts from a healthy network and only sees its own incidents."""
    assert client.post("/api/simulator/reset").status_code == 200
    KNOWN.clear()
    KNOWN.update(incident["id"] for incident in client.get("/api/incidents").json())


def test_link_cut_is_detected_rerouted_and_verified(client: TestClient) -> None:
    assert client.post("/api/simulator/failure", json={"target_type": "link", "target_id": "link-b-c"}).status_code == 200

    incident = wait_for(lambda: finished_incident(client, "link-router-b-switch-c"))
    assert incident["status"] == "verified"
    assert incident["alternate_path"] == ["router-b", "server-d", "switch-c"]
    assert "pre-computed backup" in incident["resolution_notes"]
    assert link_status(client, "link-b-c") == "down"


def test_repaired_link_fails_back_and_closes_incident(client: TestClient) -> None:
    client.post("/api/simulator/failure", json={"target_type": "link", "target_id": "link-b-c"})
    wait_for(lambda: finished_incident(client, "link-router-b-switch-c"))

    client.post("/api/simulator/recover", json={"target_type": "link", "target_id": "link-b-c"})
    wait_for(
        lambda: "returned to the primary routes"
        in finished_incident(client, "link-router-b-switch-c")["resolution_notes"]
    )
    assert link_status(client, "link-b-c") == "up"


def test_crashed_transit_router_is_routed_around(client: TestClient) -> None:
    client.post("/api/simulator/failure", json={"target_type": "node", "target_id": "router-b"})

    incident = wait_for(lambda: finished_incident(client, "router-b"))
    assert incident["status"] == "verified"
    assert "router-b" not in incident["alternate_path"]


def test_failure_that_isolates_a_device_is_escalated(client: TestClient) -> None:
    client.post("/api/simulator/failure", json={"target_type": "link", "target_id": "link-c-e"})

    incident = wait_for(lambda: finished_incident(client, "link-switch-c-server-e"))
    assert incident["status"] == "escalated"
    assert "only connection to server-e" in incident["resolution_notes"]
    assert len(client.get("/api/incidents/active").json()) == 1

    client.post("/api/simulator/reset")
    assert client.get("/api/incidents/active").json() == []
    # Closing by hand keeps the honest outcome: it was never self-healed
    assert finished_incident(client, "link-switch-c-server-e")["status"] == "escalated"


def test_second_failure_avoids_the_first(client: TestClient) -> None:
    client.post("/api/simulator/failure", json={"target_type": "link", "target_id": "link-c-d"})
    wait_for(lambda: finished_incident(client, "link-switch-c-server-d"))

    client.post("/api/simulator/failure", json={"target_type": "link", "target_id": "link-b-c"})
    incident = wait_for(lambda: finished_incident(client, "link-router-b-switch-c"))
    # switch-c and server-e are now cut off: no detour may use the first broken link
    assert incident["status"] == "escalated"
    assert "switch-c" in incident["resolution_notes"]


def test_devices_and_wires_can_be_added_and_removed(client: TestClient) -> None:
    created = client.post(
        "/api/topology/nodes",
        json={"name": "Edge Switch F", "node_type": "switch", "ip_address": "192.168.1.6"},
    )
    assert created.status_code == 201
    node_id = created.json()["id"]
    assert node_id == "edge-switch-f"

    wire = client.post("/api/topology/links", json={"source": "router-a", "target": node_id})
    assert wire.status_code == 201
    duplicate = client.post("/api/topology/links", json={"source": node_id, "target": "router-a"})
    assert duplicate.status_code == 409

    topology = client.get("/api/topology").json()
    assert any(n["id"] == node_id for n in topology["nodes"])
    assert any(link["id"] == wire.json()["id"] for link in topology["links"])

    moved = client.patch(f"/api/topology/nodes/{node_id}", json={"x": 123.0, "y": 456.0})
    assert moved.status_code == 200
    node = next(n for n in client.get("/api/topology").json()["nodes"] if n["id"] == node_id)
    assert (node["x"], node["y"]) == (123.0, 456.0)

    removed = client.delete(f"/api/topology/nodes/{node_id}")
    assert removed.json()["removed_links"] == 1
    topology = client.get("/api/topology").json()
    assert all(n["id"] != node_id for n in topology["nodes"])
    assert all(node_id not in link["id"] for link in topology["links"])


def test_invalid_requests_are_rejected(client: TestClient) -> None:
    bad_ip = client.post(
        "/api/topology/nodes", json={"name": "Bad", "node_type": "router", "ip_address": "not an ip"}
    )
    assert bad_ip.status_code == 400
    taken_ip = client.post(
        "/api/topology/nodes", json={"name": "Copy", "node_type": "router", "ip_address": "192.168.1.1"}
    )
    assert taken_ip.status_code == 409
    assert client.post("/api/simulator/failure", json={"target_type": "node", "target_id": "nope"}).status_code == 404
    assert client.post("/api/topology/links", json={"source": "router-a", "target": "router-a"}).status_code == 400


def _can_ping_localhost() -> bool:
    try:
        return isinstance(ping3.ping("127.0.0.1", timeout=1), float)
    except Exception:
        return False


@pytest.mark.skipif(not _can_ping_localhost(), reason="ICMP ping not permitted here")
def test_live_mode_pings_real_devices(client: TestClient) -> None:
    created = client.post(
        "/api/topology/nodes",
        json={"name": "Loopback", "node_type": "server", "ip_address": "127.0.0.1"},
    )
    node_id = created.json()["id"]
    try:
        assert client.put("/api/network/mode", json={"mode": "live"}).json()["mode"] == "live"
        assert client.post("/api/network/ping", json={"address": "127.0.0.1"}).json()["reachable"]

        # The campus devices (192.168.1.x) do not exist, so real pings fail and are detected
        incident = wait_for(lambda: finished_incident(client, "router-a"), timeout=15)
        assert incident["fault_type"] == "node_down"

        # Crashing a device by hand is refused in live mode
        crash = client.post("/api/simulator/failure", json={"target_type": "node", "target_id": node_id})
        assert crash.status_code == 409
    finally:
        client.put("/api/network/mode", json={"mode": "simulation"})
        client.delete(f"/api/topology/nodes/{node_id}")


def test_healing_switch_escalates_instead_of_rerouting(client: TestClient) -> None:
    client.put("/api/config", json={"healing_enabled": False})
    try:
        client.post("/api/simulator/failure", json={"target_type": "link", "target_id": "link-b-c"})
        incident = wait_for(lambda: finished_incident(client, "link-router-b-switch-c"))
        assert incident["status"] == "escalated"
        assert "Self-healing is turned off" in incident["resolution_notes"]
    finally:
        client.put("/api/config", json={"healing_enabled": True})
