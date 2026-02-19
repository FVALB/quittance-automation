"""
gmail.py — Send emails via the Gmail API.

Two functions:
  - send_receipt_email: sends the PDF quittance to a tenant.
  - send_alert_email:   sends a plain-text summary or error report to the landlord.

All sending is done via the Gmail API (no SMTP, no App Passwords).
The script must have been authorized with the gmail.send scope.

Usage:
    from src.gmail import send_receipt_email, send_alert_email
"""

import base64
import logging
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

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


def _encode_message(message: MIMEMultipart) -> dict:
    """Encode a MIME message to the format expected by the Gmail API."""
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    return {"raw": raw}


@_retry
def send_receipt_email(
    gmail_service,
    to_email: str,
    tenant_name: str,
    month_description: str,
    year: str,
    pdf_bytes: bytes,
    pdf_filename: str,
) -> None:
    """
    Send the monthly receipt to a tenant with the PDF attached.

    Args:
        gmail_service:    The Gmail API service object.
        to_email:         Tenant's email address.
        tenant_name:      Full name for the email body (e.g. "Badr EL HALKOUJ").
        month_description: French month name (e.g. "Février").
        year:             4-digit year string (e.g. "2026").
        pdf_bytes:        Raw PDF content to attach.
        pdf_filename:     Attachment filename shown to the recipient.
    """
    subject = f"Quittance de loyer — {month_description} {year}"

    body = (
        f"Bonjour {tenant_name},\n\n"
        f"Veuillez trouver ci-joint votre quittance de loyer pour le mois "
        f"de {month_description} {year}.\n\n"
        f"Cordialement,\n"
        f"Felipe VALENCIA"
    )

    message = MIMEMultipart()
    message["To"] = to_email
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain", "utf-8"))

    attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
    attachment.add_header(
        "Content-Disposition", "attachment", filename=pdf_filename
    )
    message.attach(attachment)

    gmail_service.users().messages().send(
        userId="me", body=_encode_message(message)
    ).execute()

    logger.info("Receipt email sent to '%s'.", to_email)


@_retry
def send_alert_email(
    gmail_service,
    landlord_email: str,
    subject: str,
    body: str,
) -> None:
    """
    Send a plain-text summary or error alert to the landlord.

    Args:
        gmail_service:  The Gmail API service object.
        landlord_email: Destination address (the landlord's Gmail).
        subject:        Email subject line.
        body:           Plain text content of the email.
    """
    message = MIMEMultipart()
    message["To"] = landlord_email
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain", "utf-8"))

    gmail_service.users().messages().send(
        userId="me", body=_encode_message(message)
    ).execute()

    logger.info("Alert email sent to '%s' — subject: '%s'.", landlord_email, subject)
