"""
SQLModel database tables for RevPulse.
Captures invoices, conversation threads, messages, and audit trail events.
"""

from datetime import date, datetime
from typing import Optional
from sqlmodel import Field, SQLModel


class InvoiceRecord(SQLModel, table=True):
    __tablename__ = "invoices"

    id: str = Field(primary_key=True, index=True, description="Normalized invoice ID (e.g. QBO_1001)")
    doc_number: str = Field(index=True, description="Accounting document number (e.g. INV-1001)")
    platform: str = Field(default="QUICKBOOKS", description="QUICKBOOKS, XERO, MANUAL")
    customer_name: str = Field(index=True, description="Debtor company or individual name")
    customer_email: str = Field(index=True, description="Primary contact email")
    customer_phone: Optional[str] = Field(default=None, description="Primary phone number")
    total_amount: float = Field(default=0.0, description="Gross total invoice amount")
    balance_due: float = Field(default=0.0, index=True, description="Remaining unpaid balance")
    due_date: date = Field(index=True, description="Contractual due date")
    currency: str = Field(default="USD", description="Currency code (e.g. USD, EUR)")
    status: str = Field(default="ACTIVE", index=True, description="ACTIVE, PAID, UNDER_DISPUTE, ESCALATED")
    days_overdue: int = Field(default=0, index=True, description="Days elapsed past due date")
    aging_bucket: str = Field(default="CURRENT", index=True, description="CURRENT, OVERDUE_7_PLUS, OVERDUE_15_PLUS, etc.")
    dispute_hold: bool = Field(default=False, description="Whether dunning is paused due to active dispute")


class ConversationThreadRecord(SQLModel, table=True):
    __tablename__ = "conversation_threads"

    id: str = Field(primary_key=True, index=True, description="Unique conversation thread ID")
    invoice_id: str = Field(index=True, description="Target invoice ID")
    customer_id: Optional[str] = Field(default="UNKNOWN", description="Associated customer or debtor ID")
    customer_name: str = Field(default="Unknown", description="Debtor customer name")
    channel: str = Field(default="EMAIL", description="WHATSAPP, SMS, EMAIL")
    status: str = Field(default="ACTIVE", index=True, description="ACTIVE, RESOLVED_PAID, RESOLVED_PLAN, UNDER_DISPUTE, ESCALATED")
    risk_level: str = Field(default="LOW", description="LOW, MEDIUM, HIGH, CRITICAL")
    turn_count: int = Field(default=0, description="Customer turn count")
    unread_count: int = Field(default=0, description="Unread inbound messages count")
    updated_at: datetime = Field(default_factory=datetime.utcnow, index=True, description="Last thread update timestamp")


class MessageRecord(SQLModel, table=True):
    __tablename__ = "messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    thread_id: str = Field(index=True, description="Associated conversation thread ID")
    role: str = Field(description="CUSTOMER, AGENT, SYSTEM")
    channel: str = Field(default="EMAIL", description="WHATSAPP, SMS, EMAIL")
    content: str = Field(description="Message body text")
    intent: Optional[str] = Field(default=None, description="Classified intent if evaluated")
    confidence: Optional[float] = Field(default=None, description="Model confidence score")
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True, description="Message creation timestamp")


class AuditLogRecord(SQLModel, table=True):
    __tablename__ = "audit_logs"

    id: str = Field(primary_key=True, index=True, description="Unique audit event ID")
    invoice_id: str = Field(index=True, description="Associated invoice ID")
    doc_number: Optional[str] = Field(default=None, index=True, description="Accounting document number")
    customer_id: Optional[str] = Field(default=None, index=True, description="Associated customer ID")
    event_type: str = Field(index=True, description="INBOUND_MESSAGE, AI_DECISION, PAYMENT_GENERATED, etc.")
    channel: str = Field(default="SYSTEM", description="Originating channel")
    customer_input: Optional[str] = Field(default=None, description="Inbound text content if applicable")
    response_summary: Optional[str] = Field(default=None, description="Action or response summary")
    escalation_reason: Optional[str] = Field(default=None, description="Escalation reason if tripped")
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True, description="Timestamp of recorded event")
