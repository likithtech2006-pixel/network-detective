import axios from 'axios';
import {
  Topology,
  Node,
  Metric,
  Incident,
  DashboardStats,
  SystemConfig,
  SimulateFailureRequest,
  SimulateRecoverRequest,
  NodeCreateRequest,
  NodeUpdateRequest,
  LinkCreateRequest,
  NetworkMode,
  DeviceSuggestion,
  PingResult,
} from '../types';

/**
 * Axios instance preconfigured for backend API requests
 */
export const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000,
});

/**
 * Fetch complete network topology (nodes & links)
 */
export async function getTopology(): Promise<Topology> {
  const response = await api.get<Topology>('/topology');
  return response.data;
}

/**
 * Fetch all nodes in the network
 */
export async function getNodes(): Promise<Node[]> {
  const response = await api.get<Node[]>('/nodes');
  return response.data;
}

/**
 * Fetch recent metrics for a specific node
 */
export async function getNodeMetrics(nodeId: string, limit: number = 50): Promise<Metric[]> {
  const response = await api.get<Metric[]>(`/metrics/node/${nodeId}`, {
    params: { limit },
  });
  return response.data;
}

/**
 * Fetch a node's samples from the last N minutes (newest first, thinned to maxPoints)
 */
export async function getNodeMetricsWindow(
  nodeId: string,
  minutes: number,
  maxPoints: number = 300
): Promise<Metric[]> {
  const response = await api.get<Metric[]>(`/metrics/node/${nodeId}`, {
    params: { minutes, max_points: maxPoints },
  });
  return response.data;
}

/**
 * Fetch incident list, optionally filtered by status
 */
export async function getIncidents(status?: string): Promise<Incident[]> {
  const response = await api.get<Incident[]>('/incidents', {
    params: status ? { status } : undefined,
  });
  return response.data;
}

/**
 * Fetch single incident by its ID
 */
export async function getIncidentById(id: string): Promise<Incident> {
  const response = await api.get<Incident>(`/incidents/${id}`);
  return response.data;
}

/**
 * Fetch active (unresolved) incidents
 */
export async function getActiveIncidents(): Promise<Incident[]> {
  const response = await api.get<Incident[]>('/incidents/active');
  return response.data;
}

/**
 * Fetch overall dashboard statistics
 */
export async function getDashboardStats(): Promise<DashboardStats> {
  const response = await api.get<DashboardStats>('/dashboard/stats');
  return response.data;
}

/**
 * Inject a simulated fault into a node or link
 */
export async function simulateFailure(req: SimulateFailureRequest): Promise<{ status: string; message: string; incident_id?: string }> {
  const response = await api.post('/simulator/failure', req);
  return response.data;
}

/**
 * Recover a node or link from failure
 */
export async function simulateRecover(req: SimulateRecoverRequest): Promise<{ status: string; message: string }> {
  const response = await api.post('/simulator/recover', req);
  return response.data;
}

/**
 * Reset all active simulations to healthy baseline
 */
export async function resetSimulation(): Promise<{ status: string; message: string }> {
  const response = await api.post('/simulator/reset');
  return response.data;
}

/**
 * Fetch current system configuration (thresholds, intervals)
 */
export async function getConfig(): Promise<SystemConfig> {
  const response = await api.get<SystemConfig>('/config');
  return response.data;
}

/**
 * Update system configuration
 */
export async function updateConfig(config: Partial<SystemConfig>): Promise<SystemConfig> {
  const response = await api.put<SystemConfig>('/config', config);
  return response.data;
}

/**
 * Readable message from a failed request (the backend's `detail` when it sends one)
 */
export function errorMessage(err: unknown): string {
  const detail = (err as any)?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
  return (err as any)?.message || 'Request failed';
}

/**
 * Add a router, switch or server to the topology
 */
export async function addNode(req: NodeCreateRequest): Promise<Node> {
  const response = await api.post<Node>('/topology/nodes', req);
  return response.data;
}

/**
 * Rename, retype, re-address or move a device
 */
export async function updateNode(nodeId: string, req: NodeUpdateRequest): Promise<void> {
  await api.patch(`/topology/nodes/${encodeURIComponent(nodeId)}`, req);
}

/**
 * Remove a device and every wire attached to it
 */
export async function deleteNode(nodeId: string): Promise<void> {
  await api.delete(`/topology/nodes/${encodeURIComponent(nodeId)}`);
}

/**
 * Connect two devices with a wire
 */
export async function addLink(req: LinkCreateRequest): Promise<void> {
  await api.post('/topology/links', req);
}

/**
 * Remove a wire
 */
export async function deleteLink(linkId: string): Promise<void> {
  await api.delete(`/topology/links/${encodeURIComponent(linkId)}`);
}

/**
 * Current network mode: simulated devices, or real devices pinged at their IP
 */
export async function getNetworkMode(): Promise<NetworkMode> {
  const response = await api.get<{ mode: NetworkMode }>('/network/mode');
  return response.data.mode;
}

/**
 * Switch network mode (resets device health and closes open incidents)
 */
export async function setNetworkMode(mode: NetworkMode): Promise<NetworkMode> {
  const response = await api.put<{ mode: NetworkMode }>('/network/mode', { mode });
  return response.data.mode;
}

/**
 * Send one real ping to an address
 */
export async function pingAddress(address: string): Promise<PingResult> {
  const response = await api.post<PingResult>('/network/ping', { address });
  return response.data;
}

/**
 * Real devices reachable from this computer (router, this machine, public DNS)
 */
export async function getDeviceSuggestions(): Promise<DeviceSuggestion[]> {
  const response = await api.get<DeviceSuggestion[]>('/network/suggestions');
  return response.data;
}

export default {
  getTopology,
  getNodes,
  getNodeMetrics,
  getIncidents,
  getIncidentById,
  getActiveIncidents,
  getDashboardStats,
  simulateFailure,
  simulateRecover,
  resetSimulation,
  getConfig,
  updateConfig,
};
