"""Resume the existing isolated test without reseeding or touching live containers."""

import asyncio
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import httpx
from run_load_test import BASE, phase


def docker(*args):
    return subprocess.run(
        ["docker", *args], check=True, capture_output=True, text=True
    ).stdout


async def main():
    report_path = Path("LOAD_TEST_RESULTS.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if any(
        stage["error_percent"] > 1
        or (stage["p95_seconds"] or 0) > 2
        or stage["readiness_after"] != 200
        for stage in report["stages"]
    ):
        raise RuntimeError(
            "A completed stage exceeded safety thresholds; diagnose before testing higher load."
        )
    info = json.loads(docker("inspect", "azari-load-backend"))[0]
    env = dict(item.split("=", 1) for item in info["Config"]["Env"])
    assert env["DATABASE_URL"].endswith("@load-db:5432/azari_load_test")
    assert "azari-load-test" in info["NetworkSettings"]["Networks"]
    os.environ["LOAD_JWT_SECRET"] = env["JWT_SECRET"]
    docker("start", "azari-load-db", "azari-load-frontend")
    if not info["State"]["Running"]:
        # Keep the original initializer container for inspection; do not rerun its seed.
        docker("rename", "azari-load-backend", "azari-load-initializer")
        args = [
            "run",
            "-d",
            "--name",
            "azari-load-backend",
            "--network",
            "azari-load-test",
            "--cpus",
            "2",
            "--memory",
            "1g",
            "-p",
            "127.0.0.1:18100:8000",
        ]
        for key in [
            "DATABASE_URL",
            "JWT_SECRET",
            "ML_MODEL_DIR",
            "AUTH_RATE_LIMIT_ATTEMPTS",
            "AUTH_RATE_LIMIT_WINDOW_SECONDS",
        ]:
            args.extend(["-e", f"{key}={env[key]}"])
        args.extend(
            [
                info["Image"],
                "uvicorn",
                "backend.app.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
                "--no-access-log",
            ]
        )
        docker(*args)
    async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
        for _ in range(30):
            try:
                if (await client.get(BASE + "/ready")).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
        else:
            raise RuntimeError("Isolated stack did not become ready")
    report["resumed_utc"] = datetime.now(UTC).isoformat()
    report["notes"].append(
        "Resumed existing synthetic database after Docker interruption; original 10-VU result retained; prior draft writes retained."
    )
    completed = {row["virtual_users"] for row in report["stages"]}
    for users in [100, 1000, 10000]:
        if users in completed:
            continue
        print(f"Starting {users} virtual users", flush=True)
        result = await phase(users)
        report["stages"].append(result)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {k: v for k, v in result.items() if k not in {"resources", "per_path"}}
            ),
            flush=True,
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
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(report.get("stop_reason", "All planned stages completed"), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
