# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import importlib
from pathlib import Path
import runpy

import pytest


@pytest.fixture
def lock(monkeypatch, tmp_path):
    module = runpy.run_path(str(Path(__file__).resolve().parents[3] / "tools/dependency_lock.py"))
    for name, value in {
        "BUILD_BUILDID": "12", "SYSTEM_DEFINITIONID": "164", "BUILD_SOURCEVERSION": "a" * 40,
    }.items():
        monkeypatch.setenv(name, value)
    wheel = tmp_path / "candidate.whl"
    wheel.write_bytes(b"immutable candidate")
    return module, wheel


def snapshot(module, wheel, version="12.28.0b1"):
    return {
        "schema": 1, "identity": module["identity"]("edge_stable_py313", wheel),
        "environments": {
            "main": {"azure-storage-blob": {"version": version, "metadata": "b" * 64}},
            "extension": {
                "azure-iot-ops": {"version": "2.11.0", "metadata": "c" * 64},
                "azure-storage-blob": {"version": "12.29.0", "metadata": "d" * 64},
            },
        },
    }


def test_retry_restores_separate_constraints_without_resolving_candidate_from_index(lock, tmp_path):
    module, wheel = lock
    saved = tmp_path / "history/dependencies-edge_stable_py313-1-1"
    saved.mkdir(parents=True)
    module["write"](saved / "lock.json", snapshot(module, wheel))
    output = tmp_path / "restored"
    module["restore"](saved.parent, output, "edge_stable_py313", wheel, ["main", "extension"], 2)
    assert (output / "main.txt").read_text() == "azure-storage-blob==12.28.0b1\n"
    assert (output / "extension.txt").read_text() == "azure-storage-blob==12.29.0\n"


@pytest.mark.parametrize("failure", ["missing", "wheel", "identity", "conflict"])
def test_retry_rejects_missing_or_changed_snapshot(lock, tmp_path, failure):
    module, wheel = lock
    history = tmp_path / "history"
    history.mkdir()
    value = snapshot(module, wheel)
    if failure != "missing":
        saved = history / "dependencies-edge_stable_py313-1-1"
        saved.mkdir()
        if failure == "identity":
            value["identity"]["BUILD_BUILDID"] = "13"
        module["write"](saved / "lock.json", value)
    if failure == "wheel":
        wheel.write_bytes(b"different candidate")
    if failure == "conflict":
        second = history / "dependencies-edge_stable_py313-2-1"
        second.mkdir()
        module["write"](second / "lock.json", snapshot(module, wheel, "12.30.0"))
    with pytest.raises(ValueError):
        module["restore"](history, tmp_path / "restored", "edge_stable_py313", wheel, ["main", "extension"], 2)


def test_capture_rejects_drift_without_overwriting_original(lock, tmp_path, monkeypatch):
    module, wheel = lock
    output = tmp_path / "snapshot"
    output.mkdir()
    original = snapshot(module, wheel)
    module["write"](output / "lock.json", original)
    extension = tmp_path / "extension"
    extension.mkdir()
    calls = iter([
        json.dumps({"azure-storage-blob": {"version": "12.30.0", "metadata": "b" * 64}}),
        json.dumps(original["environments"]["extension"]),
    ])
    monkeypatch.setattr(module["subprocess"], "check_output", lambda *args, **kwargs: next(calls))
    with pytest.raises(ValueError, match="Restored dependencies differ"):
        module["capture"](output, "edge_stable_py313", wheel, {"main": "python"}, {"extension": str(extension)})
    assert module["read"](output / "lock.json") == original


def test_capture_keeps_virtual_environment_interpreter_path(lock, tmp_path, monkeypatch):
    module, wheel = lock
    output = tmp_path / "snapshot"
    output.mkdir()
    interpreter = tmp_path / "venv/bin/python"
    interpreter.parent.mkdir(parents=True)
    interpreter.symlink_to(module["sys"].executable)
    calls = []

    def inventory(arguments, **_):
        calls.append(arguments)
        return json.dumps(snapshot(module, wheel)["environments"]["main"])

    monkeypatch.setattr(module["subprocess"], "check_output", inventory)
    module["capture"](output, "edge_stable_py313", wheel, {"main": str(interpreter)}, {})
    assert calls[0][0] == str(interpreter)


def test_locked_target_rejects_inventory_drift_before_tests(lock, tmp_path, monkeypatch):
    module, wheel = lock
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "tools"))
    dependencies = importlib.import_module("integration_dependencies")
    output = tmp_path / "lock"
    output.mkdir()
    value = snapshot(module, wheel)
    module["write"](output / "lock.json", value)
    monkeypatch.setenv("OPS_DEPENDENCY_LOCK", str(output))
    monkeypatch.setenv("OPS_ROW", "edge_stable_py313")
    monkeypatch.setattr(dependencies.lock, "package_inventory", lambda _: value["environments"]["extension"])
    dependencies.verify_target("extension", tmp_path / "installed", wheel)
    value["environments"]["extension"]["azure-storage-blob"]["version"] = "12.30.0"
    with pytest.raises(ValueError, match="original snapshot"):
        dependencies.verify_target("extension", tmp_path / "installed", wheel)


def test_connected_tool_is_frozen_by_bytes_not_rediscovered(lock, tmp_path, monkeypatch):
    module, _ = lock
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "tools"))
    dependencies = importlib.import_module("integration_dependencies")
    output = tmp_path / "lock"
    output.mkdir()
    target = tmp_path / "extensions/connectedk8s"
    target.mkdir(parents=True)
    tool = target / "tool.py"
    tool.write_text("original")
    module["write"](output / "connected.json", dependencies.files(target))
    monkeypatch.setenv("OPS_DEPENDENCY_LOCK", str(output))
    monkeypatch.setenv("AZURE_EXTENSION_DIR", str(target.parent))
    dependencies.verify_connected()
    (target / "tool.pyc").write_bytes(b"ignorable generated cache")
    dependencies.verify_connected()
    tool.write_text("different")
    with pytest.raises(ValueError, match="original snapshot"):
        dependencies.verify_connected()
