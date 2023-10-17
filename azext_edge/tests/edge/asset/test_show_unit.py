# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.commands_assets import show_asset
from azext_edge.edge.common import ResourceTypeMapping
from azext_edge.edge.providers.assets import API_VERSION

from ...generators import generate_generic_id


@pytest.mark.parametrize("mocked_resource_management_client", [
    {"resources.get": {"result": generate_generic_id()}}
], ids=["resources.get"], indirect=True)
@pytest.mark.parametrize("resource_group", [None, generate_generic_id()])
def test_show_asset(
    mocked_cmd,
    mocked_resource_management_client,
    mocked_send_raw_request,
    resource_group
):
    asset_name = generate_generic_id()
    resource_group = generate_generic_id()

    result = show_asset(
        cmd=mocked_cmd,
        asset_name=asset_name,
        resource_group_name=resource_group
    )
    mocked_send_raw_request.assert_not_called()
    mocked_resource_management_client.resources.get.assert_called_once()
    call_kwargs = mocked_resource_management_client.resources.get.call_args.kwargs
    assert call_kwargs["resource_group_name"] == resource_group
    assert call_kwargs["resource_provider_namespace"] == ResourceTypeMapping.asset.value
    assert call_kwargs["parent_resource_path"] == ""
    assert call_kwargs["resource_type"] == ""
    assert call_kwargs["resource_name"] == asset_name
    assert call_kwargs["api_version"] == API_VERSION
    assert result == mocked_resource_management_client.resources.get.return_value.as_dict.return_value