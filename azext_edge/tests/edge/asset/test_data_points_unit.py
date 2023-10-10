# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import json
import pytest

from azure.cli.core.azclierror import RequiredArgumentMissingError
from ....edge.commands_assets import (
    add_asset_data_point,
    list_asset_data_points,
    remove_asset_data_point
)
from . import (
    ASSETS_PATH,
    MINIMUM_ASSET,
    FULL_ASSET
)
from ...helpers import parse_rest_command
from ...generators import generate_generic_id


FULL_DATA_POINT = FULL_ASSET["properties"]["dataPoints"][0]


@pytest.mark.parametrize("embedded_cli_client", [{
    "path": ASSETS_PATH,
    "as_json_result": {"properties": {"dataPoints": {"result": generate_generic_id()}}}
}], ids=["cli"], indirect=True)
@pytest.mark.parametrize("show_asset_fixture", [MINIMUM_ASSET, FULL_ASSET], indirect=True)
@pytest.mark.parametrize("capability_id", [None, generate_generic_id()])
@pytest.mark.parametrize("name", [None, generate_generic_id()])
@pytest.mark.parametrize("observability_mode", [None, generate_generic_id()])
@pytest.mark.parametrize("queue_size", [None, 20])
@pytest.mark.parametrize("sampling_interval", [None, 33])
@pytest.mark.parametrize("resource_group_name", [None, generate_generic_id()])
def test_add_asset_data_point(
    mocked_cmd,
    embedded_cli_client,
    show_asset_fixture,
    capability_id,
    name,
    observability_mode,
    queue_size,
    sampling_interval,
    resource_group_name
):
    asset_name = generate_generic_id()
    data_source = generate_generic_id()
    result_data_points = add_asset_data_point(
        cmd=mocked_cmd,
        asset_name=asset_name,
        data_source=data_source,
        capability_id=capability_id,
        name=name,
        observability_mode=observability_mode,
        queue_size=queue_size,
        sampling_interval=sampling_interval,
        resource_group_name=resource_group_name
    )
    # Show
    show_asset, original_asset = show_asset_fixture
    assert show_asset.call_args.kwargs.get("resource_group_name") == resource_group_name

    # Asset changes
    assert result_data_points == next(embedded_cli_client.as_json.side_effect)["properties"]["dataPoints"]

    request = embedded_cli_client.invoke.call_args[0][-1]
    request_dict = parse_rest_command(request)
    assert request_dict["method"] == "PUT"
    assert f"{original_asset['id']}?api-version=" in request_dict["uri"]
    request_data_points = json.loads(request_dict["body"].strip("'"))["properties"]["dataPoints"]

    assert request_data_points[:-1] == original_asset["properties"]["dataPoints"]
    added_data_point = request_data_points[-1]
    assert added_data_point["capabilityId"] == (capability_id or name)
    assert added_data_point["name"] == name
    assert added_data_point["observabilityMode"] == observability_mode

    assert added_data_point["dataSource"] == data_source
    assert added_data_point["dataPointConfiguration"]
    assert "eventNotifier" not in added_data_point
    custom_configuration = json.loads(added_data_point["dataPointConfiguration"])
    assert custom_configuration.get("samplingInterval") == (
        sampling_interval if data_source else None
    )
    assert custom_configuration.get("queueSize") == (queue_size if data_source else None)


@pytest.mark.parametrize("show_asset_fixture", [MINIMUM_ASSET, FULL_ASSET], indirect=True)
@pytest.mark.parametrize("resource_group_name", [None, generate_generic_id()])
def test_list_asset_data_points(mocked_cmd, show_asset_fixture, resource_group_name):
    asset_name = generate_generic_id()
    result_obj = list_asset_data_points(
        cmd=mocked_cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name
    )
    # Show
    show_asset, original_asset = show_asset_fixture
    assert show_asset.call_args.kwargs.get("resource_group_name") == resource_group_name

    # Asset list
    assert result_obj == original_asset["properties"]["dataPoints"]


@pytest.mark.parametrize("embedded_cli_client", [{
    "path": ASSETS_PATH,
    "as_json_result": {"properties": {"dataPoints": {"result": generate_generic_id()}}}
}], ids=["cli"], indirect=True)
@pytest.mark.parametrize("show_asset_fixture", [FULL_ASSET], indirect=True)
@pytest.mark.parametrize("resource_group_name", [None, generate_generic_id()])
@pytest.mark.parametrize("data_source, name", [
    (FULL_DATA_POINT["dataSource"], FULL_DATA_POINT["name"]),
    (FULL_DATA_POINT["dataSource"], None),
    (None, FULL_DATA_POINT["name"]),
    (generate_generic_id(), generate_generic_id()),
    (generate_generic_id(), None),
    (None, generate_generic_id()),
])
def test_remove_asset_data_point(
    mocked_cmd, embedded_cli_client, show_asset_fixture, resource_group_name, data_source, name
):
    asset_name = generate_generic_id()
    result_obj = remove_asset_data_point(
        cmd=mocked_cmd,
        asset_name=asset_name,
        data_source=data_source,
        name=name,
        resource_group_name=resource_group_name
    )
    # show
    show_asset, original_asset = show_asset_fixture
    original_data_points = original_asset["properties"]["dataPoints"]
    assert show_asset.call_args.kwargs.get("resource_group_name") == resource_group_name

    assert result_obj == next(embedded_cli_client.as_json.side_effect)["properties"]["dataPoints"]

    # Asset changes
    request = embedded_cli_client.invoke.call_args[0][-1]
    request_body = parse_rest_command(request)["body"]
    request_data_points = json.loads(request_body.strip("'"))["properties"]["dataPoints"]
    if data_source == FULL_DATA_POINT["dataSource"] or name == FULL_DATA_POINT["name"]:
        assert len(request_data_points) + 1 == len(original_data_points)
        assert request_data_points == original_data_points[1:]
    else:
        assert request_data_points == original_data_points


@pytest.mark.parametrize("resource_group_name", [None, generate_generic_id()])
def test_remove_asset_data_point_error(mocked_cmd, resource_group_name):
    asset_name = generate_generic_id()
    with pytest.raises(RequiredArgumentMissingError) as e:
        remove_asset_data_point(
            cmd=mocked_cmd,
            asset_name=asset_name,
            resource_group_name=resource_group_name
        )
    assert e.value.error_msg == "Provide either the data source via --data-source or name via --name"\
        " to identify the data point to remove."
