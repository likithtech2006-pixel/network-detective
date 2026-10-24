# 🔍 Network Detective & Self-Healing Network

An autonomous, self-healing network monitoring and remediation system. Network Detective continuously monitors network topology health, calculates latency and packet loss metrics, diagnoses root causes of failures using graph algorithms and heuristic rules, and autonomously executes self-healing rerouting strategies with rollback safeguards.

---

## 🚀 Key Features

- **Automated Health Monitoring**: Continuous ping and TCP reachability probing of nodes and links with configurable intervals.
- **Root-Cause Diagnosis Engine**: Correlates degraded links and node outages using graph-theoretic models (NetworkX) to differentiate link failures from upstream node failures.
- **Autonomous Self-Healing**: Dijkstra-based dynamic rerouting when links degrade or fail, recalculating optimal paths and maintaining incident states.
- **Rollback & Verification**: Automatic health verification of remediation actions with fallback / rollback mechanisms if healing fails.
- **Live Event Bus**: Asynchronous publish-subscribe messaging for real-time state changes, metrics, and incident life cycles.
- **FastAPI Backend & WebSockets**: Low-latency REST endpoints for topology, metrics, and incidents, plus WebSocket broadcasts for live dashboard updates.
- **Interactive Dashboard**: Modern visualization of campus network topology, link latency metrics, and real-time self-healing incident streams.

---

## 🏗️ Architecture Overview

```
                      +-----------------------------+
                      |   Interactive Web UI        |
                      |   (React / TypeScript)      |
                      +--------------+--------------+
                                     |
                             REST / WebSocket
                                     |
+------------------------------------+------------------------------------+
| Backend Core (FastAPI / Python 3.11+)                                  |
|                                                                        |
|   +-------------------+      +-------------------+                     |
|   |   FastAPI App     | <--->|   Async EventBus  |                     |
|   |   (REST & WS)     |      |   (Pub/Sub)       |                     |
|   +---------+---------+      +---------+---------+                     |
|             |                          |                               |
|             v                          v                               |
|   +-------------------+      +-------------------+                     |
|   |  Topology Graph   | <--->| Diagnostic Engine |                     |
|   |    (NetworkX)     |      | & Root-Cause Rule |                     |
|   +---------+---------+      +---------+---------+                     |
|             |                          |                               |
|             v                          v                               |
|   +-------------------+      +-------------------+                     |
|   | Monitoring Agent  |      |   Self-Healing    |                     |
|   | (Ping/TCP/Scapy)  |      |  Controller & Fix |                     |
|   +---------+---------+      +---------+---------+                     |
|             |                          |                               |
|             +------------+-------------+                               |
|                          |                                             |
|                          v                                             |
|            +---------------------------+                               |
|            | SQLAlchemy 2.0 (Async DB) |                               |
|            | (SQLite / PostgreSQL)     |                               |
|            +---------------------------+                               |
+------------------------------------------------------------------------+
```

---

## 🛠️ Tech Stack

- **Backend Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.11+)
- **Server**: [Uvicorn](https://www.uvicorn.org/) (with ASGI & WebSockets)
- **Database / ORM**: [SQLAlchemy 2.0](https://www.sqlalchemy.org/) (Async Engine) with [aiosqlite](https://github.com/omnilib/aiosqlite) / [asyncpg](https://github.com/MagicStack/asyncpg)
- **Graph & Topology Analysis**: [NetworkX](https://networkx.org/)
- **Network Probing**: [ping3](https://github.com/kyan001/ping3), [Scapy](https://scapy.net/)
- **Task Scheduling**: [APScheduler 3.x](https://apscheduler.readthedocs.io/)
- **Validation & Settings**: [Pydantic v2](https://docs.pydantic.dev/) & [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- **Structured Logging**: [Loguru](https://github.com/Delgan/loguru)
- **Containerization**: Docker & Docker Compose

---

## 📦 Project Structure

```
network-detective- and-self-healing-network/
├── config/
│   ├── default.yaml            # Default thresholds and polling intervals
│   ├── logging.yaml            # Loguru configuration (rotation, formats)
│   └── network_topology.yaml   # Campus network node & link topology
├── src/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app entry point & lifespan handler
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py           # Pydantic Settings & YAML loader
│   │   ├── events.py           # Async EventBus (Pub/Sub)
│   │   └── models.py           # SQLAlchemy 2.0 ORM models & database manager
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── helpers.py          # Ping, TCP check, formatting utilities
│   │   └── logger.py           # Loguru logger setup
│   └── api/                    # REST routes and WebSocket endpoints
├── tests/                      # Pytest unit and integration test suite
├── Dockerfile                  # Multi-stage production container build
├── docker-compose.yml          # Containerized orchestration
├── pyproject.toml              # Project dependencies & build metadata
└── README.md
```

---

## 🚦 Getting Started

### Option 1: Docker Compose (Recommended)

To run the complete system (Backend, Frontend, and optional PostgreSQL) with a single command:

```bash
# Clone the repository and enter the directory
cd "network-detective- and-self-healing-network"

# Build and start services
docker-compose up --build
```

The backend API will be accessible at `http://localhost:8000` (API documentation at `http://localhost:8000/docs`), and the frontend dashboard at `http://localhost:3000`.

---

### Option 2: Manual Local Setup

#### 1. Prerequisites
- Python 3.11 or higher
- Node.js 18+ (for frontend dashboard)

#### 2. Virtual Environment Setup
```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install the package and dependencies in editable mode
pip install --upgrade pip
pip install -e ".[dev]"
```

#### 3. Environment Configuration
Copy the template configuration file:
```bash
cp .env.example .env
```
Adjust parameters in `.env` as required (database connection, thresholds, logging level).

#### 4. Run the Application
You can run the server directly using the registered CLI command or Uvicorn:

```bash
# Using project script entry
network-detective

# OR using Uvicorn directly
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## ⚙️ Configuration Reference

### `config/default.yaml`
Configures operational limits and probe sensitivities:
- `polling_interval_sec`: Probing cadence (default: `5` seconds).
- `thresholds.latency_warn_ms`: Latency warning threshold (`100` ms).
- `thresholds.latency_critical_ms`: Latency critical threshold (`200` ms).
- `thresholds.packet_loss_warn_pct`: Packet loss warning threshold (`5%`).
- `thresholds.packet_loss_critical_pct`: Packet loss critical threshold (`10%`).
- `thresholds.ping_timeout_sec`: Ping timeout in seconds (`3` s).
- `thresholds.max_retries`: Number of consecutive failures before triggering incident (`3`).

### `config/network_topology.yaml`
Defines the network components:
- **Nodes**: `router-a`, `router-b`, `switch-c`, `server-d`, `server-e`
- **Links**: Weighted bidirectional connections with designated bandwidth capacities.

---

## 🧪 Testing & Code Quality

Run tests, type checks, and linting with:

```bash
# Run pytest test suite
pytest

# Run tests with test coverage
pytest --cov=src --cov-report=term-missing

# Run Ruff linter
ruff check .

# Run Mypy static type analysis
mypy src
```

---

## 📄 License

This project is licensed under the MIT License.
