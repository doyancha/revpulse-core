"""
Inbound communication coordinator running the autonomous recovery loop:
Inbound Message -> State Fetch -> AI Decision -> Guardrails Check -> Action Execution -> State Update -> Audit Log.
"""

from typing import Any, Dict, Optional

from src.schemas.agent_schema import (
    ActionRequired,
    Channel,
    CommunicationDraft,
    Intent,
    RevPulseAgentResponse,
    RiskLevel,
)
from src.schemas.audit_schema import EscalationReason
from src.schemas.conversation_schema import (
    ChannelType,
    ConversationStatus,
    MessageRole,
)
from src.services.ai_engine import RevPulseAIEngine
from src.services.audit_logger import AuditLogger
from src.services.escalation_manager import HumanEscalationManager
from src.services.guardrails import ComplianceGuardrailsEngine
from src.services.payment_gateway import PaymentGatewayService
from src.services.state_manager import ConversationStateManager


class RecoveryLoopCoordinator:
    """
    Coordinates multi-turn conversational recovery loop:
    1. Ingestion of inbound messages across channels (WhatsApp, SMS, Email).
    2. Context assembly with multi-turn message history.
    3. AI Engine decisioning & guardrail verification.
    4. Compliance guardrails evaluation (legal threats, bankruptcy, abuse, low confidence).
    5. Manager handoff alerting & automated dunning freeze on escalation.
    6. Automated payment link generation or dispute ticket creation.
    7. Conversation state update & response preparation.
    8. Immutable audit log recording.
    """

    def __init__(
        self,
        ai_engine: Optional[RevPulseAIEngine] = None,
        state_manager: Optional[ConversationStateManager] = None,
        payment_gateway: Optional[PaymentGatewayService] = None,
        guardrails: Optional[ComplianceGuardrailsEngine] = None,
        audit_logger: Optional[AuditLogger] = None,
        escalation_manager: Optional[HumanEscalationManager] = None,
    ):
        self.ai_engine = ai_engine or RevPulseAIEngine()
        self.state_manager = state_manager or ConversationStateManager()
        self.payment_gateway = payment_gateway or PaymentGatewayService()
        self.guardrails = guardrails or ComplianceGuardrailsEngine()
        self.audit_logger = audit_logger or AuditLogger()
        self.escalation_manager = escalation_manager or HumanEscalationManager()

    def process_inbound_message(
        self,
        conversation_id: str,
        invoice_context: Dict[str, Any],
        customer_text: str,
        channel: ChannelType = ChannelType.EMAIL,
    ) -> Dict[str, Any]:
        """
        Executes a single conversational recovery turn with full guardrails and audit trail.
        """
        invoice_id = invoice_context.get("invoice_id", "UNKNOWN_INV")
        customer_id = invoice_context.get("customer_id", "UNKNOWN_CUST")

        # 1. Fetch or initialize conversation state
        state = self.state_manager.get_or_create_state(
            conversation_id=conversation_id,
            invoice_id=invoice_id,
            customer_id=customer_id,
            channel=channel,
        )

        # 2. Append customer message to state history
        self.state_manager.append_message(
            conversation_id=conversation_id,
            role=MessageRole.CUSTOMER,
            content=customer_text,
            channel=channel,
        )

        # 3. Log inbound message event to AuditLogger
        self.audit_logger.log_event(
            event_type="INBOUND_MESSAGE",
            invoice_id=invoice_id,
            customer_id=customer_id,
            channel=channel.value,
            raw_input=customer_text,
            metadata={"turn_count": state.turn_count},
        )

        # 4. Fast pre-AI compliance check (Legal threats, Bankruptcy, Abusive language)
        # Immediately freeze automated loop without invoking Gemini
        current_transcript = [
            {"role": msg.role.value, "content": msg.content, "channel": msg.channel.value}
            for msg in state.history
        ]
        pre_ai_alert = self.guardrails.check_raw_text(
            customer_text=customer_text,
            invoice_id=invoice_id,
            customer_id=customer_id,
            transcript=current_transcript,
        )

        if pre_ai_alert:
            self.state_manager.set_status(conversation_id, ConversationStatus.ESCALATED.value)
            alert_dispatch = self.escalation_manager.dispatch_manager_alert(pre_ai_alert)

            self.audit_logger.log_event(
                event_type="HUMAN_ESCALATED",
                invoice_id=invoice_id,
                customer_id=customer_id,
                channel=channel.value,
                raw_input=customer_text,
                response_summary=pre_ai_alert.summary,
                escalation_reason=pre_ai_alert.reason,
                metadata={"alert_dispatch": alert_dispatch, "pre_ai_check": True},
            )

            escalation_draft = CommunicationDraft(
                channel=Channel(channel.value),
                recipient=invoice_context.get("recipient_contact", {}).get(
                    "email", "customer@example.com"
                ),
                subject=f"Notice Regarding Invoice #{invoice_id}",
                body=(
                    "Thank you for your response. Automated collection communications on this invoice have been paused. "
                    "A senior accounts specialist has been assigned to personally review your file and will follow up with you directly."
                ),
            )

            self.state_manager.append_message(
                conversation_id=conversation_id,
                role=MessageRole.AGENT,
                content=escalation_draft.body,
                channel=channel,
            )

            return {
                "conversation_id": conversation_id,
                "invoice_id": invoice_id,
                "intent": Intent.HUMAN_ESCALATION.value,
                "action_required": ActionRequired.FLAG_HUMAN_REVIEW.value,
                "risk_level": RiskLevel.CRITICAL.value,
                "confidence_score": 1.0,
                "outbound_draft": escalation_draft.model_dump(),
                "executed_actions": {"escalation_alert": alert_dispatch},
                "state_status": ConversationStatus.ESCALATED.value,
                "turn_count": state.turn_count,
                "escalation_reason": pre_ai_alert.reason.value,
            }

        # 5. Enhance invoice context with past conversation history
        enriched_context = dict(invoice_context)
        history_transcript = [
            {"role": msg.role.value, "content": msg.content, "channel": msg.channel.value}
            for msg in state.history[:-1]  # history prior to current message
        ]
        enriched_context["conversation_history"] = history_transcript
        enriched_context["turn_count"] = state.turn_count

        # 6. Invoke AI Engine for decisioning
        agent_response: RevPulseAgentResponse = self.ai_engine.analyze_interaction(
            customer_input=customer_text,
            invoice_context=enriched_context,
            channel=channel.value,
        )

        # 7. Post-AI Evaluation (Low confidence, explicit model escalation)
        escalation_alert = self.guardrails.evaluate_for_escalation(
            customer_text=customer_text,
            ai_response=agent_response,
            invoice_id=invoice_id,
            customer_id=customer_id,
            turn_count=state.turn_count,
            transcript=current_transcript,
        )

        # If post-AI escalation trigger is tripped:
        if escalation_alert:
            # Freeze automated loop, mark state as ESCALATED
            self.state_manager.set_status(conversation_id, ConversationStatus.ESCALATED.value)
            alert_dispatch = self.escalation_manager.dispatch_manager_alert(escalation_alert)

            # Log HUMAN_ESCALATED event in AuditLogger
            self.audit_logger.log_event(
                event_type="HUMAN_ESCALATED",
                invoice_id=invoice_id,
                customer_id=customer_id,
                channel=channel.value,
                raw_input=customer_text,
                response_summary=escalation_alert.summary,
                escalation_reason=escalation_alert.reason,
                metadata={"alert_dispatch": alert_dispatch, "pre_ai_check": False},
            )


            # Empathetic, relationship-preserving acknowledgment
            escalation_draft = CommunicationDraft(
                channel=Channel(channel.value),
                recipient=invoice_context.get("recipient_contact", {}).get(
                    "email", "customer@example.com"
                ),
                subject=f"Notice Regarding Invoice #{invoice_id}",
                body=(
                    "Thank you for your response. Automated collection communications on this invoice have been paused. "
                    "A senior accounts specialist has been assigned to personally review your file and will follow up with you directly."
                ),
            )

            # Append agent notice to state
            self.state_manager.append_message(
                conversation_id=conversation_id,
                role=MessageRole.AGENT,
                content=escalation_draft.body,
                channel=channel,
            )

            return {
                "conversation_id": conversation_id,
                "invoice_id": invoice_id,
                "intent": Intent.HUMAN_ESCALATION.value,
                "action_required": ActionRequired.FLAG_HUMAN_REVIEW.value,
                "risk_level": RiskLevel.CRITICAL.value,
                "confidence_score": agent_response.confidence_score,
                "outbound_draft": escalation_draft.model_dump(),
                "executed_actions": {"escalation_alert": alert_dispatch},
                "state_status": ConversationStatus.ESCALATED.value,
                "turn_count": state.turn_count,
                "escalation_reason": escalation_alert.reason.value,
            }

        # 7. Normal Action Execution if not escalated
        executed_actions: Dict[str, Any] = {}

        # Case A: Full Payment promised or payment link required
        if (
            agent_response.intent == Intent.FULL_PAYMENT_PROMISED
            or agent_response.action_required == ActionRequired.SEND_PAYMENT_LINK
        ):
            balance = invoice_context.get("financial_summary", {}).get(
                "balance_due", invoice_context.get("amount_due", 0.0)
            )
            pay_link = self.payment_gateway.create_payment_link(
                invoice_id=invoice_id,
                amount=balance,
                customer_id=customer_id,
                description=f"Full payment for invoice {invoice_id}",
            )
            executed_actions["payment_link"] = pay_link
            self.audit_logger.log_event(
                event_type="PAYMENT_GENERATED",
                invoice_id=invoice_id,
                customer_id=customer_id,
                channel=channel.value,
                response_summary=f"Payment link generated for ${balance:,.2f}",
                metadata={"payment_link": pay_link},
            )

            if "{{payment_link}}" in agent_response.drafted_communication.body:
                agent_response.drafted_communication.body = (
                    agent_response.drafted_communication.body.replace(
                        "{{payment_link}}", pay_link["url"]
                    )
                )

        # Case B: Payment plan requested and settlement structured
        elif (
            agent_response.intent == Intent.PAYMENT_PLAN_REQUESTED
            and agent_response.proposed_settlement
        ):
            settlement = agent_response.proposed_settlement
            first_inst = settlement.installments[0]
            first_payment_link = self.payment_gateway.create_payment_link(
                invoice_id=invoice_id,
                amount=first_inst.amount,
                customer_id=customer_id,
                description=f"Installment 1 of {settlement.installments_count} for invoice {invoice_id}",
                installment_index=1,
            )
            executed_actions["first_installment_link"] = first_payment_link
            executed_actions["installment_schedule"] = settlement.model_dump()
            self.audit_logger.log_event(
                event_type="PAYMENT_GENERATED",
                invoice_id=invoice_id,
                customer_id=customer_id,
                channel=channel.value,
                response_summary=f"Structured payment plan ({settlement.installments_count} splits) generated",
                metadata={"settlement": settlement.model_dump()},
            )

        # Case C: Billing Dispute
        elif (
            agent_response.intent == Intent.BILLING_DISPUTE
            or agent_response.action_required == ActionRequired.OPEN_DISPUTE_TICKET
        ):
            ticket_id = f"TICK-DISP-{invoice_id}"
            executed_actions["dispute_ticket"] = {
                "ticket_id": ticket_id,
                "invoice_id": invoice_id,
                "customer_id": customer_id,
                "details": agent_response.dispute_details.model_dump()
                if agent_response.dispute_details
                else {},
                "status": "OPEN",
                "invoice_hold_active": True,
            }
            self.audit_logger.log_event(
                event_type="DISPUTE_OPENED",
                invoice_id=invoice_id,
                customer_id=customer_id,
                channel=channel.value,
                response_summary=f"Dispute ticket opened: {ticket_id}",
                metadata={"dispute_ticket": executed_actions["dispute_ticket"]},
            )

        # 8. Record AI_DECISION event into AuditLogger
        self.audit_logger.log_event(
            event_type="AI_DECISION",
            invoice_id=invoice_id,
            customer_id=customer_id,
            channel=channel.value,
            response_summary=agent_response.drafted_communication.body[:150],
            metadata={
                "intent": agent_response.intent.value,
                "action_required": agent_response.action_required.value,
                "confidence_score": agent_response.confidence_score,
                "risk_level": agent_response.risk_level.value,
            },
        )

        # 9. Update conversation state with AI response and executed action
        updated_state = self.state_manager.update_state_with_response(
            conversation_id=conversation_id,
            agent_response=agent_response,
        )

        return {
            "conversation_id": conversation_id,
            "invoice_id": invoice_id,
            "intent": agent_response.intent.value,
            "action_required": agent_response.action_required.value,
            "risk_level": agent_response.risk_level.value,
            "confidence_score": agent_response.confidence_score,
            "outbound_draft": agent_response.drafted_communication.model_dump(),
            "executed_actions": executed_actions,
            "state_status": updated_state.status,
            "turn_count": updated_state.turn_count,
        }
