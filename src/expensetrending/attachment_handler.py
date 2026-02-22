"""Handle downloading and saving PDF attachments."""

import re
from pathlib import Path

from .email_searcher import EmailResult
from .gmail_client import GmailClient

PROJECT_ROOT = Path(__file__).parent.parent.parent
RESOURCES_DIR = Path("/Users/hkochhar/Documents/Expenses")


class AttachmentHandler:
    """Download and save PDF attachments from emails."""

    def __init__(self, gmail_client: GmailClient, resources_dir: Path = RESOURCES_DIR):
        self.client = gmail_client
        self.resources_dir = resources_dir
        self.resources_dir.mkdir(parents=True, exist_ok=True)

    def download_attachments(self, email_result: EmailResult, dry_run: bool = False) -> list[Path]:
        """Download all PDF attachments from an email result."""
        downloaded_files = []

        for attachment in email_result.attachments:
            filename = self._generate_filename(email_result, attachment["filename"])
            filepath = self.resources_dir / filename

            if filepath.exists():
                print(f"  Already exists: {filename}")
                downloaded_files.append(filepath)
                continue

            if dry_run:
                print(f"  Would download: {filename}")
                continue

            try:
                data = self.client.get_attachment(
                    email_result.message_id, attachment["attachment_id"]
                )
                filepath.write_bytes(data)
                print(f"  Downloaded: {filename}")
                downloaded_files.append(filepath)
            except Exception as e:
                print(f"  Error downloading {filename}: {e}")

        return downloaded_files

    def _generate_filename(self, email_result: EmailResult, original_filename: str) -> str:
        """Generate a unique filename for the attachment."""
        date_str = email_result.date.strftime("%Y%m%d")
        bank = email_result.bank.upper()

        safe_filename = re.sub(r"[^\w\-_.]", "_", original_filename)

        return f"{bank}_{date_str}_{safe_filename}"

    def get_password_filepath(self, pdf_path: Path) -> Path:
        """Get the path for the password file corresponding to a PDF."""
        return pdf_path.with_suffix(".password.txt")
