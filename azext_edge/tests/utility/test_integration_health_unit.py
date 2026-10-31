# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest
import yaml

from . import test_ado_integration_unit as ado_tests

pipeline_environment = ado_tests.pipeline_environment
make_state = ado_tests.make_state

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
try:
    health = importlib.import_module("integration_health")
    pipeline = importlib.import_module("ado_integration")
    cluster = importlib.import_module("ado_cluster")
finally:
    sys.path.pop(0)


@pytest.fixture
def setup_health(monkeypatch, tmp_path):
    monkeypatch.setenv("BUILD_SOURCEBRANCH", "refs/heads/dev")
    monkeypatch.setenv("OPS_HEALTH_HISTORY", str(tmp_path / "history"))
    profile = {
        "clusterRegion": "westus2", "resourceRegion": "westus2", "namespaceRegion": "australiaeast",
        "pythonVersions": ["3.13"], "scenarios": ["runtime-channel"], "runtimeChannels": ["stable"],
        "scenarioTimeoutMinutes": 90, "upgradeBaselines": {},
    }
    config = {"schema": 1, "branches": {"refs/heads/dev": {"sat": profile}}}
    build = {"id": 123, "definition": {"id": 164}, "sourceVersion": "a" * 40,
             "sourceBranch": "refs/heads/dev", "queueTime": "2026-10-18T01:30:00+02:00"}
    monkeypatch.setenv("VALIDATION_PROFILES", json.dumps(config))
    monkeypatch.setattr(health, "build_metadata", Mock(return_value=build))
    return config, build


def test_ops_health_plan_uses_runtime_profile_and_records_regions(setup_health, tmp_path):
    pipeline.plan(tmp_path)
    plan = pipeline.read(tmp_path / "plan.json")
    assert plan["health"]["day"] == "sat"
    assert plan["scenarioTimeoutMinutes"] == 90
    assert plan["rows"][0]["key"] == "runtime_channel_stable_py313"
    assert plan["locations"] == {
        "clusterRegion": "westus2", "resourceRegion": "westus2", "namespaceRegion": "australiaeast",
    }


@pytest.mark.parametrize("field,value", [
    ("clusterRegion", "australiaeast"), ("namespaceRegion", "eastus;echo x"),
    ("pythonVersions", "3.13"), ("scenarios", []), ("scenarios", ["edge", "edge"]),
    ("scenarioTimeoutMinutes", True), ("scenarioTimeoutMinutes", 10), ("upgradeBaselines", []),
    ("command", "anything"),
])
def test_invalid_ops_profile_fails(setup_health, field, value):
    config, _ = setup_health
    profile = deepcopy(config["branches"]["refs/heads/dev"]["sat"])
    profile[field] = value
    with pytest.raises(ValueError):
        health.validate(profile)


@pytest.mark.parametrize("field,value", [
    ("sourceVersion", "b" * 40), ("sourceBranch", "refs/heads/preview"),
    ("queueTime", "2026-10-17T20:00:00"), ("id", 124), ("definition", {"id": 999}),
])
def test_wrong_run_identity_fails(setup_health, field, value):
    config, build = setup_health
    build[field] = value
    with pytest.raises(ValueError):
        health.choose(config, build)


def test_missing_profile_fails_instead_of_defaulting(setup_health):
    config, build = setup_health
    config["branches"]["refs/heads/dev"] = {"mon": {}}
    with pytest.raises(ValueError, match="No valid profile"):
        health.choose(config, build)


def test_ops_rerun_pins_original_library_configuration(setup_health, tmp_path, monkeypatch):
    directory = tmp_path / "history/ops-plan-1"
    pipeline.plan(directory)
    original = pipeline.read(directory / "plan.json")
    monkeypatch.setenv("VALIDATION_PROFILES", "bad replacement")
    lookup = Mock(side_effect=AssertionError("A retry must not resolve another profile."))
    monkeypatch.setattr(health, "build_metadata", lookup)
    pipeline.plan(tmp_path / "second")
    assert pipeline.read(tmp_path / "second/plan.json") == original
    assert pipeline.run_title(original, "Integration tests") == (
        "ops-health-123 (cluster westus2) (runtime-channel) (stable)"
    )
    lookup.assert_not_called()


def test_resource_creation_uses_distinct_explicit_locations(setup_health):
    state = make_state()
    config, build = setup_health
    state["health"] = health.choose(config, build)
    state["locations"] = {key: state["health"]["profile"][key] for key in
                          ("clusterRegion", "resourceRegion", "namespaceRegion")}
    commands = Mock()
    cluster.create_resources(commands, state)
    calls = [call.args[0] for call in commands.run.call_args_list]
    assert [args[args.index("--location") + 1] for args in calls] == ["westus2", "westus2", "australiaeast"]
    state["locations"]["namespaceRegion"] = "eastus"
    with pytest.raises(ValueError, match="locations"):
        cluster.validate_state(state)


def test_health_execution_budget_prevents_starting_another_command(monkeypatch):
    commands = cluster.Commands(budget=0)
    start = Mock()
    monkeypatch.setattr(cluster.subprocess, "Popen", start)
    with pytest.raises(TimeoutError, match="budget"):
        commands.run(["az", "version"])
    start.assert_not_called()


def test_health_has_no_dry_run_or_repository_cron():
    entry = yaml.safe_load((ROOT / ".azure-devops/integration-health.yml").read_text())
    assert entry["trigger"] == entry["pr"] == "none" and "schedules" not in entry
    assert entry["extends"]["parameters"] == {"health": True, "mode": "Integration tests"}
    assert entry["appendCommitMessageToRunName"] is False
