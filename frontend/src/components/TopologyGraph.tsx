import React, { useMemo } from 'react';
import { Flowinger, Background, Controls, FlowingerNode, FlowingerEdge } from 'flowinger';
import { Topology, Node, Incident } from '../types';
import { Server, Router, Globe, Cpu, AlertCircle } from 'lucide-react';

interface TopologyGraphProps {
  topology: Topology;
  selectedNodeId?: string | null;
  onNodeSelect?: (node: Node | null) => void;
  activeIncident?: Incident | null;
  className?: string;
  height?: string | number;
}

/**
 * Custom Node renderer for Flowinger
 */
const NetworkNodeComponent: React.FC<{
  id: string;
  data: {
    node: Node;
    isSelected: boolean;
    isAffected: boolean;
    isAlternate: boolean;
  };
}> = ({ data }) => {
  const { node, isSelected, isAffected, isAlternate } = data;

  const status = (node.status || 'up').toLowerCase();
  const isDown = status === 'down' || isAffected;
  const isDegraded = status === 'degraded';

  // Select appropriate icon
  const getIcon = () => {
    switch (node.node_type?.toLowerCase()) {
      case 'core_router':
        return <Router className={`w-5 h-5 ${isDown ? 'text-red-400' : isAlternate ? 'text-cyan-400' : 'text-indigo-400'}`} />;
      case 'gateway':
        return <Globe className={`w-5 h-5 ${isDown ? 'text-red-400' : isAlternate ? 'text-cyan-400' : 'text-sky-400'}`} />;
      case 'server':
        return <Server className={`w-5 h-5 ${isDown ? 'text-red-400' : isAlternate ? 'text-cyan-400' : 'text-emerald-400'}`} />;
      default:
        return <Cpu className={`w-5 h-5 ${isDown ? 'text-red-400' : isAlternate ? 'text-cyan-400' : 'text-blue-400'}`} />;
    }
  };

  return (
    <div
      className={`group relative flex flex-col min-w-[170px] max-w-[210px] rounded-xl border p-3 backdrop-blur-md transition-all duration-300 shadow-xl ${
        isDown
          ? 'border-red-500 bg-red-950/70 ring-2 ring-red-500/50 shadow-red-950/50'
          : isSelected
          ? 'border-blue-500 bg-gray-900/95 ring-2 ring-blue-500/50 shadow-blue-500/10'
          : isAlternate
          ? 'border-cyan-400 bg-cyan-950/60 ring-2 ring-cyan-400/50 shadow-cyan-950/30'
          : isDegraded
          ? 'border-amber-500/80 bg-amber-950/40 ring-1 ring-amber-500/30'
          : 'border-gray-800 bg-gray-900/85 hover:border-gray-700 hover:bg-gray-800/90'
      }`}
    >
      {/* Node Header: Icon, Name & Status Dot */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 overflow-hidden">
          <div className={`p-1.5 rounded-lg border flex-shrink-0 ${
            isDown
              ? 'bg-red-900/50 border-red-500/40'
              : isAlternate
              ? 'bg-cyan-900/40 border-cyan-500/40'
              : 'bg-gray-800/80 border-gray-700/60'
          }`}>
            {getIcon()}
          </div>
          <span className={`font-semibold text-xs truncate tracking-wide ${isDown ? 'text-red-200' : 'text-gray-100'}`}>
            {node.name}
          </span>
        </div>

        {/* Status Indicator Dot */}
        <div className="flex items-center flex-shrink-0">
          <span className="relative flex h-2.5 w-2.5">
            {(isDown || isDegraded) && (
              <span
                className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                  isDown ? 'bg-red-400' : 'bg-amber-400'
                }`}
              />
            )}
            <span
              className={`relative inline-flex rounded-full h-2.5 w-2.5 ${
                isDown
                  ? 'bg-red-500'
                  : isDegraded
                  ? 'bg-amber-500'
                  : 'bg-emerald-400'
              }`}
            />
          </span>
        </div>
      </div>

      {/* Node Subtitle: IP & Type */}
      <div className="mt-2 pt-2 border-t border-gray-800/60 flex items-center justify-between text-[11px] font-mono text-gray-400">
        <span>{node.ip_address}</span>
        <span className={`capitalize text-[10px] px-1.5 py-0.5 rounded ${
          isDown ? 'bg-red-900/40 text-red-300' : 'bg-gray-800/80 text-gray-300'
        }`}>
          {isDown ? 'OFFLINE' : node.node_type?.replace('_', ' ') || 'node'}
        </span>
      </div>

      {isDown && (
        <div className="mt-2 flex items-center gap-1.5 text-[10px] text-red-300 font-semibold bg-red-900/50 border border-red-500/40 px-2 py-0.5 rounded">
          <AlertCircle className="w-3 h-3 text-red-400 animate-pulse flex-shrink-0" />
          <span>FAULT DETECTED</span>
        </div>
      )}
      {!isDown && isAlternate && (
        <div className="mt-2 flex items-center gap-1.5 text-[10px] text-cyan-300 font-semibold bg-cyan-900/50 border border-cyan-400/40 px-2 py-0.5 rounded">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-ping flex-shrink-0" />
          <span>⚡ DETOUR ROUTE</span>
        </div>
      )}
    </div>
  );
};

// Deterministic fixed positions for known topology nodes to prevent layout shifts
const FIXED_LAYOUT: Record<string, { x: number; y: number }> = {
  // 7-Node Multi-Tier Mesh
  'node-core-1': { x: 260, y: 70 },
  'node-core-2': { x: 500, y: 70 },
  'node-edge-1': { x: 120, y: 200 },
  'node-edge-2': { x: 380, y: 200 },
  'node-edge-3': { x: 640, y: 200 },
  'node-gw-1': { x: 240, y: 330 },
  'node-gw-2': { x: 520, y: 330 },
  // 5-Node Campus Topology - Non-overlapping hierarchical layout
  'router-a': { x: 90, y: 210 },
  'router-b': { x: 360, y: 90 },
  'switch-c': { x: 360, y: 330 },
  'server-d': { x: 650, y: 90 },
  'server-e': { x: 650, y: 330 },
};

export const TopologyGraph: React.FC<TopologyGraphProps> = ({
  topology,
  selectedNodeId,
  onNodeSelect,
  activeIncident,
  className = '',
  height = '100%',
}) => {
  // Convert nodes to Flowinger format with layout positioning
  const nodes: FlowingerNode[] = useMemo(() => {
    if (!topology || !topology.nodes) return [];

    return topology.nodes.map((node, index) => {
      // Prioritize explicit node.x, then fixed known coordinate, then tiered grid
      const fixed = FIXED_LAYOUT[node.id];
      const posX =
        node.x ??
        fixed?.x ??
        (index % 3 === 0
          ? 120
          : index % 3 === 1
          ? 380
          : 640);
      const posY =
        node.y ??
        fixed?.y ??
        (80 + Math.floor(index / 3) * 140);

      const isAffected =
        activeIncident?.affected_component === node.id ||
        (node.status || '').toLowerCase() === 'down';

      const isAlternate =
        !isAffected &&
        !!activeIncident?.alternate_path &&
        activeIncident.alternate_path.includes(node.id);

      return {
        id: node.id,
        position: { x: posX, y: posY },
        type: 'networkNode',
        data: {
          node,
          isSelected: selectedNodeId === node.id,
          isAffected,
          isAlternate,
        },
      };
    });
  }, [topology, selectedNodeId, activeIncident]);

  // Convert links to Flowinger edges
  const edges: FlowingerEdge[] = useMemo(() => {
    if (!topology || !topology.links) return [];

    // Find all downed or affected node IDs
    const downedNodeIds = new Set(
      topology.nodes
        ?.filter(
          (n) =>
            (n.status || '').toLowerCase() === 'down' ||
            activeIncident?.affected_component === n.id
        )
        .map((n) => n.id) || []
    );

    // Check alternate path pairs if incident is healing or resolved
    const altPairs = new Set<string>();
    if (activeIncident?.alternate_path && activeIncident.alternate_path.length > 1) {
      for (let i = 0; i < activeIncident.alternate_path.length - 1; i++) {
        const a = activeIncident.alternate_path[i];
        const b = activeIncident.alternate_path[i + 1];
        altPairs.add(`${a}->${b}`);
        altPairs.add(`${b}->${a}`);
      }
    }

    return topology.links.map((link) => {
      const sourceId = link.source_node_id || link.source || '';
      const targetId = link.target_node_id || link.target || '';

      const isDirectlyDown =
        (link.status || '').toLowerCase() === 'down' ||
        activeIncident?.affected_component === link.id;

      const connectsToDownedNode =
        downedNodeIds.has(sourceId) ||
        downedNodeIds.has(targetId);

      const isSevered = isDirectlyDown || connectsToDownedNode;

      const isAlt =
        !isSevered &&
        (altPairs.has(`${sourceId}->${targetId}`) ||
          altPairs.has(`${targetId}->${sourceId}`));

      const edgeStatus = isSevered
        ? 'down'
        : (link.status || 'up').toLowerCase();

      const bandwidth = link.bandwidth_mbps ?? (link as any).bandwidth ?? 100;
      const label = isSevered
        ? '✖ SEVERED'
        : isAlt
        ? '⚡ HEALED'
        : bandwidth >= 1000
        ? `${bandwidth / 1000}G`
        : `${bandwidth}M`;

      return {
        id: link.id || `link-${sourceId}-${targetId}`,
        source: sourceId,
        target: targetId,
        label,
        animated: !isSevered && (edgeStatus === 'up' || isAlt),
        data: {
          status: edgeStatus,
          isAlternate: isAlt,
        },
        style: {
          stroke: isSevered
            ? '#ef4444'
            : isAlt
            ? '#38bdf8'
            : edgeStatus === 'degraded'
            ? '#f59e0b'
            : '#10b981',
          strokeWidth: isAlt ? 4 : isSevered ? 3 : 2,
        },
      };
    });
  }, [topology, activeIncident]);

  const nodeTypes = useMemo(
    () => ({
      networkNode: NetworkNodeComponent,
    }),
    []
  );

  const handleNodeClick = (_e: React.MouseEvent, flowNode: FlowingerNode) => {
    if (onNodeSelect && flowNode.data?.node) {
      onNodeSelect(flowNode.data.node);
    }
  };

  return (
    <div
      className={`relative w-full rounded-2xl overflow-hidden border border-gray-800 bg-gray-950/70 shadow-2xl ${className}`}
      style={{ height }}
    >
      <Flowinger
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={handleNodeClick}
      >
        <Background color="#1e293b" gap={28} size={1.2} />
        <Controls />
      </Flowinger>

      {/* Floating Network Legend */}
      <div className="absolute top-4 left-4 z-10 flex items-center gap-3 px-3 py-1.5 rounded-lg bg-gray-900/90 border border-gray-800 text-xs backdrop-blur shadow-md">
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
          <span className="text-gray-300">Healthy</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-amber-500" />
          <span className="text-gray-300">Degraded</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
          <span className="text-gray-300">Fault / Severed</span>
        </div>
        {activeIncident?.alternate_path && activeIncident.alternate_path.length > 0 && (
          <div className="flex items-center gap-1.5 border-l border-gray-700 pl-3">
            <span className="w-2.5 h-2.5 rounded-full bg-sky-400 animate-pulse" />
            <span className="text-sky-300 font-medium">⚡ Alternate Detour Route</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default TopologyGraph;
