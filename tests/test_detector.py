"""Unit and integration tests for the Detector module."""

from __future__ import annotations

import asyncio
from pathlib import Path

import networkx as nx

from src.core.events import EventBus, EventType
from src.core.models import (
    ActionType,
    Database,
    FaultType,
    IncidentStatus,
)
from src.detector.alert_manager import AlertManager
from src.detector.anomaly_detector import AnomalyDetector, AnomalyResult
from src.detector.diagnoser import Diagnoser, DiagnosisResult
from src.detector.fault_classifier import Fault, FaultClassifier
from src.detector.fault_detector import FaultDetector
from src.detector.threshold_engine import ThresholdEngine, ThresholdViolation
from src.monitor.topology_builder import TopologyBuilder, set_topology


async def _isolated_db(tmp_path: Path) -> Database:
    """Create a throwaway database so AlertManager never writes to the app's database."""
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.create_all()
    return db


def test_threshold_engine() -> None:
    """Test ThresholdEngine evaluation against warning and critical thresholds."""
    engine = ThresholdEngine(
        latency_warn=100.0,
        latency_critical=200.0,
        loss_warn=5.0,
        loss_critical=10.0,
        max_retries=3,
    )

    # 1. Healthy
    violations = engine.check("node-1", latency_ms=25.0, packet_loss_pct=0.0, reachable=True)
    assert len(violations) == 0

    # 2. Latency Warning
    v_warn = engine.check("node-1", latency_ms=120.0, packet_loss_pct=0.0, reachable=True)
    assert len(v_warn) == 1
    assert v_warn[0].violation_type == FaultType.HIGH_LATENCY
    assert v_warn[0].severity == "warn"

    # 3. Latency Critical
    v_crit = engine.check("node-1", latency_ms=250.0, packet_loss_pct=0.0, reachable=True)
    assert len(v_crit) == 1
    assert v_crit[0].violation_type == FaultType.HIGH_LATENCY
    assert v_crit[0].severity == "critical"

    # 4. Packet Loss Warning & Critical
    v_loss_warn = engine.check("node-1", latency_ms=20.0, packet_loss_pct=7.0, reachable=True)
    assert v_loss_warn[0].violation_type == FaultType.PACKET_LOSS
    assert v_loss_warn[0].severity == "warn"

    v_loss_crit = engine.check("node-1", latency_ms=20.0, packet_loss_pct=15.0, reachable=True)
    assert v_loss_crit[0].violation_type == FaultType.PACKET_LOSS
    assert v_loss_crit[0].severity == "critical"

    # 5. Node Down after max retries
    v_unreach_1 = engine.check("node-1", latency_ms=0, packet_loss_pct=100.0, reachable=False, consecutive_failures=2)
    assert len(v_unreach_1) == 1
    assert v_unreach_1[0].violation_type == FaultType.PACKET_LOSS

    v_down = engine.check("node-1", latency_ms=0, packet_loss_pct=100.0, reachable=False, consecutive_failures=3)
    assert any(v.violation_type == FaultType.NODE_DOWN and v.severity == "critical" for v in v_down)


def test_anomaly_detector() -> None:
    """Test rolling-window Z-score anomaly detector."""
    detector = AnomalyDetector(window_size=10, z_threshold=2.5, min_samples=5)

    # Warmup with consistent values ~ 10.0 ms
    for _ in range(5):
        res = detector.check("node-1", "latency_ms", 10.0)
        assert res.is_anomaly is False

    # Stable values with small variance
    detector.check("node-1", "latency_ms", 10.5)
    detector.check("node-1", "latency_ms", 9.5)
    detector.check("node-1", "latency_ms", 10.0)

    # Sudden extreme spike: 80.0 ms
    spike_res = detector.check("node-1", "latency_ms", 80.0)
    assert spike_res.is_anomaly is True
    assert spike_res.z_score >= 2.5
    assert spike_res.value == 80.0

    # Reset
    detector.reset("node-1")
    assert detector.get_baseline("node-1", "latency_ms")["sample_count"] == 0


def test_fault_classifier() -> None:
    """Test fault classification logic, corroboration, and priority ordering."""
    classifier = FaultClassifier()

    violations = [
        ThresholdViolation(
            node_id="node-1",
            violation_type=FaultType.HIGH_LATENCY,
            severity="critical",
            current_value=250.0,
            threshold_value=200.0,
        ),
        ThresholdViolation(
            node_id="node-1",
            violation_type=FaultType.PACKET_LOSS,
            severity="warn",
            current_value=6.0,
            threshold_value=5.0,
        ),
    ]

    # Corroborating anomaly for latency
    anomalies = [
        AnomalyResult(
            is_anomaly=True,
            z_score=3.2,
            mean=20.0,
            stdev=2.0,
            value=250.0,
            metric_name="latency_ms",
        )
    ]

    faults = classifier.classify(
        violations=violations,
        anomalies=anomalies,
        node_status="up",
        link_statuses={},
        node_id="node-1",
    )

    assert len(faults) == 2
    # Latency should rank before packet loss
    assert faults[0].fault_type == FaultType.HIGH_LATENCY
    assert faults[0].severity == "critical"
    assert faults[0].confidence >= 0.90  # Corroborated
    assert faults[1].fault_type == FaultType.PACKET_LOSS


def test_diagnoser() -> None:
    """Test topological root cause analysis and affected paths identification."""
    diagnoser = Diagnoser()

    # Build simple test topology: router-a -- switch-c -- server-d
    graph = nx.Graph()
    graph.add_node("router-a", type="router", status="up")
    graph.add_node("switch-c", type="switch", status="up")
    graph.add_node("server-d", type="server", status="up")
    graph.add_edge("router-a", "switch-c", weight=1.0, id="link-a-c")
    graph.add_edge("switch-c", "server-d", weight=1.0, id="link-c-d")

    # Fault on switch-c
    faults = [
        Fault(
            fault_type=FaultType.NODE_DOWN,
            affected_component="switch-c",
            severity="critical",
            confidence=0.95,
        ),
        Fault(
            fault_type=FaultType.HIGH_LATENCY,
            affected_component="server-d",
            severity="warn",
            confidence=0.80,
        ),
    ]

    diagnosis = diagnoser.diagnose(faults, graph)
    # switch-c is upstream of server-d and has NODE_DOWN -> root cause
    assert diagnosis.root_cause_component == "switch-c"
    assert diagnosis.fault_type == FaultType.NODE_DOWN
    assert len(diagnosis.affected_paths) > 0
    assert any("switch-c" in path for path in diagnosis.affected_paths)


def test_alert_manager(tmp_path: Path) -> None:
    """Test AlertManager incident creation, deduplication, and resolution."""
    async def _test() -> None:
        bus = EventBus()
        alerts_fired: list[dict] = []

        async def on_fault(data: dict) -> None:
            alerts_fired.append(data)

        bus.subscribe(EventType.FAULT_DETECTED, on_fault)

        db = await _isolated_db(tmp_path)
        manager = AlertManager(db=db, event_bus_instance=bus)

        diagnosis = DiagnosisResult(
            root_cause_component="switch-c",
            fault_type=FaultType.NODE_DOWN,
            affected_paths=[["router-a", "switch-c", "server-d"]],
            recommended_action="Reroute traffic around switch-c",
            action_type=ActionType.REROUTE,
        )

        # 1. Create initial alert
        incident = await manager.create_alert(diagnosis)
        assert incident is not None
        assert incident.affected_component == "switch-c"
        assert incident.status == IncidentStatus.DETECTED
        assert len(alerts_fired) == 1
        assert len(manager.get_active_incidents()) == 1

        # 2. Deduplication: second alert for switch-c should reuse the existing incident
        dup_incident = await manager.create_alert(diagnosis)
        assert dup_incident.id == incident.id
        assert len(alerts_fired) == 1  # No duplicate event published
        assert len(manager.get_active_incidents()) == 1

        # 3. Resolve incident
        resolved = await manager.resolve_incident(incident.id, "Rerouted successfully")
        assert resolved is not None
        assert resolved.status == IncidentStatus.VERIFIED
        assert len(manager.get_active_incidents()) == 0
        await db.close()

    asyncio.run(_test())


def test_fault_detector_pipeline(tmp_path: Path) -> None:
    """Test end-to-end telemetry event processing in FaultDetector."""
    async def _test() -> None:
        bus = EventBus()
        builder = TopologyBuilder()
        graph = builder.build_from_config()
        set_topology(graph)

        db = await _isolated_db(tmp_path)
        alert_mgr = AlertManager(db=db, event_bus_instance=bus)
        detector = FaultDetector(alert_manager=alert_mgr, event_bus_instance=bus)

        # Healthy telemetry -> no incident
        inc_healthy = await detector.on_metric_recorded({
            "node_id": "router-a",
            "latency_ms": 15.0,
            "packet_loss_pct": 0.0,
            "reachable": True,
            "status": "up",
        })
        assert inc_healthy is None

        # Telemetry with high latency breach (> 200 ms)
        inc_fault = await detector.on_metric_recorded({
            "node_id": "router-a",
            "latency_ms": 250.0,
            "packet_loss_pct": 0.0,
            "reachable": True,
            "status": "up",
        })
        assert inc_fault is not None
        assert inc_fault.affected_component == "router-a"
        assert inc_fault.fault_type == FaultType.HIGH_LATENCY
        await db.close()

    asyncio.run(_test())
