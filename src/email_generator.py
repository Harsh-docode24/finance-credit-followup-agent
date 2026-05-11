"""
Email Generator Module (LLM-powered)
======================================
Uses Google Gemini via LangChain to generate personalised,
tone-appropriate follow-up emails based on the escalation matrix.
Outputs are validated through Pydantic structured output schemas.
"""

import json
from datetime import date

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from rich.console import Console

from src.config import (
    GOOGLE_API_KEY,
    LLM_MODEL,
    COMPANY_NAME,
    COMPANY_PHONE,
    PAYMENT_LINK_BASE,
    ESCALATION_MATRIX,
    get_escalation_stage,
)
from src.models import CreditRecord, GeneratedEmail

console = Console()

# ── System Prompt ─────────────────────────────────────────
# This is a carefully crafted system prompt with guardrails
# to prevent hallucination and ensure personalisation.
SYSTEM_PROMPT = """You are a professional finance communication assistant for {company_name}.
Your role is to generate follow-up emails for overdue invoice payments.

CRITICAL RULES (DO NOT VIOLATE):
1. ONLY use the data provided — NEVER invent or assume any details.
2. Every email MUST include: client name, invoice number, exact amount due, due date, days overdue, and payment link.
3. Match the tone EXACTLY to the specified escalation stage.
4. Do NOT include any information not present in the input data.
5. Keep emails professional, concise, and culturally appropriate.
6. Do NOT use threatening language even at stern stage — remain professional.
7. Always sign off as "{company_name} Finance Department".

You must respond in valid JSON format matching the specified schema."""

# ── Email Generation Prompt ──────────────────────────────
EMAIL_PROMPT = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", """Generate a follow-up email for the following overdue invoice:

**Invoice Details:**
- Invoice Number: {invoice_no}
- Client Name: {client_name}
- Amount Due: {formatted_amount}
- Due Date: {due_date}
- Days Overdue: {days_overdue}
- Payment Link: {payment_link}
- Company Phone: {company_phone}

**Escalation Stage:** {stage_name} (Stage {stage_number} of 5)
**Required Tone:** {tone}
**Key Message Focus:** {key_message}
**Call to Action:** {cta}

**Previous Follow-ups Sent:** {follow_up_count}

Respond with a JSON object containing:
{{
    "subject": "Email subject line (must include invoice number and amount)",
    "body": "Complete email body with greeting, context, CTA, and professional sign-off",
    "tone_used": "{tone}",
    "stage": {stage_number},
    "key_personalisation_fields": ["list of personalised data points used"]
}}"""),
])


def _init_llm() -> ChatGoogleGenerativeAI:
    """Initialize the Google Gemini LLM with safety settings."""
    if not GOOGLE_API_KEY:
        raise ValueError(
            "GOOGLE_API_KEY is not set. Please set it in your .env file.\n"
            "Get a free key at: https://aistudio.google.com/app/apikey"
        )

    return ChatGoogleGenerativeAI(
        model=LLM_MODEL,
        google_api_key=GOOGLE_API_KEY,
        temperature=0.3,  # Low temperature for consistent, professional output
        max_output_tokens=1024,
        convert_system_message_to_human=True,
    )


def generate_email(record: CreditRecord) -> GeneratedEmail | None:
    """
    Generate a personalised follow-up email for a single credit record.
    
    Args:
        record: The credit record to generate an email for.
    
    Returns:
        GeneratedEmail object or None if the record is not overdue / flagged for escalation.
    """
    days_overdue = record.days_overdue

    if days_overdue <= 0:
        console.print(f"  [dim]⏭️  {record.invoice_no}: Not overdue, skipping[/dim]")
        return None

    # Determine escalation stage
    stage = get_escalation_stage(days_overdue, record.follow_up_count)

    if stage == 5:
        console.print(
            f"  [red]🚩 {record.invoice_no}: ESCALATION FLAG — {days_overdue} days overdue. "
            f"Flagged for human/legal review. No email generated.[/red]"
        )
        return None

    stage_config = ESCALATION_MATRIX[stage]

    # Prepare payment link
    payment_link = record.payment_link or f"{PAYMENT_LINK_BASE}{record.invoice_no}"

    # Initialize LLM and chain
    llm = _init_llm()
    parser = JsonOutputParser()
    chain = EMAIL_PROMPT | llm | parser

    try:
        # Invoke the LLM
        result = chain.invoke({
            "company_name": COMPANY_NAME,
            "company_phone": COMPANY_PHONE,
            "invoice_no": record.invoice_no,
            "client_name": record.client_name,
            "formatted_amount": record.formatted_amount,
            "due_date": str(record.due_date),
            "days_overdue": days_overdue,
            "payment_link": payment_link,
            "stage_name": stage_config["stage_name"],
            "stage_number": stage,
            "tone": stage_config["tone"],
            "key_message": stage_config["key_message"],
            "cta": stage_config["cta"],
            "follow_up_count": record.follow_up_count,
        })

        # Validate through Pydantic
        email = GeneratedEmail(**result)

        console.print(
            f"  [green]✉️  {record.invoice_no}: Generated Stage {stage} email "
            f"({stage_config['tone']})[/green]"
        )

        return email

    except Exception as e:
        console.print(f"  [red]❌ {record.invoice_no}: Email generation failed — {str(e)}[/red]")
        return None


def generate_emails_batch(records: list[CreditRecord]) -> list[tuple[CreditRecord, GeneratedEmail | None, int]]:
    """
    Generate emails for a batch of credit records.
    
    Returns:
        List of tuples: (record, generated_email_or_None, escalation_stage)
    """
    results = []

    console.print("\n[bold blue]📧 Generating follow-up emails...[/bold blue]\n")

    for i, record in enumerate(records, 1):
        console.print(f"[dim]Processing {i}/{len(records)}: {record.invoice_no}[/dim]")
        days_overdue = record.days_overdue
        stage = get_escalation_stage(days_overdue, record.follow_up_count)

        email = generate_email(record)
        results.append((record, email, stage))

    # Summary
    generated = sum(1 for _, e, _ in results if e is not None)
    escalated = sum(1 for _, _, s in results if s == 5)
    skipped = sum(1 for _, e, s in results if e is None and s != 5)

    console.print(f"\n[bold]📊 Batch Summary:[/bold]")
    console.print(f"  ✉️  Emails generated: {generated}")
    console.print(f"  🚩 Escalated (no email): {escalated}")
    console.print(f"  ⏭️  Skipped (not overdue): {skipped}")

    return results
