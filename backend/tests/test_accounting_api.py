from typing import cast

from backend.app.core.passwords import hash_password
from backend.app.db.database import SessionLocal
from backend.app.db.models import Role, User
from fastapi.testclient import TestClient
from sqlalchemy import select


def headers_for_admin(
    client: TestClient, email: str = "stage3-admin@example.com"
) -> dict[str, str]:
    with SessionLocal.begin() as session:
        admin = session.scalar(select(Role).where(Role.name == "ADMIN"))
        session.add(
            User(
                email=email,
                password_hash=hash_password("stage-three-password"),
                first_name="Stage",
                last_name="Admin",
                roles=[admin],
            )
        )
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "stage-three-password"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def admin_headers(client: TestClient) -> dict[str, str]:
    return headers_for_admin(client)


def registered_owner_headers(client: TestClient) -> dict[str, str]:
    credentials = {
        "email": "workspace-owner@example.com",
        "password": "workspace-owner-password-123",
        "first_name": "Workspace",
        "last_name": "Owner",
    }
    response = client.post("/api/v1/auth/register", json=credentials)
    assert response.status_code == 201
    assert response.json()["roles"] == ["OWNER"]
    login = client.post(
        "/api/v1/auth/login",
        json={"email": credentials["email"], "password": credentials["password"]},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_registered_users_have_private_accounting_workspaces(client: TestClient) -> None:
    first = headers_for_admin(client, "owner-one@example.com")
    second = headers_for_admin(client, "owner-two@example.com")

    first_party = client.post(
        "/api/v1/parties",
        headers=first,
        json={"name": "Shared-looking customer", "is_customer": True},
    )
    assert first_party.status_code == 201
    second_party = client.post(
        "/api/v1/parties",
        headers=second,
        json={"name": "Shared-looking customer", "is_customer": True},
    )
    assert second_party.status_code == 201
    assert first_party.json()["id"] != second_party.json()["id"]

    first_list = client.get("/api/v1/parties", headers=first).json()
    second_list = client.get("/api/v1/parties", headers=second).json()
    assert [item["id"] for item in first_list] == [first_party.json()["id"]]
    assert [item["id"] for item in second_list] == [second_party.json()["id"]]
    assert (
        client.get(
            f"/api/v1/parties/{first_party.json()['id']}", headers=second
        ).status_code
        == 404
    )

    for headers in (first, second):
        category = client.post(
            "/api/v1/account-categories",
            headers=headers,
            json={"name": "Assets", "account_type": "ASSET"},
        )
        assert category.status_code == 201
        period = client.post(
            "/api/v1/periods",
            headers=headers,
            json={
                "name": "2026",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
            },
        )
        assert period.status_code == 201

    first_customers = client.get("/api/v1/reports/customers", headers=first)
    second_customers = client.get("/api/v1/reports/customers", headers=second)
    assert first_customers.status_code == second_customers.status_code == 200
    assert [item["party_id"] for item in first_customers.json()] == [
        first_party.json()["id"]
    ]
    assert [item["party_id"] for item in second_customers.json()] == [
        second_party.json()["id"]
    ]


def test_accounting_api_requires_authentication_and_permission(client: TestClient) -> None:
    assert client.get("/api/v1/parties").status_code == 401
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "viewer@example.com",
            "password": "viewer-password-123",
            "first_name": "View",
            "last_name": "Only",
        },
    )
    with SessionLocal.begin() as session:
        user = session.scalar(select(User).where(User.email == "viewer@example.com"))
        viewer = session.scalar(select(Role).where(Role.name == "VIEWER"))
        assert user is not None and viewer is not None
        user.roles = [viewer]
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "viewer@example.com", "password": "viewer-password-123"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/parties", headers=headers).status_code == 200
    assert client.post("/api/v1/parties", headers=headers, json={}).status_code == 403


def test_accounting_api_crud_post_and_reverse(client: TestClient) -> None:
    headers = registered_owner_headers(client)
    party = client.post(
        "/api/v1/parties",
        headers=headers,
        json={"name": "API Customer", "is_customer": True},
    )
    assert party.status_code == 201
    assert (
        client.patch(
            f"/api/v1/parties/{party.json()['id']}", headers=headers, json={"phone": "123"}
        ).status_code
        == 200
    )
    asset = client.post(
        "/api/v1/account-categories",
        headers=headers,
        json={"name": "API Assets", "account_type": "ASSET"},
    ).json()
    revenue_category = client.post(
        "/api/v1/account-categories",
        headers=headers,
        json={"name": "API Revenue", "account_type": "REVENUE"},
    ).json()
    debit = client.post(
        "/api/v1/accounts",
        headers=headers,
        json={
            "code": "API-100",
            "name": "Cash",
            "category_id": asset["id"],
            "posting_role": "CASH",
        },
    ).json()
    receivable = client.post(
        "/api/v1/accounts",
        headers=headers,
        json={
            "code": "API-110",
            "name": "Receivable",
            "category_id": asset["id"],
            "posting_role": "RECEIVABLE",
        },
    ).json()
    credit = client.post(
        "/api/v1/accounts",
        headers=headers,
        json={
            "code": "API-400",
            "name": "Revenue",
            "category_id": revenue_category["id"],
            "posting_role": "REVENUE",
        },
    ).json()
    period = client.post(
        "/api/v1/periods",
        headers=headers,
        json={"name": "API 2026", "start_date": "2026-01-01", "end_date": "2026-12-31"},
    ).json()
    journal = client.post(
        "/api/v1/journals",
        headers=headers,
        json={
            "entry_number": "API-J-1",
            "entry_date": "2026-06-01",
            "description": "API posting",
            "period_id": period["id"],
            "lines": [
                {"account_id": debit["id"], "debit": "50", "credit": "0"},
                {"account_id": credit["id"], "debit": "0", "credit": "50"},
            ],
        },
    )
    assert journal.status_code == 201
    posted = client.post(f"/api/v1/journals/{journal.json()['id']}/post", headers=headers)
    assert posted.status_code == 200 and posted.json()["status"] == "POSTED"
    reversal = client.post(f"/api/v1/journals/{journal.json()['id']}/reverse", headers=headers)
    assert reversal.status_code == 201 and reversal.json()["reversal_of_id"] == journal.json()["id"]
    assert (
        client.post(f"/api/v1/journals/{journal.json()['id']}/reverse", headers=headers).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/journals/{reversal.json()['id']}/reverse", headers=headers
        ).status_code
        == 409
    )
    invoice = client.post(
        "/api/v1/invoices",
        headers=headers,
        json={
            "invoice_number": "API-I-1",
            "customer_id": party.json()["id"],
            "issue_date": "2026-06-02",
            "due_date": "2026-06-02",
            "items": [
                {
                    "description": "Owner invoice",
                    "quantity": "1",
                    "unit_price": "75",
                }
            ],
        },
    )
    assert invoice.status_code == 201, invoice.text
    issued = client.post(
        f"/api/v1/invoices/{invoice.json()['id']}/issue",
        headers=headers,
        json={
            "receivable_account_id": receivable["id"],
            "revenue_account_id": credit["id"],
        },
    )
    assert issued.status_code == 200 and issued.json()["status"] == "ISSUED"
    report = client.get(
        "/api/v1/reports/trial-balance?end_date=2026-12-31", headers=headers
    )
    assert report.status_code == 200 and report.json()["balanced"] is True


def test_supplier_bill_and_payment_api_workflow_and_reversal_protection(
    client: TestClient,
) -> None:
    headers = registered_owner_headers(client)
    supplier = client.post(
        "/api/v1/parties",
        headers=headers,
        json={"name": "API Supplier", "is_supplier": True},
    ).json()
    categories = {
        account_type: client.post(
            "/api/v1/account-categories",
            headers=headers,
            json={"name": f"Bill {account_type}", "account_type": account_type},
        ).json()
        for account_type in ("ASSET", "LIABILITY", "EXPENSE")
    }

    def account(code: str, name: str, category: str, role: str) -> dict[str, object]:
        response = client.post(
            "/api/v1/accounts",
            headers=headers,
            json={
                "code": code,
                "name": name,
                "category_id": categories[category]["id"],
                "posting_role": role,
            },
        )
        assert response.status_code == 201, response.text
        return cast(dict[str, object], response.json())

    cash = account("B-100", "Bank", "ASSET", "CASH")
    payable = account("B-200", "Supplier payable", "LIABILITY", "PAYABLE")
    expense = account("B-500", "Purchases", "EXPENSE", "EXPENSE")
    client.post(
        "/api/v1/periods",
        headers=headers,
        json={"name": "Bills 2026", "start_date": "2026-01-01", "end_date": "2026-12-31"},
    )
    created = client.post(
        "/api/v1/bills",
        headers=headers,
        json={
            "bill_number": "API-B-1",
            "supplier_id": supplier["id"],
            "issue_date": "2026-03-01",
            "due_date": "2026-03-31",
            "items": [
                {
                    "description": "Purchased service",
                    "quantity": "1",
                    "unit_price": "100",
                    "tax": "10",
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    bill = created.json()
    assert client.get("/api/v1/bills", headers=headers).status_code == 200
    assert client.get(f"/api/v1/bills/{bill['id']}", headers=headers).status_code == 200
    issued = client.post(
        f"/api/v1/bills/{bill['id']}/issue",
        headers=headers,
        json={"expense_account_id": expense["id"], "payable_account_id": payable["id"]},
    )
    assert issued.status_code == 200 and issued.json()["status"] == "ISSUED"

    created_payment = client.post(
        "/api/v1/bill-payments",
        headers=headers,
        json={
            "party_id": supplier["id"],
            "payment_date": "2026-03-15",
            "amount": "110",
            "reference": "API-BP-1",
            "method": "check",
            "sayad_id": "OPTIONAL-BILL-SAYAD",
            "check_due_date": "2026-04-15",
            "allocations": [{"bill_id": bill["id"], "amount": "110"}],
        },
    )
    assert created_payment.status_code == 201, created_payment.text
    payment = created_payment.json()
    assert payment["sayad_id"] == "OPTIONAL-BILL-SAYAD"
    assert payment["check_due_date"] == "2026-04-15"
    assert client.get("/api/v1/bill-payments", headers=headers).status_code == 200
    assert (
        client.get(f"/api/v1/bill-payments/{payment['id']}", headers=headers).status_code == 200
    )
    posted = client.post(
        f"/api/v1/bill-payments/{payment['id']}/post",
        headers=headers,
        json={"cash_account_id": cash["id"], "payable_account_id": payable["id"]},
    )
    assert posted.status_code == 200 and posted.json()["status"] == "POSTED"
    assert (
        client.post(
            f"/api/v1/journals/{issued.json()['journal_id']}/reverse", headers=headers
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/journals/{posted.json()['journal_id']}/reverse", headers=headers
        ).status_code
        == 409
    )
