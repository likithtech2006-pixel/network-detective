/**
 * Shared Type Definitions for Network Detective & Self-Healing Network
 */

export enum NodeStatus {
  UP = 'up',
  DOWN = 'down',
  DEGRADED = 'degraded',
}

export enum LinkStatus {
  UP = 'up',
  DOWN = 'down',
  DEGRADED = 'degraded',
}

export enum FaultType {
  NODE_DOWN = 'node_down',
  LINK_DOWN = 'link_down',
  LINK_DEGRADED = 'link_degraded',
  HIGH_LATENCY = 'high_latency',
  PACKET_LOSS = 'packet_loss',
}

export enum IncidentStatus {
  DETECTED = 'detected',
  DIAGNOSING = 'diagnosing',
  HEALING = 'healing',
  VERIFIED = 'verified',
  ESCALATED = 'escalated',
}

export enum ActionType {
  REROUTE = 'reroute',
  ROLLBACK = 'rollback',
  ESCALATE = 'escalate',
}

export enum ActionResult {
  SUCCESS = 'success',
  FAILED = 'failed',
}

export interface Node {
  id: string;
  name: string;
  ip_address: string;
  node_type: string; // e.g. "core_router", "edge_router", "gateway", "server"
  status: 'up' | 'down' | 'degraded' | NodeStatus;
  last_seen?: string;
  x?: number;
  y?: number;
}

export interface Link {
  id: string;
  source_node_id: string;
  target_node_id: string;
  source?: string;
  target?: string;
  status: 'up' | 'down' | 'degraded' | LinkStatus;
  weight: number;
  bandwidth_mbps: number;
  bandwidth?: number;
  latency_ms?: number;
}

export interface Topology {
  nodes: Node[];
  links: Link[];
}

export interface Metric {
  id?: string;
  node_id: string;
  latency_ms: number;
  packet_loss_pct: number;
  jitter_ms: number;
  recorded_at: string;
}

export interface HealingAction {
  id: string;
  incident_id: string;
  action_type: ActionType | 'reroute' | 'rollback' | 'escalate';
  old_route?: string[];
  new_route?: string[];
  result: ActionResult | 'success' | 'failed';
  executed_at: string;
  details?: string;
}

export interface Incident {
  id: string;
  fault_type: FaultType | string;
  affected_component: string;
  status: IncidentStatus | 'detected' | 'diagnosing' | 'healing' | 'verified' | 'escalated';
  source_node?: string;
  target_node?: string;
  original_path?: string[];
  alternate_path?: string[];
  detected_at: string;
  resolved_at?: string | null;
  resolution_notes?: string | null;
  healing_actions: HealingAction[];
  description?: string;
}

export interface DashboardStats {
  total_nodes: number;
  nodes_up: number;
  nodes_down: number;
  total_links: number;
  links_up: number;
  active_incidents: number;
  resolved_incidents: number;
  avg_latency_ms: number;
  avg_packet_loss_pct: number;
  uptime_pct: number;
}

export interface WebSocketMessage<T = any> {
  type: string;
  data: T;
  timestamp: string;
}

export interface Alert {
  id: string;
  timestamp: string;
  severity: 'critical' | 'warning' | 'info' | 'resolved';
  fault_type: string;
  affected_component: string;
  message: string;
  status: IncidentStatus | string;
  incident_id?: string;
}

export interface SystemConfig {
  polling_interval_sec: number;
  latency_warning_ms: number;
  latency_critical_ms: number;
  packet_loss_warning_pct: number;
  packet_loss_critical_pct: number;
  healing_enabled: boolean;
  auto_rollback: boolean;
}

export interface SimulateFailureRequest {
  target_type: 'node' | 'link';
  target_id: string;
  fault_type: FaultType | string;
  duration_sec?: number;
}

export interface SimulateRecoverRequest {
  target_type: 'node' | 'link';
  target_id: string;
}
