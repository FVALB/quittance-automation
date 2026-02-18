"""
config.py — Load and validate all settings from the .env file.

Import this module early in main.py. It raises EnvironmentError immediately
if any required variable is missing, so problems are caught before any
Google API calls are made.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env relative to the project root (one level above this file's directory)
_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


def _require(key: str) -> str:
    """Return the value of an env variable, raising a clear error if absent."""
    value = os.getenv(key, "").strip()
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{key}' is missing or empty. "
            f"Copy .env.example to .env and fill in all values."
        )
    return value


# ── Google Drive / Sheets ────────────────────────────────────────────────────
TEMPLATE_FILE_ID: str = _require("TEMPLATE_FILE_ID")
SPREADSHEET_ID: str = _require("SPREADSHEET_ID")
SHEET_RANGE: str = os.getenv("SHEET_RANGE", "Sheet1!A2:N").strip()

# ── Scheduling ───────────────────────────────────────────────────────────────
TRIGGER_DAY: int = int(os.getenv("TRIGGER_DAY", "7").strip())
PAYMENT_DAY: str = _require("PAYMENT_DAY")

# ── Landlord ─────────────────────────────────────────────────────────────────
LANDLORD_EMAIL: str = _require("LANDLORD_EMAIL")

# ── OAuth Paths ──────────────────────────────────────────────────────────────
CLIENT_SECRET_PATH: Path = _PROJECT_ROOT / _require("CLIENT_SECRET_PATH")
TOKEN_PATH: Path = _PROJECT_ROOT / _require("TOKEN_PATH")

# ── Idempotency ──────────────────────────────────────────────────────────────
PROCESSED_MONTHS_PATH: Path = _PROJECT_ROOT / _require("PROCESSED_MONTHS_PATH")

# ── Logging ──────────────────────────────────────────────────────────────────
LOG_FILE: Path = _PROJECT_ROOT / os.getenv("LOG_FILE", "logs/quittance.log").strip()
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").strip().upper()

# ── Google OAuth scopes ───────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/gmail.send",
]

# ── Sheet column header → dict key mapping ───────────────────────────────────
# This must match the order of columns in the Google Sheet (A through N).
SHEET_COLUMNS = [
    "Room",
    "Name",
    "Surname",
    "Year",
    "Month Description",
    "Month",
    "Last day",
    "Payment day",
    "Net rent",
    "Charges",
    "Total rent",
    "Rent description",
    "Email",
    "Link Folder",
]

# ── Columns that are auto-computed and written back to the sheet ──────────────
# Column letters (1-indexed positions) for the date fields.
# A=1 Room, B=2 Name, C=3 Surname, D=4 Year, E=5 Month Description,
# F=6 Month, G=7 Last day
AUTO_DATE_COLUMN_LETTERS = {
    "Year": "D",
    "Month Description": "E",
    "Month": "F",
    "Last day": "G",
}
