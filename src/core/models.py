"""SQLAlchemy 2.0 ORM models and database manager for Network Detective.

Defines schemas for Network Nodes, Links, Metrics, Incidents, and Healing Actions,
along with an asynchronous Database session manager.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    inspect,
    text,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# ==============================================================================
# Shared Enums
# ==============================================================================


class NodeStatus(str, Enum):
    """Operational status of a network node."""

    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"


class LinkStatus(str, Enum):
    """Operational status of a network link."""

    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"


class FaultType(str, Enum):
    """Classification of network anomalies and failure conditions."""

    NODE_DOWN = "node_down"
    LINK_DOWN = "link_down"
    LINK_DEGRADED = "link_degraded"
    HIGH_LATENCY = "high_latency"
    PACKET_LOSS = "packet_loss"


class IncidentStatus(str, Enum):
    """Life cycle stage of a detected network incident."""

    DETECTED = "detected"
    DIAGNOSING = "diagnosing"
    HEALING = "healing"
    VERIFIED = "verified"
    ESCALATED = "escalated"


class ActionType(str, Enum):
    """Remediation action type performed by the self-healing controller."""

    REROUTE = "reroute"
    ROLLBACK = "rollback"
    ESCALATE = "escalate"


class ActionResult(str, Enum):
    """Execution outcome of a remediation action."""

    SUCCESS = "success"
    FAILED = "failed"


# ==============================================================================
# Declarative Base
# ==============================================================================


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    pass


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def _gen_uuid() -> str:
    """Generate a clean UUID string."""
    return str(uuid.uuid4())


# ==============================================================================
# ORM Models
# ==============================================================================


class Node(Base):
    """Network device (router, switch, server) monitored by the system."""

    __tablename__ = "nodes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    ip_address: Mapped[str] = mapped_column(String(64), nullable=False)
    node_type: Mapped[str] = mapped_column(String(32), default="router", nullable=False)
    status: Mapped[NodeStatus] = mapped_column(
        SQLEnum(NodeStatus, native_enum=False, values_callable=lambda x: [e.value for e in x]),
        default=NodeStatus.UP,
        nullable=False,
        index=True,
    )
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Canvas position chosen in the topology editor (None = automatic layout)
    pos_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    pos_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )

    # Relationships
    source_links: Mapped[list[Link]] = relationship(
        "Link",
        foreign_keys="Link.source_node_id",
        back_populates="source_node",
        cascade="all, delete-orphan",
    )
    target_links: Mapped[list[Link]] = relationship(
        "Link",
        foreign_keys="Link.target_node_id",
        back_populates="target_node",
        cascade="all, delete-orphan",
    )
    metrics: Mapped[list[Metric]] = relationship(
        "Metric",
        back_populates="node",
        cascade="all, delete-orphan",
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert Node model to a dictionary representation."""
        return {
            "id": self.id,
            "name": self.name,
            "ip_address": self.ip_address,
            "node_type": self.node_type,
            "status": self.status.value if isinstance(self.status, NodeStatus) else self.status,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AppSetting(Base):
    """Small key/value store for settings changed at runtime (e.g. the network mode)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(256), nullable=False)


class Link(Base):
    """Bidirectional or directed network connection between two nodes."""

    __tablename__ = "links"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source_node_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_node_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[LinkStatus] = mapped_column(
        SQLEnum(LinkStatus, native_enum=False, values_callable=lambda x: [e.value for e in x]),
        default=LinkStatus.UP,
        nullable=False,
        index=True,
    )
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    bandwidth_mbps: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)

    # Relationships
    source_node: Mapped[Node] = relationship(
        "Node",
        foreign_keys=[source_node_id],
        back_populates="source_links",
    )
    target_node: Mapped[Node] = relationship(
        "Node",
        foreign_keys=[target_node_id],
        back_populates="target_links",
    )
    metrics: Mapped[list[Metric]] = relationship(
        "Metric",
        back_populates="link",
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert Link model to a dictionary representation."""
        return {
            "id": self.id,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "status": self.status.value if isinstance(self.status, LinkStatus) else self.status,
            "weight": self.weight,
            "bandwidth_mbps": self.bandwidth_mbps,
        }


class Metric(Base):
    """Historical telemetry metric sample recorded during polling."""

    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    link_id: Mapped[str | None] = mapped_column(
        String(128),
        ForeignKey("links.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    packet_loss_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    jitter_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False, index=True
    )

    # Relationships
    node: Mapped[Node] = relationship("Node", back_populates="metrics")
    link: Mapped[Link | None] = relationship("Link", back_populates="metrics")

    def to_dict(self) -> dict[str, Any]:
        """Convert Metric model to a dictionary representation."""
        return {
            "id": self.id,
            "node_id": self.node_id,
            "link_id": self.link_id,
            "latency_ms": self.latency_ms,
            "packet_loss_pct": self.packet_loss_pct,
            "jitter_ms": self.jitter_ms,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
        }


class Incident(Base):
    """Network fault event requiring diagnosis and potential self-healing remediation."""

    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_gen_uuid)
    fault_type: Mapped[FaultType] = mapped_column(
        SQLEnum(FaultType, native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )
    affected_component: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[IncidentStatus] = mapped_column(
        SQLEnum(IncidentStatus, native_enum=False, values_callable=lambda x: [e.value for e in x]),
        default=IncidentStatus.DETECTED,
        nullable=False,
        index=True,
    )
    source_node: Mapped[str] = mapped_column(String(64), nullable=False)
    target_node: Mapped[str] = mapped_column(String(64), nullable=False)
    original_path: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    alternate_path: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    healing_actions: Mapped[list[HealingAction]] = relationship(
        "HealingAction",
        back_populates="incident",
        cascade="all, delete-orphan",
        order_by="HealingAction.executed_at.asc()",
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert Incident model to a dictionary representation."""
        return {
            "id": self.id,
            "fault_type": self.fault_type.value if isinstance(self.fault_type, FaultType) else self.fault_type,
            "affected_component": self.affected_component,
            "status": self.status.value if isinstance(self.status, IncidentStatus) else self.status,
            "source_node": self.source_node,
            "target_node": self.target_node,
            "original_path": self.original_path,
            "alternate_path": self.alternate_path,
            "detected_at": self.detected_at.isoformat() if self.detected_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolution_notes": self.resolution_notes,
        }


class HealingAction(Base):
    """Autonomous action taken to remediate a network incident."""

    __tablename__ = "healing_actions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_gen_uuid)
    incident_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action_type: Mapped[ActionType] = mapped_column(
        SQLEnum(ActionType, native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )
    old_route: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    new_route: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    result: Mapped[ActionResult] = mapped_column(
        SQLEnum(ActionResult, native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False, index=True
    )

    # Relationships
    incident: Mapped[Incident] = relationship(
        "Incident",
        back_populates="healing_actions",
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert HealingAction model to a dictionary representation."""
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "action_type": self.action_type.value if isinstance(self.action_type, ActionType) else self.action_type,
            "old_route": self.old_route,
            "new_route": self.new_route,
            "result": self.result.value if isinstance(self.result, ActionResult) else self.result,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
        }


# ==============================================================================
# Database Session & Lifecycle Manager
# ==============================================================================


def _add_missing_columns(sync_conn: Any) -> None:
    """Add nullable columns that exist on a model but not yet in an older database file.

    create_all() never alters existing tables, so a database made by an earlier version
    would otherwise fail on the new columns.
    """
    inspector = inspect(sync_conn)
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name not in existing and column.nullable:
                col_type = column.type.compile(dialect=sync_conn.dialect)
                sync_conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {col_type}"))


class Database:
    """Asynchronous database manager handling engine initialization, schema creation, and sessions."""

    def __init__(self, db_url: str | None = None, echo: bool = False) -> None:
        """Initialize database with an async connection URL.

        Args:
            db_url: Database connection string (defaults to sqlite+aiosqlite).
            echo: Whether to log generated SQL statements.
        """
        self.db_url = db_url or "sqlite+aiosqlite:///./network_detective.db"
        self.echo = echo

        self._engine: AsyncEngine = create_async_engine(
            self.db_url,
            echo=self.echo,
            future=True,
        )
        self._session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @property
    def engine(self) -> AsyncEngine:
        """Return the underlying AsyncEngine."""
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Return the configured async session factory."""
        return self._session_factory

    async def create_all(self) -> None:
        """Create missing tables, and add columns introduced after a table was first created."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(_add_missing_columns)

    async def drop_all(self) -> None:
        """Drop all tables (used primarily in test fixtures)."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Dependency generator yielding an async database session."""
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def close(self) -> None:
        """Gracefully dispose of the database connection pool."""
        await self._engine.dispose()


# Global database instance placeholder
_database_instance: Database | None = None


def get_database(db_url: str | None = None) -> Database:
    """Get or create the singleton Database instance."""
    global _database_instance
    if _database_instance is None:
        _database_instance = Database(db_url=db_url)
    return _database_instance
