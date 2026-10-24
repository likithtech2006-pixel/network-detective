import React, { useEffect, useState } from 'react';
import { DeviceSuggestion, DeviceType, Node, PingResult } from '../types';
import { getDeviceSuggestions, pingAddress, errorMessage } from '../services/api';
import { Router, Network, Server, X, Radar, Loader2, Cable } from 'lucide-react';

const TYPES: { type: DeviceType; label: string; icon: React.ReactNode }[] = [
  { type: 'router', label: 'Router', icon: <Router className="w-4 h-4" /> },
  { type: 'switch', label: 'Switch', icon: <Network className="w-4 h-4" /> },
  { type: 'server', label: 'Server', icon: <Server className="w-4 h-4" /> },
];

const inputClass =
  'w-full bg-gray-950 border border-gray-800 rounded-xl px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-indigo-500 transition-colors';

/**
 * Centered dialog shell with a backdrop
 */
export const Dialog: React.FC<{
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: React.ReactNode;
}> = ({ title, subtitle, onClose, children }) => {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 animate-fade-in">
      <div className="absolute inset-0 bg-gray-950/70 backdrop-blur-sm" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="relative w-full max-w-md bg-gray-900 border border-gray-800 rounded-2xl shadow-2xl p-5 animate-pop-in"
      >
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            <h3 className="text-base font-bold text-white">{title}</h3>
            {subtitle && <p className="text-xs text-gray-400 mt-0.5">{subtitle}</p>}
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="p-1 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
};

/**
 * "Ping" button with its result, used before adding or while editing a device
 */
export const PingTester: React.FC<{ address: string }> = ({ address }) => {
  const [result, setResult] = useState<PingResult | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => setResult(null), [address]);

  const run = async () => {
    setBusy(true);
    try {
      setResult(await pingAddress(address));
    } catch {
      setResult({ address, reachable: false, latency_ms: null });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={run}
        disabled={!address.trim() || busy}
        className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-gray-800 border border-gray-700 text-xs font-semibold text-gray-200 hover:bg-gray-700 disabled:opacity-50 transition-all"
      >
        {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Radar className="w-3.5 h-3.5" />}
        <span>Ping</span>
      </button>
      {result && (
        <span
          className={`text-xs font-mono ${result.reachable ? 'text-emerald-400' : 'text-red-400'}`}
          aria-live="polite"
        >
          {result.reachable ? `Replied in ${result.latency_ms?.toFixed(1)} ms` : 'No reply'}
        </span>
      )}
    </div>
  );
};

/**
 * Add a router, switch or server; suggests real devices reachable from this computer
 */
export const AddDeviceDialog: React.FC<{
  onClose: () => void;
  onAdd: (device: { name: string; node_type: DeviceType; ip_address: string }) => Promise<void>;
}> = ({ onClose, onAdd }) => {
  const [nodeType, setNodeType] = useState<DeviceType>('router');
  const [name, setName] = useState('');
  const [address, setAddress] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [suggestions, setSuggestions] = useState<DeviceSuggestion[]>([]);

  useEffect(() => {
    getDeviceSuggestions()
      .then(setSuggestions)
      .catch(() => setSuggestions([]));
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await onAdd({ name: name.trim(), node_type: nodeType, ip_address: address.trim() });
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog
      title="Add device"
      subtitle="In live mode it is pinged at this address; in simulation it joins the virtual network."
      onClose={onClose}
    >
      <form onSubmit={submit} className="space-y-4">
        <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label="Device type">
          {TYPES.map((t) => (
            <button
              key={t.type}
              type="button"
              role="radio"
              aria-checked={nodeType === t.type}
              onClick={() => setNodeType(t.type)}
              className={`flex flex-col items-center gap-1 py-2.5 rounded-xl border text-xs font-semibold transition-all ${
                nodeType === t.type
                  ? 'border-indigo-500 bg-indigo-600/15 text-indigo-300'
                  : 'border-gray-800 bg-gray-950 text-gray-400 hover:text-gray-200 hover:border-gray-700'
              }`}
            >
              {t.icon}
              <span>{t.label}</span>
            </button>
          ))}
        </div>

        <label className="block space-y-1.5">
          <span className="text-xs font-semibold text-gray-300">Name</span>
          <input
            className={inputClass}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Core Router"
            required
            autoFocus
          />
        </label>

        <label className="block space-y-1.5">
          <span className="text-xs font-semibold text-gray-300">IP address or hostname</span>
          <input
            className={`${inputClass} font-mono`}
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="e.g. 192.168.1.10"
            required
          />
        </label>
        <PingTester address={address} />

        {suggestions.length > 0 && (
          <div className="space-y-1.5">
            <span className="text-xs font-semibold text-gray-300">Real devices you can add</span>
            <div className="grid gap-1.5">
              {suggestions.map((s) => (
                <button
                  key={s.ip_address}
                  type="button"
                  onClick={() => {
                    setName(s.name);
                    setAddress(s.ip_address);
                    setNodeType(s.node_type);
                  }}
                  className="flex items-center justify-between gap-3 px-3 py-2 rounded-xl border border-gray-800 bg-gray-950 text-left hover:border-indigo-500/60 transition-colors"
                >
                  <span className="text-xs">
                    <span className="font-semibold text-gray-200">{s.name}</span>
                    <span className="block text-gray-500">{s.description}</span>
                  </span>
                  <span className="text-xs font-mono text-gray-400">{s.ip_address}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {error && (
          <p className="text-xs text-red-400" role="alert">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-gray-300 hover:bg-gray-800 transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-on-accent text-xs font-semibold shadow-md shadow-indigo-600/20 disabled:opacity-60 transition-all"
          >
            {saving ? 'Adding…' : 'Add device'}
          </button>
        </div>
      </form>
    </Dialog>
  );
};

const BANDWIDTHS = [
  { label: '10 Mbit/s', value: 10 },
  { label: '100 Mbit/s', value: 100 },
  { label: '1 Gbit/s', value: 1000 },
  { label: '10 Gbit/s', value: 10000 },
];

/**
 * Set a new wire's bandwidth and routing cost
 */
export const WireDialog: React.FC<{
  source: Node;
  target: Node;
  onClose: () => void;
  onConnect: (wire: { weight: number; bandwidth_mbps: number }) => Promise<void>;
}> = ({ source, target, onClose, onConnect }) => {
  const [bandwidth, setBandwidth] = useState(100);
  const [weight, setWeight] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await onConnect({ weight, bandwidth_mbps: bandwidth });
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog title="Connect devices" subtitle={`${source.name} ↔ ${target.name}`} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <div className="flex items-center justify-center gap-3 py-2 text-xs font-mono text-gray-300">
          <span className="px-2 py-1 rounded-lg bg-gray-800">{source.name}</span>
          <Cable className="w-4 h-4 text-violet-400" />
          <span className="px-2 py-1 rounded-lg bg-gray-800">{target.name}</span>
        </div>

        <label className="block space-y-1.5">
          <span className="text-xs font-semibold text-gray-300">Bandwidth</span>
          <select
            className={inputClass}
            value={bandwidth}
            onChange={(e) => setBandwidth(Number(e.target.value))}
          >
            {BANDWIDTHS.map((b) => (
              <option key={b.value} value={b.value}>
                {b.label}
              </option>
            ))}
          </select>
        </label>

        <label className="block space-y-1.5">
          <span className="text-xs font-semibold text-gray-300">Routing cost (weight)</span>
          <input
            type="number"
            min={0.1}
            step={0.1}
            className={inputClass}
            value={weight}
            onChange={(e) => setWeight(Number(e.target.value))}
            required
          />
          <span className="block text-[11px] text-gray-500">
            Dijkstra prefers lower totals. In simulation each unit also adds 2 ms of delay.
          </span>
        </label>

        {error && (
          <p className="text-xs text-red-400" role="alert">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-gray-300 hover:bg-gray-800 transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-2 rounded-xl bg-violet-600 hover:bg-violet-500 text-on-accent text-xs font-semibold shadow-md shadow-violet-600/20 disabled:opacity-60 transition-all"
          >
            {saving ? 'Connecting…' : 'Connect'}
          </button>
        </div>
      </form>
    </Dialog>
  );
};
