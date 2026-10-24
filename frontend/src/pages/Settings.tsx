import React, { useState, useEffect } from 'react';
import { getConfig, updateConfig } from '../services/api';
import { SystemConfig } from '../types';
import {
  Settings as SettingsIcon,
  Save,
  RotateCcw,
  CheckCircle2,
  AlertCircle,
  Sliders,
  Shield,
  Activity,
  Radio,
} from 'lucide-react';

const DEFAULT_CONFIG: SystemConfig = {
  polling_interval_sec: 5,
  latency_warning_ms: 40,
  latency_critical_ms: 80,
  packet_loss_warning_pct: 5,
  packet_loss_critical_pct: 15,
  healing_enabled: true,
  auto_rollback: true,
};

export const Settings: React.FC = () => {
  const [config, setConfig] = useState<SystemConfig>(DEFAULT_CONFIG);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(
    null
  );

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        setIsLoading(true);
        const data = await getConfig();
        if (data) {
          setConfig(data);
        }
      } catch {
        // Fallback to defaults
      } finally {
        setIsLoading(false);
      }
    };
    fetchConfig();
  }, []);

  const handleChange = (field: keyof SystemConfig, value: any) => {
    setConfig((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setIsSaving(true);
      setFeedback(null);
      await updateConfig(config);
      setFeedback({
        type: 'success',
        message: 'System configuration saved successfully. Engine updated in real time.',
      });
      setTimeout(() => setFeedback(null), 4000);
    } catch (err: any) {
      setFeedback({
        type: 'error',
        message: err?.message || 'Failed to update system configuration.',
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleResetDefaults = () => {
    setConfig(DEFAULT_CONFIG);
    setFeedback({
      type: 'success',
      message: 'Reset configuration values to system defaults.',
    });
    setTimeout(() => setFeedback(null), 3000);
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-12">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-gray-800">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-indigo-600/20 text-indigo-400 border border-indigo-500/20">
            <SettingsIcon className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white tracking-tight">System & Telemetry Settings</h2>
            <p className="text-xs text-gray-400">
              Configure detection thresholds, telemetry polling rates, and automated remediation rules
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={handleResetDefaults}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-gray-900 border border-gray-800 text-xs font-semibold text-gray-400 hover:text-white hover:bg-gray-800 transition-all"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>Reset Defaults</span>
        </button>
      </div>

      {feedback && (
        <div
          className={`p-4 rounded-xl border text-xs flex items-center gap-2.5 animate-slide-in ${
            feedback.type === 'success'
              ? 'bg-emerald-950/70 border-emerald-500/50 text-emerald-300'
              : 'bg-red-950/70 border-red-500/50 text-red-300'
          }`}
        >
          {feedback.type === 'success' ? (
            <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
          ) : (
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
          )}
          <span>{feedback.message}</span>
        </div>
      )}

      {/* Main Form */}
      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Section 1: Telemetry Polling */}
        <div className="bg-gray-900/90 border border-gray-800 rounded-2xl p-5 shadow-xl backdrop-blur space-y-4">
          <div className="flex items-center gap-2 pb-3 border-b border-gray-800">
            <Sliders className="w-4 h-4 text-indigo-400" />
            <h3 className="font-bold text-sm text-white">Telemetry & Probe Frequency</h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-gray-300">
                Polling Interval (Seconds)
              </label>
              <input
                type="number"
                min="1"
                max="60"
                value={config.polling_interval_sec}
                onChange={(e) => handleChange('polling_interval_sec', Number(e.target.value))}
                className="bg-gray-800/80 border border-gray-700 text-xs text-white rounded-xl px-3 py-2.5 focus:outline-none focus:border-indigo-500 font-mono"
              />
              <span className="text-[11px] text-gray-500">
                Frequency for synthetic ping & latency probes across the mesh.
              </span>
            </div>
          </div>
        </div>

        {/* Section 2: Anomaly Thresholds */}
        <div className="bg-gray-900/90 border border-gray-800 rounded-2xl p-5 shadow-xl backdrop-blur space-y-4">
          <div className="flex items-center gap-2 pb-3 border-b border-gray-800">
            <Activity className="w-4 h-4 text-amber-400" />
            <h3 className="font-bold text-sm text-white">Detection Thresholds (SLA Bounds)</h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Latency Warning */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-gray-300">
                Latency Warning Threshold (ms)
              </label>
              <input
                type="number"
                min="5"
                max="500"
                value={config.latency_warning_ms}
                onChange={(e) => handleChange('latency_warning_ms', Number(e.target.value))}
                className="bg-gray-800/80 border border-gray-700 text-xs text-white rounded-xl px-3 py-2.5 focus:outline-none focus:border-indigo-500 font-mono"
              />
              <span className="text-[11px] text-gray-500">
                Flags link as degraded if RTT exceeds this limit.
              </span>
            </div>

            {/* Latency Critical */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-gray-300">
                Latency Critical Threshold (ms)
              </label>
              <input
                type="number"
                min="10"
                max="1000"
                value={config.latency_critical_ms}
                onChange={(e) => handleChange('latency_critical_ms', Number(e.target.value))}
                className="bg-gray-800/80 border border-gray-700 text-xs text-white rounded-xl px-3 py-2.5 focus:outline-none focus:border-indigo-500 font-mono"
              />
              <span className="text-[11px] text-gray-500">
                Triggers immediate rerouting and incident detection.
              </span>
            </div>

            {/* Packet Loss Warning */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-gray-300">
                Packet Loss Warning (%)
              </label>
              <input
                type="number"
                min="1"
                max="100"
                value={config.packet_loss_warning_pct}
                onChange={(e) => handleChange('packet_loss_warning_pct', Number(e.target.value))}
                className="bg-gray-800/80 border border-gray-700 text-xs text-white rounded-xl px-3 py-2.5 focus:outline-none focus:border-indigo-500 font-mono"
              />
              <span className="text-[11px] text-gray-500">
                Triggers warning alerts on jitter and minor loss.
              </span>
            </div>

            {/* Packet Loss Critical */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-gray-300">
                Packet Loss Critical (%)
              </label>
              <input
                type="number"
                min="1"
                max="100"
                value={config.packet_loss_critical_pct}
                onChange={(e) => handleChange('packet_loss_critical_pct', Number(e.target.value))}
                className="bg-gray-800/80 border border-gray-700 text-xs text-white rounded-xl px-3 py-2.5 focus:outline-none focus:border-indigo-500 font-mono"
              />
              <span className="text-[11px] text-gray-500">
                Threshold for automated link isolation and path failover.
              </span>
            </div>
          </div>
        </div>

        {/* Section 3: Self-Healing Automation Policy */}
        <div className="bg-gray-900/90 border border-gray-800 rounded-2xl p-5 shadow-xl backdrop-blur space-y-4">
          <div className="flex items-center gap-2 pb-3 border-b border-gray-800">
            <Shield className="w-4 h-4 text-emerald-400" />
            <h3 className="font-bold text-sm text-white">Autonomous Remediation Policy</h3>
          </div>

          <div className="space-y-3">
            <label className="flex items-center justify-between p-3 rounded-xl bg-gray-800/40 border border-gray-800 cursor-pointer hover:bg-gray-800/70 transition-colors">
              <div>
                <span className="text-xs font-semibold text-white">Enable Automated Rerouting</span>
                <p className="text-[11px] text-gray-400">
                  Allows the detective engine to dynamically update routing paths upon fault isolation.
                </p>
              </div>
              <input
                type="checkbox"
                checked={config.healing_enabled}
                onChange={(e) => handleChange('healing_enabled', e.target.checked)}
                className="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-500 bg-gray-700 border-gray-600"
              />
            </label>

            <label className="flex items-center justify-between p-3 rounded-xl bg-gray-800/40 border border-gray-800 cursor-pointer hover:bg-gray-800/70 transition-colors">
              <div>
                <span className="text-xs font-semibold text-white">Automatic Rollback on Recovery</span>
                <p className="text-[11px] text-gray-400">
                  Reverts traffic to primary shortest path once failed node or link passes health probes.
                </p>
              </div>
              <input
                type="checkbox"
                checked={config.auto_rollback}
                onChange={(e) => handleChange('auto_rollback', e.target.checked)}
                className="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-500 bg-gray-700 border-gray-600"
              />
            </label>
          </div>
        </div>

        {/* Submit Button */}
        <div className="flex justify-end pt-2">
          <button
            type="submit"
            disabled={isSaving}
            className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs shadow-lg shadow-indigo-600/30 transition-all disabled:opacity-50"
          >
            <Save className="w-4 h-4" />
            <span>{isSaving ? 'Saving Changes...' : 'Save Configuration'}</span>
          </button>
        </div>
      </form>
    </div>
  );
};

export default Settings;
