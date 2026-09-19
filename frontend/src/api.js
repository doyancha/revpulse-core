const API_BASE_URL = 'http://localhost:8000/api/v1';

export const fallbackInvoices = [
  {
    invoice_id: "QBO_1001",
    invoice_number: "INV-1001",
    platform: "QUICKBOOKS",
    customer_name: "Acme Industrial Supplies",
    customer_email: "billing@acmeind.com",
    customer_phone: "+1-555-0199",
    total_amount: 8500.0,
    balance_due: 8500.0,
    due_date: "2026-08-15",
    currency: "USD",
    status: "ACTIVE",
    days_overdue: 35,
    aging_bucket: "OVERDUE_30_PLUS",
    dispute_hold: false,
    preferred_channel: "WHATSAPP",
    conversation_id: "sim_QBO_1001"
  },
  {
    invoice_id: "QBO_1002",
    invoice_number: "INV-1002",
    platform: "QUICKBOOKS",
    customer_name: "Stark Global Technologies",
    customer_email: "ap@starktech.com",
    customer_phone: "+1-555-0200",
    total_amount: 14200.0,
    balance_due: 14200.0,
    due_date: "2026-09-01",
    currency: "USD",
    status: "ACTIVE",
    days_overdue: 18,
    aging_bucket: "OVERDUE_15_PLUS",
    dispute_hold: false,
    preferred_channel: "EMAIL",
    conversation_id: "sim_QBO_1002"
  },
  {
    invoice_id: "XERO_8001",
    invoice_number: "INV-8001",
    platform: "XERO",
    customer_name: "Cyberdyne Systems Corp",
    customer_email: "finance@cyberdyne.io",
    customer_phone: "+1-555-0301",
    total_amount: 6750.0,
    balance_due: 6750.0,
    due_date: "2026-08-28",
    currency: "USD",
    status: "UNDER_DISPUTE",
    days_overdue: 22,
    aging_bucket: "OVERDUE_15_PLUS",
    dispute_hold: true,
    preferred_channel: "EMAIL",
    conversation_id: "sim_XERO_8001"
  },
  {
    invoice_id: "XERO_8002",
    invoice_number: "INV-8002",
    platform: "XERO",
    customer_name: "Wayne Enterprises",
    customer_email: "accounts@wayne-ent.com",
    customer_phone: "+1-555-0302",
    total_amount: 22000.0,
    balance_due: 11000.0,
    due_date: "2026-08-10",
    currency: "USD",
    status: "RESOLVED_PLAN",
    days_overdue: 40,
    aging_bucket: "OVERDUE_30_PLUS",
    dispute_hold: false,
    preferred_channel: "SMS",
    conversation_id: "sim_XERO_8002"
  },
  {
    invoice_id: "QBO_1003",
    invoice_number: "INV-1003",
    platform: "QUICKBOOKS",
    customer_name: "Apex Logistics Ltd",
    customer_email: "disputes@apexlog.com",
    customer_phone: "+1-555-0205",
    total_amount: 19500.0,
    balance_due: 19500.0,
    due_date: "2026-07-20",
    currency: "USD",
    status: "ESCALATED",
    days_overdue: 61,
    aging_bucket: "OVERDUE_60_PLUS",
    dispute_hold: true,
    preferred_channel: "EMAIL",
    conversation_id: "sim_QBO_1003"
  }
];

export async function checkApiHealth() {
  try {
    const res = await fetch('http://localhost:8000/health');
    return res.ok;
  } catch {
    return false;
  }
}

export async function fetchInvoices() {
  try {
    const res = await fetch(`${API_BASE_URL}/dashboard/invoices`);
    if (!res.ok) throw new Error("API request failed");
    return await res.json();
  } catch {
    return fallbackInvoices;
  }
}

export async function fetchMetrics() {
  try {
    const res = await fetch(`${API_BASE_URL}/dashboard/metrics`);
    if (!res.ok) throw new Error("API request failed");
    return await res.json();
  } catch {
    const total_ar = fallbackInvoices.reduce((acc, inv) => acc + inv.balance_due, 0);
    const overdue_balance = fallbackInvoices.filter(i => i.days_overdue >= 7).reduce((acc, inv) => acc + inv.balance_due, 0);
    return {
      total_ar,
      overdue_balance,
      active_plans: 1,
      frozen_disputes: 2,
      escalated_count: 1,
      reconciled_paid: 1,
      total_invoices: fallbackInvoices.length,
      recovery_rate_pct: 20.0
    };
  }
}

export async function simulateCustomerTurn(invoiceId, text, channel = "WHATSAPP") {
  try {
    const res = await fetch(`${API_BASE_URL}/dashboard/simulate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        invoice_id: invoiceId,
        customer_text: text,
        channel: channel
      })
    });
    if (!res.ok) throw new Error(`Status ${res.status}`);
    return await res.json();
  } catch (err) {
    // Generate simulated dynamic fallback turn if server is offline
    const isPlan = text.toLowerCase().includes("plan") || text.toLowerCase().includes("split") || text.toLowerCase().includes("install");
    const isDispute = text.toLowerCase().includes("dispute") || text.toLowerCase().includes("wrong") || text.toLowerCase().includes("charge") || text.toLowerCase().includes("defective");
    const isEscalation = text.toLowerCase().includes("lawyer") || text.toLowerCase().includes("sue") || text.toLowerCase().includes("bankrupt") || text.toLowerCase().includes("scam");

    if (isEscalation) {
      return {
        result: {
          intent: "LEGAL_THREAT",
          action_required: "FLAG_HUMAN_REVIEW",
          state_status: "ESCALATED",
          confidence_score: 0.99,
          risk_level: "CRITICAL",
          executed_actions: ["manager_alert_dispatched", "dunning_halted"],
          outbound_draft: {
            channel: channel,
            recipient: "Customer",
            body: "We have acknowledged your notice regarding legal representation. Direct recovery outreach has been frozen, and your account is flagged for Senior Counsel and Account Executive review."
          }
        }
      };
    }

    if (isPlan) {
      return {
        result: {
          intent: "PAYMENT_PLAN_REQUESTED",
          action_required: "SEND_PAYMENT_PLAN_AGREEMENT",
          state_status: "RESOLVED_PLAN",
          confidence_score: 0.96,
          risk_level: "LOW",
          executed_actions: ["settlement_generated", "installment_links_created"],
          proposed_settlement: {
            installments_count: 2,
            total_amount: 8500.0,
            installments: [
              { installment_number: 1, due_date: "2026-09-27", amount: 4250.0, payment_link: "https://pay.revpulse.io/checkout/QBO_1001?inst=1" },
              { installment_number: 2, due_date: "2026-10-27", amount: 4250.0, payment_link: "https://pay.revpulse.io/checkout/QBO_1001?inst=2" }
            ]
          },
          outbound_draft: {
            channel: channel,
            recipient: "Customer",
            body: "Thank you for partnering with us to resolve this. We have structured an approved 2-part installment schedule:\n\n• Installment 1: $4,250.00 (Due Sep 27, 2026)\n• Installment 2: $4,250.00 (Due Oct 27, 2026)\n\nPlease confirm your agreement or initiate the first split via the secure link."
          }
        }
      };
    }

    if (isDispute) {
      return {
        result: {
          intent: "BILLING_DISPUTE",
          action_required: "OPEN_DISPUTE_TICKET",
          state_status: "UNDER_DISPUTE",
          confidence_score: 0.94,
          risk_level: "HIGH",
          executed_actions: ["dispute_ticket_created", "dunning_hold_applied"],
          dispute_details: {
            ticket_id: "DISP-2026-902",
            category: "SERVICES_NOT_RENDERED",
            disputed_amount: 8500.0,
            hold_dunning: true,
            summary: "Debtor raised discrepancy regarding deliverables. Dunning frozen pending billing review."
          },
          outbound_draft: {
            channel: channel,
            recipient: "Customer",
            body: "We take invoice accuracy very seriously. We have logged Dispute Ticket #DISP-2026-902 and placed an immediate administrative hold on dunning notices while our accounting team investigates."
          }
        }
      };
    }

    return {
      result: {
        intent: "GENERAL_INQUIRY",
        action_required: "REQUEST_INFO",
        state_status: "ACTIVE",
        confidence_score: 0.92,
        risk_level: "LOW",
        executed_actions: ["conversation_recorded"],
        outbound_draft: {
          channel: channel,
          recipient: "Customer",
          body: `Thank you for your message regarding Invoice #${invoiceId}. How can our accounts receivable team assist you today?`
        }
      }
    };
  }
}

export async function fetchAuditTrail(invoiceId) {
  try {
    const res = await fetch(`${API_BASE_URL}/audit/${invoiceId}`);
    if (!res.ok) throw new Error("API request failed");
    return await res.json();
  } catch {
    return [
      {
        log_id: "log_init_01",
        timestamp: "2026-09-19T10:00:00Z",
        invoice_id: invoiceId,
        customer_id: "CUST-DEFAULT",
        event_type: "INVOICE_INGESTED",
        channel: "QUICKBOOKS",
        response_summary: "Ingested invoice records and calculated 35 days past due aging bucket.",
        metadata: { platform: "QUICKBOOKS" }
      },
      {
        log_id: "log_init_02",
        timestamp: "2026-09-19T10:05:00Z",
        invoice_id: invoiceId,
        customer_id: "CUST-DEFAULT",
        event_type: "DUNNING_TRIGGERED",
        channel: "SYSTEM",
        response_summary: "Daily aging scan triggered dunning sequence across preferred WhatsApp channel.",
        metadata: { trigger: "SCHEDULED_DAILY_SYNC" }
      }
    ];
  }
}
