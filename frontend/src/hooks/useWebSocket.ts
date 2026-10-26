import { useState, useEffect, useRef, useCallback } from 'react';
import { Topology, Alert, Metric, WebSocketMessage, IncidentStatus } from '../types';
import { API_ORIGIN } from '../services/api';

interface UseWebSocketReturn {
  lastMessage: WebSocketMessage | null;
  isConnected: boolean;
  topology: Topology | null;
  alerts: Alert[];
  metrics: Record<string, Metric>;
  clearAlerts: () => void;
  sendMessage: (msg: any) => void;
}

export function useWebSocket(url?: string): UseWebSocketReturn {
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const [topology, setTopology] = useState<Topology | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [metrics, setMetrics] = useState<Record<string, Metric>>({});

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef<number>(0);
  const reconnectTimeoutRef = useRef<any>(null);
  const isMountedRef = useRef<boolean>(true);

  // Compute WebSocket URL
  const getWsUrl = useCallback(() => {
    if (url) return url;
    if (API_ORIGIN) return `${API_ORIGIN.replace(/^http/, 'ws')}/ws/live`;
    if (typeof window !== 'undefined') {
      const loc = window.location;
      // If served via Vite proxy or reverse proxy on port 3000, connect through /ws/live
      const protocol = loc.protocol === 'https:' ? 'wss:' : 'ws:';
      return `${protocol}//${loc.host}/ws/live`;
    }
    return 'ws://localhost:8000/ws/live';
  }, [url]);

  const clearAlerts = useCallback(() => {
    setAlerts([]);
  }, []);

  const sendMessage = useCallback((msg: any) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof msg === 'string' ? msg : JSON.stringify(msg));
    }
  }, []);

  const connect = useCallback(() => {
    if (!isMountedRef.current) return;

    try {
      const targetUrl = getWsUrl();
      const ws = new WebSocket(targetUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!isMountedRef.current) return;
        setIsConnected(true);
        reconnectAttemptsRef.current = 0; // Reset backoff
      };

      ws.onmessage = (event) => {
        if (!isMountedRef.current) return;
        try {
          const parsed = JSON.parse(event.data) as WebSocketMessage;
          setLastMessage(parsed);

          const type = (parsed.type || '').toUpperCase();
          const data = parsed.data;

          // Handle Topology Updates
          if (type === 'TOPOLOGY_UPDATED' || type === 'TOPOLOGY') {
            if (data && Array.isArray(data.nodes) && Array.isArray(data.links)) {
              const normalizedTopology: Topology = {
                nodes: data.nodes,
                links: data.links.map((l: any) => {
                  const src = l.source_node_id || l.source || '';
                  const tgt = l.target_node_id || l.target || '';
                  return {
                    ...l,
                    id: l.id || `link-${src}-${tgt}`,
                    source_node_id: src,
                    target_node_id: tgt,
                    source: src,
                    target: tgt,
                    bandwidth_mbps: l.bandwidth_mbps ?? l.bandwidth ?? 100,
                    status: l.status || 'up',
                    weight: typeof l.weight === 'number' ? l.weight : 1,
                  };
                }),
              };
              setTopology(normalizedTopology);
            }
          }

          // Handle Node/Link Metric Updates
          else if (type === 'METRICS_UPDATED' || type === 'METRIC') {
            if (data) {
              if (Array.isArray(data)) {
                setMetrics((prev) => {
                  const next = { ...prev };
                  data.forEach((m: Metric) => {
                    if (m && m.node_id) next[m.node_id] = m;
                  });
                  return next;
                });
              } else if (data.node_id) {
                setMetrics((prev) => ({
                  ...prev,
                  [data.node_id]: data as Metric,
                }));
              }
            }
          }

          // Handle Alert & Incident Lifecycle Updates
          else if (
            type === 'ALERT' ||
            type === 'INCIDENT_DETECTED' ||
            type === 'INCIDENT_UPDATED' ||
            type === 'INCIDENT_HEALED' ||
            type === 'INCIDENT_ESCALATED'
          ) {
            const incident = data;
            if (incident) {
              const severity: Alert['severity'] =
                incident.status === IncidentStatus.ESCALATED || incident.fault_type === 'node_down'
                  ? 'critical'
                  : incident.status === IncidentStatus.VERIFIED
                  ? 'resolved'
                  : incident.status === IncidentStatus.HEALING
                  ? 'info'
                  : 'warning';

              const newAlert: Alert = {
                id: incident.id || `alert-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
                timestamp: incident.detected_at || parsed.timestamp || new Date().toISOString(),
                severity,
                fault_type: incident.fault_type || 'Unknown Fault',
                affected_component: incident.affected_component || incident.source_node || 'Network',
                message:
                  incident.description ||
                  `Fault ${incident.fault_type} detected on ${incident.affected_component || 'component'} (${incident.status})`,
                status: incident.status || 'detected',
                incident_id: incident.id,
              };

              setAlerts((prev) => {
                // Avoid duplicating alerts with same id
                const filtered = prev.filter((a) => a.id !== newAlert.id);
                return [newAlert, ...filtered].slice(0, 50); // Keep last 50
              });
            }
          }
        } catch {
          // Non-JSON message, log or ignore
        }
      };

      ws.onclose = () => {
        if (!isMountedRef.current) return;
        setIsConnected(false);

        // Exponential backoff reconnect: 1s, 2s, 4s, 8s, max 15s
        const backoff = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 15000);
        reconnectAttemptsRef.current += 1;

        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, backoff);
      };

      ws.onerror = () => {
        // ws.onclose will be triggered automatically
      };
    } catch {
      // In case WebSocket instantiation fails
      reconnectTimeoutRef.current = setTimeout(() => {
        connect();
      }, 3000);
    }
  }, [getWsUrl]);

  useEffect(() => {
    isMountedRef.current = true;
    connect();

    return () => {
      isMountedRef.current = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  return {
    lastMessage,
    isConnected,
    topology,
    alerts,
    metrics,
    clearAlerts,
    sendMessage,
  };
}

export default useWebSocket;
