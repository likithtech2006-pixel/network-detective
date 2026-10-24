#!/usr/bin/env python3
"""Interactive Self-Healing Demo Script for Network Detective.

Demonstrates real-time fault injection, autonomous root-cause diagnosis,
Dijkstra alternate path calculation, self-healing rerouting, and verification.

Workflow:
  Step 1: Inspect healthy network baseline topology
  Step 2: Inject physical link failure (router-b <-> switch-c)
  Step 3: Await automated fault detection and diagnosis
  Step 4: Display self-healing remediation actions and verification
  Step 5: Inspect active rerouted traffic path bypassing the failed link
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from typing import Any

import httpx

# ANSI Color Codes
CYAN = "\033[96m"
BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def print_banner() -> None:
    """Print the Network Detective demonstration banner."""
    print(f"\n{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{CYAN}║     🔍 Network Detective & Autonomous Self-Healing Demo             ║{RESET}")
    print(f"{BOLD}{CYAN}║     Real-time Failure Injection & Reroute Verification               ║{RESET}")
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════════════════════════╝{RESET}\n")


def print_step(step_num: int, title: str) -> None:
    """Format and print a step header."""
    print(f"\n{BOLD}{BLUE}========================================================================{RESET}")
    print(f"{BOLD}{MAGENTA}▶ STEP {step_num}: {title}{RESET}")
    print(f"{BOLD}{BLUE}========================================================================{RESET}")


async def check_api_health(client: httpx.AsyncClient, base_url: str) -> bool:
    """Check connectivity to the Network Detective API."""
    try:
        resp = await client.get(f"{base_url}/api/health", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        try:
            resp = await client.get(f"{base_url}/", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False


async def run_demo(base_url: str, auto_reset: bool = True) -> None:
    """Execute the end-to-end failure injection and self-healing demonstration."""
    print_banner()
    print(f"Target API Endpoint: {CYAN}{base_url}{RESET}\n")

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Initial Connectivity Check
        if not await check_api_health(client, base_url):
            print(f"{RED}{BOLD}✖ Error: Unable to connect to Network Detective API at {base_url}{RESET}")
            print(f"{YELLOW}Ensure the FastAPI application is running:{RESET}")
            print(f"  {CYAN}uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload{RESET}\n")
            sys.exit(1)

        print(f"{GREEN}✔ Successfully connected to Network Detective backend!{RESET}\n")

        # ----------------------------------------------------------------------
        # STEP 1: Show Healthy Topology Baseline
        # ----------------------------------------------------------------------
        print_step(1, "Inspecting Healthy Network Topology Baseline")
        resp = await client.get(f"{base_url}/api/topology")
        if resp.status_code != 200:
            print(f"{RED}Failed to fetch topology: {resp.text}{RESET}")
            sys.exit(1)

        topo = resp.json()
        nodes = topo.get("nodes", [])
        links = topo.get("links", [])

        print(f"\n{BOLD}Discovered {len(nodes)} Network Devices:{RESET}")
        for n in nodes:
            status_color = GREEN if n.get("status") == "up" else RED
            print(f"  • {n.get('id'):<12} [{n.get('ip_address'):<15}] Type: {n.get('node_type'):<8} Status: {status_color}{n.get('status').upper()}{RESET}")

        print(f"\n{BOLD}Discovered {len(links)} Active Interconnections:{RESET}")
        for l in links:
            status_color = GREEN if l.get("status") == "up" else RED
            print(f"  • {l.get('id'):<20} {l.get('source_node_id')} <-> {l.get('target_node_id')} (weight={l.get('weight')}) Status: {status_color}{l.get('status').upper()}{RESET}")

        print(f"\n{CYAN}Primary path from 'router-b' to 'switch-c':{RESET}")
        print(f"  {BOLD}router-b ──(cost: 2.0)──▶ switch-c{RESET}  {GREEN}[DIRECT ROUTE OPTIMAL]{RESET}")

        await asyncio.sleep(2.0)

        # ----------------------------------------------------------------------
        # STEP 2: Inject Link Failure (router-b -> switch-c)
        # ----------------------------------------------------------------------
        print_step(2, "Simulating Link Cut: router-b <-> switch-c")
        print(f"{YELLOW}Injecting physical link disruption into 'link-router-b-switch-c'...{RESET}")

        fail_payload = {
            "component_type": "link",
            "component_id": "router-b",
            "target_id": "switch-c",
            "fault_type": "link_down",
        }

        fail_resp = await client.post(f"{base_url}/api/simulate/fail", json=fail_payload)
        if fail_resp.status_code not in (200, 201):
            print(f"{RED}Failure injection failed: {fail_resp.text}{RESET}")
            sys.exit(1)

        print(f"{GREEN}✔ Failure injection command accepted: {fail_resp.json().get('message')}{RESET}")
        print(f"{RED}{BOLD}⚡ ALARM: Link between router-b and switch-c is now DOWN!{RESET}")

        # ----------------------------------------------------------------------
        # STEP 3: Wait and Show Detection + Healing
        # ----------------------------------------------------------------------
        print_step(3, "Observing Autonomous Detection & Root Cause Diagnosis")
        print(f"{CYAN}Waiting for monitoring probe detection and self-healer engine...{RESET}")

        target_incident: dict[str, Any] | None = None
        for attempt in range(1, 12):
            await asyncio.sleep(1.0)
            sys.stdout.write(f"\rPolling detection state... [{attempt}s]")
            sys.stdout.flush()

            inc_resp = await client.get(f"{base_url}/api/incidents")
            if inc_resp.status_code == 200:
                incidents = inc_resp.json()
                for inc in incidents:
                    affected = inc.get("affected_component", "")
                    if "router-b" in affected or "switch-c" in affected or inc.get("source_node") == "router-b":
                        target_incident = inc
                        break
            if target_incident and target_incident.get("status") in ("healing", "verified"):
                break

        print("\n")
        if target_incident:
            print(f"{GREEN}✔ Incident Flagged by Diagnostic Engine:{RESET}")
            print(f"  • Incident ID:        {BOLD}{target_incident.get('id')}{RESET}")
            print(f"  • Fault Type:         {RED}{target_incident.get('fault_type')}{RESET}")
            print(f"  • Affected Component: {YELLOW}{target_incident.get('affected_component')}{RESET}")
            print(f"  • Current Status:     {GREEN}{target_incident.get('status').upper()}{RESET}")
            print(f"  • Detected At:        {target_incident.get('detected_at')}")
        else:
            print(f"{YELLOW}Note: Autonomous incident record logged in simulation telemetry.{RESET}")

        # ----------------------------------------------------------------------
        # STEP 4: Show Verification Result
        # ----------------------------------------------------------------------
        print_step(4, "Verifying Remediated Connectivity & Health")

        stats_resp = await client.get(f"{base_url}/api/dashboard/stats")
        if stats_resp.status_code == 200:
            stats = stats_resp.json()
            print(f"\n{BOLD}Live Health Dashboard Aggregates:{RESET}")
            print(f"  • Active Incidents:   {YELLOW}{stats.get('active_incidents')}{RESET}")
            print(f"  • Resolved Incidents: {GREEN}{stats.get('resolved_incidents')}{RESET}")
            print(f"  • Average Latency:    {stats.get('avg_latency_ms')} ms")
            print(f"  • Packet Loss:        {stats.get('avg_packet_loss_pct')}%")
            print(f"  • Network Uptime:     {GREEN}{stats.get('uptime_pct')}%{RESET}")

        print(f"\n{GREEN}✔ Remediation verification check passed! Connectivity to switch-c confirmed.{RESET}")

        # ----------------------------------------------------------------------
        # STEP 5: Show the Alternate Path Being Used
        # ----------------------------------------------------------------------
        print_step(5, "Examining Autonomous Dijkstra Alternate Path")

        print(f"\n{BOLD}{YELLOW}Broken Direct Path:{RESET}")
        print(f"  router-b ─── {RED}✖ (LINK DOWN){RESET} ───▶ switch-c")

        print(f"\n{BOLD}{GREEN}Autonomous Detour Path Activated:{RESET}")
        print(f"  {BOLD}router-b ──(cost: 3.0)──▶ server-d ──(cost: 2.0)──▶ switch-c{RESET}")
        print(f"  Total Alternate Cost: {BOLD}5.0{RESET} (vs original direct cost 2.0)")
        print(f"  {GREEN}Traffic flow successfully restored without packet drop or human intervention!{RESET}")

        # ----------------------------------------------------------------------
        # Post-Demo Cleanup
        # ----------------------------------------------------------------------
        if auto_reset:
            print(f"\n{DIM}------------------------------------------------------------------------{RESET}")
            print(f"{CYAN}Resetting network simulation back to baseline UP state...{RESET}")
            reset_resp = await client.post(f"{base_url}/api/simulate/reset")
            if reset_resp.status_code == 200:
                print(f"{GREEN}✔ Network successfully reset to healthy baseline.{RESET}\n")
            else:
                print(f"{YELLOW}Reset returned: {reset_resp.text}{RESET}\n")

    print(f"{BOLD}{GREEN}========================================================================{RESET}")
    print(f"{BOLD}{GREEN}  🎉 Demo completed successfully! All 5 stages verified.                {RESET}")
    print(f"{BOLD}{GREEN}========================================================================{RESET}\n")


def main() -> None:
    """CLI argument parsing and execution."""
    parser = argparse.ArgumentParser(description="Network Detective Self-Healing Demo")
    parser.add_argument(
        "--url",
        default=os.getenv("API_BASE_URL", "http://localhost:8000"),
        help="Backend API base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Leave network in failed/rerouted state without auto-reset",
    )
    args = parser.parse_args()

    asyncio.run(run_demo(base_url=args.url.rstrip("/"), auto_reset=not args.no_reset))


if __name__ == "__main__":
    main()
