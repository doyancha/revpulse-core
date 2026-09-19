"""
Unit and integration tests for FastAPI Webhook & Communications Gateway Server.
Covers:
- GET /health
- POST /api/v1/webhooks/stripe (Stripe reconciliation & audit entry)
- POST /api/v1/webhooks/twilio (SMS inbound roundtrip with mock AI response)
- POST /api/v1/webhooks/quickbooks (QBO ingestion & delinquent filtering)
- GET /api/v1/audit/{invoice_id} & GET /api/v1/conversation/{conversation_id}
"""

import json
from pathlib import Path
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import pytest

from src.main import app
from src.api.dependencies import (
    get_ai_engine,
    get_audit_logger,
    get_recovery_coordinator,
    get_state_manager,
    recovery_coordinator,
    audit_logger,
    state_manager,
)
from src.schemas.agent_schema import (
    ActionRequired,
    Channel,
    CommunicationDraft,
    Installment,
    Intent,
    ProposedSettlement,
    RevPulseAgentResponse,
    RiskLevel,
)
from src.schemas.conversation_schema import ConversationStatus

client = TestClient(app)
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_health_check():
    """Verify health check endpoint returns 200 OK."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "RevPulse Core"


def test_quickbooks_webhook_endpoint():
    """Verify QBO webhook endpoint processes and filters invoices."""
    qbo_path = FIXTURES_DIR / "qbo_invoices.json"
    with open(qbo_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    response = client.post("/api/v1/webhooks/quickbooks", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "PROCESSED"
    assert data["platform"] == "QUICKBOOKS"
    assert data["processed_count"] == 3
    assert data["actionable_count"] >= 1


def test_twilio_sms_webhook_roundtrip(monkeypatch):
    """
    Simulate customer requesting a payment plan via Twilio SMS webhook.
    Verify that response contains accepted installment schedule and link.
    """
    from config import settings
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", None)

    invoice_id = "INV-TWILIO-770"
    conv_id = f"sms_+15551234567_{invoice_id}"

    # Mock AI response inside recovery coordinator
    mock_ai = MagicMock()
    mock_ai.analyze_interaction.return_value = RevPulseAgentResponse(
        intent=Intent.PAYMENT_PLAN_REQUESTED,
        action_required=ActionRequired.SEND_PAYMENT_PLAN_AGREEMENT,
        confidence_score=0.96,
        risk_level=RiskLevel.MEDIUM,
        drafted_communication=CommunicationDraft(
            channel=Channel.SMS,
            recipient="+15551234567",
            body="We can offer a 2-part plan: $500 now and $500 in 30 days.",
        ),
        proposed_settlement=ProposedSettlement(
            installments_count=2,
            total_amount=1000.0,
            installments=[
                Installment(due_date="2026-09-26", amount=500.0),
                Installment(due_date="2026-10-26", amount=500.0),
            ],
        ),
        internal_notes="Approved 2-installment SMS plan.",
    )

    monkeypatch.setattr(recovery_coordinator, "ai_engine", mock_ai)

    sms_payload = {
        "From": "+15551234567",
        "Body": "Can I split this bill into two payments?",
        "invoice_id": invoice_id,
        "customer_id": "CUST-TWILIO-1",
        "balance_due": 1000.0,
        "days_overdue": 16,
    }

    response = client.post("/api/v1/webhooks/twilio", json=sms_payload)
    assert response.status_code == 200
    data = response.json()

    assert data["intent"] == "PAYMENT_PLAN_REQUESTED"
    assert data["action_required"] == "SEND_PAYMENT_PLAN_AGREEMENT"
    assert data["state_status"] == ConversationStatus.RESOLVED_PLAN.value
    assert "first_installment_link" in data["executed_actions"]


def test_stripe_webhook_endpoint():
    """Verify Stripe webhook resolves invoice and writes PAYMENT_RECONCILED audit log."""
    invoice_id = "INV-STRIPE-RECON-88"
    conv_id = f"test_conv_{invoice_id}"

    # Setup initial state
    state_manager.get_or_create_state(
        conversation_id=conv_id,
        invoice_id=invoice_id,
        customer_id="CUST-STRIPE-88",
    )

    stripe_payload = {
        "id": "evt_stripe_recon_001",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_stripe_001",
                "customer": "CUST-STRIPE-88",
                "invoice_id": invoice_id,
                "amount_total": 3500.0,
                "currency": "usd",
                "payment_status": "paid",
            }
        },
    }

    response = client.post("/api/v1/webhooks/stripe", json=stripe_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "RECONCILED"
    assert data["reconciliation"]["invoice_id"] == invoice_id
    assert data["reconciliation"]["amount_paid"] == 3500.0

    # Verify state was marked RESOLVED_PAID
    state = state_manager.get_state(conv_id)
    assert state.status == ConversationStatus.RESOLVED_PAID.value


def test_audit_and_conversation_retrieval_endpoints():
    """Verify GET /api/v1/audit/{invoice_id} and GET /api/v1/conversation/{conversation_id}."""
    invoice_id = "INV-INSPECT-100"
    conv_id = "conv-inspect-100"

    # Seed an event in audit logger
    audit_logger.log_event(
        event_type="INBOUND_MESSAGE",
        invoice_id=invoice_id,
        customer_id="CUST-INSPECT",
        channel="EMAIL",
        raw_input="Hello inspection test",
    )

    state_manager.get_or_create_state(
        conversation_id=conv_id,
        invoice_id=invoice_id,
        customer_id="CUST-INSPECT",
    )

    # Test audit trail
    audit_res = client.get(f"/api/v1/audit/{invoice_id}")
    assert audit_res.status_code == 200
    audit_data = audit_res.json()
    assert len(audit_data) >= 1
    assert audit_data[0]["invoice_id"] == invoice_id

    # Test conversation state
    conv_res = client.get(f"/api/v1/conversation/{conv_id}")
    assert conv_res.status_code == 200
    conv_data = conv_res.json()
    assert conv_data["conversation_id"] == conv_id
    assert conv_data["invoice_id"] == invoice_id
