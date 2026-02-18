"""
orchestrator.py — Main pipeline for the quittance automation.

Ties all modules together in the correct sequence:
  1. Idempotency check (skip if this month was already processed)
  2. Google OAuth authentication
  3. Read tenant data from the Google Sheet
  4. Auto-compute date fields and write them back to the sheet
  5. For each tenant:
       a. Validate required fields
       b. Copy the Word template in Drive (converted to Google Docs)
       c. Fill all {{placeholders}} via the Docs API
       d. Export the Google Doc as a PDF
       e. Upload the PDF to the tenant's Drive folder
       f. Email the PDF to the tenant
       g. Delete the temporary Google Doc
  6. Send a run summary alert email to the landlord
  7. Mark the month as processed (unless dry-run)

Partial failure policy: if one tenant fails, the error is logged and
the run continues with the remaining tenants. All failures are included
in the summary email.

Usage:
    from src.orchestrator import run
    exit_code = run(dry_run=False)
"""

import logging
from datetime import datetime

from src import config
from src.auth import build_services, get_credentials
from src.date_utils import compute_dates_for_month
from src.docs import replace_placeholders
from src.drive import copy_template, delete_file, export_as_pdf, upload_pdf
from src.gmail import send_alert_email, send_receipt_email
from src.idempotency import is_already_processed, mark_as_processed
from src.sheets import read_tenant_rows, write_date_columns
from src.validator import validate_tenant

logger = logging.getLogger(__name__)


def _build_pdf_filename(tenant: dict) -> str:
    """
    Build the PDF filename from tenant data.

    Format: Quittance de Loyer MM YYYY - Name SURNAME.pdf
    Example: Quittance de Loyer 02 2026 - Badr EL HALKOUJ.pdf
    """
    month = tenant["Month"]
    year = tenant["Year"]
    name = tenant["Name"]
    surname = tenant["Surname"].upper()
    return f"Quittance de Loyer {month} {year} - {name} {surname}.pdf"


def _build_replacements(tenant: dict) -> dict:
    """Build the {{placeholder}} → value mapping for the Docs API."""
    return {
        "{{Name}}": tenant["Name"],
        "{{Surname}}": tenant["Surname"],
        "{{Month Description}}": tenant["Month Description"],
        "{{Year}}": tenant["Year"],
        "{{Month}}": tenant["Month"],
        "{{Last day}}": tenant["Last day"],
        "{{Payment day}}": config.PAYMENT_DAY,
        "{{Net rent}}": tenant["Net rent"],
        "{{Charges}}": tenant["Charges"],
        "{{Total rent}}": tenant["Total rent"],
        "{{Rent description}}": tenant["Rent description"],
    }


def _build_summary(
    successes: list[str],
    failures: list[tuple[str, str]],
    month: str,
    year: str,
    dry_run: bool,
    run_start: datetime,
) -> tuple[str, str]:
    """Return (subject, body) for the summary alert email."""
    mode = "DRY RUN — " if dry_run else ""
    subject = f"{mode}Quittances {month}/{year} — {'Done' if not failures else 'Completed with errors'}"

    lines = [
        f"Run completed at {run_start.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Mode: {'DRY RUN (no emails sent to tenants, no files created)' if dry_run else 'LIVE'}",
        "",
        f"SUCCESSFUL ({len(successes)}/{len(successes) + len(failures)}):",
    ]
    for name in successes:
        lines.append(f"  - {name}")

    if failures:
        lines.append("")
        lines.append(f"FAILED ({len(failures)}/{len(successes) + len(failures)}):")
        for name, error in failures:
            lines.append(f"  - {name}: {error}")
        lines.append("")
        lines.append(
            "Action required: review the failures above and re-run manually if needed."
        )
    else:
        lines.append("")
        lines.append("All receipts processed successfully.")

    return subject, "\n".join(lines)


def _process_tenant(
    tenant: dict,
    services: dict,
    dry_run: bool,
) -> None:
    """
    Process a single tenant: fill template, export PDF, upload, email.

    Raises on any error so the orchestrator can catch and record the failure.
    """
    label = f"{tenant['Name']} {tenant['Surname']}"
    logger.info("Processing tenant: %s", label)

    # Validate required fields before touching any API.
    ok, errors = validate_tenant(tenant)
    if not ok:
        raise ValueError(f"Validation failed: {'; '.join(errors)}")

    pdf_filename = _build_pdf_filename(tenant)
    replacements = _build_replacements(tenant)

    if dry_run:
        logger.info("[DRY RUN] Would process: %s", label)
        logger.info("[DRY RUN] PDF filename: %s", pdf_filename)
        logger.info("[DRY RUN] Replacements: %s", replacements)
        return

    temp_doc_id: str | None = None
    try:
        # Copy template → Google Doc in Drive.
        temp_doc_id = copy_template(
            services["drive"],
            config.TEMPLATE_FILE_ID,
            title=f"TEMP_{pdf_filename}",
        )

        # Fill all placeholders.
        replace_placeholders(services["docs"], temp_doc_id, replacements)

        # Export as PDF bytes (server-side, no local conversion needed).
        pdf_bytes = export_as_pdf(services["drive"], temp_doc_id)

        # Upload PDF to the tenant's Drive folder.
        upload_pdf(
            services["drive"],
            folder_id=tenant["Link Folder"].strip(),
            filename=pdf_filename,
            pdf_bytes=pdf_bytes,
        )

        # Email the receipt to the tenant.
        send_receipt_email(
            services["gmail"],
            to_email=tenant["Email"].strip(),
            tenant_name=label,
            month_description=tenant["Month Description"],
            year=tenant["Year"],
            pdf_bytes=pdf_bytes,
            pdf_filename=pdf_filename,
        )

        logger.info("SUCCESS: %s", label)

    finally:
        # Always attempt to clean up the temp doc, even if an error occurred above.
        if temp_doc_id:
            delete_file(services["drive"], temp_doc_id)


def run(dry_run: bool = False) -> int:
    """
    Execute the full monthly quittance pipeline.

    Args:
        dry_run: If True, logs what would happen but does not send emails,
                 upload files, or mark the month as processed.

    Returns:
        0 if all tenants succeeded, 1 if any failed.
    """
    run_start = datetime.now()
    logger.info("=== Quittance automation started%s ===", " (DRY RUN)" if dry_run else "")

    # --- Step 1: Compute dates for the current month ---
    dates = compute_dates_for_month()
    year = dates["Year"]
    month = dates["Month"]
    logger.info("Target month: %s/%s (%s)", month, year, dates["Month Description"])

    # --- Step 2: Idempotency check ---
    if not dry_run and is_already_processed(year, month):
        logger.info(
            "Already processed %s-%s. Exiting to prevent duplicate receipts. "
            "Use --force (not yet implemented) to override.",
            year, month,
        )
        return 0

    # --- Step 3: Authenticate ---
    logger.info("Authenticating with Google APIs.")
    credentials = get_credentials()
    services = build_services(credentials)

    # --- Step 4: Read tenant data ---
    tenants = read_tenant_rows(services["sheets"], config.SPREADSHEET_ID)
    if not tenants:
        logger.error("No tenants found in the sheet. Aborting.")
        _send_catastrophic_alert(
            services,
            f"Quittances {month}/{year} — ABORTED: no tenants found",
            "The script found no tenant rows in the Google Sheet. "
            "Please check the SHEET_RANGE configuration and the sheet contents.",
        )
        return 1

    # --- Step 5: Inject auto-computed dates into each tenant dict ---
    for tenant in tenants:
        tenant.update(dates)

    # --- Step 6: Write auto-dates back to the sheet (skipped in dry-run) ---
    if not dry_run:
        for tenant in tenants:
            try:
                write_date_columns(
                    services["sheets"],
                    config.SPREADSHEET_ID,
                    tenant["_row_number"],
                    dates,
                )
            except Exception as exc:
                logger.warning(
                    "Could not write auto-dates to row %d: %s. Continuing.",
                    tenant["_row_number"], exc,
                )

    # --- Step 7: Process each tenant ---
    successes: list[str] = []
    failures: list[tuple[str, str]] = []

    for tenant in tenants:
        label = f"{tenant['Name']} {tenant['Surname']}"
        try:
            _process_tenant(tenant, services, dry_run)
            successes.append(label)
        except Exception as exc:
            logger.error("FAILED: %s — %s", label, exc, exc_info=True)
            failures.append((label, str(exc)))

    # --- Step 8: Mark month as processed ---
    if not dry_run and successes:
        mark_as_processed(year, month)

    # --- Step 9: Send summary alert to landlord ---
    subject, body = _build_summary(successes, failures, month, year, dry_run, run_start)
    logger.info("Sending summary alert to landlord.")
    try:
        send_alert_email(services["gmail"], config.LANDLORD_EMAIL, subject, body)
    except Exception as exc:
        logger.error("Could not send summary alert email: %s", exc)

    exit_code = 0 if not failures else 1
    logger.info(
        "=== Quittance automation finished — %d succeeded, %d failed (exit %d) ===",
        len(successes), len(failures), exit_code,
    )
    return exit_code


def _send_catastrophic_alert(services: dict, subject: str, body: str) -> None:
    """Best-effort alert email for a catastrophic (pre-loop) failure."""
    try:
        send_alert_email(services["gmail"], config.LANDLORD_EMAIL, subject, body)
    except Exception as exc:
        logger.error("Also failed to send catastrophic alert email: %s", exc)
