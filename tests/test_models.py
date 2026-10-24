"""Tests for src.core.models SQLAlchemy 2.0 ORM definitions."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from src.core.models import (
    ActionResult,
    ActionType,
    Base,
    FaultType,
    HealingAction,
    Incident,
    IncidentStatus,
    Link,
    LinkStatus,
    Metric,
    Node,
    NodeStatus,
)


def test_models_crud_and_serialization() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        node_a = Node(
            id="router-a",
            name="Router A",
            ip_address="192.168.1.1",
            node_type="router",
            status=NodeStatus.UP,
        )
        node_b = Node(
            id="router-b",
            name="Router B",
            ip_address="192.168.1.2",
            node_type="router",
            status=NodeStatus.UP,
        )
        session.add_all([node_a, node_b])
        session.flush()

        link = Link(
            id="link-a-b",
            source_node_id="router-a",
            target_node_id="router-b",
            status=LinkStatus.UP,
            weight=1.0,
            bandwidth_mbps=1000.0,
        )
        session.add(link)
        session.flush()

        metric = Metric(
            node_id="router-a",
            link_id="link-a-b",
            latency_ms=25.0,
            packet_loss_pct=0.0,
            jitter_ms=2.0,
        )
        session.add(metric)
        session.flush()

        incident = Incident(
            fault_type=FaultType.LINK_DOWN,
            affected_component="link-a-b",
            status=IncidentStatus.DETECTED,
            source_node="router-a",
            target_node="router-b",
            original_path=["router-a", "router-b"],
            alternate_path=["router-a", "switch-c", "router-b"],
        )
        session.add(incident)
        session.flush()

        healing = HealingAction(
            incident_id=incident.id,
            action_type=ActionType.REROUTE,
            old_route=["router-a", "router-b"],
            new_route=["router-a", "switch-c", "router-b"],
            result=ActionResult.SUCCESS,
        )
        session.add(healing)
        session.commit()

        # Validations
        node_dict = node_a.to_dict()
        assert node_dict["id"] == "router-a"
        assert node_dict["status"] == "up"

        link_dict = link.to_dict()
        assert link_dict["source_node_id"] == "router-a"
        assert link_dict["target_node_id"] == "router-b"

        metric_dict = metric.to_dict()
        assert metric_dict["latency_ms"] == 25.0

        incident_dict = incident.to_dict()
        assert incident_dict["fault_type"] == "link_down"
        assert incident_dict["status"] == "detected"

        healing_dict = healing.to_dict()
        assert healing_dict["action_type"] == "reroute"
        assert healing_dict["result"] == "success"
