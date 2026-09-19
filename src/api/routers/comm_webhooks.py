import json
import logging
from typing import Any, Dict, Tuple
from urllib.parse import parse_qs
from fastapi import APIRouter, Depends, HTTPException, Request
from twilio.request_validator import RequestValidator

from config import settings
from src.api.dependencies import get_recovery_coordinator
from src.schemas.conversation_schema import ChannelType
from src.services.recovery_loop import RecoveryLoopCoordinator

logger = logging.getLogger("revpulse.comm_webhooks")

router = APIRouter(prefix="/webhooks", tags=["Communications Webhooks"])


async def _extract_request_data(request: Request) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Helper to extract payload and flat string params for signature validation."""
    content_type = request.headers.get("content-type", "")
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8") if body_bytes else ""

    if "application/json" in content_type:
        try:
            payload = json.loads(body_str) if body_str else {}
        except Exception:
            payload = {}
        params = {k: str(v) for k, v in payload.items() if not isinstance(v, (dict, list))}
        return payload, params
    elif "application/x-www-form-urlencoded" in content_type:
        parsed = parse_qs(body_str)
        params = {k: v[0] for k, v in parsed.items()}
        return params, params
    else:
        try:
            payload = json.loads(body_str) if body_str else {}
            params = {k: str(v) for k, v in payload.items() if not isinstance(v, (dict, list))}
            return payload, params
        except Exception:
            parsed = parse_qs(body_str)
            params = {k: v[0] for k, v in parsed.items()}
            return params, params


def _validate_twilio_signature(request: Request, params: Dict[str, str]) -> None:
    """Validates X-Twilio-Signature against request URL and parameters if auth token configured."""
    if not settings.TWILIO_AUTH_TOKEN:
        return

    signature = request.headers.get("X-Twilio-Signature")
    if not signature:
        logger.warning("Twilio webhook rejected: missing X-Twilio-Signature header.")
        raise HTTPException(status_code=401, detail="Missing X-Twilio-Signature header.")

    validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
    url = str(request.url)
    if not validator.validate(url, params, signature):
        logger.warning(f"Twilio webhook rejected: forged or invalid signature for {url}.")
        raise HTTPException(status_code=401, detail="Invalid Twilio signature.")


@router.post("/twilio")
async def handle_twilio_sms_webhook(
    request: Request,
    coordinator: RecoveryLoopCoordinator = Depends(get_recovery_coordinator),
) -> Dict[str, Any]:
    """
    Inbound Twilio SMS webhook with cryptographic validation.
    Extracts From, Body, and invoice metadata to run recovery loop.
    """
    payload, params = await _extract_request_data(request)
    _validate_twilio_signature(request, params)

    sender_id = payload.get("From", "+15550001122")
    message_body = payload.get("Body", "")
    invoice_id = payload.get("invoice_id") or payload.get("Metadata", {}).get("invoice_id", "INV-UNKNOWN")
    customer_id = payload.get("customer_id") or payload.get("Metadata", {}).get("customer_id", sender_id)

    invoice_context = payload.get("invoice_context") or {
        "invoice_id": invoice_id,
        "customer_id": customer_id,
        "recipient_contact": {"phone": sender_id, "preferred_channel": "SMS"},
        "financial_summary": {
            "balance_due": float(payload.get("balance_due", 1000.0)),
            "days_overdue": int(payload.get("days_overdue", 15)),
        },
    }

    conversation_id = payload.get("conversation_id", f"sms_{sender_id}_{invoice_id}")

    result = coordinator.process_inbound_message(
        conversation_id=conversation_id,
        invoice_context=invoice_context,
        customer_text=message_body,
        channel=ChannelType.SMS,
    )
    return result


@router.post("/whatsapp")
async def handle_whatsapp_webhook(
    request: Request,
    coordinator: RecoveryLoopCoordinator = Depends(get_recovery_coordinator),
) -> Dict[str, Any]:
    """
    Inbound WhatsApp Cloud API / Twilio WhatsApp webhook with cryptographic validation.
    """
    payload, params = await _extract_request_data(request)

    x_twilio_signature = request.headers.get("X-Twilio-Signature")
    dev_header = (
        request.headers.get("x-dev-test", "").lower() == "true"
        or request.headers.get("X-Dev-Test", "").lower() == "true"
    )

    is_dev_env = getattr(settings, "ENVIRONMENT", "development") == "development"
    should_bypass = is_dev_env and (
        x_twilio_signature == "dev-test-signature"
        or x_twilio_signature is None
        or dev_header
    )

    if not should_bypass:
        _validate_twilio_signature(request, params)
    else:
        logger.info("Development signature bypass active for WhatsApp webhook simulation.")

    # Extract message from WhatsApp Cloud API structure or flat testing format
    entry = payload.get("entry", [{}])[0] if isinstance(payload.get("entry"), list) else {}
    changes = entry.get("changes", [{}])[0] if isinstance(entry.get("changes"), list) else {}
    value = changes.get("value", {})
    messages = value.get("messages", [{}]) if isinstance(value.get("messages"), list) else [{}]
    wa_msg = messages[0] if messages else {}

    sender_id = wa_msg.get("from") or payload.get("from") or payload.get("From") or "+15559998877"
    message_body = (
        wa_msg.get("text", {}).get("body")
        if isinstance(wa_msg.get("text"), dict)
        else payload.get("body") or payload.get("Body", "")
    )
    invoice_id = payload.get("invoice_id", "INV-WA-001")
    customer_id = payload.get("customer_id", sender_id)

    invoice_context = payload.get("invoice_context") or {
        "invoice_id": invoice_id,
        "customer_id": customer_id,
        "recipient_contact": {"phone": sender_id, "preferred_channel": "WHATSAPP"},
        "financial_summary": {
            "balance_due": float(payload.get("balance_due", 2500.0)),
            "days_overdue": int(payload.get("days_overdue", 20)),
        },
    }

    conversation_id = payload.get("conversation_id", f"wa_{sender_id}_{invoice_id}")

    result = coordinator.process_inbound_message(
        conversation_id=conversation_id,
        invoice_context=invoice_context,
        customer_text=message_body,
        channel=ChannelType.WHATSAPP,
    )

    # Extract drafted message
    drafted_message = ""
    if isinstance(result, dict):
        drafted_message = (
            result.get("outbound_draft", {}).get("body")
            if isinstance(result.get("outbound_draft"), dict)
            else result.get("drafted_message", "")
        )
        result["drafted_message"] = drafted_message
    elif hasattr(result, "drafted_message"):
        drafted_message = getattr(result, "drafted_message")

    class _AgentResponseWrapper:
        def __init__(self, msg: str):
            self.drafted_message = msg

    agent_response = _AgentResponseWrapper(drafted_message)

    # Live outbound WhatsApp reply dispatching via Twilio REST Client
    if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
        try:
            from twilio.rest import Client

            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            raw_from = payload.get("From") or payload.get("from") or sender_id
            from_number = raw_from if str(raw_from).startswith("whatsapp:") else f"whatsapp:{raw_from}"
            target_number = payload.get("To") or payload.get("to") or f"whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}"
            if not str(target_number).startswith("whatsapp:"):
                target_number = f"whatsapp:{target_number}"

            client.messages.create(
                from_=target_number,
                to=from_number,
                body=agent_response.drafted_message,
            )
            logger.info(f"Dispatched live WhatsApp reply to {from_number} from {target_number}.")
        except Exception as e:
            logger.warning(f"Failed to dispatch live Twilio WhatsApp reply: {e}")

    return result


@router.post("/sendgrid")
async def sendgrid_inbound_webhook(
    request: Request,
    coordinator: RecoveryLoopCoordinator = Depends(get_recovery_coordinator),
) -> Dict[str, Any]:
    """
    Inbound SendGrid Inbound Parse JSON webhook simulation.
    """
    payload, _ = await _extract_request_data(request)

    sender_email = payload.get("from", "customer@client.com")
    message_body = payload.get("text") or payload.get("body", "")
    invoice_id = payload.get("invoice_id", "INV-SG-001")
    customer_id = payload.get("customer_id", sender_email)

    invoice_context = payload.get("invoice_context") or {
        "invoice_id": invoice_id,
        "customer_id": customer_id,
        "recipient_contact": {"email": sender_email, "preferred_channel": "EMAIL"},
        "financial_summary": {
            "balance_due": float(payload.get("balance_due", 5000.0)),
            "days_overdue": int(payload.get("days_overdue", 30)),
        },
    }

    conversation_id = payload.get("conversation_id", f"email_{sender_email}_{invoice_id}")

    result = coordinator.process_inbound_message(
        conversation_id=conversation_id,
        invoice_context=invoice_context,
        customer_text=message_body,
        channel=ChannelType.EMAIL,
    )
    return result


# Backward-compatible aliases
twilio_sms_webhook = handle_twilio_sms_webhook
whatsapp_webhook = handle_whatsapp_webhook
