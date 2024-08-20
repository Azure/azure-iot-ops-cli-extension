# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, Optional
import json
import pytest
import responses

from azext_edge.edge.commands_assets import create_asset, delete_asset, list_assets, show_asset, update_asset

from .conftest import get_asset_mgmt_uri, get_asset_record
from ....generators import generate_random_string


@pytest.mark.parametrize("req", [
    {},
    {
        "custom_attributes": [generate_random_string()],
        "description": generate_random_string(),
        "display_name": generate_random_string(),
        "disabled": True,
        "documentation_uri": generate_random_string(),
        "events": generate_random_string(),
        "events_file_path": generate_random_string(),
        "external_asset_id": generate_random_string(),
        "hardware_revision": generate_random_string(),
        "instance_resource_group": generate_random_string(),
        "instance_subscription": generate_random_string(),
        "location": generate_random_string(),
        "manufacturer": generate_random_string(),
        "manufacturer_uri": generate_random_string(),
        "model": generate_random_string(),
        "product_code": generate_random_string(),
        "serial_number": generate_random_string(),
        "software_revision": generate_random_string(),
        "ds_publishing_interval": 3333,
        "ds_sampling_interval": 44,
        "ds_queue_size": 55,
        "ev_publishing_interval": 666,
        "ev_sampling_interval": 777,
        "ev_queue_size": 888,
        "tags": generate_random_string(),
    },
    {
        "instance_resource_group": generate_random_string(),
        "disabled": False,
        "events": generate_random_string(),
        "ds_publishing_interval": 3333,
        "ds_sampling_interval": 44,
        "ev_queue_size": 888,
    }
])
def test_asset_create(
    mocked_cmd,
    asset_helpers_fixture,
    mocked_get_extended_location,
    mocked_responses: responses,
    req: Dict[str, str]
):
    asset_name = generate_random_string()
    endpoint_profile = generate_random_string()
    resource_group_name = generate_random_string()
    instance_name = generate_random_string()

    mock_asset_record = get_asset_record(
        asset_name=asset_name, asset_resource_group=resource_group_name
    )
    mocked_responses.add(
        method=responses.PUT,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    result = create_asset(
        cmd=mocked_cmd,
        asset_name=asset_name,
        endpoint_profile=endpoint_profile,
        resource_group_name=resource_group_name,
        instance_name=instance_name,
        **req
    ).result()
    assert result == mock_asset_record
    call_body = json.loads(mocked_responses.calls[0].request.body)
    extended_location = mocked_get_extended_location.original_return_value
    assert call_body["extendedLocation"]["name"] == extended_location["name"]
    assert call_body["location"] == req.get("location", extended_location["cluster_location"])
    assert call_body["tags"] == req.get("tags")

    call_body_props = call_body["properties"]
    assert call_body_props["assetEndpointProfileRef"] == endpoint_profile

    patched_up = asset_helpers_fixture["update_properties"]
    req["disabled"] = req.get("disabled", False)
    req["ds_publishing_interval"] = req.get("ds_publishing_interval", 1000)
    req["ds_sampling_interval"] = req.get("ds_sampling_interval", 500)
    req["ds_queue_size"] = req.get("ds_queue_size", 1)
    req["ev_publishing_interval"] = req.get("ev_publishing_interval", 1000)
    req["ev_sampling_interval"] = req.get("ev_sampling_interval", 500)
    req["ev_queue_size"] = req.get("ev_queue_size", 1)
    assert call_body_props.get("defaultDataPointsConfiguration") is None
    assert call_body_props.get("defaultEventsConfiguration") is None
    for arg in patched_up.call_args.kwargs:
        assert patched_up.call_args.kwargs[arg] == req.get(arg)
        assert call_body_props.get(arg) is None

    mocked_get_extended_location.assert_called_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=req.get("instance_resource_group", resource_group_name),
        instance_subscription=req.get("instance_subscription")
    )
    assert asset_helpers_fixture["process_asset_sub_points_file_path"].called is bool(req.get("events_file_path"))


@pytest.mark.parametrize("discovered", [False, True])
def test_asset_delete(mocked_cmd, mocked_check_cluster_connectivity, mocked_responses: responses, discovered: bool):
    asset_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_asset_record = get_asset_record(
        asset_name=asset_name, asset_resource_group=resource_group_name, discovered=discovered
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json="" if discovered else mock_asset_record,
        status=404 if discovered else 200,
        content_type="application/json",
    )
    if discovered:
        mocked_responses.add(
            method=responses.GET,
            url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name, discovered=True),
            json=mock_asset_record,
            status=200,
            content_type="application/json",
        )
    mocked_responses.add(
        method=responses.DELETE,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name, discovered=discovered),
        status=202,
        content_type="application/json",
    )

    delete_asset(
        cmd=mocked_cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name,
    )
    assert len(mocked_responses.calls) == (3 if discovered else 2)


@pytest.mark.parametrize("discovered", [False, True])
@pytest.mark.parametrize("records", [0, 2])
@pytest.mark.parametrize("resource_group_name", [None, generate_random_string()])
def test_asset_list(
    mocked_cmd, mocked_responses: responses, discovered: bool, records: int, resource_group_name: Optional[str]
):
    mock_asset_records = {
        "value": [
            get_asset_record(
                asset_name=generate_random_string(),
                asset_resource_group=resource_group_name,
                discovered=discovered
            )
            for _ in range(records)
        ]
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_asset_mgmt_uri(
            asset_name="", asset_resource_group=resource_group_name, discovered=discovered
        ),
        json=mock_asset_records,
        status=200,
        content_type="application/json",
    )

    result = list(list_assets(cmd=mocked_cmd, resource_group_name=resource_group_name, discovered=discovered))
    assert result == mock_asset_records["value"]
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize("discovered", [False, True])
def test_asset_show(mocked_cmd, mocked_responses: responses, discovered: bool):
    asset_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_asset_record = get_asset_record(
        asset_name=asset_name, asset_resource_group=resource_group_name, discovered=discovered
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json="" if discovered else mock_asset_record,
        status=404 if discovered else 200,
        content_type="application/json",
    )
    if discovered:
        mocked_responses.add(
            method=responses.GET,
            url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name, discovered=True),
            json=mock_asset_record,
            status=200,
            content_type="application/json",
        )

    result = show_asset(
        cmd=mocked_cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name,
    )
    assert result == mock_asset_record
    assert len(mocked_responses.calls) == (2 if discovered else 1)


@pytest.mark.parametrize("req", [
    {},
    {
        "custom_attributes": [generate_random_string()],
        "description": generate_random_string(),
        "disabled": True,
        "display_name": generate_random_string(),
        "documentation_uri": generate_random_string(),
        "hardware_revision": generate_random_string(),
        "manufacturer": generate_random_string(),
        "manufacturer_uri": generate_random_string(),
        "model": generate_random_string(),
        "product_code": generate_random_string(),
        "serial_number": generate_random_string(),
        "software_revision": generate_random_string(),
        "ds_publishing_interval": 3333,
        "ds_sampling_interval": 44,
        "ds_queue_size": 55,
        "ev_publishing_interval": 666,
        "ev_sampling_interval": 777,
        "ev_queue_size": 888,
        "tags": generate_random_string(),
    },
    {
        "custom_attributes": [generate_random_string()],
        "disabled": False,
        "ds_publishing_interval": 3333,
        "ds_sampling_interval": 44,
        "ev_queue_size": 888,
    },
])
def test_asset_update(
    mocked_cmd,
    asset_helpers_fixture,
    mocked_check_cluster_connectivity,
    mocked_responses: responses,
    req: dict
):
    # use non discovered since delete shows the update_ops is selected correctly
    asset_name = generate_random_string()
    resource_group_name = generate_random_string()

    # make sure that the get vs patch have different results
    mock_original_asset = get_asset_record(asset_name=asset_name, asset_resource_group=resource_group_name)
    mock_asset_record = get_asset_record(
        asset_name=asset_name, asset_resource_group=resource_group_name, full=True
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json=mock_original_asset,
        status=200,
        content_type="application/json",
    )
    mocked_responses.add(
        method=responses.PUT,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    result = update_asset(
        cmd=mocked_cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name,
        **req
    ).result()
    assert result == mock_asset_record
    assert len(mocked_responses.calls) == 2
    call_body = json.loads(mocked_responses.calls[-1].request.body)
    assert call_body.get("tags") == req.get("tags", mock_original_asset.get("tags"))

    call_body_props = call_body["properties"]
    patched_up = asset_helpers_fixture["update_properties"]
    assert call_body_props.get("defaultDataPointsConfiguration") is None
    assert call_body_props.get("defaultEventsConfiguration") is None
    for arg in patched_up.call_args.kwargs:
        assert patched_up.call_args.kwargs[arg] == req.get(arg)
        assert call_body_props.get(arg) is None

