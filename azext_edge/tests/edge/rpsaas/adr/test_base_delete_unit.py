# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.providers.rpsaas.adr.base import API_VERSION

from ....generators import generate_generic_id


@pytest.mark.parametrize("mocked_resource_management_client", [
    {"resources.get": {"extendedLocation": {"name": generate_generic_id()}}}
], ids=["resources.get"], indirect=True)
@pytest.mark.parametrize("resource_group", [None, generate_generic_id()])
def test_delete_asset(
    mocked_cmd,
    mock_check_cluster_connectivity,
    mocked_resource_management_client,
    resource_group
):
    asset_name = generate_generic_id()
    resource_group = generate_generic_id()
    from azext_edge.edge.providers.rpsaas.adr.base import ADRBaseProvider
    provider = ADRBaseProvider(mocked_cmd, generate_generic_id())
    result = provider.delete(
        resource_name=asset_name,
        resource_group_name=resource_group
    )

    assert result is None
    mock_check_cluster_connectivity.assert_called_once()

    mocked_resource_management_client.resources.begin_delete.assert_called_once()
    call_kwargs = mocked_resource_management_client.resources.begin_delete.call_args.kwargs
    assert call_kwargs["resource_group_name"] == resource_group
    assert call_kwargs["parent_resource_path"] == ""
    assert call_kwargs["resource_type"] == ""
    assert call_kwargs["resource_name"] == asset_name
    assert call_kwargs["api_version"] == API_VERSION
