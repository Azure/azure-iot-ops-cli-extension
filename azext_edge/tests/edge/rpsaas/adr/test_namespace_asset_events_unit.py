# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy
from random import randint
from typing import Dict, Optional
import pytest
import responses
import json
from azure.cli.core.azclierror import InvalidArgumentValueError
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
    add_namespace_opcua_asset_event_point,
    list_namespace_asset_event_points,
    remove_namespace_asset_event_point
)

from .test_namespace_assets_unit import (
    get_namespace_asset_mgmt_uri, get_namespace_asset_record, add_device_get_call
)
from .namespace_helpers import check_event_configuration, check_destinations
from ....generators import generate_random_string


# note I am trying to minimize duplicate unit tests - so no response status code checks (already present for base asset)
# and no event not there checks (test_get_event_error does that)
def generate_event(
    event_name: Optional[str] = None, num_data_points: int = 0, event_configuration: Optional[str] = None
) -> dict:
    """Generate a mock event with the specified name and number of data points."""
    event_name = event_name or f"tev{generate_random_string(12)}"
    if not event_configuration:
        event_configuration = json.dumps({
            "publishingInterval": randint(1, 10),
            "samplingInterval": randint(1, 10),
            "queueSize": randint(1, 10)
        })
    event = {
        "name": event_name,
        "eventNotifier": f"nsu=test;s=FastUInt{randint(1, 1000)}",
        "eventConfiguration": event_configuration,
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
        "dataPoints": [
            {
                "name": f"{event_name}DataPoint{i + 1}",
                "dataSource": f"nsu=subtest;s=FastUInt{i + 1}",
                "dataPointConfiguration": json.dumps(
                    {
                        "publishingInterval": randint(1, 10),
                        "samplingInterval": randint(1, 10),
                        "queueSize": randint(1, 10)
                    }
                )
            } for i in range(num_data_points)
        ]
    }

    return event


@pytest.mark.parametrize("asset_type, command_func, config_params", [
    # Custom asset dataset with configuration
    ("custom", add_namespace_custom_asset_event, {
        "event_custom_configuration": json.dumps({
            "customSetting": "test",
            "priority": "high"
        })
    }),
    # Custom asset dataset with minimal config
    ("custom", add_namespace_custom_asset_event, {}),
    # OPCUA asset dataset with full parameters
    ("opcua", add_namespace_opcua_asset_event, {
        "opcua_event_publishing_interval": 1500,
        "opcua_event_queue_size": 100,
        "opcua_event_filter_type": "SimpleEvents",
        # filter clauses will be set in the test
    }),
    # OPCUA asset dataset with minimal config
    ("opcua", add_namespace_opcua_asset_event, {}),
    # ONVIF asset dataset with minimal config
    ("onvif", add_namespace_onvif_asset_event, {})
])
@pytest.mark.parametrize("destination_params", [
    {},  # No destinations
    # Single destination
    {
        "topic": "/contoso/events/test",
        "retain": "Keep",
        "qos": "Qos0",
        "ttl": 3600
    },
])
@pytest.mark.parametrize("has_previous_events, replace_event", [
    (False, False),  # No previous events, no replace
    (True, False),   # Has previous events, no replace
    (True, True)     # Has previous events, with replace
])
def test_add_namespace_asset_event(
    mocked_cmd,
    mocked_responses: responses,
    asset_type: str,
    command_func,
    config_params: dict,
    destination_params: Dict[str, str],
    has_previous_events: bool,
    replace_event: bool,
    mocked_check_cluster_connectivity
):
    asset_name = "testAsset"
    namespace_name = "testNamespace"
    resource_group_name = "testResourceGroup"
    event_name = f"testEvent{generate_random_string(5)}"
    event_notifier = f"nsu=test;s=FastUInt{randint(1, 1000)}"

    # Create the expected event
    expected_event = {
        "name": event_name,
        "eventNotifier": event_notifier,
        "dataPoints": []
    }

    config_params = deepcopy(config_params)
    # Add optional configuration parameters based on test case
    if config_params:
        if asset_type == "opcua":
            clause = {"path": "test", "type": "SimpleEvents", "field": "testField"}
            config_params["opcua_event_filter_clauses"] = [[
                f"{key}={value}" for key, value in clause.items()
            ]]
            expected_event["eventConfiguration"] = json.dumps({
                "publishingInterval": config_params["opcua_event_publishing_interval"],
                "queueSize": config_params["opcua_event_queue_size"],
                "eventFilter": {
                    "typeDefinitionId": config_params["opcua_event_filter_type"],
                    "selectClauses": [
                        {
                            "browsePath": clause["path"],
                            "typeDefinitionId": clause["type"],
                            "fieldId": clause["field"]
                        }
                    ]
                }
            })
        elif asset_type == "custom":
            expected_event["eventConfiguration"] = config_params.get("event_custom_configuration")

    # Add optional destination parameters based on test case
    if destination_params:
        dest = {}
        if "topic" in destination_params:
            dest = {"target": "Mqtt", "configuration": destination_params}
        expected_event["destinations"] = [dest]
        config_params["event_destinations"] = [f"{key}={value}" for key, value in dest["configuration"].items()]

    # Generate mock asset
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
    add_device_get_call(
        mocked_responses,
        resource_group_name=resource_group_name,
        namespace_name=namespace_name,
        device_name=mocked_asset["properties"]["deviceRef"]["deviceName"],
        endpoint_name=mocked_asset["properties"]["deviceRef"]["endpointName"],
        endpoint_type=asset_type
    )

    # Add previous events if needed for the test case
    if has_previous_events:
        # Add 2 existing events
        mocked_asset["properties"]["events"] = [
            generate_event(num_data_points=randint(0, 2)) for _ in range(2)
        ]

        # If testing replace, add an event with the same name to be replaced
        if replace_event:
            mocked_asset["properties"]["events"].append(generate_event(event_name=event_name))

    # Mock GET request to get the asset
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

    # Create updated asset for mock response
    updated_asset = deepcopy(mocked_asset)
    updated_asset["properties"]["events"] = updated_asset["properties"].get("events", [])

    # If replacing, keep only non-matching events
    if replace_event:
        updated_asset["properties"]["events"] = [
            e for e in mocked_asset["properties"]["events"] if e["name"] != event_name
        ]

    updated_asset["properties"]["events"].append(expected_event)

    # Mock PATCH request
    mocked_responses.add(
        responses.PATCH,
        get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=updated_asset,
        status=200
    )

    # Call the function being tested
    result = command_func(
        cmd=mocked_cmd,
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        event_name=event_name,
        event_notifier=event_notifier,
        replace=replace_event,
        wait_sec=0,
        **config_params
    )

    # Verify the result matches the event we added
    assert result == expected_event

    # Verify API calls were made correctly
    assert len(mocked_responses.calls) == 3
    assert mocked_responses.calls[0].request.method == "GET"
    assert mocked_responses.calls[1].request.method == "GET"
    assert mocked_responses.calls[2].request.method == "PATCH"

    # Verify the PATCH request body contains the expected event structure
    patch_body = json.loads(mocked_responses.calls[2].request.body)

    # Events should be in the properties section
    assert "events" in patch_body["properties"]
    events = patch_body["properties"]["events"]

    # Count should match expected
    assert len(events) == len(updated_asset["properties"]["events"])

    # Find our event in the list
    added_event = next((e for e in events if e["name"] == event_name), None)
    assert added_event is not None, "Added event not found in the list of events"
    assert added_event["eventNotifier"] == event_notifier

    # Check configuration and destinations using helper functions
    check_event_configuration(added_event, expected_event)
    check_destinations(added_event, expected_event)

    # Verify all other events are preserved
    event_map = {e["name"]: e for e in updated_asset["properties"].get("events", [])}
    for event in events:
        assert event["name"] in event_map, f"Event {event['name']} not found in updated asset"


@pytest.mark.parametrize("asset_type, command_func", [
    ("custom", add_namespace_custom_asset_event),
    ("opcua", add_namespace_opcua_asset_event),
    ("onvif", add_namespace_onvif_asset_event)
])
def test_add_namespace_asset_event_error(
    mocked_cmd,
    mocked_responses: responses,
    asset_type: str,
    command_func,
    mocked_check_cluster_connectivity
):
    """Test error cases for adding asset events with different asset types.

    Tests the following scenarios:
    - Mismatch between asset type and device endpoint type
    - Event exists but replace flag not set
    """
    asset_name = "testAsset"
    namespace_name = "testNamespace"
    resource_group_name = "testResourceGroup"
    event_name = f"testEvent{generate_random_string(5)}"
    event_notifier = f"nsu=test;s=FastUInt{randint(1, 1000)}"

    # Create base parameters for all test cases
    base_params = {
        "cmd": mocked_cmd,
        "resource_group_name": resource_group_name,
        "namespace_name": namespace_name,
        "asset_name": asset_name,
        "event_name": event_name,
        "event_notifier": event_notifier,
        "wait_sec": 0
    }

    # Generate mock asset
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
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

    if asset_type != "custom":
        # 1st do the device endpoint type mismatch
        # use media since it is not a valid type for opcua/onvif
        add_device_get_call(
            mocked_responses,
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            device_name=mocked_asset["properties"]["deviceRef"]["deviceName"],
            endpoint_name=mocked_asset["properties"]["deviceRef"]["endpointName"],
            endpoint_type="media"
        )

        with pytest.raises(InvalidArgumentValueError) as excinfo:
            command_func(**base_params)

        assert f" is of type 'microsoft.media', but expected 'microsoft.{asset_type}'." in str(excinfo.value).lower()

    mocked_responses.reset()

    # replace device call with valid asset type
    add_device_get_call(
        mocked_responses,
        resource_group_name=resource_group_name,
        namespace_name=namespace_name,
        device_name=mocked_asset["properties"]["deviceRef"]["deviceName"],
        endpoint_name=mocked_asset["properties"]["deviceRef"]["endpointName"],
        endpoint_type=asset_type
    )

    # 2nd do event already exists
    existing_event = {
        "name": event_name,
        "eventNotifier": f"nsu=existing;s=FastUInt{randint(1, 1000)}",
        "eventConfiguration": json.dumps({"existingConfig": "value"}),
        "destinations": [
            {
                "target": "Mqtt",
                "configuration": {
                    "topic": "/contoso/existing",
                    "retain": "Never",
                    "qos": "Qos0",
                    "ttl": 3600
                }
            }
        ],
        "dataPoints": []
    }
    mocked_asset["properties"]["events"] = [existing_event]

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

    with pytest.raises(InvalidArgumentValueError) as excinfo:
        command_func(**base_params)

    assert f"Event '{event_name}' already exists in asset '{asset_name}'. " in str(excinfo.value)


@pytest.mark.parametrize("num_events", [0, 1, 3])
def test_list_namespace_asset_events(
    mocked_cmd, mocked_responses: responses, num_events: int
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
        status=200
    )

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


@pytest.mark.parametrize("events_present", [True, False])
@pytest.mark.parametrize("event_deleted", [True, False])
def test_remove_namespace_asset_event(
    mocked_cmd,
    mocked_responses: responses,
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
        # Mock the PATCH request to update the asset
        updated_asset = deepcopy(mocked_asset)
        updated_asset["properties"]["events"] = expected_events
        mocked_responses.add(
            responses.PATCH,
            get_namespace_asset_mgmt_uri(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name
            ),
            json=updated_asset,
            status=200
        )

    result_events = remove_namespace_asset_event(
        cmd=mocked_cmd,
        resource_group_name=resource_group_name,
        namespace_name=namespace_name,
        asset_name=asset_name,
        event_name=event_name,
        wait_sec=0
    )

    # Verify result matches the mock updated namespace
    assert result_events == expected_events

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


@pytest.mark.parametrize("common_reqs", [
    # No specific common requirements
    {},
    # With event notifier
    {"event_notifier": "nsu=test5;s=FastUInt999"},
    # both notifier and event configuration
    {
        "event_destinations": "",  # will be set in the test
        "event_notifier": "nsu=test3;s=FastUInt999",
    }
])
@pytest.mark.parametrize("asset_type, command_func, unique_reqs", [
    # Custom asset event
    ("custom", update_namespace_custom_asset_event, {}),
    # Custom asset event
    ("custom", update_namespace_custom_asset_event, {
        "event_custom_configuration": json.dumps({
            "customSetting": "updated",
            "priority": "critical"
        })
    }),
    # OPCUA asset event - note that there are more unit tests for ensuring opcua event schemas
    # get updated correctly. This is just a simple test to ensure the command works
    ("opcua", update_namespace_opcua_asset_event, {
        "opcua_event_publishing_interval": 2000,
        "opcua_event_queue_size": 10,
        "opcua_event_filter_type": "WhereClause"
        # filter clauses will be set in the test
    }),
    # ONVIF asset event
    ("onvif", update_namespace_onvif_asset_event, {})
])
def test_update_namespace_asset_event(
    mocked_cmd,
    mocked_responses: responses,
    asset_type: str,
    command_func,
    common_reqs: dict,
    unique_reqs: dict,
    mocked_check_cluster_connectivity
):
    asset_name = "testAsset"
    namespace_name = "testNamespace"
    resource_group_name = "testResourceGroup"
    event_name = f"testEvent{generate_random_string(5)}"

    # Generate mock asset with the event already in it
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    # device call
    add_device_get_call(
        mocked_responses,
        resource_group_name=resource_group_name,
        namespace_name=namespace_name,
        device_name=mocked_asset["properties"]["deviceRef"]["deviceName"],
        endpoint_name=mocked_asset["properties"]["deviceRef"]["endpointName"],
        endpoint_type=asset_type
    )

    # add some random events
    mocked_asset["properties"]["events"] = [
        {
            "name": f"tev{generate_random_string(12)}",
            "eventNotifier": f"nsu=test;s=FastUInt{randint(1, 1000)}",
            "destinations": [],
            "eventConfiguration": "{}",
            "dataPoints": []
        } for _ in range(randint(0, 3))
    ]

    # Create the initial event
    initial_event = generate_event(event_name=event_name, num_data_points=randint(0, 2), event_configuration="{}")

    # add in initial event to the end for ease
    mocked_asset["properties"]["events"].append(initial_event)

    # Mock GET request to get the asset
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

    # Create the expected updated event
    expected_event = deepcopy(initial_event)

    # Update notifier if specified
    if "event_notifier" in common_reqs:
        expected_event["eventNotifier"] = common_reqs["event_notifier"]

    # Update configuration if specified
    if unique_reqs:
        if asset_type == "custom":
            expected_event["eventConfiguration"] = unique_reqs["event_custom_configuration"]
        elif asset_type == "opcua":
            clause = {"path": "test", "type": "SimpleEvents", "field": "testField"}
            unique_reqs["opcua_event_filter_clauses"] = [[
                f"{key}={value}" for key, value in clause.items()
            ]]
            expected_event["eventConfiguration"] = json.dumps({
                "publishingInterval": unique_reqs.get("opcua_event_publishing_interval"),
                "queueSize": unique_reqs.get("opcua_event_queue_size"),
                "eventFilter": {
                    "typeDefinitionId": unique_reqs.get("opcua_event_filter_type"),
                    "selectClauses": [
                        {
                            "browsePath": clause["path"],
                            "typeDefinitionId": clause["type"],
                            "fieldId": clause["field"]
                        }
                    ]
                }
            })

    # Update destinations if specified
    if "event_destinations" in common_reqs:
        destination = {
            "target": "Mqtt",
            "configuration": {
                "topic": "/contoso/events/updated",
                "retain": "Keep",
                "qos": "Qos1",
                "ttl": randint(1, 60)  # Random TTL for testing
            }
        }
        expected_event["destinations"] = [destination]
        common_reqs["event_destinations"] = [
            f"{key}={value}" for key, value in destination["configuration"].items()
        ]

    # Create updated asset for mock response
    updated_asset = deepcopy(mocked_asset)
    updated_asset["properties"]["events"] = [expected_event]

    # Mock PATCH request
    mocked_responses.add(
        responses.PATCH,
        get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=updated_asset,
        status=200
    )

    # Call the function being tested
    result = command_func(
        cmd=mocked_cmd,
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        event_name=event_name,
        wait_sec=0,
        **common_reqs,
        **unique_reqs,
    )

    assert result == expected_event

    # Verify API calls were made correctly
    assert len(mocked_responses.calls) == 3
    assert mocked_responses.calls[0].request.method == "GET"
    assert mocked_responses.calls[1].request.method == "GET"
    assert mocked_responses.calls[2].request.method == "PATCH"

    # Verify the PATCH request body contains the expected updated event
    patch_body = json.loads(mocked_responses.calls[2].request.body)

    events = patch_body["properties"]["events"]
    assert len(events) == len(mocked_asset["properties"]["events"])

    # Get the updated event
    patch_event = events[-1]

    # Check basic event properties
    assert patch_event["name"] == event_name

    # Check notifier update if applicable
    assert patch_event["eventNotifier"] == expected_event["eventNotifier"]

    # Check configuration and destinations using helper functions
    check_event_configuration(patch_event, expected_event)
    check_destinations(patch_event, expected_event)

    # Check data points preservation
    assert len(patch_event["dataPoints"]) == len(initial_event["dataPoints"])
    for i, dp in enumerate(patch_event["dataPoints"]):
        assert dp["name"] == initial_event["dataPoints"][i]["name"]
        assert dp["dataSource"] == initial_event["dataPoints"][i]["dataSource"]


@pytest.mark.parametrize("asset_type, command_func, config_params", [
    # Custom asset event point with custom configuration
    (
        "custom",
        add_namespace_custom_asset_event_point,
        {"custom_configuration": json.dumps({"customSetting": "value", "priority": "high"})}
    ),
    # Custom asset event point without custom configuration
    (
        "custom",
        add_namespace_custom_asset_event_point,
        {}
    ),
    # OPCUA asset event point with all parameters
    (
        "opcua",
        add_namespace_opcua_asset_event_point,
        {"queue_size": 10, "sampling_interval": 500}
    ),
    # OPCUA asset event point with minimal parameters
    (
        "opcua",
        add_namespace_opcua_asset_event_point,
        {}
    )
])
@pytest.mark.parametrize("has_points, replace", [
    (False, False),  # No previous points, no replace
    (True, False),   # Has previous points, no replace
    (True, True)     # Has previous points, with replace
])
def test_add_namespace_asset_event_point(
    mocked_cmd,
    mocked_responses: responses,
    asset_type: str,
    command_func,
    config_params: dict,
    has_points: bool,
    replace: bool,
    mocked_check_cluster_connectivity
):
    # Setup test variables
    asset_name = "testAsset"
    namespace_name = "testNamespace"
    resource_group_name = "testResourceGroup"
    event_name = f"testEvent{generate_random_string(5)}"
    datapoint_name = f"testPoint{generate_random_string(5)}"
    data_source = f"nsu=test;s=Point{randint(1, 1000)}"

    # Generate mock asset with an event
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    # Create the event within the asset
    event = generate_event(
        event_name=event_name, num_data_points=randint(1, 3) if has_points else 0
    )

    # add in point to replace
    if replace:
        event["dataPoints"].append({
            "name": datapoint_name,
            "dataSource": f"nsu=test;s=SameName{randint(1, 1000)}",
            "dataPointConfiguration": json.dumps({  # since replace should remove old point, we can have any config
                "publishingInterval": 2000,
                "samplingInterval": 1000,
                "queueSize": 5
            })
        })

    # Add the event to the asset properties
    mocked_asset["properties"]["events"] = [event]

    # Mock the device endpoint check
    add_device_get_call(
        mocked_responses,
        resource_group_name=resource_group_name,
        namespace_name=namespace_name,
        device_name=mocked_asset["properties"]["deviceRef"]["deviceName"],
        endpoint_name=mocked_asset["properties"]["deviceRef"]["endpointName"],
        endpoint_type=asset_type
    )

    # Mock GET request to get the asset
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

    # Create the expected data point
    expected_datapoint = {
        "name": datapoint_name,
        "dataSource": data_source
    }

    # Add configuration based on asset type
    if asset_type == "custom" and "custom_configuration" in config_params:
        expected_datapoint["dataPointConfiguration"] = config_params["custom_configuration"]
    elif asset_type == "opcua":
        config = {}
        if "queue_size" in config_params:
            config["queueSize"] = config_params["queue_size"]
        if "sampling_interval" in config_params:
            config["samplingInterval"] = config_params["sampling_interval"]
        if config:
            expected_datapoint["dataPointConfiguration"] = json.dumps(config)

    # Create the updated asset for the mock response
    updated_asset = deepcopy(mocked_asset)
    updated_event = updated_asset["properties"]["events"][0]
    updated_event["dataPoints"] = updated_event.get("dataPoints", [])
    if replace:
        # If replacing, remove the existing point with the same name
        updated_event["dataPoints"] = [
            dp for dp in updated_event["dataPoints"] if dp["name"] != datapoint_name
        ]

    updated_event["dataPoints"].append(expected_datapoint)

    # Mock PATCH request
    mocked_responses.add(
        responses.PATCH,
        get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=updated_asset,
        status=200
    )

    result = command_func(
        cmd=mocked_cmd,
        resource_group_name=resource_group_name,
        namespace_name=namespace_name,
        asset_name=asset_name,
        event_name=event_name,
        datapoint_name=datapoint_name,
        data_source=data_source,
        replace=replace,
        wait_sec=0,
        **config_params
    )

    # result should be a list of datapoints from the patch response
    assert isinstance(result, list)
    assert result == updated_asset["properties"]["events"][0]["dataPoints"]

    # Verify API calls were made correctly
    assert len(mocked_responses.calls) == 3  # GET device + GET asset + PATCH asset
    assert mocked_responses.calls[0].request.method == "GET"  # Device GET call
    assert mocked_responses.calls[1].request.method == "GET"  # Asset GET call
    assert mocked_responses.calls[2].request.method == "PATCH"  # Asset PATCH call

    # Verify the PATCH request payload contains the expected data point
    patch_body = json.loads(mocked_responses.calls[2].request.body)
    patch_event = patch_body["properties"]["events"][0]
    assert len(patch_event["dataPoints"]) == len(updated_event["dataPoints"])

    # check the added datapoint
    patched_point = next((p for p in patch_event["dataPoints"] if p["name"] == datapoint_name), None)
    assert patched_point is not None, f"Data point '{datapoint_name}' not found in PATCH request"
    assert patched_point["dataSource"] == data_source
    assert patched_point["dataPointConfiguration"] == expected_datapoint.get("dataPointConfiguration", "{}")


@pytest.mark.parametrize("num_points", [0, 1, 3])
def test_list_namespace_asset_event_points(
    mocked_cmd, mocked_responses: responses, num_points: int
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
        status=200
    )

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
@pytest.mark.parametrize("point_deleted", [True, False])
def test_remove_namespace_asset_event_point(
    mocked_cmd,
    mocked_responses: responses,
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
        updated_asset = deepcopy(mocked_asset)
        updated_event = updated_asset["properties"]["events"][0]
        updated_event["dataPoints"] = expected_datapoints

        mocked_responses.add(
            responses.PATCH,
            get_namespace_asset_mgmt_uri(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name
            ),
            json=updated_asset,
            status=200
        )

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
    assert result == expected_datapoints

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
