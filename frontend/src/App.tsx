import React from 'react';
import { Routes, Route, Navigate, Link } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import TopologyView from './pages/TopologyView';
import Metrics from './pages/Metrics';
import Incidents from './pages/Incidents';
import Simulator from './pages/Simulator';
import Settings from './pages/Settings';
import useWebSocket from './hooks/useWebSocket';
import ModeSwitch from './components/ModeSwitch';
import ThemeToggle from './components/ThemeToggle';
import { Zap } from 'lucide-react';

export const App: React.FC = () => {
  const { isConnected, alerts } = useWebSocket();

  const hasCriticalAlerts = alerts.some((a) => a.severity === 'critical');
  const hasWarningAlerts = alerts.some((a) => a.severity === 'warning');

  return (
    <div className="flex h-screen bg-gray-950 text-gray-100 font-sans overflow-hidden">
      {/* Left Sidebar Navigation */}
      <Sidebar isConnected={isConnected} />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Header */}
        <header className="h-16 flex items-center justify-between px-6 bg-gray-950/80 border-b border-gray-800/80 backdrop-blur z-20">
          <div className="flex items-center gap-3 pl-12 lg:pl-0">
            <h1 className="text-base font-extrabold text-white tracking-wide flex items-center gap-2">
              <span className="hidden sm:inline">Network Detective</span>
              <span className="text-gray-500 font-normal hidden sm:inline">/</span>
              <span className="text-indigo-400 font-semibold text-xs tracking-wider uppercase">
                Self-Healing Mesh
              </span>
            </h1>
          </div>

          {/* System Health Status Indicator */}
          <div className="flex items-center gap-3">
            <ModeSwitch />
            <div
              className={`flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-semibold backdrop-blur shadow-sm ${
                hasCriticalAlerts
                  ? 'bg-red-950/60 border-red-500/40 text-red-300'
                  : hasWarningAlerts
                  ? 'bg-amber-950/60 border-amber-500/40 text-amber-300'
                  : 'bg-emerald-950/60 border-emerald-500/40 text-emerald-300'
              }`}
            >
              <span className="relative flex h-2 w-2">
                <span
                  className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                    hasCriticalAlerts
                      ? 'bg-red-400'
                      : hasWarningAlerts
                      ? 'bg-amber-400'
                      : 'bg-emerald-400'
                  }`}
                />
                <span
                  className={`relative inline-flex rounded-full h-2 w-2 ${
                    hasCriticalAlerts
                      ? 'bg-red-500'
                      : hasWarningAlerts
                      ? 'bg-amber-500'
                      : 'bg-emerald-400'
                  }`}
                />
              </span>
              <span className="tracking-wide uppercase text-[11px] font-mono">
                {hasCriticalAlerts
                  ? 'Anomaly Detected (Healing)'
                  : hasWarningAlerts
                  ? 'Degraded Mesh'
                  : 'Systems Operational'}
              </span>
            </div>

            <Link
              to="/simulator"
              className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-on-accent text-xs font-semibold shadow-md shadow-indigo-600/20 transition-all"
            >
              <Zap className="w-3.5 h-3.5" />
              <span>Chaos Test</span>
            </Link>
            <ThemeToggle />
          </div>
        </header>

        {/* Scrollable View Container */}
        <main className="flex-1 overflow-y-auto px-6 py-6 bg-gray-950">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/topology" element={<TopologyView />} />
            <Route path="/metrics" element={<Metrics />} />
            <Route path="/incidents" element={<Incidents />} />
            <Route path="/simulator" element={<Simulator />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
};

export default App;
