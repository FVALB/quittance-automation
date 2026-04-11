"""
auth.py — Google OAuth 2.0 authentication for Desktop apps.

On the first run, this opens a browser window for the user to sign in and
grant access. The resulting token is saved to TOKEN_PATH and reused (with
automatic refresh) on all subsequent runs.

Usage:
    from src.auth import get_credentials, build_services
    creds = get_credentials()
    services = build_services(creds)
    drive_service = services["drive"]
"""

import logging
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src import config

logger = logging.getLogger(__name__)


def get_credentials() -> Credentials:
    """
    Return valid Google OAuth credentials.

    - If TOKEN_PATH exists and the token is still valid, it is returned as-is.
    - If the token is expired but has a refresh token, it is refreshed silently.
    - If no token exists (first run), opens a browser for the user to log in
      and then saves the new token to TOKEN_PATH.
    """
    creds: Credentials | None = None

    token_path: Path = config.TOKEN_PATH
    client_secret_path: Path = config.CLIENT_SECRET_PATH

    if not client_secret_path.exists():
        raise FileNotFoundError(
            f"OAuth client secret not found at '{client_secret_path}'. "
            "Download it from GCP Console → APIs & Services → Credentials and "
            "place it at that path."
        )

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), config.SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("OAuth token expired — refreshing automatically.")
            try:
                creds.refresh(Request())
            except RefreshError:
                logger.warning("Token refresh failed (revoked) — restarting browser OAuth flow.")
                creds = None

        if not creds:
            logger.info("No valid token found — starting browser OAuth flow.")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secret_path), config.SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Persist the token so subsequent runs skip the browser step.
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())
        logger.info("OAuth token saved to '%s'.", token_path)

    return creds


def build_services(creds: Credentials) -> dict:
    """
    Build and return a dict of Google API service clients.

    Returns:
        {
            "drive":  Resource,   # Google Drive API v3
            "sheets": Resource,   # Google Sheets API v4
            "docs":   Resource,   # Google Docs API v1
            "gmail":  Resource,   # Gmail API v1
        }
    """
    logger.debug("Building Google API service clients.")
    return {
        "drive": build("drive", "v3", credentials=creds),
        "sheets": build("sheets", "v4", credentials=creds),
        "docs": build("docs", "v1", credentials=creds),
        "gmail": build("gmail", "v1", credentials=creds),
    }
