import React, { useEffect, useState } from 'react';
import { Node, Metric } from '../types';
import { getNodeMetrics } from '../services/api';
import StatusBadge from './StatusBadge';
import {
  Server,
  Activity,
  Radio,
  Clock,
  ShieldCheck,
  X,
  ZapOff,
  RotateCcw,
} from 'lucide-react';

interface NodeCardProps {
  node: Node;
  onClose?: () => void;
  onSimulateFail?: (nodeId: string) => void;
  onRecover?: (nodeId: string) => void;
  className?: string;
  /** Extra controls (e.g. the topology editor's form) shown under the stats */
  children?: React.ReactNode;
}

export const NodeCard: React.FC<NodeCardProps> = ({
  node,
  onClose,
  onSimulateFail,
  onRecover,
  className = '',
  children,
}) => {
  const [samples, setSamples] = useState<Metric[]>([]);

  // Stored probe results for this device, oldest first
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await getNodeMetrics(node.id, 20);
        if (!cancelled) {
          setSamples(
            [...data].sort((a, b) => Date.parse(a.recorded_at) - Date.parse(b.recorded_at))
          );
        }
      } catch {
        if (!cancelled) setSamples([]);
      }
    };
    load();
    const timer = setInterval(load, 4000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [node.id]);

  const answered = samples.filter((m) => m.packet_loss_pct < 100);
  const latest = samples.length > 0 ? samples[samples.length - 1] : null;
  const latestReplied = latest !== null && latest.packet_loss_pct < 100;
  const availabilityPct = samples.length
    ? Math.round((answered.length / samples.length) * 1000) / 10
    : null;
  const lastSeen = answered.length > 0 ? answered[answered.length - 1].recorded_at : null;

  const renderSparkline = () => {
    const data = answered.map((m) => m.latency_ms);
    if (data.length < 2) {
      return <p className="text-xs text-gray-500 py-3">Waiting for measurements…</p>;
    }
    const max = Math.max(...data);
    const min = Math.min(...data);
    const width = 220;
    const height = 44;

    const points = data
      .map((val, idx) => {
        const x = (idx / (data.length - 1)) * width;
        const y = height - ((val - min) / (max - min || 1)) * (height - 8) - 4;
        return `${x},${y}`;
      })
      .join(' ');

    return (
      <svg className="w-full h-11 overflow-visible" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        <polyline
          fill="none"
          style={{ stroke: 'rgb(var(--c-blue-500))' }}
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          points={points}
        />
      </svg>
    );
  };

  return (
    <div
      className={`bg-gray-900/95 border border-gray-800 rounded-2xl p-5 shadow-2xl backdrop-blur-xl flex flex-col gap-4 text-gray-200 transition-all ${className}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-gray-800/80 border border-gray-700/60 text-indigo-400">
            <Server className="w-6 h-6" />
          </div>
          <div>
            <h3 className="font-bold text-base text-white tracking-wide">{node.name}</h3>
            <p className="text-xs font-mono text-gray-400">{node.ip_address}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <StatusBadge status={node.status} size="sm" />
          {onClose && (
            <button
              onClick={onClose}
              className="p-1 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Primary Stats Grid */}
      <div className="grid grid-cols-2 gap-2.5 pt-1">
        <div className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-3 flex flex-col">
          <div className="flex items-center gap-1.5 text-xs text-gray-400 font-medium">
            <Activity className="w-3.5 h-3.5 text-blue-400" />
            <span>Latency</span>
          </div>
          <div className="mt-1 flex items-baseline gap-1">
            <span className="text-xl font-bold text-white tracking-tight">
              {latestReplied ? latest!.latency_ms.toFixed(1) : '—'}
            </span>
            <span className="text-xs text-gray-400 font-mono">{latestReplied ? 'ms' : ''}</span>
          </div>
        </div>

        <div className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-3 flex flex-col">
          <div className="flex items-center gap-1.5 text-xs text-gray-400 font-medium">
            <Radio className="w-3.5 h-3.5 text-amber-400" />
            <span>Packet Loss</span>
          </div>
          <div className="mt-1 flex items-baseline gap-1">
            <span
              className={`text-xl font-bold tracking-tight ${
                (latest?.packet_loss_pct ?? 0) > 5 ? 'text-red-400' : 'text-white'
              }`}
            >
              {latest ? `${latest.packet_loss_pct}%` : '—'}
            </span>
          </div>
        </div>
      </div>

      {/* Sparkline Chart */}
      <div className="bg-gray-800/30 border border-gray-800 rounded-xl p-3">
        <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
          <span className="font-medium">Latency History</span>
          <span className="font-mono text-[11px] text-gray-500">Last {answered.length} replies</span>
        </div>
        <div className="py-1">{renderSparkline()}</div>
      </div>

      {/* Secondary Meta: Type, Last Seen, Uptime */}
      <div className="space-y-2 border-t border-gray-800/80 pt-3 text-xs text-gray-300">
        <div className="flex justify-between items-center">
          <span className="text-gray-400">Node Type</span>
          <span className="font-mono capitalize text-gray-200">
            {node.node_type?.replace('_', ' ') || 'Router'}
          </span>
        </div>

        <div className="flex justify-between items-center">
          <span className="flex items-center gap-1 text-gray-400">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span>Availability (last {samples.length} probes)</span>
          </span>
          <span className="font-mono font-medium text-emerald-400">
            {availabilityPct === null ? '—' : `${availabilityPct}%`}
          </span>
        </div>

        <div className="flex justify-between items-center">
          <span className="flex items-center gap-1 text-gray-400">
            <Clock className="w-3.5 h-3.5" />
            <span>Last Seen</span>
          </span>
          <span className="font-mono text-gray-400">
            {lastSeen ? new Date(lastSeen).toLocaleTimeString() : 'Not yet'}
          </span>
        </div>
      </div>

      {children}

      {/* Interactive Controls if handlers provided */}
      {(onSimulateFail || onRecover) && (
        <div className="pt-2 flex gap-2">
          {node.status === 'down' ? (
            <button
              onClick={() => onRecover?.(node.id)}
              className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-on-accent text-xs font-semibold shadow-lg shadow-emerald-900/30 transition-all"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Recover Node</span>
            </button>
          ) : (
            <button
              onClick={() => onSimulateFail?.(node.id)}
              className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-xl bg-red-600/80 hover:bg-red-600 text-on-accent text-xs font-semibold shadow-lg shadow-red-900/30 transition-all"
            >
              <ZapOff className="w-3.5 h-3.5" />
              <span>Simulate Failure</span>
            </button>
          )}
        </div>
      )}
    </div>
  );
};

export default NodeCard;
