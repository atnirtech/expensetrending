"""Gmail API client with OAuth2 authentication.

This module caches OAuth tokens on disk. Historically this project stored the
token in the repository under ``credentials/token.json``.

For better security and portability we now prefer a per-user cache directory:
  - macOS:   ~/Library/Application Support/ExpenseTrending/token.json
  - Linux:   ~/.config/expensetrending/token.json
  - Windows: %APPDATA%\\ExpenseTrending\\token.json

We keep a backward-compatible fallback to the legacy repo location.
"""

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.exceptions import RefreshError

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

PROJECT_ROOT = Path(__file__).parent.parent.parent
CREDENTIALS_DIR = PROJECT_ROOT / "credentials"
CREDENTIALS_PATH = CREDENTIALS_DIR / "credentials.json"


def _user_config_dir() -> Path:
    """Return an OS-appropriate per-user config directory."""
    home = Path.home()

    # Windows
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "ExpenseTrending"

    # macOS
    if (home / "Library").exists():
        return home / "Library" / "Application Support" / "ExpenseTrending"

    # Linux/Unix
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "expensetrending"

    return home / ".config" / "expensetrending"


def _preferred_token_path() -> Path:
    return _user_config_dir() / "token.json"


def _legacy_token_path() -> Path:
    return CREDENTIALS_DIR / "token.json"


class GmailClient:
    """Client for interacting with Gmail API."""

    def __init__(self):
        self._service = None
        self._credentials = None

    def authenticate(self) -> None:
        """Authenticate with Gmail using OAuth2."""
        token_path = _preferred_token_path()
        legacy_token_path = _legacy_token_path()

        # Load from preferred location first, then fall back to legacy repo path.
        load_path = token_path if token_path.exists() else legacy_token_path
        if load_path.exists():
            self._credentials = Credentials.from_authorized_user_file(
                str(load_path), SCOPES
            )

        if not self._credentials or not self._credentials.valid:
            if (
                self._credentials
                and self._credentials.expired
                and self._credentials.refresh_token
            ):
                try:
                    self._credentials.refresh(Request())
                except RefreshError as e:
                    # Commonly happens when the refresh token was revoked.
                    # In that case, delete cached tokens and trigger a fresh OAuth flow.
                    msg = str(e)
                    if "invalid_grant" in msg:
                        for p in (token_path, legacy_token_path):
                            try:
                                if p.exists():
                                    p.unlink()
                            except OSError:
                                pass
                        self._credentials = None
                    else:
                        raise

            if not self._credentials or not self._credentials.valid:
                if not CREDENTIALS_PATH.exists():
                    raise FileNotFoundError(
                        f"OAuth credentials not found at {CREDENTIALS_PATH}. "
                        "Please download credentials.json from Google Cloud Console."
                    )

                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_PATH), SCOPES
                )
                self._credentials = flow.run_local_server(port=0)

            # Persist token in preferred per-user location.
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(self._credentials.to_json())

    def get_service(self):
        """Get the Gmail API service instance."""
        if self._service is None:
            if self._credentials is None:
                self.authenticate()
            self._service = build("gmail", "v1", credentials=self._credentials)
        return self._service

    def search_messages(self, query: str, max_results: int = 100) -> list[dict]:
        """Search for messages matching the query."""
        service = self.get_service()
        messages = []
        page_token = None

        while True:
            result = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    q=query,
                    maxResults=min(max_results - len(messages), 100),
                    pageToken=page_token,
                )
                .execute()
            )

            if "messages" in result:
                messages.extend(result["messages"])

            if len(messages) >= max_results:
                break

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        return messages[:max_results]

    def get_message(self, message_id: str) -> dict:
        """Get a specific message by ID."""
        service = self.get_service()
        return (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )

    def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Download an attachment."""
        import base64

        service = self.get_service()
        attachment = (
            service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
            .execute()
        )
        return base64.urlsafe_b64decode(attachment["data"])
