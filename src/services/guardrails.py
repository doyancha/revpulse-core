"""
Compliance guardrails engine for identifying legal threats, bankruptcy/insolvency,
abusive language, and low confidence decisions that require immediate human handoff.
"""

import re
from typing import Any, Dict, List, Optional
import uuid

from src.schemas.agent_schema import Intent, RevPulseAgentResponse
from src.schemas.audit_schema import EscalationAlert, EscalationReason


class ComplianceGuardrailsEngine:
    """
    Evaluates customer communications and agent outputs against legal, regulatory,
    and institutional policy guardrails.
    """

    # Keyword and regex patterns
    LEGAL_PATTERNS = [
        r"\blawyer\b",
        r"\battorney\b",
        r"\bsue\b",
        r"\bsuing\b",
        r"\blegal action\b",
        r"\bcourt\b",
        r"\blitigation\b",
        r"\binjunction\b",
        r"\bsubpoena\b",
        r"\bretain(ed)? counsel\b",
    ]

    BANKRUPTCY_PATTERNS = [
        r"\bchapter 11\b",
        r"\bchapter 7\b",
        r"\bchapter 13\b",
        r"\bbankrupt\b",
        r"\bbankruptcy\b",
        r"\binsolvent\b",
        r"\binsolvency\b",
        r"\bliquidation\b",
        r"\badministration\b",
        r"\breceivership\b",
    ]

    ABUSIVE_PATTERNS = [
        r"\bharass(ment|ing)?\b",
        r"\bextort(ion)?\b",
        r"\bfraud(ster)?\b",
        r"\bscam(mer)?\b",
        r"\bfuck\b",
        r"\bshit\b",
        r"\bbullshit\b",
    ]

    def detect_immediate_escalation(self, text: str) -> Optional[EscalationReason]:
        """
        Check regex patterns for LEGAL_THREAT, INSOLVENCY_BANKRUPTCY, and ABUSIVE_LANGUAGE
        directly against the raw customer string.
        """
        text_lower = text.lower()
        for pattern in self.LEGAL_PATTERNS:
            if re.search(pattern, text_lower):
                return EscalationReason.LEGAL_THREAT

        for pattern in self.BANKRUPTCY_PATTERNS:
            if re.search(pattern, text_lower):
                return EscalationReason.INSOLVENCY_BANKRUPTCY

        for pattern in self.ABUSIVE_PATTERNS:
            if re.search(pattern, text_lower):
                return EscalationReason.ABUSIVE_LANGUAGE

        return None

    def check_raw_text(
        self,
        customer_text: str,
        invoice_id: str,
        customer_id: str,
        transcript: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[EscalationAlert]:
        """
        Fast rule-based compliance check directly on raw customer text.
        Returns EscalationAlert if legal threats, bankruptcy, or abusive language are detected, else None.
        """
        reason = self.detect_immediate_escalation(customer_text)
        if not reason:
            return None

        full_transcript = transcript or []
        if reason == EscalationReason.LEGAL_THREAT:
            return EscalationAlert(
                alert_id=f"alert_{uuid.uuid4().hex[:10]}",
                invoice_id=invoice_id,
                customer_id=customer_id,
                reason=reason,
                risk_level="CRITICAL",
                summary=f"Legal threat detected in customer message: '{customer_text[:120]}'",
                recommended_action="Immediately freeze automated outreach. Route to In-House Legal Counsel and Senior Accounts Executive.",
                full_transcript=full_transcript,
            )
        elif reason == EscalationReason.INSOLVENCY_BANKRUPTCY:
            return EscalationAlert(
                alert_id=f"alert_{uuid.uuid4().hex[:10]}",
                invoice_id=invoice_id,
                customer_id=customer_id,
                reason=reason,
                risk_level="CRITICAL",
                summary=f"Insolvency/Bankruptcy indication detected: '{customer_text[:120]}'",
                recommended_action="Halt collection activity immediately under Automatic Stay regulations. File proof of claim with bankruptcy court.",
                full_transcript=full_transcript,
            )
        elif reason == EscalationReason.ABUSIVE_LANGUAGE:
            return EscalationAlert(
                alert_id=f"alert_{uuid.uuid4().hex[:10]}",
                invoice_id=invoice_id,
                customer_id=customer_id,
                reason=reason,
                risk_level="HIGH",
                summary=f"Hostile or abusive language detected in customer message.",
                recommended_action="Transfer account to Senior Collections Supervisor. Cease SMS/WhatsApp outreach.",
                full_transcript=full_transcript,
            )

        return None


    def evaluate_for_escalation(
        self,
        customer_text: str,
        ai_response: RevPulseAgentResponse,
        invoice_id: str,
        customer_id: str,
        turn_count: int = 1,
        transcript: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[EscalationAlert]:
        """
        Evaluates the customer input and AI response.
        Returns EscalationAlert if any guardrail is tripped, else None.
        """
        full_transcript = transcript or []

        # 1. Check raw text patterns
        raw_text_alert = self.check_raw_text(
            customer_text=customer_text,
            invoice_id=invoice_id,
            customer_id=customer_id,
            transcript=full_transcript,
        )
        if raw_text_alert:
            return raw_text_alert

        # 4. Check Low Model Confidence Score
        if ai_response.confidence_score < 0.65:
            return EscalationAlert(
                alert_id=f"alert_{uuid.uuid4().hex[:10]}",
                invoice_id=invoice_id,
                customer_id=customer_id,
                reason=EscalationReason.LOW_CONFIDENCE_SCORE,
                risk_level="MEDIUM",
                summary=f"AI model confidence ({ai_response.confidence_score:.2f}) below threshold (0.65).",
                recommended_action="Review customer response manually before dispatching further correspondence.",
                full_transcript=full_transcript,
            )

        # 5. Check AI Explicit Intent for Human Escalation
        if ai_response.intent == Intent.HUMAN_ESCALATION:
            return EscalationAlert(
                alert_id=f"alert_{uuid.uuid4().hex[:10]}",
                invoice_id=invoice_id,
                customer_id=customer_id,
                reason=EscalationReason.MANUAL_OVERRIDE,
                risk_level=ai_response.risk_level.value,
                summary=f"AI Engine recommended human escalation: {ai_response.internal_notes[:140]}",
                recommended_action="Assigned account executive review required.",
                full_transcript=full_transcript,
            )

        return None
