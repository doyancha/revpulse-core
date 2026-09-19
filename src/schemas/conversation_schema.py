"""
Conversation state and multi-turn message schemas for RevPulse.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

from src.schemas.agent_schema import DisputeDetails, ProposedSettlement


class MessageRole(str, Enum):
    SYSTEM = "SYSTEM"
    AGENT = "AGENT"
    CUSTOMER = "CUSTOMER"


class ChannelType(str, Enum):
    WHATSAPP = "WHATSAPP"
    SMS = "SMS"
    EMAIL = "EMAIL"


class ConversationMessage(BaseModel):
    role: MessageRole = Field(..., description="Role of the sender (SYSTEM, AGENT, CUSTOMER)")
    channel: ChannelType = Field(..., description="Channel through which message was sent or received")
    content: str = Field(..., description="Raw text content of the message")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp of the message event"
    )


class ConversationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RESOLVED_PAID = "RESOLVED_PAID"
    RESOLVED_PLAN = "RESOLVED_PLAN"
    UNDER_DISPUTE = "UNDER_DISPUTE"
    ESCALATED = "ESCALATED"


class ConversationState(BaseModel):
    conversation_id: str = Field(..., description="Unique conversation thread identifier")
    invoice_id: str = Field(..., description="Associated normalized invoice ID")
    customer_id: str = Field(..., description="Customer / debtor identifier")
    channel: ChannelType = Field(..., description="Active communication channel")
    status: str = Field(
        default=ConversationStatus.ACTIVE.value,
        description="Current conversational recovery status (ACTIVE, RESOLVED_PAID, RESOLVED_PLAN, UNDER_DISPUTE, ESCALATED)"
    )
    turn_count: int = Field(default=0, ge=0, description="Total turns in this recovery thread")
    history: List[ConversationMessage] = Field(
        default_factory=list,
        description="Full sequential transcript of messages"
    )
    active_settlement: Optional[ProposedSettlement] = Field(
        default=None,
        description="Agreed or proposed structured settlement schedule"
    )
    active_dispute: Optional[DisputeDetails] = Field(
        default=None,
        description="Active dispute record if customer contested invoice"
    )
