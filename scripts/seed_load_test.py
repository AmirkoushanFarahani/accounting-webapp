"""Synthetic bulk fixtures, restricted to the disposable load-test database."""

import json
import os
from datetime import UTC, date, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import insert, select

from backend.app.core.config import get_settings
from backend.app.core.passwords import hash_password
from backend.app.db.bootstrap import seed_rbac
from backend.app.db.database import SessionLocal
from backend.app.db.models import (
    Account,
    AccountCategory,
    FinancialPeriod,
    Invoice,
    InvoiceItem,
    JournalEntry,
    JournalLine,
    Party,
    Product,
    Role,
    User,
    user_roles,
)


def key(label: str):
    return uuid5(NAMESPACE_URL, "azari-isolated-load/" + label)


def main():
    if not get_settings().DATABASE_URL.endswith("/azari_load_test"):
        raise RuntimeError("Load fixtures may only be seeded into azari_load_test")
    count = 10000
    password_hash = hash_password(os.environ["LOAD_PASSWORD"])
    today = datetime.now(UTC).date()
    with SessionLocal.begin() as session:
        assert session.scalar(select(User.id).limit(1)) is None, (
            "Database must be empty"
        )
        seed_rbac(session)
        role = session.scalar(select(Role.id).where(Role.name == "OWNER"))
        for start in range(0, count, 250):
            rows = {
                name: []
                for name in [
                    "users",
                    "roles",
                    "parties",
                    "products",
                    "categories",
                    "accounts",
                    "periods",
                    "journals",
                    "lines",
                    "invoices",
                    "items",
                ]
            }
            for i in range(start, start + 250):
                owner = key(f"user-{i}")
                owned = {"owner_id": owner}
                rows["users"].append(
                    {
                        "id": owner,
                        "email": f"load{i}@example.com",
                        "password_hash": password_hash,
                        "first_name": "Load",
                        "last_name": str(i),
                    }
                )
                rows["roles"].append({"user_id": owner, "role_id": role})
                period = key(f"period-{i}")
                rows["periods"].append(
                    dict(
                        id=period,
                        **owned,
                        name="Load year",
                        start_date=date(today.year, 1, 1),
                        end_date=date(today.year, 12, 31),
                    )
                )
                for j in range(5):
                    rows["parties"].append(
                        dict(
                            id=key(f"party-{i}-{j}"),
                            **owned,
                            name=f"Customer {i}-{j}",
                            is_customer=True,
                        )
                    )
                for j in range(3):
                    rows["products"].append(
                        dict(
                            id=key(f"product-{i}-{j}"),
                            **owned,
                            name=f"Product {j}",
                            sku=f"P{j}",
                            unit_price=100000,
                        )
                    )
                for role_name, kind in [
                    ("RECEIVABLE", "ASSET"),
                    ("REVENUE", "REVENUE"),
                ]:
                    category = key(f"category-{i}-{kind}")
                    rows["categories"].append(
                        dict(id=category, **owned, name=kind, account_type=kind)
                    )
                    rows["accounts"].append(
                        dict(
                            id=key(f"account-{i}-{role_name}"),
                            **owned,
                            name=role_name,
                            code=role_name,
                            category_id=category,
                            posting_role=role_name,
                        )
                    )
                journal = key(f"journal-{i}")
                rows["journals"].append(
                    dict(
                        id=journal,
                        **owned,
                        entry_number="LOAD-J1",
                        entry_date=today,
                        description="Synthetic sale",
                        period_id=period,
                        status="POSTED",
                        created_by_id=owner,
                    )
                )
                rows["lines"].extend(
                    [
                        {
                            "id": key(f"line-{i}-0"),
                            "journal_id": journal,
                            "account_id": key(f"account-{i}-RECEIVABLE"),
                            "debit": 100000,
                            "credit": 0,
                        },
                        {
                            "id": key(f"line-{i}-1"),
                            "journal_id": journal,
                            "account_id": key(f"account-{i}-REVENUE"),
                            "debit": 0,
                            "credit": 100000,
                        },
                    ]
                )
                for j in range(3):
                    invoice = key(f"invoice-{i}-{j}")
                    rows["invoices"].append(
                        dict(
                            id=invoice,
                            **owned,
                            invoice_number=f"LOAD-I{j}",
                            customer_id=key(f"party-{i}-{j}"),
                            issue_date=today,
                            due_date=today,
                            subtotal=100000,
                            total=100000,
                            status="ISSUED" if j == 0 else "DRAFT",
                            journal_id=journal if j == 0 else None,
                        )
                    )
                    rows["items"].append(
                        {
                            "id": key(f"item-{i}-{j}"),
                            "invoice_id": invoice,
                            "description": "Synthetic item",
                            "quantity": 1,
                            "unit_price": 100000,
                            "line_subtotal": 100000,
                            "line_total": 100000,
                        }
                    )
            for table, name in [
                (User, "users"),
                (user_roles, "roles"),
                (Party, "parties"),
                (Product, "products"),
                (AccountCategory, "categories"),
                (Account, "accounts"),
                (FinancialPeriod, "periods"),
                (JournalEntry, "journals"),
                (JournalLine, "lines"),
                (Invoice, "invoices"),
                (InvoiceItem, "items"),
            ]:
                session.execute(insert(table), rows[name])
    print(
        json.dumps(
            {
                "users": count,
                "customers": count * 5,
                "products": count * 3,
                "invoices": count * 3,
                "posted_journals": count,
                "journal_lines": count * 2,
            }
        )
    )


if __name__ == "__main__":
    main()
