"""
Audit Trail Module
===================
Logs every generated email to a SQLite database for complete
traceability and compliance. Supports querying and reporting.
"""

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from rich.console import Console
from rich.table import Table

from src.config import DATA_DIR
from src.models import CreditRecord, GeneratedEmail, SendStatus, AuditLogEntry

console = Console()

# ── SQLAlchemy Setup ──────────────────────────────────────
Base = declarative_base()

DATABASE_PATH = DATA_DIR / "audit_trail.db"
engine = create_engine(f"sqlite:///{DATABASE_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)


class AuditLog(Base):
    """SQLAlchemy model for the audit trail table."""
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.now, nullable=False)
    run_id = Column(String(50), nullable=True, index=True)
    invoice_no = Column(String(50), nullable=False, index=True)
    client_name = Column(String(200), nullable=False)
    contact_email = Column(String(200), nullable=False)
    amount_due = Column(Float, nullable=False)
    currency = Column(String(10), default="INR")
    days_overdue = Column(Integer, nullable=False)
    escalation_stage = Column(Integer, nullable=False)
    tone_used = Column(String(50), nullable=False)
    email_subject = Column(String(500), nullable=False)
    email_body = Column(Text, nullable=False)
    send_status = Column(String(20), nullable=False)
    error_message = Column(Text, nullable=True)


def init_database():
    """Create the audit trail database and tables if they don't exist."""
    Base.metadata.create_all(engine)
    console.print(f"[dim]📦 Audit database initialized: {DATABASE_PATH}[/dim]")


def log_email(
    record: CreditRecord,
    email: GeneratedEmail | None,
    stage: int,
    send_status: SendStatus,
    run_id: str = None,
    error_message: str = None,
) -> AuditLogEntry:
    """
    Log an email generation/send event to the audit trail.
    
    Args:
        record: The credit record.
        email: The generated email (None if escalated/skipped).
        stage: Escalation stage number.
        send_status: Status of the send operation.
        run_id: Unique identifier for this agent run.
        error_message: Error details if the send failed.
    
    Returns:
        The created AuditLogEntry.
    """
    entry = AuditLogEntry(
        timestamp=datetime.now(),
        invoice_no=record.invoice_no,
        client_name=record.client_name,
        contact_email=record.contact_email,
        amount_due=record.amount_due,
        currency=record.currency,
        days_overdue=record.days_overdue,
        escalation_stage=stage,
        tone_used=email.tone_used if email else "N/A (Escalated)",
        email_subject=email.subject if email else "ESCALATION — No email sent",
        email_body=email.body if email else f"Record flagged for human/legal review. {record.days_overdue} days overdue.",
        send_status=send_status,
        error_message=error_message,
        run_id=run_id,
    )

    # Write to SQLite
    session = SessionLocal()
    try:
        db_entry = AuditLog(
            timestamp=entry.timestamp,
            run_id=entry.run_id,
            invoice_no=entry.invoice_no,
            client_name=entry.client_name,
            contact_email=entry.contact_email,
            amount_due=entry.amount_due,
            currency=entry.currency,
            days_overdue=entry.days_overdue,
            escalation_stage=entry.escalation_stage,
            tone_used=entry.tone_used,
            email_subject=entry.email_subject,
            email_body=entry.email_body,
            send_status=entry.send_status.value if isinstance(entry.send_status, SendStatus) else entry.send_status,
            error_message=entry.error_message,
        )
        session.add(db_entry)
        session.commit()
        entry.id = db_entry.id
    except Exception as e:
        session.rollback()
        console.print(f"[red]❌ Failed to log audit entry: {e}[/red]")
    finally:
        session.close()

    return entry


def get_audit_logs(limit: int = 50, invoice_no: str = None, run_id: str = None) -> list[dict]:
    """Query audit logs with optional filters."""
    session = SessionLocal()
    try:
        query = session.query(AuditLog).order_by(AuditLog.timestamp.desc())

        if invoice_no:
            query = query.filter(AuditLog.invoice_no == invoice_no)
        if run_id:
            query = query.filter(AuditLog.run_id == run_id)

        results = query.limit(limit).all()

        return [
            {
                "id": r.id,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "run_id": r.run_id,
                "invoice_no": r.invoice_no,
                "client_name": r.client_name,
                "contact_email": r.contact_email,
                "amount_due": r.amount_due,
                "currency": r.currency,
                "days_overdue": r.days_overdue,
                "escalation_stage": r.escalation_stage,
                "tone_used": r.tone_used,
                "email_subject": r.email_subject,
                "email_body": r.email_body,
                "send_status": r.send_status,
                "error_message": r.error_message,
            }
            for r in results
        ]
    finally:
        session.close()


def get_audit_summary() -> dict:
    """Get summary statistics from the audit log."""
    session = SessionLocal()
    try:
        total = session.query(AuditLog).count()
        sent = session.query(AuditLog).filter(AuditLog.send_status == "sent").count()
        dry_run = session.query(AuditLog).filter(AuditLog.send_status == "dry_run").count()
        failed = session.query(AuditLog).filter(AuditLog.send_status == "failed").count()
        escalated = session.query(AuditLog).filter(AuditLog.send_status == "escalated").count()

        return {
            "total_entries": total,
            "sent": sent,
            "dry_run": dry_run,
            "failed": failed,
            "escalated": escalated,
        }
    finally:
        session.close()


def display_audit_table(logs: list[dict]) -> None:
    """Display audit logs in a formatted Rich table."""
    if not logs:
        console.print("[dim]No audit logs found.[/dim]")
        return

    table = Table(title="📋 Audit Trail", show_lines=True)
    table.add_column("ID", style="dim", width=4)
    table.add_column("Timestamp", style="dim", width=19)
    table.add_column("Invoice", style="cyan", width=14)
    table.add_column("Client", style="white", width=15)
    table.add_column("Days OD", justify="center", width=8)
    table.add_column("Stage", justify="center", width=6)
    table.add_column("Tone", width=18)
    table.add_column("Status", width=10)

    for log in logs:
        status = log["send_status"]
        status_style = {
            "sent": "green",
            "dry_run": "yellow",
            "failed": "red",
            "escalated": "red bold",
            "skipped": "dim",
        }.get(status, "white")

        table.add_row(
            str(log["id"]),
            log["timestamp"][:19] if log["timestamp"] else "N/A",
            log["invoice_no"],
            log["client_name"],
            str(log["days_overdue"]),
            str(log["escalation_stage"]),
            log["tone_used"],
            f"[{status_style}]{status}[/{status_style}]",
        )

    console.print(table)


def export_audit_to_json(output_path: Path = None) -> Path:
    """Export the full audit log to a JSON file."""
    logs = get_audit_logs(limit=10000)
    output_path = output_path or (DATA_DIR.parent / "output" / f"audit_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    output_path.parent.mkdir(exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2, ensure_ascii=False, default=str)

    console.print(f"[green]📁 Audit log exported to: {output_path}[/green]")
    return output_path
