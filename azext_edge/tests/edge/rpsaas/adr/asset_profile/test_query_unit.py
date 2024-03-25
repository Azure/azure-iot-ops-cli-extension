# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.common import ResourceTypeMapping
from azext_edge.edge.commands_asset_endpoint_profiles import query_asset_endpoint_profiles

from .conftest import AEP_PATH
from .....generators import generate_generic_id


@pytest.mark.parametrize("mocked_build_query", [{
    "path": AEP_PATH,
    "result": [{"result": generate_generic_id()}]
}], ids=["query"], indirect=True)
@pytest.mark.parametrize("req", [
    {},
    {
        "custom_location_name": generate_generic_id(),
        "target_address": generate_generic_id(),
        "additional_configuration": generate_generic_id(),
        "auth_mode": generate_generic_id(),
        "location": generate_generic_id(),
        "resource_group_name": generate_generic_id(),
    },
    {
        "additional_configuration": generate_generic_id(),
        "auth_mode": generate_generic_id(),
        "resource_group_name": generate_generic_id(),
    },
])
def test_query_asset_endpoint_profiles(mocked_cmd, mocked_get_subscription_id, mocked_build_query, req):
    result = query_asset_endpoint_profiles(
        cmd=mocked_cmd,
        **req
    )
    assert result == mocked_build_query.return_value
    query_args = mocked_build_query.call_args.kwargs
    assert query_args["subscription_id"] == mocked_get_subscription_id.return_value
    assert query_args["location"] == req.get("location")
    assert query_args["resource_group"] == req.get("resource_group_name")
    assert query_args["type"] == ResourceTypeMapping.asset_endpoint_profile.full_resource_path
    assert query_args["additional_project"] == "extendedLocation"

    expected_query = ""
    if req.get("additional_configuration"):
        expected_query += f"| where properties.additionalConfiguration =~ \"{req['additional_configuration']}\""
    if req.get("auth_mode"):
        expected_query += f"| where properties.userAuthentication.mode =~ \"{req['auth_mode']}\""
    if req.get("custom_location_name"):  # ##
        expected_query += f"| where extendedLocation.name contains \"{req['custom_location_name']}\""
    if req.get("target_address"):
        expected_query += f"| where properties.targetAddress =~ \"{req['target_address']}\""
    assert query_args["custom_query"] == expected_query
