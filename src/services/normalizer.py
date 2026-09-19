"""
Normalizer service for heterogeneous accounting platform payloads (QuickBooks Online, Xero).
"""

from datetime import date, datetime
import re
from typing import Any, Dict, List, Optional

from src.schemas.accounting_schema import (
    CustomerProfile,
    NormalizedInvoice,
    PlatformSource,
)
from src.services.aging_engine import calculate_days_overdue, determine_aging_bucket


class AccountingDataNormalizer:
    """
    Normalizes raw QuickBooks Online and Xero invoice JSON payloads
    into unified Pydantic NormalizedInvoice objects with credit/delinquency metrics.
    """

    @staticmethod
    def parse_date(date_val: Any) -> date:
        """
        Parses date from various formats:
        - date object
        - ISO string (e.g. '2026-07-15' or '2026-07-15T00:00:00')
        - Legacy Xero timestamp: '/Date(1791072000000+0000)/'
        """
        if isinstance(date_val, date) and not isinstance(date_val, datetime):
            return date_val
        if isinstance(date_val, datetime):
            return date_val.date()

        if isinstance(date_val, str):
            # Check legacy Xero format /Date(1234567890000+0000)/
            match = re.search(r"/Date\((\d+)([+-]\d+)?\)/", date_val)
            if match:
                timestamp_ms = int(match.group(1))
                return datetime.utcfromtimestamp(timestamp_ms / 1000.0).date()

            # Handle ISO string with or without time
            clean_str = date_val.split("T")[0]
            return datetime.strptime(clean_str, "%Y-%m-%d").date()

        raise ValueError(f"Unable to parse date value: {date_val}")

    @classmethod
    def normalize_qbo_payload(
        cls, payload: Dict[str, Any], reference_date: Optional[date] = None
    ) -> List[NormalizedInvoice]:
        """
        Normalizes QuickBooks Online QueryResponse payload.
        """
        invoices_data = payload.get("QueryResponse", {}).get("Invoice", [])
        if not invoices_data and isinstance(payload.get("Invoice"), list):
            invoices_data = payload.get("Invoice", [])

        normalized_list: List[NormalizedInvoice] = []

        for inv in invoices_data:
            platform_id = str(inv.get("Id", ""))
            doc_number = str(inv.get("DocNumber", f"INV-{platform_id}"))
            issue_date = cls.parse_date(inv.get("TxnDate", date.today().isoformat()))
            due_date = cls.parse_date(inv.get("DueDate", issue_date.isoformat()))
            total_amt = float(inv.get("TotalAmt", 0.0))
            balance = float(inv.get("Balance", 0.0))

            currency_info = inv.get("CurrencyRef", {})
            currency = currency_info.get("value", "USD") if isinstance(currency_info, dict) else "USD"

            # Customer Profile extraction
            cust_ref = inv.get("CustomerRef", {})
            cust_id = cust_ref.get("value", "UNKNOWN_CUST")
            cust_name = cust_ref.get("name", "Unknown Customer")

            bill_email = inv.get("BillEmail", {}).get("Address", "billing@customer.com")

            # Extract custom fields if any
            phone: Optional[str] = None
            preferred_channel = "EMAIL"
            for cf in inv.get("CustomField", []):
                name = cf.get("Name", "").lower()
                val = cf.get("StringValue", "")
                if "phone" in name:
                    phone = val
                elif "channel" in name:
                    preferred_channel = val.upper()

            days_overdue = calculate_days_overdue(due_date, reference_date)
            aging_bucket = determine_aging_bucket(days_overdue)

            # Calculate delinquency and risk scores based on aging & balance
            risk_score = cls._compute_risk_score(days_overdue, balance)
            avg_days_to_pay = max(30.0, 30.0 + (days_overdue if days_overdue > 0 else 0))

            customer = CustomerProfile(
                customer_id=cust_id,
                company_name=cust_name,
                primary_email=bill_email,
                phone_number=phone,
                preferred_channel=preferred_channel,
                total_outstanding=balance,
                average_days_to_pay=float(avg_days_to_pay),
                default_risk_score=risk_score,
            )

            # Summarize Line Items
            line_summaries: List[str] = []
            for line in inv.get("Line", []):
                if line.get("DetailType") == "SalesItemLineDetail" or "Amount" in line:
                    desc = line.get("Description") or line.get("SalesItemLineDetail", {}).get("ItemRef", {}).get("name", "Services")
                    amt = line.get("Amount", 0.0)
                    line_summaries.append(f"{desc} (${amt:,.2f})")

            normalized = NormalizedInvoice(
                invoice_id=f"QBO_{platform_id}",
                platform=PlatformSource.QUICKBOOKS,
                platform_invoice_id=platform_id,
                invoice_number=doc_number,
                issue_date=issue_date,
                due_date=due_date,
                total_amount=total_amt,
                balance_due=balance,
                currency=currency,
                days_overdue=days_overdue,
                aging_bucket=aging_bucket,
                customer=customer,
                line_items_summary=line_summaries,
            )
            normalized_list.append(normalized)

        return normalized_list

    @classmethod
    def normalize_xero_payload(
        cls, payload: Dict[str, Any], reference_date: Optional[date] = None
    ) -> List[NormalizedInvoice]:
        """
        Normalizes Xero API Invoices payload.
        """
        invoices_data = payload.get("Invoices", [])
        normalized_list: List[NormalizedInvoice] = []

        for inv in invoices_data:
            platform_id = str(inv.get("InvoiceID", ""))
            doc_number = str(inv.get("InvoiceNumber", f"INV-{platform_id}"))

            raw_date = inv.get("DateString") or inv.get("Date") or date.today().isoformat()
            raw_due_date = inv.get("DueDateString") or inv.get("DueDate") or raw_date

            issue_date = cls.parse_date(raw_date)
            due_date = cls.parse_date(raw_due_date)

            total_amt = float(inv.get("Total", 0.0))
            balance = float(inv.get("AmountDue", total_amt))
            currency = str(inv.get("CurrencyCode", "USD"))

            # Customer Profile extraction
            contact = inv.get("Contact", {})
            cust_id = str(contact.get("ContactID", "UNKNOWN_XERO_CONTACT"))
            cust_name = str(contact.get("Name", "Unknown Contact"))
            primary_email = str(contact.get("EmailAddress", "billing@customer.com"))

            phone: Optional[str] = None
            for p in contact.get("Phones", []):
                p_num = p.get("PhoneNumber")
                if p_num and not phone:
                    phone = p_num

            days_overdue = calculate_days_overdue(due_date, reference_date)
            aging_bucket = determine_aging_bucket(days_overdue)

            risk_score = cls._compute_risk_score(days_overdue, balance)
            avg_days_to_pay = max(30.0, 30.0 + (days_overdue if days_overdue > 0 else 0))

            customer = CustomerProfile(
                customer_id=cust_id,
                company_name=cust_name,
                primary_email=primary_email,
                phone_number=phone,
                preferred_channel="WHATSAPP" if phone else "EMAIL",
                total_outstanding=balance,
                average_days_to_pay=float(avg_days_to_pay),
                default_risk_score=risk_score,
            )

            # Summarize Line Items
            line_summaries: List[str] = []
            for item in inv.get("LineItems", []):
                desc = item.get("Description", "Product/Service")
                line_amt = float(item.get("LineAmount", item.get("UnitAmount", 0.0)))
                line_summaries.append(f"{desc} (${line_amt:,.2f})")

            normalized = NormalizedInvoice(
                invoice_id=f"XERO_{platform_id}",
                platform=PlatformSource.XERO,
                platform_invoice_id=platform_id,
                invoice_number=doc_number,
                issue_date=issue_date,
                due_date=due_date,
                total_amount=total_amt,
                balance_due=balance,
                currency=currency,
                days_overdue=days_overdue,
                aging_bucket=aging_bucket,
                customer=customer,
                line_items_summary=line_summaries,
            )
            normalized_list.append(normalized)

        return normalized_list

    @staticmethod
    def _compute_risk_score(days_overdue: int, balance: float) -> float:
        """
        Heuristic credit/delinquency risk score between 0.05 and 0.95.
        """
        if days_overdue <= 0:
            base = 0.10
        elif days_overdue <= 14:
            base = 0.25
        elif days_overdue <= 29:
            base = 0.45
        elif days_overdue <= 59:
            base = 0.70
        else:
            base = 0.90

        # Adjust slightly for high balances (> $10k)
        if balance > 10000.0:
            base = min(0.95, base + 0.05)

        return round(base, 2)
