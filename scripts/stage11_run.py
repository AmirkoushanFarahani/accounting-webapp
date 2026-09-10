"""Host launcher; secrets remain in memory and diagnostics target isolated containers."""

import json
import subprocess
import sys
from pathlib import Path


def main():
    users, seconds, tokens, admission, mode, label = sys.argv[1:]
    assert label.replace("_", "").isalnum()
    info = json.loads(subprocess.check_output(["docker", "inspect", "azari-stage11-backend"]))[0]
    env = dict(item.split("=", 1) for item in info["Config"]["Env"])
    assert env["DATABASE_URL"].endswith("/azari_load_test")
    name = "azari-stage11-gen-" + label
    output = "STAGE11_" + label + ".json"
    subprocess.run([
        "docker", "run", "--name", name, "--network", "azari-stage11",
        "--cpus", "2", "--cpuset-cpus", "4,5", "--memory", "1g",
        "-v", str(Path("scripts").resolve()) + ":/load:ro",
        "-e", "LOAD_JWT_SECRET=" + env["JWT_SECRET"], "azari-stage11-generator",
        users, seconds, tokens, admission, mode, "/tmp/result.json",
    ], check=True)
    subprocess.run(["docker", "cp", name + ":/tmp/result.json", output], check=True)


if __name__ == "__main__":
    main()
