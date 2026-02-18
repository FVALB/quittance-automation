"""
drive.py — Google Drive operations for the quittance automation.

Handles:
  1. Copying the Word template and converting it to Google Docs format.
  2. Exporting the filled Google Doc as PDF bytes (server-side, no local tools).
  3. Uploading the PDF bytes to a tenant's Drive folder.
  4. Deleting the temporary Google Doc after the PDF is uploaded.

The Word template is stored as a .docx in Drive. When copied with
`convert=True`, Drive automatically converts it to a Google Doc, which
allows the Docs API to perform text replacements. The resulting Google Doc
is then exported back to PDF format via Drive's export endpoint.

Usage:
    from src.drive import copy_template, export_as_pdf, upload_pdf, delete_file
"""

import io
import logging

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
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
def copy_template(drive_service, template_file_id: str, title: str) -> str:
    """
    Copy the Word template in Drive and convert it to Google Docs format.

    Args:
        drive_service:    The Google Drive API service object.
        template_file_id: The file ID of the original .docx template.
        title:            The name for the temporary copy.

    Returns:
        The file ID of the newly created Google Doc copy.
    """
    logger.info("Copying template '%s' as Google Doc.", template_file_id)
    body = {
        "name": title,
        "mimeType": "application/vnd.google-apps.document",
    }
    result = (
        drive_service.files()
        .copy(fileId=template_file_id, body=body, supportsAllDrives=True)
        .execute()
    )
    doc_id = result["id"]
    logger.info("Temporary Google Doc created: '%s'.", doc_id)
    return doc_id


@_retry
def export_as_pdf(drive_service, file_id: str) -> bytes:
    """
    Export a Google Doc as PDF and return the raw bytes.

    The export happens entirely server-side on Google's infrastructure.
    No local PDF library or office suite is required.

    Args:
        drive_service: The Google Drive API service object.
        file_id:       The Google Doc file ID to export.

    Returns:
        PDF content as bytes.
    """
    logger.info("Exporting doc '%s' as PDF.", file_id)
    request = drive_service.files().export_media(
        fileId=file_id, mimeType="application/pdf"
    )
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    pdf_bytes = buffer.getvalue()
    logger.info("PDF export complete — %d bytes.", len(pdf_bytes))
    return pdf_bytes


@_retry
def upload_pdf(
    drive_service, folder_id: str, filename: str, pdf_bytes: bytes
) -> str:
    """
    Upload PDF bytes to a specific Google Drive folder.

    Args:
        drive_service: The Google Drive API service object.
        folder_id:     The ID of the destination folder in Drive.
                       This is the "Link Folder" value from the sheet
                       (folder ID only, not the full URL).
        filename:      The name for the uploaded file, e.g.
                       "Quittance de Loyer 02 2026 - Badr EL HALKOUJ.pdf"
        pdf_bytes:     Raw PDF content.

    Returns:
        The file ID of the newly uploaded PDF.
    """
    logger.info("Uploading '%s' to folder '%s'.", filename, folder_id)
    file_metadata = {
        "name": filename,
        "parents": [folder_id],
    }
    media = MediaIoBaseUpload(
        io.BytesIO(pdf_bytes), mimetype="application/pdf", resumable=False
    )
    result = (
        drive_service.files()
        .create(
            body=file_metadata,
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        )
        .execute()
    )
    uploaded_id = result["id"]
    logger.info("PDF uploaded successfully — file ID: '%s'.", uploaded_id)
    return uploaded_id


def delete_file(drive_service, file_id: str) -> None:
    """
    Delete a file from Drive.

    Used to remove the temporary Google Doc after the PDF has been uploaded.
    Failure here is logged but does not raise, so a cleanup error does not
    mark the tenant as failed.

    Args:
        drive_service: The Google Drive API service object.
        file_id:       The file ID to delete.
    """
    try:
        drive_service.files().delete(
            fileId=file_id, supportsAllDrives=True
        ).execute()
        logger.info("Deleted temporary file '%s'.", file_id)
    except HttpError as exc:
        logger.warning(
            "Could not delete temporary file '%s': %s. "
            "You may need to remove it manually from Drive.",
            file_id,
            exc,
        )
