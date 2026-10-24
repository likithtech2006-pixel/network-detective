import React from 'react';
import { Node, Metric } from '../types';
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
  metrics?: Metric[];
  onClose?: () => void;
  onSimulateFail?: (nodeId: string) => void;
  onRecover?: (nodeId: string) => void;
  className?: string;
}

export const NodeCard: React.FC<NodeCardProps> = ({
  node,
  metrics = [],
  onClose,
  onSimulateFail,
  onRecover,
  className = '',
}) => {
  // Sparkline data points (latencies)
  const latencyPoints = metrics.slice(-12).map((m) => m.latency_ms);
  const currentMetric = metrics.length > 0 ? metrics[metrics.length - 1] : null;
  const currentLatency = currentMetric?.latency_ms ?? (node.status === 'down' ? 0 : 18);
  const currentLoss = currentMetric?.packet_loss_pct ?? (node.status === 'down' ? 100 : node.status === 'degraded' ? 12 : 0);
  const uptimePct = node.status === 'down' ? 84.2 : node.status === 'degraded' ? 97.8 : 99.98;

  // Render SVG Sparkline
  const renderSparkline = () => {
    const data = latencyPoints.length > 0 ? latencyPoints : [12, 14, 18, 15, 22, 16, 19, 21, 18];
    const max = Math.max(...data, 40);
    const min = Math.min(...data, 0);
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
      <svg className="w-full h-11 overflow-visible">
        <defs>
          <linearGradient id={`grad-${node.id}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
          </linearGradient>
        </defs>
        <polyline
          fill="none"
          stroke="#3b82f6"
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
            <span className="text-xl font-bold text-white tracking-tight">{currentLatency}</span>
            <span className="text-xs text-gray-400 font-mono">ms</span>
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
                currentLoss > 5 ? 'text-red-400' : 'text-white'
              }`}
            >
              {currentLoss}%
            </span>
          </div>
        </div>
      </div>

      {/* Sparkline Chart */}
      <div className="bg-gray-800/30 border border-gray-800 rounded-xl p-3">
        <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
          <span className="font-medium">Latency History</span>
          <span className="font-mono text-[11px] text-gray-500">Last 12 intervals</span>
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
            <span>Uptime (30d)</span>
          </span>
          <span className="font-mono font-medium text-emerald-400">{uptimePct}%</span>
        </div>

        <div className="flex justify-between items-center">
          <span className="flex items-center gap-1 text-gray-400">
            <Clock className="w-3.5 h-3.5" />
            <span>Last Seen</span>
          </span>
          <span className="font-mono text-gray-400">
            {node.last_seen ? new Date(node.last_seen).toLocaleTimeString() : 'Just now'}
          </span>
        </div>
      </div>

      {/* Interactive Controls if handlers provided */}
      {(onSimulateFail || onRecover) && (
        <div className="pt-2 flex gap-2">
          {node.status === 'down' ? (
            <button
              onClick={() => onRecover?.(node.id)}
              className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-lg shadow-emerald-900/30 transition-all"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Recover Node</span>
            </button>
          ) : (
            <button
              onClick={() => onSimulateFail?.(node.id)}
              className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-xl bg-red-600/80 hover:bg-red-600 text-white text-xs font-semibold shadow-lg shadow-red-900/30 transition-all"
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
