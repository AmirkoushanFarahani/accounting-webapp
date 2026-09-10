from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from backend.app.db.database import SessionLocal
from backend.app.db.models import Expense, JournalEntry
from backend.app.schemas.expense import ExpenseCreate
from backend.app.services.accounting import AccountingError, ConflictError
from backend.app.services.reporting import ReportingService
from backend.tests.test_accounting import domain
from backend.tests.test_accounting_api import headers_for_admin
from fastapi.testclient import TestClient
from sqlalchemy import select


@pytest.mark.parametrize("method", ["CASH", "CHECK", "BANK_TRANSFER"])
def test_paid_expense_posts_once_and_updates_reports(method: str) -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        expense = service.create_expense(
            ExpenseCreate(
                name="Utilities",
                amount=Decimal("125.50"),
                payment_date=date(2026, 2, 1),
                method=method,
                expense_account_id=values.expense.id,
                cash_account_id=values.cash.id,
            )
        )
        journal = session.get(JournalEntry, expense.journal_id)
        assert journal is not None and journal.status == "POSTED"
        assert [(line.account_id, line.debit, line.credit) for line in journal.lines] == [
            (values.expense.id, Decimal("125.50"), Decimal("0")),
            (values.cash.id, Decimal("0"), Decimal("125.50")),
        ]
        reports = ReportingService(session, values.admin.id)
        assert reports.cash_flow().total_outflow == Decimal("125.50")
        assert reports.income_statement().total_expenses == Decimal("125.50")
        assert reports.trial_balance().balanced
        assert reports.cash_flow(date(2026, 2, 2), None).total_outflow == 0
        assert ReportingService(session, uuid4()).cash_flow().total_outflow == 0
        with pytest.raises(ConflictError, match="Source-document"):
            service.reverse_journal(journal.id)


@pytest.mark.parametrize("failure", ["closed", "missing_period", "wrong_role", "foreign_account"])
def test_expense_rejects_invalid_posting_atomically(failure: str) -> None:
    with SessionLocal() as session:
        service, values = domain(session)
        if failure == "closed":
            values.period.status = "CLOSED"
            session.commit()
        data = ExpenseCreate(
            name="Utilities",
            amount=Decimal("10"),
            payment_date=date(2030, 1, 1) if failure == "missing_period" else date(2026, 2, 1),
            method="CASH",
            cash_account_id=values.cash.id,
            expense_account_id=uuid4()
            if failure == "foreign_account"
            else values.revenue.id
            if failure == "wrong_role"
            else values.expense.id,
        )
        with pytest.raises(AccountingError):
            service.create_expense(data)
        assert list(session.scalars(select(Expense))) == []
        assert list(session.scalars(select(JournalEntry))) == []


def test_expense_api_filter_isolation_and_validation(client: TestClient) -> None:
    first = headers_for_admin(client, "expense1@example.com")
    second = headers_for_admin(client, "expense2@example.com")

    def post(path: str, data: dict) -> dict:
        response = client.post("/api/v1/" + path, json=data, headers=first)
        assert response.status_code == 201, response.text
        return response.json()

    accounts = []
    for kind, role in [("ASSET", "CASH"), ("EXPENSE", "EXPENSE")]:
        category = post("account-categories", {"name": kind, "account_type": kind})
        accounts.append(
            post(
                "accounts",
                {"code": role, "name": role, "category_id": category["id"], "posting_role": role},
            )["id"]
        )
    post("periods", {"name": "Test", "start_date": "2026-01-01", "end_date": "2026-12-31"})
    data = {
        "name": "Electricity",
        "amount": "100",
        "payment_date": "2026-02-01",
        "method": "BANK_TRANSFER",
        "tracking_code": "00123",
        "cash_account_id": accounts[0],
        "expense_account_id": accounts[1],
    }
    assert post("expenses", data)["tracking_code"] == "00123"
    assert (
        client.get(
            "/api/v1/expenses?start_date=2026-02-01&end_date=2026-02-01", headers=first
        ).json()["total"]
        == "100.00"
    )
    assert client.get("/api/v1/expenses?start_date=2026-02-02", headers=first).json()["items"] == []
    assert client.get("/api/v1/expenses", headers=second).json()["items"] == []
    assert client.get("/api/v1/expenses").status_code == 401
    assert (
        client.get(
            "/api/v1/expenses?start_date=2026-03-01&end_date=2026-01-01", headers=first
        ).status_code
        == 422
    )
    for invalid in [{"amount": "0"}, {"name": " "}, {"method": "INVALID"}, {"amount": "1.001"}]:
        assert (
            client.post("/api/v1/expenses", json={**data, **invalid}, headers=first).status_code
            == 422
        )
    assert client.post("/api/v1/expenses", json=data, headers=second).status_code in (404, 422)
