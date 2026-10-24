import React, { useCallback, useEffect, useMemo, useState } from 'react';
import useTopology from '../hooks/useTopology';
import useNetworkMode from '../hooks/useNetworkMode';
import TopologyGraph from '../components/TopologyGraph';
import NodeCard from '../components/NodeCard';
import { AddDeviceDialog, PingTester, WireDialog } from '../components/DeviceDialogs';
import { DeviceType, Link, Node } from '../types';
import {
  addLink,
  addNode,
  deleteLink,
  deleteNode,
  errorMessage,
  simulateFailure,
  simulateRecover,
  updateNode,
} from '../services/api';
import {
  Network,
  RefreshCw,
  Search,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Plus,
  Cable,
  Trash2,
  Scissors,
  Wrench,
  X,
} from 'lucide-react';

const toolbarButton =
  'flex items-center gap-1.5 px-3 py-2 rounded-xl bg-gray-900 border border-gray-800 text-xs font-semibold text-gray-300 hover:text-white hover:bg-gray-800 transition-all';

/**
 * First free spot on a grid so a new device does not land on an existing one
 */
function freePosition(nodes: Node[]): { x: number; y: number } {
  for (let row = 0; row < 20; row++) {
    for (let col = 0; col < 5; col++) {
      const x = 90 + col * 240;
      const y = 80 + row * 150;
      const taken = nodes.some(
        (n) => Math.abs((n.x ?? 0) - x) < 200 && Math.abs((n.y ?? 0) - y) < 110
      );
      if (!taken) return { x, y };
    }
  }
  return { x: 90, y: 80 };
}

export const TopologyView: React.FC = () => {
  const { topology, loading, refetch } = useTopology();
  const { mode } = useNetworkMode();
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedLinkId, setSelectedLinkId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [showAddDevice, setShowAddDevice] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [connectFrom, setConnectFrom] = useState<Node | null>(null);
  const [connectTo, setConnectTo] = useState<Node | null>(null);
  const [notice, setNotice] = useState<{ kind: 'error' | 'info'; text: string } | null>(null);

  const selectedNode = topology.nodes.find((n) => n.id === selectedNodeId) ?? null;
  const selectedLink = topology.links.find((l) => l.id === selectedLinkId) ?? null;
  const nodeName = (id: string) => topology.nodes.find((n) => n.id === id)?.name ?? id;

  const run = useCallback(
    async (action: () => Promise<unknown>, success?: string) => {
      try {
        await action();
        if (success) setNotice({ kind: 'info', text: success });
        await refetch();
      } catch (err) {
        setNotice({ kind: 'error', text: errorMessage(err) });
      }
    },
    [refetch]
  );

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(null), 5000);
    return () => clearTimeout(timer);
  }, [notice]);

  const stopConnecting = useCallback(() => {
    setConnecting(false);
    setConnectFrom(null);
    setConnectTo(null);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && stopConnecting();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [stopConnecting]);

  // Filter nodes for search or filter
  const filteredTopology = useMemo(() => {
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

    return { nodes: filteredNodes, links: filteredLinks };
  }, [topology, searchQuery, statusFilter]);

  const handleNodeSelect = (node: Node | null) => {
    if (!node) return;
    if (connecting) {
      if (!connectFrom) setConnectFrom(node);
      else if (node.id !== connectFrom.id) setConnectTo(node);
      return;
    }
    setSelectedLinkId(null);
    setSelectedNodeId(node.id);
  };

  const handleLinkSelect = (link: Link) => {
    if (connecting) return;
    setSelectedNodeId(null);
    setSelectedLinkId(link.id);
  };

  const handleNodeMove = (nodeId: string, position: { x: number; y: number }) => {
    updateNode(nodeId, position).catch((err) =>
      setNotice({ kind: 'error', text: errorMessage(err) })
    );
  };

  const handleAddDevice = async (device: { name: string; node_type: DeviceType; ip_address: string }) => {
    const created = await addNode({ ...device, ...freePosition(topology.nodes) });
    await refetch();
    setSelectedNodeId(created.id);
    setNotice({ kind: 'info', text: `Added ${device.name}. Use Connect to wire it up.` });
  };

  const healthyCount = topology.nodes.filter((n) => n.status === 'up').length;
  const degradedCount = topology.nodes.filter((n) => n.status === 'degraded').length;
  const downCount = topology.nodes.filter((n) => n.status === 'down').length;

  const connectHint = connecting
    ? connectFrom
      ? `Now click the device to connect to ${connectFrom.name}.`
      : 'Click the first device of the new wire.'
    : null;

  return (
    <div className="flex flex-col h-[calc(100vh-6rem)] relative overflow-hidden">
      {/* Top Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-gray-800">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-indigo-600/20 text-indigo-400 border border-indigo-500/20">
            <Network className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white tracking-tight">Network Topology</h2>
            <p className="text-xs text-gray-400">
              {mode === 'live'
                ? 'Live mode: every device is pinged at its address'
                : 'Simulation mode: devices run in the built-in virtual network'}
              {' · '}drag to arrange, click to edit
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            onClick={() => setShowAddDevice(true)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-on-accent text-xs font-semibold shadow-md shadow-indigo-600/20 transition-all"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Add device</span>
          </button>
          <button
            onClick={() => (connecting ? stopConnecting() : setConnecting(true))}
            aria-pressed={connecting}
            className={
              connecting
                ? 'flex items-center gap-1.5 px-3 py-2 rounded-xl bg-violet-600 text-on-accent text-xs font-semibold shadow-md shadow-violet-600/20 transition-all'
                : toolbarButton
            }
          >
            <Cable className="w-3.5 h-3.5" />
            <span>{connecting ? 'Cancel wiring' : 'Connect'}</span>
          </button>

          {/* Search Input */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-gray-500 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search name or IP..."
              aria-label="Search devices"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-gray-900 border border-gray-800 text-xs text-gray-200 pl-8 pr-3 py-2 rounded-xl focus:outline-none focus:border-indigo-500 font-mono w-44"
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
                statusFilter === 'up' ? 'bg-emerald-950 text-emerald-300' : 'text-gray-400 hover:text-emerald-400'
              }`}
            >
              <CheckCircle2 className="w-3 h-3 text-emerald-400" />
              <span>{healthyCount}</span>
            </button>
            <button
              onClick={() => setStatusFilter('degraded')}
              className={`px-2.5 py-1 rounded-lg transition-colors flex items-center gap-1 ${
                statusFilter === 'degraded' ? 'bg-amber-950 text-amber-300' : 'text-gray-400 hover:text-amber-400'
              }`}
            >
              <AlertTriangle className="w-3 h-3 text-amber-400" />
              <span>{degradedCount}</span>
            </button>
            <button
              onClick={() => setStatusFilter('down')}
              className={`px-2.5 py-1 rounded-lg transition-colors flex items-center gap-1 ${
                statusFilter === 'down' ? 'bg-red-950 text-red-300' : 'text-gray-400 hover:text-red-400'
              }`}
            >
              <XCircle className="w-3 h-3 text-red-400" />
              <span>{downCount}</span>
            </button>
          </div>

          <button onClick={() => refetch()} disabled={loading} className={toolbarButton}>
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span className="hidden md:inline">Refresh</span>
          </button>
        </div>
      </div>

      {/* Main Canvas Area */}
      <div className="flex-1 relative mt-4">
        <TopologyGraph
          topology={filteredTopology}
          selectedNodeId={connecting ? null : selectedNodeId}
          onNodeSelect={handleNodeSelect}
          onNodeMove={handleNodeMove}
          onLinkSelect={handleLinkSelect}
          selectedLinkId={selectedLinkId}
          connectFromId={connectFrom?.id ?? null}
          onPaneClick={() => {
            setSelectedNodeId(null);
            setSelectedLinkId(null);
          }}
          height="100%"
        />

        {(connectHint || notice) && (
          <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-40 animate-pop-in" aria-live="polite">
            <div
              className={`flex items-center gap-2 px-4 py-2 rounded-xl border text-xs font-semibold shadow-lg backdrop-blur ${
                notice?.kind === 'error'
                  ? 'bg-red-950/90 border-red-500/40 text-red-200'
                  : connectHint
                  ? 'bg-violet-950/90 border-violet-500/40 text-violet-200'
                  : 'bg-gray-900/95 border-gray-700 text-gray-200'
              }`}
            >
              <span>{notice?.text ?? connectHint}</span>
              {notice && (
                <button onClick={() => setNotice(null)} aria-label="Dismiss" className="opacity-70 hover:opacity-100">
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>
        )}

        {/* Device drawer */}
        {selectedNode && !connecting && (
          <div className="absolute top-4 right-4 bottom-4 z-30 w-80 sm:w-96 overflow-y-auto animate-slide-in">
            <NodeCard
              key={selectedNode.id}
              node={selectedNode}
              onClose={() => setSelectedNodeId(null)}
              onSimulateFail={
                mode === 'simulation'
                  ? (id) =>
                      run(
                        () => simulateFailure({ target_type: 'node', target_id: id, fault_type: 'node_down' }),
                        'Device crashed. The monitor confirms it after 3 failed probes.'
                      )
                  : undefined
              }
              onRecover={
                mode === 'simulation'
                  ? (id) => run(() => simulateRecover({ target_type: 'node', target_id: id }), 'Device repaired.')
                  : undefined
              }
            >
              <DeviceEditor
                node={selectedNode}
                onSave={(changes) => run(() => updateNode(selectedNode.id, changes), 'Device updated.')}
                onDelete={() =>
                  run(async () => {
                    await deleteNode(selectedNode.id);
                    setSelectedNodeId(null);
                  }, `Removed ${selectedNode.name} and its wires.`)
                }
              />
            </NodeCard>
          </div>
        )}

        {/* Wire panel */}
        {selectedLink && !connecting && (
          <div className="absolute bottom-4 right-4 z-30 w-80 animate-slide-in">
            <div className="bg-gray-900/95 border border-gray-800 rounded-2xl p-4 shadow-2xl backdrop-blur-xl space-y-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h3 className="text-sm font-bold text-white flex items-center gap-1.5">
                    <Cable className="w-4 h-4 text-violet-400" />
                    Wire
                  </h3>
                  <p className="text-xs text-gray-400 font-mono mt-0.5">
                    {nodeName(selectedLink.source_node_id)} ↔ {nodeName(selectedLink.target_node_id)}
                  </p>
                </div>
                <button
                  onClick={() => setSelectedLinkId(null)}
                  aria-label="Close"
                  className="p-1 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <dl className="grid grid-cols-3 gap-2 text-xs">
                <div className="bg-gray-800/50 rounded-lg p-2">
                  <dt className="text-gray-400">Status</dt>
                  <dd className={`font-semibold ${selectedLink.status === 'up' ? 'text-emerald-400' : 'text-red-400'}`}>
                    {selectedLink.status}
                  </dd>
                </div>
                <div className="bg-gray-800/50 rounded-lg p-2">
                  <dt className="text-gray-400">Bandwidth</dt>
                  <dd className="font-semibold text-gray-100">
                    {selectedLink.bandwidth_mbps >= 1000
                      ? `${selectedLink.bandwidth_mbps / 1000} Gbit/s`
                      : `${selectedLink.bandwidth_mbps} Mbit/s`}
                  </dd>
                </div>
                <div className="bg-gray-800/50 rounded-lg p-2">
                  <dt className="text-gray-400">Cost</dt>
                  <dd className="font-semibold text-gray-100">{selectedLink.weight}</dd>
                </div>
              </dl>
              <div className="flex gap-2">
                {selectedLink.status === 'up' ? (
                  <button
                    onClick={() =>
                      run(
                        () => simulateFailure({ target_type: 'link', target_id: selectedLink.id, fault_type: 'link_down' }),
                        'Wire cut. The monitor confirms it after 3 failed probes.'
                      )
                    }
                    className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl bg-red-600/80 hover:bg-red-600 text-on-accent text-xs font-semibold transition-all"
                  >
                    <Scissors className="w-3.5 h-3.5" />
                    Cut wire
                  </button>
                ) : (
                  <button
                    onClick={() =>
                      run(() => simulateRecover({ target_type: 'link', target_id: selectedLink.id }), 'Wire repaired.')
                    }
                    className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-on-accent text-xs font-semibold transition-all"
                  >
                    <Wrench className="w-3.5 h-3.5" />
                    Repair wire
                  </button>
                )}
                <button
                  onClick={() =>
                    run(async () => {
                      await deleteLink(selectedLink.id);
                      setSelectedLinkId(null);
                    }, 'Wire removed.')
                  }
                  className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl border border-gray-700 text-gray-300 hover:text-red-400 hover:border-red-500/50 text-xs font-semibold transition-all"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  Remove
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {showAddDevice && <AddDeviceDialog onClose={() => setShowAddDevice(false)} onAdd={handleAddDevice} />}

      {connectFrom && connectTo && (
        <WireDialog
          source={connectFrom}
          target={connectTo}
          onClose={stopConnecting}
          onConnect={async (wire) => {
            await addLink({ source: connectFrom.id, target: connectTo.id, ...wire });
            await refetch();
            setNotice({ kind: 'info', text: `Connected ${connectFrom.name} and ${connectTo.name}.` });
          }}
        />
      )}
    </div>
  );
};

/**
 * Edit form shown in the device drawer
 */
const DeviceEditor: React.FC<{
  node: Node;
  onSave: (changes: { name: string; node_type: DeviceType; ip_address: string }) => void;
  onDelete: () => void;
}> = ({ node, onSave, onDelete }) => {
  const [name, setName] = useState(node.name);
  const [nodeType, setNodeType] = useState<DeviceType>((node.node_type as DeviceType) || 'router');
  const [address, setAddress] = useState(node.ip_address);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const changed = name !== node.name || nodeType !== node.node_type || address !== node.ip_address;
  const field =
    'w-full bg-gray-950 border border-gray-800 rounded-lg px-2.5 py-1.5 text-xs text-gray-100 focus:outline-none focus:border-indigo-500';

  return (
    <div className="border-t border-gray-800/80 pt-3 space-y-2.5">
      <p className="text-xs font-semibold text-gray-300">Edit device</p>
      <div className="grid grid-cols-2 gap-2">
        <label className="space-y-1">
          <span className="text-[11px] text-gray-400">Name</span>
          <input className={field} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="space-y-1">
          <span className="text-[11px] text-gray-400">Type</span>
          <select className={field} value={nodeType} onChange={(e) => setNodeType(e.target.value as DeviceType)}>
            <option value="router">Router</option>
            <option value="switch">Switch</option>
            <option value="server">Server</option>
          </select>
        </label>
      </div>
      <label className="block space-y-1">
        <span className="text-[11px] text-gray-400">IP address or hostname</span>
        <input className={`${field} font-mono`} value={address} onChange={(e) => setAddress(e.target.value)} />
      </label>
      <PingTester address={address} />
      <div className="flex gap-2 pt-1">
        <button
          disabled={!changed}
          onClick={() => onSave({ name: name.trim(), node_type: nodeType, ip_address: address.trim() })}
          className="flex-1 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-on-accent text-xs font-semibold transition-all"
        >
          Save changes
        </button>
        {confirmDelete ? (
          <button
            onClick={onDelete}
            className="px-3 py-2 rounded-xl bg-red-600 hover:bg-red-500 text-on-accent text-xs font-semibold transition-all"
          >
            Confirm remove
          </button>
        ) : (
          <button
            onClick={() => setConfirmDelete(true)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-gray-700 text-gray-300 hover:text-red-400 hover:border-red-500/50 text-xs font-semibold transition-all"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Remove
          </button>
        )}
      </div>
    </div>
  );
};

export default TopologyView;
