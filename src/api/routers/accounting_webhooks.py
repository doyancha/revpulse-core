"""
Router for accounting platform webhooks (QuickBooks Online and Xero).
"""

from typing import Any, Dict
from fastapi import APIRouter, Depends

from src.api.dependencies import get_orchestrator
from src.schemas.accounting_schema import PlatformSource
from src.services.orchestrator import ARPipelineOrchestrator

router = APIRouter(prefix="/webhooks", tags=["Accounting Webhooks"])


@router.post("/quickbooks")
async def quickbooks_webhook(
    payload: Dict[str, Any],
    orchestrator: ARPipelineOrchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """
    Ingests raw QuickBooks Online QueryResponse or change event payload,
    normalizes the records, and filters delinquent actionable accounts.
    """
    pipeline_result = orchestrator.run_mock_pipeline(
        raw_payload=payload,
        platform=PlatformSource.QUICKBOOKS,
    )
    return {
        "status": "PROCESSED",
        "platform": PlatformSource.QUICKBOOKS.value,
        "processed_count": pipeline_result["total_scanned"],
        "actionable_count": pipeline_result["total_delinquent_actionable"],
        "actionable_invoices": pipeline_result["actionable_invoices"],
    }


@router.post("/xero")
async def xero_webhook(
    payload: Dict[str, Any],
    orchestrator: ARPipelineOrchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """
    Ingests raw Xero API Invoices payload, normalizes the records,
    and filters delinquent actionable accounts.
    """
    pipeline_result = orchestrator.run_mock_pipeline(
        raw_payload=payload,
        platform=PlatformSource.XERO,
    )
    return {
        "status": "PROCESSED",
        "platform": PlatformSource.XERO.value,
        "processed_count": pipeline_result["total_scanned"],
        "actionable_count": pipeline_result["total_delinquent_actionable"],
        "actionable_invoices": pipeline_result["actionable_invoices"],
    }
