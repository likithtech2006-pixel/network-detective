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
