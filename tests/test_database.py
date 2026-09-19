"""
Unit and integration tests for RevPulse SQLModel Database Architecture.
Covers:
1. Database schema initialization (`init_db`).
2. CRUD operations for `InvoiceRecord`.
3. CRUD operations for `ConversationThreadRecord` and `MessageRecord`.
4. CRUD operations for `AuditLogRecord`.
5. Multi-session state persistence and retrieval with `ConversationStateManager`.
6. Audit trail durability across logger instances with `AuditLogger`.
7. Resilient SQLite fallback when an unreachable PostgreSQL URL is provided.
8. FastAPI `get_session` dependency generator.
"""

from datetime import date, datetime
import pytest
from sqlmodel import Session, select

from src.database.db import engine, get_db_engine, get_session, init_db
from src.database.models import (
    AuditLogRecord,
    ConversationThreadRecord,
    InvoiceRecord,
    MessageRecord,
)
from src.schemas.conversation_schema import ChannelType, MessageRole
from src.services.audit_logger import AuditLogger
from src.services.state_manager import ConversationStateManager




def test_init_db_creates_tables():
    """Verify init_db registers all expected table names in metadata."""
    table_names = engine.dialect.get_table_names(engine.connect())
    expected = {"invoices", "conversation_threads", "messages", "audit_logs"}
    assert expected.issubset(set(table_names))


def test_invoice_record_crud():
    """Verify InvoiceRecord can be inserted, queried, and updated."""
    inv_id = "TEST_INV_DB_1001"
    with Session(engine) as session:
        # Delete if exists from prior test
        existing = session.get(InvoiceRecord, inv_id)
        if existing:
            session.delete(existing)
            session.commit()

        # Create
        record = InvoiceRecord(
            id=inv_id,
            doc_number="INV-DB-1001",
            platform="QUICKBOOKS",
            customer_name="Stark Industries",
            customer_email="tony@stark.com",
            customer_phone="+1-555-0199",
            total_amount=15000.00,
            balance_due=15000.00,
            due_date=date(2026, 8, 1),
            currency="USD",
            status="ACTIVE",
            days_overdue=45,
            aging_bucket="OVERDUE_30_PLUS",
            dispute_hold=False,
        )
        session.add(record)
        session.commit()

        # Read
        fetched = session.get(InvoiceRecord, inv_id)
        assert fetched is not None
        assert fetched.customer_name == "Stark Industries"
        assert fetched.total_amount == 15000.00
        assert fetched.days_overdue == 45

        # Update
        fetched.balance_due = 5000.00
        fetched.status = "PARTIAL_PAID"
        session.add(fetched)
        session.commit()

        updated = session.get(InvoiceRecord, inv_id)
        assert updated.balance_due == 5000.00
        assert updated.status == "PARTIAL_PAID"


def test_conversation_thread_and_message_records():
    """Verify thread and message records can be stored and linked."""
    thread_id = "thread_test_db_001"
    with Session(engine) as session:
        thread = ConversationThreadRecord(
            id=thread_id,
            invoice_id="TEST_INV_1001",
            customer_name="Wayne Enterprises",
            channel="EMAIL",
            status="ACTIVE",
            risk_level="MEDIUM",
        )
        session.add(thread)
        session.commit()

        msg = MessageRecord(
            thread_id=thread_id,
            role="CUSTOMER",
            channel="EMAIL",
            content="Can we pay this in two splits?",
            intent="PAYMENT_PLAN_REQUEST",
            confidence=0.96,
        )
        session.add(msg)
        session.commit()

        # Query messages for this thread
        statement = select(MessageRecord).where(MessageRecord.thread_id == thread_id)
        messages = session.exec(statement).all()
        assert len(messages) >= 1
        assert any(m.content == "Can we pay this in two splits?" for m in messages)


def test_audit_log_record_crud():
    """Verify AuditLogRecord persistence."""
    log_id = "test_log_rec_001"
    with Session(engine) as session:
        audit_record = AuditLogRecord(
            id=log_id,
            invoice_id="TEST_INV_9001",
            event_type="DISPUTE_SUBMITTED",
            channel="EMAIL",
            customer_input="Defective shipment received",
            response_summary="Dispute hold initiated",
            escalation_reason=None,
        )
        session.add(audit_record)
        session.commit()

        statement = select(AuditLogRecord).where(AuditLogRecord.id == log_id)
        fetched = session.exec(statement).first()
        assert fetched is not None
        assert fetched.invoice_id == "TEST_INV_9001"
        assert fetched.event_type == "DISPUTE_SUBMITTED"


def test_state_manager_cross_session_durability():
    """Verify ConversationStateManager persists to DB and a new instance can load state and messages."""
    thread_id = "conv_persist_test_888"
    invoice_id = "INV_PERSIST_888"
    customer_id = "CUST_PERSIST_888"

    # Instance 1: Create state and add messages
    manager1 = ConversationStateManager()
    state1 = manager1.get_or_create_state(
        conversation_id=thread_id,
        invoice_id=invoice_id,
        customer_id=customer_id,
        channel=ChannelType.EMAIL,
    )
    assert state1.conversation_id == thread_id

    manager1.append_message(
        conversation_id=thread_id,
        role=MessageRole.CUSTOMER,
        content="Hello, I received the past-due notice.",
        channel=ChannelType.EMAIL,
    )
    manager1.append_message(
        conversation_id=thread_id,
        role=MessageRole.AGENT,
        content="Thank you for reaching out. We can offer a 2-part installment plan.",
        channel=ChannelType.EMAIL,
    )

    # Instance 2: Brand new instance with empty internal memory
    manager2 = ConversationStateManager()
    assert thread_id not in manager2._threads

    # Load state from DB
    loaded_state = manager2.get_state(thread_id)
    assert loaded_state is not None
    assert loaded_state.conversation_id == thread_id
    assert loaded_state.invoice_id == invoice_id
    assert loaded_state.turn_count == 1
    assert len(loaded_state.history) == 2
    assert loaded_state.history[0].role == MessageRole.CUSTOMER
    assert loaded_state.history[0].content == "Hello, I received the past-due notice."
    assert loaded_state.history[1].role == MessageRole.AGENT


def test_audit_logger_cross_session_durability():
    """Verify AuditLogger persists events to DB and a new instance can retrieve the full trail."""
    invoice_id = "INV_AUDIT_PERSIST_777"
    customer_id = "CUST_777"

    # Logger 1: Record events
    logger1 = AuditLogger()
    logger1.log_event(
        event_type="INBOUND_MESSAGE",
        invoice_id=invoice_id,
        customer_id=customer_id,
        channel="WHATSAPP",
        raw_input="Need payment extension",
    )
    logger1.log_event(
        event_type="AI_DECISION",
        invoice_id=invoice_id,
        customer_id=customer_id,
        channel="WHATSAPP",
        response_summary="Generated 3-part plan",
    )

    # Logger 2: Fresh instance, empty in-memory log
    logger2 = AuditLogger()
    assert len(logger2._logs) == 0

    trail = logger2.get_invoice_audit_trail(invoice_id)
    assert len(trail) == 2
    assert trail[0].event_type == "INBOUND_MESSAGE"
    assert trail[0].raw_input == "Need payment extension"
    assert trail[1].event_type == "AI_DECISION"
    assert trail[1].response_summary == "Generated 3-part plan"


def test_sqlite_fallback_on_unreachable_db():
    """Verify get_db_engine falls back safely to SQLite when PostgreSQL is unreachable."""
    unreachable_url = "postgresql://user:pass@127.0.0.1:59999/nonexistent_db"
    fallback_engine = get_db_engine(unreachable_url)
    assert fallback_engine is not None
    # Engine dialect should fall back to sqlite
    assert fallback_engine.dialect.name == "sqlite"


def test_get_session_dependency():
    """Verify get_session generator yields an active Session."""
    session_gen = get_session()
    session = next(session_gen)
    assert isinstance(session, Session)
    assert session.is_active
    session_gen.close()
