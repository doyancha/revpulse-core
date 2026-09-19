"""
Unit and integration tests for Background Aging Reconciliation Scheduler.
Covers:
1. Scheduler initialization, job registration, and lifecycle start/shutdown.
2. Daily sync execution (run_daily_aging_sync):
   - Ingests QBO and Xero fixtures.
   - Triggers DUNNING_TRIGGERED events for actionable overdue accounts.
3. Verification that accounts on active hold or under dispute are skipped:
   - Sets thread status to UNDER_DISPUTE -> asserts skipped.
   - Sets thread status to RESOLVED_PAID -> asserts skipped.
   - Sets thread status to ESCALATED -> asserts skipped.
"""

from datetime import date
import pytest

from src.schemas.agent_schema import DisputeCategory, DisputeDetails
from src.schemas.conversation_schema import ChannelType, ConversationStatus
from src.services.audit_logger import AuditLogger
from src.services.orchestrator import ARPipelineOrchestrator
from src.services.scheduler import ARSchedulerService
from src.services.state_manager import ConversationStateManager


@pytest.mark.asyncio
async def test_scheduler_lifecycle():
    """Verify scheduler starts, registers job, and shuts down cleanly."""
    scheduler_service = ARSchedulerService()
    assert scheduler_service._is_running is False

    scheduler_service.start()
    assert scheduler_service._is_running is True
    job = scheduler_service.scheduler.get_job("revpulse_daily_aging_sync")
    assert job is not None
    assert job.name == "RevPulse Daily AR Aging Sync"

    scheduler_service.shutdown()
    assert scheduler_service._is_running is False


@pytest.mark.asyncio
async def test_daily_aging_sync_triggers_dunning():
    """Verify daily aging sync identifies delinquent accounts and records DUNNING_TRIGGERED events."""
    orchestrator = ARPipelineOrchestrator()
    state_manager = ConversationStateManager()
    audit_logger = AuditLogger()

    scheduler_service = ARSchedulerService(
        orchestrator=orchestrator,
        state_manager=state_manager,
        audit_logger=audit_logger,
    )

    ref_date = date(2026, 9, 19)
    result = await scheduler_service.run_daily_aging_sync(reference_date=ref_date)

    assert result["total_scanned"] >= 5
    assert result["total_delinquent_actionable"] >= 3
    assert result["triggered_count"] >= 3
    assert result["skipped_count"] == 0

    # Verify audit logger recorded DUNNING_TRIGGERED events
    all_logs = audit_logger._logs
    dunning_events = [log for log in all_logs if log.event_type == "DUNNING_TRIGGERED"]
    assert len(dunning_events) == result["triggered_count"]

    # Verify audit entry attributes
    first_dunning = dunning_events[0]
    assert first_dunning.metadata["days_overdue"] >= 7
    assert "balance_due" in first_dunning.metadata


@pytest.mark.asyncio
async def test_daily_sync_skips_dispute_and_holds():
    """
    Verify daily sync skips invoices that have active dispute holds,
    are under dispute, are resolved, or are escalated.
    """
    orchestrator = ARPipelineOrchestrator()
    state_manager = ConversationStateManager()
    audit_logger = AuditLogger()

    scheduler_service = ARSchedulerService(
        orchestrator=orchestrator,
        state_manager=state_manager,
        audit_logger=audit_logger,
    )

    # Pre-configure threads with skip statuses
    # 1. Invoice QBO_1001 under dispute
    state_dispute = state_manager.get_or_create_state(
        conversation_id="auto_QBO_1001_email",
        invoice_id="QBO_1001",
        customer_id="CUST-501",
        channel=ChannelType.EMAIL,
    )
    state_dispute.status = ConversationStatus.UNDER_DISPUTE.value
    state_dispute.active_dispute = DisputeDetails(
        category=DisputeCategory.DEFECTIVE_WORK,
        summary="Concrete defect",
        requires_invoice_hold=True,
    )

    # 2. Invoice QBO_1002 marked resolved paid
    state_paid = state_manager.get_or_create_state(
        conversation_id="auto_QBO_1002_whatsapp",
        invoice_id="QBO_1002",
        customer_id="CUST-502",
        channel=ChannelType.WHATSAPP,
    )
    state_paid.status = ConversationStatus.RESOLVED_PAID.value

    # 3. Invoice XERO_xero-inv-7001 escalated
    state_esc = state_manager.get_or_create_state(
        conversation_id="auto_XERO_xero-inv-7001_whatsapp",
        invoice_id="XERO_xero-inv-7001",
        customer_id="xero-cust-301",
        channel=ChannelType.WHATSAPP,
    )
    state_esc.status = ConversationStatus.ESCALATED.value

    ref_date = date(2026, 9, 19)
    result = await scheduler_service.run_daily_aging_sync(reference_date=ref_date)

    # 3 invoices should have been skipped
    assert result["skipped_count"] >= 3
    skipped_ids = [item["invoice_id"] for item in result["skipped_invoices"]]
    assert "QBO_1001" in skipped_ids
    assert "QBO_1002" in skipped_ids
    assert "XERO_xero-inv-7001" in skipped_ids
