"""
Unit and integration tests for Live Sandbox Webhook Verification Layer.
Covers:
1. Stripe cryptographic webhook signature verification (valid, forged, missing).
2. Stripe permissive fallback mode when STRIPE_WEBHOOK_SECRET is unset.
3. Twilio SMS webhook signature validation (valid, forged, missing).
4. Twilio permissive fallback mode when TWILIO_AUTH_TOKEN is unset.
"""

import json
import time
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
import stripe
from twilio.request_validator import RequestValidator

from config import settings
from src.api.dependencies import recovery_coordinator, state_manager
from src.main import app
from src.schemas.agent_schema import (
    ActionRequired,
    Channel,
    CommunicationDraft,
    Intent,
    RevPulseAgentResponse,
    RiskLevel,
)
from src.schemas.conversation_schema import ConversationStatus

client = TestClient(app)


@pytest.fixture
def mock_ai_response(monkeypatch):
    """Mocks AI engine analysis for predictable comm webhook handling."""
    mock_ai = MagicMock()
    mock_ai.analyze_interaction.return_value = RevPulseAgentResponse(
        intent=Intent.PAYMENT_PLAN_REQUESTED,
        action_required=ActionRequired.SEND_PAYMENT_PLAN_AGREEMENT,
        confidence_score=0.98,
        risk_level=RiskLevel.LOW,
        drafted_communication=CommunicationDraft(
            channel=Channel.SMS,
            recipient="+15551234567",
            body="We have received your payment request.",
        ),
        internal_notes="Sandbox test approval.",
    )
    monkeypatch.setattr(recovery_coordinator, "ai_engine", mock_ai)
    return mock_ai


def test_stripe_webhook_valid_signature(monkeypatch):
    """Verify authentic Stripe signature successfully verifies and reconciles invoice."""
    test_secret = "whsec_live_sandbox_test_secret_123"
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", test_secret)

    invoice_id = "INV-STRIPE-SANDBOX-01"
    conv_id = f"test_conv_{invoice_id}"
    state_manager.get_or_create_state(
        conversation_id=conv_id,
        invoice_id=invoice_id,
        customer_id="CUST-SANDBOX-01",
    )

    payload_dict = {
        "id": "evt_sandbox_001",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_sandbox_001",
                "customer": "CUST-SANDBOX-01",
                "invoice_id": invoice_id,
                "amount_total": 4200.0,
                "currency": "usd",
                "payment_status": "paid",
            }
        },
    }
    raw_payload = json.dumps(payload_dict)
    timestamp = int(time.time())
    sig_header = stripe.WebhookSignature.generate_signature_header(
        raw_payload,
        test_secret,
        timestamp=timestamp,
    )

    response = client.post(
        "/api/v1/webhooks/stripe",
        content=raw_payload,
        headers={"Stripe-Signature": sig_header, "Content-Type": "application/json"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "RECONCILED"
    assert data["reconciliation"]["invoice_id"] == invoice_id
    assert data["reconciliation"]["amount_paid"] == 4200.0

    state = state_manager.get_state(conv_id)
    assert state.status == ConversationStatus.RESOLVED_PAID.value


def test_stripe_webhook_invalid_signature_rejection(monkeypatch):
    """Verify forged Stripe signature triggers 400 Bad Request."""
    test_secret = "whsec_live_sandbox_test_secret_123"
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", test_secret)

    payload_dict = {
        "id": "evt_sandbox_forged",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "invoice_id": "INV-FORGED-01",
                "amount_total": 100.0,
            }
        },
    }
    raw_payload = json.dumps(payload_dict)
    forged_header = "t=1700000000,v1=badbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadb"

    response = client.post(
        "/api/v1/webhooks/stripe",
        content=raw_payload,
        headers={"Stripe-Signature": forged_header, "Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert "Invalid Stripe signature" in response.json()["detail"]


def test_stripe_webhook_missing_signature_when_configured(monkeypatch):
    """Verify missing signature header returns 400 when webhook secret is active."""
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_active_secret")
    payload = {"id": "evt_test", "type": "checkout.session.completed"}

    response = client.post("/api/v1/webhooks/stripe", json=payload)
    assert response.status_code == 400
    assert "Missing Stripe-Signature" in response.json()["detail"]


def test_twilio_sms_webhook_valid_signature(monkeypatch, mock_ai_response):
    """Verify authentic Twilio signature passes validation and processes inbound message."""
    auth_token = "auth_token_sandbox_secret_999"
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", auth_token)

    params = {
        "From": "+15554443322",
        "Body": "Can I get an extension on invoice INV-TW-VALID?",
        "invoice_id": "INV-TW-VALID",
        "customer_id": "CUST-TW-VALID",
        "balance_due": "1500.0",
        "days_overdue": "12",
    }
    target_url = "http://testserver/api/v1/webhooks/twilio"
    validator = RequestValidator(auth_token)
    signature = validator.compute_signature(target_url, params)

    response = client.post(
        "/api/v1/webhooks/twilio",
        data=params,
        headers={"X-Twilio-Signature": signature},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "PAYMENT_PLAN_REQUESTED"
    assert data["action_required"] == "SEND_PAYMENT_PLAN_AGREEMENT"


def test_twilio_sms_webhook_forged_signature_rejection(monkeypatch, mock_ai_response):
    """Verify forged Twilio signature is rejected with 401 Unauthorized."""
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "auth_token_sandbox_secret_999")

    params = {
        "From": "+15554443322",
        "Body": "Forged payload",
    }
    response = client.post(
        "/api/v1/webhooks/twilio",
        data=params,
        headers={"X-Twilio-Signature": "forged_signature_xyz=="},
    )
    assert response.status_code == 401
    assert "Invalid Twilio signature" in response.json()["detail"]


def test_twilio_sms_webhook_missing_signature_rejection(monkeypatch, mock_ai_response):
    """Verify missing Twilio signature header returns 401 Unauthorized when secret configured."""
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "auth_token_sandbox_secret_999")

    params = {
        "From": "+15554443322",
        "Body": "Missing signature payload",
    }
    response = client.post("/api/v1/webhooks/twilio", data=params)
    assert response.status_code == 401
    assert "Missing X-Twilio-Signature" in response.json()["detail"]


def test_stripe_webhook_reconciles_by_doc_number_and_updates_db(monkeypatch):
    """Verify Stripe webhook lookup by doc_number resolves normalized ID, updates DB balance, and links audit trail."""
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", None)
    from datetime import date
    from sqlmodel import Session, select
    from src.database.db import engine
    from src.database.models import InvoiceRecord
    from src.api.dependencies import audit_logger

    inv_id = "QBO_TEST_NORM_01"
    doc_num = "INV-NORM-8888"

    with Session(engine) as session:
        inv = InvoiceRecord(
            id=inv_id,
            doc_number=doc_num,
            customer_name="Normalization Corp",
            customer_email="billing@normcorp.com",
            total_amount=7500.0,
            balance_due=7500.0,
            due_date=date.today(),
            status="ACTIVE",
        )
        session.add(inv)
        session.commit()

    payload = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_norm_001",
                "customer": "CUST_NORM",
                "amount_total": 7500.0,
                "currency": "usd",
                "metadata": {
                    "invoice_id": doc_num,  # Passed as doc_number
                },
            }
        },
    }

    response = client.post("/api/v1/webhooks/stripe", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "RECONCILED"
    assert res_data["reconciliation"]["invoice_id"] == inv_id
    assert res_data["reconciliation"]["doc_number"] == doc_num

    # Verify DB balance was wiped to 0 and status set to RESOLVED_PAID
    with Session(engine) as session:
        updated_inv = session.exec(select(InvoiceRecord).where(InvoiceRecord.id == inv_id)).first()
        assert updated_inv is not None
        assert updated_inv.balance_due == 0.0
        assert updated_inv.status == "RESOLVED_PAID"

    # Verify audit trail can be retrieved using either identifier
    trail_by_doc = audit_logger.get_invoice_audit_trail(doc_num)
    trail_by_id = audit_logger.get_invoice_audit_trail(inv_id)
    assert len(trail_by_doc) >= 1
    assert any(log.event_type == "PAYMENT_RECONCILED" for log in trail_by_doc)
    assert len(trail_by_id) >= 1
    assert any(log.event_type == "PAYMENT_RECONCILED" for log in trail_by_id)


def test_whatsapp_webhook_dispatches_outbound_reply(monkeypatch, mock_ai_response):
    """Verify live outbound WhatsApp reply is dispatched via Twilio REST client when credentials configured."""
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "AC_test_sandbox_sid")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "test_sandbox_auth_token")
    monkeypatch.setattr(settings, "TWILIO_WHATSAPP_NUMBER", "+17572508054")

    mock_client_instance = MagicMock()
    mock_messages = MagicMock()
    mock_client_instance.messages = mock_messages

    import twilio.rest
    monkeypatch.setattr(twilio.rest, "Client", MagicMock(return_value=mock_client_instance))

    params = {
        "From": "whatsapp:+8801671761312",
        "Body": "Can I split this invoice?",
        "invoice_id": "INV-WA-SANDBOX-77",
    }

    target_url = "http://testserver/api/v1/webhooks/whatsapp"
    validator = RequestValidator("test_sandbox_auth_token")
    signature = validator.compute_signature(target_url, params)

    response = client.post(
        "/api/v1/webhooks/whatsapp",
        data=params,
        headers={"X-Twilio-Signature": signature},
    )

    assert response.status_code == 200
    mock_messages.create.assert_called_once_with(
        from_="whatsapp:+17572508054",
        to="whatsapp:+8801671761312",
        body="We have received your payment request.",
    )


def test_whatsapp_webhook_fallback_when_unconfigured(monkeypatch, mock_ai_response):
    """Verify WhatsApp webhook executes cleanly and returns JSON response when Twilio credentials are unset."""
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", None)
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", None)

    params = {
        "From": "+15551234567",
        "Body": "General invoice question",
        "invoice_id": "INV-WA-UNCONFIGURED",
    }

    response = client.post("/api/v1/webhooks/whatsapp", data=params)
    assert response.status_code == 200
    data = response.json()
    assert "outbound_draft" in data
    assert data["drafted_message"] == "We have received your payment request."


def test_whatsapp_webhook_dev_signature_bypass(monkeypatch, mock_ai_response):
    """Verify development mode bypasses signature validation with dev-test-signature, None, or x-dev-test header."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "auth_token_secret_123")
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", None)  # Prevent actual dispatch in this test

    params = {
        "From": "whatsapp:+15551112233",
        "Body": "Dev test prompt",
        "invoice_id": "INV-WA-DEV-001",
    }

    # Case 1: x_twilio_signature == "dev-test-signature"
    res1 = client.post(
        "/api/v1/webhooks/whatsapp",
        data=params,
        headers={"X-Twilio-Signature": "dev-test-signature"},
    )
    assert res1.status_code == 200
    assert res1.json()["drafted_message"] == "We have received your payment request."

    # Case 2: x_twilio_signature is None
    res2 = client.post("/api/v1/webhooks/whatsapp", data=params)
    assert res2.status_code == 200
    assert res2.json()["drafted_message"] == "We have received your payment request."

    # Case 3: explicit x-dev-test header with invalid signature
    res3 = client.post(
        "/api/v1/webhooks/whatsapp",
        data=params,
        headers={"X-Twilio-Signature": "invalid-sig", "X-Dev-Test": "true"},
    )
    assert res3.status_code == 200
    assert res3.json()["drafted_message"] == "We have received your payment request."


def test_whatsapp_webhook_production_enforcement(monkeypatch, mock_ai_response):
    """Verify production mode rejects dev-test-signature or missing signature when auth token configured."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "auth_token_secret_prod_999")

    params = {
        "From": "whatsapp:+15551112233",
        "Body": "Production test prompt",
        "invoice_id": "INV-WA-PROD-001",
    }

    # Case 1: Missing signature in production -> 401
    res1 = client.post("/api/v1/webhooks/whatsapp", data=params)
    assert res1.status_code == 401
    assert "Missing X-Twilio-Signature" in res1.json()["detail"]

    # Case 2: dev-test-signature in production -> rejected with 401
    res2 = client.post(
        "/api/v1/webhooks/whatsapp",
        data=params,
        headers={"X-Twilio-Signature": "dev-test-signature"},
    )
    assert res2.status_code == 401
    assert "Invalid Twilio signature" in res2.json()["detail"]
