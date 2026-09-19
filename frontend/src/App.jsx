import React, { useState, useEffect } from 'react';
import Navbar from './components/Navbar';
import KPICards from './components/KPICards';
import InvoiceLedger from './components/InvoiceLedger';
import RecoveryConsole from './components/RecoveryConsole';
import EscalationQueue from './components/EscalationQueue';
import AuditInspector from './components/AuditInspector';
import { fetchInvoices, fetchMetrics } from './api';

export default function App() {
  const [activeTab, setActiveTab] = useState('ledger');
  const [invoices, setInvoices] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [selectedInvoice, setSelectedInvoice] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadData = async () => {
    try {
      const [invData, metricsData] = await Promise.all([
        fetchInvoices(),
        fetchMetrics()
      ]);
      setInvoices(invData);
      setMetrics(metricsData);
      if (!selectedInvoice && invData.length > 0) {
        setSelectedInvoice(invData[0]);
      }
    } catch (err) {
      console.error("Data load failed:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 3000);
    return () => clearInterval(interval);
  }, []);

  const handleSelectInvoice = (invoice) => {
    setSelectedInvoice(invoice);
    setActiveTab('console');
  };

  return (
    <div className="min-h-screen bg-[#090D16] text-slate-100 flex flex-col selection:bg-indigo-500 selection:text-white">
      {/* Top Enterprise Navigation */}
      <Navbar activeTab={activeTab} setActiveTab={setActiveTab} />

      {/* Main Content Viewport */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* Executive KPI Metrics Row */}
        <KPICards metrics={metrics} />

        {/* Tab Views */}
        <div className="transition-all duration-200">
          {activeTab === 'ledger' && (
            <InvoiceLedger
              invoices={invoices}
              onSelectInvoice={handleSelectInvoice}
              onRefresh={loadData}
              isRefreshing={loading}
            />
          )}

          {activeTab === 'console' && (
            <RecoveryConsole
              selectedInvoice={selectedInvoice}
              invoices={invoices}
              onInvoiceChange={setSelectedInvoice}
            />
          )}

          {activeTab === 'escalations' && (
            <EscalationQueue />
          )}

          {activeTab === 'audit' && (
            <AuditInspector
              selectedInvoice={selectedInvoice}
              invoices={invoices}
              onRefresh={loadData}
              isRefreshing={loading}
            />
          )}
        </div>
      </main>

      {/* Footer Status Bar */}
      <footer className="border-t border-slate-900 bg-[#0B0F1A]/80 py-4 text-center text-xs text-slate-500">
        <p>
          RevPulse Autonomous AR Recovery Engine • Built with Gemini 3.6 Flash, FastAPI & React
        </p>
      </footer>
    </div>
  );
}
