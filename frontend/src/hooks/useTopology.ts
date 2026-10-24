import { useState, useEffect, useCallback } from 'react';
import { Topology, Node, Link } from '../types';
import { getTopology } from '../services/api';
import { useWebSocket } from './useWebSocket';

/**
 * Empty topology shown until the backend answers
 */
export const EMPTY_TOPOLOGY: Topology = { nodes: [], links: [] };

/**
 * Normalizes raw topology payload from REST API or WebSocket snapshots
 */
export function normalizeTopology(data: any): Topology {
  if (!data || !Array.isArray(data.nodes)) {
    return EMPTY_TOPOLOGY;
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
let cachedTopology: Topology = EMPTY_TOPOLOGY;

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
      const normalized = normalizeTopology(data);
      cachedTopology = normalized;
      setTopology(normalized);
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

  // A pushed topology change carries statuses but not saved positions, so refetch
  useEffect(() => {
    if (!wsTopology) return;
    const timer = setTimeout(fetchTopology, 150);
    return () => clearTimeout(timer);
  }, [wsTopology, fetchTopology]);

  return {
    topology,
    loading,
    error,
    refetch: fetchTopology,
  };
}

export default useTopology;
