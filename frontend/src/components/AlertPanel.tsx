import React from 'react';
import { Alert } from '../types';
import StatusBadge from './StatusBadge';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Activity,
  Trash2,
  BellOff,
  Bell,
} from 'lucide-react';

interface AlertPanelProps {
  alerts: Alert[];
  onClearAll?: () => void;
  onSelectAlert?: (alert: Alert) => void;
  className?: string;
  maxHeight?: string;
}

export const AlertPanel: React.FC<AlertPanelProps> = ({
  alerts = [],
  onClearAll,
  onSelectAlert,
  className = '',
  maxHeight = '500px',
}) => {
  const getSeverityIcon = (severity: Alert['severity']) => {
    switch (severity) {
      case 'critical':
        return <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />;
      case 'warning':
        return <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />;
      case 'resolved':
        return <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />;
      default:
        return <Activity className="w-4 h-4 text-blue-400 flex-shrink-0" />;
    }
  };

  const getSeverityBorder = (severity: Alert['severity']) => {
    switch (severity) {
      case 'critical':
        return 'border-l-4 border-l-red-500 bg-red-950/20 hover:bg-red-950/30';
      case 'warning':
        return 'border-l-4 border-l-amber-500 bg-amber-950/20 hover:bg-amber-950/30';
      case 'resolved':
        return 'border-l-4 border-l-emerald-500 bg-emerald-950/20 hover:bg-emerald-950/30';
      default:
        return 'border-l-4 border-l-blue-500 bg-blue-950/20 hover:bg-blue-950/30';
    }
  };

  return (
    <div
      className={`flex flex-col bg-gray-900/90 border border-gray-800 rounded-2xl p-4 shadow-xl backdrop-blur-xl ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-gray-800 text-indigo-400">
            <Bell className="w-4 h-4" />
          </div>
          <h3 className="font-semibold text-sm text-gray-100">Live Alert Feed</h3>
          <span className="text-xs px-2 py-0.5 rounded-full bg-gray-800 text-gray-300 font-mono">
            {alerts.length}
          </span>
        </div>

        {alerts.length > 0 && onClearAll && (
          <button
            onClick={onClearAll}
            className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-red-400 transition-colors px-2 py-1 rounded-lg hover:bg-gray-800"
            title="Clear all alerts"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Clear</span>
          </button>
        )}
      </div>

      {/* Alert Feed Body */}
      <div
        className="overflow-y-auto space-y-2.5 mt-3 pr-1 divide-y divide-gray-800/40"
        style={{ maxHeight }}
      >
        {alerts.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-gray-500 gap-2">
            <BellOff className="w-8 h-8 opacity-40" />
            <p className="text-xs">All network systems normal. No active alerts.</p>
          </div>
        ) : (
          alerts.map((alert) => (
            <div
              key={alert.id}
              onClick={() => onSelectAlert?.(alert)}
              className={`p-3 rounded-xl border border-gray-800/80 transition-all duration-300 cursor-pointer animate-slide-in ${getSeverityBorder(
                alert.severity
              )}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  {getSeverityIcon(alert.severity)}
                  <span className="font-semibold text-xs text-white capitalize">
                    {alert.fault_type.replace('_', ' ')}
                  </span>
                </div>
                <StatusBadge status={alert.status} size="sm" />
              </div>

              <p className="text-xs text-gray-300 mt-1.5 leading-relaxed font-sans">
                {alert.message}
              </p>

              <div className="flex items-center justify-between text-[11px] text-gray-400 mt-2 font-mono">
                <span className="bg-gray-800/80 px-1.5 py-0.5 rounded text-gray-300">
                  Target: {alert.affected_component}
                </span>
                <span>
                  {new Date(alert.timestamp).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                  })}
                </span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default AlertPanel;
