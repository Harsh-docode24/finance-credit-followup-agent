"""
Finance Credit Follow-Up Email Agent — Main Entry Point
=========================================================
Run the agent from command line:
    python main.py                          # Use sample data
    python main.py --data my_records.csv    # Use custom data
    python main.py --mode dry_run           # Force dry-run mode

Or launch the Streamlit dashboard:
    streamlit run app/dashboard.py
"""

import sys
import os

# Fix Windows terminal encoding for Unicode/emoji characters
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    os.environ["PYTHONIOENCODING"] = "utf-8"

from src.agent import main

if __name__ == "__main__":
    main()
