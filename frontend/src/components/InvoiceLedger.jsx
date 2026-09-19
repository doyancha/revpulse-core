import React, { useState } from 'react';
import { Search, Filter, MessageSquare, AlertCircle, ShieldCheck, CheckCircle2, FileText, ArrowRight, RefreshCw } from 'lucide-react';

export default function InvoiceLedger({ invoices, onSelectInvoice, onRefresh, isRefreshing }) {
  const [searchTerm, setSearchTerm] = useState('');
  const [filterBucket, setFilterBucket] = useState('ALL');

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
    }).format(amount || 0);
  };

  const filteredInvoices = invoices.filter(inv => {
    const matchesSearch =
      inv.customer_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      inv.invoice_number?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      inv.invoice_id?.toLowerCase().includes(searchTerm.toLowerCase());

    if (filterBucket === 'ALL') return matchesSearch;
    if (filterBucket === 'OVERDUE') return matchesSearch && inv.days_overdue >= 7;
    if (filterBucket === 'DISPUTE') return matchesSearch && (inv.status === 'UNDER_DISPUTE' || inv.dispute_hold);
    if (filterBucket === 'PLAN') return matchesSearch && inv.status === 'RESOLVED_PLAN';
    if (filterBucket === 'ESCALATED') return matchesSearch && inv.status === 'ESCALATED';
    return matchesSearch;
  });

  const getAgingBadge = (bucket, days) => {
    if (days < 7) {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          Current ({days}d)
        </span>
      );
    }
    if (days < 30) {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
          15-30 Days ({days}d)
        </span>
      );
    }
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-rose-500/10 text-rose-400 border border-rose-500/20">
        30+ Days ({days}d)
      </span>
    );
  };

  const getStatusBadge = (status, disputeHold) => {
    if (disputeHold || status === 'UNDER_DISPUTE') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-500/15 text-rose-300 border border-rose-500/30">
          <AlertCircle className="w-3 h-3" /> Dispute Hold
        </span>
      );
    }
    if (status === 'RESOLVED_PLAN') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">
          <CheckCircle2 className="w-3 h-3" /> Active Plan
        </span>
      );
    }
    if (status === 'ESCALATED') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-purple-500/15 text-purple-300 border border-purple-500/30">
          <AlertCircle className="w-3 h-3" /> Escalated
        </span>
      );
    }
    if (status === 'RESOLVED_PAID') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
          <ShieldCheck className="w-3 h-3" /> Paid & Reconciled
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-800 text-slate-300 border border-slate-700">
        Recovery Active
      </span>
    );
  };

  return (
    <div className="bg-[#101623] border border-slate-800/80 rounded-2xl overflow-hidden shadow-2xl">
      {/* Table Toolbar */}
      <div className="p-5 border-b border-slate-800/80 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-white tracking-tight flex items-center gap-2">
            <FileText className="w-5 h-5 text-indigo-400" />
            Accounts Receivable Ledger
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Normalized delinquency pipeline synced across QuickBooks and Xero.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Search bar */}
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search company or invoice #..."
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              className="pl-9 pr-4 py-1.5 bg-slate-900/80 border border-slate-700/80 rounded-xl text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 w-56 sm:w-64"
            />
          </div>

          {/* Filter Pills */}
          <div className="flex items-center gap-1 bg-slate-900/80 p-1 rounded-xl border border-slate-800">
            {['ALL', 'OVERDUE', 'PLAN', 'DISPUTE', 'ESCALATED'].map(b => (
              <button
                key={b}
                onClick={() => setFilterBucket(b)}
                className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold transition-colors ${
                  filterBucket === b
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`}
              >
                {b}
              </button>
            ))}
          </div>

          {/* Refresh Button */}
          {onRefresh && (
            <button
              onClick={onRefresh}
              disabled={isRefreshing}
              title="Refresh ledger records"
              className="p-2 bg-slate-900/80 hover:bg-slate-800 text-slate-300 hover:text-white rounded-xl border border-slate-700/80 transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin text-indigo-400' : ''}`} />
            </button>
          )}
        </div>
      </div>

      {/* Ledger Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-slate-800/80 bg-slate-900/40 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
              <th className="py-3.5 px-5">Invoice / Platform</th>
              <th className="py-3.5 px-5">Debtor Company</th>
              <th className="py-3.5 px-5">Balance Due</th>
              <th className="py-3.5 px-5">Aging Bucket</th>
              <th className="py-3.5 px-5">Recovery Status</th>
              <th className="py-3.5 px-5 text-right">Autonomous Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 text-xs text-slate-300">
            {filteredInvoices.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-12 text-center text-slate-500 font-medium">
                  No invoice records match the selected filter criteria.
                </td>
              </tr>
            ) : (
              filteredInvoices.map(inv => (
                <tr
                  key={inv.invoice_id}
                  className="hover:bg-slate-800/30 transition-colors group"
                >
                  <td className="py-4 px-5">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-bold text-white text-xs">
                        {inv.invoice_number || inv.invoice_id}
                      </span>
                      <span className={`text-[10px] uppercase font-bold px-1.5 py-0.5 rounded border ${
                        inv.platform === 'QUICKBOOKS'
                          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                          : 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20'
                      }`}>
                        {inv.platform}
                      </span>
                    </div>
                    <span className="text-[11px] text-slate-500 font-mono">ID: {inv.invoice_id}</span>
                  </td>

                  <td className="py-4 px-5">
                    <p className="font-semibold text-slate-100">{inv.customer_name}</p>
                    <p className="text-[11px] text-slate-400">{inv.customer_email || inv.customer_phone || 'No email'}</p>
                  </td>

                  <td className="py-4 px-5">
                    <p className="font-bold text-white font-mono text-sm">
                      {formatCurrency(inv.balance_due)}
                    </p>
                    <p className="text-[11px] text-slate-500">Gross: {formatCurrency(inv.total_amount)}</p>
                  </td>

                  <td className="py-4 px-5">
                    {getAgingBadge(inv.aging_bucket, inv.days_overdue)}
                  </td>

                  <td className="py-4 px-5">
                    {getStatusBadge(inv.status, inv.dispute_hold)}
                  </td>

                  <td className="py-4 px-5 text-right">
                    <button
                      onClick={() => onSelectInvoice(inv)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-indigo-600/20 hover:bg-indigo-600 text-indigo-300 hover:text-white border border-indigo-500/30 transition-all text-xs font-semibold group-hover:shadow-md group-hover:shadow-indigo-600/20"
                    >
                      <MessageSquare className="w-3.5 h-3.5" />
                      <span>Simulate</span>
                      <ArrowRight className="w-3 h-3 opacity-70 group-hover:translate-x-0.5 transition-transform" />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
