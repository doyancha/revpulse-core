"""
Router for payment gateway webhooks (Stripe).
Includes live sandbox cryptographic signature verification with permissive fallback.
"""

import json
import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Request
import stripe

from config import settings
from src.api.dependencies import get_audit_logger, get_payment_gateway, get_state_manager
from src.schemas.conversation_schema import ConversationStatus
from src.services.audit_logger import AuditLogger
from src.services.payment_gateway import PaymentGatewayService
from src.services.state_manager import ConversationStateManager

logger = logging.getLogger("revpulse.payment_webhooks")

router = APIRouter(prefix="/webhooks", tags=["Payment Webhooks"])


@router.post("/stripe")
async def handle_stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature"),
    payment_gateway: PaymentGatewayService = Depends(get_payment_gateway),
    state_manager: ConversationStateManager = Depends(get_state_manager),
    audit_logger: AuditLogger = Depends(get_audit_logger),
) -> Dict[str, Any]:
    """
    Handles Stripe payment success events (e.g. checkout.session.completed, payment_intent.succeeded).
    Validates Stripe-Signature if STRIPE_WEBHOOK_SECRET is set.
    Updates conversation state to RESOLVED_PAID and records PAYMENT_RECONCILED audit log.
    """
    body_bytes = await request.body()

    if settings.STRIPE_WEBHOOK_SECRET:
        if not stripe_signature:
            logger.warning("Stripe webhook received without Stripe-Signature header.")
            raise HTTPException(status_code=400, detail="Missing Stripe-Signature header.")
        try:
            event = stripe.Webhook.construct_event(
                payload=body_bytes,
                sig_header=stripe_signature,
                secret=settings.STRIPE_WEBHOOK_SECRET,
            )
            # Normalize event to dict
            if isinstance(event, dict):
                payload = event
            elif hasattr(event, "to_dict_recursive"):
                payload = event.to_dict_recursive()
            else:
                payload = json.loads(body_bytes.decode("utf-8"))
        except stripe.error.SignatureVerificationError as e:
            logger.warning(f"Invalid Stripe webhook signature: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid Stripe signature: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to parse Stripe webhook: {e}")
            raise HTTPException(status_code=400, detail=f"Webhook parsing error: {str(e)}")
    else:
        # Permissive local mock / test mode
        try:
            payload = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    reconciliation = payment_gateway.reconcile_invoice_payment(payload)

    if not reconciliation.get("success"):
        raise HTTPException(
            status_code=400,
            detail=reconciliation.get("reason", "Payment reconciliation failed."),
        )

    invoice_id = reconciliation["invoice_id"]
    doc_number = reconciliation.get("doc_number", invoice_id)
    customer_id = payload.get("data", {}).get("object", {}).get("customer", "CUST-STRIPE")

    # Update any matching active conversation thread
    valid_ids = {invoice_id, doc_number}
    for conv_id, state in state_manager._threads.items():
        if state.invoice_id in valid_ids:
            state_manager.set_status(conv_id, ConversationStatus.RESOLVED_PAID.value)

    # Record immutable audit entry
    audit_logger.log_event(
        event_type="PAYMENT_RECONCILED",
        invoice_id=invoice_id,
        doc_number=doc_number,
        customer_id=customer_id,
        channel="STRIPE",
        response_summary=f"Settled payment of ${reconciliation['amount_paid']:,.2f} {reconciliation['currency']}",
        metadata=reconciliation,
    )

    return {
        "status": "RECONCILED",
        "reconciliation": reconciliation,
    }


# Backward-compatible alias
stripe_webhook = handle_stripe_webhook
