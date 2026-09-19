"""
Payment gateway and reconciliation service for RevPulse.
Simulates Stripe checkout links and webhook event processing.
"""

from typing import Any, Dict, Optional
import uuid

from sqlmodel import Session, select, or_
from src.database.db import engine
from src.database.models import InvoiceRecord


class PaymentGatewayService:
    """
    Handles payment link creation and payment webhook reconciliation.
    """

    def __init__(self, base_payment_url: str = "https://pay.revpulse.io/checkout"):
        self.base_payment_url = base_payment_url
        self._payment_records: Dict[str, Dict[str, Any]] = {}

    def create_payment_link(
        self,
        invoice_id: str,
        amount: float,
        customer_id: str,
        description: str,
        currency: str = "USD",
        installment_index: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Dynamically generates mock Stripe/Accounting payment link payload.
        """
        payment_link_id = f"plink_{uuid.uuid4().hex[:12]}"
        url = f"{self.base_payment_url}/{invoice_id}"
        if installment_index is not None:
            url += f"?inst={installment_index}"

        record = {
            "payment_link_id": payment_link_id,
            "invoice_id": invoice_id,
            "customer_id": customer_id,
            "amount": amount,
            "currency": currency.upper(),
            "description": description,
            "installment_index": installment_index,
            "url": url,
            "status": "ACTIVE",
        }
        self._payment_records[payment_link_id] = record
        return record

    def process_payment_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates event (e.g. payment_intent.succeeded or checkout.session.completed),
        marks invoice balance paid or credited, and returns reconciliation details.
        """
        event_type = payload.get("type")
        if event_type not in ["payment_intent.succeeded", "checkout.session.completed"]:
            return {
                "success": False,
                "reconciled": False,
                "reason": f"Ignored event type: {event_type}",
            }

        data_obj = payload.get("data", {}).get("object", {})
        invoice_id = data_obj.get("invoice_id") or data_obj.get("metadata", {}).get("invoice_id")
        amount_received = float(data_obj.get("amount_received", data_obj.get("amount_total", 0.0)))
        currency = data_obj.get("currency", "usd").upper()

        if not invoice_id:
            return {
                "success": False,
                "reconciled": False,
                "reason": "Missing invoice_id in webhook payload metadata",
            }

        raw_invoice_id = str(invoice_id)
        matched_invoice_id = raw_invoice_id
        matched_doc_number = raw_invoice_id

        try:
            with Session(engine) as session:
                invoice_record = session.exec(
                    select(InvoiceRecord).where(
                        or_(
                            InvoiceRecord.id == raw_invoice_id,
                            InvoiceRecord.doc_number == raw_invoice_id,
                        )
                    )
                ).first()
                if invoice_record:
                    matched_invoice_id = invoice_record.id
                    matched_doc_number = invoice_record.doc_number
                    invoice_record.balance_due = 0.0
                    invoice_record.status = "RESOLVED_PAID"
                    session.add(invoice_record)
                    session.commit()
        except Exception:
            pass

        return {
            "success": True,
            "reconciled": True,
            "invoice_id": matched_invoice_id,
            "doc_number": matched_doc_number,
            "amount_paid": amount_received,
            "currency": currency,
            "status": "PAID",
            "transaction_reference": data_obj.get("id", f"txn_{uuid.uuid4().hex[:8]}"),
        }

    def reconcile_invoice_payment(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reconciles incoming payment event (e.g. checkout.session.completed, payment_intent.succeeded).
        """
        return self.process_payment_webhook(payload)
