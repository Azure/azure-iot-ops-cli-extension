# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from .....generators import generate_random_string


@pytest.mark.parametrize("mocked_resource_management_client", [
    {"resources.get": {"extended_location": {"name": generate_random_string()}}},
    {"resources.get": {"extendedLocation": {"name": generate_random_string()}}},
    {"resources.get": {"result": generate_random_string()}},
], ids=["extended_location", "extendedLocation", "result"], indirect=True)
@pytest.mark.parametrize("parent_resource_path", ["", generate_random_string()])
@pytest.mark.parametrize("check_cluster_connectivity", [True, False])
def test_show(
    mocked_cmd,
    mock_check_cluster_connectivity,
    mocked_resource_management_client,
    check_cluster_connectivity,
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
    result = provider.show(resource_name, resource_group_name, check_cluster_connectivity)

    mocked_resource_management_client.resources.get.assert_called_once()
    kwargs = mocked_resource_management_client.resources.get.call_args.kwargs
    assert kwargs["resource_group_name"] == resource_group_name
    assert kwargs["resource_provider_namespace"] == provider_namespace
    assert kwargs["parent_resource_path"] == parent_resource_path
    assert kwargs["resource_type"] == resource_type
    assert kwargs["resource_name"] == resource_name
    assert kwargs["api_version"] == api_version

    # note that pop will modify the return value
    as_dict = mocked_resource_management_client.resources.get.return_value.as_dict.return_value
    assert "extended_location" not in result
    assert result == as_dict

    assert mock_check_cluster_connectivity.called is check_cluster_connectivity
    if check_cluster_connectivity:
        mock_check_cluster_connectivity.assert_called_once_with(
            as_dict.get("extendedLocation", {}).get("name")
        )
