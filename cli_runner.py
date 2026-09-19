"""
Interactive Terminal Testbed & Simulation CLI for RevPulse Autonomous AR Recovery Engine.
"""

from datetime import date
import json
from pathlib import Path
import sys
from typing import List, Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


from config.settings import GEMINI_API_KEY, MODEL_NAME
from src.schemas.accounting_schema import NormalizedInvoice
from src.schemas.conversation_schema import ChannelType
from src.services.audit_logger import AuditLogger
from src.services.escalation_manager import HumanEscalationManager
from src.services.guardrails import ComplianceGuardrailsEngine
from src.services.normalizer import AccountingDataNormalizer
from src.services.orchestrator import ARPipelineOrchestrator
from src.services.payment_gateway import PaymentGatewayService
from src.services.recovery_loop import RecoveryLoopCoordinator
from src.services.state_manager import ConversationStateManager
from src.services.ai_engine import RevPulseAIEngine

console = Console()
BASE_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = BASE_DIR / "tests" / "fixtures"


def load_all_fixtures() -> List[NormalizedInvoice]:
    """Loads and normalizes sample invoices from QBO and Xero fixtures."""
    normalizer = AccountingDataNormalizer()
    invoices: List[NormalizedInvoice] = []
    ref_date = date(2026, 9, 19)

    qbo_file = FIXTURES_DIR / "qbo_invoices.json"
    if qbo_file.exists():
        with open(qbo_file, "r", encoding="utf-8") as f:
            qbo_data = json.load(f)
            invoices.extend(normalizer.normalize_qbo_payload(qbo_data, reference_date=ref_date))

    xero_file = FIXTURES_DIR / "xero_invoices.json"
    if xero_file.exists():
        with open(xero_file, "r", encoding="utf-8") as f:
            xero_data = json.load(f)
            invoices.extend(normalizer.normalize_xero_payload(xero_data, reference_date=ref_date))

    return invoices


def display_invoice_table(invoices: List[NormalizedInvoice]) -> None:
    """Renders formatted table of loaded invoices."""
    table = Table(title="[bold cyan]RevPulse Available Invoices for Simulation[/bold cyan]")
    table.add_column("#", justify="center", style="dim", width=4)
    table.add_column("Invoice #", style="bold")
    table.add_column("Platform", style="magenta")
    table.add_column("Customer Name", style="white")
    table.add_column("Balance Due", justify="right", style="green")
    table.add_column("Days Overdue", justify="right", style="yellow")
    table.add_column("Aging Bucket", style="cyan")
    table.add_column("Preferred Channel", style="blue")

    for idx, inv in enumerate(invoices, start=1):
        table.add_row(
            str(idx),
            inv.invoice_number,
            inv.platform.value,
            inv.customer.company_name,
            f"${inv.balance_due:,.2f}",
            str(inv.days_overdue),
            inv.aging_bucket.value,
            inv.customer.preferred_channel,
        )

    console.print(table)


def display_audit_trail(audit_logger: AuditLogger, invoice_id: str) -> None:
    """Renders formatted table of audit log events for an invoice."""
    trail = audit_logger.get_invoice_audit_trail(invoice_id)
    if not trail:
        console.print(f"[yellow]No audit records found for invoice {invoice_id}.[/yellow]")
        return

    table = Table(title=f"[bold green]Audit Trail: Invoice {invoice_id}[/bold green]")
    table.add_column("Timestamp (UTC)", style="dim")
    table.add_column("Event Type", style="bold magenta")
    table.add_column("Channel", style="blue")
    table.add_column("Customer Input / Prompt", style="white", max_width=35)
    table.add_column("Response / Action Summary", style="cyan", max_width=45)
    table.add_column("Escalation", style="red")

    for entry in trail:
        esc = entry.escalation_reason.value if entry.escalation_reason else "-"
        table.add_row(
            entry.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            entry.event_type,
            entry.channel,
            entry.raw_input or "-",
            entry.response_summary or "-",
            esc,
        )

    console.print(table)


def run_cli_session(
    invoices: Optional[List[NormalizedInvoice]] = None,
    interactive: bool = True,
    coordinator: Optional[RecoveryLoopCoordinator] = None,
) -> None:
    """Runs the simulation REPL session."""
    if invoices is None:
        invoices = load_all_fixtures()

    if not invoices:
        console.print("[red]Error: No invoices found in fixtures.[/red]")
        return

    orchestrator = ARPipelineOrchestrator()
    delinquent_invoices = orchestrator.sync_and_filter_delinquent(invoices, min_days_overdue=7)
    usable_invoices = delinquent_invoices if delinquent_invoices else invoices

    if coordinator is None:
        ai_engine = RevPulseAIEngine()
        state_manager = ConversationStateManager()
        payment_gateway = PaymentGatewayService()
        guardrails = ComplianceGuardrailsEngine()
        audit_logger = AuditLogger()
        escalation_manager = HumanEscalationManager()

        coordinator = RecoveryLoopCoordinator(
            ai_engine=ai_engine,
            state_manager=state_manager,
            payment_gateway=payment_gateway,
            guardrails=guardrails,
            audit_logger=audit_logger,
            escalation_manager=escalation_manager,
        )

    console.print(Panel.fit(
        f"[bold cyan]RevPulse Autonomous AR Recovery Engine[/bold cyan]\n"
        f"[dim]Model: {MODEL_NAME} | API Key Configured: {'Yes' if GEMINI_API_KEY else 'No'}[/dim]\n"
        f"[green]Interactive Multi-Turn Simulation CLI[/green]",
        border_style="cyan"
    ))

    display_invoice_table(usable_invoices)

    if not interactive:
        console.print("[dim]Running in non-interactive mode. Setup verified successfully.[/dim]")
        return

    # Select invoice
    console.print("\n[bold yellow]Select an invoice by number (default: 1):[/bold yellow] ", end="")
    choice = input().strip()
    idx = int(choice) - 1 if choice.isdigit() and 1 <= int(choice) <= len(usable_invoices) else 0
    selected_invoice = usable_invoices[idx]

    # Select channel
    console.print("[bold yellow]Select channel (1: WHATSAPP, 2: SMS, 3: EMAIL, default: 1):[/bold yellow] ", end="")
    ch_choice = input().strip()
    channel_map = {"1": ChannelType.WHATSAPP, "2": ChannelType.SMS, "3": ChannelType.EMAIL}
    channel = channel_map.get(ch_choice, ChannelType.WHATSAPP)

    ai_context = orchestrator.prepare_ai_context(selected_invoice)
    conversation_id = f"sim_{selected_invoice.invoice_id}_{channel.value.lower()}"

    console.print(Panel(
        f"[bold]Active Thread Initialized[/bold]\n"
        f"Invoice: [cyan]{selected_invoice.invoice_number}[/cyan] ({selected_invoice.invoice_id})\n"
        f"Customer: [white]{selected_invoice.customer.company_name}[/white]\n"
        f"Outstanding Balance: [green]${selected_invoice.balance_due:,.2f}[/green]\n"
        f"Days Overdue: [yellow]{selected_invoice.days_overdue} days[/yellow] ([dim]{selected_invoice.aging_bucket.value}[/dim])\n"
        f"Channel: [magenta]{channel.value}[/magenta]\n\n"
        f"[dim]Commands: 'exit' to quit | 'audit' to view log | 'status' for thread info[/dim]",
        border_style="blue"
    ))

    # Multi-turn interaction loop
    while True:
        try:
            console.print("\n[bold green][Customer][/bold green] > ", end="")
            user_input = input().strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Session interrupted.[/yellow]")
            break

        if not user_input:
            continue

        cmd = user_input.lower()
        if cmd == "exit":
            # Save audit trail to disk upon exit
            export_file = BASE_DIR / f"audit_export_{selected_invoice.invoice_id}.json"
            export_content = coordinator.audit_logger.export_audit_trail_json(selected_invoice.invoice_id)
            with open(export_file, "w", encoding="utf-8") as f:
                f.write(export_content)
            console.print(f"[bold green]Audit trail saved to {export_file}[/bold green]")
            display_audit_trail(coordinator.audit_logger, selected_invoice.invoice_id)
            console.print("[cyan]Exiting RevPulse CLI Runner. Goodbye![/cyan]")
            break

        elif cmd == "audit":
            display_audit_trail(coordinator.audit_logger, selected_invoice.invoice_id)
            continue

        elif cmd == "status":
            state = coordinator.state_manager.get_state(conversation_id)
            status_text = state.status if state else "UNKNOWN"
            turn_count = state.turn_count if state else 0
            console.print(f"[cyan]Thread ID: {conversation_id} | Status: {status_text} | Turns: {turn_count}[/cyan]")
            continue

        # Process turn through recovery loop
        try:
            with console.status("[bold cyan]RevPulse AI Brain thinking...[/bold cyan]", spinner="dots"):
                response = coordinator.process_inbound_message(
                    conversation_id=conversation_id,
                    invoice_context=ai_context,
                    customer_text=user_input,
                    channel=channel,
                )
        except Exception as e:
            console.print(Panel(
                f"[bold red]API Error:[/bold red] {e}\nPlease wait a moment and try your message again.",
                title="[bold yellow]Upstream Connection Issue[/bold yellow]",
                border_style="red"
            ))
            continue

        # Format output

        intent = response.get("intent", "UNKNOWN")
        risk = response.get("risk_level", "LOW")
        conf = response.get("confidence_score", 1.0) * 100
        state_status = response.get("state_status", "ACTIVE")
        outbound = response.get("outbound_draft", {})
        actions = response.get("executed_actions", {})

        badges = (
            f"[bold blue]Intent:[/bold blue] {intent}  |  "
            f"[bold yellow]Confidence:[/bold yellow] {conf:.1f}%  |  "
            f"[bold red]Risk:[/bold red] {risk}  |  "
            f"[bold magenta]Status:[/bold magenta] {state_status}"
        )

        body_text = outbound.get("body", "")
        formatted_md = Markdown(body_text)

        extra_info = []
        if "payment_link" in actions:
            extra_info.append(f"[bold green]Stripe Link Generated:[/bold green] {actions['payment_link'].get('url')}")
        if "first_installment_link" in actions:
            extra_info.append(f"[bold green]Installment 1 Payment Link:[/bold green] {actions['first_installment_link'].get('url')}")
        if "dispute_ticket" in actions:
            extra_info.append(f"[bold red]Dispute Ticket Opened:[/bold red] {actions['dispute_ticket'].get('ticket_id')} (Invoice Hold: ON)")
        if "escalation_alert" in actions:
            extra_info.append(f"[bold red]Human Manager Alert Dispatched:[/bold red] Escalation Reason = {response.get('escalation_reason')}")

        # Channel color mapping
        channel_val = outbound.get("channel", channel.value).upper()
        channel_color_map = {
            "WHATSAPP": "green",
            "EMAIL": "blue",
            "SMS": "yellow",
        }
        card_color = channel_color_map.get(channel_val, "cyan")

        # Telemetry badges
        console.print(Panel(
            badges,
            title="[bold cyan]RevPulse Decision Telemetry[/bold cyan]",
            border_style="cyan"
        ))

        # Distinct Outbound Communication Panel with channel-coded styling
        channel_icon = "📱" if channel_val in ["WHATSAPP", "SMS"] else "✉️"
        
        if channel_val == "EMAIL":
            customer_name_val = selected_invoice.customer.company_name if hasattr(selected_invoice, "customer") else "Client"
            recipient_email_val = outbound.get("recipient") or (selected_invoice.customer.primary_email if hasattr(selected_invoice, "customer") else "billing@client.com")
            doc_num_val = selected_invoice.invoice_number if hasattr(selected_invoice, "invoice_number") else "INV-001"
            email_header_text = (
                f"[bold cyan]TO:[/bold cyan] {customer_name_val} <{recipient_email_val}>\n"
                f"[bold cyan]RE:[/bold cyan] Commercial Debt Resolution Notice — Invoice #{doc_num_val}\n"
                f"[dim]------------------------------------------------------------[/dim]\n\n"
            )
            from rich.console import Group
            email_content_group = Group(
                Text.from_markup(email_header_text),
                formatted_md,
            )
            console.print(Panel(
                email_content_group,
                title=f"[bold {card_color}]{channel_icon} Executive Email Memo ({channel_val})[/bold {card_color}]",
                subtitle=f"[dim]Recipient: {recipient_email_val} | Invoice #{doc_num_val}[/dim]",
                border_style=card_color
            ))
        else:
            console.print(Panel(
                formatted_md,
                title=f"[bold {card_color}]{channel_icon} Drafted Outbound Communication ({channel_val})[/bold {card_color}]",
                subtitle=f"[dim]Recipient: {outbound.get('recipient', 'Client')} | Subject: {outbound.get('subject', 'N/A')}[/dim]",
                border_style=card_color
            ))


        # Specialized Table: Installment Settlement Schedule
        if "installment_schedule" in actions:
            sched = actions["installment_schedule"]
            installments_list = sched.get("installments", [])
            first_link = actions.get("first_installment_link", {}).get("url", "N/A")

            inst_table = Table(title="[bold green]💳 Approved Installment Settlement Breakdown[/bold green]")
            inst_table.add_column("Split #", justify="center", style="bold cyan", width=8)
            inst_table.add_column("Due Date", justify="center", style="yellow")
            inst_table.add_column("Installment Amount", justify="right", style="bold green")
            inst_table.add_column("Remittance Link", style="blue")

            for i_idx, inst in enumerate(installments_list, start=1):
                link_val = first_link if i_idx == 1 else f"{first_link.split('?')[0]}?inst={i_idx}"
                inst_table.add_row(
                    f"#{i_idx}",
                    str(inst.get("due_date", "TBD")),
                    f"${float(inst.get('amount', 0.0)):,.2f}",
                    link_val,
                )
            console.print(inst_table)

        # Specialized Dispute Hold Certificate
        if "dispute_ticket" in actions or intent == "BILLING_DISPUTE":
            ticket = actions.get("dispute_ticket", {})
            ticket_id = ticket.get("ticket_id", f"TICK-DISP-{selected_invoice.invoice_id}")
            cat = ticket.get("details", {}).get("category", "DEFECTIVE_WORK")

            console.print(Panel(
                f"[bold red]⚠️  DISPUTE ACTIVE: INVOICE DUNNING AND LATE FEES FROZEN[/bold red]\n\n"
                f"  • [bold]Ticket ID:[/bold] [yellow]{ticket_id}[/yellow]\n"
                f"  • [bold]Dispute Category:[/bold] {cat}\n"
                f"  • [bold]Invoice Hold:[/bold] [bold green]ACTIVE (Automated Notices Halted)[/bold green]\n"
                f"  • [bold]SLA Resolution Window:[/bold] 2 Business Days\n"
                f"  • [bold]Assigned Queue:[/bold] Technical & Operational Dispute Resolution",
                title="[bold red]🔒 Formal Dispute Hold Certificate[/bold red]",
                border_style="red"
            ))

        if extra_info:
            console.print(Panel(
                "\n".join(extra_info),
                title="[bold yellow]Automated Actions Executed[/bold yellow]",
                border_style="yellow"
            ))




if __name__ == "__main__":
    run_cli_session()
