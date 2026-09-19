"""
Manager handoff alert service formatting notifications for Slack, Teams, and Email.
"""

from typing import Any, Dict
from src.schemas.audit_schema import EscalationAlert


class HumanEscalationManager:
    """
    Formats structured human handoff alerts simulating Slack Block Kit
    and internal executive email notifications with actionable decision links.
    """

    def dispatch_manager_alert(self, alert: EscalationAlert) -> Dict[str, Any]:
        """
        Dispatches structured notification payloads for operations and finance teams.
        """
        priority_emoji = ":rotating_light:" if alert.risk_level in ["CRITICAL", "HIGH"] else ":warning:"

        slack_blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{priority_emoji} RevPulse Escalation Alert: Invoice {alert.invoice_id}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Customer ID:*\n{alert.customer_id}"},
                    {"type": "mrkdwn", "text": f"*Reason:*\n`{alert.reason.value}`"},
                    {"type": "mrkdwn", "text": f"*Risk Level:*\n*{alert.risk_level}*"},
                    {"type": "mrkdwn", "text": f"*Triggered At:*\n{alert.created_at.isoformat()}"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Incident Summary:*\n{alert.summary}\n\n*Recommended Action:*\n{alert.recommended_action}",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Take Over Thread"},
                        "style": "primary",
                        "url": f"https://app.revpulse.io/invoices/{alert.invoice_id}/takeover",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Halt Outreach"},
                        "style": "danger",
                        "url": f"https://app.revpulse.io/invoices/{alert.invoice_id}/pause",
                    },
                ],
            },
        ]

        email_payload = {
            "to": "ar-escalations@revpulse.internal",
            "subject": f"[{alert.risk_level}] Immediate AR Escalation Required - Invoice #{alert.invoice_id}",
            "body": (
                f"Attention AR Management,\n\n"
                f"An automated collection thread has been halted due to a compliance escalation trigger.\n\n"
                f"Invoice ID: {alert.invoice_id}\n"
                f"Customer ID: {alert.customer_id}\n"
                f"Reason: {alert.reason.value}\n"
                f"Severity: {alert.risk_level}\n"
                f"Summary: {alert.summary}\n"
                f"Recommended Next Action: {alert.recommended_action}\n\n"
                f"View complete history and manage account here: https://app.revpulse.io/invoices/{alert.invoice_id}"
            ),
        }

        return {
            "dispatched": True,
            "alert_id": alert.alert_id,
            "invoice_id": alert.invoice_id,
            "slack_payload": {"blocks": slack_blocks},
            "email_payload": email_payload,
            "status": "DISPATCHED",
        }
