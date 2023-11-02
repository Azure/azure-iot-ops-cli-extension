# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.commands_assets import update_asset
from azext_edge.edge.providers.adr.base import API_VERSION

from .conftest import (
    MINIMUM_ASSET,
    FULL_ASSET
)
from ....generators import generate_generic_id


@pytest.mark.parametrize("mocked_resource_management_client", [
    {
        "resources.get": MINIMUM_ASSET,
        "resources.begin_create_or_update_by_id": {"result": generate_generic_id()}
    },
    {
        "resources.get": FULL_ASSET,
        "resources.begin_create_or_update_by_id": {"result": generate_generic_id()}
    },
], ids=["minimal", "full"], indirect=True)
@pytest.mark.parametrize("asset_helpers_fixture", [{
    "process_asset_sub_points": generate_generic_id(),
    "update_properties": generate_generic_id(),
}], ids=["update helpers"], indirect=True)
@pytest.mark.parametrize("req", [
    {},
    {
        "asset_type": generate_generic_id(),
        "description": generate_generic_id(),
        "disabled": True,
        "display_name": generate_generic_id(),
        "documentation_uri": generate_generic_id(),
        "external_asset_id": generate_generic_id(),
        "hardware_revision": generate_generic_id(),
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
        "disabled": False,
        "dp_publishing_interval": 3333,
        "dp_sampling_interval": 44,
        "ev_queue_size": 888,
    },
])
def test_update_asset(
    mocked_cmd, mocked_resource_management_client, asset_helpers_fixture, req
):
    _, patched_up = asset_helpers_fixture
    # Required params
    asset_name = generate_generic_id()
    # force show call to one branch
    resource_group_name = generate_generic_id()
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
    assert call_kwargs["api_version"] == API_VERSION

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
