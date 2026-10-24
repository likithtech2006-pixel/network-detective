"""Alert manager handling incident record creation, deduplication, and notifications."""

from __future__ import annotations

import asyncio
import smtplib
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy import select

from src.core.config import Settings, get_settings
from src.core.events import EventBus, EventType, event_bus as default_event_bus
from src.core.models import (
    Database,
    Incident,
    IncidentStatus,
    get_database,
)
from src.detector.diagnoser import DiagnosisResult
from src.utils.logger import logger


class AlertManager:
    """Manages active network incident lifecycles, deduplication, database persistence, and alerts."""

    def __init__(
        self,
        config: Settings | None = None,
        db: Database | None = None,
        event_bus_instance: EventBus | None = None,
    ) -> None:
        """Initialize AlertManager.

        Args:
            config: Application configuration. Defaults to get_settings().
            db: Database session manager. Defaults to get_database().
            event_bus_instance: Event bus instance for emitting FAULT_DETECTED events.
        """
        self.config = config or get_settings()
        self._db = db or get_database()
        self.event_bus = event_bus_instance or default_event_bus

        # In-memory tracking of active (unresolved) incidents: {incident_id: Incident}
        self._active_incidents: dict[str, Incident] = {}
        # Mapping component -> active incident ID for fast deduplication
        self._component_to_incident: dict[str, str] = {}

    async def create_alert(self, diagnosis: DiagnosisResult) -> Incident | None:
        """Create a new incident if not already active for the affected component, and publish alert.

        Args:
            diagnosis: Diagnostic root cause analysis outcome.

        Returns:
            Created or existing active Incident, or None if diagnosis is empty.
        """
        root_comp = diagnosis.root_cause_component
        if not root_comp:
            return None

        # 1. Deduplication: check if component already has an unresolved incident
        existing_id = self._component_to_incident.get(root_comp)
        if existing_id and existing_id in self._active_incidents:
            existing = self._active_incidents[existing_id]
            logger.debug(
                "Suppressed duplicate alert for component '{}'; incident '{}' is already active ({})",
                root_comp,
                existing.id,
                existing.status.value if hasattr(existing.status, "value") else existing.status,
            )
            return existing

        # 2. Extract representative path endpoints
        if diagnosis.affected_paths:
            rep_path = diagnosis.affected_paths[0]
            src_node = rep_path[0]
            tgt_node = rep_path[-1]
            orig_path: list[str] | None = rep_path
        else:
            src_node = root_comp
            tgt_node = root_comp
            orig_path = [root_comp]

        # 3. Construct Incident entity
        incident = Incident(
            id=str(uuid.uuid4()),
            fault_type=diagnosis.fault_type,
            affected_component=root_comp,
            status=IncidentStatus.DETECTED,
            source_node=src_node,
            target_node=tgt_node,
            original_path=orig_path,
            alternate_path=None,
            detected_at=datetime.now(timezone.utc),
            resolution_notes=f"Auto-detected: {diagnosis.recommended_action}",
        )

        # 4. Persist to Database
        try:
            async with self._db.session_factory() as session:
                session.add(incident)
                await session.commit()
                # Refresh attributes within session context
                await session.refresh(incident)
        except Exception as exc:
            logger.error("Failed to persist incident for '{}' to database: {}", root_comp, exc)

        # 5. Track in-memory
        self._active_incidents[incident.id] = incident
        self._component_to_incident[root_comp] = incident.id

        logger.warning(
            "ALERT CREATED: Incident [{}] - {} on component '{}' | Paths affected: {}",
            incident.id,
            incident.fault_type.value if hasattr(incident.fault_type, "value") else incident.fault_type,
            root_comp,
            len(diagnosis.affected_paths),
        )

        # 6. Publish FAULT_DETECTED event on event bus
        incident_payload = incident.to_dict()
        incident_payload["diagnosis"] = diagnosis.to_dict()
        await self.event_bus.publish(EventType.FAULT_DETECTED, incident_payload)

        # 7. Send notification (log / email)
        await self.send_notification(incident)

        return incident

    async def send_notification(self, incident: Incident) -> None:
        """Dispatch notifications for a newly created incident via logging and optional email.

        Args:
            incident: The newly logged Incident.
        """
        fault_type_val = (
            incident.fault_type.value
            if hasattr(incident.fault_type, "value")
            else str(incident.fault_type)
        )
        msg = (
            f"[NETWORK ALERT] Fault detected on {incident.affected_component}: "
            f"Type={fault_type_val}, Status={incident.status.value if hasattr(incident.status, 'value') else incident.status}, "
            f"Path={incident.original_path}"
        )
        logger.warning(msg)

        # Optional SMTP email delivery
        if getattr(self.config, "smtp_enabled", False):
            await self._send_email_notification(incident)

    async def _send_email_notification(self, incident: Incident) -> None:
        """Send email alert in background thread pool using smtplib."""
        cfg = self.config

        def _do_send() -> None:
            try:
                mime_msg = MIMEMultipart("alternative")
                mime_msg["Subject"] = f"CRITICAL: Network Incident on {incident.affected_component}"
                mime_msg["From"] = cfg.smtp_from
                mime_msg["To"] = cfg.smtp_to

                body = (
                    f"Network Detective Incident Report\n"
                    f"==================================\n"
                    f"Incident ID: {incident.id}\n"
                    f"Component: {incident.affected_component}\n"
                    f"Fault Type: {incident.fault_type}\n"
                    f"Detected At: {incident.detected_at}\n"
                    f"Resolution Notes: {incident.resolution_notes}\n"
                )
                mime_msg.attach(MIMEText(body, "plain"))

                with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=10.0) as server:
                    if cfg.smtp_use_tls:
                        server.starttls()
                    if cfg.smtp_user and cfg.smtp_password:
                        server.login(cfg.smtp_user, cfg.smtp_password)
                    server.send_message(mime_msg)
                logger.info("Sent email alert for incident {} to {}", incident.id, cfg.smtp_to)
            except Exception as exc:
                logger.warning("Failed to send SMTP alert for incident {}: {}", incident.id, exc)

        await asyncio.to_thread(_do_send)

    def get_active_incidents(self) -> list[Incident]:
        """Return list of all currently unresolved incidents in memory.

        Returns:
            List of active Incident models.
        """
        return list(self._active_incidents.values())

    async def resolve_incident(
        self,
        incident_id: str,
        resolution_notes: str = "Resolved by self-healing controller",
    ) -> Incident | None:
        """Mark an incident as VERIFIED/resolved and clean up in-memory tracking.

        Args:
            incident_id: Identifier of the incident to close.
            resolution_notes: Summary of healing action and outcome.

        Returns:
            Updated Incident instance or None if not found.
        """
        incident = self._active_incidents.pop(incident_id, None)

        if incident is None:
            # Query from DB if not in memory
            try:
                async with self._db.session_factory() as session:
                    stmt = select(Incident).where(Incident.id == incident_id)
                    res = await session.execute(stmt)
                    incident = res.scalar_one_or_none()
            except Exception as exc:
                logger.warning("Could not find incident {} in database: {}", incident_id, exc)

        if incident is None:
            logger.warning("Cannot resolve non-existent incident '{}'", incident_id)
            return None

        # Clean component lookup
        if incident.affected_component in self._component_to_incident:
            del self._component_to_incident[incident.affected_component]

        incident.status = IncidentStatus.VERIFIED
        incident.resolved_at = datetime.now(timezone.utc)
        incident.resolution_notes = resolution_notes

        try:
            async with self._db.session_factory() as session:
                session.add(incident)
                await session.commit()
                await session.refresh(incident)
        except Exception as exc:
            logger.error("Failed to commit resolved incident {} to DB: {}", incident_id, exc)

        logger.info("Incident '{}' marked as VERIFIED and resolved", incident_id)
        return incident

    def clear(self) -> None:
        """Clear active incident records."""
        self._active_incidents.clear()
        self._component_to_incident.clear()
