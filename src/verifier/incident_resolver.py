"""Post-healing verification, SLA auditing, and automated incident resolution."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from src.core.events import (
    HEALING_COMPLETE,
    VERIFICATION_RESULT,
    EventBus,
    event_bus as default_event_bus,
)
from src.core.models import (
    ActionResult,
    ActionType,
    Database,
    HealingAction,
    Incident,
    IncidentStatus,
)
from src.verifier.connectivity_checker import ConnectivityChecker, PathCheckResult
from src.verifier.validation_engine import ValidationEngine, ValidationResult
from src.utils.helpers import format_path
from src.utils.logger import logger


class IncidentResolver:
    """Evaluates post-healing performance to verify recovery or trigger rollback/escalation.

    Monitors HEALING_COMPLETE events, awaits network convergence, executes
    hop-by-hop and end-to-end reachability audits, confirms SLA compliance,
    and transitions incidents to VERIFIED or ESCALATED.
    """

    def __init__(
        self,
        connectivity_checker: ConnectivityChecker | None = None,
        validation_engine: ValidationEngine | None = None,
        event_bus: EventBus | None = None,
        healer: Any = None,
        node_ips: dict[str, str] | None = None,
        db: Database | None = None,
        stabilization_delay_sec: float = 2.0,
    ) -> None:
        """Initialize IncidentResolver.

        Args:
            connectivity_checker: Path connectivity tester.
            validation_engine: SLA threshold evaluator.
            event_bus: System event bus.
            healer: Optional SelfHealer instance for invoking rollback upon verification failure.
            node_ips: Mapping of node identifiers to probe IP addresses.
            db: Optional Database manager for persisting incident status updates.
            stabilization_delay_sec: Delay in seconds to wait for network convergence before probing.
        """
        self.connectivity_checker = connectivity_checker or ConnectivityChecker()
        self.validation_engine = validation_engine or ValidationEngine()
        self.event_bus = event_bus or default_event_bus
        self.healer = healer
        self.node_ips = node_ips or {}
        self.db = db
        self.stabilization_delay_sec = stabilization_delay_sec

        # Subscribe to healing completion events
        self.event_bus.subscribe(HEALING_COMPLETE, self.on_healing_complete)
        logger.info("IncidentResolver subscribed to '{}' events.", HEALING_COMPLETE)

    async def on_healing_complete(self, data: Any) -> None:
        """Handle incoming HEALING_COMPLETE events asynchronously.

        Args:
            data: Payload dictionary containing incident and healing_action objects.
        """
        logger.info("IncidentResolver received HEALING_COMPLETE event: {}", data)
        try:
            incident, healing_action = self._unpack_event_data(data)
            if incident and healing_action:
                await self.verify_and_resolve(incident, healing_action)
        except Exception as exc:
            logger.exception("Error during on_healing_complete verification: {}", exc)

    async def verify_and_resolve(
        self,
        incident: Incident,
        healing_action: HealingAction,
    ) -> bool:
        """Audit the post-healing route, confirm SLA compliance, and resolve or escalate.

        Workflow:
        1. Check if the healing action succeeded. If failed or escalated, mark incident escalated.
        2. Wait for route convergence (stabilization period).
        3. Test hop-by-hop reachability on the new alternate route.
        4. Validate post-healing latency and packet loss against SLA thresholds.
        5. If valid: mark incident VERIFIED, persist, and publish VERIFICATION_RESULT(success).
        6. If invalid: rollback via SelfHealer, mark incident ESCALATED, and publish VERIFICATION_RESULT(failed).

        Args:
            incident: Target network incident.
            healing_action: The applied remediation action.

        Returns:
            True if verification passed and incident resolved; False otherwise.
        """
        logger.info(
            "Commencing post-healing verification for incident {} (action_type={}, result={})",
            incident.id,
            healing_action.action_type,
            healing_action.result,
        )

        # 1. Guard against pre-failed healing
        if (
            healing_action.action_type == ActionType.ESCALATE
            or healing_action.result != ActionResult.SUCCESS
        ):
            logger.warning(
                "Healing action was not successful (action_type={}); escalating incident {}.",
                healing_action.action_type,
                incident.id,
            )
            await self.escalate_incident(
                incident, reason="Remediation could not find an alternate path."
            )
            await self._publish_verification_result(
                incident,
                success=False,
                details={"reason": "Healing action failed or was escalated"},
            )
            return False

        path_to_verify = healing_action.new_route or incident.alternate_path
        if not path_to_verify:
            logger.error("No path to verify for incident {}; escalating.", incident.id)
            await self.escalate_incident(
                incident, reason="No alternate path available to verify."
            )
            await self._publish_verification_result(
                incident, success=False, details={"reason": "Empty path"}
            )
            return False

        # 2. Wait for stabilization
        if self.stabilization_delay_sec > 0:
            logger.info(
                "Pausing {}s for post-healing route stabilization on path [{}]...",
                self.stabilization_delay_sec,
                format_path(path_to_verify),
            )
            await asyncio.sleep(self.stabilization_delay_sec)

        # 3. Check connectivity
        logger.info("Probing path connectivity: [{}]", format_path(path_to_verify))
        path_result: PathCheckResult = (
            await self.connectivity_checker.check_path_connectivity(
                path=path_to_verify,
                node_ips=self.node_ips,
            )
        )

        if not path_result.all_reachable:
            fail_reason = (
                f"Path reachability check failed on [{format_path(path_to_verify)}]. "
                f"Failed hops: {path_result.details.get('failed_hops', 1)}"
            )
            logger.warning(fail_reason)
            await self._handle_verification_failure(
                incident, healing_action, reason=fail_reason, details=path_result.to_dict()
            )
            return False

        # 4. Validate SLA metrics
        measured_latency = (
            path_result.end_to_end_latency_ms
            if path_result.end_to_end_latency_ms is not None
            else path_result.total_latency_ms
        )
        val_result: ValidationResult = self.validation_engine.validate_metrics(
            latency_ms=measured_latency,
            packet_loss_pct=path_result.packet_loss_pct,
        )

        if not val_result.passed:
            fail_reason = (
                f"SLA metrics exceeded allowed limits: "
                f"latency={measured_latency}ms (ok={val_result.latency_ok}), "
                f"loss={path_result.packet_loss_pct}% (ok={val_result.loss_ok})"
            )
            logger.warning(fail_reason)
            await self._handle_verification_failure(
                incident, healing_action, reason=fail_reason, details=val_result.to_dict()
            )
            return False

        # 5. Success: Resolve Incident
        resolve_notes = (
            f"Verified successfully via alternate path [{format_path(path_to_verify)}]. "
            f"Latency: {measured_latency:.2f}ms, Loss: {path_result.packet_loss_pct:.1f}%."
        )
        await self.resolve_incident(incident, notes=resolve_notes)

        verification_payload = {
            "incident_id": incident.id,
            "status": "success",
            "verified": True,
            "path": path_to_verify,
            "latency_ms": measured_latency,
            "packet_loss_pct": path_result.packet_loss_pct,
            "validation": val_result.to_dict(),
        }
        await self._publish_verification_result(
            incident, success=True, details=verification_payload
        )

        logger.info(
            "Incident {} successfully verified and resolved! Route: [{}]",
            incident.id,
            format_path(path_to_verify),
        )
        return True

    async def resolve_incident(
        self, incident: Incident, notes: str = ""
    ) -> None:
        """Mark incident status as VERIFIED and record resolution details.

        Args:
            incident: Target incident to resolve.
            notes: Context or metric details describing the resolution.
        """
        incident.status = IncidentStatus.VERIFIED
        incident.resolved_at = datetime.now(timezone.utc)
        incident.resolution_notes = (
            notes or "Incident autonomously resolved and verified by network detective."
        )

        logger.info("Incident {} resolved: {}", incident.id, incident.resolution_notes)
        await self._persist_incident(incident)

    async def escalate_incident(
        self, incident: Incident, reason: str = ""
    ) -> None:
        """Transition incident to ESCALATED and record escalation reasoning.

        Args:
            incident: Target incident to escalate.
            reason: Specific failure reason requiring human intervention.
        """
        incident.status = IncidentStatus.ESCALATED
        incident.resolution_notes = f"Escalated to network engineer: {reason}"

        logger.error(
            "Incident {} escalated: {}", incident.id, incident.resolution_notes
        )
        await self._persist_incident(incident)

    async def _handle_verification_failure(
        self,
        incident: Incident,
        healing_action: HealingAction,
        reason: str,
        details: dict[str, Any],
    ) -> None:
        """Rollback healing and escalate incident upon verification failure.

        Args:
            incident: Target incident.
            healing_action: Remediated action to rollback.
            reason: Failure description.
            details: Diagnostic information.
        """
        if self.healer is not None and hasattr(self.healer, "rollback"):
            logger.info("Triggering automatic rollback for incident {}...", incident.id)
            try:
                await self.healer.rollback(incident, healing_action)
            except Exception as exc:
                logger.exception("Error during healing rollback: {}", exc)

        await self.escalate_incident(incident, reason=reason)
        await self._publish_verification_result(
            incident,
            success=False,
            details={"reason": reason, "diagnostics": details},
        )

    async def _publish_verification_result(
        self, incident: Incident, success: bool, details: dict[str, Any]
    ) -> None:
        """Broadcast VERIFICATION_RESULT event.

        Args:
            incident: Incident being verified.
            success: Whether verification passed.
            details: Contextual details dictionary.
        """
        await self.event_bus.publish(
            VERIFICATION_RESULT,
            {
                "incident_id": incident.id,
                "incident": incident,
                "success": success,
                "status": "success" if success else "failed",
                "verified": success,
                "details": details,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _unpack_event_data(
        self, data: Any
    ) -> tuple[Incident | None, HealingAction | None]:
        """Extract Incident and HealingAction from incoming event payload."""
        if isinstance(data, dict):
            incident = data.get("incident")
            healing_action = data.get("healing_action")
            return incident, healing_action
        return None, None

    async def _persist_incident(self, incident: Incident) -> None:
        """Persist updated incident state to database if DB is configured."""
        if self.db is None:
            return

        try:
            async with self.db.session_factory() as session:
                await session.merge(incident)
                await session.commit()
                logger.debug("Persisted incident status {} in database.", incident.id)
        except Exception as exc:
            logger.warning("Could not persist incident update to DB: {}", exc)


# Verifier alias for external interface consistency
Verifier = IncidentResolver

__all__ = ["IncidentResolver", "Verifier"]
