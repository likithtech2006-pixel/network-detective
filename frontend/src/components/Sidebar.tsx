import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Network,
  Activity,
  AlertTriangle,
  Zap,
  Settings,
  ShieldCheck,
  Menu,
  X,
  Radio,
} from 'lucide-react';

interface SidebarProps {
  isConnected?: boolean;
}

export const Sidebar: React.FC<SidebarProps> = ({ isConnected = false }) => {
  const [isOpen, setIsOpen] = useState(false);

  const navItems = [
    { name: 'Dashboard', path: '/', icon: LayoutDashboard },
    { name: 'Topology', path: '/topology', icon: Network },
    { name: 'Metrics', path: '/metrics', icon: Activity },
    { name: 'Incidents', path: '/incidents', icon: AlertTriangle },
    { name: 'Simulator', path: '/simulator', icon: Zap },
    { name: 'Settings', path: '/settings', icon: Settings },
  ];

  return (
    <>
      {/* Mobile Menu Toggle Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="lg:hidden fixed top-3 left-4 z-50 p-2 rounded-xl bg-gray-900 border border-gray-800 text-gray-200 shadow-xl"
        aria-label="Toggle Navigation"
      >
        {isOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
      </button>

      {/* Backdrop for mobile */}
      {isOpen && (
        <div
          onClick={() => setIsOpen(false)}
          className="lg:hidden fixed inset-0 z-40 bg-black/60 backdrop-blur-sm transition-opacity"
        />
      )}

      {/* Sidebar Container */}
      <aside
        className={`fixed lg:static top-0 left-0 bottom-0 z-40 w-64 flex flex-col bg-gray-950 border-r border-gray-800/80 p-4 transition-transform duration-300 ease-in-out ${
          isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
      >
        {/* Brand / Logo */}
        <div className="flex items-center gap-3 px-2 py-4 mb-3 border-b border-gray-800/80">
          <div className="p-2.5 rounded-xl bg-gradient-to-tr from-indigo-600 to-cyan-500 text-white shadow-lg shadow-indigo-500/20">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <div>
            <h1 className="font-extrabold text-sm tracking-wider uppercase text-white bg-gradient-to-r from-white via-gray-200 to-gray-400 bg-clip-text text-transparent">
              Network Detective
            </h1>
            <span className="text-[10px] text-emerald-400 font-mono tracking-widest uppercase">
              Self-Healing Ops
            </span>
          </div>
        </div>

        {/* Navigation Links */}
        <nav className="flex-1 space-y-1.5 py-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                onClick={() => setIsOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-xs font-semibold tracking-wide transition-all duration-200 ${
                    isActive
                      ? 'bg-indigo-600 text-on-accent shadow-lg shadow-indigo-600/30'
                      : 'text-gray-400 hover:text-gray-100 hover:bg-gray-900/80'
                  }`
                }
              >
                <Icon className="w-4 h-4 flex-shrink-0" />
                <span>{item.name}</span>
              </NavLink>
            );
          })}
        </nav>

        {/* Footer Connection Status */}
        <div className="pt-4 border-t border-gray-800/80 px-2 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-400 flex items-center gap-1.5 font-medium">
              <Radio className="w-3.5 h-3.5 text-gray-500" />
              Telemetry Sync
            </span>
            <span
              className={`flex items-center gap-1 text-[11px] font-mono ${
                isConnected ? 'text-emerald-400' : 'text-amber-400'
              }`}
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  isConnected ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'
                }`}
              />
              {isConnected ? 'ONLINE' : 'POLLING'}
            </span>
          </div>

          <div className="p-2.5 rounded-xl bg-gray-900/90 border border-gray-800/80 text-[11px] text-gray-400 font-mono">
            <div className="flex justify-between">
              <span>Agent:</span>
              <span className="text-gray-200 font-medium">Active (Reroute)</span>
            </div>
            <div className="flex justify-between mt-1">
              <span>Engine:</span>
              <span className="text-gray-200 font-medium">Dijkstra + RCA</span>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
};

export default Sidebar;
