"""
Audit logging and human escalation schemas for RevPulse.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EscalationReason(str, Enum):
    LEGAL_THREAT = "LEGAL_THREAT"
    INSOLVENCY_BANKRUPTCY = "INSOLVENCY_BANKRUPTCY"
    ABUSIVE_LANGUAGE = "ABUSIVE_LANGUAGE"
    UNACCEPTABLE_SETTLEMENT_TERMS = "UNACCEPTABLE_SETTLEMENT_TERMS"
    PERSISTENT_NON_RESPONSIVE = "PERSISTENT_NON_RESPONSIVE"
    LOW_CONFIDENCE_SCORE = "LOW_CONFIDENCE_SCORE"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"


class EscalationAlert(BaseModel):
    alert_id: str = Field(..., description="Unique escalation alert ID")
    invoice_id: str = Field(..., description="Associated normalized invoice ID")
    customer_id: str = Field(..., description="Customer / debtor identifier")
    reason: EscalationReason = Field(..., description="Tripped compliance or policy escalation category")
    risk_level: str = Field(..., description="Severity level (e.g. HIGH, CRITICAL)")
    summary: str = Field(..., description="Concise synopsis of the trigger incident")
    recommended_action: str = Field(..., description="Prescribed next step for human accounts executive")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Alert generation timestamp")
    full_transcript: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Historical transcript up to the escalation event"
    )


class AuditLogEntry(BaseModel):
    log_id: str = Field(..., description="Unique immutable log ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp of the recorded event")
    invoice_id: str = Field(..., description="Target invoice ID")
    doc_number: Optional[str] = Field(None, description="Target accounting document number")
    customer_id: str = Field(..., description="Target customer ID")
    event_type: str = Field(
        ...,
        description="Type of event: INBOUND_MESSAGE, AI_DECISION, PAYMENT_GENERATED, DISPUTE_OPENED, HUMAN_ESCALATED, PAYMENT_RECONCILED"
    )
    channel: str = Field(..., description="Originating or dispatch channel (WHATSAPP, SMS, EMAIL, SYSTEM)")
    raw_input: Optional[str] = Field(None, description="Inbound text content or prompt trigger if applicable")
    response_summary: Optional[str] = Field(None, description="Summary of outgoing action or decision")
    escalation_reason: Optional[EscalationReason] = Field(None, description="Escalation trigger reason if escalated")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary audit details and payload state")
