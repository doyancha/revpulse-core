"""
Conversation state manager maintaining multi-turn context across AR recovery sessions.
Backbone storage powered by SQLModel with seamless fallback and memory caching.
"""

from typing import Dict, List, Optional
from datetime import datetime
import logging

from sqlmodel import Session, select

from src.database.db import engine
from src.database.models import ConversationThreadRecord, MessageRecord
from src.schemas.agent_schema import (
    ActionRequired,
    Intent,
    RevPulseAgentResponse,
)
from src.schemas.conversation_schema import (
    ChannelType,
    ConversationMessage,
    ConversationState,
    ConversationStatus,
    MessageRole,
)

logger = logging.getLogger("revpulse.state_manager")


class ConversationStateManager:
    """
    Manages recovery conversation threads with dual-layer SQLModel persistence
    and memory caching.
    """

    def __init__(self):
        self._threads: Dict[str, ConversationState] = {}

    def get_or_create_state(
        self,
        conversation_id: str,
        invoice_id: str,
        customer_id: str,
        channel: ChannelType = ChannelType.EMAIL,
    ) -> ConversationState:
        """
        Retrieves existing conversation state or initializes a new one.
        Checks memory cache first, then database, creating new state if absent.
        """
        if conversation_id in self._threads:
            return self._threads[conversation_id]

        # Check database
        try:
            with Session(engine) as session:
                record = session.get(ConversationThreadRecord, conversation_id)
                if record:
                    statement = (
                        select(MessageRecord)
                        .where(MessageRecord.thread_id == conversation_id)
                        .order_by(MessageRecord.created_at)
                    )
                    messages_db = session.exec(statement).all()
                    history = [
                        ConversationMessage(
                            role=MessageRole(m.role) if m.role in [r.value for r in MessageRole] else MessageRole.CUSTOMER,
                            channel=ChannelType(m.channel) if m.channel in [c.value for c in ChannelType] else ChannelType.EMAIL,
                            content=m.content,
                            timestamp=m.created_at,
                        )
                        for m in messages_db
                    ]

                    channel_val = ChannelType(record.channel) if record.channel in [c.value for c in ChannelType] else ChannelType.EMAIL
                    state = ConversationState(
                        conversation_id=record.id,
                        invoice_id=record.invoice_id,
                        customer_id=record.customer_id or customer_id,
                        channel=channel_val,
                        status=record.status,
                        turn_count=record.turn_count,
                        history=history,
                        active_settlement=None,
                        active_dispute=None,
                    )
                    self._threads[conversation_id] = state
                    return state
        except Exception as e:
            logger.warning(f"Database lookup failed for thread {conversation_id}: {e}")

        # Initialize new state
        new_state = ConversationState(
            conversation_id=conversation_id,
            invoice_id=invoice_id,
            customer_id=customer_id,
            channel=channel,
            status=ConversationStatus.ACTIVE.value,
            turn_count=0,
            history=[],
            active_settlement=None,
            active_dispute=None,
        )
        self._threads[conversation_id] = new_state

        # Persist to database
        try:
            with Session(engine) as session:
                db_record = ConversationThreadRecord(
                    id=conversation_id,
                    invoice_id=invoice_id,
                    customer_id=customer_id,
                    customer_name=customer_id,
                    channel=channel.value if hasattr(channel, "value") else str(channel),
                    status=ConversationStatus.ACTIVE.value,
                    risk_level="LOW",
                    turn_count=0,
                    unread_count=0,
                    updated_at=datetime.utcnow(),
                )
                session.add(db_record)
                session.commit()
        except Exception as e:
            logger.warning(f"Database persist failed for new thread {conversation_id}: {e}")

        return new_state

    def get_state(self, conversation_id: str) -> Optional[ConversationState]:
        """
        Retrieves existing state by conversation ID from memory or database.
        """
        if conversation_id in self._threads:
            return self._threads[conversation_id]

        try:
            with Session(engine) as session:
                record = session.get(ConversationThreadRecord, conversation_id)
                if record:
                    statement = (
                        select(MessageRecord)
                        .where(MessageRecord.thread_id == conversation_id)
                        .order_by(MessageRecord.created_at)
                    )
                    messages_db = session.exec(statement).all()
                    history = [
                        ConversationMessage(
                            role=MessageRole(m.role) if m.role in [r.value for r in MessageRole] else MessageRole.CUSTOMER,
                            channel=ChannelType(m.channel) if m.channel in [c.value for c in ChannelType] else ChannelType.EMAIL,
                            content=m.content,
                            timestamp=m.created_at,
                        )
                        for m in messages_db
                    ]
                    channel_val = ChannelType(record.channel) if record.channel in [c.value for c in ChannelType] else ChannelType.EMAIL
                    state = ConversationState(
                        conversation_id=record.id,
                        invoice_id=record.invoice_id,
                        customer_id=record.customer_id or "UNKNOWN",
                        channel=channel_val,
                        status=record.status,
                        turn_count=record.turn_count,
                        history=history,
                        active_settlement=None,
                        active_dispute=None,
                    )
                    self._threads[conversation_id] = state
                    return state
        except Exception as e:
            logger.warning(f"Database lookup failed for thread {conversation_id}: {e}")

        return None

    def append_message(
        self,
        conversation_id: str,
        role: MessageRole,
        content: str,
        channel: ChannelType,
    ) -> ConversationMessage:
        """
        Appends a message to the conversation history and increments turn count on customer turns.
        Persists message to database table.
        """
        if conversation_id not in self._threads:
            loaded = self.get_state(conversation_id)
            if not loaded:
                raise KeyError(f"Conversation {conversation_id} not initialized.")

        message = ConversationMessage(
            role=role,
            channel=channel,
            content=content,
            timestamp=datetime.utcnow(),
        )

        state = self._threads[conversation_id]
        state.history.append(message)
        if role == MessageRole.CUSTOMER:
            state.turn_count += 1

        # Persist message to database
        try:
            with Session(engine) as session:
                msg_record = MessageRecord(
                    thread_id=conversation_id,
                    role=role.value if hasattr(role, "value") else str(role),
                    channel=channel.value if hasattr(channel, "value") else str(channel),
                    content=content,
                    created_at=message.timestamp,
                )
                session.add(msg_record)

                # Update thread record
                thread_record = session.get(ConversationThreadRecord, conversation_id)
                if thread_record:
                    thread_record.updated_at = message.timestamp
                    thread_record.turn_count = state.turn_count
                    session.add(thread_record)
                session.commit()
        except Exception as e:
            logger.warning(f"Failed to persist message for thread {conversation_id} to DB: {e}")

        return message

    def update_state_with_response(
        self,
        conversation_id: str,
        agent_response: RevPulseAgentResponse,
    ) -> ConversationState:
        """
        Updates thread state according to AI decision (proposed settlements, disputes, status shifts).
        """
        state = self.get_or_create_state(
            conversation_id=conversation_id,
            invoice_id=getattr(self._threads.get(conversation_id), "invoice_id", "UNKNOWN"),
            customer_id=getattr(self._threads.get(conversation_id), "customer_id", "UNKNOWN"),
        )

        # Update settlement if generated
        if agent_response.proposed_settlement:
            state.active_settlement = agent_response.proposed_settlement
            state.status = ConversationStatus.RESOLVED_PLAN.value

        # Update dispute if categorized
        if agent_response.dispute_details or agent_response.intent == Intent.BILLING_DISPUTE:
            state.active_dispute = agent_response.dispute_details
            state.status = ConversationStatus.UNDER_DISPUTE.value

        # Handle escalation
        if agent_response.intent == Intent.HUMAN_ESCALATION or agent_response.action_required in [
            ActionRequired.FLAG_HUMAN_REVIEW,
            ActionRequired.NOTIFY_ACCOUNT_EXECUTIVE,
        ]:
            state.status = ConversationStatus.ESCALATED.value

        # Sync thread status to database
        try:
            with Session(engine) as session:
                thread_record = session.get(ConversationThreadRecord, conversation_id)
                if thread_record:
                    thread_record.status = state.status
                    session.add(thread_record)
                    session.commit()
        except Exception as e:
            logger.warning(f"Failed to update thread status in DB for {conversation_id}: {e}")

        # Append drafted message as AGENT turn
        channel_type = ChannelType(agent_response.drafted_communication.channel.value)
        self.append_message(
            conversation_id=conversation_id,
            role=MessageRole.AGENT,
            content=agent_response.drafted_communication.body,
            channel=channel_type,
        )

        return state

    def set_status(self, conversation_id: str, status: str) -> None:
        """Explicitly update the state status in memory and database."""
        if conversation_id in self._threads:
            self._threads[conversation_id].status = status

        try:
            with Session(engine) as session:
                thread_record = session.get(ConversationThreadRecord, conversation_id)
                if thread_record:
                    thread_record.status = status
                    session.add(thread_record)
                    session.commit()
        except Exception as e:
            logger.warning(f"Failed to set status in DB for {conversation_id}: {e}")

    def get_conversation_history(self, conversation_id: str) -> List[ConversationMessage]:
        """
        Retrieves transcript messages for the conversation.
        """
        if conversation_id in self._threads:
            return self._threads[conversation_id].history

        loaded = self.get_state(conversation_id)
        if loaded:
            return loaded.history
        return []
