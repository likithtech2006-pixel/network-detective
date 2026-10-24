"""Main network monitoring orchestrator managing periodic polling, telemetry collection, and event publishing."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.core.config import Settings, get_settings
from src.core.events import EventBus, EventType
from src.core.events import event_bus as default_event_bus
from src.core.models import NodeStatus
from src.monitor.metrics_collector import MetricsCollector
from src.monitor.ping_probe import PingProbe, PingResult
from src.monitor.tcp_probe import TcpProbe, TcpResult
from src.monitor.topology_builder import TopologyBuilder, get_topology
from src.utils.logger import logger


@dataclass
class MonitorResult:
    """Aggregated probe outcome for a single network node."""

    node_id: str
    ip: str
    ping_result: PingResult
    status: NodeStatus
    status_changed: bool
    previous_status: NodeStatus
    tcp_results: dict[int, TcpResult] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert dataclass fields to a standard dictionary."""
        d = asdict(self)
        d["status"] = self.status.value
        d["previous_status"] = self.previous_status.value
        return d


class NetworkMonitor:
    """Coordinates telemetry polling across network infrastructure and broadcasts state changes."""

    def __init__(
        self,
        config: Settings | None = None,
        metrics_collector: MetricsCollector | None = None,
        topology_builder: TopologyBuilder | None = None,
        event_bus_instance: EventBus | None = None,
        ping_probe: PingProbe | None = None,
        tcp_probe: TcpProbe | None = None,
    ) -> None:
        """Initialize NetworkMonitor with configuration, collectors, and probers.

        Args:
            config: Application configuration. Defaults to get_settings().
            metrics_collector: Collector for rolling window and DB telemetry storage.
            topology_builder: Topology builder and graph manager.
            event_bus_instance: Event bus for emitting telemetry and topology events.
            ping_probe: Custom ICMP prober.
            tcp_probe: Custom TCP prober.
        """
        self.config = config or get_settings()
        self.metrics_collector = metrics_collector or MetricsCollector()
        self.topology_builder = topology_builder or TopologyBuilder()
        self.event_bus = event_bus_instance or default_event_bus

        # Ping and TCP probers
        timeout = float(self.config.thresholds.ping_timeout_sec)
        self.ping_probe = ping_probe or PingProbe(default_timeout=timeout, default_count=3)
        self.tcp_probe = tcp_probe or TcpProbe(default_timeout=timeout)

        # In-memory tracking of consecutive failure counts and previous states
        self._consecutive_failures: dict[str, int] = {}
        self._node_statuses: dict[str, NodeStatus] = {}

        # Scheduler references
        self._scheduler: Any = None
        self._polling_task: asyncio.Task[None] | None = None
        self._is_running = False

    async def poll_node(
        self,
        node_id: str,
        ip: str,
        probe_tcp: bool = False,
    ) -> MonitorResult:
        """Probe an individual network node using ICMP and optional TCP port checks.

        Evaluates node state (UP, DOWN, DEGRADED) and tracks state transitions.

        Args:
            node_id: Monitored node ID.
            ip: Node IP address to probe.
            probe_tcp: Whether to also run TCP checks on standard ports.

        Returns:
            MonitorResult with telemetry details and status changes.
        """
        ping_res = await self.ping_probe.probe(
            host=ip,
            timeout=float(self.config.thresholds.ping_timeout_sec),
        )

        tcp_results: dict[int, TcpResult] = {}
        if probe_tcp:
            try:
                tcp_results = await self.tcp_probe.probe_common_ports(
                    host=ip,
                    timeout=float(self.config.thresholds.ping_timeout_sec),
                )
            except Exception as exc:
                logger.debug("TCP probe skipped or failed for {}: {}", ip, exc)

        # Track consecutive failures for outage detection
        prev_status = self._node_statuses.get(node_id, NodeStatus.UP)
        max_retries = int(self.config.thresholds.max_retries)

        if not ping_res.reachable:
            self._consecutive_failures[node_id] = self._consecutive_failures.get(node_id, 0) + 1
            if self._consecutive_failures[node_id] >= max_retries:
                new_status = NodeStatus.DOWN
            else:
                new_status = NodeStatus.DEGRADED
        else:
            self._consecutive_failures[node_id] = 0
            # Check if degraded due to packet loss or latency thresholds
            crit_loss = float(self.config.thresholds.packet_loss_critical_pct)
            crit_lat = float(self.config.thresholds.latency_critical_ms)

            latency = ping_res.avg_latency_ms or 0.0
            if ping_res.packet_loss_pct >= crit_loss or latency >= crit_lat:
                new_status = NodeStatus.DEGRADED
            else:
                new_status = NodeStatus.UP

        status_changed = prev_status != new_status
        self._node_statuses[node_id] = new_status

        return MonitorResult(
            node_id=node_id,
            ip=ip,
            ping_result=ping_res,
            status=new_status,
            status_changed=status_changed,
            previous_status=prev_status,
            tcp_results=tcp_results,
        )

    async def poll_all_nodes(self) -> list[MonitorResult]:
        """Perform a complete monitoring polling cycle across all configured nodes.

        Records metrics, updates the topology graph, and fires system events.

        Returns:
            List of MonitorResult objects for all polled nodes.
        """
        logger.debug("Starting polling cycle across configured nodes")
        nodes = self.config.network.nodes
        graph = get_topology()

        # Run node probes concurrently
        async def _probe(node: Any) -> MonitorResult:
            n_id = node.id if hasattr(node, "id") else node["id"]
            n_ip = node.ip_address if hasattr(node, "ip_address") else node.get("ip_address", "127.0.0.1")
            return await self.poll_node(node_id=n_id, ip=n_ip)

        tasks = [_probe(node) for node in nodes]
        results: list[MonitorResult] = await asyncio.gather(*tasks, return_exceptions=False)

        topology_changed = False

        for res in results:
            latency = res.ping_result.avg_latency_ms if res.ping_result.avg_latency_ms is not None else 999.0
            loss = res.ping_result.packet_loss_pct
            jitter = res.ping_result.jitter_ms

            # 1. Record telemetry metrics
            await self.metrics_collector.record_metric(
                node_id=res.node_id,
                latency_ms=latency,
                packet_loss_pct=loss,
                jitter_ms=jitter,
            )

            # 2. Update topology graph node status
            self.topology_builder.update_node_status(
                graph=graph,
                node_id=res.node_id,
                status=res.status,
            )

            # 3. Update dynamic edge weights for adjacent links
            if graph.has_node(res.node_id):
                for neighbor in graph.neighbors(res.node_id):
                    self.topology_builder.update_link_weight(
                        graph=graph,
                        source=res.node_id,
                        target=neighbor,
                        latency_ms=latency,
                    )
                    # If node is completely DOWN, mark incident links as DOWN
                    if res.status == NodeStatus.DOWN:
                        self.topology_builder.update_link_status(
                            graph=graph,
                            source=res.node_id,
                            target=neighbor,
                            status="down",
                        )
                    elif res.previous_status == NodeStatus.DOWN and res.status == NodeStatus.UP:
                        self.topology_builder.update_link_status(
                            graph=graph,
                            source=res.node_id,
                            target=neighbor,
                            status="up",
                        )

            # 4. Check if topology state changed
            if res.status_changed:
                topology_changed = True
                logger.warning(
                    "Node '{}' status transition: {} -> {}",
                    res.node_id,
                    res.previous_status.value,
                    res.status.value,
                )

            # 5. Publish METRIC_RECORDED event
            await self.event_bus.publish(
                EventType.METRIC_RECORDED,
                {
                    "node_id": res.node_id,
                    "ip": res.ip,
                    "latency_ms": latency,
                    "packet_loss_pct": loss,
                    "jitter_ms": jitter,
                    "reachable": res.ping_result.reachable,
                    "status": res.status.value,
                    "consecutive_failures": self._consecutive_failures.get(res.node_id, 0),
                    "timestamp": res.timestamp,
                },
            )

        # 6. Publish TOPOLOGY_UPDATED event if any status changed
        if topology_changed:
            snapshot = self.topology_builder.get_topology_snapshot(graph)
            await self.event_bus.publish(EventType.TOPOLOGY_UPDATED, snapshot)

        return results

    async def start_monitoring(self) -> None:
        """Start the periodic network polling scheduler."""
        if self._is_running:
            logger.info("Network monitor is already running")
            return

        self._is_running = True
        interval_sec = int(self.config.polling_interval_sec)
        logger.info("Starting network monitoring poller every {}s", interval_sec)

        # Try to use APScheduler if available
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler

            self._scheduler = AsyncIOScheduler()
            self._scheduler.add_job(
                self.poll_all_nodes,
                trigger="interval",
                seconds=interval_sec,
                id="network_monitor_poll",
                replace_existing=True,
                max_instances=1,
            )
            self._scheduler.start()
            logger.info("APScheduler started successfully for NetworkMonitor")
            # Run initial poll immediately
            asyncio.create_task(self.poll_all_nodes())
            return
        except ImportError:
            logger.info("APScheduler not installed; falling back to async background polling loop")
        except Exception as exc:
            logger.warning("APScheduler initialization failed: {}; using async polling loop", exc)

        # Fallback background loop
        async def _loop() -> None:
            while self._is_running:
                try:
                    await self.poll_all_nodes()
                except asyncio.CancelledError:
                    break
                except Exception as err:
                    logger.error("Error during scheduled polling iteration: {}", err)
                try:
                    await asyncio.sleep(interval_sec)
                except asyncio.CancelledError:
                    break

        self._polling_task = asyncio.create_task(_loop())

    async def stop_monitoring(self) -> None:
        """Gracefully stop the network monitoring poller."""
        if not self._is_running:
            return

        self._is_running = False
        logger.info("Stopping network monitor poller")

        if self._scheduler is not None:
            try:
                self._scheduler.shutdown(wait=False)
            except Exception as exc:
                logger.debug("Error stopping APScheduler: {}", exc)
            self._scheduler = None

        if self._polling_task is not None:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
            self._polling_task = None
