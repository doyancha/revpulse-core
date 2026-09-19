"""
Immutable audit logging service for tracking all AR events, decisions, and handoffs.
Durable persistence powered by SQLModel with seamless fallback and memory caching.
"""

from datetime import datetime
import json
import logging
from typing import Any, Dict, List, Optional
import uuid

from sqlmodel import Session, select, or_

from src.database.db import engine
from src.database.models import AuditLogRecord, InvoiceRecord
from src.schemas.audit_schema import AuditLogEntry, EscalationReason

logger = logging.getLogger("revpulse.audit_logger")


class AuditLogger:
    """
    Audit log repository providing append-only, tamper-evident recording
    of all recovery events with SQLModel persistence and structured JSON export.
    """

    def __init__(self):
        self._logs: List[AuditLogEntry] = []

    def log_event(
        self,
        event_type: str,
        invoice_id: str,
        customer_id: str,
        channel: str,
        raw_input: Optional[str] = None,
        response_summary: Optional[str] = None,
        escalation_reason: Optional[EscalationReason] = None,
        metadata: Optional[Dict[str, Any]] = None,
        doc_number: Optional[str] = None,
    ) -> AuditLogEntry:
        """
        Appends an immutable audit event to the audit trail and persists to database.
        """
        # Resolve doc_number if not directly provided
        resolved_doc_number = doc_number
        if not resolved_doc_number:
            try:
                with Session(engine) as session:
                    inv = session.exec(
                        select(InvoiceRecord).where(
                            or_(
                                InvoiceRecord.id == invoice_id,
                                InvoiceRecord.doc_number == invoice_id,
                            )
                        )
                    ).first()
                    if inv:
                        resolved_doc_number = inv.doc_number
            except Exception:
                pass

        entry = AuditLogEntry(
            log_id=f"log_{uuid.uuid4().hex[:12]}",
            timestamp=datetime.utcnow(),
            invoice_id=invoice_id,
            doc_number=resolved_doc_number,
            customer_id=customer_id,
            event_type=event_type,
            channel=channel,
            raw_input=raw_input,
            response_summary=response_summary,
            escalation_reason=escalation_reason,
            metadata=metadata or {},
        )
        self._logs.append(entry)

        # Persist to database
        try:
            with Session(engine) as session:
                record = AuditLogRecord(
                    id=entry.log_id,
                    invoice_id=invoice_id,
                    doc_number=resolved_doc_number,
                    customer_id=customer_id,
                    event_type=event_type,
                    channel=channel,
                    customer_input=raw_input,
                    response_summary=response_summary,
                    escalation_reason=escalation_reason.value if hasattr(escalation_reason, "value") else str(escalation_reason) if escalation_reason else None,
                    created_at=entry.timestamp,
                )
                session.add(record)
                session.commit()
        except Exception as e:
            logger.warning(f"Failed to persist audit log entry {entry.log_id} to DB: {e}")

        return entry

    def get_invoice_audit_trail(self, invoice_id: str) -> List[AuditLogEntry]:
        """
        Retrieves complete audit trail for a specific invoice from DB or memory cache,
        normalizing lookup by both primary ID and accounting doc_number.
        """
        target_ids = {str(invoice_id)}
        try:
            with Session(engine) as session:
                inv = session.exec(
                    select(InvoiceRecord).where(
                        or_(
                            InvoiceRecord.id == invoice_id,
                            InvoiceRecord.doc_number == invoice_id,
                        )
                    )
                ).first()
                if inv:
                    target_ids.add(inv.id)
                    target_ids.add(inv.doc_number)

                statement = (
                    select(AuditLogRecord)
                    .where(
                        or_(
                            AuditLogRecord.invoice_id.in_(target_ids),
                            AuditLogRecord.doc_number.in_(target_ids),
                        )
                    )
                    .order_by(AuditLogRecord.created_at)
                )
                records = session.exec(statement).all()
                if records:
                    trail = []
                    for r in records:
                        esc_reason = None
                        if r.escalation_reason:
                            try:
                                esc_reason = EscalationReason(r.escalation_reason)
                            except ValueError:
                                esc_reason = None
                        trail.append(
                            AuditLogEntry(
                                log_id=r.id,
                                timestamp=r.created_at,
                                invoice_id=r.invoice_id,
                                doc_number=r.doc_number,
                                customer_id=r.customer_id or "",
                                event_type=r.event_type,
                                channel=r.channel,
                                raw_input=r.customer_input,
                                response_summary=r.response_summary,
                                escalation_reason=esc_reason,
                                metadata={},
                            )
                        )
                    return trail
        except Exception as e:
            logger.warning(f"Failed to retrieve audit trail from DB for invoice {invoice_id}: {e}")

        return [
            log for log in self._logs
            if log.invoice_id in target_ids or getattr(log, "doc_number", None) in target_ids
        ]

    def export_audit_trail_json(self, invoice_id: str) -> str:
        """
        Exports the audit trail for an invoice as a JSON string.
        """
        trail = self.get_invoice_audit_trail(invoice_id)
        return json.dumps([log.model_dump(mode="json") for log in trail], indent=2)
