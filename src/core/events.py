"""Asynchronous publish-subscribe event bus for internal system decoupling.

Facilitates real-time event distribution between the monitoring poller,
diagnostic engine, self-healing controller, database persistence, and WebSocket broadcasters.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any

from src.utils.logger import logger


class EventType(str, Enum):
    """Standard system event topics emitted across the life cycle."""

    FAULT_DETECTED = "fault_detected"
    DIAGNOSIS_COMPLETE = "diagnosis_complete"
    HEALING_STARTED = "healing_started"
    HEALING_COMPLETE = "healing_complete"
    VERIFICATION_RESULT = "verification_result"
    METRIC_RECORDED = "metric_recorded"
    TOPOLOGY_UPDATED = "topology_updated"


# Shortcut constant references for direct imports
FAULT_DETECTED = EventType.FAULT_DETECTED.value
DIAGNOSIS_COMPLETE = EventType.DIAGNOSIS_COMPLETE.value
HEALING_STARTED = EventType.HEALING_STARTED.value
HEALING_COMPLETE = EventType.HEALING_COMPLETE.value
VERIFICATION_RESULT = EventType.VERIFICATION_RESULT.value
METRIC_RECORDED = EventType.METRIC_RECORDED.value
TOPOLOGY_UPDATED = EventType.TOPOLOGY_UPDATED.value

# Type alias for async callback functions
EventCallback = Callable[[str, Any], Awaitable[None]] | Callable[[Any], Awaitable[None]]


class EventBus:
    """Asynchronous in-memory event bus providing topic-based publish/subscribe."""

    def __init__(self) -> None:
        """Initialize empty listener registries."""
        self._subscribers: dict[str, list[EventCallback]] = defaultdict(list)
        self._wildcard_subscribers: list[EventCallback] = []
        self._lock = asyncio.Lock()

    def subscribe(self, event_type: str | EventType, callback: EventCallback) -> None:
        """Register an async callback for a given event topic or wildcard ('*').

        Args:
            event_type: Specific EventType / string, or '*' to receive all events.
            callback: Async function to execute when matching event is published.
        """
        key = event_type.value if isinstance(event_type, EventType) else str(event_type)
        if key == "*":
            if callback not in self._wildcard_subscribers:
                self._wildcard_subscribers.append(callback)
                logger.debug("Registered wildcard subscriber: {}", getattr(callback, "__name__", repr(callback)))
        else:
            if callback not in self._subscribers[key]:
                self._subscribers[key].append(callback)
                logger.debug(
                    "Registered subscriber for '{}': {}",
                    key,
                    getattr(callback, "__name__", repr(callback)),
                )

    def unsubscribe(self, event_type: str | EventType, callback: EventCallback) -> None:
        """Unregister an async callback from a specific event topic or wildcard.

        Args:
            event_type: Event type string or '*'
            callback: Previously registered callback function.
        """
        key = event_type.value if isinstance(event_type, EventType) else str(event_type)
        if key == "*":
            if callback in self._wildcard_subscribers:
                self._wildcard_subscribers.remove(callback)
        elif key in self._subscribers and callback in self._subscribers[key]:
            self._subscribers[key].remove(callback)

    async def publish(self, event_type: str | EventType, data: Any = None) -> None:
        """Publish an event to all registered topic and wildcard subscribers.

        Callbacks are invoked asynchronously in parallel. Any individual subscriber
        exceptions are caught and logged without affecting other subscribers.

        Args:
            event_type: Topic identifier of the event.
            data: Arbitrary payload associated with the event (dict, model, etc.).
        """
        key = event_type.value if isinstance(event_type, EventType) else str(event_type)
        callbacks: list[EventCallback] = list(self._subscribers.get(key, [])) + list(self._wildcard_subscribers)

        if not callbacks:
            logger.trace("No active subscribers for event '{}'", key)
            return

        logger.debug("Publishing event '{}' to {} subscriber(s)", key, len(callbacks))

        async def _invoke(cb: EventCallback) -> None:
            try:
                # Support callbacks that accept (event_type, data) or just (data)
                import inspect
                sig = inspect.signature(cb)
                if len(sig.parameters) >= 2:
                    await cb(key, data)  # type: ignore[call-arg]
                else:
                    await cb(data)  # type: ignore[call-arg]
            except Exception as exc:
                logger.exception(
                    "Error executing subscriber {} for event '{}': {}",
                    getattr(cb, "__name__", repr(cb)),
                    key,
                    exc,
                )

        tasks = [_invoke(cb) for cb in callbacks]
        await asyncio.gather(*tasks, return_exceptions=True)

    def clear(self) -> None:
        """Remove all subscribers from the bus (useful in testing)."""
        self._subscribers.clear()
        self._wildcard_subscribers.clear()

    def subscriber_count(self, event_type: str | EventType | None = None) -> int:
        """Return total count of subscribers for a topic or entire bus."""
        if event_type is None:
            return sum(len(cbs) for cbs in self._subscribers.values()) + len(self._wildcard_subscribers)
        key = event_type.value if isinstance(event_type, EventType) else str(event_type)
        return len(self._subscribers.get(key, [])) + len(self._wildcard_subscribers)


# Global singleton event bus instance
event_bus = EventBus()
