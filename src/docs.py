"""
docs.py — Fill template placeholders via the Google Docs API.

Uses the Docs API batchUpdate endpoint with ReplaceAllText sub-requests to
substitute every {{placeholder}} in the copied Google Doc with the tenant's
real data. This is purely a text find-and-replace — no local file parsing.

Usage:
    from src.docs import replace_placeholders
    replace_placeholders(services["docs"], doc_id, {
        "{{Name}}": "Badr",
        "{{Surname}}": "EL HALKOUJ",
        ...
    })
"""

import logging

from googleapiclient.errors import HttpError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

_retry = retry(
    retry=retry_if_exception_type((HttpError, ConnectionError, TimeoutError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=16),
    reraise=True,
)


@_retry
def replace_placeholders(docs_service, doc_id: str, replacements: dict) -> None:
    """
    Replace all occurrences of each {{placeholder}} in the Google Doc.

    Args:
        docs_service:  The Google Docs API service object.
        doc_id:        The ID of the (temporary copy of the) Google Doc.
        replacements:  A dict mapping placeholder strings to replacement values.
                       Example: {"{{Name}}": "Badr", "{{Year}}": "2026"}

    Note: If a placeholder doesn't exist in the document, the API silently
    makes 0 replacements for that key. The PDF will then contain the raw
    {{placeholder}} text. Check the alert email if a field looks wrong.
    """
    requests = [
        {
            "replaceAllText": {
                "containsText": {"text": placeholder, "matchCase": True},
                "replaceText": replacement,
            }
        }
        for placeholder, replacement in replacements.items()
    ]

    logger.debug(
        "Replacing %d placeholder(s) in doc '%s'.", len(requests), doc_id
    )

    response = (
        docs_service.documents()
        .batchUpdate(documentId=doc_id, body={"requests": requests})
        .execute()
    )

    # Log how many replacements were actually made (useful for debugging
    # formatting mismatches in the template).
    replies = response.get("replies", [])
    for req, reply in zip(requests, replies):
        placeholder = req["replaceAllText"]["containsText"]["text"]
        count = reply.get("replaceAllText", {}).get("occurrencesChanged", 0)
        if count == 0:
            logger.warning(
                "Placeholder '%s' was not found in the document — "
                "check for spacing or casing differences in the template.",
                placeholder,
            )
        else:
            logger.debug("'%s' replaced %d time(s).", placeholder, count)
