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
    return build_matrix["process_scenarios"], scenarios


def test_default_scenarios_exclude_manual_regression(scenario_matrix):
    process_scenarios, scenarios = scenario_matrix
    result = process_scenarios(scenarios, "")

    assert [scenario["name"] for scenario in result] == [
        scenario["name"] for scenario in scenarios if not scenario.get("manual_only", False)
    ]
    assert "edge" in {scenario["name"] for scenario in result}
    assert "broker-diagnostics-removal" not in {scenario["name"] for scenario in result}


@pytest.mark.parametrize("selection", ["broker-diagnostics-removal", "edge, broker-diagnostics-removal"])
def test_explicit_removal_scenario_enables_live_regression(scenario_matrix, selection):
    process_scenarios, scenarios = scenario_matrix
    result = process_scenarios(scenarios, selection)
    assert {scenario["name"] for scenario in result} == {name.strip() for name in selection.split(",")}
    removal = next(scenario for scenario in result if scenario["name"] == "broker-diagnostics-removal")

    assert removal["tox_env"] == "python-edge-int"
    assert removal["parallel"] is False
    assert {"name": "azext_edge_broker_diagnostics_removal", "value": "true"} in removal["env"]


def test_explicit_edge_selection_is_unchanged(scenario_matrix):
    process_scenarios, scenarios = scenario_matrix
    result = process_scenarios(scenarios, "edge")
    assert [scenario["name"] for scenario in result] == ["edge"]
    assert not result[0]["env"]
