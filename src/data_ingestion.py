"""
Data Ingestion Module
======================
Reads pending credit records from CSV / Excel files and validates them
into structured Pydantic models. Supports PII masking for logs.
"""

import re
from pathlib import Path
from datetime import date

import pandas as pd
from rich.console import Console
from rich.table import Table

from src.models import CreditRecord
from src.config import MASK_PII_IN_LOGS

console = Console()


def mask_email(email: str) -> str:
    """Mask email for PII protection in logs. e.g., r***h@tech***.in"""
    if not MASK_PII_IN_LOGS:
        return email
    parts = email.split("@")
    if len(parts) != 2:
        return "***@***.***"
    local = parts[0]
    domain_parts = parts[1].split(".")
    masked_local = local[0] + "***" + (local[-1] if len(local) > 1 else "")
    masked_domain = domain_parts[0][:4] + "***" if len(domain_parts[0]) > 4 else domain_parts[0] + "***"
    return f"{masked_local}@{masked_domain}.{domain_parts[-1]}"


def mask_name(name: str) -> str:
    """Mask client name for PII protection. e.g., R*** K***"""
    if not MASK_PII_IN_LOGS:
        return name
    parts = name.split()
    return " ".join(p[0] + "***" for p in parts if p)


def load_credit_records(file_path: str | Path) -> list[CreditRecord]:
    """
    Load credit records from a CSV or Excel file.
    
    Args:
        file_path: Path to the CSV or Excel file.
    
    Returns:
        List of validated CreditRecord objects.
    
    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If required columns are missing.
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Credit records file not found: {file_path}")

    # Read file based on extension
    if file_path.suffix.lower() == ".csv":
        df = pd.read_csv(file_path)
    elif file_path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(file_path)
    else:
        raise ValueError(f"Unsupported file format: {file_path.suffix}. Use .csv or .xlsx")

    # Validate required columns
    required_cols = {"invoice_no", "client_name", "contact_email", "amount_due", "due_date"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Parse and validate records
    records: list[CreditRecord] = []
    errors: list[str] = []

    for idx, row in df.iterrows():
        try:
            # Parse due_date
            due_date = pd.to_datetime(row["due_date"]).date()

            record = CreditRecord(
                invoice_no=str(row["invoice_no"]).strip(),
                client_name=str(row["client_name"]).strip(),
                contact_email=str(row["contact_email"]).strip(),
                amount_due=float(row["amount_due"]),
                currency=str(row.get("currency", "INR")).strip(),
                due_date=due_date,
                follow_up_count=int(row.get("follow_up_count", 0)),
                payment_link=str(row.get("payment_link", "")) if pd.notna(row.get("payment_link")) else None,
            )
            records.append(record)
        except Exception as e:
            errors.append(f"Row {idx + 2}: {str(e)}")

    # Log results
    if errors:
        console.print(f"\n[yellow]⚠️  {len(errors)} records had validation errors:[/yellow]")
        for err in errors[:5]:  # Show first 5 errors
            console.print(f"  → {err}", style="yellow")

    console.print(f"\n[green]✅ Successfully loaded {len(records)} credit records from {file_path.name}[/green]")

    return records


def display_records_table(records: list[CreditRecord]) -> None:
    """Display credit records in a formatted table using Rich."""
    table = Table(title="📋 Pending Credit Records", show_lines=True)
    table.add_column("Invoice", style="cyan", no_wrap=True)
    table.add_column("Client", style="white")
    table.add_column("Email", style="dim")
    table.add_column("Amount", style="green", justify="right")
    table.add_column("Due Date", style="yellow")
    table.add_column("Days Overdue", style="red", justify="center")
    table.add_column("Follow-Ups", justify="center")

    for r in records:
        days = r.days_overdue
        days_style = "green" if days == 0 else "yellow" if days <= 7 else "red"

        table.add_row(
            r.invoice_no,
            mask_name(r.client_name),
            mask_email(r.contact_email),
            r.formatted_amount,
            str(r.due_date),
            f"[{days_style}]{days}[/{days_style}]",
            str(r.follow_up_count),
        )

    console.print(table)


def get_overdue_records(records: list[CreditRecord]) -> list[CreditRecord]:
    """Filter records to only include overdue ones (days_overdue > 0)."""
    overdue = [r for r in records if r.days_overdue > 0]
    console.print(f"\n[bold]📊 {len(overdue)} of {len(records)} records are overdue[/bold]")
    return overdue
