import pytest
from pathlib import Path
import pandas as pd
from src.data_ingestion import load_credit_records
from src.models import CreditRecord

def test_load_sample_data():
    """Verify that the sample data loads correctly and parses into Pydantic models."""
    sample_file = Path("data/sample_credits.csv")
    
    if not sample_file.exists():
        pytest.skip(f"Sample data file not found at {sample_file}")
        
    records = load_credit_records(str(sample_file))
    
    assert len(records) > 0
    assert all(isinstance(r, CreditRecord) for r in records)
    
    # Check that required fields are present
    first_record = records[0]
    assert first_record.invoice_no is not None
    assert first_record.client_name is not None
    assert first_record.contact_email is not None
    assert first_record.amount_due > 0
    assert first_record.due_date is not None
    assert first_record.follow_up_count >= 0
