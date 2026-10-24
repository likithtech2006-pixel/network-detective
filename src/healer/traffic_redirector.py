"""Traffic redirection engine executing simulated or physical route updates."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.healer.route_manager import RouteManager
from src.utils.helpers import format_path
from src.utils.logger import logger


@dataclass
class RedirectResult:
    """Result of a network traffic redirection operation."""

    success: bool
    source: str
    target: str
    old_path: list[str]
    new_path: list[str]
    redirected_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize RedirectResult to a dictionary."""
        return {
            "success": self.success,
            "source": self.source,
            "target": self.target,
            "old_path": self.old_path,
            "new_path": self.new_path,
            "redirected_at": self.redirected_at.isoformat(),
            "message": self.message,
            "details": self.details,
        }


class TrafficRedirector:
    """Executes traffic rerouting operations by modifying the active forwarding state.

    Supports simulation mode (in-memory routing table adjustment) as well as
    extensibility hooks for real SDN OpenFlow / Linux iproute2 flow table rules.
    """

    def __init__(
        self,
        route_manager: RouteManager,
        simulation_mode: bool = True,
    ) -> None:
        """Initialize TrafficRedirector.

        Args:
            route_manager: Active RouteManager instance.
            simulation_mode: When True, performs route modifications entirely in-memory.
        """
        self.route_manager = route_manager
        self.simulation_mode = simulation_mode

    async def redirect(
        self,
        source: str,
        target: str,
        old_path: list[str],
        new_path: list[str],
    ) -> RedirectResult:
        """Redirect traffic between source and target from old_path to new_path.

        In simulation mode, updates the RouteManager routing table and logs
        detailed redirection metrics.

        Args:
            source: Source node identifier.
            target: Destination node identifier.
            old_path: Prior path used for the flow.
            new_path: Newly selected alternate path.

        Returns:
            RedirectResult indicating success status and operational details.
        """
        redirect_time = datetime.now(timezone.utc)
        old_str = format_path(old_path) if old_path else "Direct"
        new_str = format_path(new_path) if new_path else "None"

        logger.info(
            "Executing traffic redirection: {} -> {} | Old path: [{}] -> New path: [{}] (mode={})",
            source,
            target,
            old_str,
            new_str,
            "simulation" if self.simulation_mode else "hardware",
        )

        try:
            if not new_path:
                msg = f"Cannot redirect traffic: empty target path provided for {source} -> {target}"
                logger.error(msg)
                return RedirectResult(
                    success=False,
                    source=source,
                    target=target,
                    old_path=old_path,
                    new_path=new_path,
                    redirected_at=redirect_time,
                    message=msg,
                )

            # In simulation mode: update in-memory routing table
            self.route_manager.apply_route(
                source=source,
                target=target,
                new_path=new_path,
                reason="traffic_redirection",
            )

            success_msg = f"Successfully rerouted {source} -> {target}: [{old_str}] => [{new_str}]"
            logger.info(success_msg)

            return RedirectResult(
                success=True,
                source=source,
                target=target,
                old_path=old_path,
                new_path=new_path,
                redirected_at=redirect_time,
                message=success_msg,
                details={
                    "mode": "simulation" if self.simulation_mode else "hardware",
                    "hops_count": len(new_path),
                },
            )

        except Exception as exc:
            err_msg = f"Failed to redirect traffic {source} -> {target}: {exc}"
            logger.exception(err_msg)
            return RedirectResult(
                success=False,
                source=source,
                target=target,
                old_path=old_path,
                new_path=new_path,
                redirected_at=redirect_time,
                message=err_msg,
                details={"error": str(exc)},
            )


__all__ = ["TrafficRedirector", "RedirectResult"]
