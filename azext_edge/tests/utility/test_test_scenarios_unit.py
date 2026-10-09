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
