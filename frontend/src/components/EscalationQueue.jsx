import React, { useState } from 'react';
import { ShieldAlert, AlertTriangle, Scale, Building2, CheckCircle2, UserCheck, MessageSquare, Clock, ArrowUpRight } from 'lucide-react';

export default function EscalationQueue() {
  const [escalations, setEscalations] = useState([
    {
      id: 'ESC-901',
      invoice_id: 'QBO_1003',
      invoice_number: 'INV-1003',
      customer_name: 'Apex Logistics Ltd',
      customer_contact: 'disputes@apexlog.com',
      balance_due: 19500.0,
      days_overdue: 61,
      reason: 'LEGAL_THREAT',
      channel: 'EMAIL',
      triggered_at: '2026-09-19 14:32 UTC',
      status: 'PENDING_REVIEW',
      snippet: 'Do not contact our office again. All further communications must go through our bankruptcy attorney.'
    },
    {
      id: 'ESC-902',
      invoice_id: 'XERO_8001',
      invoice_number: 'INV-8001',
      customer_name: 'Cyberdyne Systems Corp',
      customer_contact: 'finance@cyberdyne.io',
      balance_due: 6750.0,
      days_overdue: 22,
      reason: 'SERVICES_NOT_RENDERED',
      channel: 'EMAIL',
      triggered_at: '2026-09-19 11:15 UTC',
      status: 'UNDER_INVESTIGATION',
      snippet: 'We dispute line items 3 and 4. Project deliverables were never signed off by product team.'
    }
  ]);

  const [resolvedIds, setResolvedIds] = useState(new Set());

  const handleAction = (id, actionType) => {
    setResolvedIds(prev => new Set([...prev, id]));
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-white tracking-tight flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-rose-400" />
            Human Escalation & Compliance Triage
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Hard compliance safety net: accounts with legal threats, bankruptcy filings, or manual reviews frozen locally.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold px-3 py-1 rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/30">
            {escalations.length - resolvedIds.size} Pending Triage
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4">
        {escalations.map((esc) => {
          const isHandled = resolvedIds.has(esc.id);

          return (
            <div
              key={esc.id}
              className={`rounded-2xl border transition-all p-5 shadow-xl ${
                isHandled
                  ? 'bg-slate-900/40 border-slate-800/60 opacity-60'
                  : 'bg-[#101623] border-slate-800/90 hover:border-slate-700'
              }`}
            >
              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                <div className="flex items-start gap-3.5">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
                    esc.reason === 'LEGAL_THREAT'
                      ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                      : 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                  }`}>
                    {esc.reason === 'LEGAL_THREAT' ? <Scale className="w-5 h-5" /> : <AlertTriangle className="w-5 h-5" />}
                  </div>

                  <div>
                    <div className="flex items-center gap-2.5 flex-wrap">
                      <h3 className="font-bold text-white text-sm">{esc.customer_name}</h3>
                      <span className="font-mono text-xs text-slate-400">#{esc.invoice_number}</span>
                      <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-rose-500/15 text-rose-300 border border-rose-500/30">
                        {esc.reason}
                      </span>
                      <span className="text-[11px] text-slate-500 flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {esc.triggered_at}
                      </span>
                    </div>

                    <p className="text-xs text-slate-400 mt-1">
                      {esc.customer_contact} • Outstanding Balance: <span className="font-mono font-bold text-white">${esc.balance_due.toLocaleString()} USD</span> ({esc.days_overdue} days past due)
                    </p>

                    <div className="mt-3 p-3 bg-slate-950/80 rounded-xl border border-slate-800/80 text-xs text-slate-300 italic">
                      "{esc.snippet}"
                    </div>
                  </div>
                </div>

                {/* Manager Action Buttons */}
                <div className="flex items-center gap-2 self-end lg:self-center flex-shrink-0">
                  {isHandled ? (
                    <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-400 bg-emerald-500/10 px-3 py-1.5 rounded-xl border border-emerald-500/20">
                      <CheckCircle2 className="w-3.5 h-3.5" /> Action Logged
                    </span>
                  ) : (
                    <>
                      <button
                        onClick={() => handleAction(esc.id, 'LEGAL')}
                        className="px-3 py-1.5 rounded-xl bg-purple-600/20 hover:bg-purple-600 text-purple-300 hover:text-white border border-purple-500/30 text-xs font-semibold transition-all flex items-center gap-1"
                      >
                        <Scale className="w-3.5 h-3.5" />
                        <span>Refer to Counsel</span>
                      </button>

                      <button
                        onClick={() => handleAction(esc.id, 'RESOLVE')}
                        className="px-3.5 py-1.5 rounded-xl bg-emerald-600/20 hover:bg-emerald-600 text-emerald-300 hover:text-white border border-emerald-500/30 text-xs font-semibold transition-all flex items-center gap-1"
                      >
                        <UserCheck className="w-3.5 h-3.5" />
                        <span>Acknowledge & Freeze</span>
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
