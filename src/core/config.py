"""Configuration management for Network Detective & Self-Healing Network.

Loads configuration from .env, config/default.yaml, and config/network_topology.yaml
using Pydantic Settings (v2) with strict type validation.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ThresholdConfig(BaseModel):
    """Network metric thresholds for alerting and fault detection."""

    latency_warn_ms: float = Field(
        default=100.0, description="Latency warning threshold in milliseconds"
    )
    latency_critical_ms: float = Field(
        default=200.0, description="Latency critical threshold in milliseconds"
    )
    packet_loss_warn_pct: float = Field(
        default=5.0, description="Packet loss warning threshold percentage"
    )
    packet_loss_critical_pct: float = Field(
        default=10.0, description="Packet loss critical threshold percentage"
    )
    ping_timeout_sec: float = Field(
        default=3.0, description="Ping probe timeout in seconds"
    )
    max_retries: int = Field(
        default=3, description="Consecutive failed probes required before declaring outage"
    )


class NodeConfig(BaseModel):
    """Configuration for a single network node (router, switch, server, etc.)."""

    id: str = Field(..., description="Unique node identifier (e.g. router-a)")
    name: str = Field(..., description="Human-readable node label")
    ip_address: str = Field(..., description="IPv4 or IPv6 address for probing")
    node_type: str = Field(default="router", description="Node category: router, switch, server")
    description: str = Field(default="", description="Optional node description")


class LinkConfig(BaseModel):
    """Configuration for a network link between two nodes."""

    id: str = Field(default="", description="Unique link identifier")
    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")
    weight: float = Field(default=1.0, description="Routing cost/weight for shortest path calculation")
    bandwidth_mbps: float = Field(default=100.0, description="Link bandwidth in megabits per second")
    description: str = Field(default="", description="Optional link description")

    def model_post_init(self, __context: Any) -> None:
        """Auto-generate link ID if not explicitly provided."""
        if not self.id:
            self.id = f"link-{self.source}-{self.target}"


class NetworkConfig(BaseModel):
    """Network topology model containing nodes and connecting links."""

    name: str = Field(default="Campus Network", description="Network topology name")
    description: str = Field(default="", description="Network topology summary")
    nodes: list[NodeConfig] = Field(default_factory=list, description="List of configured nodes")
    links: list[LinkConfig] = Field(default_factory=list, description="List of configured links")


def _find_project_root() -> Path:
    """Resolve project root directory by traversing upwards from this file."""
    # This file is located at <project_root>/src/core/config.py
    current = Path(__file__).resolve()
    return current.parent.parent.parent


def _load_yaml_file(path: Path) -> dict[str, Any]:
    """Safely read and parse a YAML file into a dictionary."""
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = yaml.safe_load(f)
            return content if isinstance(content, dict) else {}
    except Exception:
        return {}


class Settings(BaseSettings):
    """Application-wide settings merging environment variables, YAML defaults, and topology."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Core Application Settings
    app_name: str = Field(
        default="Network Detective & Self-Healing Network",
        description="Application title",
    )
    environment: str = Field(default="development", description="Environment: development, test, production")
    debug: bool = Field(default=True, description="Enable debug logging and OpenAPI docs")
    host: str = Field(default="0.0.0.0", description="API host bind address")
    port: int = Field(default=8000, description="API port")
    polling_interval_sec: int = Field(default=5, description="Network polling interval in seconds")
    monitor_interval_sec: float = Field(
        default=0.5, description="Health monitor probe interval for the simulated network, in seconds"
    )
    verification_delay_sec: float = Field(
        default=2.0, description="Wait for route convergence before verifying a healed path, in seconds"
    )
    log_level: str = Field(default="INFO", description="Log level: DEBUG, INFO, WARNING, ERROR")

    # Database Settings
    database_url: str = Field(
        default="sqlite+aiosqlite:///./network_detective.db",
        description="Async SQLAlchemy database connection URL",
    )

    # Thresholds
    thresholds: ThresholdConfig = Field(default_factory=ThresholdConfig)

    # Topology
    topology: NetworkConfig = Field(default_factory=NetworkConfig)

    @property
    def network(self) -> NetworkConfig:
        """Alias for topology to support settings.network access."""
        return self.topology

    # Notification & Alert Settings (SMTP)
    smtp_enabled: bool = Field(default=False, description="Enable email alert notifications")
    smtp_host: str = Field(default="", description="SMTP host server")
    smtp_port: int = Field(default=587, description="SMTP server port")
    smtp_user: str = Field(default="", description="SMTP username")
    smtp_password: str = Field(default="", description="SMTP password")
    smtp_from: str = Field(default="alerts@network-detective.local", description="Sender email address")
    smtp_to: str = Field(default="admin@example.com", description="Recipient email address")
    smtp_use_tls: bool = Field(default=True, description="Use STARTTLS for SMTP connections")

    @classmethod
    def load_with_yaml(cls) -> Settings:
        """Load settings with config/default.yaml and config/network_topology.yaml merged."""
        project_root = _find_project_root()
        default_yaml_path = project_root / "config" / "default.yaml"
        topology_yaml_path = project_root / "config" / "network_topology.yaml"

        default_data = _load_yaml_file(default_yaml_path)
        topology_data = _load_yaml_file(topology_yaml_path)

        init_data: dict[str, Any] = {}

        # Merge base application fields from default.yaml if present
        if "app_name" in default_data:
            init_data["app_name"] = default_data["app_name"]
        if "environment" in default_data:
            init_data["environment"] = default_data["environment"]
        if "debug" in default_data:
            init_data["debug"] = default_data["debug"]
        if "host" in default_data:
            init_data["host"] = default_data["host"]
        if "port" in default_data:
            init_data["port"] = default_data["port"]
        if "polling_interval_sec" in default_data:
            init_data["polling_interval_sec"] = default_data["polling_interval_sec"]
        if "log_level" in default_data:
            init_data["log_level"] = default_data["log_level"]
        monitoring = default_data.get("monitoring")
        if isinstance(monitoring, dict) and "interval_sec" in monitoring:
            init_data["monitor_interval_sec"] = monitoring["interval_sec"]
        healing = default_data.get("self_healing")
        if isinstance(healing, dict) and "verification_delay_sec" in healing:
            init_data["verification_delay_sec"] = healing["verification_delay_sec"]
        if "database" in default_data and isinstance(default_data["database"], dict):
            if "url" in default_data["database"]:
                init_data["database_url"] = default_data["database"]["url"]

        # Merge thresholds
        if "thresholds" in default_data and isinstance(default_data["thresholds"], dict):
            init_data["thresholds"] = ThresholdConfig(**default_data["thresholds"])

        # Merge network topology
        if topology_data:
            net_meta = topology_data.get("network", {})
            nodes_raw = topology_data.get("nodes", [])
            links_raw = topology_data.get("links", [])

            nodes = [NodeConfig(**n) for n in nodes_raw] if nodes_raw else []
            links = [LinkConfig(**l) for l in links_raw] if links_raw else []

            init_data["topology"] = NetworkConfig(
                name=net_meta.get("name", "Campus Network"),
                description=net_meta.get("description", ""),
                nodes=nodes,
                links=links,
            )

        # Environment variables and .env override YAML defaults. Constructor arguments would
        # otherwise win over both, so drop any YAML value that the environment also sets.
        env_keys = {k.lower() for k in os.environ}
        env_keys |= {k.lower() for k in dotenv_values(project_root / ".env")}
        init_data = {k: v for k, v in init_data.items() if k not in env_keys}
        return cls(**init_data)


@functools.lru_cache(maxsize=1)
def get_settings(reload: bool = False) -> Settings:
    """Return the singleton Settings instance.

    Args:
        reload: If True, clear the cache and reload configuration from disk/env.

    Returns:
        The singleton Settings instance.
    """
    if reload:
        get_settings.cache_clear()
    return Settings.load_with_yaml()
