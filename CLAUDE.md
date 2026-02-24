# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ExpenseTrending downloads credit card statements from Gmail, parses transactions from PDFs, stores them in MongoDB, and provides a FastAPI web dashboard for expense visualization. Supports HDFC, SBI, and IDFC First banks.

## Development Commands

```bash
# Install dependencies
poetry install

# Download statements from Gmail
poetry run expensetrending --bank hdfc --since 2024-01-01

# Download and parse into MongoDB
poetry run expensetrending --parse --since 2024-01-01

# Parse existing PDFs without downloading
poetry run expensetrending --parse-only
poetry run expensetrending --parse-only --pdf /path/to/statement.pdf

# Dry run (preview without downloading)
poetry run expensetrending --dry-run

# List supported banks
poetry run expensetrending --list-banks

# Start web dashboard (FastAPI on uvicorn)
poetry run expensetrending-web

# Query MongoDB directly
python test/read_expenses.py --summary
python test/read_expenses.py --filter --bank hdfc --category food
```

## Project Configuration

- **Python version**: 3.13+
- **Package manager**: Poetry (virtualenv in `.venv/`)
- **Database**: MongoDB at `localhost:27017`, database `expensetrending`, collection `expenses`
- **Entry points**: `expensetrending` (CLI), `expensetrending-web` (web dashboard)

## Architecture

### Data Flow

```
Gmail → GmailClient (OAuth2) → EmailSearcher (bank queries) → AttachmentHandler (PDF download)
    → StatementParser (bank-specific PDF parsing) → ExpenseDB (MongoDB) → FastAPI web dashboard
```

### Key Modules

- **main.py** — CLI entry point with argparse. Orchestrates download (`run_download`) and parse (`run_parse_only`) workflows.
- **gmail_client.py** — OAuth2 Gmail API client. Lazy service init, auto token refresh. Credentials at `credentials/credentials.json`, token cached at `credentials/token.json`.
- **email_searcher.py** — `BANK_CONFIGS` dict maps bank keys to `BankConfig` dataclass (search query, sender patterns). `EmailSearcher` returns `EmailResult` dataclass with message metadata and attachment info.
- **attachment_handler.py** — Downloads PDFs to disk. Generates filenames as `{BANK}_{YYYYMMDD}_{original}.pdf`. Skips already-downloaded files.
- **statement_parser.py** — Bank-specific PDF text parsing. Each bank has its own regex-based parser (`_parse_hdfc_statement`, `_parse_sbi_statement`, `_parse_idfc_statement`). Returns `ExpenseItem` dataclass. Includes keyword-based categorization via `CATEGORY_KEYWORDS` dict.
- **db_handler.py** — `ExpenseDB` class wraps pymongo. CRUD operations on expense documents. `get_filtered_expenses()` supports bank, category, and date range filters.
- **web_app.py** — FastAPI app with Jinja2 templates. REST API endpoints: `/api/summary`, `/api/monthly-trend`, `/api/category-breakdown`, `/api/transactions` (paginated, sortable), `/api/filters`. Supports inline editing of transaction type and category via `PUT /api/transactions/{id}`.
- **templates/dashboard.html** — Single-page dashboard using Tailwind CSS and Chart.js. Monthly trend bar chart, category doughnut chart, filterable transaction table with inline editing.

### Data Model

```python
ExpenseItem:
    date: str              # DD/MM/YYYY (normalized)
    description: str
    amount: float
    transaction_type: str  # "debit" (spend) or "credit" (refund)
    bank: str              # "hdfc", "sbi", "idfc"
    category: str          # "food", "shopping", "travel", etc. or "other"
```

### Transaction Type by Bank

- **HDFC**: 'C' = debit (charge), 'D' = credit (refund); or 'Cr' suffix = credit
- **SBI**: 'M'/'D' = debit, 'C' = credit
- **IDFC**: 'DR' = debit, 'CR' = credit

## OAuth2 Setup

1. Create a project at console.cloud.google.com
2. Enable Gmail API
3. Create OAuth2 credentials (Desktop app type)
4. Download as `credentials/credentials.json`

First run opens browser for auth. Token cached in `credentials/token.json`.

## Adding New Banks

1. Add entry to `BANK_CONFIGS` in `email_searcher.py`
2. Add parser method `_parse_{bank}_statement()` in `statement_parser.py`
3. Add bank detection in `run_parse_only()` filename matching in `main.py`
