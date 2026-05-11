"""
Email Sender Module
====================
Handles email dispatch via SMTP or dry-run logging.
Default mode is DRY-RUN to prevent accidental sends during testing.
"""

import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from src.config import (
    EMAIL_MODE,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USERNAME,
    SMTP_PASSWORD,
    SENDER_EMAIL,
    SENDER_NAME,
    OUTPUT_DIR,
)
from src.models import CreditRecord, GeneratedEmail, SendStatus

console = Console()


class EmailSender:
    """
    Email sender with SMTP and dry-run support.
    
    SECURITY: Default mode is 'dry_run' — no emails are sent.
    Switch to 'smtp' only in production with proper credentials.
    """

    def __init__(self, mode: str = None):
        self.mode = mode or EMAIL_MODE
        self.dry_run_log: list[dict] = []

        if self.mode == "dry_run":
            console.print("[yellow]📧 Email mode: DRY-RUN (no emails will be sent)[/yellow]")
        else:
            console.print("[green]📧 Email mode: SMTP (live sending enabled)[/green]")

    def send(
        self,
        record: CreditRecord,
        email: GeneratedEmail,
    ) -> SendStatus:
        """
        Send or simulate sending an email.
        
        Args:
            record: The credit record (for recipient info).
            email: The generated email content.
        
        Returns:
            SendStatus indicating the result.
        """
        if self.mode == "dry_run":
            return self._dry_run_send(record, email)
        elif self.mode == "smtp":
            return self._smtp_send(record, email)
        else:
            console.print(f"[red]Unknown email mode: {self.mode}[/red]")
            return SendStatus.FAILED

    def _dry_run_send(self, record: CreditRecord, email: GeneratedEmail) -> SendStatus:
        """Simulate sending — log the email instead of sending it."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "to": record.contact_email,
            "to_name": record.client_name,
            "invoice_no": record.invoice_no,
            "subject": email.subject,
            "body": email.body,
            "tone": email.tone_used,
            "stage": email.stage,
        }
        self.dry_run_log.append(log_entry)

        # Display preview
        console.print(Panel(
            f"[bold]To:[/bold] {record.client_name} <{record.contact_email}>\n"
            f"[bold]Subject:[/bold] {email.subject}\n"
            f"[bold]Tone:[/bold] {email.tone_used} (Stage {email.stage})\n"
            f"[dim]{'─' * 50}[/dim]\n"
            f"{email.body[:300]}{'...' if len(email.body) > 300 else ''}",
            title=f"📧 DRY-RUN: {record.invoice_no}",
            border_style="yellow",
        ))

        return SendStatus.DRY_RUN

    def _smtp_send(self, record: CreditRecord, email: GeneratedEmail) -> SendStatus:
        """Send email via SMTP."""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = email.subject
            msg["From"] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
            msg["To"] = f"{record.client_name} <{record.contact_email}>"

            # Create plain text and HTML versions
            text_part = MIMEText(email.body, "plain")
            msg.attach(text_part)

            # Send via SMTP
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)

            console.print(f"  [green]✅ Sent to {record.contact_email}[/green]")
            return SendStatus.SENT

        except smtplib.SMTPAuthenticationError:
            console.print(f"  [red]❌ SMTP authentication failed for {record.invoice_no}[/red]")
            return SendStatus.FAILED
        except smtplib.SMTPException as e:
            console.print(f"  [red]❌ SMTP error for {record.invoice_no}: {str(e)}[/red]")
            return SendStatus.FAILED
        except Exception as e:
            console.print(f"  [red]❌ Unexpected error sending {record.invoice_no}: {str(e)}[/red]")
            return SendStatus.FAILED

    def save_dry_run_log(self) -> Path | None:
        """Save the dry-run log to a JSON file."""
        if not self.dry_run_log:
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = OUTPUT_DIR / f"dry_run_log_{timestamp}.json"

        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(self.dry_run_log, f, indent=2, ensure_ascii=False)

        console.print(f"\n[green]💾 Dry-run log saved to: {log_path}[/green]")
        return log_path
