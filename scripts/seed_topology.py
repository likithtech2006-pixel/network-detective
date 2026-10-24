#!/usr/bin/env python3
"""Database Seeder Script for Network Detective & Self-Healing Network.

Populates the persistent database with network nodes and links defined in
config/network_topology.yaml. Supports both SQLAlchemy async session and
direct SQLite fallback when running in lightweight environments.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import sys

# Add project root directory to Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import yaml

# ANSI Color formatting
GREEN = "\033[92m"
BLUE = "\033[94m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _seed_via_sqlite3(db_path: Path, raw_nodes: list[dict], raw_links: list[dict]) -> tuple[int, int]:
    """Fallback seeder using Python standard library sqlite3."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Create tables matching SQLAlchemy schemas
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS nodes (
        id VARCHAR(64) PRIMARY KEY,
        name VARCHAR(128) NOT NULL,
        ip_address VARCHAR(64) NOT NULL,
        node_type VARCHAR(32) NOT NULL,
        status VARCHAR(32) NOT NULL,
        last_seen TIMESTAMP,
        created_at TIMESTAMP NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS links (
        id VARCHAR(128) PRIMARY KEY,
        source_node_id VARCHAR(64) NOT NULL,
        target_node_id VARCHAR(64) NOT NULL,
        status VARCHAR(32) NOT NULL,
        weight FLOAT NOT NULL,
        bandwidth_mbps FLOAT NOT NULL,
        FOREIGN KEY (source_node_id) REFERENCES nodes (id) ON DELETE CASCADE,
        FOREIGN KEY (target_node_id) REFERENCES nodes (id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        node_id VARCHAR(64) NOT NULL,
        link_id VARCHAR(128),
        latency_ms FLOAT NOT NULL,
        packet_loss_pct FLOAT NOT NULL,
        jitter_ms FLOAT NOT NULL,
        recorded_at TIMESTAMP NOT NULL,
        FOREIGN KEY (node_id) REFERENCES nodes (id) ON DELETE CASCADE,
        FOREIGN KEY (link_id) REFERENCES links (id) ON DELETE SET NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS incidents (
        id VARCHAR(64) PRIMARY KEY,
        fault_type VARCHAR(64) NOT NULL,
        affected_component VARCHAR(128) NOT NULL,
        status VARCHAR(32) NOT NULL,
        source_node VARCHAR(64) NOT NULL,
        target_node VARCHAR(64) NOT NULL,
        original_path TEXT,
        alternate_path TEXT,
        detected_at TIMESTAMP NOT NULL,
        resolved_at TIMESTAMP,
        resolution_notes TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS healing_actions (
        id VARCHAR(64) PRIMARY KEY,
        incident_id VARCHAR(64) NOT NULL,
        action_type VARCHAR(64) NOT NULL,
        old_route TEXT,
        new_route TEXT,
        result VARCHAR(32) NOT NULL,
        executed_at TIMESTAMP NOT NULL,
        FOREIGN KEY (incident_id) REFERENCES incidents (id) ON DELETE CASCADE
    );
    """)

    conn.commit()

    # Check existing nodes
    cursor.execute("SELECT id FROM nodes")
    existing_nodes = {row[0] for row in cursor.fetchall()}

    nodes_added = 0
    now_str = datetime.now(timezone.utc).isoformat()

    print(f"\n{BOLD}Seeding Nodes ({len(raw_nodes)} defined):{RESET}")
    for n in raw_nodes:
        node_id = str(n.get("id"))
        name = str(n.get("name", node_id))
        ip = str(n.get("ip_address", n.get("ip", "127.0.0.1")))
        node_type = str(n.get("node_type", "router"))

        if node_id in existing_nodes:
            print(f"  • {node_id:<12} [{ip:<15}] ({node_type}) - {YELLOW}Already exists{RESET}")
        else:
            cursor.execute(
                "INSERT INTO nodes (id, name, ip_address, node_type, status, last_seen, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (node_id, name, ip, node_type, "up", now_str, now_str),
            )
            nodes_added += 1
            print(f"  • {node_id:<12} [{ip:<15}] ({node_type}) - {GREEN}Added (UP){RESET}")

    conn.commit()

    # Check existing links
    cursor.execute("SELECT id FROM links")
    existing_links = {row[0] for row in cursor.fetchall()}

    links_added = 0
    print(f"\n{BOLD}Seeding Links ({len(raw_links)} defined):{RESET}")
    for l in raw_links:
        source = str(l.get("source"))
        target = str(l.get("target"))
        link_id = str(l.get("id", f"link-{source}-{target}"))
        weight = float(l.get("weight", 1.0))
        bw = float(l.get("bandwidth_mbps", 100.0))

        if link_id in existing_links:
            print(f"  • {link_id:<18} ({source} <-> {target}) - {YELLOW}Already exists{RESET}")
        else:
            cursor.execute(
                "INSERT INTO links (id, source_node_id, target_node_id, status, weight, bandwidth_mbps) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (link_id, source, target, "up", weight, bw),
            )
            links_added += 1
            print(f"  • {link_id:<18} ({source} <-> {target}, weight={weight}) - {GREEN}Added (UP){RESET}")

    conn.commit()
    conn.close()
    return nodes_added, links_added


async def _seed_via_sqlalchemy(raw_nodes: list[dict], raw_links: list[dict]) -> tuple[int, int]:
    """Attempt seeder using SQLAlchemy async session."""
    from sqlalchemy import select
    from src.core.config import get_settings
    from src.core.models import Link, LinkStatus, Node, NodeStatus, get_database

    settings = get_settings()
    db = get_database(settings.database_url)
    await db.create_all()

    nodes_added = 0
    links_added = 0

    async with db.session_factory() as session:
        # Check existing nodes
        existing_nodes_res = await session.execute(select(Node))
        existing_nodes = {n.id: n for n in existing_nodes_res.scalars().all()}

        print(f"\n{BOLD}Seeding Nodes ({len(raw_nodes)} defined):{RESET}")
        for n in raw_nodes:
            node_id = str(n.get("id"))
            name = str(n.get("name", node_id))
            ip = str(n.get("ip_address", n.get("ip", "127.0.0.1")))
            node_type = str(n.get("node_type", "router"))

            if node_id in existing_nodes:
                print(f"  • {node_id:<12} [{ip:<15}] ({node_type}) - {YELLOW}Already exists{RESET}")
            else:
                new_node = Node(
                    id=node_id,
                    name=name,
                    ip_address=ip,
                    node_type=node_type,
                    status=NodeStatus.UP,
                )
                session.add(new_node)
                nodes_added += 1
                print(f"  • {node_id:<12} [{ip:<15}] ({node_type}) - {GREEN}Added (UP){RESET}")

        await session.flush()

        # Check existing links
        existing_links_res = await session.execute(select(Link))
        existing_links = {l.id: l for l in existing_links_res.scalars().all()}

        print(f"\n{BOLD}Seeding Links ({len(raw_links)} defined):{RESET}")
        for l in raw_links:
            source = str(l.get("source"))
            target = str(l.get("target"))
            link_id = str(l.get("id", f"link-{source}-{target}"))
            weight = float(l.get("weight", 1.0))
            bw = float(l.get("bandwidth_mbps", 100.0))

            if link_id in existing_links:
                print(f"  • {link_id:<18} ({source} <-> {target}) - {YELLOW}Already exists{RESET}")
            else:
                new_link = Link(
                    id=link_id,
                    source_node_id=source,
                    target_node_id=target,
                    status=LinkStatus.UP,
                    weight=weight,
                    bandwidth_mbps=bw,
                )
                session.add(new_link)
                links_added += 1
                print(f"  • {link_id:<18} ({source} <-> {target}, weight={weight}) - {GREEN}Added (UP){RESET}")

        await session.commit()

    return nodes_added, links_added


def main() -> None:
    """Execute the database topology seeder."""
    print(f"\n{BOLD}{BLUE}======================================================{RESET}")
    print(f"{BOLD}{BLUE}  Network Detective - Database Topology Seeder        {RESET}")
    print(f"{BOLD}{BLUE}======================================================{RESET}\n")

    yaml_path = PROJECT_ROOT / "config" / "network_topology.yaml"
    if not yaml_path.is_file():
        print(f"{YELLOW}Error: Configuration file not found at: {yaml_path}{RESET}")
        sys.exit(1)

    print(f"Loading topology configuration from: {CYAN}{yaml_path}{RESET}")
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    network_info = data.get("network", {})
    raw_nodes = data.get("nodes", [])
    raw_links = data.get("links", [])

    print(f"Network Name: {BOLD}{network_info.get('name', 'Campus Network')}{RESET}")
    print(f"Description:  {network_info.get('description', '')}\n")

    try:
        nodes_added, links_added = asyncio.run(_seed_via_sqlalchemy(raw_nodes, raw_links))
    except Exception as exc:
        # Fall back gracefully to direct SQLite
        db_path = PROJECT_ROOT / "network_detective.db"
        print(f"{YELLOW}Note: SQLAlchemy async engine encountered ({exc}). Using SQLite driver directly at {db_path}...{RESET}")
        nodes_added, links_added = _seed_via_sqlite3(db_path, raw_nodes, raw_links)

    print(f"\n{BOLD}{GREEN}✔ Topology seeding completed successfully!{RESET}")
    print(f"  Nodes added: {GREEN}{nodes_added}{RESET} (Total: {len(raw_nodes)})")
    print(f"  Links added: {GREEN}{links_added}{RESET} (Total: {len(raw_links)})\n")


if __name__ == "__main__":
    main()
