"""
sheets.py — Google Sheets read/write operations.

Reads tenant data from the configured sheet range and, as a convenience,
writes the auto-computed date columns (Year, Month, Month Description,
Last day) back to each row so the sheet always reflects the current month
without manual updates.

Usage:
    from src.sheets import read_tenant_rows, write_date_columns
    tenants = read_tenant_rows(services["sheets"], config.SPREADSHEET_ID)
"""

import logging

from googleapiclient.errors import HttpError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src import config

logger = logging.getLogger(__name__)

# Retry decorator reused across all API calls in this module.
_retry = retry(
    retry=retry_if_exception_type((HttpError, ConnectionError, TimeoutError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=16),
    reraise=True,
)


@_retry
def read_tenant_rows(sheets_service, spreadsheet_id: str) -> list[dict]:
    """
    Read all tenant rows from the Google Sheet.

    Returns a list of dicts, one per data row, with keys matching
    config.SHEET_COLUMNS. A special "_row_number" key (1-based, as used
    by the Sheets API) is also included so callers can write back to the
    correct row.

    Rows where every cell is empty are skipped.
    """
    logger.info("Reading tenant data from spreadsheet '%s'.", spreadsheet_id)
    result = (
        sheets_service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=config.SHEET_RANGE)
        .execute()
    )

    rows = result.get("values", [])
    if not rows:
        logger.warning("No data found in sheet range '%s'.", config.SHEET_RANGE)
        return []

    # Determine the first data row number (e.g. "Sheet1!A2:N" → starts at row 2)
    range_start = config.SHEET_RANGE.split("!")[-1]  # e.g. "A2:N"
    first_data_row = int("".join(c for c in range_start if c.isdigit()) or "2")

    tenants = []
    for idx, row in enumerate(rows):
        # Pad short rows with empty strings so zip always covers all columns.
        padded = row + [""] * (len(config.SHEET_COLUMNS) - len(row))
        tenant = dict(zip(config.SHEET_COLUMNS, padded))
        tenant["_row_number"] = first_data_row + idx  # e.g. 2, 3, 4, 5

        # Skip fully-empty rows.
        if all(v == "" for k, v in tenant.items() if not k.startswith("_")):
            logger.debug("Skipping empty row %d.", tenant["_row_number"])
            continue

        tenants.append(tenant)

    logger.info("Found %d tenant row(s).", len(tenants))
    return tenants


@_retry
def write_date_columns(
    sheets_service, spreadsheet_id: str, row_number: int, dates: dict
) -> None:
    """
    Write auto-computed date values back into the sheet for a specific row.

    Args:
        sheets_service: The Google Sheets API service object.
        spreadsheet_id: The target spreadsheet ID.
        row_number:     1-based row index in the sheet (e.g. 2 for the first data row).
        dates:          Dict returned by date_utils.compute_dates_for_month().
                        Keys: "Year", "Month Description", "Month", "Last day".
    """
    # Build one update request per auto-date column.
    data = []
    for field, col_letter in config.AUTO_DATE_COLUMN_LETTERS.items():
        cell_range = f"{col_letter}{row_number}"
        data.append({"range": cell_range, "values": [[dates[field]]]})

    body = {"valueInputOption": "RAW", "data": data}
    sheets_service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id, body=body
    ).execute()
    logger.debug("Wrote auto-dates to row %d.", row_number)
