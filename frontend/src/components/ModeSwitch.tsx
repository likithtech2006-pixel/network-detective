import React, { useState } from 'react';
import { FlaskConical, Radio } from 'lucide-react';
import useNetworkMode from '../hooks/useNetworkMode';
import { Dialog } from './DeviceDialogs';
import { errorMessage } from '../services/api';
import { NetworkMode } from '../types';

const DESCRIPTIONS: Record<NetworkMode, string> = {
  simulation:
    'Devices run in the built-in virtual network. You can crash devices and cut wires to test self-healing.',
  live:
    'Every device is pinged at its real IP address once a second. A device that stops answering 3 times in a row is reported and routed around. Wires stay logical: you can still cut them in the simulator.',
};

/**
 * Segmented Simulation / Live control with a sliding indicator
 */
export const ModeSwitch: React.FC = () => {
  const { mode, switching, changeMode } = useNetworkMode();
  const [pending, setPending] = useState<NetworkMode | null>(null);
  const [error, setError] = useState<string | null>(null);

  const confirm = async () => {
    if (!pending) return;
    setError(null);
    try {
      await changeMode(pending);
      setPending(null);
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const isLive = mode === 'live';

  return (
    <>
      <div
        role="radiogroup"
        aria-label="Network mode"
        className="relative hidden md:grid grid-cols-2 items-center p-1 rounded-xl bg-gray-900 border border-gray-800 text-xs font-semibold"
      >
        <span
          aria-hidden="true"
          className={`absolute top-1 bottom-1 left-1 w-[calc(50%-4px)] rounded-lg transition-all duration-300 ease-out ${
            isLive ? 'translate-x-full bg-emerald-600' : 'translate-x-0 bg-indigo-600'
          } ${mode === null ? 'opacity-0' : 'opacity-100'}`}
        />
        {(['simulation', 'live'] as NetworkMode[]).map((option) => (
          <button
            key={option}
            role="radio"
            aria-checked={mode === option}
            disabled={switching}
            onClick={() => option !== mode && setPending(option)}
            className={`relative z-10 flex items-center justify-center gap-1.5 px-3 py-1 rounded-lg transition-colors duration-300 ${
              mode === option ? 'text-on-accent' : 'text-gray-400 hover:text-white'
            }`}
          >
            {option === 'live' ? (
              <Radio className={`w-3.5 h-3.5 ${mode === 'live' ? 'animate-pulse' : ''}`} />
            ) : (
              <FlaskConical className="w-3.5 h-3.5" />
            )}
            <span>{option === 'live' ? 'Live' : 'Simulation'}</span>
          </button>
        ))}
      </div>

      {pending && (
        <Dialog
          title={pending === 'live' ? 'Switch to live mode?' : 'Switch to simulation?'}
          onClose={() => setPending(null)}
        >
          <p className="text-sm text-gray-300">{DESCRIPTIONS[pending]}</p>
          <p className="mt-3 text-xs text-gray-400">
            Switching marks every device healthy again and closes open incidents. Their history is kept.
          </p>
          {pending === 'live' && (
            <p className="mt-3 text-xs text-amber-300">
              Give each device a real address on the Topology page first (Add device suggests your router and
              this computer). Addresses that do not answer will show as faults.
            </p>
          )}
          {error && (
            <p className="mt-3 text-xs text-red-400" role="alert">
              {error}
            </p>
          )}
          <div className="flex justify-end gap-2 mt-5">
            <button
              onClick={() => setPending(null)}
              className="px-4 py-2 rounded-xl text-xs font-semibold text-gray-300 hover:bg-gray-800 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={confirm}
              disabled={switching}
              className={`px-4 py-2 rounded-xl text-on-accent text-xs font-semibold disabled:opacity-60 transition-all ${
                pending === 'live' ? 'bg-emerald-600 hover:bg-emerald-500' : 'bg-indigo-600 hover:bg-indigo-500'
              }`}
            >
              {switching ? 'Switching…' : pending === 'live' ? 'Go live' : 'Use simulation'}
            </button>
          </div>
        </Dialog>
      )}
    </>
  );
};

export default ModeSwitch;
