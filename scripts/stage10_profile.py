"""Profile real API workflows against existing isolated fixtures, never live data."""

import json
import os
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from uuid import uuid4

import httpx
from run_load_test import key as fixture_key
from run_load_test import token

PROFILE_USER = int(os.environ.get("STAGE10_PROFILE_USER", "9999"))


def key(label):
    return fixture_key(label.replace("9999", str(PROFILE_USER)))


def main():
    port = int(sys.argv[1])
    assert port in {18102, 18103}
    info = json.loads(
        subprocess.check_output(["docker", "inspect", "azari-load-backend"])
    )[0]
    env = dict(item.split("=", 1) for item in info["Config"]["Env"])
    assert env["DATABASE_URL"].endswith("/azari_load_test")
    os.environ["LOAD_JWT_SECRET"] = env["JWT_SECRET"]
    samples = defaultdict(list)
    with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30) as client:
        client.headers["Authorization"] = "Bearer " + token(PROFILE_USER)

        def call(label, method, path, data=None):
            start = time.perf_counter()
            response = client.request(method, "/api/v1" + path, json=data)
            row = {
                "seconds": time.perf_counter() - start,
                "status": response.status_code,
            }
            row.update(json.loads(response.headers.get("x-stage10", "{}")))
            samples[label].append(row)
            if response.status_code >= 400:
                print(label, response.status_code, flush=True)
                return None
            return response.json()

        paths = [
            "/auth/me",
            "/parties",
            "/products",
            "/accounts",
            "/invoices",
            "/reports/customers",
            "/reports/trial-balance",
            "/reports/income-statement",
            "/reports/balance-sheet",
            "/reports/receivables",
            "/reports/payables",
            "/reports/cash-flow",
            "/dashboard",
            f"/reports/parties/{key('party-9999-0')}/history",
        ]
        for path in paths:
            for _ in range(12):
                call(path.replace(key("party-9999-0"), "{id}"), "GET", path)
        init = json.loads(
            subprocess.check_output(["docker", "inspect", "azari-load-initializer"])
        )[0]
        init_env = dict(item.split("=", 1) for item in init["Config"]["Env"])
        for _ in range(3):
            call(
                "/auth/login",
                "POST",
                "/auth/login",
                {
                    "email": f"load{PROFILE_USER}@example.com",
                    "password": init_env["LOAD_PASSWORD"],
                },
            )
        # Only this existing isolated fixture account is used for write profiling.
        cash = call(
            "setup/account",
            "POST",
            "/accounts",
            {
                "code": "S10-" + uuid4().hex[:10],
                "name": "Stage10 isolated cash",
                "category_id": key("category-9999-ASSET"),
                "posting_role": "CASH",
            },
        )
        for _ in range(12):
            journal = call(
                "journal/create",
                "POST",
                "/journals",
                {
                    "entry_number": "S10-" + uuid4().hex,
                    "entry_date": "2026-09-10",
                    "description": "Isolated profiling",
                    "period_id": key("period-9999"),
                    "lines": [
                        {"account_id": key("account-9999-RECEIVABLE"), "debit": 100},
                        {"account_id": key("account-9999-REVENUE"), "credit": 100},
                    ],
                },
            )
            if journal:
                call("journal/post", "POST", f"/journals/{journal['id']}/post")
                call("journal/reverse", "POST", f"/journals/{journal['id']}/reverse")
            invoice = call(
                "invoice/create",
                "POST",
                "/invoices",
                {
                    "invoice_number": "S10-" + uuid4().hex,
                    "customer_id": key("party-9999-0"),
                    "issue_date": "2026-09-10",
                    "due_date": "2026-09-10",
                    "items": [
                        {
                            "description": "Isolated profiling",
                            "quantity": 1,
                            "unit_price": 100,
                        }
                    ],
                },
            )
            if invoice and cash:
                call(
                    "invoice/issue",
                    "POST",
                    f"/invoices/{invoice['id']}/issue",
                    {
                        "receivable_account_id": key("account-9999-RECEIVABLE"),
                        "revenue_account_id": key("account-9999-REVENUE"),
                    },
                )
                payment = call(
                    "payment/create",
                    "POST",
                    "/payments",
                    {
                        "party_id": key("party-9999-0"),
                        "payment_date": "2026-09-10",
                        "amount": 100,
                        "reference": "S10-" + uuid4().hex,
                        "method": "CASH",
                        "allocations": [{"invoice_id": invoice["id"], "amount": 100}],
                    },
                )
                if payment:
                    call(
                        "payment/post",
                        "POST",
                        f"/payments/{payment['id']}/post",
                        {
                            "cash_account_id": cash["id"],
                            "receivable_account_id": key("account-9999-RECEIVABLE"),
                        },
                    )
        existing = call("setup/models", "GET", "/ml/models") or []
        for pipeline, identifier in [
            ("transaction_classification", "transaction/transaction-v1"),
            ("payment_delay_risk", "payment-risk/payment-risk-v1"),
            ("cash_flow_forecast", "cash-flow/cash-flow-v1"),
            ("customer_segmentation", "segmentation/customer-segments-v1"),
        ]:
            model = next((m for m in existing if m["pipeline"] == pipeline), None)
            if model is None:
                model = call(
                    "setup/register",
                    "POST",
                    "/ml/models/register",
                    {"pipeline": pipeline, "artifact_identifier": identifier},
                )
            if model:
                call("setup/activate", "POST", f"/ml/models/{model['id']}/activate")
        for path, data in [
            ("/ml/transactions/classify", {"description": "office equipment purchase"}),
            (
                "/ml/payment-risk/predict",
                {"invoice_id": key("invoice-9999-0"), "as_of": "2026-09-10"},
            ),
            ("/ml/cash-flow/forecast", {"horizon": 30, "as_of": "2026-09-10"}),
            (
                "/ml/segmentation/predict",
                {"party_id": key("party-9999-0"), "as_of": "2026-09-10"},
            ),
        ]:
            for _ in range(12):
                call(path, "POST", path, data)
        time.sleep(1)
        server = client.get("/__stage10").json()
    Path(sys.argv[2]).write_text(
        json.dumps({"client": samples, "server": server}, indent=2)
    )
    for label, rows in samples.items():
        print(
            label,
            "n",
            len(rows),
            "mean_ms",
            round(statistics.mean(r["seconds"] for r in rows) * 1000, 2),
            "queries",
            round(statistics.mean(r.get("queries", 0) for r in rows), 1),
            flush=True,
        )


if __name__ == "__main__":
    main()
