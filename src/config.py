"""
Configuration module for the Finance Credit Follow-Up Email Agent.
Loads environment variables and provides centralized config access.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# ── Paths ──────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
LOG_DIR = BASE_DIR / "logs"

# Create directories if they don't exist
DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

# ── LLM Configuration ─────────────────────────────────────
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")  # "gemini" or "groq"
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")

# ── Email Configuration ───────────────────────────────────
EMAIL_MODE = os.getenv("EMAIL_MODE", "dry_run")  # "dry_run" or "smtp"
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "finance@acmecorp.com")
SENDER_NAME = os.getenv("SENDER_NAME", "Finance Department")

# ── Company Configuration ─────────────────────────────────
COMPANY_NAME = os.getenv("COMPANY_NAME", "Acme Corp")
COMPANY_PHONE = os.getenv("COMPANY_PHONE", "+91-9876543210")
PAYMENT_LINK_BASE = os.getenv("PAYMENT_LINK_BASE", "https://pay.acmecorp.com/invoice/")

# ── Database ──────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'audit_trail.db'}")

# ── Safety ────────────────────────────────────────────────
MAX_EMAILS_PER_RUN = int(os.getenv("MAX_EMAILS_PER_RUN", "50"))
MASK_PII_IN_LOGS = os.getenv("MASK_PII_IN_LOGS", "true").lower() == "true"

# ── Tone Escalation Matrix ────────────────────────────────
ESCALATION_MATRIX = {
    1: {
        "stage_name": "1st Follow-Up",
        "trigger_days": (1, 7),
        "tone": "Warm & Friendly",
        "key_message": "Gentle reminder, assume oversight",
        "cta": "Pay now link / bank details",
    },
    2: {
        "stage_name": "2nd Follow-Up",
        "trigger_days": (8, 14),
        "tone": "Polite but Firm",
        "key_message": "Payment still pending; request confirmation",
        "cta": "Confirm payment date",
    },
    3: {
        "stage_name": "3rd Follow-Up",
        "trigger_days": (15, 21),
        "tone": "Formal & Serious",
        "key_message": "Escalating concern; mention impact",
        "cta": "Respond within 48 hrs",
    },
    4: {
        "stage_name": "4th Follow-Up",
        "trigger_days": (22, 30),
        "tone": "Stern & Urgent",
        "key_message": "Final reminder before escalation",
        "cta": "Pay immediately or call us",
    },
    5: {
        "stage_name": "Escalation Flag",
        "trigger_days": (31, 9999),
        "tone": "🚩 Flag for Legal",
        "key_message": "Human review required; no auto email",
        "cta": "Assign to finance manager",
    },
}


def get_escalation_stage(days_overdue: int, follow_up_count: int) -> int:
    """
    Determine the escalation stage based on days overdue.
    The follow_up_count is used to ensure we don't skip stages.
    Returns stage number (1-5).
    """
    if days_overdue <= 0:
        return 0  # Not overdue

    # Determine stage by days overdue
    for stage, config in ESCALATION_MATRIX.items():
        low, high = config["trigger_days"]
        if low <= days_overdue <= high:
            return stage

    return 5  # Default to escalation for anything > 30 days


def validate_config() -> list[str]:
    """Validate that essential configuration is present. Returns list of warnings."""
    warnings = []
    if LLM_PROVIDER == "gemini" and not GOOGLE_API_KEY:
        warnings.append("⚠️  GOOGLE_API_KEY is not set. LLM features will not work.")
    if LLM_PROVIDER == "groq" and not GROQ_API_KEY:
        warnings.append("⚠️  GROQ_API_KEY is not set. LLM features will not work.")
    if EMAIL_MODE == "smtp":
        if not SMTP_USERNAME:
            warnings.append("⚠️  SMTP_USERNAME is not set but EMAIL_MODE is 'smtp'.")
        if not SMTP_PASSWORD:
            warnings.append("⚠️  SMTP_PASSWORD is not set but EMAIL_MODE is 'smtp'.")
    return warnings
