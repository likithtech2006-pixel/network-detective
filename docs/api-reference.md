# 📡 REST API & WebSocket Reference — Network Detective

> Base URL: `http://localhost:8000`  
> Interactive OpenAPI Docs: `http://localhost:8000/docs`  
> WebSocket Stream: `ws://localhost:8000/ws/live`

---

## 1. System Health & Stats

### `GET /api/health`
Returns system operational state and component health.

**Response `200 OK`**:
```json
{
  "status": "healthy",
  "app_name": "Network Detective & Self-Healing Network",
  "version": "0.1.0",
  "database": "connected",
  "event_bus": "active",
  "active_listeners": 7,
  "timestamp": "2026-10-16T06:30:00Z"
}
```

### `GET /api/dashboard/stats`
Aggregated telemetry, inventory counts, and uptime score for the primary dashboard.

**Response `200 OK`**:
```json
{
  "total_nodes": 5,
  "nodes_up": 5,
  "nodes_down": 0,
  "nodes_degraded": 0,
  "total_links": 6,
  "links_up": 6,
  "active_incidents": 0,
  "resolved_incidents": 3,
  "avg_latency_ms": 8.5,
  "avg_packet_loss_pct": 0.0,
  "uptime_pct": 100.0
}
```

---

## 2. Topology Endpoints

### `GET /api/topology`
Returns the full network graph with computed visualizer canvas coordinates $(x, y)$ and live link weights.

**Response `200 OK`**:
```json
{
  "nodes": [
    {
      "id": "router-a",
      "name": "Router A (Core)",
      "ip_address": "192.168.1.1",
      "node_type": "router",
      "status": "up",
      "position": {"x": 250, "y": 80}
    }
  ],
  "links": [
    {
      "id": "link-router-a-router-b",
      "source_node_id": "router-a",
      "target_node_id": "router-b",
      "status": "up",
      "weight": 1.0,
      "bandwidth_mbps": 1000.0
    }
  ],
  "metadata": {
    "node_count": 5,
    "edge_count": 6,
    "network_name": "Campus Network"
  }
}
```

### `GET /api/topology/snapshot`
Lightweight graph snapshot optimized for high-frequency polling.

---

## 3. Nodes & Telemetry Endpoints

### `GET /api/nodes`
Lists all monitored nodes and their current operational status.

### `GET /api/nodes/{node_id}`
Returns device details, IP, type, and last probe timestamp.

### `GET /api/nodes/{node_id}/metrics`
Returns historical probe telemetry records.
- Query parameters: `limit` (default: 50), `offset` (default: 0).

---

## 4. Incidents & Self-Healing Actions

### `GET /api/incidents`
Lists all detected incidents.
- Query parameters: `status` (`detected`, `healing`, `verified`, `escalated`).

### `GET /api/incidents/{incident_id}`
Returns incident details with the full chronological audit trail of healing actions taken:
```json
{
  "id": 1,
  "fault_type": "link_down",
  "affected_component": "link-router-b-switch-c",
  "status": "verified",
  "source_node": "router-b",
  "target_node": "switch-c",
  "original_path": ["router-b", "switch-c"],
  "alternate_path": ["router-b", "server-d", "switch-c"],
  "detected_at": "2026-10-16T06:25:32Z",
  "resolved_at": "2026-10-16T06:25:34Z",
  "resolution_notes": "Verified successfully via alternate path [router-b → server-d → switch-c]. Latency: 29.50ms, Loss: 0.0%.",
  "healing_actions": [
    {
      "id": 1,
      "action_type": "reroute",
      "old_route": ["router-b", "switch-c"],
      "new_route": ["router-b", "server-d", "switch-c"],
      "result": "success",
      "executed_at": "2026-10-16T06:25:33Z"
    }
  ]
}
```

---

## 5. Chaos Simulator Controls

### `POST /api/simulate/fail`
Injects an operational failure into the simulation environment.

**Request Body (Link Cut)**:
```json
{
  "component_type": "link",
  "component_id": "router-b",
  "target_id": "switch-c"
}
```

**Request Body (Node Failure)**:
```json
{
  "component_type": "node",
  "component_id": "server-d"
}
```

### `POST /api/simulate/recover`
Restores a failed device or severed link back to operational state (`UP`).

### `POST /api/simulate/reset`
Resets the entire virtual network back to baseline healthy state.

---

## 6. Live WebSocket Streaming

Connect to `ws://localhost:8000/ws/live` to receive real-time JSON push events:

### Event Types:
1. `TOPOLOGY_SNAPSHOT`: Emitted on initial connection and whenever links/nodes change status.
2. `METRICS_STREAM`: Real-time node latency and loss samples (throttled to 1 msg/sec per node).
3. `ALERT`: Broadcast when `FAULT_DETECTED` is emitted.
4. `HEALING_EVENT`: Broadcast when remediation actions are applied.
5. `VERIFICATION_EVENT`: Broadcast when post-healing verification succeeds or fails.
