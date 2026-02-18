"""
date_utils.py — Auto-compute date fields for the current month.

This eliminates the need to manually update Year / Month / Month Description /
Last day in the Google Sheet every month. The script computes them from the
system clock (or an optional override date) and writes them back to the sheet.

Usage:
    from src.date_utils import compute_dates_for_month
    import datetime
    dates = compute_dates_for_month()
    # {'year': '2026', 'month': '02', 'month_description': 'Février', 'last_day': '28'}
"""

import calendar
import datetime
from typing import Optional


FRENCH_MONTHS = {
    1: "Janvier",
    2: "Février",
    3: "Mars",
    4: "Avril",
    5: "Mai",
    6: "Juin",
    7: "Juillet",
    8: "Août",
    9: "Septembre",
    10: "Octobre",
    11: "Novembre",
    12: "Décembre",
}


def compute_dates_for_month(
    target_date: Optional[datetime.date] = None,
) -> dict[str, str]:
    """
    Return a dict of date-related template fields for the given month.

    Args:
        target_date: The date whose month/year to use. Defaults to today.

    Returns:
        {
            "Year":              "2026",
            "Month":             "02",
            "Month Description": "Février",
            "Last day":          "28",
        }

    The keys match exactly the column names in the Google Sheet and the
    placeholder names in the Word template.
    """
    if target_date is None:
        target_date = datetime.date.today()

    year = target_date.year
    month = target_date.month
    last_day = calendar.monthrange(year, month)[1]

    return {
        "Year": str(year),
        "Month": f"{month:02d}",
        "Month Description": FRENCH_MONTHS[month],
        "Last day": str(last_day),
    }
