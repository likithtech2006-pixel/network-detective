import React, { useState } from 'react';
import { Incident, HealingAction } from '../types';
import StatusBadge from './StatusBadge';
import {
  AlertTriangle,
  Search,
  Wrench,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronRight,
  ArrowRight,
  Clock,
  ShieldCheck,
} from 'lucide-react';

interface IncidentTimelineProps {
  incident: Incident;
  className?: string;
}

export const IncidentTimeline: React.FC<IncidentTimelineProps> = ({
  incident,
  className = '',
}) => {
  const [expandedActions, setExpandedActions] = useState<Record<string, boolean>>({});

  const toggleAction = (actionId: string) => {
    setExpandedActions((prev) => ({
      ...prev,
      [actionId]: !prev[actionId],
    }));
  };

  // Every line below comes from the incident record; nothing is scripted
  const action = incident.healing_actions?.[0];
  const isEscalated = incident.status.toLowerCase() === 'escalated';
  const fault = incident.fault_type.replace(/_/g, ' ');
  const flow =
    incident.source_node && incident.target_node && incident.source_node !== incident.target_node
      ? `${incident.source_node} → ${incident.target_node}`
      : null;

  const steps = [
    {
      key: 'detected',
      title: 'Incident Detected',
      status: 'detected',
      icon: <AlertTriangle className="w-4 h-4 text-amber-400" />,
      time: incident.detected_at,
      desc: `Health monitor confirmed ${fault} on ${incident.affected_component} after consecutive failed probes.`,
      active: true,
      color: 'border-amber-500 bg-amber-950/20 text-amber-300',
    },
    {
      key: 'diagnosing',
      title: 'Root Cause Diagnosis',
      status: 'diagnosing',
      icon: <Search className="w-4 h-4 text-blue-400" />,
      time: incident.detected_at,
      desc: `Diagnoser isolated ${incident.affected_component} as the root cause${
        flow ? `; primary affected flow ${flow}` : ''
      }.`,
      active: incident.status !== 'detected',
      color: 'border-blue-500 bg-blue-950/20 text-blue-300',
    },
    {
      key: 'healing',
      title: action?.action_type === 'escalate' ? 'No Reroute Possible' : 'Self-Healing Execution',
      status: 'healing',
      icon: <Wrench className="w-4 h-4 text-purple-400" />,
      time: action?.executed_at || '',
      desc:
        action?.action_type === 'reroute' && incident.alternate_path?.length
          ? `Moved ${flow ?? 'traffic'} from [${(incident.original_path ?? []).join(' → ')}] to [${incident.alternate_path.join(' → ')}].`
          : action
          ? 'No path avoided the failed components, so nothing was rerouted.'
          : 'Waiting for the healer.',
      active: ['healing', 'verified', 'escalated'].includes(incident.status.toLowerCase()),
      color: 'border-purple-500 bg-purple-950/20 text-purple-300',
    },
    {
      key: 'verified',
      title: isEscalated ? 'Escalated to an Engineer' : 'Verified & Healed',
      status: incident.status,
      icon: isEscalated ? (
        <XCircle className="w-4 h-4 text-red-400" />
      ) : (
        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
      ),
      time: incident.resolved_at || '',
      desc: incident.resolution_notes || 'Verification in progress.',
      active: ['verified', 'escalated'].includes(incident.status.toLowerCase()),
      color: isEscalated
        ? 'border-red-500 bg-red-950/20 text-red-300'
        : 'border-emerald-500 bg-emerald-950/20 text-emerald-300',
    },
  ];

  return (
    <div
      className={`bg-gray-900/90 border border-gray-800 rounded-2xl p-5 shadow-2xl backdrop-blur-xl text-gray-200 ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-gray-800">
        <div>
          <div className="flex items-center gap-2.5">
            <h3 className="text-base font-bold text-white tracking-wide">Incident Lifecycle</h3>
            <span className="font-mono text-xs text-gray-400">ID: {incident.id.slice(0, 8)}</span>
          </div>
          <p className="text-xs text-gray-400 mt-0.5">
            Fault: <span className="text-gray-200 font-semibold">{incident.fault_type}</span> on{' '}
            <span className="text-gray-200 font-semibold">{incident.affected_component}</span>
          </p>
        </div>
        <StatusBadge status={incident.status} size="md" />
      </div>

      {/* Vertical Steps Timeline */}
      <div className="relative pl-6 pt-5 pb-2 space-y-6 before:absolute before:left-[11px] before:top-6 before:bottom-6 before:w-0.5 before:bg-gray-800">
        {steps.map((step) => (
          <div key={step.key} className="relative flex items-start gap-4">
            {/* Step Icon Node */}
            <div
              className={`absolute -left-6 flex items-center justify-center w-6 h-6 rounded-full border-2 bg-gray-950 ${
                step.active ? step.color : 'border-gray-700 bg-gray-900 text-gray-600'
              }`}
            >
              {step.icon}
            </div>

            {/* Step Content Card */}
            <div
              className={`flex-1 rounded-xl border p-3.5 transition-all ${
                step.active
                  ? 'border-gray-800 bg-gray-800/40'
                  : 'border-gray-800/40 bg-gray-900/40 opacity-40'
              }`}
            >
              <div className="flex items-center justify-between text-xs mb-1">
                <span className="font-semibold text-white tracking-wide">{step.title}</span>
                <span className="font-mono text-gray-400 flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {step.time && step.time !== 'Pending verification'
                    ? new Date(step.time).toLocaleTimeString()
                    : step.time}
                </span>
              </div>
              <p className="text-xs text-gray-300 leading-relaxed font-sans mt-1">{step.desc}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Healing Actions Details (Expandable) */}
      {incident.healing_actions && incident.healing_actions.length > 0 && (
        <div className="mt-5 pt-4 border-t border-gray-800">
          <h4 className="text-xs font-semibold text-gray-300 uppercase tracking-wider mb-2 flex items-center gap-1.5">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>Healing Actions Executed ({incident.healing_actions.length})</span>
          </h4>

          <div className="space-y-2">
            {incident.healing_actions.map((act) => {
              const isExpanded = !!expandedActions[act.id];
              return (
                <div
                  key={act.id}
                  className="rounded-xl border border-gray-800 bg-gray-800/30 overflow-hidden"
                >
                  <button
                    onClick={() => toggleAction(act.id)}
                    className="w-full flex items-center justify-between p-3 text-left hover:bg-gray-800/50 transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      {isExpanded ? (
                        <ChevronDown className="w-4 h-4 text-gray-400" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-gray-400" />
                      )}
                      <span className="font-mono text-xs uppercase font-semibold text-indigo-300">
                        {act.action_type}
                      </span>
                      <span className="text-xs text-gray-400 font-mono">
                        ({new Date(act.executed_at).toLocaleTimeString()})
                      </span>
                    </div>
                    <StatusBadge status={act.result} size="sm" />
                  </button>

                  {isExpanded && (
                    <div className="p-3 pt-0 border-t border-gray-800/60 bg-gray-900/60 text-xs space-y-2">
                      {act.old_route && (
                        <div className="flex items-center gap-2 text-gray-400">
                          <span className="w-20 font-mono text-[11px] text-gray-500">
                            Old Route:
                          </span>
                          <span className="font-mono text-red-400">
                            {act.old_route.join(' → ')}
                          </span>
                        </div>
                      )}
                      {act.new_route && (
                        <div className="flex items-center gap-2 text-gray-400">
                          <span className="w-20 font-mono text-[11px] text-gray-500">
                            New Route:
                          </span>
                          <span className="font-mono text-emerald-400 font-semibold">
                            {act.new_route.join(' → ')}
                          </span>
                        </div>
                      )}
                      {act.details && (
                        <p className="text-gray-300 font-mono text-[11px] pt-1 border-t border-gray-800/60">
                          {act.details}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

export default IncidentTimeline;
