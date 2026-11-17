# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.

"""Freeze separate host, candidate, baseline and Arc tool environments before Azure work."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import dependency_lock as lock


ROOT = Path(__file__).resolve().parents[1]


def files(directory):
    result = {}
    for path in sorted(directory.rglob("*")):
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise ValueError("Frozen tool extensions cannot contain symlinks.")
        if path.is_file():
            result[path.relative_to(directory).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not result:
        raise ValueError("Frozen tool extension is empty.")
    return result


def verify_target(name, target, wheel):
    directory = Path(os.environ["OPS_DEPENDENCY_LOCK"])
    snapshot = lock.read(directory / "lock.json")
    lock.validate(snapshot, lock.identity(os.environ["OPS_ROW"], wheel), snapshot["environments"])
    if lock.package_inventory(target) != snapshot["environments"][name]:
        raise ValueError(f"Restored {name} dependencies differ from the original snapshot.")


def verify_connected():
    directory = Path(os.environ["OPS_DEPENDENCY_LOCK"])
    target = Path(os.environ["AZURE_EXTENSION_DIR"]) / "connectedk8s"
    if files(target) != lock.read(directory / "connected.json"):
        raise ValueError("Arc tool extension differs from the original snapshot.")


def prepare():
    output = Path(os.environ["OPS_DEPENDENCY_LOCK"]).resolve()
    candidate = Path(os.environ["OPS_CANDIDATE"])
    wheel, = candidate.glob("*.whl")
    key = os.environ["OPS_ROW"]
    plan = lock.read(os.environ["OPS_PLAN"])
    row, = [item for item in plan["rows"] if item["key"] == key]
    environments = ["main", "extension"] + (["baseline"] if row["scenario"]["baseline"] else [])
    history = Path(os.environ["OPS_DEPENDENCY_HISTORY"])
    attempt = max(int(os.environ["SYSTEM_JOBATTEMPT"]), int(os.environ.get("SYSTEM_STAGEATTEMPT", "1")))
    lock.restore(history, output, key, wheel, environments, attempt)
    subprocess.run([
        sys.executable, "-m", "pip", "install", "-r", str(output / "main.txt"),
        "-r", str(ROOT / "dev_requirements.txt"), "azure-cli", "azure-cli-testsdk", "pytest-randomly", "PyYAML",
    ], check=True, env={**os.environ, "PIP_CONSTRAINT": str(output / "main.txt")})
    subprocess.run(
        [sys.executable, os.environ["PREPARE_SCRIPT"], "prepare", "--output", "attempt"],
        check=True, env={**os.environ, "PIP_CONSTRAINT": str(output / "extension.txt")},
    )
    targets = {"extension": str(Path(os.environ["AZURE_EXTENSION_DIR"]) / "azure-iot-ops")}
    if "baseline" in environments:
        subprocess.run([
            sys.executable, "-c",
            "import json, os; from pathlib import Path; from integration_runner import prepare_baseline; "
            "prepare_baseline(json.loads(os.environ['OPS_BASELINE']), os.environ['OPS_CHANNEL'], Path.cwd())",
        ], cwd=ROOT / "attempt", check=True, env={
            **os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT / "tools"), targets["extension"]]),
            "OPS_BASELINE": json.dumps(row["scenario"]["baseline"]), "OPS_CHANNEL": row["scenario"]["channel"],
            "azext_edge_cloud": plan["cloud"], "PIP_CONSTRAINT": str(output / "baseline.txt"),
        })
        targets["baseline"] = str(ROOT / "attempt/baseline-extensions/azure-iot-ops")
    connected = Path(os.environ["AZURE_EXTENSION_DIR"]) / "connectedk8s"
    previous = sorted(history.glob(f"dependencies-{key}-*/connected.json"))
    if (output / "lock.json").exists():
        if not previous:
            raise ValueError("Retry is missing the original Arc tool extension snapshot.")
        inventories = [lock.read(path) for path in previous]
        if any(value != inventories[0] for value in inventories):
            raise ValueError("Arc tool identity changed between attempts.")
        retained = previous[0].parent / "connectedk8s"
        if files(retained) != inventories[0]:
            raise ValueError("Frozen Arc tool artifact has changed.")
        if connected.exists():
            shutil.rmtree(connected)
        shutil.copytree(retained, connected)
    else:
        subprocess.run(["az", "extension", "add", "--name", "connectedk8s", "--yes"], check=True)
    shutil.copytree(connected, output / "connectedk8s", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    lock.write(output / "connected.json", files(connected))
    # Capture only after every resolver has finished; retries compare before overwriting.
    lock.capture(output, key, wheel, {"main": sys.executable}, targets)
    print(f"##vso[task.setvariable variable=OPS_DEPENDENCY_LOCK]{output}")
    if "baseline" in targets:
        print(f"##vso[task.setvariable variable=OPS_BASELINE_EXTENSION]{targets['baseline']}")


if __name__ == "__main__":
    prepare()
