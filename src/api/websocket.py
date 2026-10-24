"""Real-time WebSocket streaming handler for network telemetry and incidents.

Manages persistent client connections, subscribes to system events, and broadcasts
topology changes, fault alerts, metrics, and healing outcomes.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from src.core.events import (
    FAULT_DETECTED,
    HEALING_COMPLETE,
    METRIC_RECORDED,
    TOPOLOGY_UPDATED,
    VERIFICATION_RESULT,
    event_bus,
)
from src.monitor.topology_builder import TopologyBuilder, get_topology

router = APIRouter(tags=["WebSocket"])


def _serialize_payload(obj: Any) -> Any:
    """Helper to convert dataclasses, ORM models, or nested objects to JSON-serializable primitives."""
    if obj is None:
        return None
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return obj.to_dict()
    if hasattr(obj, "__dict__"):
        result: dict[str, Any] = {}
        for k, v in obj.__dict__.items():
            if not k.startswith("_"):
                result[k] = _serialize_payload(v)
        return result
    if isinstance(obj, dict):
        return {k: _serialize_payload(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_serialize_payload(x) for x in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


class ConnectionManager:
    """Maintains active WebSocket subscriber connections and manages message broadcasting."""

    def __init__(self) -> None:
        """Initialize connection pool and throttling state."""
        self.active_connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._last_metric_broadcast: dict[str, float] = {}
        self._subscribed = False

    async def connect(self, websocket: WebSocket) -> None:
        """Accept an incoming WebSocket connection and register it in the active set."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        logger.info("WebSocket connected. Active clients: {}", len(self.active_connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        """Unregister a disconnected WebSocket client."""
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info("WebSocket disconnected. Active clients: {}", len(self.active_connections))

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Broadcast a JSON message payload to all actively connected clients."""
        if not self.active_connections:
            return

        if "timestamp" not in message:
            message["timestamp"] = datetime.now(timezone.utc).isoformat()

        async with self._lock:
            clients = list(self.active_connections)

        dead_clients: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_json(message)
            except Exception as exc:
                logger.debug("Failed sending to client, scheduling disconnect: {}", exc)
                dead_clients.append(ws)

        if dead_clients:
            async with self._lock:
                for ws in dead_clients:
                    self.active_connections.discard(ws)

    def register_event_listeners(self) -> None:
        """Subscribe internal handlers to event_bus topics."""
        if self._subscribed:
            return

        event_bus.subscribe(TOPOLOGY_UPDATED, self._on_topology_updated)
        event_bus.subscribe(FAULT_DETECTED, self._on_fault_detected)
        event_bus.subscribe(HEALING_COMPLETE, self._on_healing_complete)
        event_bus.subscribe(VERIFICATION_RESULT, self._on_verification_result)
        event_bus.subscribe(METRIC_RECORDED, self._on_metric_recorded)
        self._subscribed = True
        logger.info("ConnectionManager successfully subscribed to system event topics.")

    async def _on_topology_updated(self, data: Any = None) -> None:
        """Broadcast updated topology graph representation."""
        try:
            snapshot = (
                data
                if isinstance(data, dict) and "nodes" in data
                else TopologyBuilder().get_topology_snapshot()
            )
            await self.broadcast({
                "type": "TOPOLOGY_UPDATED",
                "data": _serialize_payload(snapshot),
            })
        except Exception as exc:
            logger.error("Error broadcasting TOPOLOGY_UPDATED: {}", exc)

    async def _on_fault_detected(self, data: Any = None) -> None:
        """Broadcast real-time fault detection alert with incident details."""
        try:
            serialized = _serialize_payload(data)
            await self.broadcast({
                "type": "FAULT_DETECTED",
                "data": serialized,
            })
        except Exception as exc:
            logger.error("Error broadcasting FAULT_DETECTED: {}", exc)

    async def _on_healing_complete(self, data: Any = None) -> None:
        """Broadcast completed healing action outcome."""
        try:
            serialized = _serialize_payload(data)
            await self.broadcast({
                "type": "HEALING_COMPLETE",
                "data": serialized,
            })
        except Exception as exc:
            logger.error("Error broadcasting HEALING_COMPLETE: {}", exc)

    async def _on_verification_result(self, data: Any = None) -> None:
        """Broadcast verification outcome after healing rerouting."""
        try:
            serialized = _serialize_payload(data)
            await self.broadcast({
                "type": "VERIFICATION_RESULT",
                "data": serialized,
            })
        except Exception as exc:
            logger.error("Error broadcasting VERIFICATION_RESULT: {}", exc)

    async def _on_metric_recorded(self, data: Any = None) -> None:
        """Broadcast latest telemetry metrics, throttled to max 1 sample/sec per node."""
        try:
            node_id = None
            if isinstance(data, dict):
                node_id = data.get("node_id") or data.get("host")
            elif hasattr(data, "node_id"):
                node_id = getattr(data, "node_id")

            now = time.monotonic()
            if node_id:
                last_time = self._last_metric_broadcast.get(str(node_id), 0.0)
                if now - last_time < 1.0:
                    return  # Throttle to max 1 per second per node
                self._last_metric_broadcast[str(node_id)] = now

            await self.broadcast({
                "type": "METRIC_RECORDED",
                "data": _serialize_payload(data),
            })
        except Exception as exc:
            logger.error("Error broadcasting METRIC_RECORDED: {}", exc)


# Singleton connection manager instance
connection_manager = ConnectionManager()
connection_manager.register_event_listeners()


@router.websocket("/ws/live")
async def websocket_live_endpoint(websocket: WebSocket) -> None:
    """Primary WebSocket stream for real-time dashboard visualization and alerts."""
    await connection_manager.connect(websocket)
    try:
        # Deliver initial topology snapshot immediately on connection
        try:
            builder = TopologyBuilder()
            snapshot = builder.get_topology_snapshot()
            await websocket.send_json({
                "type": "TOPOLOGY_UPDATED",
                "data": _serialize_payload(snapshot),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as exc:
            logger.warning("Could not send initial topology to websocket client: {}", exc)

        # Receive incoming messages or heartbeat pings
        while True:
            text_data = await websocket.receive_text()
            if text_data == "ping":
                await websocket.send_text("pong")
            else:
                try:
                    payload = json.loads(text_data)
                    msg_type = payload.get("type", "").upper()
                    if msg_type == "PING":
                        await websocket.send_json({"type": "PONG", "timestamp": datetime.now(timezone.utc).isoformat()})
                    elif msg_type == "GET_TOPOLOGY":
                        snapshot = TopologyBuilder().get_topology_snapshot()
                        await websocket.send_json({
                            "type": "TOPOLOGY_UPDATED",
                            "data": _serialize_payload(snapshot),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })
                except json.JSONDecodeError:
                    pass
    except WebSocketDisconnect:
        await connection_manager.disconnect(websocket)
    except Exception as exc:
        logger.debug("WebSocket client disconnected with exception: {}", exc)
        await connection_manager.disconnect(websocket)
