# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from ....helpers import run


@pytest.fixture()
def require_init(init_setup):
    # get the custom location used for tests.
    if not all([init_setup.get("clusterName"), init_setup.get("resourceGroup")]):
        pytest.skip("Cannot run this test without knowing the cluster information.")

    cluster_result = run(
        f"az resource show -n {init_setup['clusterName']} -g {init_setup['resourceGroup']} "
        "--resource-type Microsoft.Kubernetes/connectedClusters"
    )
    cluster_id = cluster_result["id"]
    custom_location_result = run(
        "az graph query -q \"where type =~ 'Microsoft.ExtendedLocation/customLocations' | "
        f"where properties.hostResourceId =~ '{cluster_id}' | project name\""
    )["data"]
    init_setup["customLocation"] = custom_location_result[0]["name"]
    yield init_setup
