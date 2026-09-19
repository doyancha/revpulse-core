"""
Smoke and programmatic tests for cli_runner.py.
Verifies fixture loading, invoice tables, and non-interactive simulation execution.
"""

from unittest.mock import MagicMock
import pytest

from cli_runner import (
    load_all_fixtures,
    display_invoice_table,
    display_audit_trail,
    run_cli_session,
)
from src.schemas.agent_schema import (
    ActionRequired,
    Channel,
    CommunicationDraft,
    Intent,
    RevPulseAgentResponse,
    RiskLevel,
)
from src.schemas.conversation_schema import ChannelType
from src.services.audit_logger import AuditLogger
from src.services.payment_gateway import PaymentGatewayService
from src.services.recovery_loop import RecoveryLoopCoordinator
from src.services.state_manager import ConversationStateManager


def test_load_all_fixtures():
    """Verify load_all_fixtures successfully imports and normalizes invoices."""
    invoices = load_all_fixtures()
    assert len(invoices) >= 5
    ids = [inv.invoice_id for inv in invoices]
    assert any("QBO" in i for i in ids)
    assert any("XERO" in i for i in ids)


def test_display_helpers():
    """Verify table rendering functions execute without exceptions."""
    invoices = load_all_fixtures()
    display_invoice_table(invoices[:2])

    audit_logger = AuditLogger()
    audit_logger.log_event(
        event_type="INBOUND_MESSAGE",
        invoice_id="INV-TEST",
        customer_id="CUST-TEST",
        channel="WHATSAPP",
        raw_input="Test message",
    )
    display_audit_trail(audit_logger, "INV-TEST")


def test_cli_runner_non_interactive():
    """Verify run_cli_session executes cleanly in non-interactive mode."""
    invoices = load_all_fixtures()
    run_cli_session(invoices=invoices, interactive=False)


def test_cli_programmatic_turn():
    """
    Test programmatic execution of a conversation turn using the CLI's coordinator setup.
    """
    invoices = load_all_fixtures()
    selected_inv = invoices[0]

    mock_ai = MagicMock()
    mock_ai.analyze_interaction.return_value = RevPulseAgentResponse(
        intent=Intent.FULL_PAYMENT_PROMISED,
        action_required=ActionRequired.SEND_PAYMENT_LINK,
        confidence_score=0.99,
        risk_level=RiskLevel.LOW,
        drafted_communication=CommunicationDraft(
            channel=Channel.WHATSAPP,
            recipient="+15551234567",
            body="Here is your payment link: {{payment_link}}",
        ),
        internal_notes="Full payment confirmed in simulation test.",
    )

    state_manager = ConversationStateManager()
    audit_logger = AuditLogger()
    payment_gateway = PaymentGatewayService()

    coordinator = RecoveryLoopCoordinator(
        ai_engine=mock_ai,
        state_manager=state_manager,
        audit_logger=audit_logger,
        payment_gateway=payment_gateway,
    )

    conv_id = f"sim_test_{selected_inv.invoice_id}"
    context = {
        "invoice_id": selected_inv.invoice_id,
        "customer_id": selected_inv.customer.customer_id,
        "financial_summary": {
            "balance_due": selected_inv.balance_due,
            "days_overdue": selected_inv.days_overdue,
        },
    }

    result = coordinator.process_inbound_message(
        conversation_id=conv_id,
        invoice_context=context,
        customer_text="I will pay the bill right now.",
        channel=ChannelType.WHATSAPP,
    )

    assert result["intent"] == "FULL_PAYMENT_PROMISED"
    assert "payment_link" in result["executed_actions"]
    assert "https://pay.revpulse.io/checkout/" in result["outbound_draft"]["body"]

    # Verify audit trail has 3 events (INBOUND_MESSAGE, PAYMENT_GENERATED, AI_DECISION)
    trail = audit_logger.get_invoice_audit_trail(selected_inv.invoice_id)
    assert len(trail) == 3
