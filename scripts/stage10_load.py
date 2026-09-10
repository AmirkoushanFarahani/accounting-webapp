"""Progressive local load with per-request profiling and safe escalation gates."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import run_load_test


async def main():
    port, container, output = int(sys.argv[1]), sys.argv[2], sys.argv[3]
    assert port in {18102, 18103} and container.startswith("azari-stage10-")
    info = json.loads(
        await asyncio.to_thread(
            subprocess.check_output, ["docker", "inspect", container]
        )
    )[0]
    env = dict(item.split("=", 1) for item in info["Config"]["Env"])
    assert env["DATABASE_URL"].endswith("/azari_load_test")
    os.environ["LOAD_JWT_SECRET"] = env["JWT_SECRET"]
    run_load_test.BASE = f"http://127.0.0.1:{port}/api/v1"
    result = {"stages": [], "container": container}
    async with httpx.AsyncClient(timeout=3) as client:
        assert (await client.get(run_load_test.BASE + "/ready")).status_code == 200
        for users in [100, 250, 500, 750, 1000]:
            offset = len((await client.get(f"http://127.0.0.1:{port}/__stage10")).json())
            samples = []
            task = asyncio.create_task(run_load_test.phase(users))
            while not task.done():
                sample = (await client.get(f"http://127.0.0.1:{port}/__probe")).json()
                sample["resources"] = json.loads(
                    await asyncio.to_thread(
                        subprocess.check_output,
                        [
                            "docker",
                            "stats",
                            "--no-stream",
                            "--format",
                            "{{json .}}",
                            container,
                        ],
                    )
                )
                sample["postgres"] = json.loads(
                    await asyncio.to_thread(
                        subprocess.check_output,
                        [
                            "docker",
                            "stats",
                            "--no-stream",
                            "--format",
                            "{{json .}}",
                            "azari-load-db",
                        ],
                    )
                )
                samples.append(sample)
                await asyncio.sleep(1)
            stage = await task
            stage.pop("resources", None)  # Legacy harness samples a different backend.
            stage["samples"] = samples
            result["stages"].append(stage)
            print(
                json.dumps(
                    {k: v for k, v in stage.items() if k not in {"samples", "per_path"}}
                ),
                flush=True,
            )
            result["server"] = (
                await client.get(f"http://127.0.0.1:{port}/__stage10")
            ).json()
            stage["server"] = result["server"][offset:]
            Path(output).write_text(json.dumps(result, indent=2))
            if (
                stage["error_percent"] > 1
                or stage["p95_seconds"] > 2
                or stage["readiness_after"] != 200
            ):
                break


if __name__ == "__main__":
    asyncio.run(main())
