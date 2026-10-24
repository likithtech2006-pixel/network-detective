import React, { useState, useEffect, useMemo } from 'react';
import useTopology from '../hooks/useTopology';
import { getNodeMetricsWindow } from '../services/api';
import { Metric } from '../types';
import MetricsChart from '../components/MetricsChart';
import {
  Activity,
  Radio,
  Clock,
  TrendingUp,
  Server,
  Zap,
  RefreshCw,
} from 'lucide-react';

export const Metrics: React.FC = () => {
  const { topology } = useTopology();

  const [selectedNodeId, setSelectedNodeId] = useState<string>('');
  const [timeRange, setTimeRange] = useState<'5m' | '15m' | '1h' | '24h'>('15m');
  const [metricsHistory, setMetricsHistory] = useState<Metric[]>([]);
  const [loading, setLoading] = useState<boolean>(false);

  // Set default node if not set
  useEffect(() => {
    if (!selectedNodeId && topology.nodes.length > 0) {
      setSelectedNodeId(topology.nodes[0].id);
    }
  }, [selectedNodeId, topology]);

  const activeNode = topology.nodes.find((n) => n.id === selectedNodeId) || topology.nodes[0];

  // Stored samples for the selected window, oldest first; refreshed every 5 s
  useEffect(() => {
    if (!selectedNodeId) return;

    let isSubscribed = true;
    const minutes = { '5m': 5, '15m': 15, '1h': 60, '24h': 1440 }[timeRange];
    const fetchNodeData = async () => {
      try {
        setLoading(true);
        const data = await getNodeMetricsWindow(selectedNodeId, minutes);
        if (isSubscribed) {
          setMetricsHistory(
            [...data].sort((a, b) => Date.parse(a.recorded_at) - Date.parse(b.recorded_at))
          );
        }
      } catch {
        if (isSubscribed) setMetricsHistory([]);
      } finally {
        if (isSubscribed) setLoading(false);
      }
    };

    fetchNodeData();
    const timer = setInterval(fetchNodeData, 5000);
    return () => {
      isSubscribed = false;
      clearInterval(timer);
    };
  }, [selectedNodeId, timeRange]);

  // Compute summary stats
  const summary = useMemo(() => {
    // Latency and jitter only exist for probes that got a reply
    const replied = metricsHistory.filter((m) => m.packet_loss_pct < 100);
    if (metricsHistory.length === 0) {
      return { curLatency: '—', peakLatency: '—', avgLoss: '—', avgJitter: '—' };
    }
    const latencies = replied.map((m) => m.latency_ms);
    const losses = metricsHistory.map((m) => m.packet_loss_pct);
    const jitters = replied.map((m) => m.jitter_ms);
    const last = metricsHistory[metricsHistory.length - 1];

    const curLatency = last.packet_loss_pct < 100 ? last.latency_ms.toFixed(1) : '—';
    const peakLatency = latencies.length ? Math.max(...latencies).toFixed(1) : '—';
    const avgLoss = (losses.reduce((a, b) => a + b, 0) / losses.length).toFixed(1);
    const avgJitter = jitters.length
      ? (jitters.reduce((a, b) => a + b, 0) / jitters.length).toFixed(2)
      : '—';

    return { curLatency, peakLatency, avgLoss, avgJitter };
  }, [metricsHistory]);

  return (
    <div className="space-y-6 pb-12">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-white tracking-tight flex items-center gap-2">
            <span>Telemetry & Health Metrics</span>
            <Activity className="w-5 h-5 text-indigo-400" />
          </h2>
          <p className="text-xs text-gray-400 mt-1">
            Real-time probe telemetry: latency jitter, transport queue times, and drop ratios
          </p>
        </div>

        {/* Controls: Node Selector & Time Range */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Node Selector */}
          <div className="flex items-center gap-2 bg-gray-900 border border-gray-800 rounded-xl px-3 py-1.5">
            <Server className="w-4 h-4 text-indigo-400" />
            <select
              value={selectedNodeId}
              onChange={(e) => setSelectedNodeId(e.target.value)}
              className="bg-transparent text-xs font-mono text-gray-200 focus:outline-none cursor-pointer"
            >
              {topology.nodes.map((node) => (
                <option key={node.id} value={node.id} className="bg-gray-900 text-gray-200">
                  {node.name} ({node.ip_address})
                </option>
              ))}
            </select>
          </div>

          {/* Time Range Chips */}
          <div className="flex bg-gray-900 border border-gray-800 rounded-xl p-1 text-xs font-semibold">
            {(['5m', '15m', '1h', '24h'] as const).map((range) => (
              <button
                key={range}
                onClick={() => setTimeRange(range)}
                className={`px-3 py-1 rounded-lg transition-all ${
                  timeRange === range
                    ? 'bg-indigo-600 text-on-accent shadow-md'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                {range}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Summary KPI Cards Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-gray-900/80 border border-gray-800 rounded-2xl p-4 shadow-lg backdrop-blur">
          <div className="flex items-center justify-between text-gray-400 text-xs">
            <span>Current Latency</span>
            <Activity className="w-4 h-4 text-blue-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-1">
            <span className="text-2xl font-black text-white">{summary.curLatency}</span>
            <span className="text-xs font-mono text-gray-400">ms</span>
          </div>
          <div className="text-[11px] text-gray-400 font-mono mt-1">Latest reply</div>
        </div>

        <div className="bg-gray-900/80 border border-gray-800 rounded-2xl p-4 shadow-lg backdrop-blur">
          <div className="flex items-center justify-between text-gray-400 text-xs">
            <span>Peak Window Latency</span>
            <TrendingUp className="w-4 h-4 text-purple-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-1">
            <span className="text-2xl font-black text-white">{summary.peakLatency}</span>
            <span className="text-xs font-mono text-gray-400">ms</span>
          </div>
          <div className="text-[11px] text-gray-400 font-mono mt-1">Within selected {timeRange}</div>
        </div>

        <div className="bg-gray-900/80 border border-gray-800 rounded-2xl p-4 shadow-lg backdrop-blur">
          <div className="flex items-center justify-between text-gray-400 text-xs">
            <span>Packet Loss Rate</span>
            <Radio className="w-4 h-4 text-amber-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-1">
            <span
              className={`text-2xl font-black ${
                Number(summary.avgLoss) > 5 ? 'text-red-400' : 'text-white'
              }`}
            >
              {summary.avgLoss}%
            </span>
          </div>
          <div className="text-[11px] text-gray-400 font-mono mt-1">{metricsHistory.length} probes in {timeRange}</div>
        </div>

        <div className="bg-gray-900/80 border border-gray-800 rounded-2xl p-4 shadow-lg backdrop-blur">
          <div className="flex items-center justify-between text-gray-400 text-xs">
            <span>Average Jitter</span>
            <Clock className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-1">
            <span className="text-2xl font-black text-white">{summary.avgJitter}</span>
            <span className="text-xs font-mono text-gray-400">ms</span>
          </div>
          <div className="text-[11px] text-gray-400 font-mono mt-1">Change between replies</div>
        </div>
      </div>

      {/* Charts Grid */}
      <div className="space-y-6">
        {/* Latency Chart */}
        <MetricsChart
          nodeId={activeNode?.name || selectedNodeId}
          data={metricsHistory}
          metricType="latency"
          title="Round Trip Time (RTT Latency)"
          height={260}
          warningThreshold={100}
          criticalThreshold={200}
        />

        {/* Packet Loss Chart */}
        <MetricsChart
          nodeId={activeNode?.name || selectedNodeId}
          data={metricsHistory}
          metricType="packet_loss"
          title="Packet Drop Percentage"
          height={260}
          warningThreshold={5}
          criticalThreshold={10}
        />

        {/* Jitter Chart */}
        <MetricsChart
          nodeId={activeNode?.name || selectedNodeId}
          data={metricsHistory}
          metricType="jitter"
          title="Transport Delay Variation (Jitter)"
          height={260}
          warningThreshold={10}
          criticalThreshold={25}
        />
      </div>
    </div>
  );
};

export default Metrics;
