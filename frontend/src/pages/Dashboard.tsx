import React, { useState, useEffect, useCallback } from 'react';
import {
  Topology,
  DashboardStats,
  Incident,
  Node,
  Alert,
} from '../types';
import { getDashboardStats, getIncidents, simulateRecover, simulateFailure } from '../services/api';
import useTopology from '../hooks/useTopology';
import useWebSocket from '../hooks/useWebSocket';
import TopologyGraph from '../components/TopologyGraph';
import AlertPanel from '../components/AlertPanel';
import NodeCard from '../components/NodeCard';
import StatusBadge from '../components/StatusBadge';
import {
  Server,
  Activity,
  AlertTriangle,
  CheckCircle2,
  Radio,
  Clock,
  ShieldCheck,
  ArrowUpRight,
  RefreshCw,
} from 'lucide-react';

export const Dashboard: React.FC = () => {
  const { topology, refetch: refetchTopology } = useTopology();
  const { isConnected, alerts: wsAlerts, clearAlerts, metrics } = useWebSocket();

  const [stats, setStats] = useState<DashboardStats>({
    total_nodes: 0,
    nodes_up: 0,
    nodes_down: 0,
    total_links: 0,
    links_up: 0,
    active_incidents: 0,
    resolved_incidents: 0,
    avg_latency_ms: null,
    avg_packet_loss_pct: null,
    uptime_pct: 0,
  });

  const [recentIncidents, setRecentIncidents] = useState<Incident[]>([]);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);

  // A healed incident keeps traffic on its detour until the failed component comes back up
  const isComponentStillDown = (inc: Incident): boolean => {
    if (!topology) return false;
    const node = topology.nodes.find((n) => n.id === inc.affected_component);
    if (node) return node.status !== 'up';
    const endpoints = [inc.source_node, inc.target_node];
    return topology.links.some(
      (l) =>
        l.status !== 'up' &&
        endpoints.includes(l.source_node_id) &&
        endpoints.includes(l.target_node_id)
    );
  };

  // Active incident for path highlighting
  const activeIncident =
    recentIncidents.find(
      (inc) => inc.status !== 'verified' && (inc.status as string) !== 'resolved' && !inc.resolved_at
    ) ??
    recentIncidents.find((inc) => !!inc.alternate_path?.length && isComponentStillDown(inc));

  const fetchStatsAndIncidents = useCallback(async () => {
    try {
      setIsRefreshing(true);
      const [statsData, incidentsData] = await Promise.allSettled([
        getDashboardStats(),
        getIncidents(),
      ]);

      if (statsData.status === 'fulfilled' && statsData.value) {
        setStats(statsData.value);
      } else if (topology) {
        // Derive stats from current topology if API unavailable
        const upNodes = topology.nodes.filter((n) => n.status === 'up').length;
        const downNodes = topology.nodes.filter((n) => n.status === 'down').length;
        const upLinks = topology.links.filter((l) => l.status === 'up').length;

        setStats((prev) => ({
          ...prev,
          total_nodes: topology.nodes.length,
          nodes_up: upNodes,
          nodes_down: downNodes,
          total_links: topology.links.length,
          links_up: upLinks,
        }));
      }

      if (incidentsData.status === 'fulfilled' && incidentsData.value) {
        setRecentIncidents(incidentsData.value.slice(0, 5));
      }
    } catch {
      // Keep existing state
    } finally {
      setIsRefreshing(false);
    }
  }, [topology]);

  useEffect(() => {
    fetchStatsAndIncidents();
    const interval = setInterval(fetchStatsAndIncidents, 10000);
    return () => clearInterval(interval);
  }, [fetchStatsAndIncidents]);

  const handleSimulateFail = async (nodeId: string) => {
    try {
      await simulateFailure({ target_type: 'node', target_id: nodeId, fault_type: 'node_down' });
      await refetchTopology();
      await fetchStatsAndIncidents();
    } catch {
      // Handled
    }
  };

  const handleRecover = async (nodeId: string) => {
    try {
      await simulateRecover({ target_type: 'node', target_id: nodeId });
      await refetchTopology();
      await fetchStatsAndIncidents();
    } catch {
      // Handled
    }
  };

  return (
    <div className="space-y-6 pb-12">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-white tracking-tight flex items-center gap-2">
            <span>Operations Dashboard</span>
            <span
              className={`inline-block w-2.5 h-2.5 rounded-full ${
                isConnected ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'
              }`}
            />
          </h2>
          <p className="text-xs text-gray-400 mt-1">
            Real-time topology telemetry, automated fault isolation & dynamic healing status
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              refetchTopology();
              fetchStatsAndIncidents();
            }}
            disabled={isRefreshing}
            className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-gray-900 border border-gray-800 text-xs font-semibold text-gray-300 hover:text-white hover:bg-gray-800 transition-all shadow-sm"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Top Stat Cards Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3.5">
        {/* Total Nodes */}
        <div className="bg-gray-900/80 border border-gray-800/80 rounded-2xl p-4 flex flex-col justify-between backdrop-blur shadow-lg">
          <div className="flex items-center justify-between text-gray-400">
            <span className="text-xs font-medium">Nodes</span>
            <Server className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="mt-2">
            <div className="text-2xl font-black text-white tracking-tight">
              {stats.total_nodes}
            </div>
            <div className="text-[11px] text-gray-400 mt-1 flex items-center gap-1.5 font-mono">
              <span className="text-emerald-400">{stats.nodes_up} Up</span>
              <span>•</span>
              <span className={stats.nodes_down > 0 ? 'text-red-400 font-bold' : 'text-gray-500'}>
                {stats.nodes_down} Down
              </span>
            </div>
          </div>
        </div>

        {/* Links */}
        <div className="bg-gray-900/80 border border-gray-800/80 rounded-2xl p-4 flex flex-col justify-between backdrop-blur shadow-lg">
          <div className="flex items-center justify-between text-gray-400">
            <span className="text-xs font-medium">Mesh Links</span>
            <Radio className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="mt-2">
            <div className="text-2xl font-black text-white tracking-tight">
              {stats.total_links}
            </div>
            <div className="text-[11px] text-gray-400 mt-1 flex items-center gap-1.5 font-mono">
              <span className="text-emerald-400">{stats.links_up} Active</span>
            </div>
          </div>
        </div>

        {/* Active Incidents */}
        <div className="bg-gray-900/80 border border-gray-800/80 rounded-2xl p-4 flex flex-col justify-between backdrop-blur shadow-lg">
          <div className="flex items-center justify-between text-gray-400">
            <span className="text-xs font-medium">Active Faults</span>
            <AlertTriangle className="w-4 h-4 text-amber-400" />
          </div>
          <div className="mt-2">
            <div
              className={`text-2xl font-black tracking-tight ${
                stats.active_incidents > 0 ? 'text-red-400 animate-pulse' : 'text-white'
              }`}
            >
              {stats.active_incidents}
            </div>
            <div className="text-[11px] text-gray-400 mt-1 font-mono">
              {stats.active_incidents > 0 ? 'Automated Reroute In Flight' : 'Clean Operations'}
            </div>
          </div>
        </div>

        {/* Resolved / Healed */}
        <div className="bg-gray-900/80 border border-gray-800/80 rounded-2xl p-4 flex flex-col justify-between backdrop-blur shadow-lg">
          <div className="flex items-center justify-between text-gray-400">
            <span className="text-xs font-medium">Healed Incidents</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="mt-2">
            <div className="text-2xl font-black text-emerald-400 tracking-tight">
              {stats.resolved_incidents}
            </div>
            <div className="text-[11px] text-gray-400 mt-1 font-mono">Auto-Recovered</div>
          </div>
        </div>

        {/* Avg Latency */}
        <div className="bg-gray-900/80 border border-gray-800/80 rounded-2xl p-4 flex flex-col justify-between backdrop-blur shadow-lg">
          <div className="flex items-center justify-between text-gray-400">
            <span className="text-xs font-medium">Avg Latency</span>
            <Activity className="w-4 h-4 text-blue-400" />
          </div>
          <div className="mt-2">
            <div className="text-2xl font-black text-white tracking-tight flex items-baseline gap-1">
              <span>{stats.avg_latency_ms === null ? '—' : stats.avg_latency_ms.toFixed(1)}</span>
              <span className="text-xs font-mono text-gray-400">ms</span>
            </div>
            <div className="text-[11px] text-gray-400 mt-1 font-mono flex items-center gap-1">
              <span>Last 100 probes</span>
            </div>
          </div>
        </div>

        {/* Network Uptime */}
        <div className="bg-gray-900/80 border border-gray-800/80 rounded-2xl p-4 flex flex-col justify-between backdrop-blur shadow-lg">
          <div className="flex items-center justify-between text-gray-400">
            <span className="text-xs font-medium">Devices Reachable</span>
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="mt-2">
            <div className="text-2xl font-black text-white tracking-tight">
              {stats.uptime_pct.toFixed(2)}%
            </div>
            <div className="text-[11px] text-gray-400 mt-1 font-mono">
              {stats.nodes_up} of {stats.total_nodes} answering
            </div>
          </div>
        </div>
      </div>

      {/* Main Mid Section: Topology Graph + Alert Feed */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Topology View (2 Cols) */}
        <div className="lg:col-span-2 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-gray-200 uppercase tracking-wider flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-indigo-500" />
              <span>Live Mesh Topology</span>
            </h3>
            <span className="text-xs text-gray-500 font-mono">
              Click node for diagnostics & simulation
            </span>
          </div>

          <TopologyGraph
            topology={topology}
            activeIncident={activeIncident}
            selectedNodeId={selectedNode?.id}
            onNodeSelect={(node) => setSelectedNode(node)}
            height="460px"
          />
        </div>

        {/* Alert Feed Panel (1 Col) */}
        <div className="flex flex-col gap-3">
          <h3 className="text-sm font-bold text-gray-200 uppercase tracking-wider flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-red-500" />
            <span>Telemetry Alerts</span>
          </h3>
          <AlertPanel
            alerts={wsAlerts}
            onClearAll={clearAlerts}
            onSelectAlert={(a) => {
              const matchedNode = topology.nodes.find((n) => n.id === a.affected_component);
              if (matchedNode) setSelectedNode(matchedNode);
            }}
            maxHeight="440px"
          />
        </div>
      </div>

      {/* Node Detail Modal / Overlay if selected */}
      {selectedNode && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="max-w-md w-full">
            <NodeCard
              node={selectedNode}
              onClose={() => setSelectedNode(null)}
              onSimulateFail={handleSimulateFail}
              onRecover={handleRecover}
            />
          </div>
        </div>
      )}

      {/* Bottom Section: Recent Incidents List */}
      <div className="bg-gray-900/90 border border-gray-800 rounded-2xl p-5 shadow-xl backdrop-blur-xl">
        <div className="flex items-center justify-between pb-4 border-b border-gray-800">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-gray-800 text-indigo-400">
              <Clock className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-white">Recent Network Incidents & Heals</h3>
              <p className="text-xs text-gray-400">
                Audit log of detected anomalies and automated bypass actions
              </p>
            </div>
          </div>
          <a
            href="/incidents"
            className="flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 font-semibold"
          >
            <span>View All</span>
            <ArrowUpRight className="w-3.5 h-3.5" />
          </a>
        </div>

        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-xs font-mono text-gray-300">
            <thead>
              <tr className="border-b border-gray-800/80 text-gray-500">
                <th className="pb-3 font-semibold">INCIDENT ID</th>
                <th className="pb-3 font-semibold">FAULT TYPE</th>
                <th className="pb-3 font-semibold">TARGET COMPONENT</th>
                <th className="pb-3 font-semibold">DETECTED AT</th>
                <th className="pb-3 font-semibold">STATUS</th>
                <th className="pb-3 font-semibold">HEALING PATH</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/40">
              {recentIncidents.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-6 text-center text-gray-500 font-sans">
                    No recent network incidents recorded.
                  </td>
                </tr>
              ) : (
                recentIncidents.map((inc) => (
                  <tr key={inc.id} className="hover:bg-gray-800/30 transition-colors">
                    <td className="py-3 text-indigo-400 font-bold">{inc.id.slice(0, 8)}</td>
                    <td className="py-3 capitalize text-white">
                      {inc.fault_type.replace('_', ' ')}
                    </td>
                    <td className="py-3 text-gray-300 font-semibold">
                      {inc.affected_component}
                    </td>
                    <td className="py-3 text-gray-400">
                      {new Date(inc.detected_at).toLocaleTimeString()}
                    </td>
                    <td className="py-3">
                      <StatusBadge status={inc.status} size="sm" />
                    </td>
                    <td className="py-3 text-gray-400">
                      {inc.alternate_path?.length ? (
                        <span className="text-emerald-400 font-medium">
                          {inc.alternate_path.join(' ➔ ')}
                        </span>
                      ) : (
                        <span className="text-gray-500">-</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
