"""Capture aggregate isolated pool/thread/PG diagnostics during controlled load."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
from run_load_test import phase


async def main():
    info = json.loads(
        await asyncio.to_thread(
            subprocess.check_output, ["docker", "inspect", "azari-load-backend"]
        )
    )[0]
    env = dict(item.split("=", 1) for item in info["Config"]["Env"])
    assert env["DATABASE_URL"].endswith("/azari_load_test")
    os.environ["LOAD_JWT_SECRET"] = env["JWT_SECRET"]
    output = Path(sys.argv[1])
    data = {"stages": []}
    async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
        for _attempt in range(30):
            try:
                if (
                    await client.get("http://127.0.0.1:18100/api/v1/ready")
                ).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
        else:
            raise RuntimeError("Backend did not become ready before load")
        for level in map(int, sys.argv[2:]):
            print(f"Diagnostic stage {level}", flush=True)
            samples = []
            task = asyncio.create_task(phase(level))
            while not task.done():
                try:
                    sample = (await client.get("http://127.0.0.1:18100/__probe")).json()
                    sql = (
                        "SELECT state,wait_event_type,wait_event,count(*) "
                        "FROM pg_stat_activity WHERE datname='azari_load_test' "
                        "GROUP BY state,wait_event_type,wait_event"
                    )
                    pg = await asyncio.to_thread(
                        subprocess.check_output,
                        [
                            "docker",
                            "exec",
                            "azari-load-db",
                            "psql",
                            "-U",
                            "loadtest",
                            "-d",
                            "azari_load_test",
                            "-Atc",
                            sql,
                        ],
                    )
                    sample["pg"] = pg.decode()
                    samples.append(sample)
                except (httpx.HTTPError, ValueError):
                    samples.append({"probe": "unavailable"})
                await asyncio.sleep(2)
            result = await task
            result["diagnostics"] = samples
            data["stages"].append(result)
            output.write_text(json.dumps(data, indent=2), encoding="utf-8")
            print(
                json.dumps(
                    {
                        k: v
                        for k, v in result.items()
                        if k not in {"resources", "per_path", "diagnostics"}
                    }
                ),
                flush=True,
            )
            if (
                result["error_percent"] > 1
                or (result["p95_seconds"] or 0) > 2
                or result["readiness_after"] != 200
            ):
                break


if __name__ == "__main__":
    asyncio.run(main())
