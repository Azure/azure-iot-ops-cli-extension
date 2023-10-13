# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.commands_assets import delete_asset
from azext_edge.edge.common import ResourceTypeMapping
from azext_edge.edge.providers.assets import API_VERSION

from ...generators import generate_generic_id


@pytest.mark.parametrize("mocked_resource_management_client", [
    {"resources.get": {"result": generate_generic_id()}}
], ids=["resources.get"], indirect=True)
@pytest.mark.parametrize("mocked_send_raw_request", [
    {
        "value": [
            {"name": generate_generic_id(), "resourceGroup": generate_generic_id()},
            {"name": generate_generic_id(), "resourceGroup": generate_generic_id()}
        ]
    }
], ids=["raw_request"], indirect=True)
@pytest.mark.parametrize("resource_group", [None, generate_generic_id()])
def test_delete_asset(
    mocked_cmd,
    mocked_resource_management_client,
    mocked_send_raw_request,
    resource_group
):

    expected_list_asset = mocked_send_raw_request.return_value.json.return_value["value"][1]

    result = delete_asset(
        cmd=mocked_cmd,
        asset_name=expected_list_asset["name"],
        resource_group_name=resource_group
    )

    assert result is None
    mocked_resource_management_client.resources.begin_delete.assert_called_once()
    call_kwargs = mocked_resource_management_client.resources.begin_delete.call_args.kwargs
    assert call_kwargs["resource_group_name"] == (resource_group or expected_list_asset["resourceGroup"])
    assert call_kwargs["resource_provider_namespace"] == ResourceTypeMapping.asset.value
    assert call_kwargs["parent_resource_path"] == ""
    assert call_kwargs["resource_type"] == ""
    assert call_kwargs["resource_name"] == expected_list_asset["name"]
    assert call_kwargs["api_version"] == API_VERSION
