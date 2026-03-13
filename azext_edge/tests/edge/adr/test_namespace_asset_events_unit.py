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
    add_namespace_custom_asset_event_group,
    add_namespace_onvif_asset_event_group,
    add_namespace_opcua_asset_event_group,
    add_namespace_sse_asset_event_group,
    list_namespace_asset_event_groups,
    show_namespace_asset_event_group,
    remove_namespace_asset_event_group,
    update_namespace_custom_asset_event_group,
    update_namespace_onvif_asset_event_group,
    update_namespace_opcua_asset_event_group,
    update_namespace_sse_asset_event_group,
    add_namespace_custom_asset_event_group_event,
    add_namespace_onvif_asset_event_group_event,
    add_namespace_opcua_asset_event_group_event,
    add_namespace_sse_asset_event_group_event,
    list_namespace_asset_event_group_events,
    remove_namespace_asset_event_group_event
)

from .test_namespace_assets_unit import (
    get_namespace_asset_mgmt_uri, get_namespace_asset_record, add_device_get_call
)
from .namespace_helpers import check_event_configuration, check_destinations
from ...generators import generate_random_string


# note I am trying to minimize duplicate unit tests - so no response status code checks (already present for base asset)
# and no event not there checks (test_get_event_error does that)
def generate_event_group(
    group_name: Optional[str] = None,
    num_data_points: int = 0,
    event_configuration: Optional[str] = None,
    data_source: Optional[str] = None,
) -> dict:
    """Generate a mock event group with the specified name and number of data points."""
    group_name = group_name or f"tev{generate_random_string(12)}"
    if not event_configuration:
        event_configuration = json.dumps({
            "publishingInterval": randint(1, 10),
            "samplingInterval": randint(1, 10),
            "queueSize": randint(1, 10)
        })
    return {
        "name": group_name,
        "dataSource": data_source or f"nsu=test;s=FastUInt{randint(1, 1000)}",
        "eventGroupConfiguration": event_configuration,
        "defaultDestinations": [
            {
                "target": "Mqtt",
                "configuration": {
                    "topic": f"/contoso/{group_name}",
                    "retain": "Keep",
                    "qos": "Qos0",
                    "ttl": 7200
                }
            }
        ],
        "events": [
            {
                "name": f"{group_name}DataPoint{i + 1}",
                "dataSource": f"nsu=subtest;s=FastUInt{i + 1}",
                "eventConfiguration": json.dumps(
                    {
                        "publishingInterval": randint(1, 10),
                        "samplingInterval": randint(1, 10),
                        "queueSize": randint(1, 10)
                    }
                )
            } for i in range(num_data_points)
        ],
        "typeRef": None
    }


@pytest.mark.parametrize("asset_type, command_func, config_params", [
    # Custom asset dataset with configuration
    ("custom", add_namespace_custom_asset_event_group, {
        "event_custom_configuration": json.dumps({
            "customSetting": "test",
            "priority": "high"
        }),
        "type_ref": f"myevent{randint(0, 100)}"
    }),
    # Custom asset dataset with minimal config
    ("custom", add_namespace_custom_asset_event_group, {}),
    # OPCUA asset dataset with full parameters
    ("opcua", add_namespace_opcua_asset_event_group, {
        "opcua_event_publishing_interval": 1500,
        "opcua_event_queue_size": 100,
    }),
    # OPCUA asset dataset with minimal config
    ("opcua", add_namespace_opcua_asset_event_group, {}),
    # ONVIF asset dataset with minimal config
    ("onvif", add_namespace_onvif_asset_event_group, {}),
    # SSE asset event group with minimal config (event-driven, no sampling intervals)
    ("sse", add_namespace_sse_asset_event_group, {})
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
@pytest.mark.parametrize("data_source", [
    None,
    f"nsu=test;s=FastUInt{randint(1, 1000)}",
])
def test_add_namespace_asset_event_group(
    mocked_cmd,
    mocked_responses: responses,
    asset_type: str,
    command_func,
    config_params: dict,
    destination_params: Dict[str, str],
    has_previous_events: bool,
    replace_event: bool,
    data_source: Optional[str],
    mocked_check_cluster_connectivity,
    mocked_get_namespace_for_instance
):
    asset_name = "testAsset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"
    group_name = f"testEvent{generate_random_string(5)}"

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

    # Create the expected event
    expected_group = generate_event_group(group_name=group_name, data_source=data_source)
    expected_group["defaultDestinations"] = []  # start with no destinations
    expected_group["eventGroupConfiguration"] = "{}"  # start with no config
    expected_group["typeRef"] = config_params.get("type_ref")

    config_params = deepcopy(config_params)
    # Add optional configuration parameters based on test case
    if config_params:
        if asset_type == "opcua":
            opcua_config = {}
            if "opcua_event_publishing_interval" in config_params:
                opcua_config["publishingInterval"] = config_params["opcua_event_publishing_interval"]
            if "opcua_event_queue_size" in config_params:
                opcua_config["queueSize"] = config_params["opcua_event_queue_size"]
            expected_group["eventGroupConfiguration"] = json.dumps(opcua_config)
        elif asset_type == "custom":
            expected_group["eventGroupConfiguration"] = config_params.get("event_custom_configuration")

    # Add optional destination parameters based on test case
    if destination_params:
        dest = {}
        if "topic" in destination_params:
            dest = {"target": "Mqtt", "configuration": destination_params}
        expected_group["defaultDestinations"] = [dest]
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

    # Add previous event group if needed for the test case
    if has_previous_events:
        # Add 2 existing events
        mocked_asset["properties"]["eventGroups"] = [
            generate_event_group(num_data_points=randint(0, 2)) for _ in range(2)
        ]

        # If testing replace, add an event with the same name to be replaced
        if replace_event:
            mocked_asset["properties"]["eventGroups"].append(generate_event_group(group_name=group_name))

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
    updated_asset["properties"]["eventGroups"] = updated_asset["properties"].get("eventGroups", [])

    # If replacing, keep only non-matching eventGroups
    if replace_event:
        updated_asset["properties"]["eventGroups"] = [
            e for e in mocked_asset["properties"]["eventGroups"] if e["name"] != group_name
        ]

    updated_asset["properties"]["eventGroups"].append(expected_group)

    # Mock PATCH request
    mocked_responses.add(
        responses.PATCH,
        get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        status=200
    )

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        ),
        json=updated_asset,
        status=200,
        content_type="application/json",
    )

    # Call the function being tested
    result = command_func(
        cmd=mocked_cmd,
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        data_source=data_source,
        replace=replace_event,
        wait_sec=0,
        **config_params
    )

    # Verify the result matches the event we added
    assert result == expected_group

    # Verify API calls were made correctly
    assert len(mocked_responses.calls) == 4
    assert mocked_responses.calls[0].request.method == "GET"
    assert mocked_responses.calls[1].request.method == "GET"
    assert mocked_responses.calls[2].request.method == "PATCH"
    assert mocked_responses.calls[3].request.method == "GET"

    # Verify the PATCH request body contains the expected event structure
    patch_body = json.loads(mocked_responses.calls[2].request.body)

    # Events should be in the properties section
    assert "eventGroups" in patch_body["properties"]
    groups = patch_body["properties"]["eventGroups"]

    # Count should match expected
    assert len(groups) == len(updated_asset["properties"]["eventGroups"])

    # Find our event in the list
    added_group = next((e for e in groups if e["name"] == group_name), None)
    assert added_group is not None, "Added event group not found in the list of event groups"
    if data_source:
        assert added_group["dataSource"] == data_source
    else:
        assert "dataSource" not in added_group
    assert added_group["typeRef"] == expected_group["typeRef"]

    # Check configuration and destinations using helper functions
    check_event_configuration(added_group, expected_group)
    check_destinations(added_group, expected_group, default=True)

    # Verify all other events are preserved
    group_map = {e["name"]: e for e in updated_asset["properties"].get("eventGroups", [])}
    for group in groups:
        assert group["name"] in group_map, f"Event {group['name']} not found in updated asset"

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


@pytest.mark.parametrize("asset_type, command_func", [
    ("custom", add_namespace_custom_asset_event_group),
    ("opcua", add_namespace_opcua_asset_event_group),
    ("onvif", add_namespace_onvif_asset_event_group)
])
def test_add_namespace_asset_event_group_error(
    mocked_cmd,
    mocked_responses: responses,
    asset_type: str,
    command_func,
    mocked_check_cluster_connectivity,
    mocked_get_namespace_for_instance
):
    """Test error cases for adding asset events with different asset types.

    Tests the following scenarios:
    - Mismatch between asset type and device endpoint type
    - Event exists but replace flag not set
    """
    asset_name = "testAsset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"
    group_name = f"testEvent{generate_random_string(5)}"
    data_source = f"nsu=test;s=FastUInt{randint(1, 1000)}"

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

    # Create base parameters for all test cases
    base_params = {
        "cmd": mocked_cmd,
        "instance_name": instance_name,
        "instance_resource_group": instance_resource_group,
        "asset_name": asset_name,
        "group_name": group_name,
        "data_source": data_source,
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
    mocked_asset["properties"]["eventGroups"] = [generate_event_group(group_name=group_name, num_data_points=0)]

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

    assert f"Event group '{group_name}' already exists in asset '{asset_name}'. " in str(excinfo.value)

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


@pytest.mark.parametrize("num_events", [0, 1, 3])
def test_list_namespace_asset_event_groups(
    mocked_cmd, mocked_responses: responses, num_events: int, mocked_get_namespace_for_instance
):
    asset_name = "testAsset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

    expected_groups = [generate_event_group(num_data_points=randint(0, 2)) for _ in range(num_events)]
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    # ensure we can have the option of no event property
    if expected_groups:
        mocked_asset["properties"]["eventGroups"] = expected_groups

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

    events = list_namespace_asset_event_groups(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        asset_name=asset_name
    )
    assert len(events) == num_events
    expected_group_map = {event["name"]: event for event in expected_groups}
    for event in events:
        assert event["name"] in expected_group_map
        expected_group = expected_group_map[event["name"]]
        assert event["dataSource"] == expected_group["dataSource"]
        assert event["eventGroupConfiguration"] == expected_group["eventGroupConfiguration"]
        assert event["defaultDestinations"] == expected_group["defaultDestinations"]

        # Check events if any
        if "events" in expected_group:
            assert len(event.get("events", [])) == len(expected_group["events"])
            for dp in event.get("events", []):
                assert dp in expected_group["events"]

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


def test_show_namespace_asset_event_group(
    mocked_cmd, mocked_responses: responses, mocked_get_namespace_for_instance
):
    asset_name = "testAsset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"
    group_name = generate_random_string()

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

    expected_group = generate_event_group(group_name=group_name, num_data_points=randint(0, 2))
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
    mocked_asset["properties"]["eventGroups"] = [expected_group]

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

    event = show_namespace_asset_event_group(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        asset_name=asset_name,
        group_name=group_name
    )
    assert event["name"] == expected_group["name"]
    assert event["dataSource"] == expected_group["dataSource"]
    assert event["eventGroupConfiguration"] == expected_group["eventGroupConfiguration"]
    assert event["defaultDestinations"] == expected_group["defaultDestinations"]

    # Check data points if any
    if "events" in expected_group:
        result_data_points = event.get("events", [])
        assert len(result_data_points) == len(expected_group["events"])
        expected_dp_map = {dp["name"]: dp for dp in expected_group["events"]}
        for dp in result_data_points:
            assert dp["name"] in expected_dp_map
            assert dp["dataSource"] == expected_dp_map[dp["name"]]["dataSource"]
            assert dp["eventConfiguration"] == expected_dp_map[dp["name"]]["eventConfiguration"]

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


@pytest.mark.parametrize("groups_present", [True, False])
@pytest.mark.parametrize("group_deleted", [True, False])
def test_remove_namespace_asset_event_group(
    mocked_cmd,
    mocked_responses: responses,
    groups_present: bool,
    group_deleted: bool,
    mocked_check_cluster_connectivity,
    mocked_get_namespace_for_instance
):
    asset_name = "testAsset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"
    group_name = generate_random_string()

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
    # make some other eventGroups, have the event prop there
    if groups_present:
        mocked_asset["properties"]["eventGroups"] = [
            generate_event_group(num_data_points=randint(0, 2)),
            generate_event_group(num_data_points=randint(0, 2))
        ]
    expected_groups = deepcopy(mocked_asset["properties"].get("eventGroups", []))
    # the remove should not fail even if the event is not there
    if group_deleted:
        mocked_asset["properties"]["eventGroups"] = mocked_asset["properties"].get("eventGroups", [])
        mocked_asset["properties"]["eventGroups"].append(
            generate_event_group(group_name=group_name, num_data_points=randint(0, 2))
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

    if group_deleted:
        # Mock the PATCH request to update the asset
        updated_asset = deepcopy(mocked_asset)
        updated_asset["properties"]["eventGroups"] = expected_groups
        mocked_responses.add(
            responses.PATCH,
            get_namespace_asset_mgmt_uri(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name
            ),
            status=200
        )

        mocked_responses.add(
            method=responses.GET,
            url=get_namespace_asset_mgmt_uri(
                asset_name=asset_name,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name
            ),
            json=updated_asset,
            status=200,
            content_type="application/json",
        )

    result_events = remove_namespace_asset_event_group(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        asset_name=asset_name,
        group_name=group_name,
        wait_sec=0
    )

    # Verify result matches the mock updated namespace
    assert result_events == expected_groups

    # Verify API calls were made correctly
    assert len(mocked_responses.calls) == (3 if group_deleted else 1)
    assert mocked_responses.calls[0].request.method == "GET"
    if group_deleted:
        assert mocked_responses.calls[1].request.method == "PATCH"
        assert mocked_responses.calls[2].request.method == "GET"

        call_body = json.loads(mocked_responses.calls[1].request.body)
        call_groups = call_body["properties"].get("eventGroups", [])
        expected_group_map = {event["name"]: event for event in expected_groups}
        assert len(expected_groups) == len(call_groups)
        for group in call_groups:
            assert group["name"] in expected_group_map
            expected_group = expected_group_map[group["name"]]
            assert group["dataSource"] == expected_group["dataSource"]
            assert group["eventGroupConfiguration"] == expected_group["eventGroupConfiguration"]
            assert group["defaultDestinations"] == expected_group["defaultDestinations"]

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


@pytest.mark.parametrize("common_reqs", [
    # No specific common requirements
    {},
    # With event notifier
    {"data_source": "nsu=other5;s=Int1000"},
    # both notifier and event configuration
    {
        "event_destinations": "",  # will be set in the test
        "data_source": "nsu=other3;s=Int1000",
    }
])
@pytest.mark.parametrize("asset_type, command_func, unique_reqs", [
    # Custom asset event
    ("custom", update_namespace_custom_asset_event_group, {}),
    # Custom asset event
    ("custom", update_namespace_custom_asset_event_group, {
        "event_custom_configuration": json.dumps({
            "customSetting": "updated",
            "priority": "critical"
        }),
        "type_ref": f"myevent{randint(0, 100)}"
    }),
    # OPCUA asset event - note that there are more unit tests for ensuring opcua event schemas
    # get updated correctly. This is just a simple test to ensure the command works
    ("opcua", update_namespace_opcua_asset_event_group, {
        "opcua_event_publishing_interval": 2000,
        "opcua_event_queue_size": 10,
    }),
    # ONVIF asset event
    ("onvif", update_namespace_onvif_asset_event_group, {}),
    # SSE asset event group (event-driven, no sampling intervals)
    ("sse", update_namespace_sse_asset_event_group, {})
])
def test_update_namespace_asset_event_group(
    mocked_cmd,
    mocked_responses: responses,
    asset_type: str,
    command_func,
    common_reqs: dict,
    unique_reqs: dict,
    mocked_check_cluster_connectivity,
    mocked_get_namespace_for_instance
):
    asset_name = "testAsset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"
    group_name = f"testEvent{generate_random_string(5)}"

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

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

    # add some random groups
    mocked_asset["properties"]["eventGroups"] = [
        generate_event_group() for _ in range(randint(0, 3))
    ]

    # Create the initial event
    initial_event = generate_event_group(
        group_name=group_name, num_data_points=randint(0, 2), event_configuration="{}"
    )

    # add in initial event to the end for ease
    mocked_asset["properties"]["eventGroups"].append(initial_event)

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
    expected_group = deepcopy(initial_event)

    # Update notifier if specified
    if "data_source" in common_reqs:
        expected_group["dataSource"] = common_reqs["data_source"]

    # Update configuration if specified
    if unique_reqs:
        if asset_type == "custom":
            expected_group["eventGroupConfiguration"] = unique_reqs["event_custom_configuration"]
            expected_group["typeRef"] = unique_reqs.get("type_ref")
        elif asset_type == "opcua":
            opcua_config = {}
            if "opcua_event_publishing_interval" in unique_reqs:
                opcua_config["publishingInterval"] = unique_reqs.get("opcua_event_publishing_interval")
            if "opcua_event_queue_size" in unique_reqs:
                opcua_config["queueSize"] = unique_reqs.get("opcua_event_queue_size")
            expected_group["eventGroupConfiguration"] = json.dumps(opcua_config)

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
        expected_group["defaultDestinations"] = [destination]
        common_reqs["event_destinations"] = [
            f"{key}={value}" for key, value in destination["configuration"].items()
        ]

    # Create updated asset for mock response
    updated_asset = deepcopy(mocked_asset)
    updated_asset["properties"]["eventGroups"] = [expected_group]

    # Mock PATCH request
    mocked_responses.add(
        responses.PATCH,
        get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        status=200
    )

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        ),
        json=updated_asset,
        status=200,
        content_type="application/json",
    )

    # Call the function being tested
    result = command_func(
        cmd=mocked_cmd,
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        wait_sec=0,
        **common_reqs,
        **unique_reqs,
    )

    assert result == expected_group

    # Verify API calls were made correctly
    assert len(mocked_responses.calls) == 4
    assert mocked_responses.calls[0].request.method == "GET"
    assert mocked_responses.calls[1].request.method == "GET"
    assert mocked_responses.calls[2].request.method == "PATCH"
    assert mocked_responses.calls[3].request.method == "GET"

    # Verify the PATCH request body contains the expected updated event
    patch_body = json.loads(mocked_responses.calls[2].request.body)

    groups = patch_body["properties"]["eventGroups"]
    assert len(groups) == len(mocked_asset["properties"]["eventGroups"])

    # Get the updated event
    patch_group = groups[-1]

    # Check basic event properties
    assert patch_group["name"] == group_name

    # Check notifier update if applicable
    assert patch_group["dataSource"] == expected_group["dataSource"]
    assert patch_group.get("typeRef") == expected_group.get("typeRef")

    # Check configuration and destinations using helper functions
    check_event_configuration(patch_group, expected_group)
    check_destinations(patch_group, expected_group)

    # Check event preservation
    assert len(patch_group["events"]) == len(initial_event["events"])
    for i, ev in enumerate(patch_group["events"]):
        assert ev["name"] == initial_event["events"][i]["name"]
        assert ev["dataSource"] == initial_event["events"][i]["dataSource"]

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


@pytest.mark.parametrize("asset_type, command_func, config_params", [
    # Custom asset event point with custom configuration
    (
        "custom",
        add_namespace_custom_asset_event_group_event,
        {
            "custom_configuration": json.dumps({"customSetting": "value", "priority": "high"}),
            "type_ref": f"myevent{randint(0, 100)}"
        }
    ),
    # Custom asset event point without custom configuration
    (
        "custom",
        add_namespace_custom_asset_event_group_event,
        {}
    ),
    # OPCUA asset event point with all parameters
    (
        "opcua",
        add_namespace_opcua_asset_event_group_event,
        {"queue_size": 10, "sampling_interval": 500}
    ),
    # OPCUA asset event point with minimal parameters
    (
        "opcua",
        add_namespace_opcua_asset_event_group_event,
        {}
    ),
    # ONVIF asset event with minimal parameters
    (
        "onvif",
        add_namespace_onvif_asset_event_group_event,
        {}
    ),
    # ONVIF asset event with data source and type_ref
    (
        "onvif",
        add_namespace_onvif_asset_event_group_event,
        {"type_ref": f"onvif{randint(0, 100)}"}
    ),
    # SSE asset event point with event destinations (event-driven, no sampling intervals)
    (
        "sse",
        add_namespace_sse_asset_event_group_event,
        {
            "event_destinations": ["topic=factory/sse/events", "qos=Qos1", "retain=Keep", "ttl=3600"],
            "type_ref": f"sseevent{randint(0, 100)}"
        }
    ),
    # SSE asset event point with minimal parameters (event-driven)
    (
        "sse",
        add_namespace_sse_asset_event_group_event,
        {}
    )
])
@pytest.mark.parametrize("has_points, replace", [
    (False, False),  # No previous points, no replace
    (True, False),   # Has previous points, no replace
    (True, True)     # Has previous points, with replace
])
@pytest.mark.parametrize("data_source", [
    None,
    f"nsu=test;s=Point{randint(1, 1000)}",
])
def test_add_namespace_asset_event_group_event(
    mocked_cmd,
    mocked_responses: responses,
    asset_type: str,
    command_func,
    config_params: dict,
    has_points: bool,
    replace: bool,
    data_source: Optional[str],
    mocked_check_cluster_connectivity,
    mocked_get_namespace_for_instance
):
    # Setup test variables
    asset_name = "testAsset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"
    group_name = f"testEvent{generate_random_string(5)}"
    event_name = f"testPoint{generate_random_string(5)}"

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

    # Generate mock asset with an event
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    # Create the event within the asset
    group = generate_event_group(
        group_name=group_name, num_data_points=randint(1, 3) if has_points else 0
    )

    # add in point to replace
    if replace:
        group["events"].append({
            "name": event_name,
            "dataSource": f"nsu=test;s=SameName{randint(1, 1000)}",
            "eventConfiguration": json.dumps({  # since replace should remove old point, we can have any config
                "publishingInterval": 2000,
                "samplingInterval": 1000,
                "queueSize": 5
            })
        })

    # Add the event to the asset properties
    mocked_asset["properties"]["eventGroups"] = [group]

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
    expected_event = {
        "name": event_name,
    }
    if data_source:
        expected_event["dataSource"] = data_source

    # Add configuration based on asset type
    if asset_type == "custom" and "custom_configuration" in config_params:
        expected_event["eventConfiguration"] = config_params["custom_configuration"]
        expected_event["typeRef"] = config_params.get("type_ref")
    elif asset_type == "opcua":
        config = {}
        if "queue_size" in config_params:
            config["queueSize"] = config_params["queue_size"]
        if "sampling_interval" in config_params:
            config["samplingInterval"] = config_params["sampling_interval"]
        if config:
            expected_event["eventConfiguration"] = json.dumps(config)
    elif asset_type == "onvif":
        # ONVIF events support type_ref; no configuration schema
        expected_event["typeRef"] = config_params.get("type_ref")
        expected_event["eventConfiguration"] = "{}"
    elif asset_type == "sse":
        # SSE events support type_ref and event destinations
        expected_event["typeRef"] = config_params.get("type_ref")
        # SSE uses empty eventConfiguration since it's event-driven
        expected_event["eventConfiguration"] = "{}"

    # Create the updated asset for the mock response
    updated_asset = deepcopy(mocked_asset)
    updated_group = updated_asset["properties"]["eventGroups"][0]
    updated_group["events"] = updated_group.get("events", [])
    if replace:
        # If replacing, remove the existing point with the same name
        updated_group["events"] = [
            dp for dp in updated_group["events"] if dp["name"] != event_name
        ]

    updated_group["events"].append(expected_event)

    # Mock PATCH request
    mocked_responses.add(
        responses.PATCH,
        get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        status=200
    )

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        ),
        json=updated_asset,
        status=200,
        content_type="application/json",
    )

    result = command_func(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        asset_name=asset_name,
        group_name=group_name,
        event_name=event_name,
        data_source=data_source,
        replace=replace,
        wait_sec=0,
        **config_params
    )

    # result should be a list of events from the patch response
    assert isinstance(result, list)
    assert result == updated_asset["properties"]["eventGroups"][0]["events"]

    # Verify API calls were made correctly
    assert len(mocked_responses.calls) == 4  # GET device + GET asset + PATCH asset + GET asset
    assert mocked_responses.calls[0].request.method == "GET"  # Device GET call
    assert mocked_responses.calls[1].request.method == "GET"  # Asset GET call
    assert mocked_responses.calls[2].request.method == "PATCH"  # Asset PATCH call
    assert mocked_responses.calls[3].request.method == "GET"  # Asset GET call

    # Verify the PATCH request payload contains the expected data point
    patch_body = json.loads(mocked_responses.calls[2].request.body)
    patch_group = patch_body["properties"]["eventGroups"][0]
    assert len(patch_group["events"]) == len(updated_group["events"])

    # check the added datapoint
    patched_event = next((p for p in patch_group["events"] if p["name"] == event_name), None)
    assert patched_event is not None, f"Data point '{event_name}' not found in PATCH request"
    if data_source:
        assert patched_event["dataSource"] == data_source
    else:
        assert "dataSource" not in patched_event
    assert patched_event.get("typeRef") == expected_event.get("typeRef")
    assert patched_event["eventConfiguration"] == expected_event.get("eventConfiguration", "{}")

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


@pytest.mark.parametrize("num_events", [0, 1, 3])
def test_list_namespace_asset_event_group_events(
    mocked_cmd, mocked_responses: responses, num_events: int, mocked_get_namespace_for_instance
):
    asset_name = "testAsset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"
    group_name = generate_random_string()

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
    mocked_asset["properties"]["eventGroups"] = [
        generate_event_group(group_name=group_name, num_data_points=num_events)
    ]
    expected_events = mocked_asset["properties"]["eventGroups"][0].get("events", [])

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

    events = list_namespace_asset_event_group_events(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        asset_name=asset_name,
        group_name=group_name
    )
    assert len(events) == num_events
    expected_event_map = {event["name"]: event for event in expected_events}
    for ev in events:
        assert ev["name"] in expected_event_map
        expected_event = expected_event_map[ev["name"]]
        assert ev["dataSource"] == expected_event["dataSource"]
        assert ev["eventConfiguration"] == expected_event["eventConfiguration"]

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


@pytest.mark.parametrize("events_present", [True, False])
@pytest.mark.parametrize("event_deleted", [True, False])
def test_remove_namespace_asset_event_group_event(
    mocked_cmd,
    mocked_responses: responses,
    events_present: bool,
    event_deleted: bool,
    mocked_check_cluster_connectivity,
    mocked_get_namespace_for_instance
):
    asset_name = "testAsset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"
    group_name = generate_random_string()
    event_name = generate_random_string()

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

    # Create mock asset with an group
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    # Create the group with or without events
    group = generate_event_group(group_name=group_name)
    if events_present:
        # Add some other events that should remain after deletion
        group["events"] = [
            {
                "name": f"otherDataPoint{i}",
                "dataSource": f"nsu=subtest;s=FastUInt{i}",
                "eventConfiguration": json.dumps(
                    {
                        "publishingInterval": randint(1, 10),
                        "samplingInterval": randint(1, 10),
                        "queueSize": randint(1, 10)
                    }
                )
            } for i in range(2)
        ]

    # Save the expected events (the ones that should remain after deletion)
    expected_events = deepcopy(group.get("events", []))

    # Add the datapoint to be deleted if needed for testing
    if event_deleted:
        group["events"].append({
            "name": event_name,
            "dataSource": "nsu=subtest;s=ToBeDeleted",
            "eventConfiguration": json.dumps(
                {
                    "publishingInterval": randint(1, 10),
                    "samplingInterval": randint(1, 10),
                    "queueSize": randint(1, 10)
                }
            )
        })

    # Add the group to the asset
    mocked_asset["properties"]["eventGroups"] = [group]

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

    if event_deleted:
        # Mock the PATCH request to update the asset
        updated_asset = deepcopy(mocked_asset)
        updated_event = updated_asset["properties"]["eventGroups"][0]
        updated_event["events"] = expected_events

        mocked_responses.add(
            responses.PATCH,
            get_namespace_asset_mgmt_uri(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name
            ),
            status=200
        )

        mocked_responses.add(
            method=responses.GET,
            url=get_namespace_asset_mgmt_uri(
                asset_name=asset_name,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name
            ),
            json=updated_asset,
            status=200,
            content_type="application/json",
        )

    # Call the function being tested
    result = remove_namespace_asset_event_group_event(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        asset_name=asset_name,
        group_name=group_name,
        event_name=event_name,
        wait_sec=0
    )

    # Verify the result is the updated datapoints list
    assert result == expected_events

    # Verify API calls were made correctly
    assert len(mocked_responses.calls) == (3 if event_deleted else 1)
    assert mocked_responses.calls[0].request.method == "GET"

    # If the point was deleted, there should be a PATCH request
    if event_deleted:
        assert mocked_responses.calls[1].request.method == "PATCH"
        assert mocked_responses.calls[2].request.method == "GET"

        # Verify the PATCH request body contains the expected datapoints
        patch_body = json.loads(mocked_responses.calls[1].request.body)
        patch_events = patch_body["properties"]["eventGroups"]
        assert len(patch_events) == 1

        # Check that the datapoints in the patch request match the expected datapoints
        patched_events = patch_events[0].get("events", [])

        # The datapoint that was supposed to be deleted should not be in the request
        for dp in patched_events:
            assert dp["name"] != event_name

        # All expected datapoints should be present
        assert len(patched_events) == len(expected_events)
        for dp in expected_events:
            assert dp in patched_events

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )
