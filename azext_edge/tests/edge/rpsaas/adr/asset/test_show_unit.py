# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.commands_assets import show_asset
from azext_edge.edge.common import ResourceTypeMapping, ResourceProviderMapping
from azext_edge.edge.providers.rpsaas.adr.base import ADR_API_VERSION

from .....generators import generate_random_string


@pytest.mark.parametrize("mocked_resource_management_client", [
    {"resources.get": {"result": generate_random_string()}}
], ids=["resources.get"], indirect=True)
@pytest.mark.parametrize("resource_group", [None, generate_random_string()])
def test_show_asset(
    mocked_cmd,
    mocked_resource_management_client,
    resource_group
):
    asset_name = generate_random_string()
    resource_group = generate_random_string()

    result = show_asset(
        cmd=mocked_cmd,
        asset_name=asset_name,
        resource_group_name=resource_group
    )
    mocked_resource_management_client.resources.get.assert_called_once()
    call_kwargs = mocked_resource_management_client.resources.get.call_args.kwargs
    assert call_kwargs["resource_group_name"] == resource_group
    assert call_kwargs["resource_type"] == ResourceTypeMapping.asset.value
    assert call_kwargs["parent_resource_path"] == ""
    assert call_kwargs["resource_provider_namespace"] == ResourceProviderMapping.deviceregistry.value
    assert call_kwargs["resource_name"] == asset_name
    assert call_kwargs["api_version"] == ADR_API_VERSION
    assert result == mocked_resource_management_client.resources.get.return_value.as_dict.return_value
