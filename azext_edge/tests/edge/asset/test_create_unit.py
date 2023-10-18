# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import pytest

from azure.cli.core.azclierror import (
    ResourceNotFoundError, RequiredArgumentMissingError, ValidationError
)

from azext_edge.edge.commands_assets import create_asset
from azext_edge.edge.common import ResourceTypeMapping
from azext_edge.edge.providers.assets import API_VERSION

from ...generators import generate_generic_id
from .conftest import ASSETS_PATH


@pytest.mark.parametrize("mocked_resource_management_client", [{
    "resource_groups.get": {"location": generate_generic_id()},
    "resources.begin_create_or_update_by_id": {"result": generate_generic_id()}
}], ids=["create"], indirect=True)
@pytest.mark.parametrize("asset_helpers_fixture", [{
    "process_asset_sub_points": generate_generic_id(),
    "update_properties": generate_generic_id(),
}], ids=["create helpers"], indirect=True)
@pytest.mark.parametrize("req", [
    {},
    {
        "asset_type": generate_generic_id(),
        "custom_location_name": generate_generic_id(),
        "custom_location_resource_group": generate_generic_id(),
        "custom_location_subscription": generate_generic_id(),
        "cluster_name": generate_generic_id(),
        "cluster_resource_group": generate_generic_id(),
        "cluster_subscription": generate_generic_id(),
        "data_points": generate_generic_id(),
        "description": generate_generic_id(),
        "disabled": True,
        "documentation_uri": generate_generic_id(),
        "events": generate_generic_id(),
        "external_asset_id": generate_generic_id(),
        "hardware_revision": generate_generic_id(),
        "location": generate_generic_id(),
        "manufacturer": generate_generic_id(),
        "manufacturer_uri": generate_generic_id(),
        "model": generate_generic_id(),
        "product_code": generate_generic_id(),
        "serial_number": generate_generic_id(),
        "software_revision": generate_generic_id(),
        "dp_publishing_interval": 3333,
        "dp_sampling_interval": 44,
        "dp_queue_size": 55,
        "ev_publishing_interval": 666,
        "ev_sampling_interval": 777,
        "ev_queue_size": 888,
        "tags": generate_generic_id(),
    },
    {
        "asset_type": generate_generic_id(),
        "custom_location_resource_group": generate_generic_id(),
        "disabled": False,
        "dp_publishing_interval": 3333,
        "dp_sampling_interval": 44,
        "ev_queue_size": 888,
    },
])
def test_create_asset(mocker, mocked_cmd, mocked_resource_management_client, asset_helpers_fixture, req):
    patched_sp, patched_up = asset_helpers_fixture
    patched_cap = mocker.patch(
        "azext_edge.edge.providers.assets.AssetProvider._check_asset_cluster_and_custom_location"
    )
    patched_cap.return_value = generate_generic_id()

    # Required params
    asset_name = generate_generic_id()
    resource_group_name = generate_generic_id()
    endpoint_profile = generate_generic_id()

    result = create_asset(
        cmd=mocked_cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name,
        endpoint=endpoint_profile,
        **req
    ).result()

    # resource group call
    location = req.get(
        "location",
        mocked_resource_management_client.resource_groups.get.return_value.as_dict.return_value["location"]
    )
    if req.get("location"):
        mocked_resource_management_client.resource_groups.get.assert_not_called()
    else:
        mocked_resource_management_client.resource_groups.get.assert_called_once()

    # create call
    poller = mocked_resource_management_client.resources.begin_create_or_update_by_id.return_value
    assert result == poller.result()
    mocked_resource_management_client.resources.begin_create_or_update_by_id.assert_called_once()
    call_kwargs = mocked_resource_management_client.resources.begin_create_or_update_by_id.call_args.kwargs
    expected_resource_path = f"/resourceGroups/{resource_group_name}/providers/{ResourceTypeMapping.asset.value}"\
        f"/{asset_name}"
    assert expected_resource_path in call_kwargs["resource_id"]
    assert call_kwargs["api_version"] == API_VERSION

    # asset body
    request_body = call_kwargs["parameters"]
    assert request_body["location"] == location
    assert request_body["tags"] == req.get("tags")
    assert request_body["extendedLocation"]["type"] == "CustomLocation"
    assert request_body["extendedLocation"]["name"] == patched_cap.return_value

    # Extended location helper call
    for arg in patched_cap.call_args.kwargs:
        expected_arg = mocked_cmd.cli_ctx.data['subscription_id'] if arg == "subscription" else req.get(arg)
        assert patched_cap.call_args.kwargs[arg] == expected_arg

    # Properties
    request_props = request_body["properties"]
    assert request_props["connectivityProfileUri"] == endpoint_profile

    # Check that update props mock got called correctly
    assert request_props["result"]
    assert request_props.get("defaultDataPointsConfiguration") is None
    assert request_props.get("defaultEventsConfiguration") is None

    # Set up defaults
    req["disabled"] = req.get("disabled", False)
    req["dp_publishing_interval"] = req.get("dp_publishing_interval", 1000)
    req["dp_sampling_interval"] = req.get("dp_sampling_interval", 500)
    req["dp_queue_size"] = req.get("dp_queue_size", 1)
    req["ev_publishing_interval"] = req.get("ev_publishing_interval", 1000)
    req["ev_sampling_interval"] = req.get("ev_sampling_interval", 500)
    req["ev_queue_size"] = req.get("ev_queue_size", 1)
    for arg in patched_up.call_args.kwargs:
        assert patched_up.call_args.kwargs[arg] == req.get(arg)
        assert request_props.get(arg) is None

    # Data points + events
    assert patched_sp.call_args_list[0].args[0] == "data_source"
    assert patched_sp.call_args_list[0].args[1] == req.get("data_points")
    assert request_props["dataPoints"] == patched_sp.return_value
    assert patched_sp.call_args_list[1].args[0] == "event_notifier"
    assert patched_sp.call_args_list[1].args[1] == req.get("events")
    assert request_props["events"] == patched_sp.return_value


@pytest.mark.parametrize("mocked_resource_management_client", [{
    "resources.get_by_id": {"properties": {"extensionType": "microsoft.deviceregistry.assets"}},
}], ids=["extension"], indirect=True)
@pytest.mark.parametrize("mocked_build_query", [{
    "path": ASSETS_PATH,
    "side_effect": [[{
        "id": generate_generic_id(),
        "properties": {
            "clusterExtensionIds": [generate_generic_id()],
            "hostResourceId": generate_generic_id()
        }
    }]]
}], ids=["query for location"], indirect=True)
@pytest.mark.parametrize("custom_location_resource_group", [None, generate_generic_id()])
@pytest.mark.parametrize("custom_location_subscription", [None, generate_generic_id()])
@pytest.mark.parametrize("cluster_resource_group", [None, generate_generic_id()])
@pytest.mark.parametrize("cluster_subscription", [None, generate_generic_id()])
@pytest.mark.parametrize("req", [
    {
        "custom_location_name": generate_generic_id(),
        "cluster_name": generate_generic_id()
    },
    {
        "custom_location_name": generate_generic_id(),
    },
    {
        "cluster_name": generate_generic_id()
    }
], ids=[
    "location and cluster",
    "location only",
    "cluster only"
])
def test_check_asset_cluster_and_custom_location(
    mocked_cmd,
    mocked_get_subscription_id,
    mocked_resource_management_client,
    mocked_build_query,
    req,
    custom_location_resource_group,
    custom_location_subscription,
    cluster_resource_group,
    cluster_subscription
):
    from azext_edge.edge.providers.assets import AssetProvider
    asset_provider = AssetProvider(mocked_cmd)

    custom_location_name = req.get("custom_location_name")
    cluster_name = req.get("cluster_name")

    # Get all the query results for checking
    query_results = list(mocked_build_query.side_effect)
    cluster_query_result = {
        "id": generate_generic_id(),
        "name": generate_generic_id()
    }
    location_query_result = query_results[0][0]
    if cluster_name:
        query_results.insert(0, [cluster_query_result])
    else:
        query_results.append([cluster_query_result])
    mocked_build_query.side_effect = query_results
    asset_subscription = mocked_get_subscription_id.return_value

    result_id = asset_provider._check_asset_cluster_and_custom_location(
        custom_location_name=custom_location_name,
        custom_location_resource_group=custom_location_resource_group,
        custom_location_subscription=custom_location_subscription,
        cluster_name=cluster_name,
        cluster_resource_group=cluster_resource_group,
        cluster_subscription=cluster_subscription
    )
    assert result_id == location_query_result["id"]

    assert mocked_build_query.call_count == 2

    # queries
    call = 0
    if cluster_name:
        cluster_query_kwargs = mocked_build_query.call_args_list[call].kwargs
        assert cluster_query_kwargs["subscription_id"] == (cluster_subscription or asset_subscription)
        assert cluster_query_kwargs["type"] == ResourceTypeMapping.connected_cluster.value
        assert cluster_query_kwargs["name"] == cluster_name
        assert cluster_query_kwargs["resource_group"] == cluster_resource_group
        call += 1

    location_query_kwargs = mocked_build_query.call_args_list[call].kwargs
    assert location_query_kwargs["subscription_id"] == (custom_location_subscription or asset_subscription)
    assert location_query_kwargs["type"] == ResourceTypeMapping.custom_location.value
    assert location_query_kwargs["name"] == custom_location_name
    assert location_query_kwargs["resource_group"] == custom_location_resource_group
    custom_query = f"| where properties.hostResourceId =~ \"{cluster_query_result['id']}\" " if cluster_name else ""
    assert location_query_kwargs["custom_query"] == custom_query
    call += 1

    if not cluster_name:
        cluster_query_kwargs = mocked_build_query.call_args_list[call].kwargs
        assert cluster_query_kwargs["subscription_id"] == (cluster_subscription or asset_subscription)
        assert cluster_query_kwargs["type"] == ResourceTypeMapping.connected_cluster.value
        custom_query = f'| where id =~ "{location_query_result["properties"]["hostResourceId"]}"'
        assert cluster_query_kwargs["custom_query"] == custom_query

    # Extension Call
    mocked_resource_management_client.resources.get_by_id.assert_called_once()
    extension_kwargs = mocked_resource_management_client.resources.get_by_id.call_args.kwargs
    assert extension_kwargs["resource_id"] == location_query_result["properties"]["clusterExtensionIds"][0]
    assert extension_kwargs["api_version"] == "2023-05-01"


def test_check_asset_cluster_and_custom_location_argument_error(
    mocked_cmd,
):
    from azext_edge.edge.providers.assets import AssetProvider
    asset_provider = AssetProvider(mocked_cmd)

    with pytest.raises(RequiredArgumentMissingError):
        asset_provider._check_asset_cluster_and_custom_location(
            custom_location_name=None,
            cluster_name=None,
        )


@pytest.mark.parametrize("mocked_build_query", [
    {
        "path": ASSETS_PATH,
        "return_value": []
    },
    {
        "path": ASSETS_PATH,
        "return_value": generate_generic_id()
    },
], ids=["not found", "too many"], indirect=True)
@pytest.mark.parametrize("req", [
    {
        "custom_location_name": generate_generic_id(),
        "cluster_name": generate_generic_id()
    },
    {
        "custom_location_name": generate_generic_id(),
    },
    {
        "cluster_name": generate_generic_id()
    }
], ids=[
    "location and cluster",
    "location only",
    "cluster only"
])
def test_check_asset_cluster_and_custom_location_build_query_error(
    mocked_cmd,
    mocked_build_query,
    req
):
    from azext_edge.edge.providers.assets import AssetProvider
    asset_provider = AssetProvider(mocked_cmd)

    custom_location_name = req.get("custom_location_name")
    cluster_name = req.get("cluster_name")

    expected_result = mocked_build_query.return_value

    with pytest.raises(Exception) as e:
        asset_provider._check_asset_cluster_and_custom_location(
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
        "resources.get_by_id": {"properties": {"extensionType": generate_generic_id()}}
    },
], ids=["invalid_extensions"], indirect=True)
@pytest.mark.parametrize("mocked_build_query", [
    {
        "path": ASSETS_PATH,
        "return_value": [{
            "name": generate_generic_id(),
            "id": generate_generic_id(),
            "properties": {
                "clusterExtensionIds": [generate_generic_id()],
                "hostResourceId": generate_generic_id()
            }
        }]
    },
], ids=["build_query"], indirect=True)
def test_check_asset_cluster_and_custom_location_no_extension_error(
    mocked_cmd,
    mocked_build_query,
    mocked_resource_management_client,
):
    from azext_edge.edge.providers.assets import AssetProvider
    asset_provider = AssetProvider(mocked_cmd)

    with pytest.raises(Exception) as e:
        asset_provider._check_asset_cluster_and_custom_location(
            custom_location_name=generate_generic_id(),
            cluster_name=generate_generic_id(),
        )

    assert mocked_build_query.call_count == 2
    mocked_resource_management_client.resources.get_by_id.assert_called_once()

    assert isinstance(e.value, ValidationError)
    assert "missing the microsoft.deviceregistry.assets extension" in e.value.error_msg.lower()
