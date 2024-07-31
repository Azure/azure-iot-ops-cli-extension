# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from .....generators import generate_random_string


@pytest.mark.parametrize("mocked_resource_management_client", [
    {
        "resources.begin_delete": {"result": generate_random_string()},
        "resources.get": {"extendedLocation": {"name": generate_random_string()}}
    },
], ids=["result"], indirect=True)
@pytest.mark.parametrize("skip_connectivity_check", [True, False])
@pytest.mark.parametrize("parent_resource_path", ["", generate_random_string()])
def test_delete(
    mocked_cmd,
    mock_check_cluster_connectivity,
    mocked_resource_management_client,
    skip_connectivity_check,
    parent_resource_path
):
    from azext_edge.edge.providers.rpsaas.base_provider import RPSaaSBaseProvider
    api_version = generate_random_string()
    resource_type = generate_random_string()
    resource_name = generate_random_string()
    resource_group_name = generate_random_string()
    provider_namespace = generate_random_string()
    provider = RPSaaSBaseProvider(
        cmd=mocked_cmd,
        api_version=api_version,
        provider_namespace=provider_namespace,
        resource_type=resource_type,
        parent_resource_path=parent_resource_path
    )
    result = provider.delete(resource_name, resource_group_name, skip_connectivity_check)

    assert mock_check_cluster_connectivity.called is not skip_connectivity_check

    mocked_resource_management_client.resources.begin_delete.assert_called_once()
    kwargs = mocked_resource_management_client.resources.begin_delete.call_args.kwargs
    assert kwargs["resource_group_name"] == resource_group_name
    assert kwargs["resource_provider_namespace"] == provider_namespace
    assert kwargs["parent_resource_path"] == parent_resource_path
    assert kwargs["resource_type"] == resource_type
    assert kwargs["resource_name"] == resource_name
    assert kwargs["api_version"] == api_version
    assert result is None
