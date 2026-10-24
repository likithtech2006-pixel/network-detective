"""Pydantic v2 schemas for API requests, responses, and serialization.

Provides strict data validation and serialization for network topology, nodes,
links, metrics, incidents, healing actions, simulation commands, and dashboard stats.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.core.models import (
    ActionResult,
    ActionType,
    FaultType,
    IncidentStatus,
    LinkStatus,
    NodeStatus,
)

# ==============================================================================
# Common & Base Schemas
# ==============================================================================


class BaseSchema(BaseModel):
    """Base schema configured for ORM compatibility."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )

    @field_validator("*", mode="after")
    @classmethod
    def _assume_utc(cls, value: Any) -> Any:
        """Times are stored in UTC without a zone (SQLite drops it); send them marked as UTC."""
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class MessageResponse(BaseSchema):
    """Generic status/message response."""

    status: str = Field(default="ok", description="Status code or summary ('ok', 'error')")
    message: str = Field(..., description="Human-readable informational message")
    data: dict[str, Any] | None = Field(default=None, description="Optional payload")


# ==============================================================================
# Node & Link Schemas
# ==============================================================================


class NodeResponse(BaseSchema):
    """Network device response schema."""

    id: str = Field(..., description="Unique node identifier (e.g. 'router-a')")
    name: str = Field(..., description="Human-readable node label")
    ip_address: str = Field(..., description="IPv4 or IPv6 address")
    node_type: str = Field(default="router", description="Device type ('router', 'switch', 'server')")
    status: NodeStatus | str = Field(default=NodeStatus.UP, description="Current operational status")
    last_seen: datetime | None = Field(default=None, description="Timestamp of last successful probe")
    x: float | None = Field(default=None, description="Layout X coordinate for visualization")
    y: float | None = Field(default=None, description="Layout Y coordinate for visualization")


class NodeCreateRequest(BaseSchema):
    """Add a device in the topology editor."""

    name: str = Field(..., description="Display name, e.g. 'Core Router'")
    node_type: Literal["router", "switch", "server"] = Field(..., description="Device type")
    ip_address: str = Field(..., description="IP address or hostname that live mode pings")
    x: float | None = Field(default=None, description="Canvas X position")
    y: float | None = Field(default=None, description="Canvas Y position")


class NodeUpdateRequest(BaseSchema):
    """Change a device's name, type, address or canvas position."""

    name: str | None = None
    node_type: Literal["router", "switch", "server"] | None = None
    ip_address: str | None = None
    x: float | None = None
    y: float | None = None


class LinkCreateRequest(BaseSchema):
    """Connect two devices with a wire."""

    source: str = Field(..., description="Device ID at one end")
    target: str = Field(..., description="Device ID at the other end")
    weight: float = Field(default=1.0, gt=0, description="Routing cost; also sets simulated delay")
    bandwidth_mbps: float = Field(default=100.0, gt=0, description="Link capacity in Mbit/s")


class NetworkModeRequest(BaseSchema):
    """Choose what the health monitor probes."""

    mode: Literal["simulation", "live"]


class PingRequest(BaseSchema):
    """Test whether an address answers before adding it as a device."""

    address: str


class LinkResponse(BaseSchema):
    """Network link response schema."""

    id: str = Field(..., description="Unique link identifier (e.g. 'link-a-b')")
    source_node_id: str = Field(..., description="Source node ID")
    target_node_id: str = Field(..., description="Target node ID")
    source: str | None = Field(default=None, description="Source node ID alias")
    target: str | None = Field(default=None, description="Target node ID alias")
    status: LinkStatus | str = Field(default=LinkStatus.UP, description="Current operational status")
    weight: float = Field(default=1.0, description="Routing cost / weight")
    bandwidth_mbps: float = Field(default=100.0, description="Bandwidth capacity in Mbps")


class TopologyResponse(BaseSchema):
    """Complete network topology graph representation."""

    nodes: list[NodeResponse] = Field(default_factory=list, description="List of network nodes")
    links: list[LinkResponse] = Field(default_factory=list, description="List of connecting links")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Metadata including network name, summary counts, layout"
    )


# ==============================================================================
# Telemetry Metric Schemas
# ==============================================================================


class MetricResponse(BaseSchema):
    """Recorded network metric data point."""

    id: int | None = Field(default=None, description="Database metric record ID")
    node_id: str = Field(..., description="Target node identifier")
    link_id: str | None = Field(default=None, description="Associated link identifier if link probe")
    latency_ms: float = Field(default=0.0, description="Round-trip latency in milliseconds")
    packet_loss_pct: float = Field(default=0.0, description="Packet loss percentage (0.0 - 100.0)")
    jitter_ms: float = Field(default=0.0, description="Jitter variation in milliseconds")
    recorded_at: datetime | None = Field(default=None, description="Timestamp when metric was sampled")


# ==============================================================================
# Healing Action & Incident Schemas
# ==============================================================================


class HealingActionResponse(BaseSchema):
    """Remediation action record executed for an incident."""

    id: str = Field(..., description="Unique healing action ID")
    incident_id: str = Field(..., description="Associated incident ID")
    action_type: ActionType | str = Field(..., description="Action performed ('reroute', 'rollback', 'escalate')")
    old_route: list[str] | None = Field(default=None, description="Original routing path")
    new_route: list[str] | None = Field(default=None, description="Alternate routing path applied")
    result: ActionResult | str = Field(..., description="Execution outcome ('success', 'failed')")
    executed_at: datetime = Field(..., description="Execution timestamp")
    details: str | None = Field(default=None, description="Additional execution logs or details")


class IncidentResponse(BaseSchema):
    """Network fault incident record."""

    id: str = Field(..., description="Unique incident ID")
    fault_type: FaultType | str = Field(..., description="Type of fault detected")
    affected_component: str = Field(..., description="Identifier of failed or degraded component")
    status: IncidentStatus | str = Field(..., description="Life cycle state of the incident")
    source_node: str | None = Field(default=None, description="Originating node of the affected flow")
    target_node: str | None = Field(default=None, description="Destination node of the affected flow")
    original_path: list[str] | None = Field(default=None, description="Pre-failure primary path")
    alternate_path: list[str] | None = Field(default=None, description="Computed or applied alternate path")
    detected_at: datetime = Field(..., description="Timestamp when fault was first flagged")
    resolved_at: datetime | None = Field(default=None, description="Timestamp when incident was verified resolved")
    resolution_notes: str | None = Field(default=None, description="Notes on root cause and remediation")
    healing_actions: list[HealingActionResponse] = Field(
        default_factory=list, description="List of healing actions taken"
    )


class IncidentStatsResponse(BaseSchema):
    """Aggregate statistics for incidents."""

    total_incidents: int = Field(default=0, description="Total count of recorded incidents")
    active_incidents: int = Field(default=0, description="Number of currently unresolved incidents")
    resolved_incidents: int = Field(default=0, description="Number of resolved incidents")
    by_status: dict[str, int] = Field(default_factory=dict, description="Counts grouped by IncidentStatus")
    by_fault_type: dict[str, int] = Field(default_factory=dict, description="Counts grouped by FaultType")
    avg_resolution_time_sec: float | None = Field(
        default=None, description="Mean resolution duration in seconds"
    )


# ==============================================================================
# Simulation Request & Response Schemas
# ==============================================================================


class SimulateFailureRequest(BaseSchema):
    """Request payload to inject a simulated failure into a node or link."""

    component_type: Literal["node", "link"] = Field(
        default="node",
        description="Target type: 'node' or 'link'",
    )
    component_id: str = Field(
        default="",
        description="Target node identifier or source node / link ID",
    )
    target_id: str | None = Field(
        default=None,
        description="Target node identifier (if component_type is 'link' and component_id is source)",
    )
    fault_type: str | None = Field(
        default=None,
        description="Type of fault to simulate ('node_down', 'link_down', 'link_degraded', 'high_latency', 'packet_loss')",
    )
    duration_sec: float | None = Field(
        default=None,
        description="Optional failure duration in seconds before automatic recovery",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, data: Any) -> Any:
        """Allow frontend naming ('target_type' / 'target_id') interchangeably."""
        if isinstance(data, dict):
            # Map target_type -> component_type if not provided
            if "target_type" in data and "component_type" not in data:
                data["component_type"] = data["target_type"]
            # If target_id is present and component_id is not:
            if "target_id" in data and "component_id" not in data:
                data["component_id"] = data["target_id"]
                data["target_id"] = None
        return data


class SimulateRecoverRequest(BaseSchema):
    """Request payload to recover a previously failed node or link."""

    component_type: Literal["node", "link"] = Field(
        default="node",
        description="Target type: 'node' or 'link'",
    )
    component_id: str = Field(
        default="",
        description="Target node identifier or link ID",
    )
    target_id: str | None = Field(
        default=None,
        description="Target node identifier (if component_type is 'link')",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, data: Any) -> Any:
        """Allow frontend naming ('target_type' / 'target_id') interchangeably."""
        if isinstance(data, dict):
            if "target_type" in data and "component_type" not in data:
                data["component_type"] = data["target_type"]
            if "target_id" in data and "component_id" not in data:
                data["component_id"] = data["target_id"]
                data["target_id"] = None
        return data


class SimulationStatusResponse(BaseSchema):
    """Current state of simulated network conditions."""

    simulation_active: bool = Field(default=False, description="True if any simulated faults are active")
    failed_nodes: list[str] = Field(default_factory=list, description="IDs of currently failed nodes")
    failed_links: list[str] = Field(default_factory=list, description="IDs of currently failed links")
    degraded_links: list[dict[str, Any]] = Field(
        default_factory=list, description="Links experiencing synthetic latency or loss"
    )
    active_injections: list[dict[str, Any]] = Field(
        default_factory=list, description="Detailed records of all active fault injections"
    )


# ==============================================================================
# Configuration Schemas
# ==============================================================================


class ThresholdsDict(BaseSchema):
    """Configurable detection thresholds."""

    latency_warn_ms: float = Field(default=100.0, description="Latency warning threshold (ms)")
    latency_critical_ms: float = Field(default=200.0, description="Latency critical threshold (ms)")
    packet_loss_warn_pct: float = Field(default=5.0, description="Packet loss warning threshold (%)")
    packet_loss_critical_pct: float = Field(default=10.0, description="Packet loss critical threshold (%)")
    ping_timeout_sec: float = Field(default=3.0, description="Ping probe timeout (seconds)")
    max_retries: int = Field(default=3, description="Consecutive retries before incident creation")


class ConfigResponse(BaseSchema):
    """Current application configuration response."""

    app_name: str = Field(default="Network Detective & Self-Healing Network")
    environment: str = Field(default="development")
    polling_interval_sec: int = Field(default=5, description="Polling interval in seconds")
    thresholds: ThresholdsDict = Field(default_factory=ThresholdsDict)
    auto_remediation_enabled: bool = Field(default=True)
    rollback_on_failure: bool = Field(default=True)


class ConfigUpdateRequest(BaseSchema):
    """Payload to update runtime operational parameters."""

    polling_interval_sec: int | None = Field(
        default=None, ge=1, le=3600, description="Polling interval in seconds"
    )
    thresholds: dict[str, Any] | None = Field(
        default=None, description="Dictionary of threshold overrides"
    )
    auto_remediation_enabled: bool | None = Field(
        default=None, description="Enable or disable autonomous remediation"
    )
    rollback_on_failure: bool | None = Field(
        default=None, description="Enable or disable automatic rollback on verification failure"
    )


# ==============================================================================
# Dashboard Aggregation Schemas
# ==============================================================================


class DashboardStats(BaseSchema):
    """Aggregated network health statistics for dashboard visualizer."""

    total_nodes: int = Field(default=0, description="Total number of nodes configured")
    nodes_up: int = Field(default=0, description="Count of nodes in UP status")
    nodes_down: int = Field(default=0, description="Count of nodes in DOWN status")
    total_links: int = Field(default=0, description="Total number of links configured")
    links_up: int = Field(default=0, description="Count of links in UP status")
    active_incidents: int = Field(default=0, description="Number of currently active/open incidents")
    resolved_incidents: int = Field(default=0, description="Number of resolved incidents")
    avg_latency_ms: float | None = Field(
        default=None, description="Mean latency of answered probes among the last 100, in ms"
    )
    avg_packet_loss_pct: float | None = Field(
        default=None, description="Mean packet loss across the last 100 probes"
    )
    uptime_pct: float = Field(default=100.0, description="Overall network availability percentage")


class SystemHealth(BaseSchema):
    """System health check diagnostic status."""

    status: str = Field(default="ok", description="Overall health: 'ok', 'degraded', 'error'")
    database: str = Field(default="connected", description="Database connection health")
    event_bus: str = Field(default="active", description="Event bus status")
    scheduler: str = Field(default="running", description="Scheduler status")
    uptime_pct: float = Field(default=100.0, description="Network device uptime percentage")
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
