"""
Unit and integration tests for Phase 2: Accounting Data Mocking & Middleware Logic.
Covers:
- Aging bucket calculations and boundary conditions (0, 7, 15, 30, 60 days)
- QuickBooks Online (QBO) normalization from fixtures
- Xero normalization from fixtures (including legacy date formats)
- End-to-end pipeline filtering and AI context bundling
"""

from datetime import date
import json
from pathlib import Path
import pytest

from src.schemas.accounting_schema import (
    AgingBucket,
    PlatformSource,
    NormalizedInvoice,
)
from src.services.aging_engine import calculate_days_overdue, determine_aging_bucket
from src.services.normalizer import AccountingDataNormalizer
from src.services.orchestrator import ARPipelineOrchestrator

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# ============================================================================
# 1. Aging Calculation Tests
# ============================================================================
def test_aging_bucket_calculations():
    """Verify exact boundary conditions for aging engine."""
    ref_date = date(2026, 9, 19)

    # Future or due today (<= 0 days)
    assert calculate_days_overdue(date(2026, 9, 25), ref_date) == -6
    assert determine_aging_bucket(-6) == AgingBucket.CURRENT
    assert calculate_days_overdue(date(2026, 9, 19), ref_date) == 0
    assert determine_aging_bucket(0) == AgingBucket.CURRENT

    # 1 to 14 days overdue -> OVERDUE_7_PLUS
    assert calculate_days_overdue(date(2026, 9, 18), ref_date) == 1
    assert determine_aging_bucket(1) == AgingBucket.OVERDUE_7_PLUS
    assert calculate_days_overdue(date(2026, 9, 12), ref_date) == 7
    assert determine_aging_bucket(7) == AgingBucket.OVERDUE_7_PLUS
    assert calculate_days_overdue(date(2026, 9, 5), ref_date) == 14
    assert determine_aging_bucket(14) == AgingBucket.OVERDUE_7_PLUS

    # 15 to 29 days overdue -> OVERDUE_15_PLUS
    assert calculate_days_overdue(date(2026, 9, 4), ref_date) == 15
    assert determine_aging_bucket(15) == AgingBucket.OVERDUE_15_PLUS
    assert calculate_days_overdue(date(2026, 8, 21), ref_date) == 29
    assert determine_aging_bucket(29) == AgingBucket.OVERDUE_15_PLUS

    # 30 to 59 days overdue -> OVERDUE_30_PLUS
    assert calculate_days_overdue(date(2026, 8, 20), ref_date) == 30
    assert determine_aging_bucket(30) == AgingBucket.OVERDUE_30_PLUS
    assert calculate_days_overdue(date(2026, 7, 22), ref_date) == 59
    assert determine_aging_bucket(59) == AgingBucket.OVERDUE_30_PLUS

    # >= 60 days overdue -> OVERDUE_60_PLUS
    assert calculate_days_overdue(date(2026, 7, 21), ref_date) == 60
    assert determine_aging_bucket(60) == AgingBucket.OVERDUE_60_PLUS
    assert calculate_days_overdue(date(2026, 6, 1), ref_date) == 110
    assert determine_aging_bucket(110) == AgingBucket.OVERDUE_60_PLUS


# ============================================================================
# 2. QBO Normalization Tests
# ============================================================================
def test_qbo_normalization():
    """Verify normalization of realistic QBO payload from JSON fixture."""
    qbo_fixture_path = FIXTURES_DIR / "qbo_invoices.json"
    with open(qbo_fixture_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    ref_date = date(2026, 9, 19)
    normalizer = AccountingDataNormalizer()
    invoices = normalizer.normalize_qbo_payload(payload, reference_date=ref_date)

    assert len(invoices) == 3

    # Invoice 1: Due 2026-08-15 (35 days overdue as of 2026-09-19 -> OVERDUE_30_PLUS)
    inv1 = invoices[0]
    assert inv1.invoice_id == "QBO_1001"
    assert inv1.platform == PlatformSource.QUICKBOOKS
    assert inv1.invoice_number == "INV-QBO-1001"
    assert inv1.total_amount == 8500.0
    assert inv1.balance_due == 8500.0
    assert inv1.days_overdue == 35
    assert inv1.aging_bucket == AgingBucket.OVERDUE_30_PLUS
    assert inv1.customer.company_name == "Apex Civil Contracting LLC"
    assert inv1.customer.primary_email == "billing@apexcivil.com"
    assert inv1.customer.phone_number == "+1-512-555-0199"
    assert inv1.customer.preferred_channel == "EMAIL"
    assert len(inv1.line_items_summary) == 2
    assert "Phase 1 Foundation Excavation & Grading ($5,500.00)" in inv1.line_items_summary[0]

    # Invoice 2: Due 2026-09-04 (15 days overdue -> OVERDUE_15_PLUS)
    inv2 = invoices[1]
    assert inv2.invoice_id == "QBO_1002"
    assert inv2.days_overdue == 15
    assert inv2.aging_bucket == AgingBucket.OVERDUE_15_PLUS
    assert inv2.customer.preferred_channel == "WHATSAPP"

    # Invoice 3: Due 2026-09-25 (-6 days overdue -> CURRENT)
    inv3 = invoices[2]
    assert inv3.invoice_id == "QBO_1003"
    assert inv3.days_overdue == -6
    assert inv3.aging_bucket == AgingBucket.CURRENT


# ============================================================================
# 3. Xero Normalization Tests
# ============================================================================
def test_xero_normalization():
    """Verify normalization of realistic Xero payload from JSON fixture."""
    xero_fixture_path = FIXTURES_DIR / "xero_invoices.json"
    with open(xero_fixture_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    ref_date = date(2026, 9, 19)
    normalizer = AccountingDataNormalizer()
    invoices = normalizer.normalize_xero_payload(payload, reference_date=ref_date)

    assert len(invoices) == 3

    # Invoice 1: Due 2026-07-20 (61 days overdue -> OVERDUE_60_PLUS)
    inv1 = invoices[0]
    assert inv1.invoice_id == "XERO_xero-inv-7001"
    assert inv1.platform == PlatformSource.XERO
    assert inv1.total_amount == 8000.0
    assert inv1.balance_due == 8000.0
    assert inv1.days_overdue == 61
    assert inv1.aging_bucket == AgingBucket.OVERDUE_60_PLUS
    assert inv1.customer.company_name == "BluePeak Solar Energy Inc."
    assert inv1.customer.phone_number == "+1-415-555-9281"
    assert inv1.customer.preferred_channel == "WHATSAPP"
    assert len(inv1.line_items_summary) == 2
    assert "Commercial Inverter Installation & Wiring ($6,500.00)" in inv1.line_items_summary[0]

    # Invoice 2: Due 2026-09-02 (17 days overdue -> OVERDUE_15_PLUS)
    inv2 = invoices[1]
    assert inv2.days_overdue == 17
    assert inv2.aging_bucket == AgingBucket.OVERDUE_15_PLUS

    # Invoice 3: Due 2026-10-05 (-16 days overdue -> CURRENT)
    inv3 = invoices[2]
    assert inv3.days_overdue == -16
    assert inv3.aging_bucket == AgingBucket.CURRENT


# ============================================================================
# 4. Pipeline Filter & AI Context Bundling Tests
# ============================================================================
def test_pipeline_filter_and_context():
    """Verify orchestrator filters out non-delinquent invoices and generates valid AI context."""
    qbo_fixture_path = FIXTURES_DIR / "qbo_invoices.json"
    with open(qbo_fixture_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    ref_date = date(2026, 9, 19)
    orchestrator = ARPipelineOrchestrator()

    pipeline_result = orchestrator.run_mock_pipeline(
        raw_payload=payload,
        platform=PlatformSource.QUICKBOOKS,
        reference_date=ref_date,
        min_days_overdue=7,
    )

    assert pipeline_result["platform"] == "QUICKBOOKS"
    assert pipeline_result["total_scanned"] == 3
    # 2 are overdue >= 7 days (35 days and 15 days); the 3rd is CURRENT (-6 days)
    assert pipeline_result["total_delinquent_actionable"] == 2

    actionable_invoices = pipeline_result["actionable_invoices"]
    assert len(actionable_invoices) == 2

    # Check structure of bundled AI context for first actionable invoice
    first_actionable = actionable_invoices[0]
    ai_context = first_actionable["ai_engine_context"]

    assert ai_context["invoice_id"] == "QBO_1001"
    assert ai_context["customer_name"] == "Apex Civil Contracting LLC"
    assert ai_context["financial_summary"]["balance_due"] == 8500.0
    assert ai_context["financial_summary"]["days_overdue"] == 35
    assert ai_context["financial_summary"]["aging_bucket"] == "OVERDUE_30_PLUS"
    assert "default_risk_score" in ai_context["credit_health_metrics"]
    assert "historical_average_days_to_pay" in ai_context["credit_health_metrics"]
    assert len(ai_context["line_items"]) == 2
