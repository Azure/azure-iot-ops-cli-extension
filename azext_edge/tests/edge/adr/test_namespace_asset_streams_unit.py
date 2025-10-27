# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
import responses
import json
from copy import deepcopy
from random import randint
from typing import Optional
from azure.cli.core.azclierror import InvalidArgumentValueError
from azext_edge.edge.commands_namespaces import (
    add_namespace_custom_asset_stream,
    add_namespace_media_asset_stream,
    list_namespace_asset_streams,
    show_namespace_asset_stream,
    remove_namespace_asset_stream,
    update_namespace_custom_asset_stream,
    update_namespace_media_asset_stream,
)

from .test_namespace_assets_unit import (
    add_device_get_call, get_namespace_asset_mgmt_uri, get_namespace_asset_record
)
from .namespace_helpers import check_destinations, check_stream_configuration
from ...generators import generate_random_string


def generate_stream(
    stream_name: Optional[str] = None,
    stream_configuration: Optional[str] = None,
    asset_type: str = "custom"
) -> dict:
    """Generate a mock stream with the specified name and configuration."""
    stream_name = stream_name or f"stream{generate_random_string(12)}"

    if not stream_configuration:
        if asset_type == "media":
            # Generate media stream configuration
            stream_configuration = json.dumps({
                "taskType": "snapshot-to-mqtt",
                "autostart": True,
                "format": "jpeg",
                "snapshotsPerSecond": randint(1, 10)
            })
        else:
            # Generate custom stream configuration
            stream_configuration = json.dumps({
                "customProperty": f"value{randint(1, 100)}",
                "streamType": "sensor-data"
            })

    stream = {
        "name": stream_name,
        "streamConfiguration": stream_configuration,
        "destinations": [
            {
                "target": "Mqtt",
                "configuration": {
                    "topic": f"/contoso/streams/{stream_name}",
                    "retain": "Keep",
                    "qos": "Qos1",
                    "ttl": 3600
                }
            }
        ]
    }

    return stream


@pytest.mark.parametrize("asset_type, command_func, stream_params", [
    # Custom asset stream tests
    (
        "custom",
        add_namespace_custom_asset_stream,
        {
            "stream_custom_configuration": json.dumps({"customProperty": "testValue", "streamType": "sensor-data"}),
            "type_ref": f"custom.stream{randint(0, 1000)}"
        },
    ),
    # Media asset stream tests - snapshot-to-mqtt
    (
        "media",
        add_namespace_media_asset_stream,
        {
            "task_type": "snapshot-to-mqtt",
            "disable_autostart": True,
            "task_format": "jpeg",
            "snapshots_per_second": 2
        },
    ),
    # Media asset stream tests - snapshot-to-fs
    (
        "media",
        add_namespace_media_asset_stream,
        {
            "task_type": "snapshot-to-fs",
            "task_format": "png",
            "snapshots_per_second": 1,
            "path": "/tmp/snapshots"
        },
    ),
    # Media asset stream tests - clip-to-fs
    (
        "media",
        add_namespace_media_asset_stream,
        {
            "task_type": "clip-to-fs",
            "disable_autostart": False,
            "task_format": "mp4",
            "duration": 30,
            "path": "/tmp/clips"
        },
    ),
    # Media asset stream tests - stream-to-rtsp
    (
        "media",
        add_namespace_media_asset_stream,
        {
            "task_type": "stream-to-rtsp",
            "disable_autostart": True,
            "media_server_address": "192.168.1.100",
            "media_server_port": 554,
            "media_server_path": "/live/stream1",
            "media_server_username": "user",
            "media_server_password": "pass"
        },
    ),
    # Media asset stream tests - stream-to-rtsps
    (
        "media",
        add_namespace_media_asset_stream,
        {
            "task_type": "stream-to-rtsps",
            "disable_autostart": False,
            "media_server_address": "secure.example.com",
            "media_server_port": 322,
            "media_server_path": "/secure/stream",
            "media_server_username": "secureuser",
            "media_server_password": "securepass",
            "media_server_certificate": "cert-content"
        },
    ),
])
@pytest.mark.parametrize("has_previous_streams, replace_stream", [
    (False, False),  # No previous streams, do not replace
    (True, False),  # Previous streams exist, replace
    (True, True)     # Previous streams exist, replace
])
@pytest.mark.parametrize("destination_params", [
    {},
    {
        "topic": "/contoso/events/test",
        "retain": "Keep",
        "qos": "Qos0",
        "ttl": 3600
    },
    {
        "path": "/data/streams",
    },
])
def test_add_namespace_asset_stream(
    mocked_cmd,
    mocked_responses: responses,
    asset_type: str,
    command_func,
    stream_params: dict,
    destination_params: dict,
    has_previous_streams: bool,
    replace_stream: bool,
    mocked_check_cluster_connectivity,
    mocked_get_namespace_for_instance
):
    asset_name = f"test{asset_type.title()}Asset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"
    stream_name = f"test{asset_type.title()}Stream{generate_random_string(5)}"

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]
    expected_stream = {}

    # Build expected stream configuration based on asset type
    if asset_type == "custom":
        expected_stream = {
            "name": stream_name,
            "streamConfiguration": stream_params["stream_custom_configuration"],
            "typeRef": stream_params.get("type_ref")
        }
    else:  # media
        # Build stream configuration based on task type and parameters
        stream_config = {"taskType": stream_params["task_type"]}

        # Map CLI parameters to stream configuration
        param_mapping = {
            "disable_autostart": "autostart",
            "task_format": "format",
            "snapshots_per_second": "snapshotsPerSecond",
            "path": "path",
            "duration": "duration",
            "media_server_address": "mediaServerAddress",
            "media_server_port": "mediaServerPort",
            "media_server_path": "mediaServerPath",
            "media_server_username": "mediaServerUsernameRef",
            "media_server_password": "mediaServerPasswordRef",
            "media_server_certificate": "mediaServerCertificateRef"
        }

        for cli_param, config_key in param_mapping.items():
            if cli_param in stream_params:
                if cli_param == "disable_autostart":
                    # Convert to 'enabled' property
                    stream_config[config_key] = not stream_params[cli_param]
                else:
                    stream_config[config_key] = stream_params[cli_param]

        expected_stream = {
            "name": stream_name,
            "streamConfiguration": json.dumps(stream_config)
        }

    # Add optional destination parameters based on test case
    if destination_params:
        dest = {
            "target": "Mqtt" if "topic" in destination_params else "Storage",
            "configuration": destination_params
        }
        expected_stream["destinations"] = [dest]
        stream_params["stream_destinations"] = [f"{key}={value}" for key, value in destination_params.items()]

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

    # Add previous streams if needed for the test case
    if has_previous_streams:
        # Add existing streams based on asset type
        if asset_type == "custom":
            previous_streams = [
                generate_stream(stream_name=f"existingStream{i}", asset_type=asset_type)
                for i in range(2)
            ]
        else:  # media
            previous_streams = [
                generate_stream(stream_name="existingMediaStream", asset_type="media")
            ]
        mocked_asset["properties"]["streams"] = previous_streams

    # Mock the existing asset
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=mocked_asset,
        status=200
    )

    # Expected asset payload for patch request
    updated_asset = deepcopy(mocked_asset)
    updated_asset["properties"]["streams"] = updated_asset["properties"].get("streams", [])

    # If replacing, keep only non-matching streams
    if replace_stream:
        updated_asset["properties"]["streams"] = [
            s for s in mocked_asset["properties"]["streams"] if s["name"] != stream_name
        ]

    updated_asset["properties"]["streams"].append(expected_stream)

    # Mock the asset patch response
    mocked_responses.add(
        method=responses.PATCH,
        url=get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        status=200
    )

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=updated_asset,
        status=200
    )

    # Execute the command
    result = command_func(
        cmd=mocked_cmd,
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        stream_name=stream_name,
        replace=replace_stream,
        wait_sec=0,
        **stream_params
    )

    # Verify the result
    assert result == expected_stream

    # Verify API calls were made correctly
    expected_calls = 4  # device GET, asset GET, asset PATCH, asset GET
    assert len(mocked_responses.calls) == expected_calls
    assert mocked_responses.calls[0].request.method == "GET"  # device
    assert mocked_responses.calls[1].request.method == "GET"  # asset
    assert mocked_responses.calls[2].request.method == "PATCH"  # asset update
    assert mocked_responses.calls[3].request.method == "GET"  # asset

    # Verify the PATCH request body contains the expected stream structure
    patch_body = json.loads(mocked_responses.calls[2].request.body)
    assert "streams" in patch_body["properties"]
    streams = patch_body["properties"]["streams"]

    # Find our stream in the list
    added_stream = next((s for s in streams if s["name"] == stream_name), None)
    assert added_stream is not None, "Added stream not found in the list of streams"

    # Verify stream configuration
    assert added_stream["typeRef"] == expected_stream.get("typeRef")
    check_stream_configuration(added_stream, expected_stream)
    check_destinations(added_stream, expected_stream)

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


@pytest.mark.parametrize("asset_type, command_func", [
    ("custom", add_namespace_custom_asset_stream),
    ("media", add_namespace_media_asset_stream),
])
def test_add_namespace_asset_stream_error(
    mocked_cmd,
    mocked_responses: responses,
    asset_type: str,
    command_func,
    mocked_check_cluster_connectivity,
    mocked_get_namespace_for_instance
):
    """Test error cases for adding asset streams with different asset types.

    Tests the following scenarios:
    - Mismatch between asset type and device endpoint type
    - Stream exists but replace flag not set
    """
    asset_name = "testAsset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"
    stream_name = f"test{generate_random_string(5)}"

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
        "stream_name": stream_name,
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
        add_device_get_call(
            mocked_responses,
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            device_name=mocked_asset["properties"]["deviceRef"]["deviceName"],
            endpoint_name=mocked_asset["properties"]["deviceRef"]["endpointName"],
            endpoint_type="onvif"
        )

        with pytest.raises(InvalidArgumentValueError) as excinfo:
            command_func(**base_params)

        assert f" is of type 'microsoft.onvif', but expected 'microsoft.{asset_type}'." in str(excinfo.value).lower()

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

    # 2nd do stream already exists
    mocked_asset["properties"]["streams"] = [generate_stream(stream_name=stream_name)]

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

    assert f"Stream '{stream_name}' already exists in asset '{asset_name}'. " in str(excinfo.value)

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


@pytest.mark.parametrize("num_streams", [0, 1, 3])
def test_list_namespace_asset_streams(
    mocked_cmd, mocked_responses: responses, num_streams: int, mocked_get_namespace_for_instance
):
    asset_name = "testAsset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

    expected_streams = [generate_stream() for _ in range(num_streams)]
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    # ensure we can have the option of no stream property
    if expected_streams:
        mocked_asset["properties"]["streams"] = expected_streams

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

    streams = list_namespace_asset_streams(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        asset_name=asset_name
    )
    assert len(streams) == num_streams
    expected_stream_map = {stream["name"]: stream for stream in expected_streams}
    for stream in streams:
        assert stream["name"] in expected_stream_map
        expected_stream = expected_stream_map[stream["name"]]
        assert stream["streamConfiguration"] == expected_stream["streamConfiguration"]
        assert stream["destinations"] == expected_stream["destinations"]

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


def test_show_namespace_asset_stream(mocked_cmd, mocked_responses: responses, mocked_get_namespace_for_instance):
    asset_name = "testAsset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"
    stream_name = generate_random_string()

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

    expected_stream = generate_stream(stream_name=stream_name, asset_type="media")
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
    mocked_asset["properties"]["streams"] = [expected_stream]

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

    stream = show_namespace_asset_stream(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        asset_name=asset_name,
        stream_name=stream_name
    )
    assert stream["name"] == expected_stream["name"]
    assert stream["streamConfiguration"] == expected_stream["streamConfiguration"]
    assert stream["destinations"] == expected_stream["destinations"]

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


@pytest.mark.parametrize("streams_present", [True, False])
@pytest.mark.parametrize("stream_deleted", [True, False])
def test_remove_namespace_asset_stream(
    mocked_cmd,
    mocked_responses: responses,
    streams_present: bool,
    stream_deleted: bool,
    mocked_check_cluster_connectivity,
    mocked_get_namespace_for_instance
):
    asset_name = "testAsset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"
    stream_name = generate_random_string()

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    # make some other streams, have the stream prop there
    if streams_present:
        mocked_asset["properties"]["streams"] = [
            generate_stream(asset_type="custom"),
            generate_stream(asset_type="media")
        ]
    expected_streams = deepcopy(mocked_asset["properties"].get("streams", []))

    # the remove should not fail even if the stream is not there
    if stream_deleted:
        mocked_asset["properties"]["streams"] = mocked_asset["properties"].get("streams", [])
        mocked_asset["properties"]["streams"].append(
            generate_stream(stream_name=stream_name, asset_type="custom")
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

    if stream_deleted:
        # Mock the PATCH request to update the asset
        updated_asset = deepcopy(mocked_asset)
        updated_asset["properties"]["streams"] = expected_streams
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

    result_streams = remove_namespace_asset_stream(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        asset_name=asset_name,
        stream_name=stream_name,
        wait_sec=0
    )

    # Verify result matches the mock updated namespace
    assert result_streams == expected_streams

    # Verify API calls were made correctly
    assert len(mocked_responses.calls) == (3 if stream_deleted else 1)
    assert mocked_responses.calls[0].request.method == "GET"
    if stream_deleted:
        assert mocked_responses.calls[1].request.method == "PATCH"
        assert mocked_responses.calls[2].request.method == "GET"

        # Verify the PATCH request body contains the expected updated streams
        patch_body = json.loads(mocked_responses.calls[1].request.body)

        # Streams should be in the properties section
        assert "streams" in patch_body["properties"]
        streams = patch_body["properties"]["streams"]

        # Should not contain the deleted stream
        stream_names = [s["name"] for s in streams]
        assert stream_name not in stream_names

        # Should contain all other streams
        assert len(streams) == len(expected_streams)
        for expected_stream in expected_streams:
            assert expected_stream["name"] in stream_names

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


@pytest.mark.parametrize("asset_type, command_func, stream_params", [
    # Custom asset stream updates
    (
        "custom",
        update_namespace_custom_asset_stream,
        {
            "stream_custom_configuration": json.dumps({
                "customProperty": "updatedValue", "streamType": "updated-sensor-data"
            }),
            "type_ref": f"custom.stream{randint(0, 1000)}"
        },
    ),
    (
        "custom",
        update_namespace_custom_asset_stream,
        {},  # No configuration update, only destinations
    ),
    # Media asset stream updates - snapshot-to-mqtt
    (
        "media",
        update_namespace_media_asset_stream,
        {
            "task_type": "snapshot-to-mqtt",
            "disable_autostart": False,
            "task_format": "png",
            "snapshots_per_second": 5
        },
    ),
    # Media asset stream updates - snapshot-to-fs
    (
        "media",
        update_namespace_media_asset_stream,
        {
            "task_type": "snapshot-to-fs",
            "disable_autostart": True,
            "task_format": "bmp",
            "snapshots_per_second": 3,
            "path": "/updated/snapshots"
        },
    ),
    # Media asset stream updates - clip-to-fs
    (
        "media",
        update_namespace_media_asset_stream,
        {
            "task_type": "clip-to-fs",
            "disable_autostart": False,
            "task_format": "avi",
            "duration": 60,
            "path": "/updated/clips"
        },
    ),
    # Media asset stream updates - stream-to-rtsp
    (
        "media",
        update_namespace_media_asset_stream,
        {
            "task_type": "stream-to-rtsp",
            "disable_autostart": False,
            "media_server_address": "updated.192.168.1.200",
            "media_server_port": 8554,
            "media_server_path": "/updated/live/stream1",
            "media_server_username": "updateduser",
            "media_server_password": "updatedpass"
        },
    ),
    # Media asset stream updates - stream-to-rtsps
    (
        "media",
        update_namespace_media_asset_stream,
        {
            "task_type": "stream-to-rtsps",
            "disable_autostart": True,
            "media_server_address": "updated.secure.example.com",
            "media_server_port": 443,
            "media_server_path": "/updated/secure/stream",
            "media_server_username": "updatedSecureUser",
            "media_server_password": "updatedSecurePass",
            "media_server_certificate": "updated-cert-content"
        },
    ),
    # Media asset stream - partial updates (only some parameters)
    (
        "media",
        update_namespace_media_asset_stream,
        {
            "disable_autostart": True,  # Only update autostart, keep existing task_type
        },
    ),
])
@pytest.mark.parametrize("destination_params", [
    {},
    {
        "topic": "/contoso/events/test",
        "retain": "Keep",
        "qos": "Qos0",
        "ttl": 3600
    },
    {
        "path": "/data/streams",
    },
])
def test_update_namespace_asset_stream(
    mocked_cmd,
    mocked_responses: responses,
    asset_type: str,
    command_func,
    stream_params: dict,
    destination_params: dict,
    mocked_check_cluster_connectivity,
    mocked_get_namespace_for_instance
):
    asset_name = f"test{asset_type.title()}Asset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"
    stream_name = f"test{asset_type.title()}Stream{generate_random_string(5)}"

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

    # Generate mock asset with existing stream
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    # Mock device endpoint validation
    add_device_get_call(
        mocked_responses,
        resource_group_name=resource_group_name,
        namespace_name=namespace_name,
        device_name=mocked_asset["properties"]["deviceRef"]["deviceName"],
        endpoint_name=mocked_asset["properties"]["deviceRef"]["endpointName"],
        endpoint_type=asset_type
    )

    # Create initial stream to be updated
    initial_stream_config = None
    if asset_type == "custom":
        initial_stream_config = json.dumps({
            "customProperty": "originalValue",
            "streamType": "original-sensor-data"
        })
    else:  # media
        initial_stream_config = json.dumps({
            "taskType": "snapshot-to-mqtt",
            "autostart": True,
            "format": "jpeg",
            "snapshotsPerSecond": 1
        })

    initial_stream = generate_stream(
        stream_name=stream_name,
        stream_configuration=initial_stream_config,
        asset_type=asset_type
    )

    # Add some other streams to the asset
    other_streams = [
        generate_stream(stream_name=f"otherStream{i}", asset_type=asset_type)
        for i in range(2)
    ]
    mocked_asset["properties"]["streams"] = other_streams + [initial_stream]

    # Mock GET request to get the asset
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=mocked_asset,
        status=200
    )

    # Build expected updated stream
    if asset_type == "custom":
        expected_stream_config = initial_stream_config
        if "stream_custom_configuration" in stream_params:
            expected_stream_config = stream_params["stream_custom_configuration"]

        expected_stream = {
            "name": stream_name,
            "streamConfiguration": expected_stream_config,
            "typeRef": stream_params.get("type_ref", initial_stream.get("typeRef"))
        }
    else:  # media
        # Start with initial config and update with provided parameters
        updated_config = json.loads(initial_stream_config)
        if "task_type" in stream_params and stream_params["task_type"] != updated_config["taskType"]:
            updated_config = {}

        # Map CLI parameters to stream configuration
        param_mapping = {
            "task_type": "taskType",
            "disable_autostart": "autostart",
            "task_format": "format",
            "snapshots_per_second": "snapshotsPerSecond",
            "path": "path",
            "duration": "duration",
            "media_server_address": "mediaServerAddress",
            "media_server_port": "mediaServerPort",
            "media_server_path": "mediaServerPath",
            "media_server_username": "mediaServerUsernameRef",
            "media_server_password": "mediaServerPasswordRef",
            "media_server_certificate": "mediaServerCertificateRef"
        }

        for cli_param, config_key in param_mapping.items():
            if cli_param in stream_params:
                if cli_param == "disable_autostart":
                    # Convert to 'autostart' property
                    updated_config["autostart"] = not stream_params[cli_param]
                else:
                    updated_config[config_key] = stream_params[cli_param]

        expected_stream = {
            "name": stream_name,
            "streamConfiguration": json.dumps(updated_config)
        }

    # Handle destination updates
    if destination_params:
        dest = {
            "target": "Mqtt" if "topic" in destination_params else "Storage",
            "configuration": destination_params
        }
        expected_stream["destinations"] = [dest]
        stream_params["stream_destinations"] = [f"{key}={value}" for key, value in destination_params.items()]
    else:
        # Keep original destinations if not updating
        expected_stream["destinations"] = initial_stream["destinations"]

    # Create expected asset after update
    expected_asset_payload = deepcopy(mocked_asset)
    for i, stream in enumerate(expected_asset_payload["properties"]["streams"]):
        if stream["name"] == stream_name:
            expected_asset_payload["properties"]["streams"][i] = expected_stream
            break

    # Mock PATCH request
    mocked_responses.add(
        method=responses.PATCH,
        url=get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        status=200
    )

    # Mock final GET request to return updated asset
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        ),
        json=expected_asset_payload,
        status=200,
        content_type="application/json",
    )

    # Execute the command
    result = command_func(
        cmd=mocked_cmd,
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        stream_name=stream_name,
        wait_sec=0,
        **stream_params
    )

    # Verify the result
    assert result == expected_stream

    # Verify API calls were made correctly
    expected_calls = 4  # device GET, asset GET, asset PATCH, asset GET
    assert len(mocked_responses.calls) == expected_calls
    assert mocked_responses.calls[0].request.method == "GET"  # device
    assert mocked_responses.calls[1].request.method == "GET"  # asset
    assert mocked_responses.calls[2].request.method == "PATCH"  # asset update
    assert mocked_responses.calls[3].request.method == "GET"  # final asset get

    # Verify the PATCH request body contains the expected stream structure
    patch_body = json.loads(mocked_responses.calls[2].request.body)
    assert "streams" in patch_body["properties"]
    streams = patch_body["properties"]["streams"]

    # Find our updated stream in the list
    updated_stream = next((s for s in streams if s["name"] == stream_name), None)
    assert updated_stream is not None, "Updated stream not found in the list of streams"

    # Verify stream configuration was updated correctly
    assert updated_stream.get("typeRef") == expected_stream.get("typeRef")
    check_stream_configuration(updated_stream, expected_stream)
    check_destinations(updated_stream, expected_stream)

    # Verify other streams were preserved
    assert len(streams) == len(mocked_asset["properties"]["streams"])
    for stream in other_streams:
        found_stream = next((s for s in streams if s["name"] == stream["name"]), None)
        assert found_stream is not None
        assert found_stream["streamConfiguration"] == stream["streamConfiguration"]

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )
