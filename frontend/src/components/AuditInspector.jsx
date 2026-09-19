import React, { useState, useEffect } from 'react';
import { ShieldCheck, Download, Clock, Radio, CheckCircle, AlertTriangle, CreditCard, Mail, MessageSquare, RefreshCw } from 'lucide-react';
import { fetchAuditTrail } from '../api';

export default function AuditInspector({ selectedInvoice, invoices, onRefresh, isRefreshing }) {
  const [selectedInvId, setSelectedInvId] = useState(selectedInvoice?.invoice_id || invoices[0]?.invoice_id || 'QBO_1001');
  const [auditLogs, setAuditLogs] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (selectedInvoice?.invoice_id) {
      setSelectedInvId(selectedInvoice.invoice_id);
    }
  }, [selectedInvoice]);

  const loadAudit = async (showLoading = true) => {
    if (showLoading) setLoading(true);
    try {
      const data = await fetchAuditTrail(selectedInvId);
      setAuditLogs(data);
    } catch (err) {
      console.error("Failed to fetch audit trail:", err);
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  useEffect(() => {
    loadAudit(true);
    const interval = setInterval(() => {
      loadAudit(false);
    }, 3000);
    return () => clearInterval(interval);
  }, [selectedInvId]);

  const exportJSON = () => {
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(auditLogs, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", `revpulse_audit_${selectedInvId}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  const getEventIcon = (eventType) => {
    switch (eventType) {
      case 'INVOICE_INGESTED':
      case 'DUNNING_TRIGGERED':
        return <Radio className="w-4 h-4 text-cyan-400" />;
      case 'PAYMENT_GENERATED':
      case 'PAYMENT_RECONCILED':
        return <CreditCard className="w-4 h-4 text-emerald-400" />;
      case 'LEGAL_THREAT':
      case 'HUMAN_ESCALATED':
      case 'DISPUTE_SUBMITTED':
        return <AlertTriangle className="w-4 h-4 text-rose-400" />;
      default:
        return <CheckCircle className="w-4 h-4 text-indigo-400" />;
    }
  };

  return (
    <div className="bg-[#101623] border border-slate-800/80 rounded-2xl p-6 shadow-2xl space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-5 border-b border-slate-800/80">
        <div>
          <h2 className="text-lg font-bold text-white tracking-tight flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-emerald-400" />
            Immutable Audit Trail Inspector
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Tamper-evident chronological event log capturing AI decisions, channel actions, and payment reconciliations.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <select
            value={selectedInvId}
            onChange={e => setSelectedInvId(e.target.value)}
            className="bg-slate-900 border border-slate-700 text-xs rounded-xl px-3 py-2 text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 max-w-[240px] sm:max-w-xs truncate"
          >
            {invoices.map(inv => {
              const label = inv.invoice_number && inv.invoice_number !== inv.invoice_id
                ? `${inv.invoice_number} (${inv.invoice_id})`
                : (inv.invoice_number || inv.invoice_id);
              return (
                <option key={inv.invoice_id} value={inv.invoice_id}>
                  {label} — {inv.customer_name}
                </option>
              );
            })}
          </select>

          <button
            onClick={() => {
              loadAudit(true);
              if (onRefresh) onRefresh();
            }}
            disabled={loading || isRefreshing}
            title="Refresh audit records"
            className="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-semibold flex items-center justify-center transition-colors disabled:opacity-50 shadow-sm"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading || isRefreshing ? 'animate-spin text-indigo-400' : ''}`} />
          </button>

          <button
            onClick={exportJSON}
            className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-sm"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export JSON</span>
          </button>
        </div>
      </div>

      {/* Timeline view */}
      <div className="relative pl-6 space-y-8 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-800">
        {loading ? (
          <p className="text-xs text-slate-500 py-6">Loading audit records...</p>
        ) : auditLogs.length === 0 ? (
          <p className="text-xs text-slate-500 py-6">No recorded events for this invoice yet.</p>
        ) : (
          auditLogs.map((log, index) => (
            <div key={log.log_id || index} className="relative group">
              {/* Timeline marker */}
              <div className="absolute -left-[27px] top-1 w-6 h-6 rounded-full bg-slate-900 border border-slate-700 flex items-center justify-center shadow-md">
                {getEventIcon(log.event_type)}
              </div>

              <div className="bg-slate-900/70 border border-slate-800/90 rounded-xl p-4 hover:border-slate-700 transition-colors">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 mb-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold text-white bg-slate-800 px-2 py-0.5 rounded">
                      {log.event_type}
                    </span>
                    <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                      {log.channel}
                    </span>
                  </div>
                  <span className="text-[11px] text-slate-400 font-mono flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {log.timestamp}
                  </span>
                </div>

                <p className="text-xs text-slate-300 leading-relaxed">
                  {log.response_summary || log.raw_input || 'System state synchronized.'}
                </p>

                {log.raw_input && (
                  <div className="mt-2 text-[11px] text-slate-400 bg-slate-950 p-2 rounded-lg border border-slate-800 font-mono">
                    <span className="text-slate-500">Inbound input:</span> "{log.raw_input}"
                  </div>
                )}

                <div className="mt-2 text-[10px] text-slate-500 font-mono">
                  Hash/Log ID: {log.log_id}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
