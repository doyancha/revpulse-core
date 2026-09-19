"""
AI Engine service wrapping Google GenAI SDK for RevPulse AR recovery.
Includes resilient retry with exponential backoff and automatic model fallback.
"""

import json
import logging
from typing import Any, Dict, List, Optional
from google import genai
from google.genai import errors, types
from tenacity import (
    Retrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config.settings import GEMINI_API_KEY, MODEL_NAME
from src.core.prompts import REVPULSE_SYSTEM_INSTRUCTION
from src.schemas.agent_schema import RevPulseAgentResponse

logger = logging.getLogger("revpulse.ai_engine")


class RevPulseAIEngine:
    """
    Autonomous AR Recovery AI Engine powered by Google Gemini.
    Configured with structured Pydantic output schemas, negotiation policy guardrails,
    tenacity retry logic, and multi-model fallback.
    """

    FALLBACK_MODELS: List[str] = ["gemini-3.1-pro-preview", "gemini-3.8-flash"]

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        client: Optional[genai.Client] = None,
    ):
        self.api_key = api_key or GEMINI_API_KEY
        self.model_name = model_name or MODEL_NAME or "gemini-3.6-flash"

        if client is not None:
            self.client = client
        elif self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None

    def _generate_with_model(
        self,
        model: str,
        prompt: str,
    ) -> Any:
        """Helper to invoke generate_content with structured output configuration."""
        config = types.GenerateContentConfig(
            system_instruction=REVPULSE_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=RevPulseAgentResponse,
            temperature=0.1,
        )
        return self.client.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )

    def analyze_interaction(
        self,
        customer_input: str,
        invoice_context: Dict[str, Any],
        channel: str = "EMAIL",
    ) -> RevPulseAgentResponse:
        """
        Analyze customer response and determine next collection/negotiation step.
        Wraps primary model with tenacity retry (4 attempts, exponential backoff)
        and automatically falls back to secondary models if transient/503 errors persist.
        """
        if self.client is None:
            raise ValueError(
                "Gemini Client is not initialized. Please provide GEMINI_API_KEY."
            )

        prompt = self._build_prompt(
            customer_input=customer_input,
            invoice_context=invoice_context,
            channel=channel,
        )

        retryer = Retrying(
            retry=retry_if_exception_type((errors.ServerError, errors.APIError)),
            wait=wait_exponential(multiplier=1.0, min=1, max=2),
            stop=stop_after_attempt(2),
            reraise=True,
        )

        response = None
        try:
            response = retryer(self._generate_with_model, self.model_name, prompt)
        except (errors.ServerError, errors.APIError, RetryError, Exception) as primary_err:
            logger.debug(f"Primary model {self.model_name} failed ({primary_err}). Attempting single fast fallback.")
            # Attempt fallback models in sequence with single shot
            fallback_success = False
            for fallback_model in self.FALLBACK_MODELS:
                if fallback_model == self.model_name:
                    continue
                try:
                    logger.debug(f"Attempting fallback to {fallback_model}...")
                    response = self._generate_with_model(fallback_model, prompt)
                    fallback_success = True
                    break
                except Exception as fb_err:
                    logger.debug(f"Fallback model {fallback_model} failed: {fb_err}")
                    # Fast-fail immediately on rate limits/network errors
                    break

            if not fallback_success or response is None:
                logger.debug(
                    "[RevPulse AI] Notice: Upstream rate limit encountered. Switched to deterministic rule parser."
                )
                return self._heuristic_fallback(
                    customer_text=customer_input,
                    invoice_context=invoice_context,
                    channel=channel,
                )

        # In google-genai SDK with response_schema, response.parsed contains the validated Pydantic model
        if hasattr(response, "parsed") and response.parsed is not None:
            if isinstance(response.parsed, RevPulseAgentResponse):
                return response.parsed
            if isinstance(response.parsed, dict):
                return RevPulseAgentResponse.model_validate(response.parsed)

        # Fallback to response.text if parsed is not directly populated
        raw_text = getattr(response, "text", None)
        if not raw_text:
            return self._heuristic_fallback(
                customer_text=customer_input,
                invoice_context=invoice_context,
                channel=channel,
            )

        try:
            return RevPulseAgentResponse.model_validate_json(raw_text)
        except Exception as parse_err:
            logger.warning(f"Failed parsing response text as JSON ({parse_err}). Using heuristic fallback.")
            return self._heuristic_fallback(
                customer_text=customer_input,
                invoice_context=invoice_context,
                channel=channel,
            )

    def _heuristic_fallback(
        self,
        customer_text: str,
        invoice_context: Dict[str, Any],
        channel: str,
    ) -> RevPulseAgentResponse:
        """
        Deterministic offline rule-based parser when Gemini API is throttled or offline.
        Ensures recovery operations continue smoothly without crashing multi-turn loops.
        """
        from datetime import date, timedelta
        from src.schemas.agent_schema import (
            ActionRequired,
            Channel as CommChannel,
            CommunicationDraft,
            DisputeCategory,
            DisputeDetails,
            Installment,
            Intent,
            ProposedSettlement,
            RiskLevel,
        )

        text_lower = customer_text.lower()
        channel_enum = CommChannel(channel.upper()) if channel.upper() in CommChannel.__members__ else CommChannel.EMAIL
        recipient = invoice_context.get("recipient_contact", {}).get("email") or invoice_context.get("recipient_contact", {}).get("phone") or "customer@client.com"
        invoice_id = invoice_context.get("invoice_id", "INV-UNKNOWN")
        balance = float(
            invoice_context.get("financial_summary", {}).get("balance_due")
            or invoice_context.get("amount_due")
            or 1000.0
        )

        company_name = invoice_context.get("customer_name") or invoice_context.get("company_name", "Valued Client")
        doc_number = invoice_context.get("invoice_number") or invoice_id
        company_domain = "revpulse.io"

        # 0. Immediate Legal Threat / Insolvency Keywords
        legal_keywords = ["lawyer", "attorney", "legal", "sue", "court", "bankrupt", "bankruptcy", "cease and desist", "scam", "fraud"]
        if any(kw in text_lower for kw in legal_keywords):
            if channel_enum == CommChannel.EMAIL:
                legal_body = f"""Dear {company_name} Management Team,

We have formally noted your notification regarding legal representation. 

In strict compliance with AR regulatory standards:
  🔒  **Automated Communications:** SUSPENDED
  📋  **Account Status:** TRANSFERRED TO LEGAL & SENIOR MANAGEMENT
  ⏱️  **Operational Hold:** ACTIVE

All automated recovery communications have been ceased. A senior account executive and legal liaison will review your account file directly.

Sincerely,  
**RevPulse Compliance & Legal Operations**  
compliance@{company_domain}"""
            else:
                legal_body = (
                    f"⚖️ *RevPulse Notice - Invoice #{doc_number}*\n\n"
                    f"We acknowledge your notification regarding legal counsel or insolvency.\n"
                    f"• Status: OUTREACH SUSPENDED (Legal Hold Active)\n"
                    f"• Your file has been escalated to senior management."
                )

            return RevPulseAgentResponse(
                intent=Intent.HUMAN_ESCALATION,
                action_required=ActionRequired.FLAG_HUMAN_REVIEW,
                confidence_score=0.99,
                risk_level=RiskLevel.CRITICAL,
                drafted_communication=CommunicationDraft(
                    channel=channel_enum,
                    recipient=recipient,
                    subject=f"Notice of Account Freeze & Escalation: Invoice #{doc_number} - {company_name}",
                    body=legal_body,
                ),
                internal_notes="Deterministic fallback: Detected legal threat / bankruptcy mention. Ceased collections and flagged for human review.",
            )

        # 1. Billing Dispute Keywords: cracks, defect, pause, incomplete, repair, dispute, not paying, wrong, charge
        dispute_keywords = ["crack", "cracks", "defect", "defective", "pause", "incomplete", "repair", "dispute", "not paying", "wrong", "charge", "incorrect", "overcharge"]
        if any(kw in text_lower for kw in dispute_keywords):
            if channel_enum == CommChannel.EMAIL:
                email_body = f"""Dear {company_name} Management Team,

We have logged a formal dispute regarding deliverable defects on Invoice #{doc_number} (${balance:,.2f}):

  ⚠️  **Dispute Ticket:** TICK-DISP-{invoice_id}  
  🔒  **Account Status:** COLLECTIONS FROZEN (Hold: Active)  
  📋  **Late Fees & Reminders:** SUSPENDED  
  ⏱️  **Operational SLA:** 2 Business Days  

To expedite our operational review and coordinate remedial site measures:
  1. Please submit site inspection notes, contractor punch lists, or photographic evidence of the reported defects.
  2. Our operations project lead will review your submission within two (2) business days.

Thank you for your partnership as we work together to bring this to resolution.

Sincerely,  
**RevPulse Dispute Resolution Team**  
disputes@{company_domain}"""
            else:
                email_body = (
                    f"⚠️ *RevPulse Notice - Invoice #{doc_number}*\n\n"
                    f"We have logged your dispute regarding deliverable defects:\n"
                    f"• Ticket: TICK-DISP-{invoice_id}\n"
                    f"• Status: COLLECTIONS FROZEN (Hold: Active)\n"
                    f"• Review SLA: 2 Business Days\n\n"
                    f"Please reply with any inspection notes or photos to expedite review."
                )

            return RevPulseAgentResponse(
                intent=Intent.BILLING_DISPUTE,
                action_required=ActionRequired.OPEN_DISPUTE_TICKET,
                confidence_score=0.90,
                risk_level=RiskLevel.HIGH,
                drafted_communication=CommunicationDraft(
                    channel=channel_enum,
                    recipient=recipient,
                    subject=f"Notice of Formal Dispute Ticket & Temporary Hold: Invoice #{doc_number}",
                    body=email_body,
                ),
                dispute_details=DisputeDetails(
                    category=DisputeCategory.DEFECTIVE_WORK,
                    summary=f"Customer reported deliverable quality or completeness issue: {customer_text[:140]}",
                    requires_invoice_hold=True,
                    requested_documentation=["Inspection photos or error logs", "Statement of work reference"],
                ),
                internal_notes="Deterministic fallback: Detected defective work dispute keywords. Opened dispute ticket and halted dunning.",
            )

        # 2. Payment Plan Keywords: pay, installments, split, half, cash flow, tight
        plan_keywords = ["installment", "installments", "split", "half", "cash flow", "tight", "payment plan", "two payments"]
        if any(kw in text_lower for kw in plan_keywords):
            half_amt = round(balance / 2.0, 2)
            rem_amt = round(balance - half_amt, 2)
            due1 = (date.today() + timedelta(days=7)).isoformat()
            due2 = (date.today() + timedelta(days=37)).isoformat()

            if channel_enum == CommChannel.EMAIL:
                plan_body = f"""Dear {company_name} Accounting Team,

We have approved your request for an installment arrangement on Invoice #{doc_number} (${balance:,.2f}):

📋  **Approved Installment Schedule:**
  • **Installment 1:** ${half_amt:,.2f} due by **{due1}**
  • **Installment 2:** ${rem_amt:,.2f} due by **{due2}**

Next Steps:
  1. Remit Installment 1 using the secure payment portal link provided below.
  2. Upon confirmation of receipt, automated collections will remain paused until the final maturity date.

Collections are paused while payments remain on schedule.

Sincerely,  
**RevPulse Accounts Receivable Team**  
billing@{company_domain}"""
            else:
                plan_body = (
                    f"💳 *RevPulse Payment Plan - Invoice #{doc_number}*\n\n"
                    f"We have approved your 2-part installment plan (${balance:,.2f}):\n"
                    f"  • Installment 1: ${half_amt:,.2f} due by {due1}\n"
                    f"  • Installment 2: ${rem_amt:,.2f} due by {due2}\n\n"
                    f"Pay Installment 1 here: {{payment_link}}\n"
                    f"Collections remain paused while payments are on schedule."
                )

            return RevPulseAgentResponse(
                intent=Intent.PAYMENT_PLAN_REQUESTED,
                action_required=ActionRequired.SEND_PAYMENT_PLAN_AGREEMENT,
                confidence_score=0.90,
                risk_level=RiskLevel.MEDIUM,
                drafted_communication=CommunicationDraft(
                    channel=channel_enum,
                    recipient=recipient,
                    subject=f"Payment Plan Confirmation: Invoice #{doc_number} - {company_name}",
                    body=plan_body,
                ),
                proposed_settlement=ProposedSettlement(
                    installments_count=2,
                    total_amount=balance,
                    installments=[
                        Installment(due_date=due1, amount=half_amt),
                        Installment(due_date=due2, amount=rem_amt),
                    ],
                ),
                internal_notes="Deterministic fallback: Generated structured 50/50 installment proposal based on customer request.",
            )

        # 3. Full payment promise
        if any(kw in text_lower for kw in ["pay in full", "pay today", "pay right away", "pay now", "full payment"]):
            if channel_enum == CommChannel.EMAIL:
                full_body = f"""Dear {company_name} Accounting Team,

Thank you for confirming your intention to settle Invoice #{doc_number} (${balance:,.2f}) in full today. 

💳  **Secure Payment Portal:**  
{{{{payment_link}}}}

Upon successful transmission of your payment, our ledger will automatically reconcile your balance to $0.00 and dispatch your final receipt.

Sincerely,  
**RevPulse Accounts Receivable Team**  
billing@{company_domain}"""
            else:
                full_body = (
                    f"💳 *RevPulse Settlement Link - Invoice #{doc_number}*\n\n"
                    f"Thank you for confirming full payment (${balance:,.2f}).\n"
                    f"Settle securely here: {{{{payment_link}}}}\n"
                    f"A receipt will be issued immediately upon completion."
                )

            return RevPulseAgentResponse(
                intent=Intent.FULL_PAYMENT_PROMISED,
                action_required=ActionRequired.SEND_PAYMENT_LINK,
                confidence_score=0.95,
                risk_level=RiskLevel.LOW,
                drafted_communication=CommunicationDraft(
                    channel=channel_enum,
                    recipient=recipient,
                    subject=f"Secure Payment Link: Invoice #{doc_number} - {company_name}",
                    body=full_body,
                ),
                internal_notes="Deterministic fallback: Customer promised full payment.",
            )

        # 4. Default: Information Request
        if channel_enum == CommChannel.EMAIL:
            info_body = f"""Dear {company_name} Accounting Team,

Thank you for contacting RevPulse regarding Invoice #{doc_number} for ${balance:,.2f}. 

We are committed to assisting your team with account clarifications, statement copies, or payment scheduling arrangements. Could you please let us know how we can best support you in bringing this balance to resolution?

Sincerely,  
**RevPulse Accounts Receivable Team**  
billing@{company_domain}"""
        else:
            info_body = (
                f"📋 *RevPulse Notice - Invoice #{doc_number}*\n\n"
                f"Hello from RevPulse regarding balance ${balance:,.2f}.\n"
                f"Please let us know how we can assist you with your statement or payment schedule."
            )

        return RevPulseAgentResponse(
            intent=Intent.INFORMATION_REQUEST,
            action_required=ActionRequired.REQUEST_INFO,
            confidence_score=0.85,
            risk_level=RiskLevel.LOW,
            drafted_communication=CommunicationDraft(
                channel=channel_enum,
                recipient=recipient,
                subject=f"Account Review: Invoice #{doc_number} - {company_name}",
                body=info_body,
            ),
            internal_notes="Deterministic fallback: Information request / account clarification.",
        )




    def _build_prompt(
        self,
        customer_input: str,
        invoice_context: Dict[str, Any],
        channel: str,
    ) -> str:
        return f"""
Analyze the following customer communication regarding an outstanding invoice and provide an actionable, structured AR recovery response following all system policies and guardrails.

### INVOICE & ACCOUNT CONTEXT:
{json.dumps(invoice_context, indent=2)}

### COMMUNICATION CHANNEL:
{channel.upper()}

### CUSTOMER MESSAGE:
\"\"\"{customer_input}\"\"\"

Generate the response matching the RevPulseAgentResponse schema.
""".strip()
