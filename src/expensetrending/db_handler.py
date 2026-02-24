"""MongoDB handler for storing expense data."""

from dataclasses import asdict

from bson import ObjectId
from pymongo import MongoClient

from .statement_parser import ExpenseItem, normalize_date_str

DEFAULT_MONGO_URI = "mongodb://localhost:27017"
DEFAULT_DB_NAME = "expensetrending"
DEFAULT_COLLECTION_NAME = "expenses"


class ExpenseDB:
    """Handle MongoDB operations for expenses."""

    def __init__(
        self,
        mongo_uri: str = DEFAULT_MONGO_URI,
        db_name: str = DEFAULT_DB_NAME,
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]

    def save_expense(self, expense: ExpenseItem) -> str:
        """Save a single expense to the database."""
        result = self.collection.insert_one(asdict(expense))
        return str(result.inserted_id)

    def save_expenses(self, expenses: list[ExpenseItem]) -> int:
        """Save multiple expenses to the database."""
        if not expenses:
            return 0
        docs = [asdict(e) for e in expenses]
        result = self.collection.insert_many(docs)
        return len(result.inserted_ids)

    def flush_collection(self) -> int:
        """Delete all documents in the collection."""
        result = self.collection.delete_many({})
        return result.deleted_count

    def get_expense_count(self) -> int:
        """Get the total number of expenses in the collection."""
        return self.collection.count_documents({})

    def normalize_dates(self) -> int:
        """Migrate all date values in the collection to DD/MM/YYYY format.

        Returns the number of documents updated.
        """
        updated = 0
        for doc in self.collection.find():
            old_date = doc.get("date", "")
            new_date = normalize_date_str(old_date)
            if new_date != old_date:
                self.collection.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"date": new_date}},
                )
                updated += 1
        return updated

    @staticmethod
    def _serialize(doc: dict) -> dict:
        """Convert MongoDB doc to JSON-safe dict with string _id."""
        doc["_id"] = str(doc["_id"])
        return doc

    def get_all_debits(self) -> list[dict]:
        """Return all documents where transaction_type is debit."""
        return [self._serialize(d) for d in self.collection.find({"transaction_type": "debit"})]

    def get_filtered_expenses(
        self,
        bank: str | None = None,
        category: str | None = None,
    ) -> list[dict]:
        """Return debit expenses with optional bank/category filters."""
        query: dict = {"transaction_type": "debit"}
        if bank:
            query["bank"] = bank
        if category:
            query["category"] = category
        return [self._serialize(d) for d in self.collection.find(query)]

    def get_distinct_values(self, field: str) -> list[str]:
        """Return distinct values for a field among debit transactions."""
        return self.collection.distinct(field, {"transaction_type": "debit"})

    def search_by_description(self, description: str) -> list[dict]:
        """Return debit expenses whose description contains the given substring (case-insensitive)."""
        query = {
            "transaction_type": "debit",
            "description": {"$regex": description, "$options": "i"},
        }
        return [self._serialize(d) for d in self.collection.find(query)]

    def update_expense(self, expense_id: str, updates: dict) -> bool:
        """Update specific fields of an expense by its _id.

        Returns True if a document was modified.
        """
        result = self.collection.update_one(
            {"_id": ObjectId(expense_id)},
            {"$set": updates},
        )
        return result.modified_count > 0

    def close(self) -> None:
        """Close the MongoDB connection."""
        self.client.close()
