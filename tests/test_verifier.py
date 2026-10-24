"""Tests for src.verifier module: ConnectivityChecker, ValidationEngine, and IncidentResolver."""

import asyncio
from unittest.mock import AsyncMock, patch

from src.core.events import EventBus, HEALING_COMPLETE, VERIFICATION_RESULT
from src.core.models import (
    ActionResult,
    ActionType,
    FaultType,
    HealingAction,
    Incident,
    IncidentStatus,
)
from src.verifier.connectivity_checker import ConnectivityChecker
from src.verifier.incident_resolver import IncidentResolver
from src.verifier.validation_engine import ValidationEngine


def test_validation_engine_normal_and_exceeded() -> None:
    engine = ValidationEngine(grace_multiplier=1.5)

    custom_thresholds = {
        "latency_critical_ms": 200.0,
        "packet_loss_critical_pct": 10.0,
    }

    # Within normal limits
    res_pass = engine.validate_metrics(
        latency_ms=45.0,
        packet_loss_pct=0.0,
        thresholds=custom_thresholds,
    )
    assert res_pass.passed is True
    assert res_pass.latency_ok is True
    assert res_pass.loss_ok is True

    # Within grace limit (200 * 1.5 = 300ms)
    res_grace = engine.validate_metrics(
        latency_ms=250.0,
        packet_loss_pct=5.0,
        thresholds=custom_thresholds,
    )
    assert res_grace.passed is True
    assert res_grace.latency_ok is True

    # Exceeding grace limit
    res_fail = engine.validate_metrics(
        latency_ms=350.0,
        packet_loss_pct=0.0,
        thresholds=custom_thresholds,
    )
    assert res_fail.passed is False
    assert res_fail.latency_ok is False


def test_connectivity_checker_with_mocked_ping() -> None:
    async def _test() -> None:
        checker = ConnectivityChecker()

        async def mock_ping(host: str, timeout: float = 3.0) -> tuple[bool, float | None]:
            if host == "192.168.1.99":
                return False, None
            return True, 15.0

        with patch("src.verifier.connectivity_checker.ping_host", side_effect=mock_ping):
            node_ips = {
                "router-a": "192.168.1.1",
                "router-b": "192.168.1.2",
                "switch-c": "192.168.1.3",
            }

            result_ok = await checker.check_path_connectivity(
                ["router-a", "router-b", "switch-c"],
                node_ips=node_ips,
            )
            assert result_ok.all_reachable is True
            assert len(result_ok.hop_results) == 3

            # Test unreachable
            node_ips["router-b"] = "192.168.1.99"
            result_fail = await checker.check_path_connectivity(
                ["router-a", "router-b", "switch-c"],
                node_ips=node_ips,
            )
            assert result_fail.all_reachable is False

    asyncio.run(_test())


def test_incident_resolver_workflow() -> None:
    async def _test() -> None:
        bus = EventBus()
        checker = ConnectivityChecker()
        engine = ValidationEngine()

        resolver = IncidentResolver(
            connectivity_checker=checker,
            validation_engine=engine,
            event_bus=bus,
            stabilization_delay_sec=0.01,  # Fast testing delay
        )

        verified_events: list[dict] = []

        async def on_verified(data: dict) -> None:
            verified_events.append(data)

        bus.subscribe(VERIFICATION_RESULT, on_verified)

        incident = Incident(
            id=202,
            fault_type=FaultType.LINK_DOWN,
            affected_component="link-router-b-switch-c",
            status=IncidentStatus.HEALING,
            source_node="router-b",
            target_node="switch-c",
            alternate_path=["router-b", "server-d", "switch-c"],
        )

        healing_action = HealingAction(
            id=303,
            incident_id=202,
            action_type=ActionType.REROUTE,
            old_route=["router-b", "switch-c"],
            new_route=["router-b", "server-d", "switch-c"],
            result=ActionResult.SUCCESS,
        )

        # Mock check_path_connectivity to return success
        async def mock_check(*args, **kwargs):
            from src.verifier.connectivity_checker import PathCheckResult
            return PathCheckResult(
                path=["router-b", "server-d", "switch-c"],
                all_reachable=True,
                hop_results=[],
                end_to_end_latency_ms=25.0,
                packet_loss_pct=0.0,
            )

        checker.check_path_connectivity = mock_check

        await bus.publish(
            HEALING_COMPLETE,
            {"incident": incident, "healing_action": healing_action},
        )

        assert len(verified_events) == 1
        event = verified_events[0]
        assert event["incident"].status == IncidentStatus.VERIFIED
        assert event["verified"] is True
        assert event["success"] is True

    asyncio.run(_test())
