"""CLI entry point for ExpenseTrending."""

import argparse
from datetime import datetime
from getpass import getpass
from pathlib import Path
from typing import Optional

from .attachment_handler import AttachmentHandler, RESOURCES_DIR
from .db_handler import ExpenseDB
from .email_searcher import BANK_CONFIGS, EmailSearcher
from .gmail_client import GmailClient
from .statement_parser import StatementParser


def parse_date(date_str: str) -> datetime:
    """Parse date string in YYYY-MM-DD format."""
    return datetime.strptime(date_str, "%Y-%m-%d")


def get_bank_passwords(banks: list[str]) -> None:
    """Prompt user for password for each bank and store in BankConfig."""
    print("\nEnter passwords for each bank (press Enter to skip):")
    for bank in banks:
        config = BANK_CONFIGS[bank]
        password = getpass(f"  {config.name} password: ").strip()
        if password:
            config.password = password


def run_download(
    bank: Optional[str] = None,
    since_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    max_results: int = 100,
    dry_run: bool = False,
    parse_statements: bool = False,
    flush_db: bool = False,
) -> None:
    """Run the statement download process."""
    print("Initializing Gmail client...")
    gmail_client = GmailClient()
    gmail_client.authenticate()
    print("Authenticated successfully.")

    searcher = EmailSearcher(gmail_client)
    attachment_handler = AttachmentHandler(gmail_client)

    # Determine which banks to search
    banks_to_search = [bank] if bank else list(BANK_CONFIGS.keys())

    # Get passwords for each bank
    get_bank_passwords(banks_to_search)

    # Initialize database if parsing
    db = None
    if parse_statements:
        db = ExpenseDB()
        if flush_db:
            deleted = db.flush_collection()
            print(f"\nFlushed {deleted} existing records from database.")

    print("\nSearching for credit card statements...")
    emails = searcher.search_bank_statements(
        bank=bank,
        since_date=since_date,
        to_date=to_date,
        max_results=max_results,
    )

    print(f"\nFound {len(emails)} emails with PDF attachments.")

    total_saved = 0

    for email in emails:
        print(f"\nProcessing: {email.subject}")
        print(f"  Bank: {email.bank.upper()}")
        print(f"  Date: {email.date.strftime('%Y-%m-%d')}")

        downloaded_files = attachment_handler.download_attachments(email, dry_run=dry_run)

        if parse_statements and not dry_run and db:
            parser = StatementParser(email.bank)
            for pdf_path in downloaded_files:
                print(f"  Parsing: {pdf_path.name}")
                expenses = parser.parse_pdf(pdf_path)
                if expenses:
                    saved = db.save_expenses(expenses)
                    total_saved += saved
                    print(f"  Saved {saved} transactions to database")

    if parse_statements and db:
        print(f"\nTotal: {total_saved} transactions saved to MongoDB")
        db.close()

    print("\nDone!")


def run_parse_only(
    bank: Optional[str] = None,
    pdf_path: Optional[str] = None,
    flush_db: bool = False,
) -> None:
    """Parse existing PDF statements without downloading."""
    # Determine which banks to parse
    banks_to_parse = [bank] if bank else list(BANK_CONFIGS.keys())

    # Get passwords for each bank
    get_bank_passwords(banks_to_parse)

    # Initialize database
    db = ExpenseDB()
    if flush_db:
        deleted = db.flush_collection()
        print(f"\nFlushed {deleted} existing records from database.")

    resources_path = Path(RESOURCES_DIR)
    total_saved = 0

    if pdf_path:
        # Parse specific PDF
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            print(f"File not found: {pdf_path}")
            return

        # Determine bank from filename
        bank_key = None
        for key in BANK_CONFIGS.keys():
            if key.upper() in pdf_file.name.upper():
                bank_key = key
                break

        if not bank_key:
            bank_key = bank or "hdfc"  # Default to hdfc if can't determine

        parser = StatementParser(bank_key)
        print(f"Parsing: {pdf_file.name} (bank: {bank_key})")
        expenses = parser.parse_pdf(pdf_file)
        if expenses:
            saved = db.save_expenses(expenses)
            total_saved += saved
            print(f"  Saved {saved} transactions to database")
    else:
        # Parse all PDFs in resources directory
        for bank_key in banks_to_parse:
            pattern = f"{bank_key.upper()}_*.pdf"
            pdf_files = list(resources_path.glob(pattern))

            if not pdf_files:
                print(f"No PDFs found for {bank_key}")
                continue

            parser = StatementParser(bank_key)
            for pdf_file in pdf_files:
                print(f"Parsing: {pdf_file.name}")
                expenses = parser.parse_pdf(pdf_file)
                if expenses:
                    saved = db.save_expenses(expenses)
                    total_saved += saved
                    print(f"  Saved {saved} transactions to database")

    print(f"\nTotal: {total_saved} transactions saved to MongoDB")
    db.close()


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Download credit card statements from Gmail"
    )

    parser.add_argument(
        "--bank",
        choices=list(BANK_CONFIGS.keys()),
        help="Specific bank to search (default: all)",
    )

    parser.add_argument(
        "--since",
        type=parse_date,
        metavar="YYYY-MM-DD",
        help="Only fetch statements after this date",
    )

    parser.add_argument(
        "--to",
        type=parse_date,
        metavar="YYYY-MM-DD",
        help="Only fetch statements before this date",
    )

    parser.add_argument(
        "--max-results",
        type=int,
        default=100,
        help="Maximum number of emails to process (default: 100)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be downloaded without actually downloading",
    )

    parser.add_argument(
        "--list-banks",
        action="store_true",
        help="List supported banks and exit",
    )

    parser.add_argument(
        "--parse",
        action="store_true",
        help="Parse downloaded statements and save to MongoDB",
    )

    parser.add_argument(
        "--parse-only",
        action="store_true",
        help="Only parse existing PDFs (skip download)",
    )

    parser.add_argument(
        "--pdf",
        type=str,
        metavar="PATH",
        help="Parse a specific PDF file",
    )

    parser.add_argument(
        "--flush",
        action="store_true",
        default=False,
        help="Flush (clear) the database collection before saving (default: no flush)",
    )

    parser.add_argument(
        "--normalize-dates",
        action="store_true",
        help="Migrate all dates in MongoDB to DD/MM/YYYY format and exit",
    )

    args = parser.parse_args()

    if args.normalize_dates:
        db = ExpenseDB()
        updated = db.normalize_dates()
        print(f"Normalized {updated} date(s) to DD/MM/YYYY format.")
        db.close()
        return

    if args.list_banks:
        print("Supported banks:")
        for key, config in BANK_CONFIGS.items():
            print(f"  {key}: {config.name}")
        return

    if args.parse_only or args.pdf:
        run_parse_only(
            bank=args.bank,
            pdf_path=args.pdf,
            flush_db=args.flush,
        )
    else:
        run_download(
            bank=args.bank,
            since_date=args.since,
            to_date=args.to,
            max_results=args.max_results,
            dry_run=args.dry_run,
            parse_statements=args.parse,
            flush_db=args.flush,
        )


if __name__ == "__main__":
    main()
