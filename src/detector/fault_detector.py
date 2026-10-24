"""Main fault detection orchestrator executing thresholds, anomalies, classification, and alerts."""

from __future__ import annotations

from typing import Any

from src.core.events import EventBus, EventType
from src.core.events import event_bus as default_event_bus
from src.core.models import Incident, LinkStatus
from src.detector.alert_manager import AlertManager
from src.detector.anomaly_detector import AnomalyDetector, AnomalyResult
from src.detector.diagnoser import Diagnoser, DiagnosisResult
from src.detector.fault_classifier import Fault, FaultClassifier
from src.detector.threshold_engine import ThresholdEngine, ThresholdViolation
from src.monitor.topology_builder import get_topology
from src.utils.logger import logger


class FaultDetector:
    """Orchestrates the real-time anomaly detection, fault classification, diagnosis, and alerting pipeline."""

    def __init__(
        self,
        threshold_engine: ThresholdEngine | None = None,
        anomaly_detector: AnomalyDetector | None = None,
        fault_classifier: FaultClassifier | None = None,
        diagnoser: Diagnoser | None = None,
        alert_manager: AlertManager | None = None,
        event_bus_instance: EventBus | None = None,
    ) -> None:
        """Initialize FaultDetector with component pipeline stages and wire event bus listeners.

        Args:
            threshold_engine: Static threshold evaluation engine.
            anomaly_detector: Statistical Z-score anomaly detector.
            fault_classifier: Fault classifier combining violations & anomalies.
            diagnoser: Topological root-cause diagnosis engine.
            alert_manager: Incident record creator and notification manager.
            event_bus_instance: Pub/sub event bus.
        """
        self.threshold_engine = threshold_engine or ThresholdEngine()
        self.anomaly_detector = anomaly_detector or AnomalyDetector()
        self.fault_classifier = fault_classifier or FaultClassifier()
        self.diagnoser = diagnoser or Diagnoser()
        self.alert_manager = alert_manager or AlertManager()
        self.event_bus = event_bus_instance or default_event_bus

        # Track consecutive failures per node
        self._consecutive_failures: dict[str, int] = {}

        # Subscribe to telemetry and topology events
        self._subscribe_events()

    def _subscribe_events(self) -> None:
        """Register listeners on the shared event bus."""
        self.event_bus.subscribe(EventType.METRIC_RECORDED, self.on_metric_recorded)
        self.event_bus.subscribe(EventType.TOPOLOGY_UPDATED, self.on_topology_updated)
        logger.info("FaultDetector subscribed to METRIC_RECORDED and TOPOLOGY_UPDATED events")

    async def on_metric_recorded(self, data: Any, extra: Any = None) -> Incident | None:
        """Event handler triggered whenever new telemetry is published for a node.

        Runs the end-to-end detection pipeline:
        1. Evaluates static threshold breaches
        2. Detects statistical Z-score anomalies
        3. Classifies and prioritizes active faults
        4. Performs topological root-cause diagnosis
        5. Logs and alerts incidents via AlertManager

        Args:
            data: Telemetry event payload dictionary (or event topic string if 2 args passed).
            extra: Optional payload if event bus passed (event_type, data).

        Returns:
            Created or updated Incident, or None if network is healthy.
        """
        payload = extra if extra is not None else data
        if not isinstance(payload, dict):
            return None

        node_id = str(payload.get("node_id", ""))
        if not node_id:
            return None

        latency_ms = float(payload.get("latency_ms", 0.0))
        packet_loss_pct = float(payload.get("packet_loss_pct", 0.0))
        reachable = bool(payload.get("reachable", True))
        status = str(payload.get("status", "up"))

        # Maintain consecutive failures
        if not reachable:
            self._consecutive_failures[node_id] = self._consecutive_failures.get(node_id, 0) + 1
        else:
            self._consecutive_failures[node_id] = 0

        consecutive = self._consecutive_failures[node_id]

        # Execute detection pipeline
        faults, diagnosis, incident = await self.process_telemetry(
            node_id=node_id,
            latency_ms=latency_ms,
            packet_loss_pct=packet_loss_pct,
            reachable=reachable,
            status=status,
            consecutive_failures=consecutive,
        )

        return incident

    async def process_telemetry(
        self,
        node_id: str,
        latency_ms: float,
        packet_loss_pct: float,
        reachable: bool,
        status: str = "up",
        consecutive_failures: int = 0,
    ) -> tuple[list[Fault], DiagnosisResult | None, Incident | None]:
        """Execute the full detection pipeline directly for a single telemetry sample.

        Args:
            node_id: Monitored node ID.
            latency_ms: Measured latency in milliseconds.
            packet_loss_pct: Packet loss percentage (0-100).
            reachable: Reachability boolean.
            status: Operational status ('up', 'down', 'degraded').
            consecutive_failures: Count of consecutive failed probes.

        Returns:
            Tuple of (classified_faults, diagnosis_result, incident_record).
        """
        # Step 1: Static Threshold Evaluation
        violations: list[ThresholdViolation] = self.threshold_engine.check(
            node_id=node_id,
            latency_ms=latency_ms,
            packet_loss_pct=packet_loss_pct,
            reachable=reachable,
            consecutive_failures=consecutive_failures,
        )

        # Step 2: Statistical Anomaly Detection
        anomalies: list[AnomalyResult] = []
        if reachable and latency_ms >= 0:
            anom_lat = self.anomaly_detector.check(
                node_id=node_id,
                metric_name="latency_ms",
                value=latency_ms,
            )
            anomalies.append(anom_lat)

        anom_loss = self.anomaly_detector.check(
            node_id=node_id,
            metric_name="packet_loss_pct",
            value=packet_loss_pct,
        )
        anomalies.append(anom_loss)

        # Step 3: Link status extraction from current topology
        topology = get_topology()
        link_statuses: dict[str, str] = {}
        if topology.has_node(node_id):
            for neighbor in topology.neighbors(node_id):
                edge_attrs = topology.get_edge_data(node_id, neighbor, default={})
                link_id = edge_attrs.get("id", f"link-{node_id}-{neighbor}")
                link_stat = edge_attrs.get("status", LinkStatus.UP.value)
                link_statuses[link_id] = link_stat

        # Step 4: Fault Classification
        faults = self.fault_classifier.classify(
            violations=violations,
            anomalies=anomalies,
            node_status=status,
            link_statuses=link_statuses,
            node_id=node_id,
        )

        if not faults:
            return [], None, None

        # Step 5: Root Cause Diagnosis & Path Analysis
        diagnosis = self.diagnoser.diagnose(faults=faults, topology=topology)

        # Step 6: Incident Creation & Alert Notification
        incident = await self.alert_manager.create_alert(diagnosis)

        return faults, diagnosis, incident

    async def on_topology_updated(self, data: Any, extra: Any = None) -> None:
        """Event handler invoked when topology updates occur.

        Args:
            data: Topology snapshot payload or event topic.
            extra: Optional secondary payload.
        """
        payload = extra if extra is not None else data
        summary = payload.get("summary") if isinstance(payload, dict) else None
        logger.debug("FaultDetector acknowledged topology update: {}", summary)

    def get_active_incidents(self) -> list[Incident]:
        """Return all active unresolved incidents from the alert manager."""
        return self.alert_manager.get_active_incidents()
