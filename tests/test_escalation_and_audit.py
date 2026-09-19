"""
Unit and integration tests for Phase 4: Escalation Triggers, Audit Logging & Human Handoff.
Covers:
1. Legal threat escalation:
   - Inbound: "Don't contact us again or our corporate lawyer will file an injunction."
   - Verifies EscalationReason == LEGAL_THREAT, state becomes ESCALATED, and manager alert is produced.
2. Bankruptcy / Insolvency escalation:
   - Inbound: "Our company filed for Chapter 11 bankruptcy this morning."
   - Verifies EscalationReason == INSOLVENCY_BANKRUPTCY, dunning frozen.
3. Audit trail integrity:
   - Verifies complete sequence of AuditLogEntry events across a multi-turn lifecycle.
4. Low confidence score escalation:
   - AI response with confidence_score = 0.50 triggers LOW_CONFIDENCE_SCORE escalation.
"""

from unittest.mock import MagicMock
import pytest

from src.schemas.agent_schema import (
    ActionRequired,
    Channel,
    CommunicationDraft,
    Intent,
    RevPulseAgentResponse,
    RiskLevel,
)
from src.schemas.audit_schema import EscalationReason
from src.schemas.conversation_schema import ChannelType, ConversationStatus
from src.services.audit_logger import AuditLogger
from src.services.escalation_manager import HumanEscalationManager
from src.services.guardrails import ComplianceGuardrailsEngine
from src.services.payment_gateway import PaymentGatewayService
from src.services.recovery_loop import RecoveryLoopCoordinator
from src.services.state_manager import ConversationStateManager


@pytest.fixture
def sample_invoice_context():
    return {
        "invoice_id": "INV-9901",
        "customer_id": "CUST-882",
        "customer_name": "Titanium Heavy Machinery",
        "financial_summary": {
            "total_amount": 18500.0,
            "balance_due": 18500.0,
            "currency": "USD",
            "days_overdue": 45,
            "aging_bucket": "OVERDUE_30_PLUS",
        },
        "credit_health_metrics": {
            "total_outstanding_portfolio": 18500.0,
            "historical_average_days_to_pay": 60.0,
            "default_risk_score": 0.70,
        },
        "recipient_contact": {
            "email": "legal@titaniummachinery.com",
            "phone": "+1-312-555-0144",
            "preferred_channel": "EMAIL",
        },
    }


def test_legal_threat_escalation(sample_invoice_context):
    """
    Test customer threatening legal action.
    Asserts EscalationReason == LEGAL_THREAT, state becomes ESCALATED, and manager alert is dispatched.
    """
    mock_ai_engine = MagicMock()
    # Mock AI response if reached
    mock_ai_engine.analyze_interaction.return_value = RevPulseAgentResponse(
        intent=Intent.HUMAN_ESCALATION,
        action_required=ActionRequired.FLAG_HUMAN_REVIEW,
        confidence_score=0.95,
        risk_level=RiskLevel.CRITICAL,
        drafted_communication=CommunicationDraft(
            channel=Channel.EMAIL,
            recipient="legal@titaniummachinery.com",
            body="We have paused communications.",
        ),
        internal_notes="Customer threatened legal action.",
    )

    state_manager = ConversationStateManager()
    audit_logger = AuditLogger()
    escalation_manager = HumanEscalationManager()
    guardrails = ComplianceGuardrailsEngine()

    coordinator = RecoveryLoopCoordinator(
        ai_engine=mock_ai_engine,
        state_manager=state_manager,
        guardrails=guardrails,
        audit_logger=audit_logger,
        escalation_manager=escalation_manager,
    )

    conv_id = "conv-legal-01"
    customer_input = "Don't contact us again or our corporate lawyer will file an injunction in court."

    result = coordinator.process_inbound_message(
        conversation_id=conv_id,
        invoice_context=sample_invoice_context,
        customer_text=customer_input,
        channel=ChannelType.EMAIL,
    )

    # Verifications
    assert result["state_status"] == ConversationStatus.ESCALATED.value
    assert result["escalation_reason"] == EscalationReason.LEGAL_THREAT.value
    assert result["risk_level"] == "CRITICAL"
    assert "escalation_alert" in result["executed_actions"]
    assert result["executed_actions"]["escalation_alert"]["dispatched"] is True

    # Check conversation state in state manager
    state = state_manager.get_state(conv_id)
    assert state.status == ConversationStatus.ESCALATED.value

    # Check audit log trail
    logs = audit_logger.get_invoice_audit_trail("INV-9901")
    event_types = [log.event_type for log in logs]
    assert "INBOUND_MESSAGE" in event_types
    assert "HUMAN_ESCALATED" in event_types
    # Verify AI engine was bypassed for hard compliance trigger
    mock_ai_engine.analyze_interaction.assert_not_called()


def test_bankruptcy_escalation(sample_invoice_context):
    """
    Test customer announcing bankruptcy / chapter 11 filing.
    Asserts EscalationReason == INSOLVENCY_BANKRUPTCY and automated dunning is paused.
    """
    mock_ai_engine = MagicMock()
    mock_ai_engine.analyze_interaction.return_value = RevPulseAgentResponse(
        intent=Intent.HUMAN_ESCALATION,
        action_required=ActionRequired.FLAG_HUMAN_REVIEW,
        confidence_score=0.98,
        risk_level=RiskLevel.CRITICAL,
        drafted_communication=CommunicationDraft(
            channel=Channel.EMAIL,
            recipient="legal@titaniummachinery.com",
            body="Noted.",
        ),
        internal_notes="Chapter 11 filing indicated.",
    )

    state_manager = ConversationStateManager()
    audit_logger = AuditLogger()
    escalation_manager = HumanEscalationManager()
    guardrails = ComplianceGuardrailsEngine()

    coordinator = RecoveryLoopCoordinator(
        ai_engine=mock_ai_engine,
        state_manager=state_manager,
        guardrails=guardrails,
        audit_logger=audit_logger,
        escalation_manager=escalation_manager,
    )

    conv_id = "conv-bankrupt-01"
    customer_input = "Our company filed for Chapter 11 bankruptcy this morning. Please contact our trustee."

    result = coordinator.process_inbound_message(
        conversation_id=conv_id,
        invoice_context=sample_invoice_context,
        customer_text=customer_input,
        channel=ChannelType.EMAIL,
    )

    assert result["state_status"] == ConversationStatus.ESCALATED.value
    assert result["escalation_reason"] == EscalationReason.INSOLVENCY_BANKRUPTCY.value

    # Verify polite, relationship-preserving acknowledgment stating manual follow-up
    assert "senior accounts specialist" in result["outbound_draft"]["body"]
    # Verify AI engine was bypassed for hard compliance trigger
    mock_ai_engine.analyze_interaction.assert_not_called()



def test_low_confidence_escalation(sample_invoice_context):
    """
    Test model low confidence score (< 0.65) triggering human escalation.
    """
    mock_ai_engine = MagicMock()
    mock_ai_engine.analyze_interaction.return_value = RevPulseAgentResponse(
        intent=Intent.INFORMATION_REQUEST,
        action_required=ActionRequired.REQUEST_INFO,
        confidence_score=0.50,  # Below threshold of 0.65
        risk_level=RiskLevel.MEDIUM,
        drafted_communication=CommunicationDraft(
            channel=Channel.EMAIL,
            recipient="info@titaniummachinery.com",
            body="Could you provide more clarity?",
        ),
        internal_notes="Ambiguous customer input.",
    )

    state_manager = ConversationStateManager()
    audit_logger = AuditLogger()
    escalation_manager = HumanEscalationManager()
    guardrails = ComplianceGuardrailsEngine()

    coordinator = RecoveryLoopCoordinator(
        ai_engine=mock_ai_engine,
        state_manager=state_manager,
        guardrails=guardrails,
        audit_logger=audit_logger,
        escalation_manager=escalation_manager,
    )

    conv_id = "conv-low-conf-01"
    customer_input = "Maybe next week, or perhaps we check with our third-party subsidiary overseas."

    result = coordinator.process_inbound_message(
        conversation_id=conv_id,
        invoice_context=sample_invoice_context,
        customer_text=customer_input,
        channel=ChannelType.EMAIL,
    )

    assert result["state_status"] == ConversationStatus.ESCALATED.value
    assert result["escalation_reason"] == EscalationReason.LOW_CONFIDENCE_SCORE.value


def test_audit_trail_integrity(sample_invoice_context):
    """
    Verifies complete sequence of AuditLogEntry events across a multi-turn lifecycle.
    """
    audit_logger = AuditLogger()
    invoice_id = "INV-AUDIT-505"
    cust_id = "CUST-505"

    # Log sequence of events
    e1 = audit_logger.log_event(
        event_type="INBOUND_MESSAGE",
        invoice_id=invoice_id,
        customer_id=cust_id,
        channel="EMAIL",
        raw_input="Can I get a payment link?",
    )
    e2 = audit_logger.log_event(
        event_type="AI_DECISION",
        invoice_id=invoice_id,
        customer_id=cust_id,
        channel="EMAIL",
        response_summary="Payment link issued.",
    )
    e3 = audit_logger.log_event(
        event_type="PAYMENT_GENERATED",
        invoice_id=invoice_id,
        customer_id=cust_id,
        channel="EMAIL",
        response_summary="Checkout URL generated.",
    )
    e4 = audit_logger.log_event(
        event_type="PAYMENT_RECONCILED",
        invoice_id=invoice_id,
        customer_id=cust_id,
        channel="SYSTEM",
        response_summary="Invoice settled via Stripe webhook.",
    )

    trail = audit_logger.get_invoice_audit_trail(invoice_id)
    assert len(trail) == 4
    assert trail[0].event_type == "INBOUND_MESSAGE"
    assert trail[1].event_type == "AI_DECISION"
    assert trail[2].event_type == "PAYMENT_GENERATED"
    assert trail[3].event_type == "PAYMENT_RECONCILED"

    json_export = audit_logger.export_audit_trail_json(invoice_id)
    assert invoice_id in json_export
    assert "PAYMENT_RECONCILED" in json_export
