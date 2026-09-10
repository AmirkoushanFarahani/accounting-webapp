"""Bounded local HTTP load test. Never targets the real application's ports."""

import asyncio
import json
import os
import random
import subprocess
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

import httpx
import jwt

BASE = "http://127.0.0.1:18100/api/v1"
FRONT = "http://127.0.0.1:14173"


def key(label):
    return str(uuid5(NAMESPACE_URL, "azari-isolated-load/" + label))


def token(user):
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": key(f"user-{user}"),
            "type": "access",
            "iat": now,
            "exp": now + timedelta(hours=1),
            "jti": str(uuid4()),
        },
        os.environ["LOAD_JWT_SECRET"],
        algorithm="HS256",
    )


def percentile(values, fraction):
    return (
        round(
            sorted(values)[min(len(values) - 1, int((len(values) - 1) * fraction))], 3
        )
        if values
        else None
    )


def sample_resources():
    result = subprocess.run(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{json .}}",
            "azari-load-backend",
            "azari-load-db",
            "azari-load-frontend",
        ],
        capture_output=True,
        check=True,
        text=True,
        timeout=12,
    )
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


async def phase(users, seconds=30):
    start = time.monotonic()
    stop = asyncio.Event()
    latencies, codes, by_path = [], Counter(), defaultdict(list)
    resources, in_flight, max_in_flight = [], 0, 0
    lag = []

    async def monitor():
        while not stop.is_set():
            resources.extend(await asyncio.to_thread(sample_resources))
            await asyncio.sleep(3)

    async def event_loop_monitor():
        while not stop.is_set():
            tick = time.monotonic()
            await asyncio.sleep(0.2)
            lag.append(max(0, time.monotonic() - tick - 0.2))

    async with httpx.AsyncClient(
        timeout=10,
        limits=httpx.Limits(
            max_connections=users + 10, max_keepalive_connections=users
        ),
        trust_env=False,
    ) as client:

        async def user_loop(i):
            nonlocal in_flight, max_in_flight
            rng = random.Random(i)
            await asyncio.sleep(5 * i / users)
            headers = {"Authorization": "Bearer " + token(i)}
            while time.monotonic() - start < seconds and not stop.is_set():
                path = rng.choice(
                    [
                        "/dashboard",
                        "/dashboard",
                        "/invoices",
                        "/parties",
                        "/reports/customers",
                        "/reports/trial-balance",
                        "/expenses",
                        "/auth/me",
                        "/products",
                        "WRITE_DRAFT",
                    ]
                )
                tick = time.monotonic()
                in_flight += 1
                max_in_flight = max(max_in_flight, in_flight)
                try:
                    if path == "WRITE_DRAFT":
                        response = await client.post(
                            BASE + "/invoices",
                            headers=headers,
                            json={
                                "invoice_number": "LT-" + str(uuid4()),
                                "customer_id": key(f"party-{i}-0"),
                                "issue_date": datetime.now(UTC).date().isoformat(),
                                "due_date": datetime.now(UTC).date().isoformat(),
                                "items": [
                                    {
                                        "description": "Load draft",
                                        "quantity": "1",
                                        "unit_price": "100000",
                                        "tax": "0",
                                    }
                                ],
                            },
                        )
                    else:
                        response = await client.get(BASE + path, headers=headers)
                    code = str(response.status_code)
                    if response.is_success:
                        body = response.json()
                        if path == "/auth/me" and body["id"] != key(f"user-{i}"):
                            code = "ISOLATION_ERROR"
                        if (
                            path == "/dashboard"
                            and float(body["total_revenue"]) != 100000
                        ):
                            code = "FINANCIAL_ERROR"
                except httpx.HTTPError as exc:
                    code = type(exc).__name__
                finally:
                    in_flight -= 1
                elapsed = time.monotonic() - tick
                latencies.append(elapsed)
                codes[code] += 1
                by_path[path].append(elapsed)
                failures = sum(n for c, n in codes.items() if c not in {"200", "201"})
                if len(latencies) >= 50 and failures / len(latencies) > 0.05:
                    stop.set()
                await asyncio.sleep(rng.uniform(0.8, 1.2))

        watchers = [
            asyncio.create_task(monitor()),
            asyncio.create_task(event_loop_monitor()),
        ]
        await asyncio.gather(*(user_loop(i) for i in range(users)))
        stop.set()
        await asyncio.gather(*watchers)
        try:
            health = (await client.get(BASE + "/ready")).status_code
        except httpx.HTTPError:
            health = "unreachable"
    elapsed = time.monotonic() - start
    errors = sum(n for c, n in codes.items() if c not in {"200", "201"})
    return {
        "virtual_users": users,
        "elapsed_seconds": round(elapsed, 2),
        "requests": len(latencies),
        "rps": round(len(latencies) / elapsed, 2),
        "successful_rps": round((len(latencies) - errors) / elapsed, 2),
        "average_seconds": round(sum(latencies) / max(1, len(latencies)), 3),
        "status_counts": dict(codes),
        "error_percent": round(100 * errors / max(1, len(latencies)), 2),
        "p50_seconds": percentile(latencies, 0.5),
        "p95_seconds": percentile(latencies, 0.95),
        "p99_seconds": percentile(latencies, 0.99),
        "max_seconds": round(max(latencies, default=0), 3),
        "peak_inflight": max_in_flight,
        "client_event_loop_lag_p95": percentile(lag, 0.95),
        "readiness_after": health,
        "per_path": {
            path: {"requests": len(vals), "p95_seconds": percentile(vals, 0.95)}
            for path, vals in by_path.items()
        },
        "resources": resources,
    }


async def main():
    report = {
        "time_utc": datetime.now(UTC).isoformat(),
        "seed_users": 10000,
        "stages": [],
        "notes": [
            "API virtual users, not real browsers; 5s ramp, 0.8-1.2s think time, 10s request timeout",
            "90% reads, 10% draft-invoice writes; JWT preauthenticated sessions; no AI or payment-posting workload",
            "Stop escalation if p95 exceeds 2s, error rate exceeds 1%, or readiness fails",
            "Isolated Docker stack: backend 2 CPUs/1GiB, database 2 CPUs/1GiB, frontend 0.5CPU/128MiB; same physical host as generator",
            "Synthetic fixtures: 5 customers, 3 products, 3 invoices (1 issued,2 drafts) per user, plus balanced journal",
        ],
    }
    async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
        logins = await asyncio.gather(
            *(
                client.post(
                    BASE + "/auth/login",
                    json={
                        "email": f"load{i}@example.com",
                        "password": os.environ["LOAD_PASSWORD"],
                    },
                )
                for i in range(10)
            )
        )
        report["login_burst_same_ip"] = dict(
            Counter(str(r.status_code) for r in logins)
        )
        report["login_note"] = (
            "Default per-IP rate limit retained; 429 is expected protection, not a crash. This is not a distributed-login capacity test."
        )
        tick = time.monotonic()
        static = await asyncio.gather(
            *(client.get(FRONT + "/login") for _ in range(100))
        )
        report["frontend_100_parallel_html"] = {
            "status_counts": dict(Counter(str(r.status_code) for r in static)),
            "elapsed_seconds": round(time.monotonic() - tick, 2),
        }
    for users in [10, 100, 1000, 10000]:
        print(f"Starting {users} virtual users", flush=True)
        result = await phase(users)
        report["stages"].append(result)
        print(
            json.dumps(
                {k: v for k, v in result.items() if k not in {"resources", "per_path"}}
            ),
            flush=True,
        )
        Path("LOAD_TEST_RESULTS.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        if (
            result["error_percent"] > 1
            or (result["p95_seconds"] or 0) > 2
            or result["readiness_after"] != 200
        ):
            report["stop_reason"] = (
                f"Stopped escalation after {users} VUs: threshold exceeded. Larger stages NOT tested."
            )
            break
        await asyncio.sleep(3)
    Path("LOAD_TEST_RESULTS.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(report.get("stop_reason", "All planned stages completed"), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
