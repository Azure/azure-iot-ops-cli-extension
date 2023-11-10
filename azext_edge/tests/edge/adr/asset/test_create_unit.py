# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from azure.cli.core.azclierror import (
    RequiredArgumentMissingError
)

from azext_edge.edge.commands_assets import create_asset
from azext_edge.edge.common import ResourceTypeMapping
from azext_edge.edge.providers.adr.base import API_VERSION

from ....generators import generate_generic_id


@pytest.mark.parametrize("mocked_resource_management_client", [{
    "resource_groups.get": {"location": generate_generic_id()},
    "resources.begin_create_or_update_by_id": {"result": generate_generic_id()}
}], ids=["create"], indirect=True)
@pytest.mark.parametrize("asset_helpers_fixture", [{
    "process_asset_sub_points": generate_generic_id(),
    "update_properties": generate_generic_id(),
}], ids=["create helpers"], indirect=True)
@pytest.mark.parametrize("req", [
    {
        "data_points": generate_generic_id(),
    },
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
        "display_name": generate_generic_id(),
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
        "events": generate_generic_id(),
        "dp_publishing_interval": 3333,
        "dp_sampling_interval": 44,
        "ev_queue_size": 888,
    },
])
def test_create_asset(mocker, mocked_cmd, mocked_resource_management_client, asset_helpers_fixture, req):
    patched_sp, patched_up = asset_helpers_fixture
    patched_cap = mocker.patch(
        "azext_edge.edge.providers.adr.base.ResourceManagementProvider._check_cluster_and_custom_location"
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
    assert request_body["extendedLocation"] == patched_cap.return_value

    # Extended location helper call
    for arg in patched_cap.call_args.kwargs:
        expected_arg = mocked_cmd.cli_ctx.data['subscription_id'] if arg == "subscription" else req.get(arg)
        assert patched_cap.call_args.kwargs[arg] == expected_arg

    # Properties
    request_props = request_body["properties"]
    assert request_props["assetEndpointProfileUri"] == endpoint_profile

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


def test_create_asset_error(mocked_cmd):
    with pytest.raises(RequiredArgumentMissingError):
        create_asset(
            cmd=mocked_cmd,
            asset_name=generate_generic_id(),
            resource_group_name=generate_generic_id(),
            endpoint=generate_generic_id()
        )
