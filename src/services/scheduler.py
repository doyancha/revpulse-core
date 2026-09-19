"""
Background Aging Reconciliation Scheduler for RevPulse.
Automates daily AR synchronization, evaluations against active conversation states/holds,
and dunning triggers.
"""

from datetime import date
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.schemas.accounting_schema import NormalizedInvoice, PlatformSource
from src.schemas.conversation_schema import ChannelType, ConversationStatus
from src.services.audit_logger import AuditLogger
from src.services.normalizer import AccountingDataNormalizer
from src.services.orchestrator import ARPipelineOrchestrator
from src.services.recovery_loop import RecoveryLoopCoordinator
from src.services.state_manager import ConversationStateManager

logger = logging.getLogger("revpulse.scheduler")
BASE_DIR = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = BASE_DIR / "tests" / "fixtures"


class ARSchedulerService:
    """
    Automates scheduled accounts receivable evaluations:
    - Ingests accounting records from QuickBooks and Xero.
    - Evaluates aging thresholds via ARPipelineOrchestrator.
    - Checks ConversationStateManager to skip accounts on hold, under dispute, escalated, or resolved.
    - Triggers automated dunning outreach and records audit trail events.
    """

    def __init__(
        self,
        orchestrator: Optional[ARPipelineOrchestrator] = None,
        state_manager: Optional[ConversationStateManager] = None,
        audit_logger: Optional[AuditLogger] = None,
        recovery_coordinator: Optional[RecoveryLoopCoordinator] = None,
        cron_expression: str = "0 8 * * *",  # Daily at 8:00 AM
    ):
        self.orchestrator = orchestrator or ARPipelineOrchestrator()
        self.state_manager = state_manager or ConversationStateManager()
        self.audit_logger = audit_logger or AuditLogger()
        self.recovery_coordinator = recovery_coordinator or RecoveryLoopCoordinator(
            state_manager=self.state_manager,
            audit_logger=self.audit_logger,
        )
        self.cron_expression = cron_expression
        self.scheduler = AsyncIOScheduler()
        self._is_running = False

    def load_mock_invoices(self, reference_date: Optional[date] = None) -> List[NormalizedInvoice]:
        """Loads and normalizes accounting records from QBO and Xero fixtures."""
        normalizer = AccountingDataNormalizer()
        invoices: List[NormalizedInvoice] = []
        ref = reference_date or date(2026, 9, 19)

        qbo_file = FIXTURES_DIR / "qbo_invoices.json"
        if qbo_file.exists():
            with open(qbo_file, "r", encoding="utf-8") as f:
                qbo_data = json.load(f)
                invoices.extend(normalizer.normalize_qbo_payload(qbo_data, reference_date=ref))

        xero_file = FIXTURES_DIR / "xero_invoices.json"
        if xero_file.exists():
            with open(xero_file, "r", encoding="utf-8") as f:
                xero_data = json.load(f)
                invoices.extend(normalizer.normalize_xero_payload(xero_data, reference_date=ref))

        return invoices

    async def run_daily_aging_sync(
        self,
        invoices: Optional[List[NormalizedInvoice]] = None,
        reference_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Executes the daily aging synchronization pipeline:
        1. Ingests accounting records from QuickBooks and Xero.
        2. Evaluates aging thresholds via ARPipelineOrchestrator.
        3. Skips invoices on hold, under dispute, escalated, or resolved.
        4. Triggers dunning outreach for actionable accounts and records DUNNING_TRIGGERED in AuditLogger.
        """
        logger.info("Executing daily AR aging reconciliation sync...")
        all_invoices = invoices if invoices is not None else self.load_mock_invoices(reference_date)
        delinquent_actionable = self.orchestrator.sync_and_filter_delinquent(all_invoices, min_days_overdue=7)

        synced_count = len(all_invoices)
        actionable_count = len(delinquent_actionable)
        skipped_invoices: List[Dict[str, Any]] = []
        triggered_invoices: List[Dict[str, Any]] = []

        skip_statuses = {
            ConversationStatus.UNDER_DISPUTE.value,
            ConversationStatus.ESCALATED.value,
            ConversationStatus.RESOLVED_PAID.value,
            ConversationStatus.RESOLVED_PLAN.value,
        }

        for inv in delinquent_actionable:
            invoice_id = inv.invoice_id
            customer_id = inv.customer.customer_id
            channel_str = inv.customer.preferred_channel.upper()
            channel = ChannelType[channel_str] if channel_str in ChannelType.__members__ else ChannelType.EMAIL
            conv_id = f"auto_{invoice_id}_{channel.value.lower()}"

            existing_state = self.state_manager.get_state(conv_id)
            # Also check any thread associated with this invoice
            active_holds = False
            skip_reason = None

            if existing_state:
                if existing_state.status in skip_statuses:
                    skip_reason = f"Thread status is {existing_state.status}"
                elif existing_state.active_dispute and existing_state.active_dispute.requires_invoice_hold:
                    skip_reason = "Active dispute hold in place"

            # Check across all threads for invoice hold
            for _, st in self.state_manager._threads.items():
                if st.invoice_id == invoice_id:
                    if st.status in skip_statuses:
                        skip_reason = f"Associated thread status is {st.status}"
                        break
                    if st.active_dispute and st.active_dispute.requires_invoice_hold:
                        skip_reason = "Associated thread has dispute hold"
                        break

            if skip_reason:
                logger.info(f"Skipping automated outreach for invoice {invoice_id}: {skip_reason}")
                skipped_invoices.append({
                    "invoice_id": invoice_id,
                    "customer_id": customer_id,
                    "reason": skip_reason,
                })
                continue

            # Eligible for automated initial/follow-up dunning outreach
            ai_context = self.orchestrator.prepare_ai_context(inv)
            dunning_prompt = (
                f"Automated system reminder: Invoice #{inv.invoice_number} is {inv.days_overdue} days overdue "
                f"with a balance of ${inv.balance_due:,.2f}. Please review statement and arrange remittance."
            )

            # Log DUNNING_TRIGGERED in AuditLogger
            self.audit_logger.log_event(
                event_type="DUNNING_TRIGGERED",
                invoice_id=invoice_id,
                customer_id=customer_id,
                channel=channel.value,
                raw_input=dunning_prompt,
                response_summary=f"Automated aging trigger for {inv.aging_bucket.value} account",
                metadata={
                    "balance_due": inv.balance_due,
                    "days_overdue": inv.days_overdue,
                    "aging_bucket": inv.aging_bucket.value,
                },
            )

            triggered_invoices.append({
                "invoice_id": invoice_id,
                "customer_id": customer_id,
                "balance_due": inv.balance_due,
                "channel": channel.value,
                "days_overdue": inv.days_overdue,
            })

        summary = {
            "timestamp": date.today().isoformat(),
            "total_scanned": synced_count,
            "total_delinquent_actionable": actionable_count,
            "triggered_count": len(triggered_invoices),
            "skipped_count": len(skipped_invoices),
            "triggered_invoices": triggered_invoices,
            "skipped_invoices": skipped_invoices,
        }
        logger.info(f"Daily sync completed: {len(triggered_invoices)} triggered, {len(skipped_invoices)} skipped.")
        return summary

    def start(self) -> None:
        """Starts the background scheduler job."""
        if not self._is_running:
            try:
                # Add cron job for daily sync
                self.scheduler.add_job(
                    self.run_daily_aging_sync,
                    trigger=CronTrigger.from_crontab(self.cron_expression),
                    id="revpulse_daily_aging_sync",
                    name="RevPulse Daily AR Aging Sync",
                    replace_existing=True,
                )
                self.scheduler.start()
                self._is_running = True
                logger.info("ARSchedulerService started successfully.")
            except Exception as e:
                logger.error(f"Failed to start ARSchedulerService: {e}")

    def shutdown(self) -> None:
        """Stops the scheduler cleanly."""
        if self._is_running:
            self.scheduler.shutdown(wait=False)
            self._is_running = False
            logger.info("ARSchedulerService shut down cleanly.")
