import React, { useState, useEffect, useMemo } from 'react';
import { getIncidents, errorMessage } from '../services/api';
import { Incident } from '../types';
import IncidentTimeline from '../components/IncidentTimeline';
import StatusBadge from '../components/StatusBadge';
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Search,
  Filter,
  ChevronDown,
  ChevronUp,
  ShieldAlert,
  Wrench,
  RefreshCw,
} from 'lucide-react';

export const Incidents: React.FC = () => {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<'all' | 'active' | 'resolved'>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [expandedIncidentId, setExpandedIncidentId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const fetchIncidentsData = async () => {
    try {
      setIsLoading(true);
      const data = await getIncidents();
      setIncidents(data ?? []);
      setLoadError(null);
    } catch (err) {
      setLoadError(errorMessage(err));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchIncidentsData();
  }, []);

  const filteredIncidents = useMemo(() => {
    return incidents.filter((inc) => {
      const isResolved =
        inc.status.toLowerCase() === 'verified' ||
        inc.status.toLowerCase() === 'resolved' ||
        !!inc.resolved_at;
      const matchesFilter =
        filterStatus === 'all'
          ? true
          : filterStatus === 'active'
          ? !isResolved
          : isResolved;

      const q = searchQuery.toLowerCase().trim();
      const matchesSearch =
        !q ||
        inc.id.toLowerCase().includes(q) ||
        inc.fault_type.toLowerCase().includes(q) ||
        inc.affected_component.toLowerCase().includes(q);

      return matchesFilter && matchesSearch;
    });
  }, [incidents, filterStatus, searchQuery]);

  const stats = useMemo(() => {
    const total = incidents.length;
    const healed = incidents.filter((i) => i.status.toLowerCase() === 'verified');
    const active = incidents.filter(
      (i) => i.status.toLowerCase() !== 'verified' && !i.resolved_at
    ).length;
    const resolved = healed.length;
    const healedPct = total ? Math.round((resolved / total) * 100) : 0;
    // Mean time from detection to verified recovery, over self-healed incidents only
    const durations = healed
      .filter((i) => i.resolved_at)
      .map((i) => (Date.parse(i.resolved_at as string) - Date.parse(i.detected_at)) / 1000);
    const avgTime = durations.length
      ? `${(durations.reduce((s, d) => s + d, 0) / durations.length).toFixed(1)}s`
      : '—';

    return { total, active, resolved, healedPct, avgTime };
  }, [incidents]);

  const toggleExpand = (id: string) => {
    setExpandedIncidentId((prev) => (prev === id ? null : id));
  };

  return (
    <div className="space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-white tracking-tight flex items-center gap-2">
            <span>Incident Management & Self-Healing Audit</span>
            <ShieldAlert className="w-5 h-5 text-indigo-400" />
          </h2>
          <p className="text-xs text-gray-400 mt-1">
            End-to-end incident lifecycle history: Detection ➔ RCA ➔ Dynamic Bypass ➔ Verification
          </p>
        </div>

        <button
          onClick={fetchIncidentsData}
          disabled={isLoading}
          className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-gray-900 border border-gray-800 text-xs font-semibold text-gray-300 hover:text-white hover:bg-gray-800 transition-all self-start sm:self-auto"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Stats Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-gray-900/80 border border-gray-800 rounded-2xl p-4 shadow-lg backdrop-blur">
          <div className="flex items-center justify-between text-gray-400 text-xs">
            <span>Total Incidents</span>
            <AlertTriangle className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="text-2xl font-black text-white mt-2">{stats.total}</div>
          <div className="text-[11px] text-gray-400 font-mono mt-1">All recorded events</div>
        </div>

        <div className="bg-gray-900/80 border border-gray-800 rounded-2xl p-4 shadow-lg backdrop-blur">
          <div className="flex items-center justify-between text-gray-400 text-xs">
            <span>Active Incidents</span>
            <AlertTriangle className="w-4 h-4 text-amber-400" />
          </div>
          <div
            className={`text-2xl font-black mt-2 ${
              stats.active > 0 ? 'text-red-400 animate-pulse' : 'text-white'
            }`}
          >
            {stats.active}
          </div>
          <div className="text-[11px] text-gray-400 font-mono mt-1">Requiring action or healing</div>
        </div>

        <div className="bg-gray-900/80 border border-gray-800 rounded-2xl p-4 shadow-lg backdrop-blur">
          <div className="flex items-center justify-between text-gray-400 text-xs">
            <span>Auto-Resolved</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-black text-emerald-400 mt-2">{stats.resolved}</div>
          <div className="text-[11px] text-emerald-400 font-mono mt-1">{stats.healedPct}% self-healed</div>
        </div>

        <div className="bg-gray-900/80 border border-gray-800 rounded-2xl p-4 shadow-lg backdrop-blur">
          <div className="flex items-center justify-between text-gray-400 text-xs">
            <span>Avg Healing Time</span>
            <Clock className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-black text-white mt-2">{stats.avgTime}</div>
          <div className="text-[11px] text-cyan-400 font-mono mt-1">Detection to verified recovery</div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-gray-900/60 border border-gray-800 p-3 rounded-2xl">
        <div className="flex bg-gray-950 p-1 rounded-xl border border-gray-800 w-full sm:w-auto">
          {(['all', 'active', 'resolved'] as const).map((filter) => (
            <button
              key={filter}
              onClick={() => setFilterStatus(filter)}
              className={`flex-1 sm:flex-initial px-4 py-1.5 rounded-lg text-xs font-semibold capitalize transition-all ${
                filterStatus === filter
                  ? 'bg-indigo-600 text-on-accent shadow-md'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              {filter}
            </button>
          ))}
        </div>

        <div className="relative w-full sm:w-72">
          <Search className="w-3.5 h-3.5 text-gray-500 absolute left-3 top-3" />
          <input
            type="text"
            placeholder="Search incident, fault, component..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-gray-950 border border-gray-800 text-xs text-gray-200 pl-9 pr-3 py-2 rounded-xl focus:outline-none focus:border-indigo-500 font-mono"
          />
        </div>
      </div>

      {/* Incidents Table / Accordion */}
      <div className="bg-gray-900/90 border border-gray-800 rounded-2xl shadow-xl overflow-hidden backdrop-blur">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono text-gray-300">
            <thead>
              <tr className="border-b border-gray-800 bg-gray-950/60 text-gray-400">
                <th className="py-3.5 px-4 font-semibold">INCIDENT ID</th>
                <th className="py-3.5 px-4 font-semibold">FAULT TYPE</th>
                <th className="py-3.5 px-4 font-semibold">AFFECTED TARGET</th>
                <th className="py-3.5 px-4 font-semibold">STATUS</th>
                <th className="py-3.5 px-4 font-semibold">DETECTED AT</th>
                <th className="py-3.5 px-4 font-semibold">ACTIONS</th>
                <th className="py-3.5 px-4 font-semibold text-right">DETAILS</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/40">
              {filteredIncidents.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-10 text-center text-gray-500 font-sans">
                    {loadError
                      ? `Could not load incidents: ${loadError}`
                      : incidents.length === 0
                      ? 'No incidents yet. Break a wire or device in the Simulator to see self-healing.'
                      : 'No incidents match the active search or filter.'}
                  </td>
                </tr>
              ) : (
                filteredIncidents.map((inc) => {
                  const isExpanded = expandedIncidentId === inc.id;
                  return (
                    <React.Fragment key={inc.id}>
                      <tr
                        onClick={() => toggleExpand(inc.id)}
                        className={`cursor-pointer transition-colors ${
                          isExpanded ? 'bg-gray-800/60' : 'hover:bg-gray-800/30'
                        }`}
                      >
                        <td className="py-3.5 px-4 font-bold text-indigo-400">
                          {inc.id.slice(0, 10)}
                        </td>
                        <td className="py-3.5 px-4 capitalize text-white">
                          {inc.fault_type.replace('_', ' ')}
                        </td>
                        <td className="py-3.5 px-4 text-gray-200 font-semibold">
                          {inc.affected_component}
                        </td>
                        <td className="py-3.5 px-4">
                          <StatusBadge status={inc.status} size="sm" />
                        </td>
                        <td className="py-3.5 px-4 text-gray-400">
                          {new Date(inc.detected_at).toLocaleString()}
                        </td>
                        <td className="py-3.5 px-4">
                          <span className="flex items-center gap-1 text-emerald-400 font-semibold">
                            <Wrench className="w-3.5 h-3.5" />
                            {inc.healing_actions?.length || 1} action(s)
                          </span>
                        </td>
                        <td className="py-3.5 px-4 text-right">
                          <button className="p-1 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition-colors">
                            {isExpanded ? (
                              <ChevronUp className="w-4 h-4" />
                            ) : (
                              <ChevronDown className="w-4 h-4" />
                            )}
                          </button>
                        </td>
                      </tr>

                      {/* Expanded Lifecycle Timeline */}
                      {isExpanded && (
                        <tr>
                          <td colSpan={7} className="p-4 bg-gray-950/80 border-b border-gray-800">
                            <div className="max-w-4xl mx-auto">
                              <IncidentTimeline incident={inc} />
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default Incidents;
