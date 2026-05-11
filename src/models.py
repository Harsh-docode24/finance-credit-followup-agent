"""
Data Models using Pydantic for structured, validated output.
Ensures type safety and prevents hallucination in LLM responses.
"""

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, EmailStr, field_validator


class EscalationStage(str, Enum):
    """Enum for follow-up escalation stages."""
    FIRST = "1st_follow_up"
    SECOND = "2nd_follow_up"
    THIRD = "3rd_follow_up"
    FOURTH = "4th_follow_up"
    ESCALATION = "escalation_flag"


class ToneLevel(str, Enum):
    """Enum for email tone levels."""
    WARM_FRIENDLY = "Warm & Friendly"
    POLITE_FIRM = "Polite but Firm"
    FORMAL_SERIOUS = "Formal & Serious"
    STERN_URGENT = "Stern & Urgent"
    FLAG_LEGAL = "Flag for Legal"


class SendStatus(str, Enum):
    """Status of email send operation."""
    PENDING = "pending"
    SENT = "sent"
    DRY_RUN = "dry_run"
    FAILED = "failed"
    SKIPPED = "skipped"
    ESCALATED = "escalated"


class CreditRecord(BaseModel):
    """Represents a single pending credit/invoice record."""
    invoice_no: str = Field(..., description="Unique invoice identifier")
    client_name: str = Field(..., description="Name of the client/debtor")
    contact_email: str = Field(..., description="Client's email address")
    amount_due: float = Field(..., gt=0, description="Outstanding amount")
    currency: str = Field(default="INR", description="Currency code")
    due_date: date = Field(..., description="Payment due date")
    follow_up_count: int = Field(default=0, ge=0, description="Number of follow-ups sent")
    payment_link: Optional[str] = Field(default=None, description="Dynamic payment link")

    @property
    def days_overdue(self) -> int:
        """Calculate days overdue from today."""
        delta = date.today() - self.due_date
        return max(0, delta.days)

    @property
    def formatted_amount(self) -> str:
        """Format amount with currency symbol."""
        if self.currency == "INR":
            return f"₹{self.amount_due:,.0f}"
        elif self.currency == "USD":
            return f"${self.amount_due:,.2f}"
        return f"{self.currency} {self.amount_due:,.2f}"


class GeneratedEmail(BaseModel):
    """Structured output from the LLM for a generated email."""
    subject: str = Field(..., description="Email subject line")
    body: str = Field(..., description="Full email body text")
    tone_used: str = Field(..., description="Tone level applied")
    stage: int = Field(..., ge=1, le=5, description="Escalation stage number")
    key_personalisation_fields: list[str] = Field(
        default_factory=list,
        description="List of personalised fields used in the email"
    )

    @field_validator("subject")
    @classmethod
    def subject_must_contain_invoice(cls, v: str) -> str:
        """Validate that subject line references the invoice."""
        if not v.strip():
            raise ValueError("Subject line cannot be empty")
        return v


class AuditLogEntry(BaseModel):
    """Represents a single audit trail entry."""
    id: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    invoice_no: str
    client_name: str
    contact_email: str
    amount_due: float
    currency: str
    days_overdue: int
    escalation_stage: int
    tone_used: str
    email_subject: str
    email_body: str
    send_status: SendStatus
    error_message: Optional[str] = None
    run_id: Optional[str] = None

    class Config:
        use_enum_values = True


class AgentRunSummary(BaseModel):
    """Summary of a single agent execution run."""
    run_id: str
    timestamp: datetime
    total_records_processed: int = 0
    emails_generated: int = 0
    emails_sent: int = 0
    emails_dry_run: int = 0
    emails_failed: int = 0
    escalations_flagged: int = 0
    skipped_not_overdue: int = 0
    errors: list[str] = Field(default_factory=list)
