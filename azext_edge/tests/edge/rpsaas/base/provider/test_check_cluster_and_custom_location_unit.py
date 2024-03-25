# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from azure.cli.core.azclierror import (
    ResourceNotFoundError, RequiredArgumentMissingError, ValidationError
)

from azext_edge.edge.common import ResourceTypeMapping
from ...conftest import BP_PATH
from .....generators import generate_random_string


@pytest.mark.parametrize("mocked_resource_management_client", [{
    "resources.get_by_id": {"properties": {"extensionType": "microsoft.deviceregistry.assets"}},
}], ids=["extension"], indirect=True)
@pytest.mark.parametrize("mocked_build_query", [{
    "path": BP_PATH,
    "side_effect": [[{
        "id": generate_random_string(),
        "properties": {
            "clusterExtensionIds": [generate_random_string()],
            "hostResourceId": generate_random_string(),
        }
    }]]
}], ids=["query for location"], indirect=True)
@pytest.mark.parametrize("custom_location_resource_group", [None, generate_random_string()])
@pytest.mark.parametrize("custom_location_subscription", [None, generate_random_string()])
@pytest.mark.parametrize("cluster_resource_group", [None, generate_random_string()])
@pytest.mark.parametrize("cluster_subscription", [None, generate_random_string()])
@pytest.mark.parametrize("req", [
    {
        "custom_location_name": generate_random_string(),
        "cluster_name": generate_random_string()
    },
    {
        "custom_location_name": generate_random_string(),
    },
    {
        "cluster_name": generate_random_string()
    }
], ids=[
    "location and cluster",
    "location only",
    "cluster only"
])
def test_check_cluster_and_custom_location(
    mocked_cmd,
    mocked_resource_management_client,
    mocked_build_query,
    req,
    custom_location_resource_group,
    custom_location_subscription,
    cluster_resource_group,
    cluster_subscription
):
    from azext_edge.edge.providers.rpsaas.adr.base import ADRBaseProvider
    provider = ADRBaseProvider(mocked_cmd, generate_random_string())

    custom_location_name = req.get("custom_location_name")
    cluster_name = req.get("cluster_name")

    # Get all the query results for checking
    query_results = list(mocked_build_query.side_effect)
    cluster_query_result = {
        "id": generate_random_string(),
        "name": generate_random_string(),
        "properties": {"connectivityStatus": "Connected"}
    }
    location_query_result = query_results[0][0]
    if cluster_name:
        query_results.insert(0, [cluster_query_result])
    else:
        query_results.append([cluster_query_result])
    mocked_build_query.side_effect = query_results

    result = provider.check_cluster_and_custom_location(
        custom_location_name=custom_location_name,
        custom_location_resource_group=custom_location_resource_group,
        custom_location_subscription=custom_location_subscription,
        cluster_name=cluster_name,
        cluster_resource_group=cluster_resource_group,
        cluster_subscription=cluster_subscription
    )
    assert result["type"] == "CustomLocation"
    assert result["name"] == location_query_result["id"]

    assert mocked_build_query.call_count == 2

    # queries
    call = 0
    if cluster_name:
        cluster_query_kwargs = mocked_build_query.call_args_list[call].kwargs
        assert cluster_query_kwargs["subscription_id"] == cluster_subscription
        assert cluster_query_kwargs["type"] == ResourceTypeMapping.connected_cluster.full_resource_path
        assert cluster_query_kwargs["name"] == cluster_name
        assert cluster_query_kwargs["resource_group"] == cluster_resource_group
        call += 1

    location_query_kwargs = mocked_build_query.call_args_list[call].kwargs
    assert location_query_kwargs["subscription_id"] == custom_location_subscription
    assert location_query_kwargs["type"] == ResourceTypeMapping.custom_location.full_resource_path
    assert location_query_kwargs["name"] == custom_location_name
    assert location_query_kwargs["resource_group"] == custom_location_resource_group
    custom_query = f"| where properties.hostResourceId =~ \"{cluster_query_result['id']}\" " if cluster_name else ""
    assert location_query_kwargs["custom_query"] == custom_query
    call += 1

    if not cluster_name:
        cluster_query_kwargs = mocked_build_query.call_args_list[call].kwargs
        assert cluster_query_kwargs["subscription_id"] == cluster_subscription
        assert cluster_query_kwargs["type"] == ResourceTypeMapping.connected_cluster.full_resource_path
        custom_query = f'| where id =~ "{location_query_result["properties"]["hostResourceId"]}"'
        assert cluster_query_kwargs["custom_query"] == custom_query

    # Extension Call
    mocked_resource_management_client.resources.get_by_id.assert_called_once()
    extension_kwargs = mocked_resource_management_client.resources.get_by_id.call_args.kwargs
    assert extension_kwargs["resource_id"] == location_query_result["properties"]["clusterExtensionIds"][0]
    assert extension_kwargs["api_version"] == "2023-05-01"


def test_check_cluster_and_custom_location_argument_error(
    mocked_cmd,
):
    from azext_edge.edge.providers.rpsaas.adr.base import ADRBaseProvider
    provider = ADRBaseProvider(mocked_cmd, generate_random_string())

    with pytest.raises(RequiredArgumentMissingError):
        provider.check_cluster_and_custom_location(
            custom_location_name=None,
            cluster_name=None,
        )


@pytest.mark.parametrize("mocked_build_query", [
    {
        "path": BP_PATH,
        "return_value": []
    },
    {
        "path": BP_PATH,
        "return_value": generate_random_string()
    },
], ids=["not found", "too many"], indirect=True)
@pytest.mark.parametrize("req", [
    {
        "custom_location_name": generate_random_string(),
        "cluster_name": generate_random_string()
    },
    {
        "custom_location_name": generate_random_string(),
    },
    {
        "cluster_name": generate_random_string()
    }
], ids=[
    "location and cluster",
    "location only",
    "cluster only"
])
def test_check_cluster_and_custom_location_build_query_error(
    mocked_cmd,
    mocked_build_query,
    req
):
    from azext_edge.edge.providers.rpsaas.adr.base import ADRBaseProvider
    provider = ADRBaseProvider(mocked_cmd, generate_random_string())
    custom_location_name = req.get("custom_location_name")
    cluster_name = req.get("cluster_name")

    expected_result = mocked_build_query.return_value

    with pytest.raises(Exception) as e:
        provider.check_cluster_and_custom_location(
            custom_location_name=custom_location_name,
            cluster_name=cluster_name,
        )

    if len(expected_result) == 0:
        assert isinstance(e.value, ResourceNotFoundError)
    if len(expected_result) > 1:
        assert isinstance(e.value, ValidationError)

    if custom_location_name and not cluster_name:
        assert "custom location" in e.value.error_msg.lower()
    if cluster_name:
        assert "cluster" in e.value.error_msg.lower()


@pytest.mark.parametrize("mocked_resource_management_client", [
    {
        "resources.get_by_id": {"properties": {"extensionType": generate_random_string()}}
    },
], ids=["invalid_extensions"], indirect=True)
@pytest.mark.parametrize("mocked_build_query", [
    {
        "path": BP_PATH,
        "return_value": [{
            "name": generate_random_string(),
            "id": generate_random_string(),
            "properties": {
                "clusterExtensionIds": [generate_random_string()],
                "hostResourceId": generate_random_string(),
                "connectivityStatus": "Connected"
            }
        }]
    },
], ids=["build_query"], indirect=True)
def test_check_cluster_and_custom_location_no_extension_error(
    mocked_cmd,
    mocked_build_query,
    mocked_resource_management_client,
):
    from azext_edge.edge.providers.rpsaas.adr.base import ADRBaseProvider
    provider = ADRBaseProvider(mocked_cmd, generate_random_string())

    with pytest.raises(Exception) as e:
        provider.check_cluster_and_custom_location(
            custom_location_name=generate_random_string(),
            cluster_name=generate_random_string(),
        )

    assert mocked_build_query.call_count == 2
    mocked_resource_management_client.resources.get_by_id.assert_called_once()

    assert isinstance(e.value, ValidationError)
    assert "missing the microsoft.deviceregistry.assets extension" in e.value.error_msg.lower()
