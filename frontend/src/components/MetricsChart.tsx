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
import useTheme, { themeColor } from '../hooks/useTheme';

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
  // Recharts writes SVG attributes, so theme colors are resolved here and redrawn on change
  const { theme } = useTheme();
  const colors = React.useMemo(
    () => ({
      blue: themeColor('blue-500'),
      red: themeColor('red-500'),
      violet: themeColor('violet-500'),
      amber: themeColor('amber-500'),
      grid: themeColor('gray-800'),
      axis: themeColor('gray-700'),
      tick: themeColor('gray-500'),
      card: themeColor('gray-900'),
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [theme]
  );

  // Metric configurations
  const config = {
    latency: {
      key: 'latency_ms',
      name: 'Latency',
      unit: 'ms',
      color: colors.blue,
      warn: warningThreshold ?? 40,
      crit: criticalThreshold ?? 80,
    },
    packet_loss: {
      key: 'packet_loss_pct',
      name: 'Packet Loss',
      unit: '%',
      color: colors.red,
      warn: warningThreshold ?? 5,
      crit: criticalThreshold ?? 15,
    },
    jitter: {
      key: 'jitter_ms',
      name: 'Jitter',
      unit: 'ms',
      color: colors.violet,
      warn: warningThreshold ?? 10,
      crit: criticalThreshold ?? 25,
    },
  }[metricType];

  // Format data for chart display
  const chartData = data.map((m, idx) => ({
    time: m.recorded_at
      ? new Date(m.recorded_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
      : `T-${data.length - idx}`,
    // An unanswered probe has no latency or jitter: leave a gap instead of a spike
    value:
      metricType !== 'packet_loss' && m.packet_loss_pct >= 100
        ? null
        : Number(m[config.key as keyof Metric] || 0),
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
            <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} vertical={false} />
            <XAxis
              dataKey="time"
              stroke={colors.tick}
              fontSize={10}
              tickLine={false}
              axisLine={{ stroke: colors.axis }}
            />
            <YAxis
              stroke={colors.tick}
              fontSize={10}
              tickLine={false}
              axisLine={{ stroke: colors.axis }}
              unit={config.unit}
            />
            <Tooltip content={<CustomTooltip />} />
            {/* Warning and Critical dashed reference lines */}
            <ReferenceLine
              y={config.warn}
              stroke={colors.amber}
              strokeDasharray="4 4"
              strokeWidth={1.5}
            />
            <ReferenceLine
              y={config.crit}
              stroke={colors.red}
              strokeDasharray="4 4"
              strokeWidth={1.5}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke={config.color}
              strokeWidth={2.5}
              dot={{ r: 2, fill: config.color }}
              activeDot={{ r: 5, stroke: colors.card, strokeWidth: 1.5 }}
              isAnimationActive={true}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default MetricsChart;
