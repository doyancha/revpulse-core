import React, { useState, useEffect, useRef } from 'react';
import { Send, Sparkles, ShieldAlert, CreditCard, CheckCircle2, MessageSquare, AlertTriangle, ArrowRight, User, Bot, ExternalLink, RefreshCw, XCircle } from 'lucide-react';
import { simulateCustomerTurn } from '../api';

export default function RecoveryConsole({ selectedInvoice, invoices, onInvoiceChange }) {
  const [currentInv, setCurrentInv] = useState(selectedInvoice || invoices[0] || null);
  const [channel, setChannel] = useState(selectedInvoice?.preferred_channel || 'WHATSAPP');
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorAlert, setErrorAlert] = useState(null);
  const [messages, setMessages] = useState([
    {
      role: 'agent',
      content: `Automated recovery initialized for Invoice #${selectedInvoice?.invoice_number || selectedInvoice?.invoice_id || 'QBO_1001'} ($${Number(selectedInvoice?.balance_due || 8500).toLocaleString()} USD). Standing by for customer reply.`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
  ]);
  const [lastResponse, setLastResponse] = useState(null);
  const messagesEndRef = useRef(null);

  // Only re-initialize when switching to a DIFFERENT invoice, preventing periodic poll wipeouts
  useEffect(() => {
    if (selectedInvoice && selectedInvoice.invoice_id !== currentInv?.invoice_id) {
      setCurrentInv(selectedInvoice);
      setChannel(selectedInvoice.preferred_channel || 'WHATSAPP');
      setMessages([
        {
          role: 'agent',
          content: `Automated recovery initiated for Invoice #${selectedInvoice.invoice_number || selectedInvoice.invoice_id} ($${Number(selectedInvoice.balance_due).toLocaleString()} USD). Standing by for customer reply.`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
      ]);
      setLastResponse(null);
      setErrorAlert(null);
    }
  }, [selectedInvoice?.invoice_id]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading, errorAlert]);

  const handleSend = async (textToSend) => {
    const text = textToSend || inputText;
    if (!text.trim() || !currentInv) return;

    setErrorAlert(null);
    const userTimestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    // Append customer message immediately without clearing history
    setMessages(prev => [
      ...prev,
      { role: 'customer', content: text, timestamp: userTimestamp }
    ]);
    setInputText('');
    setLoading(true);

    try {
      const response = await simulateCustomerTurn(currentInv.invoice_id, text, channel);
      const agentTimestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

      const agentResp = response?.agent_response || response?.result;

      if (!agentResp) {
        throw new Error("Invalid response received from RevPulse engine.");
      }

      setLastResponse(agentResp);

      const draftBody =
        agentResp.drafted_communication?.body ||
        agentResp.outbound_draft?.body ||
        agentResp.body ||
        "Message acknowledged by RevPulse AR recovery engine.";

      // Append new turn immediately
      setMessages(prev => [
        ...prev,
        {
          role: 'agent',
          content: draftBody,
          intent: agentResp.intent,
          actions: agentResp.executed_actions,
          riskLevel: agentResp.risk_level,
          timestamp: agentTimestamp
        }
      ]);
    } catch (err) {
      console.error("Simulation error:", err);
      const errorMsg = err.message || "Failed to communicate with RevPulse AI core.";
      setErrorAlert(`Simulation Warning: ${errorMsg}`);
      setMessages(prev => [
        ...prev,
        {
          role: 'error',
          content: `⚠️ Communication Error: ${errorMsg}. Please re-submit your message or check backend server health.`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const presetMessages = [
    { label: "💳 Propose 2-Part Plan", text: "Can we split this into 2 monthly payments?" },
    { label: "⚠️ Raise Billing Dispute", text: "We received defective parts. I dispute this invoice amount." },
    { label: "⚖️ Legal Representation", text: "Do not contact us again. Speak to our bankruptcy attorney." },
    { label: "✅ Promise Full Payment", text: "I have approved the payment. Sending full wire today." }
  ];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Left 2 Cols: Active Interactive Simulation Transcript */}
      <div className="lg:col-span-2 bg-[#101623] border border-slate-800/80 rounded-2xl flex flex-col h-[650px] shadow-2xl overflow-hidden">
        {/* Console Header */}
        <div className="p-4 border-b border-slate-800/80 bg-slate-900/40 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400">
              <MessageSquare className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-white">Autonomous Recovery Session</h3>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                  {currentInv?.invoice_number || currentInv?.invoice_id}
                </span>
              </div>
              <p className="text-[11px] text-slate-400">
                {currentInv?.customer_name} • Balance: ${Number(currentInv?.balance_due || 0).toLocaleString()} USD
              </p>
            </div>
          </div>

          {/* Channel selector */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400 font-medium">Channel:</span>
            <select
              value={channel}
              onChange={e => setChannel(e.target.value)}
              className="bg-slate-900 border border-slate-700 text-xs rounded-lg px-2.5 py-1 text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="WHATSAPP">WhatsApp</option>
              <option value="EMAIL">Email Memo</option>
              <option value="SMS">SMS Message</option>
            </select>
          </div>
        </div>

        {/* Optional Visible Red Error Alert Banner */}
        {errorAlert && (
          <div className="bg-rose-950/70 border-b border-rose-500/30 px-4 py-2.5 flex items-center justify-between text-xs text-rose-300">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-rose-400 flex-shrink-0" />
              <span>{errorAlert}</span>
            </div>
            <button
              onClick={() => setErrorAlert(null)}
              className="text-rose-400 hover:text-white"
            >
              <XCircle className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Message Stream */}
        <div className="flex-1 p-5 overflow-y-auto space-y-4">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex gap-3 max-w-[85%] ${msg.role === 'customer' ? 'ml-auto flex-row-reverse' : ''}`}
            >
              <div className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 text-xs font-bold ${
                msg.role === 'customer'
                  ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                  : msg.role === 'error'
                  ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                  : 'bg-indigo-600/20 text-indigo-400 border border-indigo-500/30'
              }`}>
                {msg.role === 'customer' ? (
                  <User className="w-4 h-4" />
                ) : msg.role === 'error' ? (
                  <AlertTriangle className="w-4 h-4 text-rose-400" />
                ) : (
                  <Bot className="w-4 h-4" />
                )}
              </div>

              <div>
                <div className={`p-4 rounded-2xl text-xs leading-relaxed ${
                  msg.role === 'customer'
                    ? 'bg-amber-500/10 text-slate-200 border border-amber-500/20 rounded-tr-none'
                    : msg.role === 'error'
                    ? 'bg-rose-950/40 text-rose-300 border border-rose-500/40 rounded-tl-none'
                    : 'bg-slate-900/90 text-slate-200 border border-slate-800 rounded-tl-none shadow-lg'
                }`}>
                  <div className="whitespace-pre-line">{msg.content}</div>

                  {/* Metadata pill for agent responses */}
                  {msg.intent && (
                    <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center gap-2 flex-wrap text-[10px]">
                      <span className="font-semibold text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20">
                        Intent: {msg.intent}
                      </span>
                      {msg.riskLevel && (
                        <span className={`px-2 py-0.5 rounded font-semibold border ${
                          msg.riskLevel === 'CRITICAL' || msg.riskLevel === 'HIGH'
                            ? 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                            : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                        }`}>
                          Risk: {msg.riskLevel}
                        </span>
                      )}
                    </div>
                  )}
                </div>
                <p className={`text-[10px] text-slate-500 mt-1 px-1 ${msg.role === 'customer' ? 'text-right' : ''}`}>
                  {msg.timestamp}
                </p>
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex gap-3 max-w-[80%]">
              <div className="w-8 h-8 rounded-xl bg-indigo-600/20 text-indigo-400 border border-indigo-500/30 flex items-center justify-center animate-pulse">
                <Sparkles className="w-4 h-4 text-cyan-400" />
              </div>
              <div className="p-3.5 rounded-2xl bg-slate-900/90 border border-slate-800 text-xs text-slate-400 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-ping" />
                <span>Evaluating intent & calculating financial bounds with Gemini...</span>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Preset Debtor Scenarios */}
        <div className="p-3 bg-slate-900/50 border-t border-slate-800/60 flex items-center gap-2 overflow-x-auto">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex-shrink-0">
            Quick Prompts:
          </span>
          {presetMessages.map((btn, idx) => (
            <button
              key={idx}
              onClick={() => handleSend(btn.text)}
              disabled={loading}
              className="text-[11px] font-medium px-2.5 py-1 rounded-lg bg-slate-800/90 hover:bg-slate-800 text-slate-300 hover:text-white border border-slate-700/60 transition-colors whitespace-nowrap flex-shrink-0 disabled:opacity-50"
            >
              {btn.label}
            </button>
          ))}
        </div>

        {/* Input Bar */}
        <form
          onSubmit={(e) => { e.preventDefault(); handleSend(); }}
          className="p-3.5 bg-slate-900/90 border-t border-slate-800 flex items-center gap-2"
        >
          <input
            type="text"
            placeholder="Type customer reply (e.g. 'Can I pay half now and half next month?')..."
            value={inputText}
            onChange={e => setInputText(e.target.value)}
            disabled={loading}
            className="flex-1 bg-slate-950/80 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
          />
          <button
            type="submit"
            disabled={loading || !inputText.trim()}
            className="px-4 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl text-xs font-semibold flex items-center gap-1.5 shadow-lg shadow-indigo-600/30 transition-all"
          >
            <Send className="w-3.5 h-3.5" />
            <span>Send Turn</span>
          </button>
        </form>
      </div>

      {/* Right 1 Col: Real-time Decision Inspector & Action Cards */}
      <div className="space-y-4">
        {/* Active Target Invoice Card */}
        <div className="bg-[#101623] border border-slate-800/80 rounded-2xl p-5 shadow-xl">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 flex items-center justify-between">
            <span>Target Invoice Context</span>
            <span className="text-[10px] text-indigo-400 font-mono">QBO/XERO SYNC</span>
          </h4>

          <div className="space-y-2.5 text-xs">
            <div className="flex justify-between py-1 border-b border-slate-800/60">
              <span className="text-slate-400">Company:</span>
              <span className="font-semibold text-slate-200">{currentInv?.customer_name}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-800/60">
              <span className="text-slate-400">Invoice ID:</span>
              <span className="font-mono text-slate-200">{currentInv?.invoice_number || currentInv?.invoice_id}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-800/60">
              <span className="text-slate-400">Total Due:</span>
              <span className="font-bold text-white font-mono">${Number(currentInv?.balance_due || 0).toLocaleString()} USD</span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-800/60">
              <span className="text-slate-400">Overdue Age:</span>
              <span className="font-medium text-rose-400">{currentInv?.days_overdue} Days Past Due</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-400">Hold Status:</span>
              <span className={`font-semibold ${currentInv?.dispute_hold ? 'text-rose-400' : 'text-emerald-400'}`}>
                {currentInv?.dispute_hold ? 'Dunning Paused (Hold)' : 'Active Dunning'}
              </span>
            </div>
          </div>
        </div>

        {/* Dynamic AI Inspector Result Panel */}
        {lastResponse?.proposed_settlement && (
          <div className="bg-gradient-to-b from-indigo-950/30 to-[#101623] border border-indigo-500/40 rounded-2xl p-5 shadow-xl animate-in fade-in duration-300">
            <div className="flex items-center gap-2 text-indigo-400 text-xs font-bold uppercase tracking-wider mb-2">
              <CreditCard className="w-4 h-4" />
              <span>Structured Settlement Approved</span>
            </div>
            <p className="text-xs text-slate-300 mb-3">
              Complies with strict max 3-split policy without exceeding debt balance.
            </p>

            <div className="space-y-2">
              {lastResponse.proposed_settlement.installments?.map((inst, i) => (
                <div key={i} className="flex items-center justify-between p-2.5 rounded-xl bg-slate-900/80 border border-slate-800 text-xs">
                  <div>
                    <p className="font-bold text-white">Split #{inst.installment_number || i + 1}</p>
                    <p className="text-[11px] text-slate-400">Due: {inst.due_date}</p>
                  </div>
                  <div className="text-right">
                    <p className="font-mono font-bold text-indigo-400">${Number(inst.amount).toLocaleString()} USD</p>
                    <a
                      href={inst.payment_link || "#"}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[10px] text-cyan-400 hover:underline flex items-center gap-0.5 justify-end"
                    >
                      <span>Pay Link</span>
                      <ExternalLink className="w-2.5 h-2.5" />
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {lastResponse?.dispute_details && (
          <div className="bg-gradient-to-b from-rose-950/30 to-[#101623] border border-rose-500/40 rounded-2xl p-5 shadow-xl animate-in fade-in duration-300">
            <div className="flex items-center gap-2 text-rose-400 text-xs font-bold uppercase tracking-wider mb-2">
              <ShieldAlert className="w-4 h-4" />
              <span>Dispute Hold Certificate</span>
            </div>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between py-1 border-b border-slate-800">
                <span className="text-slate-400">Ticket #:</span>
                <span className="font-mono font-bold text-white">{lastResponse.dispute_details.ticket_id}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-800">
                <span className="text-slate-400">Category:</span>
                <span className="font-semibold text-rose-300">{lastResponse.dispute_details.category}</span>
              </div>
              <div className="py-1">
                <span className="text-slate-400 block mb-1">Operational Action:</span>
                <p className="text-[11px] text-slate-300 bg-slate-900 p-2 rounded-lg border border-slate-800">
                  {lastResponse.dispute_details.summary}
                </p>
              </div>
            </div>
          </div>
        )}

        {lastResponse?.risk_level === 'CRITICAL' && (
          <div className="bg-gradient-to-b from-purple-950/30 to-[#101623] border border-purple-500/40 rounded-2xl p-5 shadow-xl animate-in fade-in duration-300">
            <div className="flex items-center gap-2 text-purple-400 text-xs font-bold uppercase tracking-wider mb-2">
              <AlertTriangle className="w-4 h-4" />
              <span>Incident Escalation Active</span>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              Customer invoked legal / insolvency boundaries. AI automated communication has been stopped. Incident pushed to Human Escalation Queue.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
