# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy
from typing import Optional
import json
import pytest
import responses

from azure.cli.core.azclierror import InvalidArgumentValueError, ValidationError
from azext_edge.edge.commands_namespaces import (
    create_namespace_custom_asset,
    create_namespace_media_asset,
    create_namespace_onvif_asset,
    create_namespace_opcua_asset,
    create_namespace_rest_asset,
    create_namespace_sse_asset,
    create_namespace_mqtt_asset,
    show_namespace_asset,
    delete_namespace_asset,
    update_namespace_custom_asset,
    update_namespace_media_asset,
    update_namespace_onvif_asset,
    update_namespace_opcua_asset,
    update_namespace_rest_asset,
    update_namespace_sse_asset,
    update_namespace_mqtt_asset,
    query_namespace_assets
)
from azext_edge.edge.providers.adr.namespace_assets import _process_configs
from azext_edge.edge.providers.adr.namespace_devices import DeviceEndpointType
from azext_edge.edge.util.common import parse_kvp_nargs
from azext_edge.edge.util.az_client import DeviceRegistryMgmtApiVersion

from .test_namespace_devices_unit import get_namespace_device_record, get_namespace_device_mgmt_uri
from .test_namespaces_unit import get_namespace_mgmt_uri
from ...generators import BASE_URL, generate_random_string

# TODO: consolidate all these ADR refresh apis
NAMESPACE_ASSET_RESOURCE_TYPE = "Microsoft.DeviceRegistry/namespaces/assets"


def get_namespace_asset_mgmt_uri(
    namespace_name: str, resource_group_name: str, asset_name: Optional[str] = None
) -> str:
    """
    Get the management URI for a namespace asset.
    """
    base_uri = get_namespace_mgmt_uri(
        namespace_name=namespace_name, resource_group_name=resource_group_name, include_api=False
    )
    base_uri += "/assets" + (f"/{asset_name}" if asset_name else "")
    return f"{base_uri}?api-version={DeviceRegistryMgmtApiVersion.V20251001.value}"


def get_namespace_asset_record(
    asset_name: str, namespace_name: str, resource_group_name: str
) -> dict:
    """
    Get a mock namespace asset record.
    """
    return {
        "name": asset_name,
        "id": get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        ).split("?", maxsplit=1)[0][len(BASE_URL) :],
        "type": NAMESPACE_ASSET_RESOURCE_TYPE,
        "location": "westus",
        "resourceGroup": resource_group_name,
        "extendedLocation": {
            "name": generate_random_string(),
            "type": "CustomLocation"
        },
        "properties": {
            "deviceRef": {
                "deviceName": f"test{generate_random_string()}",
                "endpointName": f"test{generate_random_string()}"
            },
            "description": "Test asset description",
            "displayName": "Test Asset",
            "provisioningState": "Succeeded"
        }
    }


def add_device_get_call(
    mocked_responses: responses,
    device_name: str,
    namespace_name: str,
    resource_group_name: str,
    endpoint_name: str,
    endpoint_type: Optional[str] = "custom"
):
    """Add a mock GET call for a namespace device.

    Required for any asset operation that validates the device and endpoint."""
    # Create mock device record
    mock_device_record = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
    # Add the endpoint with valid type
    mock_device_record["properties"]["endpoints"]["inbound"] = {
        endpoint_name: {"endpointType": f"Microsoft.{endpoint_type}"}
    }
    # Add mock device response
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_device_mgmt_uri(
            device_name=device_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        ),
        json=mock_device_record,
        status=200,
        content_type="application/json",
    )


@pytest.mark.parametrize("reqs", [
    {},
    {
        "asset_type_refs": ["testTypeRef1", "testTypeRef2"],
        "attributes": ["key1=value1", "key2=value2"],
        "description": "Test description",
        "disabled": True,
        "display_name": "Test Display Name",
        "documentation_uri": "http://test-docs.com",
        "external_asset_id": "external-id-123",
        "hardware_revision": "HW-Rev-1",
        "manufacturer": "Test Manufacturer",
        "manufacturer_uri": "http://manufacturer.com",
        "model": "TestModel",
        "product_code": "PROD-123",
        "serial_number": "SN12345",
        "software_revision": "SW-Rev-1",
        "tags": {"tag1": "value1", "tag2": "value2"},
    },
    {
        "disabled": False,
        "asset_type_refs": ["type1", "type2"],
    }
])
@pytest.mark.parametrize("asset_type, unique_reqs", [
    # Empty
    ["custom", {}],
    ["media", {}],
    ["onvif", {}],
    ["opcua", {}],
    ["rest", {}],
    ["sse", {}],
    ["mqtt", {}],
    # CUSTOM
    [
        "custom",
        {
            "default_dataset_custom_configuration": json.dumps({"testConfig": "value"}),
            "default_dataset_destinations": ["key=test-key"],
            "default_event_custom_configuration": json.dumps({"eventsConfig": "value"}),
            "default_event_destinations": ["path=/data/test"],
            "default_mgmtg_custom_configuration": json.dumps({"mgmtgConfig": "value"}),
            "default_stream_custom_configuration": json.dumps({"streamsConfig": "value"}),
            "default_stream_destinations": ["topic=/contoso/test", "retain=Never", "qos=Qos0", "ttl=3600"]
        }
    ],
    # Media task type: snapshot-to-mqtt with all allowed parameters
    [
        "media",
        {
            "task_type": "snapshot-to-mqtt",
            "format": "jpeg",
            "snapshots_per_second": 1,
            "default_stream_destinations": ["topic=/contoso/snapshots", "retain=Never", "qos=Qos0", "ttl=3600"]
        }
    ],
    # Media task type: clip-to-fs with all allowed parameters
    [
        "media",
        {
            "task_type": "clip-to-fs",
            "format": "mp4",
            "duration": 60,
            "path": "/data/clips",
            "default_stream_destinations": ["path=/contoso/clips"]
        }
    ],
    # Media task type: stream-to-rtsp with all allowed parameters
    [
        "media",
        {
            "task_type": "stream-to-rtsp",
            "media_server_address": "media-server.svc.cluster.local",
            "media_server_port": 8554,
            "media_server_path": "/live/stream1",
            "media_server_username": "streamuser",
            "media_server_password": "streampassword",
        }
    ],
    # OPCUA
    [
        "opcua",
        {
            "default_dataset_publishing_interval": 2000,
            "default_dataset_sampling_interval": 1000,
            "default_dataset_queue_size": 2,
            "default_dataset_key_frame_count": 3,
            "default_dataset_destinations": ["topic=/contoso/test", "retain=Never", "qos=0", "ttl=3600"],
            "default_events_publishing_interval": 1500,
            "default_events_queue_size": 4,
            "default_event_destinations": ["topic=/contoso/test2", "retain=Never", "qos=1", "ttl=400"]
        }
    ],
    # REST
    [
        "rest",
        {
            "rest_dataset_sampling_interval": 1000,
        }
    ],
    # SSE (Server-Sent Events)
    [
        "sse",
        {
            "default_dataset_destinations": ["topic=/contoso/sse/data", "retain=Keep", "qos=Qos1", "ttl=3600"],
            "default_event_destinations": ["topic=/contoso/sse/events", "retain=Never", "qos=Qos0", "ttl=7200"]
        }
    ],
    # SSE with BrokerStateStore destinations
    [
        "sse",
        {
            "default_dataset_destinations": ["key=sse-data-cache"],
            "default_event_destinations": ["topic=/contoso/sse/alerts", "retain=Keep", "qos=Qos1", "ttl=3600"]
        }
    ],
    # MQTT (In-cluster MQTT broker)
    [
        "mqtt",
        {
            "default_dataset_destinations": ["topic=/contoso/mqtt/data", "retain=Keep", "qos=Qos1", "ttl=3600"]
        }
    ],
    # MQTT with BrokerStateStore destinations
    [
        "mqtt",
        {
            "default_dataset_destinations": ["key=mqtt-data-cache"]
        }
    ]
])
def test_create_namespace_asset(
    mocked_cmd,
    mocked_responses: responses,
    reqs: dict,
    asset_type: str,
    unique_reqs: dict,
    mocked_check_cluster_connectivity,
    mocked_get_namespace_for_instance
):
    """
    Test the create_namespace_asset function for different asset types.
    Only tests success cases with various parameter combinations.
    """
    # Setup variables
    asset_name = generate_random_string()
    instance_name = generate_random_string()
    instance_resource_group = generate_random_string()
    device_name = generate_random_string()
    device_endpoint_name = generate_random_string()

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    namespace_resource_group = namespace_resource["resource_group"]

    # Merge shared and unique requirements
    all_reqs = {**reqs, **unique_reqs}

    add_device_get_call(
        mocked_responses=mocked_responses,
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=namespace_resource_group,
        endpoint_name=device_endpoint_name,
        endpoint_type=asset_type
    )

    # Create mock asset record
    mock_asset_record = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=namespace_resource_group
    )

    # Add mock asset creation response
    mocked_responses.add(
        method=responses.PUT,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    type_to_command = {
        "custom": create_namespace_custom_asset,
        "media": create_namespace_media_asset,
        "onvif": create_namespace_onvif_asset,
        "opcua": create_namespace_opcua_asset,
        "rest": create_namespace_rest_asset,
        "sse": create_namespace_sse_asset,
        "mqtt": create_namespace_mqtt_asset,
    }
    result = type_to_command[asset_type](
        cmd=mocked_cmd,
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        device_name=device_name,
        device_endpoint_name=device_endpoint_name,
        wait_sec=0,
        **all_reqs
    )

    # Verify result matches mock response
    assert result == mock_asset_record

    # Ensure we've made the expected API calls
    assert len(mocked_responses.calls) == 2  # GET for device + PUT for asset

    # Verify request payload in the second call (PUT)
    put_request = mocked_responses.calls[1].request
    request_body = json.loads(put_request.body)

    # Verify required properties
    assert request_body["properties"]["deviceRef"]["deviceName"] == device_name
    assert request_body["properties"]["deviceRef"]["endpointName"] == device_endpoint_name

    all_reqs["asset_type"] = DeviceEndpointType.get_type_from_keyword(asset_type)
    assert request_body.get("tags") == all_reqs.get("tags")

    assert_asset_properties(request_body["properties"], all_reqs)

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


@pytest.mark.parametrize("asset_type, create_command", [
    ["media", create_namespace_media_asset],
    ["onvif", create_namespace_onvif_asset],
    ["opcua", create_namespace_opcua_asset],
    ["rest", create_namespace_rest_asset],
    ["sse", create_namespace_sse_asset],
    ["mqtt", create_namespace_mqtt_asset]
])
def test_create_namespace_asset_error(
    mocked_cmd,
    mocked_responses: responses,
    asset_type: str,
    create_command,
    mocked_check_cluster_connectivity,
    mocked_get_namespace_for_instance
):
    # Setup variables
    asset_name = generate_random_string()
    instance_name = generate_random_string()
    instance_resource_group = generate_random_string()
    device_name = generate_random_string()
    device_endpoint_name = generate_random_string()

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    namespace_resource_group = namespace_resource["resource_group"]

    # Create mock device record
    mock_device_record = get_namespace_device_record(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=namespace_resource_group,
    )

    # Add the endpoint but with an incompatible type
    # For each asset type, use a different incorrect type
    incorrect_types = {
        "media": DeviceEndpointType.REST.value,
        "onvif": DeviceEndpointType.MEDIA.value,
        "opcua": DeviceEndpointType.ONVIF.value,
        "rest": DeviceEndpointType.OPCUA.value,
        "sse": DeviceEndpointType.MEDIA.value,
        "mqtt": DeviceEndpointType.REST.value
    }
    mock_device_record["properties"]["endpoints"]["inbound"] = {
        device_endpoint_name: {"endpointType": incorrect_types[asset_type]}
    }

    # Add mock device response
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_device_mgmt_uri(
            device_name=device_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=mock_device_record,
        status=200,
        content_type="application/json",
    )

    # Test that InvalidArgumentValueError is raised due to incompatible endpoint type
    with pytest.raises(InvalidArgumentValueError):
        create_command(
            cmd=mocked_cmd,
            asset_name=asset_name,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
            device_name=device_name,
            device_endpoint_name=device_endpoint_name,
            wait_sec=0
        )

    # Verify that mocked_get_namespace_for_instance was called
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


@pytest.mark.parametrize("response_status", [202, 404])
def test_delete_namespace_asset(
    mocked_cmd,
    mocked_responses: responses,
    response_status: int,
    mocked_get_namespace_for_instance
):
    """
    Test the delete_namespace_asset function.
    """
    # Setup variables
    asset_name = generate_random_string()
    instance_name = generate_random_string()
    instance_resource_group = generate_random_string()

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    namespace_resource_group = namespace_resource["resource_group"]

    # Create mock response
    mock_response = {} if response_status == 202 else {"error": {"code": "NotFound", "message": "Asset not found"}}

    # Add mock response
    mocked_responses.add(
        method=responses.DELETE,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=mock_response,
        status=response_status,
        content_type="application/json",
    )

    # Execute test based on status code
    if response_status != 202:
        with pytest.raises(Exception):
            delete_namespace_asset(
                cmd=mocked_cmd,
                asset_name=asset_name,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                confirm_yes=True,
                wait_sec=0
            )
        return

    # Test delete_namespace_asset for success case
    delete_namespace_asset(
        cmd=mocked_cmd,
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        confirm_yes=True,
        wait_sec=0
    )

    # Verify result matches mock response
    assert len(mocked_responses.calls) == 1

    # Verify that mocked_get_namespace_for_instance was called
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


@pytest.mark.parametrize("response_status", [200, 404])
def test_show_namespace_asset(
    mocked_cmd, mocked_responses: responses, mocked_get_namespace_for_instance, response_status: int
):
    """
    Test the show_namespace_asset function using instance-based parameters.
    """
    # Setup variables
    asset_name = generate_random_string()
    instance_name = generate_random_string()
    instance_resource_group = generate_random_string()

    # Setup mock for get_namespace_for_instance to return the namespace_name
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    namespace_resource_group = namespace_resource["resource_group"]

    # Create mock response
    mock_asset_record = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=namespace_resource_group
    )

    # Add mock response
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=mock_asset_record if response_status == 200 else {"error": "NotFound"},
        status=response_status,
        content_type="application/json",
    )

    # Execute test based on status code
    if response_status != 200:
        with pytest.raises(Exception):
            show_namespace_asset(
                cmd=mocked_cmd,
                asset_name=asset_name,
                instance_name=instance_name,
                resource_group_name=instance_resource_group
            )
        # Verify the namespace resolution mock was called
        mocked_get_namespace_for_instance.assert_called_once_with(
            cmd=mocked_cmd,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group
        )
        return

    # Test show_namespace_asset for success case
    result = show_namespace_asset(
        cmd=mocked_cmd,
        asset_name=asset_name,
        instance_name=instance_name,
        resource_group_name=instance_resource_group
    )

    # Verify result matches mock response
    assert result == mock_asset_record
    assert len(mocked_responses.calls) == 1

    # Verify the namespace resolution mock was called
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


@pytest.mark.parametrize("reqs", [
    {},
    {
        "asset_types": ["testTypeRef1", "testTypeRef2"],
        "attributes": ["key1=value1", "key2=value2"],
        "description": "Updated description",
        "disabled": True,
        "display_name": "Updated Display Name",
        "documentation_uri": "http://updated-docs.com",
        "external_asset_id": "updated-external-id-123",
        "hardware_revision": "Updated-HW-Rev-1",
        "manufacturer": "Updated Manufacturer",
        "manufacturer_uri": "http://updated-manufacturer.com",
        "model": "UpdatedTestModel",
        "product_code": "UPDATED-PROD-123",
        "serial_number": "UPDATED-SN12345",
        "software_revision": "Updated-SW-Rev-1",
        "tags": {"updated_tag1": "value1", "updated_tag2": "value2"},
    },
    {
        "disabled": False,
        "asset_type_refs": ["updated_type1", "updated_type2"],
    }
])
@pytest.mark.parametrize("asset_type, unique_reqs", [
    # Empty
    ["custom", {}],
    ["media", {}],
    ["onvif", {}],
    ["opcua", {}],
    ["rest", {}],
    ["sse", {}],
    # Custom
    [
        "custom",
        {
            "default_dataset_custom_configuration": json.dumps({"testConfig": "value"}),
            "default_dataset_destinations": ["key=test-key"],
            "default_event_custom_configuration": json.dumps({"eventsConfig": "value"}),
            "default_event_destinations": ["path=/data/test"],
            "default_mgmtg_custom_configuration": json.dumps({"mgmtgConfig": "value"}),
            "default_stream_custom_configuration": json.dumps({"streamsConfig": "value"}),
            "default_stream_destinations": ["topic=/contoso/test", "retain=Never", "qos=Qos0", "ttl=3600"]
        }
    ],
    # Media task type: snapshot-to-mqtt with all allowed parameters
    [
        "media",
        {
            "task_type": "snapshot-to-mqtt",
            "format": "jpeg",
            "snapshots_per_second": 1,
            "default_stream_destinations": ["topic=/contoso/snapshots", "retain=Never", "qos=Qos0", "ttl=3600"]
        }
    ],
    # Media task type: clip-to-fs with all allowed parameters
    [
        "media",
        {
            "task_type": "clip-to-fs",
            "format": "mp4",
            "duration": 60,
            "path": "/data/clips",
            "default_stream_destinations": ["path=/contoso/clips"]
        }
    ],
    # Media task type: stream-to-rtsp with all allowed parameters
    [
        "media",
        {
            "task_type": "stream-to-rtsp",
            "media_server_address": "media-server.svc.cluster.local",
            "media_server_port": 8554,
            "media_server_path": "/live/stream1",
            "media_server_username": "streamuser",
            "media_server_password": "streampassword",
        }
    ],
    # Opcua
    [
        "opcua",
        {
            "default_dataset_publishing_interval": 2000,
            "default_dataset_sampling_interval": 1000,
            "default_dataset_queue_size": 2,
            "default_dataset_key_frame_count": 3,
            "default_dataset_destinations": ["topic=/contoso/test", "retain=Never", "qos=0", "ttl=3600"],
            "default_events_publishing_interval": 1500,
            "default_events_queue_size": 4,
            "default_event_destinations": ["topic=/contoso/test2", "retain=Never", "qos=1", "ttl=400"]
        }
    ],
    # REST
    [
        "rest",
        {
            "rest_dataset_sampling_interval": 1000,
        }
    ],
    # SSE (Server-Sent Events)
    [
        "sse",
        {
            "default_dataset_destinations": ["topic=/contoso/sse/updated-data", "retain=Keep", "qos=Qos1", "ttl=1800"],
            "default_event_destinations": ["topic=/contoso/sse/updated-events", "retain=Never", "qos=Qos0", "ttl=3600"]
        }
    ],
    # MQTT (In-cluster MQTT broker)
    [
        "mqtt",
        {
            "default_dataset_destinations": ["topic=/contoso/mqtt/updated-data", "retain=Keep", "qos=Qos1", "ttl=1800"]
        }
    ]
])
@pytest.mark.parametrize("original_properties", [
    {},
    {
        "asset_type_refs": ["original_type1", "original_type2"],
        "attributes": {"original_key": "original_value"},
        "description": "Original description",
        "enabled": True,
        "display_name": "Original Display Name",
        "documentation_uri": "http://original-docs.com",
        "external_asset_id": "original-external-id",
        "hardware_revision": "Original-HW-Rev",
        "manufacturer": "Original Manufacturer",
        "manufacturer_uri": "http://original-manufacturer.com",
        "model": "OriginalModel",
        "product_code": "ORIG-PROD",
        "serial_number": "ORIG-SN",
        "software_revision": "Original-SW-Rev",
        "default_datasets_configuration": json.dumps({"originalConfig": "value"}),
        "default_dataset_destinations": [{"target": "Storage", "configuration": {"path": "original/path"}}],
        "default_events_configuration": json.dumps({"originalEventsConfig": "value"}),
        "default_event_destinations": [{"target": "BrokerStateStore", "configuration": {"key": "original/key"}}],
        "default_management_groups_configuration": json.dumps({"originalMgmtgConfig": "value"}),
        "default_streams_configuration": json.dumps({"originalStreamsConfig": "value"}),
        "default_stream_destinations": [
            {
                "target": "Mqtt", "configuration": {
                    "topic": "/contoso/test",
                    "retain": "Never",
                    "qos": "Qos0",
                    "ttl": 3600
                }
            }
        ]
    }
])
def test_update_namespace_asset(
    mocked_cmd,
    mocked_responses: responses,
    reqs: dict,
    asset_type: str,
    unique_reqs: dict,
    original_properties: dict,
    mocked_check_cluster_connectivity,
    mocked_get_namespace_for_instance
):
    # Setup variables
    asset_name = generate_random_string()
    instance_name = generate_random_string()
    instance_resource_group = generate_random_string()

    # Get the namespace from the mocked function
    namespace_name = mocked_get_namespace_for_instance.return_value["name"]
    namespace_resource_group = mocked_get_namespace_for_instance.return_value["resource_group"]

    # Merge shared and unique requirements
    all_reqs = {**reqs, **unique_reqs}

    # Create the original asset properties based on the original_asset_state
    original_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=namespace_resource_group
    )
    original_asset["properties"].update(original_properties)

    # GET device call for validation
    add_device_get_call(
        mocked_responses=mocked_responses,
        device_name=original_asset["properties"]["deviceRef"]["deviceName"],
        namespace_name=namespace_name,
        resource_group_name=namespace_resource_group,
        endpoint_name=original_asset["properties"]["deviceRef"]["endpointName"],
        endpoint_type=asset_type
    )

    # Add mock GET response for the show operation that happens before update
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=original_asset,
        status=200,
        content_type="application/json",
    )

    # Create mock updated asset record and make sure it is different from original_asset
    updated_asset = deepcopy(original_asset)
    updated_asset["properties"]["description"] = "new updated description"

    # Add mock PATCH response
    mocked_responses.add(
        method=responses.PATCH,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        status=200,
        content_type="application/json",
    )

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=updated_asset,
        status=200,
        content_type="application/json",
    )

    # Map asset types to their update commands
    type_to_command = {
        "custom": update_namespace_custom_asset,
        "media": update_namespace_media_asset,
        "onvif": update_namespace_onvif_asset,
        "opcua": update_namespace_opcua_asset,
        "rest": update_namespace_rest_asset,
        "sse": update_namespace_sse_asset,
        "mqtt": update_namespace_mqtt_asset,
    }

    # Execute the update command
    result = type_to_command[asset_type](
        cmd=mocked_cmd,
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        wait_sec=0,
        **all_reqs
    )

    # Verify result matches mock response
    assert result == updated_asset

    # Ensure we've made the expected API calls
    # GET to fetch the device + GET to fetch original asset + PATCH to update it + GET
    assert len(mocked_responses.calls) == 4

    # Verify request payload in the second call (PATCH)
    patch_request = mocked_responses.calls[2].request
    request_body = json.loads(patch_request.body)

    # Use the helper function to verify properties in the request
    all_reqs["asset_type"] = f"Microsoft.{asset_type}"
    assert request_body.get("tags") == all_reqs.get("tags")

    # Only check properties key if it exists in the request body
    if "properties" in request_body:
        assert_asset_properties(request_body["properties"], all_reqs)

    # Verify that mocked_get_namespace_for_instance was called
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


@pytest.mark.parametrize("reqs", [
    {},
    {
        "asset_name": generate_random_string(),
        "device_name": generate_random_string(),
        "device_endpoint_name": generate_random_string(),
        "display_name": "Test Display Name",
        "documentation_uri": "http://test-docs.com",
        "external_asset_id": "external-id-123",
        "hardware_revision": "HW-Rev-1",
        "manufacturer": "Test Manufacturer",
        "manufacturer_uri": "http://manufacturer.com",
        "model": "TestModel",
        "product_code": "PROD-123",
        "serial_number": "SN12345",
        "software_revision": "SW-Rev-1",
        "disabled": True,
    },
    {
        "disabled": False,
        "instance_name": generate_random_string(),
        "instance_resource_group": generate_random_string(),
    },
    {
        "custom_query": "| where resouceGroupName == 'test-rg' | project name, type",
    },
    {
        "asset_name": generate_random_string(),
        "custom_query": "| where resouceGroupName == 'test-rg' | project name, type",
        "instance_name": generate_random_string(),
        "instance_resource_group": generate_random_string(),
    }
])
def test_query_namespace_assets(mocked_cmd, mocker, reqs):
    return_value = [{"id": "asset1"}, {"id": "asset2"}]
    # Mock the query method from the Queryable class
    mock_query = mocker.patch(
        "azext_edge.edge.util.queryable.Queryable.query",
        return_value=return_value
    )

    # Call the command under test
    result = query_namespace_assets(mocked_cmd, **reqs)

    # Verify the function returns the mocked query result
    assert result == return_value

    # Assert that the query method was called
    assert mock_query.call_count == 1

    # Check the query string that was passed to the query method
    query = mock_query.call_args[1]["query"]

    asset_start = "Resources | where type =~ 'Microsoft.DeviceRegistry/namespaces/assets'"
    # Assert that the query starts with the expected base
    if "instance_name" in reqs or "instance_resource_group" in reqs:
        assert query.startswith("Resources | where type =~ 'microsoft.iotoperations/instances'")
        if "instance_name" in reqs:
            assert f"| where name =~ \"{reqs['instance_name']}\"" in query
        if "instance_resource_group" in reqs:
            assert f"| where resourceGroup =~ \"{reqs['instance_resource_group']}\"" in query
        # asset start should be included still
        assert asset_start in query
        # project away only custom location 1
        assert "| project-away customLocation1" in query
        assert "| project-away customLocation1, customLocation" not in query
    else:
        assert query.startswith(asset_start)

    custom = "custom_query" in reqs
    # If a custom query was specified, verify it overrides other parameters
    if custom:
        assert reqs["custom_query"] in query

    # Check that each specified parameter is included in the query if the query is not custom
    # otherwise, the specified parameter should not be there
    for param, prop in [
        ("asset_name", "name"),
        ("device_name", "properties.deviceRef.deviceName"),
        ("device_endpoint_name", "properties.deviceRef.endpointName"),
        ("display_name", "properties.displayName"),
        ("documentation_uri", "properties.documentationUri"),
        ("external_asset_id", "properties.externalAssetId"),
        ("hardware_revision", "properties.hardwareRevision"),
        ("manufacturer", "properties.manufacturer"),
        ("manufacturer_uri", "properties.manufacturerUri"),
        ("model", "properties.model"),
        ("product_code", "properties.productCode"),
        ("serial_number", "properties.serialNumber"),
        ("software_revision", "properties.softwareRevision"),
    ]:
        if param in reqs:
            assert (f'| where {prop} =~ "{reqs[param]}"' in query) is not custom

    if "disabled" in reqs:
        assert (f'| where properties.enabled == {not reqs["disabled"]}' in query) is not custom

    # Verify the standard projection part is included
    assert ("| project id, customLocation, location, name, resourceGroup, provisioningState" in query) is not custom


def assert_asset_properties(result_props: dict, expected: dict):
    """
    Helper function to assert asset properties in the result.
    """
    assert result_props.get("assetTypeRefs") == expected.get("asset_type_refs")
    assert result_props.get("description") == expected.get("description")
    assert result_props.get("discoveredAssetRefs") == expected.get("discovered_asset_refs")
    assert result_props.get("displayName") == expected.get("display_name")
    assert result_props.get("documentationUri") == expected.get("documentation_uri")
    assert result_props.get("externalAssetId") == expected.get("external_asset_id")
    assert result_props.get("hardwareRevision") == expected.get("hardware_revision")
    assert result_props.get("manufacturer") == expected.get("manufacturer")
    assert result_props.get("manufacturerUri") == expected.get("manufacturer_uri")
    assert result_props.get("model") == expected.get("model")
    assert result_props.get("productCode") == expected.get("product_code")
    assert result_props.get("serialNumber") == expected.get("serial_number")
    assert result_props.get("softwareRevision") == expected.get("software_revision")

    if "attributes" in expected:
        assert result_props["attributes"] == parse_kvp_nargs(expected["attributes"])
    if "disabled" in expected:
        assert result_props["enabled"] is not expected["disabled"]

    # Destinations and configurations
    expected_configs = _process_configs(**expected)
    for key in expected_configs:
        assert key in result_props
        assert result_props[key] == expected_configs[key]


# ==================== EXPORT/IMPORT TESTS ====================

def test_export_namespace_asset_dataset_datapoints(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_namespace_for_instance,
    mocker
):
    """Test exporting datapoints from a dataset to JSON file."""
    asset_name = generate_random_string()
    dataset_name = "temperatureDataset"
    instance_name = generate_random_string()
    instance_resource_group = generate_random_string()

    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    namespace_resource_group = namespace_resource["resource_group"]

    # Create mock asset with dataset and datapoints
    mock_asset_record = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=namespace_resource_group
    )
    mock_asset_record["properties"]["datasets"] = [
        {
            "name": dataset_name,
            "dataPoints": [
                {
                    "name": "temperature1",
                    "dataSource": "nsu=http://microsoft.com/Opc/OpcPlc/;s=FastUInt1",
                    "dataPointConfiguration": json.dumps({"samplingInterval": 1000, "queueSize": 10})
                },
                {
                    "name": "temperature2",
                    "dataSource": "nsu=http://microsoft.com/Opc/OpcPlc/;s=FastUInt2",
                    "dataPointConfiguration": json.dumps({"samplingInterval": 2000, "queueSize": 20})
                }
            ]
        }
    ]

    # Mock GET asset response
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    # Mock dump_content_to_file
    expected_file_path = f"./{asset_name}_datapoint_{dataset_name}.json"
    mock_dump = mocker.patch(
        "azext_edge.edge.util.dump_content_to_file",
        return_value=expected_file_path
    )

    from azext_edge.edge.commands_namespaces import export_namespace_asset_dataset_points

    result = export_namespace_asset_dataset_points(
        cmd=mocked_cmd,
        asset_name=asset_name,
        dataset_name=dataset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        format="json",
        output_dir="."
    )

    # Verify result
    assert result == {"file_path": expected_file_path}

    # Verify dump_content_to_file was called with correct datapoints
    assert mock_dump.call_count == 1
    call_kwargs = mock_dump.call_args[1]
    assert call_kwargs["content"] == mock_asset_record["properties"]["datasets"][0]["dataPoints"]
    assert call_kwargs["file_name"] == f"{asset_name}_datapoint_{dataset_name}"
    assert call_kwargs["extension"] == "json"
    assert call_kwargs["output_dir"] == "."


def test_export_namespace_asset_dataset_datapoints_csv(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_namespace_for_instance,
    mocker
):
    """Test exporting datapoints to CSV format."""
    asset_name = generate_random_string()
    dataset_name = "pressureDataset"
    instance_name = generate_random_string()
    instance_resource_group = generate_random_string()

    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    namespace_resource_group = namespace_resource["resource_group"]

    mock_asset_record = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=namespace_resource_group
    )
    mock_asset_record["properties"]["datasets"] = [
        {
            "name": dataset_name,
            "dataPoints": [
                {"name": "pressure1", "dataSource": "source1"},
                {"name": "pressure2", "dataSource": "source2"}
            ]
        }
    ]

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    expected_file_path = f"./{asset_name}_datapoint_{dataset_name}.csv"
    mock_dump = mocker.patch(
        "azext_edge.edge.util.dump_content_to_file",
        return_value=expected_file_path
    )

    from azext_edge.edge.commands_namespaces import export_namespace_asset_dataset_points

    result = export_namespace_asset_dataset_points(
        cmd=mocked_cmd,
        asset_name=asset_name,
        dataset_name=dataset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        format="csv",
        output_dir="."
    )

    assert result == {"file_path": expected_file_path}
    assert mock_dump.call_count == 1
    call_kwargs = mock_dump.call_args[1]
    assert call_kwargs["extension"] == "csv"


def test_import_namespace_asset_dataset_datapoints(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_namespace_for_instance,
    mocked_check_cluster_connectivity,
    mocker
):
    """Test importing datapoints from a JSON file."""
    asset_name = generate_random_string()
    dataset_name = "importDataset"
    instance_name = generate_random_string()
    instance_resource_group = generate_random_string()
    input_file = "/tmp/datapoints.json"

    # Mock validator to skip validation
    mock_validator = mocker.Mock()
    mock_validator.validate_datapoint.return_value = None
    mocker.patch(
        "azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator.from_asset",
        return_value=mock_validator
    )

    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    namespace_resource_group = namespace_resource["resource_group"]

    # Existing asset with one datapoint
    mock_asset_record = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=namespace_resource_group
    )
    mock_asset_record["properties"]["datasets"] = [
        {
            "name": dataset_name,
            "dataPoints": [
                {"name": "existing1", "dataSource": "existingSource"}
            ]
        }
    ]

    # File contains new datapoints
    [
        {"name": "new1", "dataSource": "newSource1"},
        {"name": "new2", "dataSource": "newSource2"}
    ]

    # Mock _process_asset_sub_points_file_path (merge logic)
    # This function internally handles file deserialization
    merged_datapoints = [
        {"name": "existing1", "dataSource": "existingSource"},
        {"name": "new1", "dataSource": "newSource1"},
        {"name": "new2", "dataSource": "newSource2"}
    ]
    mock_process = mocker.patch(
        "azext_edge.edge.providers.adr.assets._process_asset_sub_points_file_path",
        return_value=merged_datapoints
    )

    # Mock GET asset response (initial)
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    # Mock PATCH update response
    updated_asset = deepcopy(mock_asset_record)
    updated_asset["properties"]["datasets"][0]["dataPoints"] = merged_datapoints
    mocked_responses.add(
        method=responses.PATCH,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=updated_asset,
        status=200,
        content_type="application/json",
    )

    # Mock GET asset response (final)
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=updated_asset,
        status=200,
        content_type="application/json",
    )

    from azext_edge.edge.commands_namespaces import import_namespace_asset_dataset_points

    result = import_namespace_asset_dataset_points(
        cmd=mocked_cmd,
        asset_name=asset_name,
        dataset_name=dataset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        input_file=input_file,
        wait_sec=0
    )

    # Verify result contains merged datapoints
    assert result == merged_datapoints

    # Verify _process_asset_sub_points_file_path was called with correct parameters
    mock_process.assert_called_once()
    call_kwargs = mock_process.call_args[1]
    assert call_kwargs["file_path"] == input_file
    assert call_kwargs["point_key"] == "name"
    assert call_kwargs["replace"] is False


def test_export_namespace_asset_datasets(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_namespace_for_instance,
    mocker
):
    """Test exporting all datasets from an asset to JSON file."""
    asset_name = generate_random_string()
    instance_name = generate_random_string()
    instance_resource_group = generate_random_string()

    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    namespace_resource_group = namespace_resource["resource_group"]

    # Create mock asset with multiple datasets
    mock_asset_record = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=namespace_resource_group
    )
    mock_asset_record["properties"]["datasets"] = [
        {
            "name": "dataset1",
            "datasetConfiguration": json.dumps({"publishingInterval": 1000}),
            "dataPoints": [
                {"name": "dp1", "dataSource": "source1"}
            ]
        },
        {
            "name": "dataset2",
            "datasetConfiguration": json.dumps({"publishingInterval": 2000}),
            "dataPoints": [
                {"name": "dp2", "dataSource": "source2"}
            ]
        }
    ]

    # Mock GET asset response
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    # Mock dump_content_to_file
    expected_file_path = f"./{asset_name}_dataset.json"
    mock_dump = mocker.patch(
        "azext_edge.edge.util.dump_content_to_file",
        return_value=expected_file_path
    )

    from azext_edge.edge.commands_namespaces import export_namespace_asset_datasets

    result = export_namespace_asset_datasets(
        cmd=mocked_cmd,
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        format="json",
        output_dir="."
    )

    # Verify result
    assert result == {"file_path": expected_file_path}

    # Verify dump_content_to_file was called with datasets WITHOUT dataPoints
    assert mock_dump.call_count == 1
    call_kwargs = mock_dump.call_args[1]
    exported_datasets = call_kwargs["content"]

    # Check that dataPoints are removed
    for dataset in exported_datasets:
        assert "dataPoints" not in dataset
        assert dataset["name"] in ["dataset1", "dataset2"]
        assert "datasetConfiguration" in dataset


def test_export_namespace_asset_datasets_yaml(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_namespace_for_instance,
    mocker
):
    """Test exporting datasets to YAML format."""
    asset_name = generate_random_string()
    instance_name = generate_random_string()
    instance_resource_group = generate_random_string()

    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    namespace_resource_group = namespace_resource["resource_group"]

    mock_asset_record = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=namespace_resource_group
    )
    mock_asset_record["properties"]["datasets"] = [
        {"name": "dataset1", "dataPoints": []}
    ]

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    expected_file_path = f"./{asset_name}_dataset.yaml"
    mock_dump = mocker.patch(
        "azext_edge.edge.util.dump_content_to_file",
        return_value=expected_file_path
    )

    from azext_edge.edge.commands_namespaces import export_namespace_asset_datasets

    result = export_namespace_asset_datasets(
        cmd=mocked_cmd,
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        format="yaml",
        output_dir="."
    )

    assert result == {"file_path": expected_file_path}
    call_kwargs = mock_dump.call_args[1]
    assert call_kwargs["extension"] == "yaml"


def test_import_namespace_asset_datasets(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_namespace_for_instance,
    mocked_check_cluster_connectivity,
    mocker
):
    """Test importing datasets from a JSON file."""
    asset_name = generate_random_string()
    instance_name = generate_random_string()
    instance_resource_group = generate_random_string()
    input_file = "/tmp/datasets.json"

    # Mock validator to skip validation
    mock_validator = mocker.Mock()
    mock_validator.validate_dataset.return_value = None
    mock_validator.validate_datapoint.return_value = None
    mocker.patch(
        "azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator.from_asset",
        return_value=mock_validator
    )

    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    namespace_resource_group = namespace_resource["resource_group"]

    # Existing asset with one dataset
    mock_asset_record = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=namespace_resource_group
    )
    mock_asset_record["properties"]["datasets"] = [
        {
            "name": "existingDataset",
            "dataPoints": [{"name": "existingDp", "dataSource": "existingSource"}]
        }
    ]

    # File contains new datasets
    file_datasets = [
        {"name": "newDataset1", "datasetConfiguration": json.dumps({"publishingInterval": 1000})},
        {"name": "newDataset2", "datasetConfiguration": json.dumps({"publishingInterval": 2000})}
    ]

    # Mock deserialize_file_content
    mock_deserialize = mocker.patch(
        "azext_edge.edge.util.deserialize_file_content",
        return_value=file_datasets
    )

    # Mock GET asset response (initial)
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    # Mock PATCH update response
    updated_asset = deepcopy(mock_asset_record)
    # Merge logic: keep existing, add new datasets
    updated_asset["properties"]["datasets"] = [
        mock_asset_record["properties"]["datasets"][0],  # existing
        file_datasets[0],  # new1
        file_datasets[1]   # new2
    ]

    mocked_responses.add(
        method=responses.PATCH,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=updated_asset,
        status=200,
        content_type="application/json",
    )

    # Mock GET asset response (final)
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=updated_asset,
        status=200,
        content_type="application/json",
    )

    from azext_edge.edge.commands_namespaces import import_namespace_asset_datasets

    result = import_namespace_asset_datasets(
        cmd=mocked_cmd,
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        input_file=input_file,
        wait_sec=0
    )

    # Verify result contains all datasets
    assert len(result) == 3
    dataset_names = [ds["name"] for ds in result]
    assert "existingDataset" in dataset_names
    assert "newDataset1" in dataset_names
    assert "newDataset2" in dataset_names

    # Verify mocks were called
    mock_deserialize.assert_called_once_with(file_path=input_file)


# ==================== EDGE CASE TESTS ====================

def test_export_dataset_datapoints_dataset_not_found(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_namespace_for_instance,
):
    """
    Test exporting datapoints when the specified dataset doesn't exist.
    WHY: Validates proper error handling when user specifies wrong dataset name.
    """
    asset_name = generate_random_string()
    dataset_name = "nonexistentDataset"
    instance_name = generate_random_string()
    instance_resource_group = generate_random_string()

    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    namespace_resource_group = namespace_resource["resource_group"]

    # Asset has no matching dataset
    mock_asset_record = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=namespace_resource_group
    )
    mock_asset_record["properties"]["datasets"] = [
        {"name": "otherDataset", "dataPoints": []}
    ]

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    from azext_edge.edge.commands_namespaces import export_namespace_asset_dataset_points

    # Should raise InvalidArgumentValueError
    with pytest.raises(InvalidArgumentValueError) as exc_info:
        export_namespace_asset_dataset_points(
            cmd=mocked_cmd,
            asset_name=asset_name,
            dataset_name=dataset_name,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
        )

    assert f"Dataset '{dataset_name}' not found" in str(exc_info.value)


def test_export_dataset_datapoints_empty_datapoints(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_namespace_for_instance,
    mocker
):
    """
    Test exporting when dataset has no datapoints.
    WHY: Ensures system handles empty collections gracefully (common in new assets).
    """
    asset_name = generate_random_string()
    dataset_name = "emptyDataset"
    instance_name = generate_random_string()
    instance_resource_group = generate_random_string()

    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    namespace_resource_group = namespace_resource["resource_group"]

    mock_asset_record = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=namespace_resource_group
    )
    mock_asset_record["properties"]["datasets"] = [
        {"name": dataset_name, "dataPoints": []}  # Empty array
    ]

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    expected_file_path = f"./{asset_name}_datapoint_{dataset_name}.json"
    mock_dump = mocker.patch(
        "azext_edge.edge.util.dump_content_to_file",
        return_value=expected_file_path
    )

    from azext_edge.edge.commands_namespaces import export_namespace_asset_dataset_points

    result = export_namespace_asset_dataset_points(
        cmd=mocked_cmd,
        asset_name=asset_name,
        dataset_name=dataset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
    )

    # Should still succeed and export empty array
    assert result == {"file_path": expected_file_path}
    call_kwargs = mock_dump.call_args[1]
    assert call_kwargs["content"] == []


def test_import_dataset_datapoints_all_duplicates(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_namespace_for_instance,
    mocked_check_cluster_connectivity,
    mocker
):
    """
    Test importing when all datapoints from file are duplicates.
    WHY: Validates skip-duplicate logic doesn't break when nothing needs importing.
    """
    asset_name = generate_random_string()
    dataset_name = "dataset1"
    instance_name = generate_random_string()
    instance_resource_group = generate_random_string()
    input_file = "/tmp/duplicates.json"

    # Mock validator to skip validation
    mock_validator = mocker.Mock()
    mock_validator.validate_datapoint.return_value = None
    mocker.patch(
        "azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator.from_asset",
        return_value=mock_validator
    )

    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    namespace_resource_group = namespace_resource["resource_group"]

    # Existing datapoints
    existing_datapoints = [
        {"name": "dp1", "dataSource": "source1"},
        {"name": "dp2", "dataSource": "source2"}
    ]

    mock_asset_record = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=namespace_resource_group
    )
    mock_asset_record["properties"]["datasets"] = [
        {"name": dataset_name, "dataPoints": existing_datapoints}
    ]

    # Mock returns same datapoints (all duplicates skipped)
    mocker.patch(
        "azext_edge.edge.providers.adr.assets._process_asset_sub_points_file_path",
        return_value=existing_datapoints
    )

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    # Update response (no changes)
    mocked_responses.add(
        method=responses.PATCH,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    from azext_edge.edge.commands_namespaces import import_namespace_asset_dataset_points

    result = import_namespace_asset_dataset_points(
        cmd=mocked_cmd,
        asset_name=asset_name,
        dataset_name=dataset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        input_file=input_file,
        wait_sec=0
    )

    # Result should be unchanged
    assert result == existing_datapoints
    assert len(result) == 2


def test_export_datasets_no_datasets(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_namespace_for_instance,
    mocker
):
    """
    Test exporting when asset has no datasets at all.
    WHY: New assets or certain asset types may have no datasets - must handle gracefully.
    """
    asset_name = generate_random_string()
    instance_name = generate_random_string()
    instance_resource_group = generate_random_string()

    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    namespace_resource_group = namespace_resource["resource_group"]

    mock_asset_record = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=namespace_resource_group
    )
    mock_asset_record["properties"]["datasets"] = []  # No datasets

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    expected_file_path = f"./{asset_name}_dataset.json"
    mock_dump = mocker.patch(
        "azext_edge.edge.util.dump_content_to_file",
        return_value=expected_file_path
    )

    from azext_edge.edge.commands_namespaces import export_namespace_asset_datasets

    result = export_namespace_asset_datasets(
        cmd=mocked_cmd,
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
    )

    assert result == {"file_path": expected_file_path}
    call_kwargs = mock_dump.call_args[1]
    assert call_kwargs["content"] == []


def test_import_datasets_duplicate_skip(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_namespace_for_instance,
    mocked_check_cluster_connectivity,
    mocker
):
    """
    Test that duplicate datasets are properly skipped during import.
    WHY: Prevents accidental overwrites - user should see warning, data preserved.
    """
    asset_name = generate_random_string()
    instance_name = generate_random_string()
    instance_resource_group = generate_random_string()
    input_file = "/tmp/datasets_with_dup.json"

    # Mock validator to skip validation
    mock_validator = mocker.Mock()
    mock_validator.validate_dataset.return_value = None
    mock_validator.validate_datapoint.return_value = None
    mocker.patch(
        "azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator.from_asset",
        return_value=mock_validator
    )

    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    namespace_resource_group = namespace_resource["resource_group"]

    existing_dataset = {
        "name": "dataset1",
        "dataPoints": [{"name": "existingDp", "dataSource": "existingSource"}]
    }

    mock_asset_record = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=namespace_resource_group
    )
    mock_asset_record["properties"]["datasets"] = [existing_dataset]

    # File contains: 1 duplicate (dataset1) + 1 new (dataset2)
    file_datasets = [
        {"name": "dataset1", "datasetConfiguration": json.dumps({"publishingInterval": 9999})},  # Duplicate
        {"name": "dataset2", "datasetConfiguration": json.dumps({"publishingInterval": 2000})}   # New
    ]

    mocker.patch(
        "azext_edge.edge.util.deserialize_file_content",
        return_value=file_datasets
    )

    # Mock logger to verify warning is logged
    mock_logger = mocker.patch("azext_edge.edge.providers.adr.namespace_assets.logger")

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    # Updated asset: existing dataset unchanged, only new dataset added
    updated_asset = deepcopy(mock_asset_record)
    updated_asset["properties"]["datasets"] = [
        existing_dataset,  # Original preserved
        {"name": "dataset2", "dataPoints": [], "datasetConfiguration": json.dumps({"publishingInterval": 2000})}
    ]

    mocked_responses.add(
        method=responses.PATCH,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=updated_asset,
        status=200,
        content_type="application/json",
    )

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=updated_asset,
        status=200,
        content_type="application/json",
    )

    from azext_edge.edge.commands_namespaces import import_namespace_asset_datasets

    result = import_namespace_asset_datasets(
        cmd=mocked_cmd,
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        input_file=input_file,
        wait_sec=0
    )

    # Verify: 2 datasets total, duplicate was skipped
    assert len(result) == 2
    dataset_names = [ds["name"] for ds in result]
    assert "dataset1" in dataset_names
    assert "dataset2" in dataset_names

    # Verify existing dataset is unchanged (not overwritten)
    existing_in_result = next(ds for ds in result if ds["name"] == "dataset1")
    assert existing_in_result == existing_dataset

    # Verify warning was logged for duplicate
    mock_logger.warning.assert_called_once()
    warning_msg = mock_logger.warning.call_args[0][0]
    assert "dataset1" in warning_msg
    assert "already exists" in warning_msg


def test_export_datasets_with_complex_configurations(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_namespace_for_instance,
    mocker
):
    """
    Test exporting datasets with complex nested configurations.
    WHY: Real-world datasets have nested JSON configs - ensure proper serialization.
    """
    asset_name = generate_random_string()
    instance_name = generate_random_string()
    instance_resource_group = generate_random_string()

    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    namespace_resource_group = namespace_resource["resource_group"]

    # Complex dataset with nested configurations
    complex_config = {
        "publishingInterval": 1000,
        "samplingInterval": 500,
        "queueSize": 10,
        "advanced": {
            "compression": "gzip",
            "encryption": {"enabled": True, "algorithm": "AES256"}
        }
    }

    mock_asset_record = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=namespace_resource_group
    )
    mock_asset_record["properties"]["datasets"] = [
        {
            "name": "complexDataset",
            "datasetConfiguration": json.dumps(complex_config),
            "dataPoints": [{"name": "dp1", "dataSource": "src1"}]  # Will be removed in export
        }
    ]

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    expected_file_path = f"./{asset_name}_dataset.json"
    mock_dump = mocker.patch(
        "azext_edge.edge.util.dump_content_to_file",
        return_value=expected_file_path
    )

    from azext_edge.edge.commands_namespaces import export_namespace_asset_datasets

    result = export_namespace_asset_datasets(
        cmd=mocked_cmd,
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
    )

    # Verify export succeeded
    assert result == {"file_path": expected_file_path}

    # Verify complex configuration is preserved but dataPoints removed
    exported_datasets = mock_dump.call_args[1]["content"]
    assert len(exported_datasets) == 1
    assert "dataPoints" not in exported_datasets[0]
    assert exported_datasets[0]["datasetConfiguration"] == json.dumps(complex_config)


def test_import_dataset_datapoints_into_empty_dataset(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_namespace_for_instance,
    mocked_check_cluster_connectivity,
    mocker
):
    """
    Test importing datapoints into a dataset that has no existing datapoints.
    WHY: Common scenario for newly created datasets - all imports should succeed.
    """
    asset_name = generate_random_string()
    dataset_name = "newDataset"
    instance_name = generate_random_string()
    instance_resource_group = generate_random_string()
    input_file = "/tmp/first_datapoints.json"

    # Mock validator to skip validation
    mock_validator = mocker.Mock()
    mock_validator.validate_datapoint.return_value = None
    mocker.patch(
        "azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator.from_asset",
        return_value=mock_validator
    )

    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    namespace_resource_group = namespace_resource["resource_group"]

    # Dataset with no datapoints
    mock_asset_record = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=namespace_resource_group
    )
    mock_asset_record["properties"]["datasets"] = [
        {"name": dataset_name, "dataPoints": []}  # Empty
    ]

    # File contains first datapoints
    new_datapoints = [
        {"name": "dp1", "dataSource": "source1"},
        {"name": "dp2", "dataSource": "source2"},
        {"name": "dp3", "dataSource": "source3"}
    ]

    mocker.patch(
        "azext_edge.edge.providers.adr.assets._process_asset_sub_points_file_path",
        return_value=new_datapoints
    )

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    updated_asset = deepcopy(mock_asset_record)
    updated_asset["properties"]["datasets"][0]["dataPoints"] = new_datapoints

    mocked_responses.add(
        method=responses.PATCH,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=updated_asset,
        status=200,
        content_type="application/json",
    )

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=updated_asset,
        status=200,
        content_type="application/json",
    )

    from azext_edge.edge.commands_namespaces import import_namespace_asset_dataset_points

    result = import_namespace_asset_dataset_points(
        cmd=mocked_cmd,
        asset_name=asset_name,
        dataset_name=dataset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        input_file=input_file,
        wait_sec=0
    )

    # All datapoints should be imported
    assert result == new_datapoints
    assert len(result) == 3


# ==================== VALIDATION TESTS ====================

def test_validate_datapoint_invalid_json_configuration(mocker):
    """
    Test that datapoint with invalid JSON configuration raises ValidationError.
    WHY: Prevents importing malformed configuration that would break the system.
    """
    from azext_edge.edge.providers.adr.validator import ConnectorMetadataValidator

    mock_cmd = mocker.Mock()
    validator = ConnectorMetadataValidator(
        cmd=mock_cmd,
        resource_group_name="test-rg",
        instance_name="test-instance",
        endpoint_type="Microsoft.OpcUa",
        endpoint_version="1.0"
    )

    # Mock metadata to return empty (skip schema validation, focus on JSON parsing)
    validator.metadata = {}

    # Datapoint with invalid JSON string in configuration
    invalid_datapoint = {
        "name": "temperature1",
        "dataSource": "ns=2;i=1001",
        "dataPointConfiguration": "{invalid json here"  # Malformed JSON
    }

    with pytest.raises(ValidationError) as exc_info:
        validator.validate_datapoint(invalid_datapoint)

    assert "Invalid dataPointConfiguration JSON" in str(exc_info.value)
    assert "temperature1" in str(exc_info.value)


def test_validate_dataset_invalid_json_configuration(mocker):
    """
    Test that dataset with invalid JSON configuration raises ValidationError.
    WHY: Ensures data integrity at import/create time.
    """
    from azext_edge.edge.providers.adr.validator import ConnectorMetadataValidator

    mock_cmd = mocker.Mock()
    validator = ConnectorMetadataValidator(
        cmd=mock_cmd,
        resource_group_name="test-rg",
        instance_name="test-instance",
        endpoint_type="Microsoft.OpcUa",
        endpoint_version="1.0"
    )

    validator.metadata = {}

    invalid_dataset = {
        "name": "dataset1",
        "dataSource": "ns=2;i=1000",
        "datasetConfiguration": '{"publishingInterval": 1000'  # Missing closing brace
    }

    with pytest.raises(ValidationError) as exc_info:
        validator.validate_dataset(invalid_dataset)

    assert "Invalid datasetConfiguration JSON" in str(exc_info.value)


def test_validate_datapoint_with_schema_validation(mocker):
    """
    Test datapoint validation against a JSON schema.
    WHY: Validates that configuration follows connector-specific requirements.
    """
    from azext_edge.edge.providers.adr.validator import ConnectorMetadataValidator

    mock_cmd = mocker.Mock()
    validator = ConnectorMetadataValidator(
        cmd=mock_cmd,
        resource_group_name="test-rg",
        instance_name="test-instance",
        endpoint_type="Microsoft.OpcUa",
        endpoint_version="1.0"
    )

    # Mock metadata with schema
    validator.metadata = {
        "inboundEndpoints": [
            {
                "endpointType": "Microsoft.OpcUa",
                "datasets": {
                    "dataPointConfigurationSchema": {
                        "type": "object",
                        "properties": {
                            "samplingInterval": {"type": "integer", "minimum": 0},
                            "queueSize": {"type": "integer", "minimum": 1}
                        },
                        "required": ["samplingInterval"]
                    }
                }
            }
        ]
    }

    # Valid datapoint
    valid_datapoint = {
        "name": "temperature",
        "dataSource": "ns=2;i=1001",
        "dataPointConfiguration": json.dumps({"samplingInterval": 1000, "queueSize": 10})
    }

    # Should not raise
    validator.validate_datapoint(valid_datapoint)

    # Invalid datapoint - missing required field
    invalid_datapoint = {
        "name": "pressure",
        "dataSource": "ns=2;i=1002",
        "dataPointConfiguration": json.dumps({"queueSize": 10})  # Missing samplingInterval
    }

    with pytest.raises(ValidationError) as exc_info:
        validator.validate_datapoint(invalid_datapoint)

    assert "Datapoint configuration is invalid" in str(exc_info.value)


def test_validate_datapoint_negative_sampling_interval(mocker):
    """
    Test that negative sampling interval is rejected by schema validation.
    WHY: Negative values don't make sense for timing parameters.
    """
    from azext_edge.edge.providers.adr.validator import ConnectorMetadataValidator

    mock_cmd = mocker.Mock()
    validator = ConnectorMetadataValidator(
        cmd=mock_cmd,
        resource_group_name="test-rg",
        instance_name="test-instance",
        endpoint_type="Microsoft.OpcUa",
        endpoint_version="1.0"
    )

    validator.metadata = {
        "inboundEndpoints": [
            {
                "endpointType": "Microsoft.OpcUa",
                "datasets": {
                    "dataPointConfigurationSchema": {
                        "type": "object",
                        "properties": {
                            "samplingInterval": {"type": "integer", "minimum": 0}
                        }
                    }
                }
            }
        ]
    }

    invalid_datapoint = {
        "name": "temp",
        "dataSource": "ns=2;i=1001",
        "dataPointConfiguration": json.dumps({"samplingInterval": -1000})  # Negative value
    }

    with pytest.raises(ValidationError) as exc_info:
        validator.validate_datapoint(invalid_datapoint)

    assert "Datapoint configuration is invalid" in str(exc_info.value)


def test_validate_dataset_with_schema_validation(mocker):
    """
    Test dataset validation against a JSON schema.
    WHY: Ensures dataset configuration meets connector requirements.
    """
    from azext_edge.edge.providers.adr.validator import ConnectorMetadataValidator

    mock_cmd = mocker.Mock()
    validator = ConnectorMetadataValidator(
        cmd=mock_cmd,
        resource_group_name="test-rg",
        instance_name="test-instance",
        endpoint_type="Microsoft.OpcUa",
        endpoint_version="1.0"
    )

    validator.metadata = {
        "inboundEndpoints": [
            {
                "endpointType": "Microsoft.OpcUa",
                "datasets": {
                    "datasetConfigurationSchema": {
                        "type": "object",
                        "properties": {
                            "publishingInterval": {"type": "integer", "minimum": 100},
                            "keyFrameCount": {"type": "integer", "minimum": 1}
                        },
                        "required": ["publishingInterval"]
                    }
                }
            }
        ]
    }

    # Valid dataset
    valid_dataset = {
        "name": "dataset1",
        "dataSource": "ns=2;i=1000",
        "datasetConfiguration": json.dumps({"publishingInterval": 1000, "keyFrameCount": 5})
    }

    validator.validate_dataset(valid_dataset)

    # Invalid dataset - publishingInterval too low
    invalid_dataset = {
        "name": "dataset2",
        "dataSource": "ns=2;i=1000",
        "datasetConfiguration": json.dumps({"publishingInterval": 50})  # Below minimum
    }

    with pytest.raises(ValidationError) as exc_info:
        validator.validate_dataset(invalid_dataset)

    assert "Dataset configuration is invalid" in str(exc_info.value)


def test_validate_datapoint_without_configuration(mocker):
    """
    Test that datapoint without configuration field is skipped gracefully.
    WHY: Not all datapoints require custom configuration, should not fail validation.
    """
    from azext_edge.edge.providers.adr.validator import ConnectorMetadataValidator

    mock_cmd = mocker.Mock()
    validator = ConnectorMetadataValidator(
        cmd=mock_cmd,
        resource_group_name="test-rg",
        instance_name="test-instance",
        endpoint_type="Microsoft.OpcUa",
        endpoint_version="1.0"
    )

    validator.metadata = {
        "inboundEndpoints": [
            {
                "endpointType": "Microsoft.OpcUa",
                "datasets": {
                    "dataPointConfigurationSchema": {
                        "type": "object",
                        "properties": {"samplingInterval": {"type": "integer"}},
                        "required": ["samplingInterval"]
                    }
                }
            }
        ]
    }

    # Datapoint without configuration - should not raise error
    datapoint_no_config = {
        "name": "temperature",
        "dataSource": "ns=2;i=1001"
        # No dataPointConfiguration field
    }

    # Should not raise
    validator.validate_datapoint(datapoint_no_config)


def test_validate_datapoint_with_empty_configuration(mocker):
    """
    Test that datapoint with empty/null configuration is handled gracefully.
    WHY: Empty configurations are valid when no custom settings are needed.
    """
    from azext_edge.edge.providers.adr.validator import ConnectorMetadataValidator

    mock_cmd = mocker.Mock()
    validator = ConnectorMetadataValidator(
        cmd=mock_cmd,
        resource_group_name="test-rg",
        instance_name="test-instance",
        endpoint_type="Microsoft.Custom",
        endpoint_version="1.0"
    )

    validator.metadata = {}

    # Datapoint with empty string configuration
    datapoint_empty = {
        "name": "sensor1",
        "dataSource": "sensor/data",
        "dataPointConfiguration": ""
    }

    # Should not raise
    validator.validate_datapoint(datapoint_empty)

    # Datapoint with None configuration
    datapoint_none = {
        "name": "sensor2",
        "dataSource": "sensor/data2",
        "dataPointConfiguration": None
    }

    # Should not raise
    validator.validate_datapoint(datapoint_none)


def test_validate_datapoint_wrong_type_in_configuration(mocker):
    """
    Test that wrong data types in configuration are rejected.
    WHY: Type safety prevents runtime errors in the connector.
    """
    from azext_edge.edge.providers.adr.validator import ConnectorMetadataValidator

    mock_cmd = mocker.Mock()
    validator = ConnectorMetadataValidator(
        cmd=mock_cmd,
        resource_group_name="test-rg",
        instance_name="test-instance",
        endpoint_type="Microsoft.OpcUa",
        endpoint_version="1.0"
    )

    validator.metadata = {
        "inboundEndpoints": [
            {
                "endpointType": "Microsoft.OpcUa",
                "datasets": {
                    "dataPointConfigurationSchema": {
                        "type": "object",
                        "properties": {
                            "samplingInterval": {"type": "integer"},
                            "enabled": {"type": "boolean"}
                        }
                    }
                }
            }
        ]
    }

    # String instead of integer
    wrong_type_datapoint = {
        "name": "temp",
        "dataSource": "ns=2;i=1001",
        "dataPointConfiguration": json.dumps({"samplingInterval": "1000"})  # String not int
    }

    with pytest.raises(ValidationError) as exc_info:
        validator.validate_datapoint(wrong_type_datapoint)

    assert "Datapoint configuration is invalid" in str(exc_info.value)


def test_import_datapoints_validation_failure_prevents_import(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_namespace_for_instance,
    mocked_check_cluster_connectivity,
    mocker
):
    """
    Test that validation errors prevent datapoint import.
    WHY: Critical - must not persist invalid data to the system.
    """
    asset_name = generate_random_string()
    dataset_name = "dataset1"
    instance_name = generate_random_string()
    instance_resource_group = generate_random_string()
    input_file = "/tmp/invalid_datapoints.json"

    # Mock validator that raises ValidationError
    mock_validator = mocker.Mock()
    mock_validator.validate_datapoint.side_effect = ValidationError("Invalid configuration: samplingInterval must be positive")

    mocker.patch(
        "azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator.from_asset",
        return_value=mock_validator
    )

    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    namespace_resource_group = namespace_resource["resource_group"]

    mock_asset_record = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=namespace_resource_group
    )
    mock_asset_record["properties"]["datasets"] = [
        {"name": dataset_name, "dataPoints": []}
    ]

    # Mock file processing to return invalid datapoints
    invalid_datapoints = [
        {"name": "dp1", "dataSource": "source1", "dataPointConfiguration": json.dumps({"samplingInterval": -1000})}
    ]

    mocker.patch(
        "azext_edge.edge.providers.adr.assets._process_asset_sub_points_file_path",
        return_value=invalid_datapoints
    )

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    from azext_edge.edge.commands_namespaces import import_namespace_asset_dataset_points

    # Should raise ValidationError before any PATCH is attempted
    with pytest.raises(ValidationError) as exc_info:
        import_namespace_asset_dataset_points(
            cmd=mocked_cmd,
            asset_name=asset_name,
            dataset_name=dataset_name,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
            input_file=input_file,
            wait_sec=0
        )

    assert "validation" in str(exc_info.value).lower()
    # Verify no PATCH was attempted (only GET should have been called)
    assert len(mocked_responses.calls) == 1
    assert mocked_responses.calls[0].request.method == "GET"


def test_import_datasets_validation_failure_prevents_import(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_namespace_for_instance,
    mocked_check_cluster_connectivity,
    mocker
):
    """
    Test that validation errors prevent dataset import.
    WHY: Validates that invalid datasets are rejected before persistence.
    """
    asset_name = generate_random_string()
    instance_name = generate_random_string()
    instance_resource_group = generate_random_string()
    input_file = "/tmp/invalid_datasets.json"

    # Mock validator that raises ValidationError
    mock_validator = mocker.Mock()
    mock_validator.validate_dataset.side_effect = ValidationError("Invalid dataset: publishingInterval too low")
    mock_validator.validate_datapoint.return_value = None

    mocker.patch(
        "azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator.from_asset",
        return_value=mock_validator
    )

    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    namespace_resource_group = namespace_resource["resource_group"]

    mock_asset_record = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=namespace_resource_group
    )
    mock_asset_record["properties"]["datasets"] = []

    invalid_datasets = [
        {
            "name": "dataset1",
            "datasetConfiguration": json.dumps({"publishingInterval": 10})  # Too low
        }
    ]

    mocker.patch(
        "azext_edge.edge.util.deserialize_file_content",
        return_value=invalid_datasets
    )

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=namespace_resource_group
        ),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    from azext_edge.edge.commands_namespaces import import_namespace_asset_datasets

    with pytest.raises(ValidationError) as exc_info:
        import_namespace_asset_datasets(
            cmd=mocked_cmd,
            asset_name=asset_name,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
            input_file=input_file,
            wait_sec=0
        )

    assert "validation" in str(exc_info.value).lower()
    # Only GET should have been called
    assert len(mocked_responses.calls) == 1


def test_validate_datapoint_additional_properties_allowed(mocker):
    """
    Test that additional properties not in schema are allowed (if not strict).
    WHY: Forward compatibility - new connector versions may add fields.
    """
    from azext_edge.edge.providers.adr.validator import ConnectorMetadataValidator

    mock_cmd = mocker.Mock()
    validator = ConnectorMetadataValidator(
        cmd=mock_cmd,
        resource_group_name="test-rg",
        instance_name="test-instance",
        endpoint_type="Microsoft.OpcUa",
        endpoint_version="1.0"
    )

    # Schema without additionalProperties: false
    validator.metadata = {
        "inboundEndpoints": [
            {
                "endpointType": "Microsoft.OpcUa",
                "datasets": {
                    "dataPointConfigurationSchema": {
                        "type": "object",
                        "properties": {
                            "samplingInterval": {"type": "integer"}
                        }
                    }
                }
            }
        ]
    }

    # Datapoint with extra field not in schema
    datapoint_with_extra = {
        "name": "temp",
        "dataSource": "ns=2;i=1001",
        "dataPointConfiguration": json.dumps({
            "samplingInterval": 1000,
            "customField": "value"  # Not in schema
        })
    }

    # Should not raise (additional properties allowed by default)
    validator.validate_datapoint(datapoint_with_extra)


def test_validator_from_asset_missing_device_ref(mocker):
    """
    Test validator creation fails when asset has no deviceRef.
    WHY: deviceRef is required to determine endpoint type for validation.
    """
    from azext_edge.edge.providers.adr.validator import ConnectorMetadataValidator

    mock_cmd = mocker.Mock()

    # Asset without deviceRef
    invalid_asset = {
        "id": "/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.DeviceRegistry/namespaces/ns1/assets/asset1",
        "properties": {
            "adrNamespace": "/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.DeviceRegistry/namespaces/ns1"
            # Missing deviceRef
        }
    }

    with pytest.raises(ValidationError) as exc_info:
        ConnectorMetadataValidator.from_asset(mock_cmd, invalid_asset)

    assert "deviceRef" in str(exc_info.value).lower()


def test_validator_from_asset_missing_namespace(mocker):
    """
    Test validator creation fails when asset has no adrNamespace.
    WHY: adrNamespace is required to locate the device.
    """
    from azext_edge.edge.providers.adr.validator import ConnectorMetadataValidator

    mock_cmd = mocker.Mock()

    invalid_asset = {
        "id": "/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.DeviceRegistry/namespaces/ns1/assets/asset1",
        "properties": {
            "deviceRef": {
                "deviceName": "device1",
                "endpointName": "endpoint1"
            }
            # Missing adrNamespace
        }
    }

    with pytest.raises(ValidationError) as exc_info:
        ConnectorMetadataValidator.from_asset(mock_cmd, invalid_asset)

    assert "adrNamespace" in str(exc_info.value).lower()


def test_validate_event_with_invalid_json(mocker):
    """
    Test that event with invalid JSON configuration raises ValidationError.
    WHY: Ensures event configuration integrity.
    """
    from azext_edge.edge.providers.adr.validator import ConnectorMetadataValidator

    mock_cmd = mocker.Mock()
    validator = ConnectorMetadataValidator(
        cmd=mock_cmd,
        resource_group_name="test-rg",
        instance_name="test-instance",
        endpoint_type="Microsoft.OpcUa",
        endpoint_version="1.0"
    )

    validator.metadata = {}

    invalid_event = {
        "name": "alarm1",
        "eventConfiguration": '{"queueSize": 10'  # Missing closing brace
    }

    with pytest.raises(ValidationError) as exc_info:
        validator.validate_event(invalid_event)

    assert "Invalid eventConfiguration JSON" in str(exc_info.value)
    assert "alarm1" in str(exc_info.value)


def test_validate_no_schema_warning(mocker):
    """
    Test that validation is skipped with warning when no schema is available.
    WHY: Graceful degradation - system should work even without schema.
    """
    from azext_edge.edge.providers.adr.validator import ConnectorMetadataValidator

    mock_cmd = mocker.Mock()
    validator = ConnectorMetadataValidator(
        cmd=mock_cmd,
        resource_group_name="test-rg",
        instance_name="test-instance",
        endpoint_type="Microsoft.Custom",  # No schema available
        endpoint_version="1.0"
    )

    # Empty metadata - no schema
    validator.metadata = {}

    # Mock logger to verify warning
    mock_logger = mocker.patch("azext_edge.edge.providers.adr.validator.logger")

    datapoint = {
        "name": "sensor1",
        "dataSource": "data/source",
        "dataPointConfiguration": json.dumps({"customField": "value"})
    }

    # Should not raise, just warn
    validator.validate_datapoint(datapoint)

    # Verify warning was logged
    assert mock_logger.warning.called
    warning_msg = str(mock_logger.warning.call_args)
    assert "No datapoint schema found" in warning_msg or "skipping validation" in warning_msg.lower()
