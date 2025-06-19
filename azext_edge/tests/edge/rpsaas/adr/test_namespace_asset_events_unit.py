# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy
from random import randint
from typing import Optional
import pytest
import responses
import json

from azext_edge.edge.commands_namespaces import (
    add_namespace_custom_asset_event,
    add_namespace_onvif_asset_event,
    add_namespace_opcua_asset_event,
    list_namespace_asset_events,
    show_namespace_asset_event,
    remove_namespace_asset_event,
    update_namespace_custom_asset_event,
    update_namespace_onvif_asset_event,
    update_namespace_opcua_asset_event,
    add_namespace_custom_asset_event_point,
    add_namespace_onvif_asset_event_point,
    add_namespace_opcua_asset_event_point,
    list_namespace_asset_event_points,
    remove_namespace_asset_event_point
)
from .test_namespace_assets_unit import get_namespace_asset_mgmt_uri, get_namespace_asset_record
from ....generators import generate_random_string


def generate_event(event_name: Optional[str] = None, num_data_points: int = 0) -> dict:
    """Generate a mock event with the specified name and number of data points."""
    event = {
        "name": event_name or f"tev{generate_random_string(12)}",
        "eventNotifier": f"nsu=test;s=FastUInt{randint(1, 1000)}",
        "eventConfiguration": json.dumps(
            {
                "publishingInterval": randint(1, 10),
                "samplingInterval": randint(1, 10),
                "queueSize": randint(1, 10)
            }
        ),
        "destinations": [
            {
                "target": "Mqtt",
                "configuration": {
                    "topic": f"/contoso/{event_name}",
                    "retain": "Keep",
                    "qos": "Qos0",
                    "ttl": 7200
                }
            }
        ],
        "dataPoints": []
    }

    for i in range(num_data_points):
        data_point = {
            "name": f"{event_name}DataPoint{i + 1}",
            "dataSource": f"nsu=subtest;s=FastUInt{i + 1}",
            "dataPointConfiguration": json.dumps(
                {
                    "publishingInterval": randint(1, 10),
                    "samplingInterval": randint(1, 10),
                    "queueSize": randint(1, 10)
                }
            )
        }
        event["dataPoints"].append(data_point)

    return event


def test_add_namespace_custom_asset_event(mocked_cmd, mocked_responses: responses):
    pass


def test_add_namespace_onvif_asset_event(mocked_cmd, mocked_responses: responses):
    pass


def test_add_namespace_opcua_asset_event(mocked_cmd, mocked_responses: responses):
    pass


@pytest.mark.parametrize("num_events", [0, 1, 3])
@pytest.mark.parametrize("response_status", [200, 404])
def test_list_namespace_asset_events(
    mocked_cmd, mocked_responses: responses, num_events: int, response_status: int
):
    asset_name = "testAsset"
    namespace_name = "testNamespace"
    resource_group_name = "testResourceGroup"

    expected_events = [generate_event(num_data_points=randint(0, 2)) for _ in range(num_events)]
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    # ensure we can have the option of no event property
    if expected_events:
        mocked_asset["properties"]["events"] = expected_events

    mocked_responses.add(
        responses.GET,
        get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=mocked_asset,
        status=response_status
    )

    if response_status == 404:
        with pytest.raises(Exception):
            list_namespace_asset_events(
                cmd=mocked_cmd,
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name
            )
        return

    events = list_namespace_asset_events(
        cmd=mocked_cmd,
        resource_group_name=resource_group_name,
        namespace_name=namespace_name,
        asset_name=asset_name
    )
    assert len(events) == num_events
    expected_event_map = {event["name"]: event for event in expected_events}
    for event in events:
        assert event["name"] in expected_event_map
        expected_event = expected_event_map[event["name"]]
        assert event["eventNotifier"] == expected_event["eventNotifier"]
        assert event["eventConfiguration"] == expected_event["eventConfiguration"]
        assert event["destinations"] == expected_event["destinations"]

        # Check data points if any
        if "dataPoints" in expected_event:
            assert len(event.get("dataPoints", [])) == len(expected_event["dataPoints"])
            for dp in event.get("dataPoints", []):
                assert dp in expected_event["dataPoints"]


def test_show_namespace_asset_event(mocked_cmd, mocked_responses: responses):
    asset_name = "testAsset"
    namespace_name = "testNamespace"
    resource_group_name = "testResourceGroup"
    event_name = generate_random_string()

    expected_event = generate_event(event_name=event_name, num_data_points=randint(0, 2))
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
    mocked_asset["properties"]["events"] = [expected_event]

    mocked_responses.add(
        responses.GET,
        get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=mocked_asset,
        status=200
    )

    event = show_namespace_asset_event(
        cmd=mocked_cmd,
        resource_group_name=resource_group_name,
        namespace_name=namespace_name,
        asset_name=asset_name,
        event_name=event_name
    )
    assert event["name"] == expected_event["name"]
    assert event["eventNotifier"] == expected_event["eventNotifier"]
    assert event["eventConfiguration"] == expected_event["eventConfiguration"]
    assert event["destinations"] == expected_event["destinations"]

    # Check data points if any
    if "dataPoints" in expected_event:
        result_data_points = event.get("dataPoints", [])
        assert len(result_data_points) == len(expected_event["dataPoints"])
        expected_dp_map = {dp["name"]: dp for dp in expected_event["dataPoints"]}
        for dp in result_data_points:
            assert dp["name"] in expected_dp_map
            assert dp["dataSource"] == expected_dp_map[dp["name"]]["dataSource"]
            assert dp["dataPointConfiguration"] == expected_dp_map[dp["name"]]["dataPointConfiguration"]


# TODO
def test_show_namespace_asset_event_error(mocked_cmd, mocked_responses: responses):
    pass


@pytest.mark.parametrize("events_present", [True, False])
@pytest.mark.parametrize("event_deleted, response_status", [
    (True, 200),
    (True, 404),
    (False, 200)
])
def test_remove_namespace_asset_event(
    mocked_cmd,
    mocked_responses: responses,
    response_status: int,
    events_present: bool,
    event_deleted: bool,
    mocked_check_cluster_connectivity
):
    asset_name = "testAsset"
    namespace_name = "testNamespace"
    resource_group_name = "testResourceGroup"
    event_name = generate_random_string()

    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
    # make some other events, have the event prop there
    if events_present:
        mocked_asset["properties"]["events"] = [
            generate_event(num_data_points=randint(0, 2)),
            generate_event(num_data_points=randint(0, 2))
        ]
    expected_events = deepcopy(mocked_asset["properties"].get("events", []))
    # the remove should not fail even if the event is not there
    if event_deleted:
        mocked_asset["properties"]["events"] = mocked_asset["properties"].get("events", [])
        mocked_asset["properties"]["events"].append(
            generate_event(event_name=event_name, num_data_points=randint(0, 2))
        )

    mocked_responses.add(
        responses.GET,
        get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=mocked_asset,
        status=200
    )

    if event_deleted:
        mocked_responses.add(
            responses.PATCH,
            get_namespace_asset_mgmt_uri(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name
            ),
            json=mocked_asset,
            status=response_status
        )

    if response_status == 404:
        with pytest.raises(Exception):
            remove_namespace_asset_event(
                cmd=mocked_cmd,
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name,
                event_name=event_name,
                wait_sec=0
            )
        return

    result_events = remove_namespace_asset_event(
        cmd=mocked_cmd,
        resource_group_name=resource_group_name,
        namespace_name=namespace_name,
        asset_name=asset_name,
        event_name=event_name,
        wait_sec=0
    )

    # Verify result matches the mock updated namespace
    assert result_events == mocked_asset["properties"].get("events", [])

    # Verify API calls were made correctly
    assert len(mocked_responses.calls) == (2 if event_deleted else 1)
    assert mocked_responses.calls[0].request.method == "GET"
    if event_deleted:
        assert mocked_responses.calls[1].request.method == "PATCH"

        call_body = json.loads(mocked_responses.calls[1].request.body)
        call_events = call_body["properties"].get("events", [])
        expected_event_map = {event["name"]: event for event in expected_events}
        assert len(expected_events) == len(call_events)
        for event in call_events:
            assert event["name"] in expected_event_map
            expected_event = expected_event_map[event["name"]]
            assert event["eventNotifier"] == expected_event["eventNotifier"]
            assert event["eventConfiguration"] == expected_event["eventConfiguration"]
            assert event["destinations"] == expected_event["destinations"]


def test_update_namespace_custom_asset_event(
    mocked_cmd, mocked_responses: responses,
    mocked_check_cluster_connectivity
):
    pass


def test_update_namespace_onvif_asset_event(
    mocked_cmd, mocked_responses: responses,
    mocked_check_cluster_connectivity
):
    pass


def test_update_namespace_opcua_asset_event(
    mocked_cmd, mocked_responses: responses,
    mocked_check_cluster_connectivity
):
    pass


def test_add_namespace_custom_asset_event_point(
    mocked_cmd, mocked_responses: responses,
    mocked_check_cluster_connectivity
):
    pass


def test_add_namespace_onvif_asset_event_point(
    mocked_cmd, mocked_responses: responses,
    mocked_check_cluster_connectivity
):
    pass


def test_add_namespace_opcua_asset_event_point(
    mocked_cmd, mocked_responses: responses,
    mocked_check_cluster_connectivity
):
    pass


@pytest.mark.parametrize("num_points", [0, 1, 3])
@pytest.mark.parametrize("response_status", [200, 404])
def test_list_namespace_asset_event_points(
    mocked_cmd, mocked_responses: responses, num_points: int, response_status: int
):
    asset_name = "testAsset"
    namespace_name = "testNamespace"
    resource_group_name = "testResourceGroup"
    event_name = generate_random_string()

    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
    mocked_asset["properties"]["events"] = [generate_event(event_name=event_name, num_data_points=num_points)]
    expected_points = mocked_asset["properties"]["events"][0].get("dataPoints", [])

    mocked_responses.add(
        responses.GET,
        get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=mocked_asset,
        status=response_status
    )

    if response_status == 404:
        with pytest.raises(Exception):
            list_namespace_asset_event_points(
                cmd=mocked_cmd,
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name,
                event_name=event_name
            )
        return

    points = list_namespace_asset_event_points(
        cmd=mocked_cmd,
        resource_group_name=resource_group_name,
        namespace_name=namespace_name,
        asset_name=asset_name,
        event_name=event_name
    )
    assert len(points) == num_points
    expected_point_map = {point["name"]: point for point in expected_points}
    for point in points:
        assert point["name"] in expected_point_map
        expected_point = expected_point_map[point["name"]]
        assert point["dataSource"] == expected_point["dataSource"]
        assert point["dataPointConfiguration"] == expected_point["dataPointConfiguration"]


@pytest.mark.parametrize("points_present", [True, False])
@pytest.mark.parametrize("point_deleted, response_status", [
    (True, 200),
    (True, 404),
    (False, 200)
])
def test_remove_namespace_asset_event_point(
    mocked_cmd,
    mocked_responses: responses,
    response_status: int,
    points_present: bool,
    point_deleted: bool,
    mocked_check_cluster_connectivity
):
    asset_name = "testAsset"
    namespace_name = "testNamespace"
    resource_group_name = "testResourceGroup"
    event_name = generate_random_string()
    datapoint_name = generate_random_string()

    # Create mock asset with an event
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    # Create the event with or without datapoints
    event = generate_event(event_name=event_name)
    if points_present:
        # Add some other datapoints that should remain after deletion
        event["dataPoints"] = [
            {
                "name": f"otherDataPoint{i}",
                "dataSource": f"nsu=subtest;s=FastUInt{i}",
                "dataPointConfiguration": json.dumps(
                    {
                        "publishingInterval": randint(1, 10),
                        "samplingInterval": randint(1, 10),
                        "queueSize": randint(1, 10)
                    }
                )
            } for i in range(2)
        ]

    # Save the expected datapoints (the ones that should remain after deletion)
    expected_datapoints = deepcopy(event.get("dataPoints", []))

    # Add the datapoint to be deleted if needed for testing
    if point_deleted:
        event["dataPoints"].append({
            "name": datapoint_name,
            "dataSource": "nsu=subtest;s=ToBeDeleted",
            "dataPointConfiguration": json.dumps(
                {
                    "publishingInterval": randint(1, 10),
                    "samplingInterval": randint(1, 10),
                    "queueSize": randint(1, 10)
                }
            )
        })

    # Add the event to the asset
    mocked_asset["properties"]["events"] = [event]

    # Mock the GET request to get the asset
    mocked_responses.add(
        responses.GET,
        get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=mocked_asset,
        status=200
    )

    if point_deleted:
        # Mock the PATCH request to update the asset
        mocked_responses.add(
            responses.PATCH,
            get_namespace_asset_mgmt_uri(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name
            ),
            json=mocked_asset,
            status=response_status
        )

    if response_status == 404:
        with pytest.raises(Exception):
            remove_namespace_asset_event_point(
                cmd=mocked_cmd,
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name,
                event_name=event_name,
                datapoint_name=datapoint_name,
                wait_sec=0
            )
        return

    # Call the function being tested
    result = remove_namespace_asset_event_point(
        cmd=mocked_cmd,
        resource_group_name=resource_group_name,
        namespace_name=namespace_name,
        asset_name=asset_name,
        event_name=event_name,
        datapoint_name=datapoint_name,
        wait_sec=0
    )

    # Verify the result is the updated datapoints list
    assert result == mocked_asset["properties"]["events"][0].get("dataPoints", [])

    # Verify API calls were made correctly
    assert len(mocked_responses.calls) == (2 if point_deleted else 1)
    assert mocked_responses.calls[0].request.method == "GET"

    # If the point was deleted, there should be a PATCH request
    if point_deleted:
        assert mocked_responses.calls[1].request.method == "PATCH"

        # Verify the PATCH request body contains the expected datapoints
        patch_body = json.loads(mocked_responses.calls[1].request.body)
        patch_events = patch_body["properties"]["events"]
        assert len(patch_events) == 1

        # Find the event in the patch request
        patched_event = next((e for e in patch_events if e["name"] == event_name), None)
        assert patched_event is not None

        # Check that the datapoints in the patch request match the expected datapoints
        patched_datapoints = patched_event.get("dataPoints", [])

        # The datapoint that was supposed to be deleted should not be in the request
        for dp in patched_datapoints:
            assert dp["name"] != datapoint_name

        # All expected datapoints should be present
        assert len(patched_datapoints) == len(expected_datapoints)
        for dp in expected_datapoints:
            assert dp in patched_datapoints
