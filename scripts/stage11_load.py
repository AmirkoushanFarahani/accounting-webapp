"""Controlled isolated capacity experiments; no retries of financial writes."""

import asyncio
import json
import os
import random
import sys
import time
from collections import Counter
from pathlib import Path
from uuid import uuid4

import httpx
from run_load_test import key, percentile, token


async def main():
    users, duration, tokens, admission = map(int, sys.argv[1:5])
    mode = sys.argv[5]
    output = sys.argv[6]
    base = os.environ.get("STAGE11_URL", "http://azari-stage11-backend:8000")
    assert base in ("http://azari-stage11-backend:8000", "http://127.0.0.1:18111")
    assert 1 <= users <= 300 and 10 <= duration <= 600
    rows, lag = [], []
    started = time.perf_counter()
    cpu = time.process_time()
    stop = asyncio.Event()
    async with httpx.AsyncClient(
        base_url=base, timeout=10, trust_env=False,
        limits=httpx.Limits(max_connections=users*5+10, max_keepalive_connections=users*5),
    ) as client:
        assert (await client.get("/api/v1/ready")).status_code == 200
        configured = await client.post("/__stage11/reset", json={"tokens": tokens, "admission": admission})
        configured.raise_for_status()
        warm = await client.get("/api/v1/dashboard", headers={"Authorization": "Bearer " + token(500)})
        warm.raise_for_status()
        steady_start = time.perf_counter() + 10
        end = steady_start + duration

        async def monitor():
            while not stop.is_set():
                tick = time.perf_counter()
                await asyncio.sleep(0.1)
                lag.append(time.perf_counter()-tick-0.1)

        async def request(i, path, method="GET", data=None):
            tick = time.perf_counter()
            try:
                response = await client.request(method, "/api/v1" + path,
                    headers={"Authorization": "Bearer " + token(i)}, json=data)
                code = str(response.status_code)
                body = response.json()
                if response.is_success and path == "/auth/me" and body["id"] != key(f"user-{i}"):
                    code = "ISOLATION_ERROR"
                if response.is_success and path == "/dashboard" and mode in ("mixed", "reads"):
                    if float(body["total_revenue"]) != 100000:
                        code = "FINANCIAL_ERROR"
                size = len(response.content)
            except httpx.HTTPError as exc:
                code, body, size = type(exc).__name__, None, 0
            rows.append({"at": tick, "seconds": time.perf_counter()-tick, "status": code,
                         "path": path if len(path)<50 else method + "/detail", "bytes": size,
                         "steady": tick >= steady_start})
            return body if code in ("200", "201") else None

        async def user_loop(n):
            rng = random.Random(n)
            i = n + 500  # untouched equivalent owners, separate from previous benchmark writers
            await asyncio.sleep(10*n/users)
            while time.perf_counter() < end:
                paths = ["/dashboard", "/dashboard", "/invoices", "/parties",
                         "/reports/customers", "/reports/trial-balance", "/expenses",
                         "/auth/me", "/products", "WRITE_DRAFT"]
                if mode == "reads":
                    paths[-1] = "/accounts"
                if mode == "dashboard":
                    await asyncio.gather(*(request(i, p) for p in (
                        "/dashboard", "/reports/cash-flow", "/invoices", "/payments", "/ml/predictions")))
                elif mode == "ml":
                    path, data = rng.choice([
                        ("/ml/transactions/classify", {"description": "office equipment purchase"}),
                        ("/ml/payment-risk/predict", {"invoice_id": key(f"invoice-{i}-0"), "as_of": "2026-09-10"}),
                        ("/ml/cash-flow/forecast", {"horizon": 30, "as_of": "2026-09-10"}),
                        ("/ml/segmentation/predict", {"party_id": key(f"party-{i}-0"), "as_of": "2026-09-10"}),
                    ])
                    await request(i, path, "POST", data)
                else:
                    path = rng.choice(paths)
                    if path == "WRITE_DRAFT":
                        await request(i, "/invoices", "POST", {
                            "invoice_number": "S11-" + uuid4().hex, "customer_id": key(f"party-{i}-0"),
                            "issue_date": "2026-09-10", "due_date": "2026-09-10",
                            "items": [{"description": "Isolated capacity", "quantity": 1, "unit_price": 100000}],
                        })
                    else:
                        await request(i, path)
                await asyncio.sleep(rng.uniform(0.8, 1.2))

        watcher = asyncio.create_task(monitor())
        await asyncio.gather(*(user_loop(n) for n in range(users)))
        stop.set()
        await watcher
        await asyncio.sleep(1)
        ready = (await client.get("/api/v1/ready")).status_code
        diagnostics = (await client.get("/__stage11")).json()
    selected = [r for r in rows if r["steady"]]
    codes = Counter(r["status"] for r in selected)
    latencies = [r["seconds"] for r in selected]
    errors = sum(v for k, v in codes.items() if k not in ("200", "201"))
    summary = {"users": users, "steady_seconds": duration, "mode": mode,
               "tokens": tokens, "admission": admission, "requests": len(selected),
               "codes": dict(codes), "error_percent": 100*errors/max(1,len(selected)),
               "p50": percentile(latencies, .5), "p95": percentile(latencies, .95),
               "p99": percentile(latencies, .99), "rps": len(selected)/duration,
               "ready": ready, "generator_cpu_seconds": time.process_time()-cpu,
               "elapsed": time.perf_counter()-started, "generator_lag_p95": percentile(lag, .95)}
    summary["gate"] = errors/max(1,len(selected)) <= .01 and summary["p95"] <= 2 and ready == 200
    Path(output).write_text(json.dumps({"summary": summary, "client": rows, "diagnostics": diagnostics}))
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
