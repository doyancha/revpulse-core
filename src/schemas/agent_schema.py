"""
Pydantic v2 schemas for RevPulse Autonomous AR Recovery Engine.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class Intent(str, Enum):
    FULL_PAYMENT_PROMISED = "FULL_PAYMENT_PROMISED"
    PAYMENT_PLAN_REQUESTED = "PAYMENT_PLAN_REQUESTED"
    BILLING_DISPUTE = "BILLING_DISPUTE"
    INFORMATION_REQUEST = "INFORMATION_REQUEST"
    HUMAN_ESCALATION = "HUMAN_ESCALATION"


class ActionRequired(str, Enum):
    SEND_PAYMENT_LINK = "SEND_PAYMENT_LINK"
    SEND_PAYMENT_PLAN_AGREEMENT = "SEND_PAYMENT_PLAN_AGREEMENT"
    OPEN_DISPUTE_TICKET = "OPEN_DISPUTE_TICKET"
    NOTIFY_ACCOUNT_EXECUTIVE = "NOTIFY_ACCOUNT_EXECUTIVE"
    REQUEST_INFO = "REQUEST_INFO"
    FLAG_HUMAN_REVIEW = "FLAG_HUMAN_REVIEW"


class DisputeCategory(str, Enum):
    INCOMPLETE_DELIVERABLE = "INCOMPLETE_DELIVERABLE"
    DEFECTIVE_WORK = "DEFECTIVE_WORK"
    INCORRECT_PRICING = "INCORRECT_PRICING"
    ALREADY_PAID = "ALREADY_PAID"
    NEVER_RECEIVED_INVOICE = "NEVER_RECEIVED_INVOICE"
    UNAUTHORIZED_PURCHASE = "UNAUTHORIZED_PURCHASE"
    OTHER = "OTHER"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Channel(str, Enum):
    WHATSAPP = "WHATSAPP"
    SMS = "SMS"
    EMAIL = "EMAIL"


class CommunicationDraft(BaseModel):
    channel: Channel = Field(..., description="Communication channel (WHATSAPP, SMS, EMAIL)")
    recipient: str = Field(..., description="Recipient email address, phone number, or identifier")
    subject: Optional[str] = Field(None, description="Optional subject line, primarily used for email")
    body: str = Field(..., description="Drafted message content complying with channel constraints")


class Installment(BaseModel):
    due_date: str = Field(..., description="Installment payment amount in USD")
    amount: float = Field(..., ge=0.01, description="Installment payment amount in USD")


class ProposedSettlement(BaseModel):
    installments_count: int = Field(
        ...,
        ge=1,
        le=3,
        description="Number of installment payments (policy limit: maximum 3 splits)"
    )
    total_amount: float = Field(..., ge=0.01, description="Sum of all installments")
    installments: List[Installment] = Field(..., min_length=1, max_length=3, description="List of installments")

    @field_validator("installments")
    @classmethod
    def validate_installments_match_count(cls, v: List[Installment], info) -> List[Installment]:
        count = info.data.get("installments_count")
        if count is not None and len(v) != count:
            raise ValueError(f"Number of installments ({len(v)}) must match installments_count ({count})")
        return v


class DisputeDetails(BaseModel):
    category: DisputeCategory = Field(..., description="Specific category classifying the dispute")
    summary: str = Field(..., description="Summary of customer dispute claims")
    requires_invoice_hold: bool = Field(
        default=True,
        description="Whether collections/reminders should be paused pending dispute resolution"
    )
    requested_documentation: List[str] = Field(
        default_factory=list,
        description="List of documents or clarifications requested from customer or operations"
    )


class RevPulseAgentResponse(BaseModel):
    intent: Intent = Field(..., description="Classified intent of customer communication")
    action_required: ActionRequired = Field(..., description="Recommended downstream system action")
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model confidence in its assessment between 0.0 and 1.0"
    )
    risk_level: RiskLevel = Field(..., description="Risk assessment for account delinquency or relationship damage")
    drafted_communication: CommunicationDraft = Field(..., description="Drafted response to customer")
    proposed_settlement: Optional[ProposedSettlement] = Field(
        None,
        description="Populated if a structured payment plan was negotiated or proposed"
    )
    dispute_details: Optional[DisputeDetails] = Field(
        None,
        description="Populated if the communication is a billing dispute"
    )
    internal_notes: str = Field(
        ...,
        description="Internal context, audit rationale, or instructions for AR staff"
    )
