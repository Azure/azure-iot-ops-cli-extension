# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from ...helpers import run
from ...generators import generate_names


@pytest.fixture()
def cluster_setup(settings):
    cluster_name = f"cli-init-{generate_names(max_length=5)}"
    yield cluster_name
    run(f"az iot ops delete --cluster {cluster_name} -g {settings.env.azext_edge_rg} -y --no-progress --force")


@pytest.mark.parametrize("scenario", [
    pytest.param({"simulate_plc": True}, id="simualte plc"),
    pytest.param({"include_dp": True, "dp_instance": f"processor-{generate_names(max_length=5)}"}, id="data processor")
])
def test_init_scenarios_test(
    settings, scenario, cluster_setup, tracked_files
):
    command = f"az iot ops init -g {settings.env.azext_edge_rg} --cluster {cluster_setup} "\
        f"--kv-id {settings.env.azext_edge_kv} --no-progress "

    for param, value in scenario.items():
        command += f"--{param.replace('_', '-')} {value} "

    result = run(command)
    assert result
    assert result["clusterName"] == cluster_setup
    assert result["clusterNamespace"] == scenario.get("cluster_namespace", "azure-iot-operations")
    assert result["deploymentLink"]
    assert result["deploymentName"]

    dstate = result["deploymentState"]
    assert dstate["correlationId"]
    assert dstate["opsVersion"]
