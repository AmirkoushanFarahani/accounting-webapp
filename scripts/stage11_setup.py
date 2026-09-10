"""Create a separate test topology from the existing synthetic database only."""

import json
import subprocess
import time
from pathlib import Path


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True)


def main():
    previous = json.loads(docker("inspect", "azari-stage10-after"))[0]
    env = dict(item.split("=", 1) for item in previous["Config"]["Env"])
    assert env["DATABASE_URL"].endswith("@load-db:5432/azari_load_test")
    database = json.loads(docker("inspect", "azari-load-db"))[0]
    db_env = dict(item.split("=", 1) for item in database["Config"]["Env"])
    assert db_env["POSTGRES_DB"] == "azari_load_test"
    names = docker("ps", "-a", "--format", "{{.Names}}").splitlines()
    assert "azari-stage11-db" not in names, "Refuse to overwrite existing experiment"
    docker("network", "create", "azari-stage11")
    docker(
        "run", "-d", "--name", "azari-stage11-db", "--network", "azari-stage11",
        "--network-alias", "load-db", "--cpus", "2", "--cpuset-cpus", "2,3",
        "--memory", "1g", "-e", "POSTGRES_DB=azari_load_test",
        "-e", "POSTGRES_USER=loadtest", "-e", "POSTGRES_PASSWORD=" + db_env["POSTGRES_PASSWORD"],
        "postgres:16-alpine",
    )
    for _ in range(30):
        result = subprocess.run(
            ["docker", "exec", "azari-stage11-db", "pg_isready", "-U", "loadtest"],
            capture_output=True,
        )
        if result.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError("Test database did not become ready")
    # Binary pipe; no SQL dump or secrets are written to disk or printed.
    producer = subprocess.Popen(
        ["docker", "exec", "azari-load-db", "pg_dump", "-U", "loadtest", "azari_load_test"],
        stdout=subprocess.PIPE,
    )
    consumer = subprocess.run(
        ["docker", "exec", "-i", "azari-stage11-db", "psql", "-v", "ON_ERROR_STOP=1",
         "-U", "loadtest", "-d", "azari_load_test"],
        stdin=producer.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    producer.stdout.close()
    assert producer.wait() == 0 and consumer.returncode == 0, "Synthetic clone failed"
    args = ["run", "-d", "--name", "azari-stage11-backend", "--network", "azari-stage11",
            "--cpus", "2", "--cpuset-cpus", "0,1", "--memory", "1g",
            "-p", "127.0.0.1:18111:8000", "-v", str(Path("scripts").resolve()) + ":/load:ro",
            "-v", str(Path("ml/models").resolve()) + ":/models:ro"]
    for name in ("DATABASE_URL", "JWT_SECRET"):
        args.extend(["-e", name + "=" + env[name]])
    args.extend(["-e", "ML_MODEL_DIR=/models", "-e", "PYTHONPATH=/app:/load",
                 "azari-stage10-final:latest", "uvicorn", "stage11_probe:app",
                 "--host", "0.0.0.0", "--port", "8000", "--no-access-log"])
    docker(*args)
    print("Created isolated Stage 11 database clone and backend; no real data used")


if __name__ == "__main__":
    main()
