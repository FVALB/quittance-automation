"""
idempotency.py — Prevent duplicate receipt runs within the same month.

Stores a JSON file (processed_months.json) that records when each
YYYY-MM was successfully processed. The orchestrator checks this before
doing any work and updates it after a successful run.

File format:
    {
        "2026-01": "2026-01-07T08:14:22.123456",
        "2026-02": "2026-02-07T08:10:05.654321"
    }

Usage:
    from src.idempotency import is_already_processed, mark_as_processed
    if is_already_processed("2026", "02"):
        print("Already done this month.")
    else:
        # ... do the work ...
        mark_as_processed("2026", "02")
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from src import config

logger = logging.getLogger(__name__)


def _load() -> dict:
    """Load the processed months dict, returning {} on missing or corrupt file."""
    path: Path = config.PROCESSED_MONTHS_PATH
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(
            "Could not read '%s' (%s). Treating as empty — will reprocess.",
            path,
            exc,
        )
        return {}


def _save(data: dict) -> None:
    """Write the processed months dict atomically."""
    path: Path = config.PROCESSED_MONTHS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _key(year: str, month: str) -> str:
    return f"{year}-{month}"


def is_already_processed(year: str, month: str) -> bool:
    """Return True if this YYYY-MM has already been marked as processed."""
    return _key(year, month) in _load()


def mark_as_processed(year: str, month: str) -> None:
    """Record that YYYY-MM was successfully processed (with a timestamp)."""
    data = _load()
    data[_key(year, month)] = datetime.now().isoformat()
    _save(data)
    logger.info("Marked %s-%s as processed.", year, month)
