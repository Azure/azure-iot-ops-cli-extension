# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import pytest

from azure.cli.core.azclierror import RequiredArgumentMissingError
from azext_edge.edge.commands_assets import (
    add_asset_data_point,
    list_asset_data_points,
    remove_asset_data_point
)
from azext_edge.edge.providers.rpsaas.adr.base import ADR_API_VERSION

from .conftest import (
    MINIMUM_ASSET,
    FULL_ASSET
)
from .....generators import generate_generic_id


FULL_EVENT = FULL_ASSET["properties"]["dataPoints"][0]


@pytest.mark.parametrize("mocked_resource_management_client", [
    {
        "resources.get": MINIMUM_ASSET,
        "resources.begin_create_or_update_by_id": {
            "properties": {"dataPoints": {"result": generate_generic_id()}}
        }
    },
    {
        "resources.get": FULL_ASSET,
        "resources.begin_create_or_update_by_id": {
            "properties": {"dataPoints": {"result": generate_generic_id()}}
        }
    },
], ids=["minimal", "full"], indirect=True)
@pytest.mark.parametrize("capability_id", [None, generate_generic_id()])
@pytest.mark.parametrize("name", [None, generate_generic_id()])
@pytest.mark.parametrize("observability_mode", [None, generate_generic_id()])
@pytest.mark.parametrize("queue_size", [None, 20])
@pytest.mark.parametrize("sampling_interval", [None, 33])
def test_add_asset_data_point(
    mocked_cmd,
    mock_check_cluster_connectivity,
    mocked_resource_management_client,
    capability_id,
    name,
    observability_mode,
    queue_size,
    sampling_interval,
):
    asset_name = generate_generic_id()
    resource_group_name = generate_generic_id()
    data_source = generate_generic_id()
    result_events = add_asset_data_point(
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
    mocked_resource_management_client.resources.get.assert_called_once()
    mocked_resource_management_client.resources.begin_create_or_update_by_id.assert_called_once()
    original_asset = mocked_resource_management_client.resources.get.return_value.original
    poller = mocked_resource_management_client.resources.begin_create_or_update_by_id.return_value
    expected_asset = poller.result()
    assert result_events == expected_asset["properties"]["dataPoints"]

    # Asset changes
    call_kwargs = mocked_resource_management_client.resources.begin_create_or_update_by_id.call_args.kwargs
    assert call_kwargs["resource_id"] == original_asset["id"]
    assert call_kwargs["api_version"] == ADR_API_VERSION

    # Check update request
    request_data_points = call_kwargs["parameters"]["properties"]["dataPoints"]

    assert request_data_points[:-1] == original_asset["properties"].get("dataPoints", [])
    added_event = request_data_points[-1]
    assert added_event["capabilityId"] == (capability_id or name)
    assert added_event["name"] == name
    assert added_event["observabilityMode"] == observability_mode

    assert added_event["dataSource"] == data_source
    assert added_event["dataPointConfiguration"]
    assert "eventNotifier" not in added_event
    custom_configuration = json.loads(added_event["dataPointConfiguration"])
    assert custom_configuration.get("samplingInterval") == (
        sampling_interval if data_source else None
    )
    assert custom_configuration.get("queueSize") == (queue_size if data_source else None)


@pytest.mark.parametrize("mocked_resource_management_client", [
    {"resources.get": MINIMUM_ASSET},
    {"resources.get": FULL_ASSET},
], ids=["minimal", "full"], indirect=True)
def test_list_asset_data_points(mocked_cmd, mocked_resource_management_client):
    asset_name = generate_generic_id()
    resource_group_name = generate_generic_id()
    result_events = list_asset_data_points(
        cmd=mocked_cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name
    )
    mocked_resource_management_client.resources.get.assert_called_once()
    original_asset = mocked_resource_management_client.resources.get.return_value.as_dict.return_value
    assert result_events == original_asset["properties"].get("dataPoints", [])


@pytest.mark.parametrize("mocked_resource_management_client", [
    {
        "resources.get": FULL_ASSET,
        "resources.begin_create_or_update_by_id": {
            "properties": {"dataPoints": {"result": generate_generic_id()}}
        }
    },
], ids=["full"], indirect=True)
@pytest.mark.parametrize("data_source, name", [
    (FULL_EVENT["dataSource"], FULL_EVENT["name"]),
    (FULL_EVENT["dataSource"], None),
    (None, FULL_EVENT["name"]),
    (generate_generic_id(), generate_generic_id()),
    (generate_generic_id(), None),
    (None, generate_generic_id()),
])
def test_remove_asset_data_point(
    mocked_cmd,
    mock_check_cluster_connectivity,
    mocked_resource_management_client,
    data_source,
    name
):
    asset_name = generate_generic_id()
    resource_group_name = generate_generic_id()
    result_events = remove_asset_data_point(
        cmd=mocked_cmd,
        asset_name=asset_name,
        data_source=data_source,
        name=name,
        resource_group_name=resource_group_name
    )
    mocked_resource_management_client.resources.get.assert_called_once()
    mocked_resource_management_client.resources.begin_create_or_update_by_id.assert_called_once()
    original_asset = mocked_resource_management_client.resources.get.return_value.original
    poller = mocked_resource_management_client.resources.begin_create_or_update_by_id.return_value
    expected_asset = poller.result()
    assert result_events == expected_asset["properties"]["dataPoints"]

    # Asset changes
    call_kwargs = mocked_resource_management_client.resources.begin_create_or_update_by_id.call_args.kwargs
    assert call_kwargs["resource_id"] == original_asset["id"]
    assert call_kwargs["api_version"] == ADR_API_VERSION

    # Check update request
    request_data_points = call_kwargs["parameters"]["properties"]["dataPoints"]
    original_events = original_asset["properties"]["dataPoints"]

    if data_source == FULL_EVENT["dataSource"] or name == FULL_EVENT["name"]:
        assert len(request_data_points) + 1 == len(original_events)
        assert request_data_points == original_events[1:]
    else:
        assert request_data_points == original_events


def test_remove_asset_data_point_error(mocked_cmd):
    with pytest.raises(RequiredArgumentMissingError) as e:
        remove_asset_data_point(
            cmd=mocked_cmd,
            asset_name=generate_generic_id(),
            resource_group_name=generate_generic_id()
        )
    assert e.value.error_msg == "Provide either the data source via --data-source or name via "\
        "--data-point-name to identify the data point to remove."
