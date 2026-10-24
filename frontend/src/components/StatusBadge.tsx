import React from 'react';
import { NodeStatus, LinkStatus, IncidentStatus } from '../types';

export type StatusValue =
  | 'up'
  | 'down'
  | 'degraded'
  | 'detected'
  | 'diagnosing'
  | 'healing'
  | 'verified'
  | 'escalated'
  | 'success'
  | 'failed'
  | NodeStatus
  | LinkStatus
  | IncidentStatus
  | string;

interface StatusBadgeProps {
  status: StatusValue;
  size?: 'sm' | 'md' | 'lg';
  showDot?: boolean;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  size = 'md',
  showDot = true,
  className = '',
}) => {
  const norm = (status || '').toLowerCase();

  let colorClasses = 'bg-gray-800 text-gray-300 border-gray-700';
  let dotColor = 'bg-gray-400';
  let isPulsing = false;

  switch (norm) {
    case 'up':
    case 'verified':
    case 'success':
      colorClasses = 'bg-emerald-950/70 text-emerald-300 border-emerald-600/40';
      dotColor = 'bg-emerald-400';
      break;

    case 'down':
    case 'escalated':
    case 'failed':
      colorClasses = 'bg-red-950/70 text-red-300 border-red-600/40';
      dotColor = 'bg-red-500';
      isPulsing = true;
      break;

    case 'degraded':
    case 'healing':
    case 'diagnosing':
      colorClasses = 'bg-amber-950/70 text-amber-300 border-amber-600/40';
      dotColor = 'bg-amber-400';
      isPulsing = true;
      break;

    case 'detected':
      colorClasses = 'bg-blue-950/70 text-blue-300 border-blue-600/40';
      dotColor = 'bg-blue-400';
      isPulsing = true;
      break;

    default:
      colorClasses = 'bg-gray-800 text-gray-300 border-gray-700';
      dotColor = 'bg-gray-400';
  }

  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5 gap-1.5',
    md: 'text-xs px-2.5 py-1 gap-2 font-medium',
    lg: 'text-sm px-3.5 py-1.5 gap-2.5 font-semibold',
  }[size];

  const dotSizeClasses = {
    sm: 'w-1.5 h-1.5',
    md: 'w-2 h-2',
    lg: 'w-2.5 h-2.5',
  }[size];

  return (
    <span
      className={`inline-flex items-center rounded-full border shadow-sm backdrop-blur uppercase tracking-wider ${sizeClasses} ${colorClasses} ${className}`}
    >
      {showDot && (
        <span className="relative flex items-center justify-center">
          {isPulsing && (
            <span
              className={`absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping ${dotColor}`}
            />
          )}
          <span className={`relative inline-flex rounded-full ${dotSizeClasses} ${dotColor}`} />
        </span>
      )}
      <span>{norm}</span>
    </span>
  );
};

export default StatusBadge;
