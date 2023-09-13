# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import json
import pytest

from azext_edge.common.utility import assemble_nargs_to_dict

from ....edge.commands_assets import create_asset

from . import EMBEDDED_CLI_ASSETS_PATH, PROCESS_DP_ASSETS_PATH, PROCESS_EV_ASSETS_PATH
from ...helpers import parse_rest_command
from ...generators import generate_generic_id

@pytest.fixture()
def process_dp_and_ev_fixture(mocker, request):
    patched_dp = mocker.patch(PROCESS_DP_ASSETS_PATH)
    patched_dp.return_value = request.param["process_dp_result"]
    patched_ev = mocker.patch(PROCESS_EV_ASSETS_PATH)
    patched_ev.return_value = request.param["process_ev_result"]
    yield patched_dp, patched_ev

@pytest.mark.parametrize("embedded_cli_client", [{
    "path": EMBEDDED_CLI_ASSETS_PATH,
    "as_json_result": {"result": generate_generic_id()}
}], indirect=True)
@pytest.mark.parametrize("process_dp_and_ev_fixture", [{
    "process_dp_result": generate_generic_id(),
    "process_ev_result": generate_generic_id()
}], indirect=True)
@pytest.mark.parametrize("req", [
    {},
    {
        "asset_type": generate_generic_id(),
        "custom_location_resource_group": generate_generic_id(),
        "custom_location_subscription": generate_generic_id(),
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
def test_create_asset(fixture_cmd, embedded_cli_client, process_dp_and_ev_fixture, req):
    patched_dp, patched_ev = process_dp_and_ev_fixture
    # Required params
    asset_name = generate_generic_id()
    resource_group_name = generate_generic_id()
    endpoint_profile = generate_generic_id()
    custom_location = generate_generic_id()
    location = req.get("location")
    custom_location_subscription = req.get(
        "custom_location_subscription",
        fixture_cmd.cli_ctx.data['subscription_id']
    )
    custom_location_resource_group = req.get(
        "custom_location_resource_group",
        resource_group_name
    )

    # no location triggers rg call
    if not location:
        location = generate_generic_id()
        as_json_results = list(embedded_cli_client.as_json.side_effect)
        as_json_results.insert(0, {"location": location})
        embedded_cli_client.as_json.side_effect = as_json_results

    result = create_asset(
        cmd=fixture_cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name,
        endpoint_profile=endpoint_profile,
        custom_location=custom_location,
        **req
    )
    assert result == next(embedded_cli_client.as_json.side_effect)

    request = embedded_cli_client.invoke.call_args[0][-1]
    request_dict = parse_rest_command(request)
    assert request_dict["method"] == "PUT"

    assert f"/resourceGroups/{resource_group_name}/providers/Microsoft.DeviceRegistry"\
        f"/assets/{asset_name}?api-version=" in request_dict["uri"]

    # Check create request
    request_body = json.loads(request_dict["body"].strip("'"))
    assert request_body["location"] == location
    assert request_body["tags"] == req.get("tags")
    assert request_body["extendedLocation"]["type"] == "CustomLocation"
    assert request_body["extendedLocation"]["name"] == f"/subscriptions/{custom_location_subscription}/resourcegroups"\
        f"/{custom_location_resource_group}/providers/microsoft.extendedlocation/customlocations/{custom_location}"

    # Properties
    request_props = request_body["properties"]
    assert request_props["connectivityProfileUri"] == endpoint_profile
    assert request_props["enabled"] is not req.get("disabled", False)

    # Optional props
    assert request_props.get("assetType") == req.get("asset_type")
    assert request_props.get("description") == req.get("description")
    assert request_props.get("documentationUri") == req.get("documentation_uri")
    assert request_props.get("externalAssetId") == req.get("external_asset_id")
    assert request_props.get("hardwareRevision") == req.get("hardware_revision")
    assert request_props.get("manufacturer") == req.get("manufacturer")
    assert request_props.get("manufacturerUri") == req.get("manufacturer_uri")
    assert request_props.get("model") == req.get("model")
    assert request_props.get("productCode") == req.get("product_code")
    assert request_props.get("serialNumber") == req.get("serial_number")
    assert request_props.get("softwareRevision") == req.get("software_revision")

    # Defaults
    dp_defaults = {
        "publishingInterval": req.get("dp_publishing_interval", 1000),
        "samplingInterval": req.get("dp_sampling_interval", 500),
        "queueSize": req.get("dp_queue_size", 1)
    }
    assert request_props["defaultDataPointsConfiguration"] == json.dumps(dp_defaults)

    ev_defaults = {
        "publishingInterval": req.get("ev_publishing_interval", 1000),
        "samplingInterval": req.get("ev_sampling_interval", 500),
        "queueSize": req.get("ev_queue_size", 1)
    }
    assert request_props["defaultEventsConfiguration"] == json.dumps(ev_defaults)

    # Data points + events
    assert patched_dp.call_args[0][0] == req.get("data_points")
    assert request_props["dataPoints"] == patched_dp.return_value
    assert patched_ev.call_args[0][0] == req.get("events")
    assert request_props["events"] == patched_ev.return_value
