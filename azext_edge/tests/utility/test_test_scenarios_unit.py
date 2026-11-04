# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from pathlib import Path
from runpy import run_path

import pytest
from yaml import safe_load


@pytest.fixture
def scenario_matrix():
    root = Path(__file__).resolve().parents[3]
    build_matrix = run_path(str(root / ".github/actions/build-int-test-matrix/build_matrix.py"))
    with (root / ".github/test-scenarios.yml").open(encoding="utf-8") as config_file:
        scenarios = safe_load(config_file)["scenarios"]
    return build_matrix, scenarios


def test_default_scenarios_exclude_manual_regression(scenario_matrix):
    build_matrix, scenarios = scenario_matrix
    result = build_matrix["process_scenarios"](scenarios, "")

    assert [scenario["name"] for scenario in result] == [
        scenario["name"] for scenario in scenarios
        if not scenario.get("manual_only", False) and not scenario.get("requires_baseline", False)
    ]
    assert "edge" in {scenario["name"] for scenario in result}
    assert "broker-diagnostics-removal" not in {scenario["name"] for scenario in result}
    assert "upgrade-path" not in {scenario["name"] for scenario in result}


@pytest.mark.parametrize("selection", ["broker-diagnostics-removal", "edge, broker-diagnostics-removal"])
def test_explicit_removal_scenario_enables_live_regression(scenario_matrix, selection, capsys):
    build_matrix, scenarios = scenario_matrix
    result = build_matrix["process_scenarios"](scenarios, selection)
    assert capsys.readouterr().out == ""
    assert {scenario["name"] for scenario in result} == {name.strip() for name in selection.split(",")}
    removal = next(scenario for scenario in result if scenario["name"] == "broker-diagnostics-removal")

    assert removal["tox_env"] == "python-edge-int"
    assert removal["parallel"] is False
    assert removal["create_args"] == ""
    assert removal["init_args"] == ""
    assert {"name": "azext_edge_broker_diagnostics_removal", "value": "true"} in removal["env"]


@pytest.mark.parametrize("channels", ["stable", "preview", "stable,preview"])
def test_removal_scenario_uses_channel_profiles(scenario_matrix, channels):
    build_matrix, scenarios = scenario_matrix
    selected = build_matrix["process_scenarios"](scenarios, "broker-diagnostics-removal")
    rows = build_matrix["expand_channels"](selected, channels)

    assert [row["name"] for row in rows] == [
        f"broker-diagnostics-removal-{channel}" for channel in channels.split(",")
    ]
    for row, channel in zip(rows, channels.split(",")):
        assert row["channel"] == channel
        assert row["init_args"] == ""
        assert row["create_args"] == ("--use-preview" if channel == "preview" else "")
        assert row["tox_env"] == "python-edge-int"
        assert row["parallel"] is False
        assert row["baseline"] is None
        assert row["requires_baseline"] is False
        assert {"name": "azext_edge_broker_diagnostics_removal", "value": "true"} in row["env"]


def test_explicit_edge_selection_is_unchanged(scenario_matrix):
    build_matrix, scenarios = scenario_matrix
    result = build_matrix["process_scenarios"](scenarios, "edge")
    assert [scenario["name"] for scenario in result] == ["edge"]
    assert not result[0]["env"]
    assert result[0]["create_args"] == ""


@pytest.mark.parametrize("version", ["1.4.112", "1.3.14"])
def test_older_management_scenario_uses_explicit_baseline(scenario_matrix, version):
    build_matrix, scenarios = scenario_matrix
    selected = build_matrix["process_scenarios"](scenarios, "mgmtactions")
    baseline = {
        "wheel_url": "https://example.invalid/azure_iot_ops-2.10.0-py3-none-any.whl",
        "sha256": "a" * 64, "version": version, "train": "stable",
        "create_args": f"--ops-version {version} --ops-train stable",
    }
    rows = build_matrix["expand_channels"](selected, "stable", previous_targets={"n-1": baseline})
    assert len(rows) == 2
    assert rows[0]["name"] == "mgmtactions-stable"
    assert rows[0]["baseline"] is None
    assert not rows[0]["env"]
    row = rows[1]
    assert row["name"] == "mgmtactions-stable-n-1"
    assert row["tox_env"] == "python-mgmtactions-int"
    assert row["parallel"] is False
    assert row["baseline"] == baseline
    assert {"name": "azext_edge_preserve_runtime", "value": "true"} in row["env"]
    assert row["test_redeploy"] is False


def test_current_management_runs_do_not_require_baseline(scenario_matrix):
    build_matrix, scenarios = scenario_matrix
    selected = build_matrix["process_scenarios"](scenarios, "mgmtactions")
    rows = build_matrix["expand_channels"](selected, "stable")
    assert len(rows) == 1
    assert rows[0]["baseline"] is None
    default = build_matrix["process_scenarios"](scenarios, "")
    assert "mgmtactions" in {row["name"] for row in default}


@pytest.mark.parametrize("include_current", [False, True])
def test_runtime_targets_expand_all_selected_scenarios(scenario_matrix, include_current):
    build_matrix, scenarios = scenario_matrix
    selected = build_matrix["process_scenarios"](scenarios, "edge,mgmtactions,upgrade,redeploy,runtime-channel")
    first = {
        "wheel_url": "https://example.invalid/azure_iot_ops-2.10.0-py3-none-any.whl",
        "sha256": "a" * 64, "version": "1.4.112", "train": "stable", "create_args": "",
    }
    second = {**first, "version": "1.3.14", "create_args": "--ops-version 1.3.14 --ops-train stable"}
    rows = build_matrix["expand_channels"](
        selected, "stable,preview", include_current=include_current,
        previous_targets={"n-1": first, "n-2": second},
    )
    assert len(rows) == len(selected) * (4 if include_current else 2)
    assert len({row["name"] for row in rows}) == len(rows)
    for row in rows:
        if not row["baseline"]:
            assert row["channel"] in ("stable", "preview")
            continue
        assert row["channel"] == "stable"
        assert row["baseline"] in (first, second)
        if row["tox_env"] == "python-upgrade-int":
            assert row["description"].endswith("-> current")
            assert not any(item["name"] == "azext_edge_preserve_runtime" for item in row["env"])
        else:
            assert {"name": "azext_edge_preserve_runtime", "value": "true"} in row["env"]


def test_empty_runtime_selection_fails(scenario_matrix):
    build_matrix, scenarios = scenario_matrix
    selected = build_matrix["process_scenarios"](scenarios, "edge")
    with pytest.raises(ValueError, match="Select at least one"):
        build_matrix["expand_channels"](selected, include_current=False)


@pytest.mark.parametrize("selection", ["", "essentials-sku,mgmtactions"])
def test_older_targets_exclude_only_ineligible_scenarios(scenario_matrix, capsys, selection):
    build_matrix, scenarios = scenario_matrix
    selected = build_matrix["process_scenarios"](scenarios, selection)
    baseline = {
        "wheel_url": "https://example.invalid/cli.whl", "sha256": "a" * 64,
        "version": "1.4.112", "train": "stable", "create_args": "",
    }
    rows = build_matrix["expand_channels"](
        selected, previous_targets={"n-1": baseline, "n-2": {**baseline, "version": "1.3.137"}},
    )
    expected_names = {
        f"{scenario['name']}-{channel}" for scenario in selected for channel in ("stable", "preview")
    } | {
        f"{scenario['name']}-stable-{generation}"
        for scenario in selected if scenario["name"] != "essentials-sku"
        for generation in ("n-1", "n-2")
    }
    assert {row["name"] for row in rows} == expected_names
    assert len(rows) == len(expected_names)
    for row in rows:
        if row["name"].startswith("essentials-sku-"):
            assert row["create_args"].startswith("--sku Essentials --feature opcua.mode=Stable")
    warnings = capsys.readouterr().out.splitlines()
    assert warnings == [
        "::warning file=.github/test-scenarios.yml::"
        f"Skipping scenario 'essentials-sku' on {generation} AIO {version}: requires AIO 1.5.0 or later."
        for generation, version in (("N-1", "1.4.112"), ("N-2", "1.3.137"))
    ]


@pytest.mark.parametrize("version,eligible", [
    ("1.4.999", False), ("1.5.0", True), ("1.5.41", True), ("1.10.0", True), ("2.0.0", True),
])
def test_essentials_eligibility_follows_runtime_not_generation(scenario_matrix, capsys, version, eligible):
    build_matrix, scenarios = scenario_matrix
    selected = build_matrix["process_scenarios"](scenarios, "essentials-sku")
    baseline = {
        "wheel_url": "https://example.invalid/cli.whl", "sha256": "a" * 64,
        "version": version, "train": "stable", "create_args": "",
    }
    rows = build_matrix["expand_channels"](
        selected, include_current=False, previous_targets={"n-2": baseline},
    )
    assert len(rows) == int(eligible)
    if eligible:
        assert rows[0]["name"] == "essentials-sku-stable-n-2"
        assert rows[0]["baseline"] == baseline
        assert rows[0]["create_args"] == "--sku Essentials --feature opcua.mode=Stable"
        assert capsys.readouterr().out == ""
    else:
        assert "requires AIO 1.5.0 or later" in capsys.readouterr().out


@pytest.mark.parametrize("minimum", ["", "1.5", "1.5.0-preview.1", "bad", 1.5, True, []])
def test_invalid_scenario_minimum_fails(scenario_matrix, minimum):
    build_matrix, _ = scenario_matrix
    with pytest.raises(ValueError, match="min_runtime_version must be a stable semantic version"):
        build_matrix["process_scenarios"]([{"name": "example", "min_runtime_version": minimum}], "")


def test_no_eligible_jobs_fails_before_emitting_matrix(scenario_matrix, monkeypatch, tmp_path, capsys):
    build_matrix, _ = scenario_matrix
    root = Path(__file__).resolve().parents[3]
    output = tmp_path / "matrix"
    baseline = {
        "wheel_url": "https://example.invalid/cli.whl", "sha256": "a" * 64,
        "version": "1.4.112", "train": "stable", "create_args": "",
    }
    monkeypatch.setattr("runpy.run_path", lambda _: {"discover_previous": lambda _: {"n-1": baseline}})
    for key, value in {
        "TEST_SCENARIO_FILE": str(root / ".github/test-scenarios.yml"), "GITHUB_OUTPUT": str(output),
        "TEST_SCENARIOS": "essentials-sku", "TEST_CURRENT": "false", "TEST_N_1": "true", "TEST_N_2": "false",
        "RUNTIME_CHANNELS": "stable,preview", "UPGRADE_BASELINES": "{}",
        "RUNTIME_INIT_ARGS": "", "RUNTIME_CREATE_ARGS": "",
    }.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(SystemExit) as exc:
        build_matrix["main"]()
    assert exc.value.code == 1
    assert not output.exists()
    messages = capsys.readouterr().out
    assert "Skipping scenario 'essentials-sku' on N-1 AIO 1.4.112" in messages
    assert "::error::No valid scenarios to run." in messages
