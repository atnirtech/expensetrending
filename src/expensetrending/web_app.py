"""FastAPI web dashboard for expense data visualization."""

from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .db_handler import ExpenseDB
from .statement_parser import CATEGORY_KEYWORDS

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

db: ExpenseDB | None = None


def parse_date(date_str: str) -> datetime | None:
    """Parse a DD/MM/YYYY date string into a datetime object."""
    try:
        return datetime.strptime(date_str.strip(), "%d/%m/%Y")
    except ValueError:
        return None


def month_key(dt: datetime) -> str:
    """Return YYYY-MM string for grouping."""
    return dt.strftime("%Y-%m")


def filter_by_date_range(
    expenses: list[dict],
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Filter expenses by optional start/end date strings (YYYY-MM-DD)."""
    if not start_date and not end_date:
        return expenses

    start_dt = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None
    end_dt = datetime.strptime(end_date, "%Y-%m-%d") if end_date else None

    filtered = []
    for exp in expenses:
        dt = parse_date(exp.get("date", ""))
        if dt is None:
            continue
        if start_dt and dt < start_dt:
            continue
        if end_dt and dt > end_dt:
            continue
        filtered.append(exp)
    return filtered


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db
    db = ExpenseDB()
    yield
    if db:
        db.close()


app = FastAPI(title="ExpenseTrending Dashboard", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Serve the main dashboard page."""
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/api/monthly-trend")
async def monthly_trend():
    """Monthly totals grouped by bank for chart rendering."""
    expenses = db.get_all_debits()

    # bank -> month -> total
    data: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    all_months: set[str] = set()

    for exp in expenses:
        dt = parse_date(exp.get("date", ""))
        if dt is None:
            continue
        mk = month_key(dt)
        all_months.add(mk)
        data[exp["bank"]][mk] += exp["amount"]

    sorted_months = sorted(all_months)
    datasets = []
    for bank, monthly in sorted(data.items()):
        datasets.append({
            "bank": bank,
            "totals": [round(monthly.get(m, 0), 2) for m in sorted_months],
        })

    return {"months": sorted_months, "datasets": datasets}


@app.get("/api/category-breakdown")
async def category_breakdown(
    bank: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
):
    """Category totals for doughnut chart, with optional filters."""
    expenses = db.get_filtered_expenses(bank=bank)
    expenses = filter_by_date_range(expenses, start_date, end_date)

    totals: dict[str, float] = defaultdict(float)
    for exp in expenses:
        totals[exp.get("category", "other")] += exp["amount"]

    # Sort by amount descending
    sorted_cats = sorted(totals.items(), key=lambda x: x[1], reverse=True)
    return {
        "categories": [c[0] for c in sorted_cats],
        "amounts": [round(c[1], 2) for c in sorted_cats],
    }


@app.get("/api/transactions")
async def transactions(
    bank: str | None = Query(None),
    category: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort_by: str = Query("date"),
    sort_order: str = Query("desc"),
):
    """Paginated transaction list with sorting."""
    expenses = db.get_filtered_expenses(bank=bank, category=category)
    expenses = filter_by_date_range(expenses, start_date, end_date)

    reverse = sort_order == "desc"

    if sort_by == "amount":
        expenses.sort(key=lambda exp: exp.get("amount", 0), reverse=reverse)
    else:
        def sort_key(exp):
            dt = parse_date(exp.get("date", ""))
            return dt if dt else datetime.min
        expenses.sort(key=sort_key, reverse=reverse)

    total = len(expenses)
    start = (page - 1) * page_size
    end = start + page_size

    return {
        "transactions": expenses[start:end],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total else 0,
    }


@app.get("/api/transactions/search")
async def search_transactions(
    description: str = Query(..., min_length=1),
):
    """Search transactions by description substring (case-insensitive)."""
    results = db.search_by_description(description)
    return {"transactions": results, "total": len(results)}


@app.get("/api/filters")
async def filters():
    """Distinct banks, categories, and valid transaction types for dropdowns."""
    return {
        "banks": sorted(db.get_distinct_values("bank")),
        "categories": sorted(db.get_distinct_values("category")),
        "all_categories": sorted(VALID_CATEGORIES),
        "transaction_types": sorted(VALID_TRANSACTION_TYPES),
    }


@app.get("/api/summary")
async def summary():
    """Total spent, transaction count, and top category."""
    expenses = db.get_all_debits()
    total_spent = sum(exp["amount"] for exp in expenses)
    count = len(expenses)

    cat_totals: dict[str, float] = defaultdict(float)
    for exp in expenses:
        cat_totals[exp.get("category", "other")] += exp["amount"]

    top_category = max(cat_totals, key=cat_totals.get) if cat_totals else "N/A"

    return {
        "total_spent": round(total_spent, 2),
        "transaction_count": count,
        "top_category": top_category,
    }


VALID_TRANSACTION_TYPES = {"debit", "credit"}
VALID_CATEGORIES = set(CATEGORY_KEYWORDS.keys()) | {"other"}


class TransactionUpdate(BaseModel):
    """Request body for updating a transaction."""
    transaction_type: str | None = None
    category: str | None = None


@app.put("/api/transactions/{transaction_id}")
async def update_transaction(transaction_id: str, body: TransactionUpdate):
    """Update transaction_type and/or category for a transaction."""
    updates = {}

    if body.transaction_type is not None:
        if body.transaction_type not in VALID_TRANSACTION_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"transaction_type must be one of: {', '.join(VALID_TRANSACTION_TYPES)}",
            )
        updates["transaction_type"] = body.transaction_type

    if body.category is not None:
        if body.category not in VALID_CATEGORIES:
            raise HTTPException(
                status_code=400,
                detail=f"category must be one of: {', '.join(sorted(VALID_CATEGORIES))}",
            )
        updates["category"] = body.category

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updated = db.update_expense(transaction_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return {"status": "ok", "updated": updates}


def start_server():
    """Entry point for the CLI script."""
    uvicorn.run(
        "expensetrending.web_app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
