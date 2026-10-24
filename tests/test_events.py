"""Tests for src.core.events EventBus."""

import asyncio
from src.core.events import (
    DIAGNOSIS_COMPLETE,
    FAULT_DETECTED,
    HEALING_COMPLETE,
    HEALING_STARTED,
    EventBus,
    EventType,
)


def test_event_bus_subscribe_and_publish() -> None:
    async def _test() -> None:
        bus = EventBus()
        received_events: list[tuple[str, dict]] = []

        async def on_fault(event_type: str, data: dict) -> None:
            received_events.append((event_type, data))

        bus.subscribe(FAULT_DETECTED, on_fault)
        assert bus.subscriber_count(FAULT_DETECTED) == 1

        payload = {"node_id": "router-a", "reason": "unreachable"}
        await bus.publish(FAULT_DETECTED, payload)

        assert len(received_events) == 1
        assert received_events[0] == (FAULT_DETECTED, payload)

    asyncio.run(_test())


def test_event_bus_single_arg_callback() -> None:
    async def _test() -> None:
        bus = EventBus()
        received_data: list[dict] = []

        async def on_data(data: dict) -> None:
            received_data.append(data)

        bus.subscribe(HEALING_STARTED, on_data)
        await bus.publish(HEALING_STARTED, {"action": "reroute"})

        assert len(received_data) == 1
        assert received_data[0]["action"] == "reroute"

    asyncio.run(_test())


def test_event_bus_wildcard_subscription() -> None:
    async def _test() -> None:
        bus = EventBus()
        wildcard_received: list[str] = []

        async def on_any_event(event_type: str, data: dict) -> None:
            wildcard_received.append(event_type)

        bus.subscribe("*", on_any_event)

        await bus.publish(FAULT_DETECTED, {"id": 1})
        await bus.publish(DIAGNOSIS_COMPLETE, {"id": 2})
        await bus.publish(HEALING_COMPLETE, {"id": 3})

        assert wildcard_received == [FAULT_DETECTED, DIAGNOSIS_COMPLETE, HEALING_COMPLETE]

    asyncio.run(_test())


def test_event_bus_unsubscribe() -> None:
    async def _test() -> None:
        bus = EventBus()
        calls: list[int] = []

        async def handler(data: int) -> None:
            calls.append(data)

        bus.subscribe(FAULT_DETECTED, handler)
        await bus.publish(FAULT_DETECTED, 1)
        assert calls == [1]

        bus.unsubscribe(FAULT_DETECTED, handler)
        await bus.publish(FAULT_DETECTED, 2)
        assert calls == [1]

    asyncio.run(_test())
