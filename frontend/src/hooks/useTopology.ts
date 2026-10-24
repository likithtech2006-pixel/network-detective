import { useState, useEffect, useCallback } from 'react';
import { Topology, Node, Link } from '../types';
import { getTopology } from '../services/api';
import { useWebSocket } from './useWebSocket';

/**
 * Baseline 5-node campus topology matching backend default configuration
 */
export const DEFAULT_TOPOLOGY: Topology = {
  nodes: [
    { id: 'router-a', name: 'router-a', ip_address: '192.168.1.1', node_type: 'router', status: 'up', x: 90, y: 210 },
    { id: 'router-b', name: 'router-b', ip_address: '192.168.1.2', node_type: 'router', status: 'up', x: 360, y: 90 },
    { id: 'switch-c', name: 'switch-c', ip_address: '192.168.1.3', node_type: 'switch', status: 'up', x: 360, y: 330 },
    { id: 'server-d', name: 'server-d', ip_address: '192.168.1.4', node_type: 'server', status: 'up', x: 650, y: 90 },
    { id: 'server-e', name: 'server-e', ip_address: '192.168.1.5', node_type: 'server', status: 'up', x: 650, y: 330 },
  ],
  links: [
    { id: 'link-a-b', source_node_id: 'router-a', target_node_id: 'router-b', source: 'router-a', target: 'router-b', status: 'up', weight: 1, bandwidth_mbps: 1000 },
    { id: 'link-b-c', source_node_id: 'router-b', target_node_id: 'switch-c', source: 'router-b', target: 'switch-c', status: 'up', weight: 2, bandwidth_mbps: 100 },
    { id: 'link-b-d', source_node_id: 'router-b', target_node_id: 'server-d', source: 'router-b', target: 'server-d', status: 'up', weight: 3, bandwidth_mbps: 100 },
    { id: 'link-c-d', source_node_id: 'switch-c', target_node_id: 'server-d', source: 'switch-c', target: 'server-d', status: 'up', weight: 2, bandwidth_mbps: 100 },
    { id: 'link-c-e', source_node_id: 'switch-c', target_node_id: 'server-e', source: 'switch-c', target: 'server-e', status: 'up', weight: 2, bandwidth_mbps: 100 },
    { id: 'link-a-d', source_node_id: 'router-a', target_node_id: 'server-d', source: 'router-a', target: 'server-d', status: 'up', weight: 5, bandwidth_mbps: 100 },
  ],
};

/**
 * Normalizes raw topology payload from REST API or WebSocket snapshots
 */
export function normalizeTopology(data: any): Topology {
  if (!data || !Array.isArray(data.nodes) || data.nodes.length === 0) {
    return DEFAULT_TOPOLOGY;
  }

  const nodes: Node[] = data.nodes.map((n: any) => ({
    id: n.id,
    name: n.name || n.id,
    ip_address: n.ip_address || n.ip || '',
    node_type: n.node_type || n.type || 'router',
    status: n.status || 'up',
    x: n.x,
    y: n.y,
    last_seen: n.last_seen,
  }));

  const links: Link[] = (Array.isArray(data.links) ? data.links : []).map((l: any) => {
    const src = l.source_node_id || l.source || '';
    const tgt = l.target_node_id || l.target || '';
    return {
      id: l.id || `link-${src}-${tgt}`,
      source_node_id: src,
      target_node_id: tgt,
      source: src,
      target: tgt,
      status: l.status || 'up',
      weight: typeof l.weight === 'number' ? l.weight : 1,
      bandwidth_mbps: l.bandwidth_mbps ?? l.bandwidth ?? 100,
      latency_ms: l.latency_ms,
    };
  });

  return { nodes, links };
}

// Module-level persistent cache across route changes
let cachedTopology: Topology = DEFAULT_TOPOLOGY;

interface UseTopologyReturn {
  topology: Topology;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useTopology(): UseTopologyReturn {
  const [topology, setTopology] = useState<Topology>(cachedTopology);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const { topology: wsTopology } = useWebSocket();

  const fetchTopology = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getTopology();
      if (data && Array.isArray(data.nodes) && data.nodes.length > 0) {
        const normalized = normalizeTopology(data);
        cachedTopology = normalized;
        setTopology(normalized);
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to fetch topology');
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch on mount
  useEffect(() => {
    fetchTopology();
  }, [fetchTopology]);

  // Update when WebSocket delivers new topology
  useEffect(() => {
    if (wsTopology && Array.isArray(wsTopology.nodes) && wsTopology.nodes.length > 0) {
      const normalized = normalizeTopology(wsTopology);
      cachedTopology = normalized;
      setTopology(normalized);
    }
  }, [wsTopology]);

  return {
    topology,
    loading,
    error,
    refetch: fetchTopology,
  };
}

export default useTopology;
