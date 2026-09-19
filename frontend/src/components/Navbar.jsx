import React, { useState, useEffect } from 'react';
import { ShieldCheck, Cpu, RefreshCw, Activity, Zap, Sparkles } from 'lucide-react';
import { checkApiHealth } from '../api';

export default function Navbar({ activeTab, setActiveTab }) {
  const [isOnline, setIsOnline] = useState(false);
  const [lastCheck, setLastCheck] = useState(new Date());

  const verifyHealth = async () => {
    const ok = await checkApiHealth();
    setIsOnline(ok);
    setLastCheck(new Date());
  };

  useEffect(() => {
    verifyHealth();
    const timer = setInterval(verifyHealth, 15000);
    return () => clearInterval(timer);
  }, []);

  const navItems = [
    { id: 'ledger', label: 'Invoices Ledger' },
    { id: 'console', label: 'Recovery Console' },
    { id: 'escalations', label: 'Escalations Queue' },
    { id: 'audit', label: 'Audit Trail' }
  ];

  return (
    <header className="border-b border-slate-800/80 bg-[#0B101D]/90 backdrop-blur-md sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Brand Logo & Tag */}
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-cyan-400 flex items-center justify-center shadow-lg shadow-indigo-500/20 ring-1 ring-white/20">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-lg font-bold tracking-tight bg-gradient-to-r from-white via-slate-100 to-slate-400 bg-clip-text text-transparent">
                  RevPulse
                </span>
                <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/30">
                  Enterprise
                </span>
              </div>
              <p className="text-[11px] text-slate-400 font-medium hidden sm:block">
                Autonomous Accounts Receivable Engine
              </p>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="hidden md:flex items-center gap-1 bg-slate-900/60 p-1 rounded-xl border border-slate-800">
            {navItems.map(item => (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 ${
                  activeTab === item.id
                    ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`}
              >
                {item.label}
              </button>
            ))}
          </nav>

          {/* System Telemetry & Model Badge */}
          <div className="flex items-center gap-2.5">
            {/* Engine badge */}
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-900/90 border border-slate-700/60 text-xs text-slate-300">
              <Sparkles className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />
              <span className="font-mono text-[11px] font-medium text-slate-300">Gemini 3.6 Flash</span>
            </div>

            {/* API Status Badge */}
            <button
              onClick={verifyHealth}
              title="Click to re-ping API health"
              className={`flex items-center gap-2 px-2.5 py-1 rounded-full border text-xs font-medium transition-all ${
                isOnline
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/20'
                  : 'bg-amber-500/10 text-amber-400 border-amber-500/30 hover:bg-amber-500/20'
              }`}
            >
              <span className={`w-2 h-2 rounded-full ${isOnline ? 'bg-emerald-400 animate-ping' : 'bg-amber-400'}`} />
              <span className="text-[11px]">{isOnline ? 'Core Active' : 'Simulation Mode'}</span>
            </button>
          </div>
        </div>

        {/* Mobile Nav Tabs */}
        <div className="flex md:hidden items-center justify-around py-2 border-t border-slate-800">
          {navItems.map(item => (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`px-2 py-1 rounded text-xs font-semibold ${
                activeTab === item.id ? 'text-indigo-400 font-bold' : 'text-slate-400'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}
