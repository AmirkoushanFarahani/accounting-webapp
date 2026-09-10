"""Create a new, isolated synthetic workspace through the local application's API.

Every invocation creates a new account. No existing account or model is modified.
Credentials are printed once, never written to a repository file.
Run: python scripts/seed_demo_workspace.py
"""

import json
import os
import secrets
import urllib.error
import urllib.request
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

BASE = "http://localhost:8100/api/v1"

PROFILES = {
    "RETAIL": (
        "فروشگاه نمونه",
        "عدد",
        [
            "دفتر",
            "خودکار",
            "کاغذ",
            "کیبورد",
            "ماوس",
            "نصب نرم‌افزار",
            "پشتیبانی",
            "آموزش",
        ],
    ),
    "EDUCATION": (
        "آموزشگاه نمونه",
        "دوره",
        [
            "زبان انگلیسی مقدماتی",
            "ریاضی",
            "برنامه‌نویسی پایتون",
            "نقاشی",
            "موسیقی",
            "آمادگی آزمون",
            "مکالمه زبان",
            "طراحی وب",
        ],
    ),
    "ONLINE": (
        "فروشگاه آنلاین نمونه",
        "عدد",
        [
            "هدفون",
            "قاب گوشی",
            "کابل شارژ",
            "کیف لپ‌تاپ",
            "پاوربانک",
            "چراغ مطالعه",
            "پایه موبایل",
            "ماوس بی‌سیم",
        ],
    ),
    "SERVICES": (
        "خدمات دوره‌ای نمونه",
        "جلسه",
        [
            "مشاوره",
            "نظافت دوره‌ای",
            "سرویس کولر",
            "تعمیر رایانه",
            "پشتیبانی ماهانه",
            "آموزش خصوصی",
            "عکاسی",
            "نگهداری تجهیزات",
        ],
    ),
}


def main():
    business_category = os.environ.get("DEMO_CATEGORY", "RETAIL")
    business_name, unit, product_names = PROFILES[business_category]
    token = None

    def api(path, data=None, method=None):
        # Resume only in the explicitly supplied demo workspace; never duplicate records.
        keys = {
            "/parties": "name",
            "/products": "sku",
            "/account-categories": "name",
            "/accounts": "code",
            "/periods": "name",
            "/journals": "entry_number",
            "/invoices": "invoice_number",
            "/bills": "bill_number",
            "/payments": "reference",
            "/bill-payments": "reference",
        }
        if token and data is not None and path in keys:
            key = keys[path]
            for existing in api(path):
                if existing[key] == data[key]:
                    return existing
        if token and data is not None and path.endswith(("/post", "/issue", "/close")):
            resource, record_id, action = path.rsplit("/", 2)
            existing = next(x for x in api(resource) if x["id"] == record_id)
            if existing["status"] != ("OPEN" if action == "close" else "DRAFT"):
                return existing
        if token and path.endswith("/reverse"):
            original_id = path.split("/")[-2]
            for existing in api("/journals"):
                if existing["reversal_of_id"] == original_id:
                    return existing
        if token and path.startswith("/invoice-checks/") and method == "PATCH":
            check_id = path.rsplit("/", 1)[1]
            for invoice in api("/invoices"):
                for check in invoice["checks"]:
                    if check["id"] == check_id and check["status"] == data["status"]:
                        return check
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request(
            BASE + path,
            headers=headers,
            method=method,
            data=json.dumps(data).encode() if data is not None else None,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"{request.get_method()} {path}: HTTP {exc.code}: {exc.read().decode()}"
            ) from None

    def money(value):
        return Decimal(str(value))

    today = datetime.now(UTC).date()
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    email = os.environ.get(
        "DEMO_EMAIL", f"demo.{business_category.lower()}.{stamp}@example.com"
    )
    password = os.environ.get("DEMO_PASSWORD") or "Demo-" + secrets.token_urlsafe(16)
    resuming = "DEMO_EMAIL" in os.environ
    if not resuming:
        print(json.dumps({"demo_email": email, "demo_password": password}), flush=True)
        api(
            "/auth/register",
            {
                "email": email,
                "password": password,
                "first_name": "آزمایشی",
                "last_name": business_name,
                "business_category": business_category,
            },
        )
    token = api("/auth/login", {"email": email, "password": password})["access_token"]
    user = api("/auth/me")
    assert user["roles"] == ["OWNER"]
    assert user["first_name"] == "آزمایشی" and user["last_name"] == business_name
    assert user["business_category"] == business_category
    if not resuming:
        assert api("/invoices") == [] and api("/parties") == []

    categories = {}
    for kind, name in [
        ("ASSET", "دارایی"),
        ("LIABILITY", "بدهی"),
        ("REVENUE", "درآمد"),
        ("EXPENSE", "هزینه"),
        ("EQUITY", "سرمایه"),
    ]:
        categories[kind] = api(
            "/account-categories", {"name": name, "account_type": kind}
        )["id"]
    accounts = {}
    specs = [
        ("CASH", "ASSET", "بانک آزمایشی"),
        ("RECEIVABLE", "ASSET", "مطالبات مشتریان"),
        ("REVENUE", "REVENUE", "فروش کالا و خدمات"),
        ("EXPENSE", "EXPENSE", "هزینه خرید"),
        ("PAYABLE", "LIABILITY", "بدهی تأمین‌کنندگان"),
        ("TAX_LIABILITY", "LIABILITY", "مالیات فروش"),
        ("CUSTOMER_CREDIT", "LIABILITY", "اعتبار مشتریان"),
        ("CAPITAL", "EQUITY", "سرمایه اولیه"),
        ("PETTY", "ASSET", "صندوق آزمایشی"),
    ]
    for index, (role, kind, name) in enumerate(specs, 1):
        accounts[role] = api(
            "/accounts",
            {
                "code": str(1000 + index),
                "name": name,
                "category_id": categories[kind],
                "posting_role": role if role not in {"CAPITAL", "PETTY"} else "GENERAL",
            },
        )["id"]
    period = api(
        "/periods",
        {
            "name": "دوره باز آزمایشی",
            "start_date": f"{today.year}-01-01",
            "end_date": f"{today.year}-12-31",
        },
    )
    old_period = api(
        "/periods",
        {
            "name": "دوره بسته آزمایشی",
            "start_date": f"{today.year - 1}-01-01",
            "end_date": f"{today.year - 1}-12-31",
        },
    )
    api(f"/periods/{old_period['id']}/close", {})

    def journal(number, description, amount, post=True):
        item = api(
            "/journals",
            {
                "entry_number": number,
                "entry_date": today.isoformat(),
                "description": description,
                "period_id": period["id"],
                "lines": [
                    {"account_id": accounts["CASH"], "debit": str(amount)},
                    {"account_id": accounts["CAPITAL"], "credit": str(amount)},
                ],
            },
        )
        if post:
            item = api(f"/journals/{item['id']}/post", {})
        return item

    journal("DEMO-OPENING", "سرمایه اولیه آزمایشی", 500000000)
    reversible = journal("DEMO-REVERSAL", "نمونه سند قابل برگشت", 200000)
    api(f"/journals/{reversible['id']}/reverse", {})
    journal("DEMO-DRAFT", "پیش‌نویس بدون اثر مالی", 900000, False)

    names = [
        "علی رضایی",
        "سارا احمدی",
        "رضا محمدی",
        "مریم کریمی",
        "حسین موسوی",
        "نرگس حسینی",
        "امیر جعفری",
        "فاطمه مرادی",
        "محمد صادقی",
        "زهرا رحیمی",
        "کیان نوری",
        "نگار عباسی",
        "آرمان شریفی",
        "پریسا کاظمی",
        "سامان اکبری",
        "الهام میرزایی",
    ]
    customers = [
        api(
            "/parties",
            {
                "name": name + " (آزمایشی)",
                "is_customer": True,
                "email": f"customer{i}@example.com",
                "address": "نشانی ساختگی برای تست",
            },
        )
        for i, name in enumerate(names, 1)
    ]
    suppliers = [
        api("/parties", {"name": name + " (آزمایشی)", "is_supplier": True})
        for name in ["تجهیزات آریا", "پخش سپهر", "خدمات نوین", "بازرگانی پارس"]
    ]
    products = [
        api(
            "/products",
            {
                "sku": f"DEMO-P{i:02}",
                "name": name,
                "description": "کالا یا خدمت ساختگی برای تست",
                "unit": unit,
                "unit_price": str(250000 * i),
            },
        )
        for i, name in enumerate(
            product_names,
            1,
        )
    ]
    print(
        "Created account, categories, accounts, periods, parties and products.",
        flush=True,
    )

    invoices = []
    for i in range(24):
        issued_on = max(date(today.year, 1, 1), today - timedelta(days=85 - i * 3))
        price = Decimal(500000 + i * 125000)
        quantity = 1 + i % 3
        subtotal = price * quantity
        tax = subtotal / 10 if i % 3 == 0 else Decimal(0)
        total = subtotal + tax
        checks = []
        if 14 <= i < 20:
            # Includes checks below, equal to, and above the invoice total.
            first = total * (Decimal("1.2") if i == 16 else Decimal("0.4"))
            second = total * Decimal("0.4")
            checks = [
                {
                    "amount": str(amount),
                    "due_date": (today + timedelta(days=15 * j - 10)).isoformat(),
                    "sayad_id": None if j == 0 else f"990000000000{i:02}{j:02}",
                    "status": "PENDING",
                }
                for j, amount in enumerate([first, second])
            ]
        item = api(
            "/invoices",
            {
                "invoice_number": f"DEMO-INV-{i + 1:03}",
                "customer_id": customers[i % 16]["id"],
                "issue_date": issued_on.isoformat(),
                "due_date": (issued_on + timedelta(days=30)).isoformat(),
                "payment_method": "CHECK" if checks else "CASH",
                "checks": checks,
                "items": [
                    {
                        "product_id": products[i % 8]["id"],
                        "description": products[i % 8]["name"],
                        "quantity": str(quantity),
                        "unit_price": str(price),
                        "tax": str(tax),
                    }
                ],
            },
        )
        if i < 20:
            item = api(
                f"/invoices/{item['id']}/issue",
                {
                    "receivable_account_id": accounts["RECEIVABLE"],
                    "revenue_account_id": accounts["REVENUE"],
                    "tax_liability_account_id": accounts["TAX_LIABILITY"]
                    if tax
                    else None,
                },
            )
        invoices.append(item)

    for i, invoice in enumerate(invoices[:11]):
        total = money(invoice["total"])
        allocation = total if i < 5 else total / 2
        amount = allocation + (Decimal(200000) if i == 4 else Decimal(0))
        payment = api(
            "/payments",
            {
                "party_id": invoice["customer_id"],
                "payment_date": (
                    date.fromisoformat(invoice["issue_date"]) + timedelta(days=10)
                ).isoformat(),
                "amount": str(amount),
                "reference": f"DEMO-PAY-{i + 1:03}",
                "method": "CASH",
                "customer_credit_account_id": accounts["CUSTOMER_CREDIT"],
                "allocations": [
                    {"invoice_id": invoice["id"], "amount": str(allocation)}
                ],
            },
        )
        if i < 10:
            api(
                f"/payments/{payment['id']}/post",
                {
                    "cash_account_id": accounts["CASH"],
                    "receivable_account_id": accounts["RECEIVABLE"],
                    "customer_credit_account_id": accounts["CUSTOMER_CREDIT"],
                },
            )
    for i in range(14, 18):
        api(
            f"/invoice-checks/{invoices[i]['checks'][0]['id']}",
            {
                "status": "CLEARED",
                "cash_account_id": accounts["CASH"],
                "customer_credit_account_id": accounts["CUSTOMER_CREDIT"],
                "cleared_date": today.isoformat(),
            },
            "PATCH",
        )
    for i in [15, 18]:
        api(
            f"/invoice-checks/{invoices[i]['checks'][1]['id']}",
            {"status": "BOUNCED"},
            "PATCH",
        )
    print(
        "Created sales, partial/full receipts, drafts and check scenarios.", flush=True
    )

    for i in range(12):
        issued_on = max(date(today.year, 1, 1), today - timedelta(days=70 - i * 4))
        bill = api(
            "/bills",
            {
                "bill_number": f"DEMO-BILL-{i + 1:03}",
                "supplier_id": suppliers[i % 4]["id"],
                "issue_date": issued_on.isoformat(),
                "due_date": (issued_on + timedelta(days=25)).isoformat(),
                "items": [
                    {
                        "description": "خرید آزمایشی " + products[i % 8]["name"],
                        "product_id": products[i % 8]["id"],
                        "quantity": "2",
                        "unit_price": str(200000 + i * 50000),
                        "tax": "40000" if i % 2 == 0 else "0",
                    }
                ],
            },
        )
        if i < 10:
            bill = api(
                f"/bills/{bill['id']}/issue",
                {
                    "expense_account_id": accounts["EXPENSE"],
                    "payable_account_id": accounts["PAYABLE"],
                },
            )
        if i < 7:
            amount = money(bill["total"]) / (1 if i < 3 else 2)
            payment = api(
                "/bill-payments",
                {
                    "party_id": bill["supplier_id"],
                    "payment_date": (issued_on + timedelta(days=12)).isoformat(),
                    "amount": str(amount),
                    "reference": f"DEMO-BP-{i + 1:03}",
                    "method": "CASH",
                    "allocations": [{"bill_id": bill["id"], "amount": str(amount)}],
                },
            )
            if i < 6:
                api(
                    f"/bill-payments/{payment['id']}/post",
                    {
                        "cash_account_id": accounts["CASH"],
                        "payable_account_id": accounts["PAYABLE"],
                    },
                )

    data = {
        path: api("/" + path)
        for path in [
            "parties",
            "products",
            "account-categories",
            "accounts",
            "periods",
            "invoices",
            "bills",
            "payments",
            "bill-payments",
            "journals",
        ]
    }
    inv = data["invoices"]
    bills = data["bills"]
    posted_invoices = [x for x in inv if x["status"] != "DRAFT"]
    posted_bills = [x for x in bills if x["status"] != "DRAFT"]
    receipts = [x for x in data["payments"] if x["status"] == "POSTED"]
    outgoing = [x for x in data["bill-payments"] if x["status"] == "POSTED"]
    total = lambda rows, key: sum((money(x[key]) for x in rows), Decimal(0))
    expected = {
        "revenue": total(posted_invoices, "subtotal"),
        "expenses": total(posted_bills, "total"),
        "receivables": total(posted_invoices, "balance_due"),
        "payables": total(posted_bills, "balance_due"),
        "inflow": total(receipts, "amount"),
        "outflow": total(outgoing, "amount"),
    }
    trial = api("/reports/trial-balance")
    balance = api("/reports/balance-sheet")
    income = api("/reports/income-statement")
    cash = api("/reports/cash-flow")
    assert trial["balanced"] and balance["balanced"]
    assert money(income["total_revenue"]) == expected["revenue"]
    assert money(income["total_expenses"]) == expected["expenses"]
    assert money(api("/reports/revenue")["total"]) == expected["revenue"]
    assert money(api("/reports/expenses")["total"]) == expected["expenses"]
    assert (
        money(api("/reports/receivables")["total_outstanding"])
        == expected["receivables"]
    )
    assert money(api("/reports/payables")["total_payables"]) == expected["payables"]
    assert money(cash["total_inflow"]) == expected["inflow"]
    assert money(cash["total_outflow"]) == expected["outflow"]
    for entry in data["journals"]:
        assert total(entry["lines"], "debit") == total(entry["lines"], "credit")
    summaries = api("/reports/customers")
    assert len(summaries) == 16
    for customer in customers:
        history = api(f"/reports/parties/{customer['id']}/history")
        owned = [x for x in posted_invoices if x["customer_id"] == customer["id"]]
        assert history["purchase_count"] == len(owned)
        assert money(history["total_purchased"]) == total(owned, "total")
    dashboard = api("/dashboard")
    assert dashboard == api("/dashboard")
    assert money(dashboard["total_revenue"]) == expected["revenue"]
    assert money(dashboard["total_expenses"]) == expected["expenses"]
    assert money(dashboard["outstanding_invoices"]) == expected["receivables"]
    checks = [c for x in inv for c in x["checks"]]
    counts = {key: len(rows) for key, rows in data.items()}
    counts["invoice_checks"] = len(checks)
    active = {x["pipeline"] for x in api("/ml/models") if x["is_active"]}
    ml_results = []
    if len(active) == 4 and not api("/ml/predictions"):
        for description in [
            "office rent payment",
            "business travel hotel booking",
            "هزینه اجاره دفتر",
            "خرید تجهیزات اداری",
        ]:
            prediction = api(
                "/ml/transactions/classify",
                {"description": description, "source_reference": "DEMO"},
            )
            assert 0 <= prediction["confidence"] <= 1
            ml_results.append(
                {
                    "pipeline": "classification",
                    "category": prediction["category"],
                    "confidence": prediction["confidence"],
                }
            )
        for invoice in [x for x in inv if x["status"] in {"ISSUED", "PARTIALLY_PAID"}][
            :4
        ]:
            prediction = api(
                "/ml/payment-risk/predict",
                {"invoice_id": invoice["id"], "as_of": today.isoformat()},
            )
            assert 0 <= prediction["probability"] <= 1
            ml_results.append(
                {
                    "pipeline": "risk",
                    "invoice": invoice["invoice_number"],
                    "risk": prediction["risk_category"],
                }
            )
        forecast = api(
            "/ml/cash-flow/forecast", {"horizon": 30, "as_of": today.isoformat()}
        )
        assert len(forecast["points"]) == 30
        assert all(
            p["lower"] <= p["predicted"] <= p["upper"] for p in forecast["points"]
        )
        ml_results.append({"pipeline": "forecast", "points": 30})
        for customer in customers[:8]:
            prediction = api(
                "/ml/segmentation/predict",
                {"party_id": customer["id"], "as_of": today.isoformat()},
            )
            assert prediction["behavioral_description"]
            ml_results.append(
                {"pipeline": "segmentation", "segment": prediction["segment"]}
            )
        for prediction in api("/ml/predictions")[:2]:
            api(
                f"/ml/predictions/{prediction['id']}/feedback",
                {
                    "feedback_type": "COMMENT",
                    "comment": "آزمایش عملکرد؛ این نتیجه تأیید واقعی تجاری نیست.",
                },
            )
        assert dashboard == api("/dashboard"), "AI must not change financial totals"
    predictions = api("/ml/predictions")
    counts["ml_predictions"] = len(predictions)
    counts["ml_feedback"] = sum(len(p["feedback"]) for p in predictions)
    print(
        json.dumps(
            {
                "user_id": user["id"],
                "counts": counts,
                "main_record_count": sum(counts.values()),
                "invoice_statuses": dict(Counter(x["status"] for x in inv)),
                "bill_statuses": dict(Counter(x["status"] for x in bills)),
                "check_statuses": dict(Counter(x["status"] for x in checks)),
                "customer_balance_directions": dict(
                    Counter(x["balance_direction"] for x in summaries)
                ),
                "expected_rials": {k: str(v) for k, v in expected.items()},
                "reports_verified": True,
                "active_ml_models": len(active),
                "ml_results": ml_results,
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
