"""
Main Agent Orchestrator
========================
Coordinates the full pipeline: data ingestion → email generation →
email sending/dry-run → audit logging. This is the core agent logic
that ties all modules together.
"""

import uuid
from datetime import datetime

from rich.console import Console
from rich.panel import Panel

from src.config import (
    MAX_EMAILS_PER_RUN,
    ESCALATION_MATRIX,
    get_escalation_stage,
    validate_config,
    EMAIL_MODE,
)
from src.models import CreditRecord, GeneratedEmail, SendStatus, AgentRunSummary
from src.data_ingestion import load_credit_records, display_records_table, get_overdue_records
from src.email_generator import generate_email
from src.email_sender import EmailSender
from src.audit_trail import init_database, log_email, display_audit_table, get_audit_logs

console = Console()


class FinanceCreditAgent:
    """
    Finance Credit Follow-Up Email Agent
    
    Orchestrates the entire pipeline:
    1. Load credit records from CSV/Excel
    2. Identify overdue records
    3. Determine escalation stage for each
    4. Generate personalised emails via LLM
    5. Send or dry-run emails
    6. Log everything to audit trail
    """

    def __init__(self, data_file: str = None):
        """
        Initialize the agent.
        
        Args:
            data_file: Path to the credit records CSV/Excel file.
                       Defaults to data/sample_credits.csv
        """
        self.data_file = data_file or "data/sample_credits.csv"
        self.run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self.sender = EmailSender()
        self.summary = AgentRunSummary(
            run_id=self.run_id,
            timestamp=datetime.now(),
        )

        # Validate configuration
        warnings = validate_config()
        if warnings:
            for w in warnings:
                console.print(f"[yellow]{w}[/yellow]")

    def run(self) -> AgentRunSummary:
        """
        Execute the full agent pipeline.
        
        Returns:
            AgentRunSummary with statistics about the run.
        """
        console.print(Panel(
            f"[bold white]Finance Credit Follow-Up Email Agent[/bold white]\n"
            f"[dim]Run ID: {self.run_id}[/dim]\n"
            f"[dim]Mode: {EMAIL_MODE.upper()}[/dim]\n"
            f"[dim]Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]",
            title="🚀 Agent Starting",
            border_style="blue",
        ))

        # Step 1: Initialize database
        init_database()

        # Step 2: Load credit records
        console.print("\n[bold]Step 1: Loading credit records...[/bold]")
        try:
            records = load_credit_records(self.data_file)
        except (FileNotFoundError, ValueError) as e:
            console.print(f"[red]❌ Data load failed: {e}[/red]")
            self.summary.errors.append(str(e))
            return self.summary

        self.summary.total_records_processed = len(records)
        display_records_table(records)

        # Step 3: Filter overdue records
        console.print("\n[bold]Step 2: Identifying overdue records...[/bold]")
        overdue = get_overdue_records(records)

        if not overdue:
            console.print("[green]🎉 No overdue records! Nothing to do.[/green]")
            return self.summary

        # Safety cap
        if len(overdue) > MAX_EMAILS_PER_RUN:
            console.print(
                f"[yellow]⚠️  Safety cap: Processing only first {MAX_EMAILS_PER_RUN} "
                f"of {len(overdue)} overdue records.[/yellow]"
            )
            overdue = overdue[:MAX_EMAILS_PER_RUN]

        # Step 4: Process each record
        console.print(f"\n[bold]Step 3: Generating & sending emails ({len(overdue)} records)...[/bold]")

        for i, record in enumerate(overdue, 1):
            console.print(f"\n[bold cyan]── Record {i}/{len(overdue)}: {record.invoice_no} ──[/bold cyan]")

            days_overdue = record.days_overdue
            stage = get_escalation_stage(days_overdue, record.follow_up_count)

            if stage == 0:
                # Not overdue (shouldn't happen after filter, but safety check)
                self.summary.skipped_not_overdue += 1
                continue

            if stage == 5:
                # Escalation flag — no email, just log
                console.print(
                    f"  [red bold]🚩 ESCALATION: {record.invoice_no} — "
                    f"{days_overdue} days overdue. Flagged for legal/finance review.[/red bold]"
                )
                log_email(
                    record=record,
                    email=None,
                    stage=stage,
                    send_status=SendStatus.ESCALATED,
                    run_id=self.run_id,
                )
                self.summary.escalations_flagged += 1
                continue

            # Generate email via LLM
            try:
                email = generate_email(record)
            except Exception as e:
                console.print(f"  [red]❌ Generation error: {e}[/red]")
                log_email(
                    record=record,
                    email=None,
                    stage=stage,
                    send_status=SendStatus.FAILED,
                    run_id=self.run_id,
                    error_message=str(e),
                )
                self.summary.emails_failed += 1
                self.summary.errors.append(f"{record.invoice_no}: {str(e)}")
                continue

            if email is None:
                self.summary.skipped_not_overdue += 1
                continue

            self.summary.emails_generated += 1

            # Send or dry-run
            try:
                status = self.sender.send(record, email)
            except Exception as e:
                status = SendStatus.FAILED
                console.print(f"  [red]❌ Send error: {e}[/red]")
                self.summary.errors.append(f"{record.invoice_no} send: {str(e)}")

            # Update summary counters
            if status == SendStatus.SENT:
                self.summary.emails_sent += 1
            elif status == SendStatus.DRY_RUN:
                self.summary.emails_dry_run += 1
            elif status == SendStatus.FAILED:
                self.summary.emails_failed += 1

            # Log to audit trail
            log_email(
                record=record,
                email=email,
                stage=stage,
                send_status=status,
                run_id=self.run_id,
            )

        # Step 5: Save dry-run log if applicable
        if self.sender.mode == "dry_run":
            self.sender.save_dry_run_log()

        # Step 6: Display final summary
        self._print_summary()

        # Step 7: Show audit trail
        console.print("\n[bold]📋 Audit Trail for this run:[/bold]")
        logs = get_audit_logs(run_id=self.run_id)
        display_audit_table(logs)

        return self.summary

    def _print_summary(self):
        """Print the run summary."""
        s = self.summary
        console.print(Panel(
            f"[bold]Total Records Processed:[/bold] {s.total_records_processed}\n"
            f"[bold]Emails Generated:[/bold]       {s.emails_generated}\n"
            f"[bold]Emails Sent:[/bold]             {s.emails_sent}\n"
            f"[bold]Emails Dry-Run:[/bold]          {s.emails_dry_run}\n"
            f"[bold]Emails Failed:[/bold]           {s.emails_failed}\n"
            f"[bold]Escalations Flagged:[/bold]     {s.escalations_flagged}\n"
            f"[bold]Skipped (Not Overdue):[/bold]   {s.skipped_not_overdue}\n"
            f"[bold]Errors:[/bold]                  {len(s.errors)}",
            title=f"📊 Run Summary — {self.run_id}",
            border_style="green" if not s.errors else "yellow",
        ))


def main():
    """Entry point for the agent."""
    import argparse

    parser = argparse.ArgumentParser(description="Finance Credit Follow-Up Email Agent")
    parser.add_argument(
        "--data", "-d",
        default="data/sample_credits.csv",
        help="Path to credit records CSV/Excel file (default: data/sample_credits.csv)"
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["dry_run", "smtp"],
        default=None,
        help="Email mode override (default: from .env)"
    )
    args = parser.parse_args()

    if args.mode:
        import os
        os.environ["EMAIL_MODE"] = args.mode

    agent = FinanceCreditAgent(data_file=args.data)
    summary = agent.run()

    # Exit with error code if there were failures
    if summary.emails_failed > 0 or summary.errors:
        exit(1)


if __name__ == "__main__":
    main()
