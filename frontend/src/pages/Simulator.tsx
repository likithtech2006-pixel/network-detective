import React, { useState } from 'react';
import useTopology from '../hooks/useTopology';
import useNetworkMode from '../hooks/useNetworkMode';
import SimulatorControls from '../components/SimulatorControls';
import TopologyGraph from '../components/TopologyGraph';
import {
  errorMessage,
  getIncidents,
  simulateFailure,
  simulateRecover,
  resetSimulation,
} from '../services/api';
import { FaultType, Incident } from '../types';
import {
  Zap,
  Terminal,
  Compass,
  CheckCircle2,
  ArrowRight,
  ShieldAlert,
  Play,
  RotateCcw,
} from 'lucide-react';

const PRESETS: {
  label: string;
  title: string;
  type: 'node' | 'link';
  target: string;
  fault: FaultType;
  color: string;
}[] = [
  { label: 'Fiber Cut', title: 'Cut the B–C distribution link', type: 'link', target: 'link-b-c', fault: FaultType.LINK_DOWN, color: 'text-amber-400' },
  { label: 'Core-B Fail', title: 'Crash core router B (transit traffic must detour)', type: 'node', target: 'router-b', fault: FaultType.NODE_DOWN, color: 'text-sky-400' },
  { label: 'Switch-C Crash', title: 'Crash switch C (server E is cut off, so this escalates)', type: 'node', target: 'switch-c', fault: FaultType.NODE_DOWN, color: 'text-red-400' },
  { label: 'Core-A Fail', title: 'Crash core router A', type: 'node', target: 'router-a', fault: FaultType.NODE_DOWN, color: 'text-indigo-400' },
];

interface SimulationEvent {
  id: string;
  timestamp: string;
  level: 'info' | 'warn' | 'error' | 'success';
  message: string;
}

export const Simulator: React.FC = () => {
  const { topology, refetch } = useTopology();
  const { mode } = useNetworkMode();
  const [events, setEvents] = useState<SimulationEvent[]>([
    {
      id: 'e-init',
      timestamp: new Date().toLocaleTimeString(),
      level: 'info',
      message: 'Ready. Break a device or wire below; the log follows the real incident as the backend handles it.',
    },
  ]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [activeSimulationIncident, setActiveSimulationIncident] = useState<Incident | null>(null);

  const addEvent = (message: string, level: SimulationEvent['level'] = 'info') => {
    setEvents((prev) => [
      {
        id: `ev-${Date.now()}-${prev.length}`,
        timestamp: new Date().toLocaleTimeString(),
        level,
        message,
      },
      ...prev.slice(0, 49),
    ]);
  };

  /**
   * Follow the first incident raised after an injection through detection, healing
   * and verification, logging each stage once with the backend's own details.
   */
  const followIncident = async (known: Set<string>) => {
    const deadline = Date.now() + 20000;
    const logged = new Set<string>();
    while (Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 300));
      const incident = (await getIncidents()).find((inc) => !known.has(inc.id));
      if (!incident) continue;
      setActiveSimulationIncident(incident);

      if (!logged.has('detected')) {
        logged.add('detected');
        addEvent(
          `[DETECTED] ${incident.fault_type} on ${incident.affected_component}. ${incident.resolution_notes ?? ''}`.trim(),
          'warn'
        );
      }
      if (incident.alternate_path?.length && !logged.has('healing')) {
        logged.add('healing');
        addEvent(
          `[REROUTED] ${incident.source_node} ➔ ${incident.target_node} now uses ${incident.alternate_path.join(' ➔ ')}.`,
          'success'
        );
      }
      if (incident.status === 'verified') {
        addEvent(`[VERIFIED] ${incident.resolution_notes ?? 'Alternate path verified.'}`, 'success');
        return;
      }
      if (incident.status === 'escalated') {
        addEvent(`[ESCALATED] ${incident.resolution_notes ?? 'No alternate path available.'}`, 'error');
        return;
      }
    }
    addEvent('[TIMEOUT] No incident finished within 20 s. Check that the backend is running.', 'warn');
  };

  const handleInjectFailure = async (
    targetType: 'node' | 'link',
    targetId: string,
    faultType: FaultType | string
  ) => {
    setIsLoading(true);
    setActiveSimulationIncident(null);
    try {
      const known = new Set((await getIncidents()).map((inc) => inc.id));
      const result = await simulateFailure({ target_type: targetType, target_id: targetId, fault_type: faultType });
      addEvent(`[INJECTED] ${result.message}`, 'error');
      await refetch();
      await followIncident(known);
      await refetch();
    } catch (err) {
      addEvent(`[REFUSED] ${errorMessage(err)}`, 'error');
    } finally {
      setIsLoading(false);
    }
  };

  const handleRecover = async (targetType: 'node' | 'link', targetId: string) => {
    setIsLoading(true);
    try {
      const result = await simulateRecover({ target_type: targetType, target_id: targetId });
      addEvent(`[REPAIRED] ${result.message}`, 'info');
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await refetch();
      setActiveSimulationIncident(null);
      addEvent('[RECOVERED] Monitor saw it answer again; routes returned to the primary paths.', 'success');
    } catch (err) {
      addEvent(`[REFUSED] ${errorMessage(err)}`, 'error');
    } finally {
      setIsLoading(false);
    }
  };

  const handleResetAll = async () => {
    setIsLoading(true);
    try {
      await resetSimulation();
      setActiveSimulationIncident(null);
      await refetch();
      addEvent('[RESET] Every fault repaired, all devices healthy, open incidents closed.', 'success');
    } catch (err) {
      addEvent(`[REFUSED] ${errorMessage(err)}`, 'error');
    } finally {
      setIsLoading(false);
    }
  };

  // Quick Preset Scenarios
  const runPresetScenario = (title: string, targetType: 'node' | 'link', targetId: string, fault: FaultType) => {
    addEvent(`[SCENARIO] ${title}`, 'info');
    handleInjectFailure(targetType, targetId, fault);
  };

  return (
    <div className="space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-white tracking-tight flex items-center gap-2">
            <span>Chaos & Self-Healing Simulator</span>
            <Zap className="w-5 h-5 text-amber-400" />
          </h2>
          <p className="text-xs text-gray-400 mt-1">
            Induce controlled network failures to stress-test detective diagnostics and autonomous rerouting
          </p>
        </div>

        {/* Preset Scenarios (shown only while their target exists in the topology) */}
        <div className="flex flex-wrap items-center gap-2">
          {PRESETS.filter((preset) =>
            preset.type === 'node'
              ? topology.nodes.some((n) => n.id === preset.target)
              : topology.links.some((l) => l.id === preset.target)
          ).map((preset) => {
            const blocked = preset.type === 'node' && mode === 'live';
            return (
              <button
                key={preset.label}
                disabled={blocked || isLoading}
                title={blocked ? 'In live mode, switch the real device off instead' : preset.title}
                onClick={() => runPresetScenario(preset.title, preset.type, preset.target, preset.fault)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-gray-900 border border-gray-800 text-xs font-semibold text-gray-300 hover:text-white hover:bg-gray-800 disabled:opacity-40 disabled:hover:bg-gray-900 transition-all"
              >
                <Play className={`w-3 h-3 ${preset.color}`} />
                <span>{preset.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Simulator Controls & Walkthrough Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Controls */}
        <div className="lg:col-span-2">
          <SimulatorControls
            nodes={topology.nodes}
            links={topology.links}
            onInjectFailure={handleInjectFailure}
            onRecover={handleRecover}
            onResetAll={handleResetAll}
            isLoading={isLoading}
          />
        </div>

        {/* Right 1 Col: Walkthrough Panel */}
        <div className="bg-gray-900/90 border border-gray-800 rounded-2xl p-5 shadow-xl backdrop-blur flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2 pb-3 border-b border-gray-800">
              <Compass className="w-4 h-4 text-indigo-400" />
              <h3 className="font-bold text-sm text-white">How Self-Healing Operates</h3>
            </div>

            <ol className="mt-4 space-y-3 text-xs text-gray-300">
              <li className="flex items-start gap-2.5">
                <span className="flex items-center justify-center w-5 h-5 rounded-full bg-indigo-900/80 text-indigo-300 text-[11px] font-mono font-bold flex-shrink-0">
                  1
                </span>
                <span>
                  <strong className="text-white">Failure Injection:</strong> Simulates link drop, fiber cut, or router crash.
                </span>
              </li>
              <li className="flex items-start gap-2.5">
                <span className="flex items-center justify-center w-5 h-5 rounded-full bg-indigo-900/80 text-indigo-300 text-[11px] font-mono font-bold flex-shrink-0">
                  2
                </span>
                <span>
                  <strong className="text-white">Detection:</strong> The monitor probes every device and wire ({mode === 'live' ? 'real pings, every 1 s' : 'every 0.5 s'}); 3 failed probes in a row confirm a fault.
                </span>
              </li>
              <li className="flex items-start gap-2.5">
                <span className="flex items-center justify-center w-5 h-5 rounded-full bg-indigo-900/80 text-indigo-300 text-[11px] font-mono font-bold flex-shrink-0">
                  3
                </span>
                <span>
                  <strong className="text-white">Root cause:</strong> The diagnoser walks the topology graph so a crashed device is reported once, not once per wire.
                </span>
              </li>
              <li className="flex items-start gap-2.5">
                <span className="flex items-center justify-center w-5 h-5 rounded-full bg-indigo-900/80 text-indigo-300 text-[11px] font-mono font-bold flex-shrink-0">
                  4
                </span>
                <span>
                  <strong className="text-white">Reroute:</strong> A pre-computed backup path is used if it avoids every failure; otherwise Dijkstra finds one.
                </span>
              </li>
              <li className="flex items-start gap-2.5">
                <span className="flex items-center justify-center w-5 h-5 rounded-full bg-indigo-900/80 text-indigo-300 text-[11px] font-mono font-bold flex-shrink-0">
                  5
                </span>
                <span>
                  <strong className="text-white">Verification:</strong> After 2 s for routes to settle, every hop of the detour is probed (≤ 300 ms, ≤ 15% loss) or the change is rolled back.
                </span>
              </li>
            </ol>
          </div>

          <div className="mt-5 p-3 rounded-xl bg-emerald-950/40 border border-emerald-500/30 text-emerald-300 text-xs flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
            <span>Autonomous Closed-Loop Control is ACTIVE</span>
          </div>
        </div>
      </div>

      {/* Mid: Live Topology Reaction */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-gray-200 uppercase tracking-wider flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-cyan-400" />
            <span>Network Reaction & Healing</span>
          </h3>
          <span className="text-xs text-gray-400 font-mono">
            Detour highlighted in blue while the fault lasts
          </span>
        </div>

        <TopologyGraph
          topology={topology}
          activeIncident={activeSimulationIncident}
          height="420px"
        />
      </div>

      {/* Bottom: Real-Time Event Log */}
      <div className="bg-gray-900/90 border border-gray-800 rounded-2xl p-5 shadow-xl backdrop-blur">
        <div className="flex items-center justify-between pb-3 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <Terminal className="w-4 h-4 text-emerald-400" />
            <h3 className="font-bold text-sm text-white">Real-Time Simulation Event Log</h3>
          </div>
          <span className="text-xs text-gray-500 font-mono">{events.length} events logged</span>
        </div>

        <div className="mt-3 max-h-56 overflow-y-auto space-y-1.5 font-mono text-xs pr-2">
          {events.map((ev) => (
            <div
              key={ev.id}
              className={`p-2 rounded-lg border flex items-start gap-3 ${
                ev.level === 'error'
                  ? 'bg-red-950/30 border-red-900/40 text-red-300'
                  : ev.level === 'warn'
                  ? 'bg-amber-950/30 border-amber-900/40 text-amber-300'
                  : ev.level === 'success'
                  ? 'bg-emerald-950/30 border-emerald-900/40 text-emerald-300'
                  : 'bg-gray-950/40 border-gray-800 text-gray-300'
              }`}
            >
              <span className="text-gray-500 flex-shrink-0">[{ev.timestamp}]</span>
              <span className="flex-1">{ev.message}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default Simulator;
