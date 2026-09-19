"""
Middleware Orchestration service simulating Make.com/n8n daily sync pipelines.
"""

from datetime import date
from typing import Any, Dict, List, Optional

from src.schemas.accounting_schema import (
    AgingBucket,
    NormalizedInvoice,
    PlatformSource,
)
from src.services.normalizer import AccountingDataNormalizer


class ARPipelineOrchestrator:
    """
    Orchestrates the synchronization, aging analysis, delinquency filtering,
    and context bundling pipeline for the RevPulse Autonomous AR Recovery Engine.
    """

    def __init__(self, normalizer: Optional[AccountingDataNormalizer] = None):
        self.normalizer = normalizer or AccountingDataNormalizer()

    def sync_and_filter_delinquent(
        self,
        invoices: List[NormalizedInvoice],
        min_days_overdue: int = 7,
    ) -> List[NormalizedInvoice]:
        """
        Filter invoices that require automated AR action.
        Excludes CURRENT and invoices with zero balance.
        """
        delinquent_invoices = [
            inv
            for inv in invoices
            if inv.balance_due > 0
            and inv.days_overdue >= min_days_overdue
            and inv.aging_bucket != AgingBucket.CURRENT
        ]
        return delinquent_invoices

    def prepare_ai_context(self, invoice: NormalizedInvoice) -> Dict[str, Any]:
        """
        Constructs the exact structured context payload expected by RevPulseAIEngine.
        """
        return {
            "invoice_id": invoice.invoice_id,
            "invoice_number": invoice.invoice_number,
            "platform": invoice.platform.value,
            "customer_name": invoice.customer.company_name,
            "customer_id": invoice.customer.customer_id,
            "recipient_contact": {
                "email": invoice.customer.primary_email,
                "phone": invoice.customer.phone_number,
                "preferred_channel": invoice.customer.preferred_channel,
            },
            "financial_summary": {
                "total_amount": invoice.total_amount,
                "balance_due": invoice.balance_due,
                "currency": invoice.currency,
                "issue_date": invoice.issue_date.isoformat(),
                "due_date": invoice.due_date.isoformat(),
                "days_overdue": invoice.days_overdue,
                "aging_bucket": invoice.aging_bucket.value,
            },
            "credit_health_metrics": {
                "total_outstanding_portfolio": invoice.customer.total_outstanding,
                "historical_average_days_to_pay": invoice.customer.average_days_to_pay,
                "default_risk_score": invoice.customer.default_risk_score,
            },
            "line_items": invoice.line_items_summary,
        }

    def run_mock_pipeline(
        self,
        raw_payload: Dict[str, Any],
        platform: PlatformSource,
        reference_date: Optional[date] = None,
        min_days_overdue: int = 7,
    ) -> Dict[str, Any]:
        """
        Runs the end-to-end sync pipeline simulation:
        1. Ingests raw platform payload.
        2. Normalizes into unified schema with aging analysis.
        3. Filters actionable delinquent invoices.
        4. Bundles prepared AI context for each actionable invoice.
        """
        if platform == PlatformSource.QUICKBOOKS:
            normalized_invoices = self.normalizer.normalize_qbo_payload(
                raw_payload, reference_date=reference_date
            )
        elif platform == PlatformSource.XERO:
            normalized_invoices = self.normalizer.normalize_xero_payload(
                raw_payload, reference_date=reference_date
            )
        else:
            raise ValueError(f"Unsupported platform source: {platform}")

        actionable = self.sync_and_filter_delinquent(
            normalized_invoices, min_days_overdue=min_days_overdue
        )

        bundled_contexts = [
            {
                "normalized_invoice": inv.model_dump(mode="json"),
                "ai_engine_context": self.prepare_ai_context(inv),
                "preferred_channel": inv.customer.preferred_channel,
            }
            for inv in actionable
        ]

        return {
            "platform": platform.value,
            "total_scanned": len(normalized_invoices),
            "total_delinquent_actionable": len(actionable),
            "actionable_invoices": bundled_contexts,
        }
