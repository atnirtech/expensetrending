"""Email search logic for bank-specific credit card statements."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .gmail_client import GmailClient


@dataclass
class BankConfig:
    """Configuration for a bank's email patterns."""

    name: str
    search_query: str
    sender_patterns: list[str]
    password: str = ""


BANK_CONFIGS = {
    "hdfc": BankConfig(
        name="HDFC Bank",
        search_query='from:hdfcbank.net subject:"credit card statement" has:attachment',
        sender_patterns=["alerts@hdfcbank.net", "hdfcbank.net"],
    ),
    # "icici": BankConfig(
    #     name="ICICI Bank",
    #     search_query='from:icicibank.com subject:"statement" has:attachment',
    #     sender_patterns=["credit_cards@icicibank.com", "icicibank.com"],
    # ),
    "sbi": BankConfig(
        name="SBI Card",
        search_query='from:sbicard.com subject:"statement" has:attachment',
        sender_patterns=["sbicard.com"],
    ),
    "idfc": BankConfig(
        name="IDFC First Bank",
        search_query='from:idfcfirstbank.com subject:"credit card statement" has:attachment',
        sender_patterns=["idfcfirstbank.com", "idfcfirst.bank.in"],
    ),
}


@dataclass
class EmailResult:
    """Result from email search."""

    message_id: str
    bank: str
    subject: str
    date: datetime
    sender: str
    attachments: list[dict]
    body_text: str
    body_html: str


class EmailSearcher:
    """Search for credit card statement emails."""

    def __init__(self, gmail_client: GmailClient):
        self.client = gmail_client

    def search_bank_statements(
        self,
        bank: Optional[str] = None,
        since_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        max_results: int = 100,
    ) -> list[EmailResult]:
        """Search for credit card statements from specified bank(s)."""
        results = []

        banks_to_search = [bank] if bank else list(BANK_CONFIGS.keys())

        for bank_key in banks_to_search:
            if bank_key not in BANK_CONFIGS:
                print(f"Unknown bank: {bank_key}")
                continue

            config = BANK_CONFIGS[bank_key]
            query = config.search_query

            if since_date:
                date_str = since_date.strftime("%Y/%m/%d")
                query += f" after:{date_str}"

            if to_date:
                date_str = to_date.strftime("%Y/%m/%d")
                query += f" before:{date_str}"

            messages = self.client.search_messages(query, max_results)
            print(f"Found {len(messages)} emails from {config.name}")

            for msg_info in messages:
                try:
                    email_result = self._parse_message(msg_info["id"], bank_key)
                    if email_result:
                        results.append(email_result)
                except Exception as e:
                    print(f"Error parsing message {msg_info['id']}: {e}")

        return results

    def _parse_message(self, message_id: str, bank: str) -> Optional[EmailResult]:
        """Parse a Gmail message into EmailResult."""
        message = self.client.get_message(message_id)
        payload = message.get("payload", {})
        headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}

        subject = headers.get("subject", "")
        sender = headers.get("from", "")
        date_str = headers.get("date", "")

        date = self._parse_date(date_str)

        body_text, body_html = self._extract_body(payload)
        attachments = self._extract_attachments(payload)

        pdf_attachments = [a for a in attachments if a["filename"].lower().endswith(".pdf")]

        if not pdf_attachments:
            return None

        return EmailResult(
            message_id=message_id,
            bank=bank,
            subject=subject,
            date=date,
            sender=sender,
            attachments=pdf_attachments,
            body_text=body_text,
            body_html=body_html,
        )

    def _parse_date(self, date_str: str) -> datetime:
        """Parse email date string."""
        from email.utils import parsedate_to_datetime

        try:
            return parsedate_to_datetime(date_str)
        except Exception:
            return datetime.now()

    def _extract_body(self, payload: dict) -> tuple[str, str]:
        """Extract plain text and HTML body from message payload."""
        import base64

        body_text = ""
        body_html = ""

        def extract_from_part(part: dict) -> None:
            nonlocal body_text, body_html
            mime_type = part.get("mimeType", "")
            body = part.get("body", {})

            if "data" in body:
                data = base64.urlsafe_b64decode(body["data"]).decode("utf-8", errors="ignore")
                if mime_type == "text/plain":
                    body_text = data
                elif mime_type == "text/html":
                    body_html = data

            for sub_part in part.get("parts", []):
                extract_from_part(sub_part)

        extract_from_part(payload)
        return body_text, body_html

    def _extract_attachments(self, payload: dict) -> list[dict]:
        """Extract attachment information from message payload."""
        attachments = []

        def extract_from_part(part: dict) -> None:
            filename = part.get("filename", "")
            body = part.get("body", {})
            attachment_id = body.get("attachmentId")

            if filename and attachment_id:
                attachments.append(
                    {
                        "filename": filename,
                        "attachment_id": attachment_id,
                        "size": body.get("size", 0),
                        "mime_type": part.get("mimeType", ""),
                    }
                )

            for sub_part in part.get("parts", []):
                extract_from_part(sub_part)

        extract_from_part(payload)
        return attachments
