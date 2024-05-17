# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import pytest
from ....helpers import run


@pytest.fixture()
def require_init(init_setup, tracked_files):
    # get the custom location used for tests.
    if not all([init_setup.get("clusterName"), init_setup.get("resourceGroup")]):
        pytest.skip("Cannot run this test without knowing the cluster information.")

    cluster_result = run(
        f"az resource show -n {init_setup['clusterName']} -g {init_setup['resourceGroup']} "
        "--resource-type Microsoft.Kubernetes/connectedClusters"
    )
    cluster_id = cluster_result["id"]

    # create a file to avoid shell parsing issues with dictionaries.
    file_name = "cluster_query.json"
    with open(file_name, "w", encoding="utf-8") as f:
        body = {
            "query": "where type =~ 'Microsoft.ExtendedLocation/customLocations' | where properties.hostResourceId "
            f"=~ '{cluster_id}' | project name, resourceGroup"
        }
        json.dump(body, f)
    tracked_files.append(file_name)

    custom_location_result = run(
        "az rest --method POST --url https://management.azure.com/providers/Microsoft.ResourceGraph"
        f"/resources?api-version=2022-10-01 --body @{file_name}"
    )["data"]
    init_setup["customLocation"] = custom_location_result[0]["name"]
    init_setup["customLocationResourceGroup"] = custom_location_result[0]["resourceGroup"]
    yield init_setup
