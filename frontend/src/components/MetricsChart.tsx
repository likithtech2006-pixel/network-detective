import React from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
} from 'recharts';
import { Metric } from '../types';

export type MetricType = 'latency' | 'packet_loss' | 'jitter';

interface MetricsChartProps {
  nodeId?: string;
  data: Metric[];
  metricType: MetricType;
  title?: string;
  height?: number;
  warningThreshold?: number;
  criticalThreshold?: number;
}

export const MetricsChart: React.FC<MetricsChartProps> = ({
  nodeId,
  data = [],
  metricType = 'latency',
  title,
  height = 240,
  warningThreshold,
  criticalThreshold,
}) => {
  // Metric configurations
  const config = {
    latency: {
      key: 'latency_ms',
      name: 'Latency',
      unit: 'ms',
      color: '#3b82f6', // blue
      warn: warningThreshold ?? 40,
      crit: criticalThreshold ?? 80,
    },
    packet_loss: {
      key: 'packet_loss_pct',
      name: 'Packet Loss',
      unit: '%',
      color: '#ef4444', // red
      warn: warningThreshold ?? 5,
      crit: criticalThreshold ?? 15,
    },
    jitter: {
      key: 'jitter_ms',
      name: 'Jitter',
      unit: 'ms',
      color: '#8b5cf6', // purple
      warn: warningThreshold ?? 10,
      crit: criticalThreshold ?? 25,
    },
  }[metricType];

  // Format data for chart display
  const chartData = data.map((m, idx) => ({
    time: m.recorded_at
      ? new Date(m.recorded_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
      : `T-${data.length - idx}`,
    value: Number(m[config.key as keyof Metric] || 0),
    timestamp: m.recorded_at,
  }));

  // Custom Dark Tooltip
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      const val = payload[0].value;
      return (
        <div className="bg-gray-900 border border-gray-700/80 p-2.5 rounded-lg shadow-xl text-xs backdrop-blur font-mono">
          <p className="text-gray-400 mb-1">{label}</p>
          <p className="font-bold flex items-center gap-1.5" style={{ color: config.color }}>
            <span>{config.name}:</span>
            <span>
              {val} {config.unit}
            </span>
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="bg-gray-900/80 border border-gray-800 rounded-2xl p-4 shadow-xl backdrop-blur-xl flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h4 className="text-sm font-semibold text-gray-200">
            {title || `${config.name} over Time`}
          </h4>
          {nodeId && <span className="text-xs text-gray-500 font-mono">Node: {nodeId}</span>}
        </div>
        <div className="flex items-center gap-3 text-xs text-gray-400 font-mono">
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-0.5 bg-amber-400" /> Warn: {config.warn}
            {config.unit}
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-0.5 bg-red-400" /> Crit: {config.crit}
            {config.unit}
          </span>
        </div>
      </div>

      <div style={{ width: '100%', height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
            <XAxis
              dataKey="time"
              stroke="#6b7280"
              fontSize={10}
              tickLine={false}
              axisLine={{ stroke: '#374151' }}
            />
            <YAxis
              stroke="#6b7280"
              fontSize={10}
              tickLine={false}
              axisLine={{ stroke: '#374151' }}
              unit={config.unit}
            />
            <Tooltip content={<CustomTooltip />} />
            {/* Warning and Critical dashed reference lines */}
            <ReferenceLine
              y={config.warn}
              stroke="#f59e0b"
              strokeDasharray="4 4"
              strokeWidth={1.5}
            />
            <ReferenceLine
              y={config.crit}
              stroke="#ef4444"
              strokeDasharray="4 4"
              strokeWidth={1.5}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke={config.color}
              strokeWidth={2.5}
              dot={{ r: 2, fill: config.color }}
              activeDot={{ r: 5, stroke: '#fff', strokeWidth: 1.5 }}
              isAnimationActive={true}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default MetricsChart;
