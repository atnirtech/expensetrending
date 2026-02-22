"""Parse credit card statements from PDF files."""

import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader

from .email_searcher import BANK_CONFIGS


# Category keywords for expense classification
CATEGORY_KEYWORDS = {
    "food": [
        "swiggy", "zomato", "restaurant", "cafe", "food", "pizza", "burger",
        "kitchen", "dhaba", "biryani", "bakery", "sweet", "juice", "tea",
        "coffee", "starbucks", "mcdonald", "kfc", "domino", "subway", "dining",
        "bundl", "mc donalds"
    ],
    "shopping": [
        "amazon", "flipkart", "myntra", "ajio", "mall", "retail", "store",
        "mart", "bazaar", "shoppers", "lifestyle", "westside", "pantaloons",
        "reliance trends", "max fashion", "h&m", "zara", "decathlon"
    ],
    "travel": [
        "uber", "ola", "rapido", "irctc", "railway", "airline", "makemytrip",
        "hotel", "oyo", "goibibo", "yatra", "cleartrip", "indigo", "spicejet",
        "air india", "vistara", "booking.com", "airbnb", "cab", "taxi"
    ],
    "utilities": [
        "electricity", "airtel", "jio", "vodafone", "bsnl", "broadband",
        "gas", "water", "bill", "recharge", "postpaid", "prepaid", "dth",
        "tata sky", "dish tv", "internet", "atria convergence"
    ],
    "entertainment": [
        "netflix", "hotstar", "spotify", "prime video", "movie", "pvr", "inox",
        "bookmyshow", "gaming", "playstation", "xbox", "steam", "youtube",
        "disney", "zee5", "sonyliv", "jiocinema", "cinema", "multiplex"
    ],
    "healthcare": [
        "hospital", "pharmacy", "medical", "apollo", "medplus", "clinic",
        "diagnostic", "lab", "doctor", "medicine", "pharma", "health",
        "netmeds", "1mg", "practo", "dental", "optical", "rxdx"
    ],
    "groceries": [
        "bigbasket", "zepto", "blinkit", "dmart", "reliance fresh", "supermarket",
        "grofers", "jiomart", "spencer", "more supermarket", "nature basket",
        "organic", "vegetables", "fruits", "daily needs", "instamart", "bbnow",
        "innovative retail", "bb daily"
    ],
    "fuel": [
        "petrol", "diesel", "hp ", "indian oil", "bharat petroleum", "shell",
        "fuel", "iocl", "bpcl", "hpcl", "filling station", "gas station",
        "mohan n p enter"
    ],
    "emi": [
        "emi", "loan", "finserv", "bajaj", "hdfc ltd", "icici bank emi",
        "credit card emi", "no cost emi"
    ],
    "insurance": [
        "generali central", "niva bupa", "icici lombard"
    ],
    "automobiles": [
        "epitome automobiles", "k h t agencies"
    ],
    "jewellery": [
        "malabar gold", "bluestone jewellery", "tanishq", "neelkanth jewel"
    ],
    "electronics": [
        "rel retail ltd digital", "adishwar india"
    ]
}


DATE_FORMATS = [
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d %b %y",
    "%d %b %Y",
]


def normalize_date_str(date_str: str) -> str:
    """Convert any supported date format to DD/MM/YYYY.

    Returns the original string if parsing fails.
    """
    cleaned = re.sub(r"\s+", " ", date_str.strip())
    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            continue
    return date_str


def categorize_expense(description: str) -> str:
    """Categorize an expense based on its description."""
    desc_lower = description.lower()

    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in desc_lower:
                return category

    return "other"


@dataclass
class ExpenseItem:
    """A single expense line item from a statement."""
    date: str
    description: str
    amount: float
    transaction_type: str  # "debit" or "credit"
    bank: str
    category: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


class StatementParser:
    """Parse credit card statements from different banks."""

    def __init__(self, bank: str):
        self.bank = bank
        self.password = BANK_CONFIGS.get(bank, {}).password if bank in BANK_CONFIGS else ""

    def parse_pdf(self, pdf_path: Path) -> list[ExpenseItem]:
        """Parse a PDF statement and extract expense items."""
        try:
            reader = PdfReader(pdf_path)

            if reader.is_encrypted:
                if not self.password:
                    print(f"  PDF is encrypted but no password set for {self.bank}")
                    return []
                reader.decrypt(self.password)

            full_text = ""
            for page in reader.pages:
                full_text += page.extract_text() + "\n"

            # Parse based on bank format
            if self.bank == "hdfc":
                return self._parse_hdfc_statement(full_text)
            elif self.bank == "sbi":
                return self._parse_sbi_statement(full_text)
            elif self.bank == "idfc":
                return self._parse_idfc_statement(full_text)
            else:
                return self._parse_generic_statement(full_text)

        except Exception as e:
            print(f"  Error parsing PDF {pdf_path.name}: {e}")
            return []

    def _parse_hdfc_statement(self, text: str) -> list[ExpenseItem]:
        """Parse HDFC Bank credit card statement."""
        expenses = []

        # Format 1 (older): DD/MM/YYYY| HH:MM DESCRIPTION C/D AMOUNT
        # Example: 19/10/2025| 15:28 ANAND SWEETS AND SAVOURBANGALORE C 2,250.00
        # C = Charge (debit), D = Credit (refund)
        pattern1 = r'(\d{2}/\d{2}/\d{4})\|\s*\d{2}:\d{2}\s+(.+?)\s+([CD])\s+([\d,]+\.\d{2})'

        for match in re.finditer(pattern1, text):
            date_str = match.group(1)
            description = match.group(2).strip()
            description = re.sub(r'\s*\+\s*\d+$', '', description).strip()
            txn_type = match.group(3)
            amount_str = match.group(4).replace(',', '')

            try:
                amount = float(amount_str)
                expenses.append(ExpenseItem(
                    date=date_str,
                    description=description,
                    amount=amount,
                    transaction_type="credit" if txn_type == 'D' else "debit",
                    bank="hdfc",
                    category=categorize_expense(description)
                ))
            except ValueError:
                continue

        if expenses:
            return expenses

        # Format 2 (newer): DD/MM/YYYY [HH:MM:SS] DESCRIPTION [REWARD_PTS] AMOUNT [Cr]
        # Example: 20/06/2025 11:53:21 RXDX WHITEFIELD RECEPTBENGALURU 16 650.00
        # Example: 02/07/2025 10:26:34 NETBANKING TRANSFER (Ref# ...) 45,741.62 Cr
        pattern2 = r'(\d{2}/\d{2}/\d{4})(?:\s+\d{2}:\d{2}:\d{2})?\s+(.+?)\s+([\d,]+\.\d{2})(\s+Cr)?\s*$'

        for match in re.finditer(pattern2, text, re.MULTILINE):
            date_str = match.group(1)
            description = match.group(2).strip()
            # Remove trailing reward points (integer) from description
            description = re.sub(r'\s+-?\d+$', '', description).strip()
            amount_str = match.group(3).replace(',', '')
            is_credit = match.group(4) is not None

            try:
                amount = float(amount_str)
                expenses.append(ExpenseItem(
                    date=date_str,
                    description=description,
                    amount=amount,
                    transaction_type="credit" if is_credit else "debit",
                    bank="hdfc",
                    category=categorize_expense(description)
                ))
            except ValueError:
                continue

        return expenses

    def _parse_sbi_statement(self, text: str) -> list[ExpenseItem]:
        """Parse SBI Card credit card statement."""
        expenses = []

        # SBI format: DD Mon YY Description Amount Type
        # Type: M (debit), D (debit), C (credit)
        # Example: 13 Feb 26 FP EMI 05/06(EXCL TAX 49.73) 10,569.35 M
        # Example: 24 Jan 26 NEFTO00000000000000000HDFCH00757618150 13,142.00 C
        pattern = r'(\d{2}\s+\w{3}\s+\d{2})\s+(.+?)\s+([\d,]+\.\d{2})\s+([MDC])'

        for match in re.finditer(pattern, text):
            date_str = normalize_date_str(match.group(1))
            description = match.group(2).strip()
            amount_str = match.group(3).replace(',', '')
            txn_type = match.group(4).upper()

            try:
                amount = float(amount_str)
                expenses.append(ExpenseItem(
                    date=date_str,
                    description=description,
                    amount=amount,
                    transaction_type="credit" if txn_type == 'C' else "debit",
                    bank="sbi",
                    category=categorize_expense(description)
                ))
            except ValueError:
                continue

        return expenses

    def _parse_idfc_statement(self, text: str) -> list[ExpenseItem]:
        """Parse IDFC First Bank credit card statement."""
        expenses = []

        # IDFC has two date formats:
        # Format 1: DD Mon YY Description Amount CR/DR
        # Example: 31 Aug 24 Innovative Retail Concept, Bangalore Convert 3,780.41 DR
        # Format 2: DD/MM/YYYY Description Amount CR/DR
        # Example: 28/06/2024 ADISHWAR INDIA LIMITED, BANGALORE Convert 4,248.00 DR
        patterns = [
            r'(\d{2}\s+\w{3}\s+\d{2})\s+(.+?)\s+([\d,]+\.\d{2})\s+(CR|DR)',
            r'(\d{2}/\d{2}/\d{4})\s+(.+?)\s+([\d,]+\.\d{2})\s+(CR|DR)',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                date_str = normalize_date_str(match.group(1))
                description = match.group(2).strip()
                amount_str = match.group(3).replace(',', '')
                txn_type = match.group(4).upper()

                try:
                    amount = float(amount_str)
                    expenses.append(ExpenseItem(
                        date=date_str,
                        description=description,
                        amount=amount,
                        transaction_type="credit" if txn_type == 'CR' else "debit",
                        bank="idfc",
                        category=categorize_expense(description)
                    ))
                except ValueError:
                    continue

        return expenses

    def _parse_generic_statement(self, text: str) -> list[ExpenseItem]:
        """Generic parser for unknown bank formats."""
        expenses = []

        # Try to match common date-description-amount patterns
        patterns = [
            r'(\d{2}/\d{2}/\d{4})\s+(.+?)\s+([\d,]+\.\d{2})',
            r'(\d{2}-\d{2}-\d{4})\s+(.+?)\s+([\d,]+\.\d{2})',
            r'(\d{2}\s+\w{3}\s+\d{4})\s+(.+?)\s+([\d,]+\.\d{2})',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text):
                date_str = normalize_date_str(match.group(1))
                description = match.group(2).strip()
                amount_str = match.group(3).replace(',', '')

                try:
                    amount = float(amount_str)
                    expenses.append(ExpenseItem(
                        date=date_str,
                        description=description,
                        amount=amount,
                        transaction_type="debit",
                        bank=self.bank,
                        category=categorize_expense(description)
                    ))
                except ValueError:
                    continue

        return expenses


def parse_statement(pdf_path: Path, bank: str) -> list[ExpenseItem]:
    """Convenience function to parse a statement."""
    parser = StatementParser(bank)
    return parser.parse_pdf(pdf_path)


def print_expenses_as_json(expenses: list[ExpenseItem]) -> None:
    """Print each expense as a JSON object."""
    for expense in expenses:
        print(expense.to_json())
