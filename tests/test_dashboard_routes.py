"""
Unit and integration tests for Dashboard Routes.
Verifies:
1. GET /api/v1/dashboard/invoices returns live records from database (and auto-seeds if empty).
2. GET /api/v1/dashboard/metrics calculates KPIs directly from database InvoiceRecords.
3. Live payment reconciliation via Stripe immediately updates ledger and KPIs.
"""

from fastapi.testclient import TestClient
from sqlmodel import Session, select
import pytest

from src.main import app
from src.database.db import engine
from src.database.models import InvoiceRecord

client = TestClient(app)


def test_get_dashboard_invoices_seeds_and_returns_database_records():
    """Verify get_dashboard_invoices auto-seeds database and returns records reflecting DB state."""
    response = client.get("/api/v1/dashboard/invoices")
    assert response.status_code == 200
    invoices = response.json()
    assert len(invoices) >= 1

    first = invoices[0]
    assert "invoice_id" in first
    assert "doc_number" in first
    assert "balance_due" in first
    assert "status" in first

    # Verify records exist in database
    with Session(engine) as session:
        db_records = session.exec(select(InvoiceRecord)).all()
        assert len(db_records) == len(invoices)


def test_get_dashboard_metrics_calculates_from_database():
    """Verify get_dashboard_metrics calculates KPIs directly from InvoiceRecord."""
    response = client.get("/api/v1/dashboard/metrics")
    assert response.status_code == 200
    metrics = response.json()

    assert "total_outstanding" in metrics
    assert "actionable_overdue" in metrics
    assert "frozen_disputes" in metrics
    assert "total_ar" in metrics
    assert "overdue_balance" in metrics
    assert metrics["total_invoices"] >= 1
    assert metrics["total_outstanding"] > 0
    assert metrics["actionable_overdue"] > 0


def test_dashboard_reflects_live_payment_reconciliation():
    """Verify that reconciling an invoice immediately updates ledger balance_due and metric totals."""
    # 1. Fetch initial invoices and metrics
    inv_res = client.get("/api/v1/dashboard/invoices")
    assert inv_res.status_code == 200
    invoices = inv_res.json()
    target_invoice = invoices[0]
    target_id = target_invoice["invoice_id"]
    target_balance = target_invoice["balance_due"]

    metric_res_initial = client.get("/api/v1/dashboard/metrics")
    assert metric_res_initial.status_code == 200
    initial_metrics = metric_res_initial.json()
    initial_outstanding = initial_metrics["total_outstanding"]

    # 2. Reconcile target invoice via Stripe webhook
    payload = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_dash_recon",
                "customer": "CUST_TEST_DASH",
                "amount_total": target_balance,
                "currency": "usd",
                "metadata": {
                    "invoice_id": target_id,
                },
            }
        },
    }
    stripe_res = client.post("/api/v1/webhooks/stripe", json=payload)
    assert stripe_res.status_code == 200
    assert stripe_res.json()["status"] == "RECONCILED"

    # 3. Query ledger again: verify balance_due is 0.0 and status is RESOLVED_PAID
    inv_res_after = client.get("/api/v1/dashboard/invoices")
    assert inv_res_after.status_code == 200
    updated_invoices = inv_res_after.json()
    updated_target = next(i for i in updated_invoices if i["invoice_id"] == target_id)
    assert updated_target["balance_due"] == 0.0
    assert updated_target["status"] == "RESOLVED_PAID"

    # 4. Query metrics again: verify total_outstanding reduced by paid balance
    metric_res_after = client.get("/api/v1/dashboard/metrics")
    assert metric_res_after.status_code == 200
    updated_metrics = metric_res_after.json()
    assert round(updated_metrics["total_outstanding"], 2) == round(initial_outstanding - target_balance, 2)
    assert updated_metrics["reconciled_paid"] >= 1
