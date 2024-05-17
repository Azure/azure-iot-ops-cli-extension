# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.commands_assets import update_asset
from azext_edge.edge.providers.rpsaas.adr.base import ADR_API_VERSION

from .conftest import (
    MINIMUM_ASSET,
    FULL_ASSET
)
from .....generators import generate_random_string


@pytest.mark.parametrize("mocked_resource_management_client", [
    {
        "resources.get": MINIMUM_ASSET,
        "resources.begin_create_or_update_by_id": {"result": generate_random_string()}
    },
    {
        "resources.get": FULL_ASSET,
        "resources.begin_create_or_update_by_id": {"result": generate_random_string()}
    },
], ids=["minimal", "full"], indirect=True)
@pytest.mark.parametrize("asset_helpers_fixture", [{
    "process_asset_sub_points": generate_random_string(),
    "update_properties": generate_random_string(),
}], ids=["update helpers"], indirect=True)
@pytest.mark.parametrize("req", [
    {},
    {
        "asset_type": generate_random_string(),
        "custom_attributes": [generate_random_string()],
        "description": generate_random_string(),
        "disabled": True,
        "display_name": generate_random_string(),
        "documentation_uri": generate_random_string(),
        "external_asset_id": generate_random_string(),
        "hardware_revision": generate_random_string(),
        "manufacturer": generate_random_string(),
        "manufacturer_uri": generate_random_string(),
        "model": generate_random_string(),
        "product_code": generate_random_string(),
        "serial_number": generate_random_string(),
        "software_revision": generate_random_string(),
        "dp_publishing_interval": 3333,
        "dp_sampling_interval": 44,
        "dp_queue_size": 55,
        "ev_publishing_interval": 666,
        "ev_sampling_interval": 777,
        "ev_queue_size": 888,
        "tags": generate_random_string(),
    },
    {
        "asset_type": generate_random_string(),
        "custom_attributes": [generate_random_string()],
        "disabled": False,
        "dp_publishing_interval": 3333,
        "dp_sampling_interval": 44,
        "ev_queue_size": 888,
    },
])
def test_update_asset(
    mocked_cmd,
    mock_check_cluster_connectivity,
    mocked_resource_management_client,
    asset_helpers_fixture,
    req
):
    patched_up = asset_helpers_fixture["update_properties"]
    # Required params
    asset_name = generate_random_string()
    # force show call to one branch
    resource_group_name = generate_random_string()
    result = update_asset(
        cmd=mocked_cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name,
        **req
    ).result()

    mocked_resource_management_client.resources.get.assert_called_once()
    mocked_resource_management_client.resources.begin_create_or_update_by_id.assert_called_once()
    original_asset = mocked_resource_management_client.resources.get.return_value.original
    poller = mocked_resource_management_client.resources.begin_create_or_update_by_id.return_value
    assert result == poller.result()

    # Update call
    call_kwargs = mocked_resource_management_client.resources.begin_create_or_update_by_id.call_args.kwargs
    assert call_kwargs["resource_id"] == original_asset["id"]
    assert call_kwargs["api_version"] == ADR_API_VERSION

    # Check update request
    request_body = call_kwargs["parameters"]
    assert request_body["location"] == original_asset["location"]
    assert request_body["extendedLocation"] == original_asset["extendedLocation"]
    assert request_body.get("tags") == req.get("tags", original_asset.get("tags"))

    # Properties
    request_props = request_body["properties"]
    original_props = original_asset["properties"]
    assert request_props["assetEndpointProfileUri"] == original_props["assetEndpointProfileUri"]

    # Check that update props mock got called correctly
    assert request_props["result"]
    assert request_props.get("defaultDataPointsConfiguration") is None
    assert request_props.get("defaultEventsConfiguration") is None
    for arg in patched_up.call_args.kwargs:
        assert patched_up.call_args.kwargs[arg] == req.get(arg)
        assert request_props.get(arg) is None
