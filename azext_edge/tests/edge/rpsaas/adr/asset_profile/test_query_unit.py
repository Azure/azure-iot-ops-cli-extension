# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import pytest

from azext_edge.edge.common import ResourceTypeMapping
from azext_edge.edge.commands_asset_endpoint_profiles import query_asset_endpoint_profiles

from .conftest import FULL_AEP, MINIMUM_AEP
from .....generators import generate_random_string


@pytest.mark.parametrize(
    "mocked_resource_graph", [[FULL_AEP, MINIMUM_AEP]], ids=["resource_graph"], indirect=True
)
@pytest.mark.parametrize("req", [
    {},
    {
        "custom_location_name": generate_random_string(),
        "target_address": generate_random_string(),
        "additional_configuration": generate_random_string(),
        "auth_mode": generate_random_string(),
        "location": generate_random_string(),
        "resource_group_name": generate_random_string(),
    },
    {
        "additional_configuration": generate_random_string(),
        "auth_mode": generate_random_string(),
        "resource_query": f"|{generate_random_string()}"
    },
    {
        "additional_configuration": generate_random_string(),
        "auth_mode": generate_random_string(),
        "resource_group_name": generate_random_string(),
        "resource_query": generate_random_string()
    },
])
def test_query_asset_endpoint_profiles(mocked_cmd, mocked_resource_graph, req):
    result = query_asset_endpoint_profiles(
        cmd=mocked_cmd,
        **req
    )
    assert result == mocked_resource_graph.return_value.json.return_value["data"]
    query_args = json.loads(mocked_resource_graph.call_args.kwargs["body"])["query"]

    expected_query = f"Resources | where type =~ \"{ResourceTypeMapping.asset_endpoint_profile.full_resource_path}\" "
    if req.get("resource_query"):
        if not req["resource_query"].startswith("|"):
            expected_query += "|"
        expected_query += req["resource_query"]
    else:
        if req.get("resource_group_name"):
            expected_query += f"| where resourceGroup =~ \"{req['resource_group_name']}\" "
        if req.get("location"):
            expected_query += f"| where location =~ \"{req['location']}\" "
        if req.get("additional_configuration"):
            expected_query += f"| where properties.additionalConfiguration =~ \"{req['additional_configuration']}\""
        if req.get("auth_mode"):
            expected_query += f"| where properties.userAuthentication.mode =~ \"{req['auth_mode']}\""
        if req.get("custom_location_name"):  # ##
            expected_query += f"| where extendedLocation.name contains \"{req['custom_location_name']}\""
        if req.get("target_address"):
            expected_query += f"| where properties.targetAddress =~ \"{req['target_address']}\""
        expected_query += "| project id, location, name, resourceGroup, properties, tags, type, subscriptionId, extendedLocation"
    assert query_args == expected_query
