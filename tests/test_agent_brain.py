"""
Pytest suite for RevPulse AI Brain Architecture.
Covers:
1. Scenario A: Full payment promise returns SEND_PAYMENT_LINK and LOW risk.
2. Scenario B: Deliverable dispute returns BILLING_DISPUTE, OPEN_DISPUTE_TICKET, and populates dispute_details.
3. Scenario C: 50/50 split request returns PAYMENT_PLAN_REQUESTED, SEND_PAYMENT_PLAN_AGREEMENT, and validates installments <= 3.
4. Scenario D: Schema validation test verifying invalid fields, malformed numbers, or policy breaches are rejected by Pydantic.
5. Integration/Mock tests verifying RevPulseAIEngine wiring and response_schema enforcement.
"""

from unittest.mock import MagicMock
import pytest
from pydantic import ValidationError

from src.schemas.agent_schema import (
    ActionRequired,
    Channel,
    CommunicationDraft,
    DisputeCategory,
    DisputeDetails,
    Installment,
    Intent,
    ProposedSettlement,
    RevPulseAgentResponse,
    RiskLevel,
)
from src.services.ai_engine import RevPulseAIEngine


# ============================================================================
# SCENARIO A: Full Payment Check-in
# ============================================================================
def test_scenario_a_full_payment_promise():
    """Customer agrees to settle balance immediately in full."""
    response_data = {
        "intent": Intent.FULL_PAYMENT_PROMISED,
        "action_required": ActionRequired.SEND_PAYMENT_LINK,
        "confidence_score": 0.98,
        "risk_level": RiskLevel.LOW,
        "drafted_communication": {
            "channel": Channel.EMAIL,
            "recipient": "finance@acme.corp",
            "subject": "Payment Link for Invoice #INV-2024-001",
            "body": "Thank you for confirming. You can settle the full balance of $5,000.00 via our secure payment portal here: https://pay.revpulse.io/inv-2024-001. Please reply with the receipt once completed.",
        },
        "proposed_settlement": None,
        "dispute_details": None,
        "internal_notes": "Customer confirmed intent to pay full balance today. Payment link provided.",
    }

    parsed = RevPulseAgentResponse.model_validate(response_data)
    assert parsed.intent == Intent.FULL_PAYMENT_PROMISED
    assert parsed.action_required == ActionRequired.SEND_PAYMENT_LINK
    assert parsed.risk_level == RiskLevel.LOW
    assert parsed.confidence_score >= 0.9
    assert parsed.proposed_settlement is None
    assert parsed.dispute_details is None
    assert "https://pay.revpulse.io" in parsed.drafted_communication.body


# ============================================================================
# SCENARIO B: Billing Dispute (Deliverable/Work Issue)
# ============================================================================
def test_scenario_b_billing_dispute():
    """Customer raises a dispute regarding incomplete or defective deliverable."""
    response_data = {
        "intent": Intent.BILLING_DISPUTE,
        "action_required": ActionRequired.OPEN_DISPUTE_TICKET,
        "confidence_score": 0.95,
        "risk_level": RiskLevel.MEDIUM,
        "drafted_communication": {
            "channel": Channel.EMAIL,
            "recipient": "operations@globex.com",
            "subject": "Dispute Acknowledgment - Invoice #INV-8821",
            "body": "Thank you for reaching out. We have registered your dispute regarding milestone 2 deliverable defects. Collections have been placed on hold while our accounts team investigates.",
        },
        "proposed_settlement": None,
        "dispute_details": {
            "category": DisputeCategory.DEFECTIVE_WORK,
            "summary": "Customer claims milestone 2 deliverables failed acceptance tests.",
            "requires_invoice_hold": True,
            "requested_documentation": [
                "QA acceptance test failure logs",
                "Original statement of work milestone specification",
            ],
        },
        "internal_notes": "Placed invoice on hold. Ticket #DISP-401 opened for engineering/account review.",
    }

    parsed = RevPulseAgentResponse.model_validate(response_data)
    assert parsed.intent == Intent.BILLING_DISPUTE
    assert parsed.action_required == ActionRequired.OPEN_DISPUTE_TICKET
    assert parsed.dispute_details is not None
    assert parsed.dispute_details.category == DisputeCategory.DEFECTIVE_WORK
    assert parsed.dispute_details.requires_invoice_hold is True
    assert len(parsed.dispute_details.requested_documentation) == 2
    assert parsed.risk_level in [RiskLevel.MEDIUM, RiskLevel.HIGH]


# ============================================================================
# SCENARIO C: Structured Installment Proposal (50/50 Split)
# ============================================================================
def test_scenario_c_installment_proposal():
    """Customer requests payment plan: 50% now, 50% in 30 days."""
    response_data = {
        "intent": Intent.PAYMENT_PLAN_REQUESTED,
        "action_required": ActionRequired.SEND_PAYMENT_PLAN_AGREEMENT,
        "confidence_score": 0.94,
        "risk_level": RiskLevel.MEDIUM,
        "drafted_communication": {
            "channel": Channel.EMAIL,
            "recipient": "treasury@initech.io",
            "subject": "Proposed Payment Plan Agreement - Invoice #INV-3004",
            "body": "We have accepted your request for a 2-part installment plan. Installment 1 ($5,000.00) is due by 2026-09-26, and Installment 2 ($5,000.00) is due by 2026-10-26.",
        },
        "proposed_settlement": {
            "installments_count": 2,
            "total_amount": 10000.00,
            "installments": [
                {"due_date": "2026-09-26", "amount": 5000.00},
                {"due_date": "2026-10-26", "amount": 5000.00},
            ],
        },
        "dispute_details": None,
        "internal_notes": "Approved 2-part installment plan. First payment is 50% (exceeds 33% minimum) and due within 7 days.",
    }

    parsed = RevPulseAgentResponse.model_validate(response_data)
    assert parsed.intent == Intent.PAYMENT_PLAN_REQUESTED
    assert parsed.action_required == ActionRequired.SEND_PAYMENT_PLAN_AGREEMENT
    assert parsed.proposed_settlement is not None
    assert parsed.proposed_settlement.installments_count <= 3
    assert len(parsed.proposed_settlement.installments) == 2
    assert sum(inst.amount for inst in parsed.proposed_settlement.installments) == 10000.00

    # Policy guardrail verification: first installment >= 33%
    first_payment = parsed.proposed_settlement.installments[0].amount
    total = parsed.proposed_settlement.total_amount
    assert (first_payment / total) >= 0.33


# ============================================================================
# SCENARIO D: Schema Validation & Guardrail Rejection Tests
# ============================================================================
def test_schema_rejection_more_than_three_installments():
    """Validation must fail if installments_count exceeds policy maximum of 3."""
    with pytest.raises(ValidationError) as excinfo:
        ProposedSettlement(
            installments_count=4,
            total_amount=1000.0,
            installments=[
                Installment(due_date="2026-10-01", amount=250.0),
                Installment(due_date="2026-10-15", amount=250.0),
                Installment(due_date="2026-11-01", amount=250.0),
                Installment(due_date="2026-11-15", amount=250.0),
            ],
        )
    assert "Input should be less than or equal to 3" in str(excinfo.value)


def test_schema_rejection_mismatched_installments_count():
    """Validation must fail if installments length does not match installments_count."""
    with pytest.raises(ValidationError) as excinfo:
        ProposedSettlement(
            installments_count=2,
            total_amount=1000.0,
            installments=[
                Installment(due_date="2026-10-01", amount=500.0),
            ],
        )
    assert "Number of installments (1) must match installments_count (2)" in str(excinfo.value)


def test_schema_rejection_negative_amount():
    """Validation must fail on negative or zero installment amounts."""
    with pytest.raises(ValidationError):
        Installment(due_date="2026-10-01", amount=-50.0)

    with pytest.raises(ValidationError):
        Installment(due_date="2026-10-01", amount=0.0)


def test_schema_rejection_invalid_confidence_score():
    """Confidence score must strictly be between 0.0 and 1.0."""
    valid_comm = CommunicationDraft(
        channel=Channel.SMS,
        recipient="+15551234567",
        body="Please pay your bill",
    )
    with pytest.raises(ValidationError):
        RevPulseAgentResponse(
            intent=Intent.FULL_PAYMENT_PROMISED,
            action_required=ActionRequired.SEND_PAYMENT_LINK,
            confidence_score=1.5,  # > 1.0 invalid
            risk_level=RiskLevel.LOW,
            drafted_communication=valid_comm,
            internal_notes="Invalid confidence",
        )


def test_schema_rejection_invalid_enum_value():
    """Unrecognized intents or action_required strings must be rejected."""
    with pytest.raises(ValidationError):
        RevPulseAgentResponse(
            intent="INVALID_INTENT_NAME",  # Not in Intent Enum
            action_required=ActionRequired.SEND_PAYMENT_LINK,
            confidence_score=0.9,
            risk_level=RiskLevel.LOW,
            drafted_communication=CommunicationDraft(
                channel=Channel.EMAIL,
                recipient="test@example.com",
                body="test",
            ),
            internal_notes="Test invalid enum",
        )


# ============================================================================
# SCENARIO E: RevPulseAIEngine Wrapper Integration & Mock Execution
# ============================================================================
def test_ai_engine_analyze_interaction_with_parsed_response():
    """Test AI Engine returns strongly-typed RevPulseAgentResponse from Gemini client."""
    mock_gemini_client = MagicMock()

    expected_agent_response = RevPulseAgentResponse(
        intent=Intent.FULL_PAYMENT_PROMISED,
        action_required=ActionRequired.SEND_PAYMENT_LINK,
        confidence_score=0.99,
        risk_level=RiskLevel.LOW,
        drafted_communication=CommunicationDraft(
            channel=Channel.WHATSAPP,
            recipient="+1234567890",
            body="Hello! Here is your link to settle invoice #101: https://pay.revpulse.io/101",
        ),
        internal_notes="Customer confirmed full settlement via WhatsApp.",
    )

    # Mock Gemini SDK response
    mock_model_response = MagicMock()
    mock_model_response.parsed = expected_agent_response
    mock_gemini_client.models.generate_content.return_value = mock_model_response

    engine = RevPulseAIEngine(
        api_key="dummy-key",
        model_name="gemini-2.5-flash",
        client=mock_gemini_client,
    )

    result = engine.analyze_interaction(
        customer_input="I'll pay the invoice right away, please send the link.",
        invoice_context={"invoice_id": "INV-101", "amount_due": 1500.0},
        channel="WHATSAPP",
    )

    assert isinstance(result, RevPulseAgentResponse)
    assert result.intent == Intent.FULL_PAYMENT_PROMISED
    assert result.action_required == ActionRequired.SEND_PAYMENT_LINK
    assert result.drafted_communication.channel == Channel.WHATSAPP
    mock_gemini_client.models.generate_content.assert_called_once()


def test_ai_engine_analyze_interaction_json_fallback():
    """Test AI Engine falls back to parsing JSON text if parsed field is empty."""
    mock_gemini_client = MagicMock()

    raw_json_str = """
    {
      "intent": "BILLING_DISPUTE",
      "action_required": "OPEN_DISPUTE_TICKET",
      "confidence_score": 0.91,
      "risk_level": "HIGH",
      "drafted_communication": {
        "channel": "EMAIL",
        "recipient": "client@enterprise.com",
        "subject": "Dispute Registration",
        "body": "We have halted automated reminders while investigating."
      },
      "dispute_details": {
        "category": "INCORRECT_PRICING",
        "summary": "Billed rate was $150/hr instead of contracted $120/hr.",
        "requires_invoice_hold": true,
        "requested_documentation": ["Contract Addendum A"]
      },
      "internal_notes": "Pricing discrepancy escalated."
    }
    """

    mock_model_response = MagicMock()
    mock_model_response.parsed = None
    mock_model_response.text = raw_json_str
    mock_gemini_client.models.generate_content.return_value = mock_model_response

    engine = RevPulseAIEngine(
        api_key="dummy-key",
        client=mock_gemini_client,
    )

    result = engine.analyze_interaction(
        customer_input="You overbilled us by $30/hr on this invoice.",
        invoice_context={"invoice_id": "INV-500", "amount_due": 3000.0},
        channel="EMAIL",
    )

    assert isinstance(result, RevPulseAgentResponse)
    assert result.intent == Intent.BILLING_DISPUTE
    assert result.dispute_details.category == DisputeCategory.INCORRECT_PRICING
    assert result.dispute_details.requires_invoice_hold is True


def test_ai_engine_model_fallback_on_server_error(monkeypatch):
    """Test that ai_engine falls back to secondary model when primary fails with ServerError."""
    from google.genai import errors
    from tenacity import wait_none

    mock_gemini_client = MagicMock()

    expected_agent_response = RevPulseAgentResponse(
        intent=Intent.FULL_PAYMENT_PROMISED,
        action_required=ActionRequired.SEND_PAYMENT_LINK,
        confidence_score=0.95,
        risk_level=RiskLevel.LOW,
        drafted_communication=CommunicationDraft(
            channel=Channel.EMAIL,
            recipient="test@example.com",
            body="Payment link: https://pay.revpulse.io/fallback",
        ),
        internal_notes="Processed via fallback model.",
    )

    fallback_model_response = MagicMock()
    fallback_model_response.parsed = expected_agent_response

    def mock_generate_content(model, contents, config):
        if model == "gemini-3.6-flash":
            raise errors.ServerError(503, "Service Unavailable")
        elif model == "gemini-3.1-pro-preview":
            return fallback_model_response
        raise RuntimeError("Unexpected model called")

    mock_gemini_client.models.generate_content.side_effect = mock_generate_content

    engine = RevPulseAIEngine(
        api_key="dummy-key",
        model_name="gemini-3.6-flash",
        client=mock_gemini_client,
    )

    monkeypatch.setattr("src.services.ai_engine.wait_exponential", lambda **kwargs: wait_none())

    result = engine.analyze_interaction(
        customer_input="I'll pay today",
        invoice_context={"invoice_id": "INV-FALLBACK", "amount_due": 1000.0},
        channel="EMAIL",
    )

    assert isinstance(result, RevPulseAgentResponse)
    assert result.intent == Intent.FULL_PAYMENT_PROMISED
    assert result.internal_notes == "Processed via fallback model."


def test_ai_engine_heuristic_fallback_when_all_models_fail(monkeypatch):
    """Test that ai_engine falls back to heuristic rule-based parsing when all models fail."""
    from google.genai import errors
    from tenacity import wait_none

    mock_gemini_client = MagicMock()
    mock_gemini_client.models.generate_content.side_effect = errors.ServerError(503, "Service Unavailable")

    engine = RevPulseAIEngine(
        api_key="dummy-key",
        model_name="gemini-3.6-flash",
        client=mock_gemini_client,
    )

    monkeypatch.setattr("src.services.ai_engine.wait_exponential", lambda **kwargs: wait_none())

    # Case 1: Defective work dispute
    result_dispute = engine.analyze_interaction(
        customer_input="There are severe cracks in the concrete and defective work, we are not paying until repaired.",
        invoice_context={"invoice_id": "INV-CRACK", "amount_due": 5000.0},
        channel="EMAIL",
    )
    assert result_dispute.intent == Intent.BILLING_DISPUTE
    assert result_dispute.action_required == ActionRequired.OPEN_DISPUTE_TICKET
    assert result_dispute.dispute_details.requires_invoice_hold is True

    # Case 2: Payment plan request
    result_plan = engine.analyze_interaction(
        customer_input="Cash flow is tight, can we split this into two installments?",
        invoice_context={"invoice_id": "INV-PLAN", "amount_due": 4000.0},
        channel="EMAIL",
    )
    assert result_plan.intent == Intent.PAYMENT_PLAN_REQUESTED
    assert result_plan.action_required == ActionRequired.SEND_PAYMENT_PLAN_AGREEMENT
    assert result_plan.proposed_settlement.installments_count == 2
    assert result_plan.proposed_settlement.installments[0].amount == 2000.0


