# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.commands_asset_endpoint_profiles import delete_asset_endpoint_profile
from azext_edge.edge.common import ResourceTypeMapping
from azext_edge.edge.providers.rpsaas.adr.base import API_VERSION

from .....generators import generate_generic_id


@pytest.mark.parametrize("mocked_resource_management_client", [
    {"resources.get": {"extendedLocation": {"name": generate_generic_id()}}}
], ids=["resources.get"], indirect=True)
@pytest.mark.parametrize("resource_group", [None, generate_generic_id()])
def test_delete_asset(
    mocked_cmd,
    mocked_resource_management_client,
    mock_check_cluster_connectivity,
    resource_group
):
    asset_endpoint_profile_name = generate_generic_id()
    resource_group = generate_generic_id()
    result = delete_asset_endpoint_profile(
        cmd=mocked_cmd,
        asset_endpoint_profile_name=asset_endpoint_profile_name,
        resource_group_name=resource_group
    )

    assert result is None
    mocked_resource_management_client.resources.begin_delete.assert_called_once()
    call_kwargs = mocked_resource_management_client.resources.begin_delete.call_args.kwargs
    assert call_kwargs["resource_group_name"] == resource_group
    assert call_kwargs["resource_provider_namespace"] == ResourceTypeMapping.asset_endpoint_profile.value
    assert call_kwargs["parent_resource_path"] == ""
    assert call_kwargs["resource_type"] == ""
    assert call_kwargs["resource_name"] == asset_endpoint_profile_name
    assert call_kwargs["api_version"] == API_VERSION
