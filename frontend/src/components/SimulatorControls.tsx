import React, { useState } from 'react';
import { Node, Link, FaultType } from '../types';
import {
  Zap,
  ZapOff,
  RotateCcw,
  AlertTriangle,
  CheckCircle,
  Activity,
  Layers,
  ArrowRightLeft,
} from 'lucide-react';

interface SimulatorControlsProps {
  nodes: Node[];
  links: Link[];
  onInjectFailure: (targetType: 'node' | 'link', targetId: string, faultType: FaultType | string) => Promise<void>;
  onRecover: (targetType: 'node' | 'link', targetId: string) => Promise<void>;
  onResetAll: () => Promise<void>;
  isLoading?: boolean;
}

export const SimulatorControls: React.FC<SimulatorControlsProps> = ({
  nodes = [],
  links = [],
  onInjectFailure,
  onRecover,
  onResetAll,
  isLoading = false,
}) => {
  const [targetType, setTargetType] = useState<'node' | 'link'>('node');
  const [selectedTargetId, setSelectedTargetId] = useState<string>('');
  const [selectedFaultType, setSelectedFaultType] = useState<string>(FaultType.NODE_DOWN);
  const [statusMessage, setStatusMessage] = useState<{ text: string; type: 'success' | 'error' | 'info' } | null>(null);

  // Set default target ID if not selected
  const activeTargetId =
    selectedTargetId ||
    (targetType === 'node' ? nodes[0]?.id || '' : links[0]?.id || '');

  const handleTargetTypeChange = (type: 'node' | 'link') => {
    setTargetType(type);
    if (type === 'node') {
      setSelectedTargetId(nodes[0]?.id || '');
      setSelectedFaultType(FaultType.NODE_DOWN);
    } else {
      setSelectedTargetId(links[0]?.id || '');
      setSelectedFaultType(FaultType.LINK_DOWN);
    }
  };

  const handleTriggerInject = async () => {
    if (!activeTargetId) return;
    try {
      await onInjectFailure(targetType, activeTargetId, selectedFaultType);
      setStatusMessage({
        text: `Injected ${selectedFaultType} into ${activeTargetId}. Graph reacting...`,
        type: 'success',
      });
      setTimeout(() => setStatusMessage(null), 5000);
    } catch (err: any) {
      setStatusMessage({
        text: err?.message || 'Failed to inject fault',
        type: 'error',
      });
    }
  };

  const executeRecover = async () => {
    try {
      await onRecover(targetType, activeTargetId);
      setStatusMessage({
        text: `Recovered ${targetType} [${activeTargetId}] to healthy baseline`,
        type: 'success',
      });
      setTimeout(() => setStatusMessage(null), 5000);
    } catch (err: any) {
      setStatusMessage({
        text: err?.message || 'Failed to recover component',
        type: 'error',
      });
    }
  };

  const executeResetAll = async () => {
    try {
      await onResetAll();
      setStatusMessage({
        text: 'All simulated faults cleared. Complete network returned to UP state.',
        type: 'success',
      });
      setTimeout(() => setStatusMessage(null), 5000);
    } catch (err: any) {
      setStatusMessage({
        text: err?.message || 'Failed to reset network simulations',
        type: 'error',
      });
    }
  };

  return (
    <div className="bg-gray-900/90 border border-gray-800 rounded-2xl p-5 shadow-2xl backdrop-blur-xl flex flex-col gap-5">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-gray-800">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <Zap className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-bold text-base text-white">Chaos & Failure Simulator</h3>
            <p className="text-xs text-gray-400">Inject active faults to evaluate self-healing detection</p>
          </div>
        </div>

        {/* Reset All Button */}
        <button
          onClick={executeResetAll}
          disabled={isLoading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white border border-gray-700 text-xs font-semibold transition-all"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>Reset All</span>
        </button>
      </div>

      {/* Target Category Tabs */}
      <div className="flex bg-gray-950 p-1 rounded-xl border border-gray-800">
        <button
          type="button"
          onClick={() => handleTargetTypeChange('node')}
          className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-semibold transition-all ${
            targetType === 'node'
              ? 'bg-indigo-600 text-white shadow-md'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          <Layers className="w-4 h-4" />
          <span>Node Target</span>
        </button>

        <button
          type="button"
          onClick={() => handleTargetTypeChange('link')}
          className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-semibold transition-all ${
            targetType === 'link'
              ? 'bg-indigo-600 text-white shadow-md'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          <ArrowRightLeft className="w-4 h-4" />
          <span>Link Target</span>
        </button>
      </div>

      {/* Selection Form */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Component Selector */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-gray-300">
            Target {targetType === 'node' ? 'Node' : 'Link'}
          </label>
          <select
            value={activeTargetId}
            onChange={(e) => setSelectedTargetId(e.target.value)}
            className="w-full bg-gray-800/80 border border-gray-700 text-gray-200 text-xs rounded-xl px-3 py-2.5 focus:outline-none focus:border-indigo-500 font-mono"
          >
            {targetType === 'node'
              ? nodes.map((n) => (
                  <option key={n.id} value={n.id}>
                    {n.name} ({n.ip_address}) [{n.status}]
                  </option>
                ))
              : links.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.id}: {l.source_node_id} ➔ {l.target_node_id} [{l.status}]
                  </option>
                ))}
          </select>
        </div>

        {/* Fault Type Selector */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-gray-300">Fault Mechanism</label>
          <select
            value={selectedFaultType}
            onChange={(e) => setSelectedFaultType(e.target.value)}
            className="w-full bg-gray-800/80 border border-gray-700 text-gray-200 text-xs rounded-xl px-3 py-2.5 focus:outline-none focus:border-indigo-500 capitalize font-mono"
          >
            {targetType === 'node' ? (
              <>
                <option value={FaultType.NODE_DOWN}>Node Crash / Down (node_down)</option>
                <option value={FaultType.HIGH_LATENCY}>High Latency Spike (high_latency)</option>
                <option value={FaultType.PACKET_LOSS}>Packet Dropper (packet_loss)</option>
              </>
            ) : (
              <>
                <option value={FaultType.LINK_DOWN}>Fiber Cut / Link Down (link_down)</option>
                <option value={FaultType.LINK_DEGRADED}>Link Degradation (link_degraded)</option>
                <option value={FaultType.HIGH_LATENCY}>Congestion / High Latency</option>
                <option value={FaultType.PACKET_LOSS}>Intermittent Packet Loss</option>
              </>
            )}
          </select>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex flex-wrap gap-3 pt-2">
        <button
          onClick={handleTriggerInject}
          disabled={isLoading || !activeTargetId}
          className="flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-red-600 hover:bg-red-500 text-white font-semibold text-xs shadow-lg shadow-red-900/30 transition-all disabled:opacity-50"
        >
          <ZapOff className="w-4 h-4" />
          <span>Inject {targetType === 'node' ? 'Node' : 'Link'} Failure</span>
        </button>

        <button
          onClick={executeRecover}
          disabled={isLoading || !activeTargetId}
          className="flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs shadow-lg shadow-emerald-900/30 transition-all disabled:opacity-50"
        >
          <CheckCircle className="w-4 h-4" />
          <span>Recover {targetType === 'node' ? 'Node' : 'Link'}</span>
        </button>
      </div>

      {/* Status banner */}
      {statusMessage && (
        <div
          className={`p-3 rounded-xl border text-xs flex items-center gap-2 animate-slide-in ${
            statusMessage.type === 'success'
              ? 'bg-emerald-950/60 border-emerald-500/50 text-emerald-300'
              : 'bg-red-950/60 border-red-500/50 text-red-300'
          }`}
        >
          <Activity className="w-4 h-4 flex-shrink-0" />
          <span>{statusMessage.text}</span>
        </div>
      )}
    </div>
  );
};

export default SimulatorControls;
