import { useCallback, useEffect, useState } from 'react';
import { NetworkMode } from '../types';
import { getNetworkMode, setNetworkMode } from '../services/api';

// Shared across every component that shows or changes the mode
let currentMode: NetworkMode | null = null;
const listeners = new Set<(mode: NetworkMode) => void>();

function publish(mode: NetworkMode) {
  currentMode = mode;
  listeners.forEach((listener) => listener(mode));
}

/**
 * The network mode: "simulation" probes the built-in virtual network,
 * "live" pings every device at its real IP address.
 */
export function useNetworkMode() {
  const [mode, setMode] = useState<NetworkMode | null>(currentMode);
  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    listeners.add(setMode);
    if (currentMode === null) {
      getNetworkMode()
        .then(publish)
        .catch(() => undefined);
    }
    return () => {
      listeners.delete(setMode);
    };
  }, []);

  const changeMode = useCallback(async (next: NetworkMode) => {
    setSwitching(true);
    try {
      publish(await setNetworkMode(next));
    } finally {
      setSwitching(false);
    }
  }, []);

  return { mode, switching, changeMode };
}

export default useNetworkMode;
