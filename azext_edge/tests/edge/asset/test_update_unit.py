# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import json
import pytest

from azext_edge.edge.commands_assets import update_asset

from . import (
    ASSETS_PATH,
    MINIMUM_ASSET,
    FULL_ASSET
)
from ...helpers import parse_rest_command
from ...generators import generate_generic_id


@pytest.mark.parametrize("embedded_cli_client", [{
    "path": ASSETS_PATH,
    "as_json_result": {"result": generate_generic_id()}
}], ids=["cli"], indirect=True)
@pytest.mark.parametrize("show_asset_fixture", [MINIMUM_ASSET, FULL_ASSET], indirect=True)
@pytest.mark.parametrize("asset_helpers_fixture", [{
    "process_asset_sub_points": generate_generic_id(),
    "update_properties": generate_generic_id(),
}], ids=["update helpers"], indirect=True)
@pytest.mark.parametrize("req", [
    {},
    {
        "resource_group_name": generate_generic_id(),
        "asset_type": generate_generic_id(),
        "data_points": generate_generic_id(),
        "description": generate_generic_id(),
        "disabled": True,
        "documentation_uri": generate_generic_id(),
        "events": generate_generic_id(),
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
    mocker, mocked_cmd, embedded_cli_client, show_asset_fixture, asset_helpers_fixture, req
):
    patched_sp, patched_up = asset_helpers_fixture
    # Required params
    asset_name = generate_generic_id()
    result = update_asset(
        cmd=mocked_cmd,
        asset_name=asset_name,
        **req
    )

    show_asset, original_asset = show_asset_fixture
    assert show_asset.call_args.kwargs.get("resource_group_name") == req.get("resource_group_name")
    assert result == next(embedded_cli_client.as_json.side_effect)

    request = embedded_cli_client.invoke.call_args[0][-1]
    request_dict = parse_rest_command(request)
    assert request_dict["method"] == "PUT"

    assert f"{original_asset['id']}?api-version=" in request_dict["uri"]

    # Check update request
    request_body = json.loads(request_dict["body"].strip("'"))
    assert request_body["location"] == original_asset["location"]
    assert request_body["extendedLocation"] == original_asset["extendedLocation"]
    assert request_body.get("tags") == req.get("tags", original_asset.get("tags"))

    # Properties
    request_props = request_body["properties"]
    original_props = original_asset["properties"]
    assert request_props["connectivityProfileUri"] == original_props["connectivityProfileUri"]

    # Check that update props mock got called correctly
    assert request_props["result"]
    assert request_props.get("defaultDataPointsConfiguration") is None
    assert request_props.get("defaultEventsConfiguration") is None
    for arg in patched_up.call_args.kwargs:
        assert patched_up.call_args.kwargs[arg] == req.get(arg)
        assert request_props.get(arg) is None

    # Data points + events
    if req.get("data_points"):
        assert patched_sp.call_args_list[0].args[0] == "data_source"
        assert patched_sp.call_args_list[0].args[1] == req["data_points"]
        assert request_props["dataPoints"] == patched_sp.return_value
    else:
        assert request_props["dataPoints"] == original_props["dataPoints"]

    if req.get("events"):
        assert patched_sp.call_args_list[-1].args[0] == "event_notifier"
        assert patched_sp.call_args_list[-1].args[1] == req["events"]
        assert request_props["events"] == patched_sp.return_value
    else:
        assert request_props["events"] == original_props["events"]
