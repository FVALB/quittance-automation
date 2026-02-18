"""
validator.py — Validate that a tenant row contains all required fields
before any Google API calls are made.

Catching missing data early avoids:
  - Wasted API quota (copy + fill + export for a bad row)
  - Orphan temporary Google Docs left in Drive on partial failure

Usage:
    from src.validator import validate_tenant
    ok, errors = validate_tenant(tenant_dict)
    if not ok:
        raise ValueError(f"Invalid tenant data: {errors}")
"""

# Fields that must be present and non-empty in every tenant row.
# "Year", "Month", "Month Description", and "Last day" are excluded here
# because they are auto-computed by date_utils and injected before validation.
REQUIRED_FIELDS = [
    "Name",
    "Surname",
    "Email",
    "Link Folder",
    "Net rent",
    "Charges",
    "Total rent",
    "Rent description",
]


def validate_tenant(tenant: dict) -> tuple[bool, list[str]]:
    """
    Check that all required fields are present and non-empty.

    Args:
        tenant: A dict built from one row of the Google Sheet,
                with auto-computed date fields already merged in.

    Returns:
        (True, [])                   if all required fields are present
        (False, ["error1", ...])     if any fields are missing or empty
    """
    errors: list[str] = []

    for field in REQUIRED_FIELDS:
        value = tenant.get(field, "")
        if not isinstance(value, str) or not value.strip():
            errors.append(f"Missing or empty required field: '{field}'")

    return (len(errors) == 0, errors)
