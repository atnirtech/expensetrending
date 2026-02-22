# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ExpenseTrending downloads credit card statements from Gmail and extracts password patterns from email bodies. It supports HDFC, ICICI, SBI, and IDFC First banks.

## Development Commands

```bash
# Install dependencies
poetry install

# Run the statement downloader
poetry run expensetrending

# Run with specific bank
poetry run expensetrending --bank hdfc

# Run with date filter
poetry run expensetrending --since 2024-01-01

# Dry run (preview without downloading)
poetry run expensetrending --dry-run

# List supported banks
poetry run expensetrending --list-banks
```

## Project Configuration

- **Python version**: 3.13+
- **Package manager**: Poetry (with virtual environment stored in `.venv/`)
- **Build system**: poetry-core

## Architecture

```
src/expensetrending/
├── gmail_client.py      # OAuth2 Gmail API client
├── email_searcher.py    # Bank-specific email search (BANK_CONFIGS dict)
├── attachment_handler.py # PDF download to resources/
├── password_extractor.py # Parse password patterns from email body
└── main.py              # CLI entry point
```

## OAuth2 Setup

Before running, you need Google Cloud credentials:
1. Create a project at console.cloud.google.com
2. Enable Gmail API
3. Create OAuth2 credentials (Desktop app type)
4. Download as `credentials/credentials.json`

First run will open browser for authentication. Token is cached in `credentials/token.json`.

## Adding New Banks

Edit `BANK_CONFIGS` in `email_searcher.py`:
```python
BANK_CONFIGS = {
    "bank_key": BankConfig(
        name="Bank Name",
        search_query='from:bank.com subject:"statement" has:attachment',
        sender_patterns=["email@bank.com"],
    ),
}
```
