# 🏛️ Architecture & System Design — Network Detective & Self-Healing Network

> **Autonomous Closed-Loop Network Monitoring, Root-Cause Diagnosis, and Dynamic Path Remediation**

---

## 1. High-Level Architectural Model

Network Detective operates on an autonomic closed-loop architecture inspired by IBM's MAPE-K (Monitor, Analyze, Plan, Execute, Knowledge) reference model. It replaces human-in-the-loop manual network administration with continuous, automated self-healing.

```mermaid
flowchart TD
    subgraph SENSE["1. SENSING (Network Detective)"]
        PROBE["Probing Engines\n(ICMP Ping & TCP Port)"]
        METRICS["Rolling Metrics Collector\n(Latency, Packet Loss, Jitter)"]
        TOPO_MGR["Topology Manager\n(Dynamic NetworkX Graph)"]
    end

    subgraph DETECT_ANALYZE["2. DETECTION & DIAGNOSIS"]
        THRESH["Threshold Engine\n(Multi-tier Warn/Critical)"]
        ANOMALY["Anomaly Detector\n(Rolling Z-Score Outliers)"]
        CLASSIFIER["Fault Classifier\n(Severity & Priority Ranking)"]
        DIAGNOSER["Root-Cause Diagnoser\n(Topological Upstream Isolation)"]
    end

    subgraph PLAN_EXECUTE["3. PLAN & EXECUTION (Self-Healing)"]
        PATH_FINDER["Path Finder\n(Dijkstra & Yen's K-Shortest Detours)"]
        ROUTE_MGR["Route Manager\n(Forwarding State & Rollback Stacks)"]
        REDIRECTOR["Traffic Redirector\n(Flow Switching & Simulation)"]
    end

    subgraph VERIFY_AUDIT["4. VERIFICATION & AUDIT"]
        CONN_CHECK["Connectivity Checker\n(Hop-by-Hop & E2E Validation)"]
        SLA_ENGINE["SLA Validation Engine\n(Convergence Grace Multipliers)"]
        RESOLVER["Incident Resolver\n(VERIFIED or ESCALATED)"]
    end

    subgraph PRESENTATION["5. REAL-TIME INTERACTION"]
        FASTAPI["FastAPI REST & WebSocket Gateway"]
        DASHBOARD["Flowinger Native Graph Dashboard"]
    end

    PROBE --> METRICS
    METRICS --> TOPO_MGR
    TOPO_MGR --> THRESH & ANOMALY
    THRESH & ANOMALY --> CLASSIFIER
    CLASSIFIER --> DIAGNOSER
    DIAGNOSER -->|"FAULT_DETECTED Event"| PATH_FINDER
    PATH_FINDER --> ROUTE_MGR
    ROUTE_MGR --> REDIRECTOR
    REDIRECTOR -->|"HEALING_COMPLETE Event"| CONN_CHECK
    CONN_CHECK --> SLA_ENGINE
    SLA_ENGINE --> RESOLVER
    RESOLVER -->|"Re-enter Loop / Rollback"| SENSE

    FASTAPI <--> PRESENTATION
    SENSE & DETECT_ANALYZE & PLAN_EXECUTE & VERIFY_AUDIT -->|"Event Stream"| FASTAPI
```

---

## 2. Core Subsystems

### 2.1 Network Detective (Monitoring & Telemetry)
- **Probing Engine**: Probes nodes and links using non-blocking multi-sample ICMP ping sequences and concurrent TCP port reachability checks (HTTP, SSH, HTTPS, DNS).
- **Metrics Collector**: Maintains in-memory sliding windows (`deque`) calculating rolling mean, min/max latency, packet loss percentage, and RTT jitter.
- **Topology Manager**: Synchronizes an in-memory weighted graph (`NetworkX`). Edge weights dynamically adjust based on live measured link latency.

### 2.2 Fault Detection & Root-Cause Diagnosis
- **Threshold Engine**: Evaluates telemetry against configured boundaries (`latency_warn_ms`, `latency_critical_ms`, `packet_loss_critical_pct`, `max_retries`).
- **Anomaly Detection**: Computes rolling Z-score statistical deviations ($Z = \frac{x - \mu}{\sigma}$). Detects sudden degrading trends before total link disconnects occur.
- **Fault Classifier**: Merges rule-based violations and statistical anomalies, prioritizing `NODE_DOWN > LINK_DOWN > HIGH_LATENCY > PACKET_LOSS`.
- **Topological Diagnoser**: Performs upstream graph traversal to differentiate root causes from secondary downstream symptom drops.

### 2.3 Self-Healing Engine
- **Dijkstra Detour Computation**: Upon failure confirmation, constructs an isolated subgraph excluding failed components and computes the least-cost alternate path.
- **Yen's K-Shortest Paths**: Computes backup candidate routes in advance to ensure instant failover if the primary alternate path is congested.
- **Route Forwarding State**: The `RouteManager` atomic routing table updates live traffic paths while keeping a rollback stack.

### 2.4 Verification & Incident Resolution
- **Route Stabilization Pause**: Introduces a configurable delay (default 2s) to allow convergence before testing reachability.
- **SLA Validation**: Evaluates hop-by-hop latency and packet loss against operational thresholds with a 1.5x grace multiplier for post-convergence stabilization.
- **Automated Rollback & Escalation**: If verification fails or no alternate path exists, the system automatically rolls back route modifications and marks the incident as `ESCALATED`.

---

## 3. Asynchronous Event Bus

Decoupled inter-module communication is coordinated via `src.core.events.EventBus`:

| Event Topic | Emitter | Consumers | Payload Description |
|-------------|---------|-----------|---------------------|
| `TOPOLOGY_UPDATED` | Monitor / Simulator | WebSocket Gateway, Diagnoser | Graph snapshot with nodes, links, and weights |
| `METRIC_RECORDED` | NetworkMonitor | FaultDetector, WebSocket Gateway | Node ID, latency, packet loss, jitter, timestamp |
| `FAULT_DETECTED` | FaultDetector / FailureInjector | SelfHealer, AlertManager, UI | Incident entity, fault type, affected component |
| `HEALING_STARTED` | SelfHealer | AlertManager, WebSocket UI | Incident entity, affected flows |
| `HEALING_COMPLETE` | SelfHealer | IncidentResolver, WebSocket UI | HealingAction entity, new route, old route, status |
| `VERIFICATION_RESULT` | IncidentResolver | WebSocket UI, AlertManager | Verification verdict, measured metrics, SLA status |

---

## 4. Fault Handling State Machine

```mermaid
stateDiagram-v2
    [*] --> DETECTED: Anomaly or Threshold Breach
    DETECTED --> DIAGNOSING: Correlate Multi-Node Symptoms
    DIAGNOSING --> HEALING: Isolate Root Cause & Find Alternate Detour
    DIAGNOSING --> ESCALATED: No Upstream Root Cause Isolated
    HEALING --> VERIFYING: Reroute Active Traffic via New Path
    HEALING --> ESCALATED: No Alternate Graph Path Exists
    VERIFYING --> VERIFIED: Reachability & SLA Compliance Confirmed
    VERIFYING --> ROLLBACK: Ping Fails or SLA Exceeded
    ROLLBACK --> ESCALATED: Restore Previous Routes & Alert Engineer
    VERIFIED --> [*]: Return to Normal Probing Loop
```
