"""
main.py — Entry point for the Quittance de Loyer automation.

Run modes:
    python main.py              — live run (sends emails, uploads PDFs)
    python main.py --dry-run    — simulate run (logs only, no side-effects)

The script is designed to be called directly by Windows Task Scheduler.
Exit codes:
    0 — all tenants processed successfully
    1 — one or more tenants failed, or a catastrophic error occurred
"""

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _setup_logging(log_file: Path, log_level: str) -> None:
    """Configure root logger with a rotating file handler and a console handler."""
    log_file.parent.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, log_level.upper(), logging.INFO)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    root = logging.getLogger()
    root.setLevel(level)

    # Rotating file: max 5 MB, keep 3 backups.
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(fmt, datefmt))
    root.addHandler(file_handler)

    # Console output (useful when running interactively or via Task Scheduler logs).
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(fmt, datefmt))
    root.addHandler(console_handler)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate and send monthly rent receipts (quittances de loyer)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Simulate the run without sending emails, uploading files, "
            "or marking the month as processed. "
            "A DRY RUN summary email IS sent to the landlord so you can verify "
            "that Gmail is working."
        ),
    )
    args = parser.parse_args()

    # Import config here so logging is set up before any module-level code runs.
    # config.py raises EnvironmentError immediately if .env is incomplete.
    try:
        from src import config
    except EnvironmentError as exc:
        # Can't log to file yet (config not loaded), so print to stderr.
        print(f"[FATAL] Configuration error: {exc}", file=sys.stderr)
        return 1

    _setup_logging(config.LOG_FILE, config.LOG_LEVEL)
    logger = logging.getLogger(__name__)

    try:
        from src.orchestrator import run
        return run(dry_run=args.dry_run)
    except Exception as exc:
        logger.critical(
            "Unhandled exception in orchestrator: %s", exc, exc_info=True
        )
        # Attempt a best-effort alert even after a catastrophic failure.
        try:
            from src.auth import build_services, get_credentials
            from src.gmail import send_alert_email
            services = build_services(get_credentials())
            send_alert_email(
                services["gmail"],
                config.LANDLORD_EMAIL,
                subject="Quittances — CRITICAL FAILURE",
                body=(
                    f"The quittance automation crashed with an unhandled error:\n\n"
                    f"{type(exc).__name__}: {exc}\n\n"
                    f"Please check the log file for the full traceback:\n"
                    f"{config.LOG_FILE}"
                ),
            )
        except Exception as alert_exc:
            logger.error("Also failed to send critical alert: %s", alert_exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
