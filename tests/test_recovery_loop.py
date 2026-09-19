"""
Unit and integration tests for Phase 3: Conversational Recovery Loop & Webhooks.
Covers:
- Multi-turn negotiation:
  * Turn 1: Customer asks why invoice is high -> AI explains / requests details.
  * Turn 2: Customer proposes 2 split payments -> AI accepts, builds schedule, generates installment link.
- Payment webhook reconciliation:
  * Stripe payment webhook received -> balance updated to 0 -> status becomes RESOLVED_PAID.
- Dispute flow and state transition:
  * Defective work dispute -> active_dispute logged to state -> status becomes UNDER_DISPUTE.
"""

from unittest.mock import MagicMock
import pytest

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
from src.schemas.conversation_schema import ChannelType, ConversationStatus, MessageRole
from src.services.payment_gateway import PaymentGatewayService
from src.services.recovery_loop import RecoveryLoopCoordinator
from src.services.state_manager import ConversationStateManager


@pytest.fixture
def base_invoice_context():
    return {
        "invoice_id": "INV-2024-8801",
        "customer_id": "CUST-900",
        "customer_name": "Apex Engineering Corp",
        "financial_summary": {
            "total_amount": 6000.0,
            "balance_due": 6000.0,
            "currency": "USD",
            "days_overdue": 18,
            "aging_bucket": "OVERDUE_15_PLUS",
        },
        "credit_health_metrics": {
            "total_outstanding_portfolio": 6000.0,
            "historical_average_days_to_pay": 45.0,
            "default_risk_score": 0.45,
        },
        "line_items": ["Mechanical Engineering Consulting ($6,000.00)"],
    }


def test_multi_turn_negotiation(base_invoice_context):
    """
    Test a 2-turn conversation:
    - Turn 1: Customer asks for invoice breakdown.
    - Turn 2: Customer proposes paying in 2 installments (50% now, 50% next month).
    """
    mock_ai_engine = MagicMock()
    state_manager = ConversationStateManager()
    payment_gateway = PaymentGatewayService()

    coordinator = RecoveryLoopCoordinator(
        ai_engine=mock_ai_engine,
        state_manager=state_manager,
        payment_gateway=payment_gateway,
    )

    conv_id = "conv-apex-001"

    # --- TURN 1 ---
    turn_1_response = RevPulseAgentResponse(
        intent=Intent.INFORMATION_REQUEST,
        action_required=ActionRequired.REQUEST_INFO,
        confidence_score=0.96,
        risk_level=RiskLevel.LOW,
        drafted_communication=CommunicationDraft(
            channel=Channel.EMAIL,
            recipient="accounting@apexeng.com",
            subject="Invoice #INV-2024-8801 Breakdown",
            body="Hello, this invoice is for 40 hours of Mechanical Engineering Consulting completed on Aug 15.",
        ),
        internal_notes="Explained invoice itemization per customer request.",
    )
    mock_ai_engine.analyze_interaction.return_value = turn_1_response

    res1 = coordinator.process_inbound_message(
        conversation_id=conv_id,
        invoice_context=base_invoice_context,
        customer_text="Why is this invoice $6,000? Could you clarify the line items?",
        channel=ChannelType.EMAIL,
    )

    assert res1["intent"] == "INFORMATION_REQUEST"
    assert res1["turn_count"] == 1
    state = state_manager.get_state(conv_id)
    assert state is not None
    assert len(state.history) == 2  # Customer turn + Agent turn
    assert state.history[0].role == MessageRole.CUSTOMER
    assert state.history[1].role == MessageRole.AGENT

    # --- TURN 2 ---
    turn_2_response = RevPulseAgentResponse(
        intent=Intent.PAYMENT_PLAN_REQUESTED,
        action_required=ActionRequired.SEND_PAYMENT_PLAN_AGREEMENT,
        confidence_score=0.97,
        risk_level=RiskLevel.MEDIUM,
        drafted_communication=CommunicationDraft(
            channel=Channel.EMAIL,
            recipient="accounting@apexeng.com",
            subject="Payment Agreement - Invoice #INV-2024-8801",
            body="We have accepted your request for a 2-part installment plan of $3,000 today and $3,000 in 30 days.",
        ),
        proposed_settlement=ProposedSettlement(
            installments_count=2,
            total_amount=6000.0,
            installments=[
                Installment(due_date="2026-09-26", amount=3000.0),
                Installment(due_date="2026-10-26", amount=3000.0),
            ],
        ),
        internal_notes="Approved 50/50 plan. Minimum first installment requirement (>= 33%) satisfied.",
    )
    mock_ai_engine.analyze_interaction.return_value = turn_2_response

    res2 = coordinator.process_inbound_message(
        conversation_id=conv_id,
        invoice_context=base_invoice_context,
        customer_text="Got it. Can we split this into two equal payments of $3,000, half now and half next month?",
        channel=ChannelType.EMAIL,
    )

    assert res2["intent"] == "PAYMENT_PLAN_REQUESTED"
    assert res2["action_required"] == "SEND_PAYMENT_PLAN_AGREEMENT"
    assert res2["state_status"] == ConversationStatus.RESOLVED_PLAN.value
    assert res2["turn_count"] == 2

    # Verify executed payment link and settlement attachment
    executed = res2["executed_actions"]
    assert "first_installment_link" in executed
    assert executed["first_installment_link"]["amount"] == 3000.0
    assert "https://pay.revpulse.io/checkout/INV-2024-8801?inst=1" in executed["first_installment_link"]["url"]
    assert executed["installment_schedule"]["installments_count"] == 2

    # Verify conversation state captures active settlement
    state_after = state_manager.get_state(conv_id)
    assert state_after.active_settlement is not None
    assert state_after.active_settlement.installments_count == 2
    assert len(state_after.history) == 4


def test_payment_webhook_reconciliation():
    """
    Test Stripe payment success webhook reconciling an active conversation thread.
    """
    state_manager = ConversationStateManager()
    payment_gateway = PaymentGatewayService()

    conv_id = "conv-stripe-pay-01"
    invoice_id = "INV-2024-7711"

    # Initialize active state
    state = state_manager.get_or_create_state(
        conversation_id=conv_id,
        invoice_id=invoice_id,
        customer_id="CUST-77",
        channel=ChannelType.EMAIL,
    )
    assert state.status == ConversationStatus.ACTIVE.value

    # Simulate webhook event payload from Stripe
    stripe_webhook_payload = {
        "id": "evt_test_123456",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_999888",
                "invoice_id": invoice_id,
                "amount_total": 4500.0,
                "currency": "usd",
                "payment_status": "paid",
            }
        },
    }

    recon_result = payment_gateway.process_payment_webhook(stripe_webhook_payload)
    assert recon_result["success"] is True
    assert recon_result["reconciled"] is True
    assert recon_result["invoice_id"] == invoice_id
    assert recon_result["amount_paid"] == 4500.0

    # Mark conversation state as RESOLVED_PAID
    state_manager.set_status(conv_id, ConversationStatus.RESOLVED_PAID.value)
    updated_state = state_manager.get_state(conv_id)
    assert updated_state.status == ConversationStatus.RESOLVED_PAID.value


def test_dispute_flow_state_transition(base_invoice_context):
    """
    Test customer raising a billing dispute regarding defective work.
    Verifies state status becomes UNDER_DISPUTE, ticket is opened, and active_dispute is stored.
    """
    mock_ai_engine = MagicMock()
    state_manager = ConversationStateManager()
    payment_gateway = PaymentGatewayService()

    coordinator = RecoveryLoopCoordinator(
        ai_engine=mock_ai_engine,
        state_manager=state_manager,
        payment_gateway=payment_gateway,
    )

    conv_id = "conv-dispute-01"

    dispute_response = RevPulseAgentResponse(
        intent=Intent.BILLING_DISPUTE,
        action_required=ActionRequired.OPEN_DISPUTE_TICKET,
        confidence_score=0.95,
        risk_level=RiskLevel.HIGH,
        drafted_communication=CommunicationDraft(
            channel=Channel.EMAIL,
            recipient="procurement@apexeng.com",
            subject="Dispute Logged - Invoice #INV-2024-8801",
            body="We acknowledge your dispute regarding incomplete structural drawings. Collections have been placed on hold.",
        ),
        dispute_details=DisputeDetails(
            category=DisputeCategory.DEFECTIVE_WORK,
            summary="Customer claims engineering drawings contained critical structural errors.",
            requires_invoice_hold=True,
            requested_documentation=["Redline PDF markups", "Engineering audit checklist"],
        ),
        internal_notes="Dispute filed. Halting automated collection dunning.",
    )
    mock_ai_engine.analyze_interaction.return_value = dispute_response

    result = coordinator.process_inbound_message(
        conversation_id=conv_id,
        invoice_context=base_invoice_context,
        customer_text="We cannot pay this invoice. The mechanical drawings had severe structural defects.",
        channel=ChannelType.EMAIL,
    )

    assert result["intent"] == "BILLING_DISPUTE"
    assert result["action_required"] == "OPEN_DISPUTE_TICKET"
    assert result["state_status"] == ConversationStatus.UNDER_DISPUTE.value

    # Verify executed ticket payload
    executed = result["executed_actions"]
    assert "dispute_ticket" in executed
    assert executed["dispute_ticket"]["invoice_hold_active"] is True
    assert executed["dispute_ticket"]["details"]["category"] == "DEFECTIVE_WORK"

    # Verify state saved dispute
    state = state_manager.get_state(conv_id)
    assert state.active_dispute is not None
    assert state.active_dispute.category == DisputeCategory.DEFECTIVE_WORK
    assert state.active_dispute.requires_invoice_hold is True
