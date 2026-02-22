#!/usr/bin/env python3
"""Standalone script to read expenses from MongoDB."""

import json
from datetime import datetime

from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "expensetrending"
COLLECTION_NAME = "expenses"


def read_all_expenses():
    """Read and print all expenses from MongoDB."""
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    count = collection.count_documents({})
    print(f"Total expenses in database: {count}\n")

    if count == 0:
        print("No expenses found.")
        client.close()
        return

    print("=" * 60)
    for expense in collection.find():
        # Remove MongoDB _id for cleaner output
        expense.pop("_id", None)
        print(json.dumps(expense, indent=2))
        print("-" * 60)

    client.close()


def read_expenses_by_bank(bank: str):
    """Read expenses filtered by bank."""
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    count = collection.count_documents({"bank": bank})
    print(f"Expenses for {bank.upper()}: {count}\n")

    if count == 0:
        print(f"No expenses found for {bank}.")
        client.close()
        return

    print("=" * 60)
    for expense in collection.find({"bank": bank}):
        expense.pop("_id", None)
        print(json.dumps(expense, indent=2))
        print("-" * 60)

    client.close()


def get_summary():
    """Get summary statistics."""
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    total = collection.count_documents({})
    print(f"Total expenses: {total}")

    # Group by bank
    pipeline = [
        {"$group": {"_id": "$bank", "count": {"$sum": 1}, "total": {"$sum": "$amount"}}}
    ]
    results = list(collection.aggregate(pipeline))

    print("\nBy Bank:")
    for r in results:
        print(f"  {r['_id'].upper()}: {r['count']} transactions, Total: ₹{r['total']:,.2f}")

    # Group by transaction type
    pipeline = [
        {"$group": {"_id": "$transaction_type", "count": {"$sum": 1}, "total": {"$sum": "$amount"}}}
    ]
    results = list(collection.aggregate(pipeline))

    print("\nBy Type:")
    for r in results:
        print(f"  {r['_id']}: {r['count']} transactions, Total: ₹{r['total']:,.2f}")

    client.close()


def _to_mongo_date_str(date_str: str) -> str:
    """Convert YYYY-MM-DD to DD/MM/YYYY for MongoDB query matching."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%d/%m/%Y")


def read_filtered_expenses(
    bank: str | None = None,
    category: str | None = None,
    transaction_type: str | None = None,
    since_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    """Return expenses matching the given filters.

    Args:
        bank: Filter by bank name (e.g. "hdfc", "sbi").
        category: Filter by category (e.g. "food", "travel").
        transaction_type: Filter by "debit" or "credit".
        since_date: Only include expenses on or after this date (YYYY-MM-DD).
        to_date: Only include expenses on or before this date (YYYY-MM-DD).

    Returns:
        List of expense dicts (without _id).
    """
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    query: dict = {}
    if bank:
        query["bank"] = bank
    if category:
        query["category"] = category
    if transaction_type:
        query["transaction_type"] = transaction_type

    # Dates are stored as DD/MM/YYYY strings. Use $expr with
    # $dateFromString to parse and compare them in the query.
    date_conditions = []
    if since_date:
        since_str = _to_mongo_date_str(since_date)
        date_conditions.append({
            "$gte": [
                {"$dateFromString": {"dateString": "$date", "format": "%d/%m/%Y"}},
                {"$dateFromString": {"dateString": since_str, "format": "%d/%m/%Y"}},
            ]
        })
    if to_date:
        to_str = _to_mongo_date_str(to_date)
        date_conditions.append({
            "$lte": [
                {"$dateFromString": {"dateString": "$date", "format": "%d/%m/%Y"}},
                {"$dateFromString": {"dateString": to_str, "format": "%d/%m/%Y"}},
            ]
        })

    if date_conditions:
        query["$expr"] = {"$and": date_conditions} if len(date_conditions) > 1 else date_conditions[0]

    expenses = []
    for expense in collection.find(query, {"_id": 0}):
        expenses.append(expense)

    client.close()
    return expenses


def _parse_cli_filters(argv: list[str]) -> dict:
    """Parse filter arguments from CLI args list."""
    kwargs = {}
    i = 0
    while i < len(argv):
        if argv[i] == "--bank" and i + 1 < len(argv):
            kwargs["bank"] = argv[i + 1]
            i += 2
        elif argv[i] == "--category" and i + 1 < len(argv):
            kwargs["category"] = argv[i + 1]
            i += 2
        elif argv[i] == "--type" and i + 1 < len(argv):
            kwargs["transaction_type"] = argv[i + 1]
            i += 2
        elif argv[i] == "--since" and i + 1 < len(argv):
            kwargs["since_date"] = argv[i + 1]
            i += 2
        elif argv[i] == "--to" and i + 1 < len(argv):
            kwargs["to_date"] = argv[i + 1]
            i += 2
        else:
            i += 1
    return kwargs


FILTER_ARGS = {"--filter", "--bank", "--category", "--type", "--since", "--to"}


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--summary":
            get_summary()
        elif arg in FILTER_ARGS:
            # All filter flags route to read_filtered_expenses
            # Skip "--filter" if it's the first arg, parse the rest
            start = 2 if arg == "--filter" else 1
            kwargs = _parse_cli_filters(sys.argv[start:])
            results = read_filtered_expenses(**kwargs)
            print(f"Found {len(results)} expenses\n")
            print("=" * 60)
            for expense in results:
                print(json.dumps(expense, indent=2))
                print("-" * 60)
        else:
            print("Usage:")
            print("  python read_expenses.py                        # Read all expenses")
            print("  python read_expenses.py --summary              # Show summary statistics")
            print("  python read_expenses.py --bank hdfc            # Filter by bank")
            print("  python read_expenses.py --since 2025-01-01     # Filter by date")
            print("  python read_expenses.py --filter [OPTIONS]     # Filter with multiple criteria")
            print("    --bank BANK        Filter by bank (hdfc, sbi, idfc)")
            print("    --category CAT     Filter by category (food, travel, etc.)")
            print("    --type TYPE        Filter by transaction type (debit, credit)")
            print("    --since YYYY-MM-DD Only include expenses on or after this date")
            print("    --to YYYY-MM-DD    Only include expenses on or before this date")
    else:
        read_all_expenses()
