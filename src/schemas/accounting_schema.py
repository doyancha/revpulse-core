"""
Accounting data normalization and ingestion schemas for RevPulse.
"""

from datetime import date
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class PlatformSource(str, Enum):
    QUICKBOOKS = "QUICKBOOKS"
    XERO = "XERO"
    MANUAL = "MANUAL"


class AgingBucket(str, Enum):
    CURRENT = "CURRENT"
    OVERDUE_7_PLUS = "OVERDUE_7_PLUS"
    OVERDUE_15_PLUS = "OVERDUE_15_PLUS"
    OVERDUE_30_PLUS = "OVERDUE_30_PLUS"
    OVERDUE_60_PLUS = "OVERDUE_60_PLUS"


class CustomerProfile(BaseModel):
    customer_id: str = Field(..., description="Unique customer/contact ID from origin platform or RevPulse")
    company_name: str = Field(..., description="Legal or trade name of the debtor organization")
    primary_email: str = Field(..., description="Primary billing or contact email address")
    phone_number: Optional[str] = Field(None, description="Primary contact phone number or SMS target")
    preferred_channel: str = Field(
        default="EMAIL",
        description="Preferred communication channel (WHATSAPP, SMS, EMAIL)"
    )
    total_outstanding: float = Field(
        default=0.0,
        ge=0.0,
        description="Aggregate outstanding balance across all active invoices for this customer"
    )
    average_days_to_pay: float = Field(
        default=30.0,
        ge=0.0,
        description="Historical average days to settlement"
    )
    default_risk_score: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Calculated delinquency or default risk score between 0.0 and 1.0"
    )


class NormalizedInvoice(BaseModel):
    invoice_id: str = Field(..., description="Normalized unique identifier in RevPulse (e.g. QBO_1001)")
    platform: PlatformSource = Field(..., description="Origin accounting platform source")
    platform_invoice_id: str = Field(..., description="Raw origin platform invoice primary key")
    invoice_number: str = Field(..., description="Human-readable invoice/document number")
    issue_date: date = Field(..., description="Date invoice was issued/created")
    due_date: date = Field(..., description="Invoice contractual due date")
    total_amount: float = Field(..., gt=0, description="Gross total invoice amount")
    balance_due: float = Field(..., ge=0, description="Current unpaid balance outstanding")
    currency: str = Field(default="USD", description="Three-letter ISO currency code")
    days_overdue: int = Field(..., description="Number of days elapsed past due date (negative if not yet due)")
    aging_bucket: AgingBucket = Field(..., description="Categorized AR aging bucket")
    customer: CustomerProfile = Field(..., description="Customer profile and delinquency health details")
    line_items_summary: List[str] = Field(
        default_factory=list,
        description="Itemized list of product/service line items with amounts"
    )
