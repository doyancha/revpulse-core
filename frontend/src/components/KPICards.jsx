import React from 'react';
import { DollarSign, Clock, CalendarCheck, ShieldAlert, TrendingUp, ShieldCheck } from 'lucide-react';

export default function KPICards({ metrics }) {
  const formatCurrency = (val) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 0
    }).format(val || 0);
  };

  const cards = [
    {
      title: 'Total Outstanding AR',
      value: formatCurrency(metrics?.total_ar),
      subtitle: `${metrics?.total_invoices || 5} tracked accounting entries`,
      icon: DollarSign,
      color: 'from-blue-600/20 to-indigo-600/20 text-indigo-400 border-indigo-500/30',
      badge: 'Portfolio Gross',
      badgeColor: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20'
    },
    {
      title: 'Actionable Overdue',
      value: formatCurrency(metrics?.overdue_balance),
      subtitle: 'Accounts aging past 7+ days',
      icon: Clock,
      color: 'from-amber-600/20 to-rose-600/20 text-amber-400 border-amber-500/30',
      badge: 'Delinquent',
      badgeColor: 'bg-amber-500/10 text-amber-400 border-amber-500/20'
    },
    {
      title: 'Active Payment Plans',
      value: metrics?.active_plans ?? 1,
      subtitle: 'Structured multi-part installments',
      icon: CalendarCheck,
      color: 'from-emerald-600/20 to-teal-600/20 text-emerald-400 border-emerald-500/30',
      badge: 'Autonomous',
      badgeColor: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
    },
    {
      title: 'Frozen Disputes',
      value: metrics?.frozen_disputes ?? 2,
      subtitle: 'Dunning paused per compliance',
      icon: ShieldAlert,
      color: 'from-rose-600/20 to-purple-600/20 text-rose-400 border-rose-500/30',
      badge: 'Protected Hold',
      badgeColor: 'bg-rose-500/10 text-rose-400 border-rose-500/20'
    }
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card, idx) => {
        const Icon = card.icon;
        return (
          <div
            key={idx}
            className="relative overflow-hidden rounded-2xl bg-gradient-to-b from-[#111726] to-[#0D121F] p-5 border border-slate-800/80 hover:border-slate-700/80 transition-all duration-200 shadow-xl group"
          >
            {/* Ambient subtle glow */}
            <div className={`absolute -right-8 -top-8 w-24 h-24 rounded-full bg-gradient-to-br ${card.color} blur-2xl opacity-40 group-hover:opacity-60 transition-opacity`} />

            <div className="flex items-center justify-between mb-3">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center bg-slate-900 border ${card.color}`}>
                <Icon className="w-5 h-5" />
              </div>
              <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${card.badgeColor}`}>
                {card.badge}
              </span>
            </div>

            <div>
              <p className="text-xs font-medium text-slate-400 tracking-wide uppercase">
                {card.title}
              </p>
              <h3 className="text-2xl font-extrabold text-white mt-1 tracking-tight font-['JetBrains_Mono',monospace]">
                {card.value}
              </h3>
              <p className="text-[11px] text-slate-400 mt-1 flex items-center gap-1 font-medium">
                {card.subtitle}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
