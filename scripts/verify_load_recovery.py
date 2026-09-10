"""Exercise outage recovery on the explicitly named synthetic load stack only."""

import json
import subprocess
import time
from pathlib import Path

import httpx


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True)


def main():
    backend = json.loads(docker("inspect", "azari-load-backend"))[0]
    database = json.loads(docker("inspect", "azari-load-db"))[0]
    env = dict(item.split("=", 1) for item in backend["Config"]["Env"])
    db_env = dict(item.split("=", 1) for item in database["Config"]["Env"])
    assert env["DATABASE_URL"].endswith("@load-db:5432/azari_load_test")
    assert db_env["POSTGRES_DB"] == "azari_load_test"
    assert "azari-load-test" in backend["NetworkSettings"]["Networks"]
    result = {}
    with httpx.Client(base_url="http://127.0.0.1:18100", timeout=10) as client:
        result["before"] = client.get("/__probe").json()
        assert result["before"]["admitted_sessions"] == 0
        # A failed pre-ping/reconnect can emit checkin(None) without checkout.
        # Pool occupancy, not raw event equality, is authoritative after an outage.
        assert result["before"]["pool"].endswith("Checked out connections: 0")
        assert result["before"]["max_hold_seconds"] == 0
        try:
            docker("stop", "azari-load-db")
            start = time.monotonic()
            health = client.get("/api/v1/health")
            ready = client.get("/api/v1/ready")
            result["outage"] = {
                "health": health.status_code,
                "ready": ready.status_code,
                "body": ready.json(),
                "seconds": round(time.monotonic() - start, 3),
            }
            assert health.status_code == 200
            assert ready.status_code == 503
            assert ready.json() == {"detail": "Database temporarily unavailable"}
        finally:
            docker("start", "azari-load-db")
        for _ in range(30):
            if client.get("/api/v1/ready").status_code == 200:
                break
            time.sleep(1)
        else:
            raise AssertionError("Readiness did not recover")
        time.sleep(1)
        result["after"] = client.get("/__probe").json()
        assert result["after"]["admitted_sessions"] == 0
        assert result["after"]["pool"].endswith("Checked out connections: 0")
        assert result["after"]["max_hold_seconds"] == 0
    result["backend_not_restarted"] = (
        json.loads(docker("inspect", "azari-load-backend"))[0]["State"]["StartedAt"]
        == backend["State"]["StartedAt"]
    )
    assert result["backend_not_restarted"]
    Path("LOAD_RECOVERY_RESULTS.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result["outage"]))
    print("PASS: connections returned, outage detected, recovered without backend restart")


if __name__ == "__main__":
    main()
