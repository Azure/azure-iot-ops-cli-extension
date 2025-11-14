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

from azure.cli.core.azclierror import InvalidArgumentValueError
from azext_edge.edge.commands_namespaces import (
    create_namespace_custom_asset,
    create_namespace_media_asset,
    create_namespace_onvif_asset,
    create_namespace_opcua_asset,
    create_namespace_rest_asset,
    create_namespace_sse_asset,
    show_namespace_asset,
    delete_namespace_asset,
    update_namespace_custom_asset,
    update_namespace_media_asset,
    update_namespace_onvif_asset,
    update_namespace_opcua_asset,
    update_namespace_rest_asset,
    update_namespace_sse_asset,
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
    ["sse", create_namespace_sse_asset]
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
        "sse": DeviceEndpointType.MEDIA.value
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
