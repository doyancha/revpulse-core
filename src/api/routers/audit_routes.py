"""
Router for audit log queries and conversation thread inspection.
"""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import get_audit_logger, get_state_manager
from src.schemas.audit_schema import AuditLogEntry
from src.schemas.conversation_schema import ConversationState
from src.services.audit_logger import AuditLogger
from src.services.state_manager import ConversationStateManager

router = APIRouter(tags=["Audit & Inspection"])


@router.get("/audit/{invoice_id}", response_model=List[AuditLogEntry])
async def get_invoice_audit_trail(
    invoice_id: str,
    audit_logger: AuditLogger = Depends(get_audit_logger),
) -> List[AuditLogEntry]:
    """
    Returns the complete immutable chronological audit trail for an invoice.
    """
    trail = audit_logger.get_invoice_audit_trail(invoice_id)
    return trail


@router.get("/conversation/{conversation_id}", response_model=ConversationState)
async def get_conversation_state(
    conversation_id: str,
    state_manager: ConversationStateManager = Depends(get_state_manager),
) -> ConversationState:
    """
    Returns the current multi-turn conversation state, message history, active settlement, or dispute status.
    """
    state = state_manager.get_state(conversation_id)
    if not state:
        raise HTTPException(
            status_code=404,
            detail=f"Conversation thread '{conversation_id}' not found.",
        )
    return state
