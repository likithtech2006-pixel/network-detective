import React, { useState } from 'react';
import useTopology from '../hooks/useTopology';
import useWebSocket from '../hooks/useWebSocket';
import TopologyGraph from '../components/TopologyGraph';
import NodeCard from '../components/NodeCard';
import { Node } from '../types';
import { simulateFailure, simulateRecover } from '../services/api';
import {
  Network,
  RefreshCw,
  Search,
  Filter,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Eye,
  EyeOff,
} from 'lucide-react';

export const TopologyView: React.FC = () => {
  const { topology, loading, refetch } = useTopology();
  const { metrics } = useWebSocket();
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [showLabels, setShowLabels] = useState<boolean>(true);

  // Filter nodes for search or filter
  const filteredTopology = React.useMemo(() => {
    let filteredNodes = topology.nodes;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      filteredNodes = filteredNodes.filter(
        (n) => n.name.toLowerCase().includes(q) || n.ip_address.includes(q)
      );
    }
    if (statusFilter !== 'all') {
      filteredNodes = filteredNodes.filter((n) => n.status.toLowerCase() === statusFilter);
    }

    const nodeIds = new Set(filteredNodes.map((n) => n.id));
    const filteredLinks = topology.links.filter((l) => {
      const src = l.source_node_id || l.source;
      const tgt = l.target_node_id || l.target;
      return nodeIds.has(src || '') && nodeIds.has(tgt || '');
    });

    return {
      nodes: filteredNodes,
      links: filteredLinks,
    };
  }, [topology, searchQuery, statusFilter]);

  const handleSimulateFail = async (nodeId: string) => {
    await simulateFailure({ target_type: 'node', target_id: nodeId, fault_type: 'node_down' });
    await refetch();
    // Update local selected node status
    setSelectedNode((prev) => (prev ? { ...prev, status: 'down' } : null));
  };

  const handleRecover = async (nodeId: string) => {
    await simulateRecover({ target_type: 'node', target_id: nodeId });
    await refetch();
    // Update local selected node status
    setSelectedNode((prev) => (prev ? { ...prev, status: 'up' } : null));
  };

  const healthyCount = topology.nodes.filter((n) => n.status === 'up').length;
  const degradedCount = topology.nodes.filter((n) => n.status === 'degraded').length;
  const downCount = topology.nodes.filter((n) => n.status === 'down').length;

  return (
    <div className="flex flex-col h-[calc(100vh-6rem)] relative overflow-hidden">
      {/* Top Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-gray-800">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-indigo-600/20 text-indigo-400 border border-indigo-500/20">
            <Network className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white tracking-tight">Full Topology Canvas</h2>
            <p className="text-xs text-gray-400">
              Interactive node mesh visualizer with real-time status and link load
            </p>
          </div>
        </div>

        {/* Action Controls & Filters */}
        <div className="flex items-center gap-2.5">
          {/* Search Input */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-gray-500 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search node or IP..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-gray-900 border border-gray-800 text-xs text-gray-200 pl-8 pr-3 py-2 rounded-xl focus:outline-none focus:border-indigo-500 font-mono w-48"
            />
          </div>

          {/* Status Filter Chips */}
          <div className="hidden sm:flex items-center bg-gray-900 border border-gray-800 rounded-xl p-1 text-xs font-semibold">
            <button
              onClick={() => setStatusFilter('all')}
              className={`px-2.5 py-1 rounded-lg transition-colors ${
                statusFilter === 'all' ? 'bg-gray-800 text-white' : 'text-gray-400 hover:text-white'
              }`}
            >
              All ({topology.nodes.length})
            </button>
            <button
              onClick={() => setStatusFilter('up')}
              className={`px-2.5 py-1 rounded-lg transition-colors flex items-center gap-1 ${
                statusFilter === 'up'
                  ? 'bg-emerald-950 text-emerald-300'
                  : 'text-gray-400 hover:text-emerald-400'
              }`}
            >
              <CheckCircle2 className="w-3 h-3 text-emerald-400" />
              <span>{healthyCount}</span>
            </button>
            <button
              onClick={() => setStatusFilter('degraded')}
              className={`px-2.5 py-1 rounded-lg transition-colors flex items-center gap-1 ${
                statusFilter === 'degraded'
                  ? 'bg-amber-950 text-amber-300'
                  : 'text-gray-400 hover:text-amber-400'
              }`}
            >
              <AlertTriangle className="w-3 h-3 text-amber-400" />
              <span>{degradedCount}</span>
            </button>
            <button
              onClick={() => setStatusFilter('down')}
              className={`px-2.5 py-1 rounded-lg transition-colors flex items-center gap-1 ${
                statusFilter === 'down'
                  ? 'bg-red-950 text-red-300'
                  : 'text-gray-400 hover:text-red-400'
              }`}
            >
              <XCircle className="w-3 h-3 text-red-400" />
              <span>{downCount}</span>
            </button>
          </div>

          {/* Toggle Labels */}
          <button
            onClick={() => setShowLabels(!showLabels)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-gray-900 border border-gray-800 text-xs font-semibold text-gray-300 hover:text-white hover:bg-gray-800 transition-all"
            title="Toggle link label visibility"
          >
            {showLabels ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5 text-gray-500" />}
            <span className="hidden md:inline">Labels</span>
          </button>

          {/* Refresh Button */}
          <button
            onClick={() => refetch()}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-gray-900 border border-gray-800 text-xs font-semibold text-gray-300 hover:text-white hover:bg-gray-800 transition-all"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span className="hidden md:inline">Refetch</span>
          </button>
        </div>
      </div>

      {/* Main Canvas Area */}
      <div className="flex-1 relative mt-4">
        <TopologyGraph
          topology={filteredTopology}
          selectedNodeId={selectedNode?.id}
          onNodeSelect={(node) => setSelectedNode(node)}
          height="100%"
        />

        {/* Slide-in Node Detail Drawer */}
        {selectedNode && (
          <div className="absolute top-4 right-4 z-30 w-80 sm:w-96 animate-slide-in">
            <NodeCard
              node={selectedNode}
              metrics={metrics[selectedNode.id] ? [metrics[selectedNode.id]] : []}
              onClose={() => setSelectedNode(null)}
              onSimulateFail={handleSimulateFail}
              onRecover={handleRecover}
            />
          </div>
        )}
      </div>
    </div>
  );
};

export default TopologyView;
