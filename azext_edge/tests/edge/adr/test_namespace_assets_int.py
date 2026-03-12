# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from typing import List
from azext_edge.edge.util.common import parse_kvp_nargs

from ...generators import generate_random_string
from ...helpers import run
from .namespace_helpers import (
    assert_event_properties,
    assert_management_group_action_properties,
    assert_management_group_properties,
    assert_stream_properties,
    create_config_file,
    assert_point_properties,
    assert_dataset_properties
)

pytestmark = pytest.mark.rpsaas


def test_namespace_asset_smoke_test(require_init, tracked_resources: List[str], tracked_files: List[str]):
    """Smoke test for namespace asset operations using custom asset type."""
    # 12 put/patch/delete calls
    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    custom_location = require_init["customLocationId"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name_custom = f"custom-{generate_random_string(8)}"
    asset_name = f"custom-{generate_random_string(8, force_lower=True)}"

    # Tags and attributes
    common_tags = {"env": "test", "purpose": "automation"}
    common_attrs = ["location=building1", "floor=3"]

    # Create Device
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    # Create device endpoints
    for endpoint_name, endpoint_type in [
        (endpoint_name_custom, "custom")
    ]:
        command = (
            f"az iot ops ns device endpoint inbound add {endpoint_type} --name {endpoint_name} "
            f"--instance {instance_name} -g {resource_group} --device {device_name} "
            f"--endpoint-address 'http://192.168.1.100:8000/onvif/device_service'"
        )
        if endpoint_type == "custom":
            command += " --endpoint-type custom"
        run(command)

    # Create Custom asset with maximum inputs
    asset_custom = run(
        f"az iot ops ns asset custom create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name_custom} "
        "--description \"Custom Device\" --display-name \"Multi-Sensor\" --model \"Custom-MS100\" "
        "--manufacturer \"CustomDevices\" --serial-number \"CUST123456\" "
        f"--dataset-config \"{{\\\"publishingInterval\\\": 1000}}\" "
        f"--event-config \"{{\\\"queueSize\\\": 5}}\" "
        "--dataset-dest topic=\"custom/data\" qos=Qos1 retain=Keep ttl=3600 "
        "--event-dest topic=\"custom/events\" qos=Qos0 retain=Never ttl=3600 "
        f"--attribute {' '.join(common_attrs)} --tags {' '.join([f'{k}={v}' for k, v in common_tags.items()])}"
    )
    tracked_resources.append(asset_custom["id"])

    assert_asset_properties(
        asset_custom,
        name=asset_name,
        device=device_name,
        endpoint=endpoint_name_custom,
        description="Custom Device",
        display_name="Multi-Sensor",
        custom_location=custom_location
    )

    # Test show operation for an asset
    shown_asset = run(
        f"az iot ops ns asset show --name {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )

    assert_asset_properties(
        shown_asset,
        name=asset_name,
        device=device_name,
        endpoint=endpoint_name_custom,
    )

    # Update Custom asset
    updated_custom = run(
        f"az iot ops ns asset custom update --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --dataset-config \"{{\\\"publishingInterval\\\": 2000}}\" "
        f"--event-config \"{{\\\"queueSize\\\": 10}}\" --software-revision \"v2.0\" "

    )

    assert_asset_properties(
        updated_custom,
        name=asset_name,
        software_revision="v2.0",
    )

    # Test query operation
    queried_assets = run(
        "az iot ops ns asset query"
    )

    asset_names = [asset["name"] for asset in queried_assets]
    assert asset_name in asset_names

    queried_assets = run(
        f"az iot ops ns asset query -i {instance_name} -g {resource_group}"
    )

    asset_names = [asset["name"] for asset in queried_assets]
    assert asset_name in asset_names

    # DATASET
    # add a dataset to the asset
    dataset_name = "default"
    dataset_destinations = "topic=factory/temperature qos=Qos1 retain=Keep ttl=3600"
    custom_config_path, custom_config = create_config_file(tracked_files)

    # Add custom asset dataset
    dataset_result = run(
        f"az iot ops ns asset custom dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name} "
        f"--destination {dataset_destinations} "
        f"--config {custom_config_path}"
    )

    assert_dataset_properties(
        dataset_result,
        name=dataset_name,
        asset_type="custom",
        custom_configuration=custom_config
    )

    # add point
    datapoint_name_1 = f"point{generate_random_string(size=4)}"
    datapoint_data_source_1 = "sensor/temperature/value"
    custom_config_path, custom_config = create_config_file(tracked_files)

    datapoint_result_1 = run(
        f"az iot ops ns asset custom datapoint add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
        f"--name {datapoint_name_1} --data-source {datapoint_data_source_1} "
        f"--config {custom_config_path}"
    )

    assert_point_properties(
        datapoint_result_1,
        name=datapoint_name_1,
        data_source=datapoint_data_source_1
    )

    # show dataset
    shown_dataset = run(
        f"az iot ops ns asset custom dataset show --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name}"
    )

    assert_dataset_properties(
        shown_dataset,
        name=dataset_name,
        asset_type="custom"
    )

    # list dataset points
    datapoints_list = run(
        f"az iot ops ns asset custom datapoint list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name}"
    )

    datapoint_names = [dp["name"] for dp in datapoints_list]
    assert datapoint_name_1 in datapoint_names
    assert len(datapoints_list) == 1

    # EVENT
    # First create an event group
    event_group_name = f"event{generate_random_string(size=4)}"
    custom_config_path, custom_config = create_config_file(tracked_files)
    event_destinations = "topic=factory/custom/events qos=Qos1 retain=Never ttl=3600"

    event_group_result = run(
        f"az iot ops ns asset custom event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name} "
        f"--config {custom_config_path} --destination {event_destinations}"
    )

    assert_event_properties(
        event_group_result,
        name=event_group_name,
        custom_configuration=custom_config,
    )

    # Now add an event to the event group
    event_name = f"event{generate_random_string(size=4)}"
    custom_config_path, custom_config = create_config_file(tracked_files)

    event_result = run(
        f"az iot ops ns asset custom event add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name} --name {event_name} "
        f"--config {custom_config_path}"
    )

    assert_point_properties(
        event_result,
        name=event_name,
        custom_configuration=custom_config
    )

    # add event point
    datapoint_name_2 = f"point{generate_random_string(size=4)}"
    datapoint_data_source = "temperature.severity"
    custom_config_path, custom_config = create_config_file(tracked_files)

    datapoint_result = run(
        f"az iot ops ns asset custom event add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name} --name {datapoint_name_2} "
        f"--data-source {datapoint_data_source} --config {custom_config_path}"
    )

    assert_point_properties(
        datapoint_result,
        name=datapoint_name_2,
        data_source=datapoint_data_source,
        custom_configuration=custom_config
    )

    # STREAM
    # add stream
    stream_name = f"stream{generate_random_string(size=4)}"
    custom_config_path, custom_config = create_config_file(tracked_files)
    stream_destinations = "topic=factory/custom/streams qos=Qos1 retain=Never ttl=3600"

    stream_result = run(
        f"az iot ops ns asset custom stream add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {stream_name} "
        f"--config {custom_config_path} --destination {stream_destinations}"
    )

    assert_stream_properties(
        stream_result,
        name=stream_name,
        custom_configuration=custom_config,
    )

    # MANAGEMENT GROUP
    # add management group
    mgmt_group_name = f"mgmt-{generate_random_string(8)}"
    default_topic = "factory/custom/management/responses"
    default_timeout = 30
    custom_config_path, custom_config = create_config_file(tracked_files)

    mgmt_group_result = run(
        f"az iot ops ns asset custom mgmt-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {mgmt_group_name} "
        f"--default-topic {default_topic} --default-timeout {default_timeout} --config {custom_config_path}"
    )

    assert_management_group_properties(
        mgmt_group_result,
        name=mgmt_group_name,
        default_topic=default_topic,
        default_timeout=default_timeout,
        custom_configuration=custom_config,
    )

    # add management group action
    action_name = f"action-{generate_random_string(6)}"
    action_target_uri = "/mgmt/device_service?profile=startProduction"
    action_type = "Call"
    action_timeout = 30
    action_topic = "factory/opcua/actions/production"

    action_result = run(
        f"az iot ops ns asset opcua mgmt-action add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --group {mgmt_group_name} --name {action_name} "
        f"--target-uri {action_target_uri} --action-type {action_type} --timeout {action_timeout} "
        f"--topic {action_topic}"
    )

    assert_management_group_action_properties(
        action_result,
        name=action_name,
        target_uri=action_target_uri,
        action_type=action_type,
        timeout=action_timeout,
        topic=action_topic
    )

    # Test delete operation
    run(
        f"az iot ops ns asset delete --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} -y"
    )


def test_namespace_asset_1p_types(require_init, tracked_resources: List[str]):
    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    custom_location = require_init["customLocationId"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name_onvif = f"onvif-{generate_random_string(8)}"
    endpoint_name_opcua = f"opcua-{generate_random_string(8)}"
    endpoint_name_media = f"media-{generate_random_string(8)}"
    endpoint_name_rest = f"rest-{generate_random_string(8)}"
    endpoint_name_sse = f"sse-{generate_random_string(8)}"
    endpoint_name_mqtt = f"mqtt-{generate_random_string(8)}"
    asset_name_onvif = f"onvif-{generate_random_string(8, force_lower=True)}"
    asset_name_opcua = f"opcua-{generate_random_string(8, force_lower=True)}"
    asset_name_media = f"media-{generate_random_string(8, force_lower=True)}"
    asset_name_rest = f"rest-{generate_random_string(8, force_lower=True)}"
    asset_name_sse = f"sse-{generate_random_string(8, force_lower=True)}"
    asset_name_mqtt = f"mqtt-{generate_random_string(8, force_lower=True)}"

    # Tags and attributes
    common_tags = {"env": "test", "purpose": "automation"}
    common_attrs = ["location=building1", "floor=3"]

    # Create Device
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    # Create device endpoints
    for endpoint_name, endpoint_type in [
        (endpoint_name_onvif, "onvif"),
        (endpoint_name_opcua, "opcua"),
        (endpoint_name_media, "media"),
        (endpoint_name_rest, "rest"),
        (endpoint_name_sse, "sse"),
        (endpoint_name_mqtt, "mqtt"),
    ]:
        command = (
            f"az iot ops ns device endpoint inbound add {endpoint_type} --name {endpoint_name} "
            f"--instance {instance_name} -g {resource_group} --device {device_name} "
        )
        if endpoint_type == "mqtt":
            command += "--endpoint-address 'aio-broker:18883'"
        else:
            command += "--endpoint-address 'http://192.168.1.100:8000/onvif/device_service'"
        if endpoint_type == "custom":
            command += " --endpoint-type custom"
        run(command)

    # 1. Create ONVIF asset with maximum inputs
    asset_onvif = run(
        f"az iot ops ns asset onvif create --name {asset_name_onvif} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name_onvif} "
        "--description \"ONVIF Camera\" --display-name \"Entrance Camera\" --model \"Camera-X1\" "
        "--manufacturer \"SecurityCo\" --serial-number \"CAM123456\" "
        "--documentation-uri \"https://example.com/docs/camera\" "
        "--external-asset-id \"EXT-CAM-01\" --hardware-revision \"v1.2\" "
        f"--attribute {' '.join(common_attrs)} --tags {' '.join([f'{k}={v}' for k, v in common_tags.items()])}"
    )
    tracked_resources.append(asset_onvif["id"])

    assert_asset_properties(
        asset_onvif,
        name=asset_name_onvif,
        device=device_name,
        endpoint=endpoint_name_onvif,
        description="ONVIF Camera",
        display_name="Entrance Camera",
        model="Camera-X1",
        manufacturer="SecurityCo",
        serial_number="CAM123456",
        documentation_uri="https://example.com/docs/camera",
        external_asset_id="EXT-CAM-01",
        hardware_revision="v1.2",
        tags=common_tags,
        attributes=common_attrs,
        custom_location=custom_location
    )

    # 2. Create OPCUA asset with maximum inputs
    asset_opcua = run(
        f"az iot ops ns asset opcua create --name {asset_name_opcua} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name_opcua} "
        "--description \"OPC UA Sensor\" --display-name \"Temperature Sensor\" --model \"Sensor-T2000\" "
        "--manufacturer \"Contoso\" --serial-number \"OPCUA987654\" "
        "--dataset-publish-int 2000 --dataset-sampling-int 1000 --dataset-queue-size 5 "
        "--dataset-key-frame-count 2 "
        "--event-publish-int 3000 --event-queue-size 10 "
        "--dataset-dest topic=\"factory/data\" qos=Qos1 retain=Keep ttl=3600 "
        "--event-dest topic=\"factory/events\" qos=Qos0 retain=Never ttl=7200 "
        "--product-code \"PROD-1234\""
    )
    tracked_resources.append(asset_opcua["id"])

    assert_asset_properties(
        asset_opcua,
        name=asset_name_opcua,
        device=device_name,
        endpoint=endpoint_name_opcua,
        description="OPC UA Sensor",
        display_name="Temperature Sensor",
        model="Sensor-T2000",
        manufacturer="Contoso",
        serial_number="OPCUA987654",
        product_code="PROD-1234",
        custom_location=custom_location
    )

    # 3. Create Media asset with maximum inputs
    asset_media = run(
        f"az iot ops ns asset media create --name {asset_name_media} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name_media} "
        "--description \"Media Camera\" --display-name \"Monitoring Camera\" --model \"MediaCam-4K\" "
        "--manufacturer \"MediaCorp\" --serial-number \"MEDIA567890\" "
        "--task-type \"snapshot-to-mqtt\" --task-format \"jpeg\" --snapshots-per-sec 1 "
        "--stream-dest topic=\"security/cameras/main\" qos=Qos0 retain=Never ttl=300 "
        "--external-asset-id \"EXT-MEDIA-01\" --hardware-revision \"v1.0\" "
    )
    tracked_resources.append(asset_media["id"])

    assert_asset_properties(
        asset_media,
        name=asset_name_media,
        device=device_name,
        endpoint=endpoint_name_media,
        description="Media Camera",
        display_name="Monitoring Camera",
        model="MediaCam-4K",
        manufacturer="MediaCorp",
        serial_number="MEDIA567890",
        external_asset_id="EXT-MEDIA-01",
        hardware_revision="v1.0",
        custom_location=custom_location,
    )

    # 4. Create Rest asset with maximum inputs
    asset_rest = run(
        f"az iot ops ns asset rest create --name {asset_name_rest} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name_rest} "
        "--description \"Rest Camera\" --display-name \"Main Entrance Camera\" "
        "--model \"Camera-X1\" --manufacturer \"SecurityCo\" --serial-number \"CAM123456\" "
        "--documentation-uri \"https://example.com/docs/camera\" "
        "--external-asset-id \"EXT-CAM-01\" --hardware-revision \"v1.2\" "
        f"--attribute {' '.join(common_attrs)} --tags {' '.join([f'{k}={v}' for k, v in common_tags.items()])} "
        "--sampling-int 1000"
    )
    tracked_resources.append(asset_media["id"])

    assert_asset_properties(
        asset_rest,
        name=asset_name_rest,
        device=device_name,
        endpoint=endpoint_name_rest,
        description="Rest Camera",
        display_name="Main Entrance Camera",
        model="Camera-X1",
        manufacturer="SecurityCo",
        serial_number="CAM123456",
        documentation_uri="https://example.com/docs/camera",
        external_asset_id="EXT-CAM-01",
        attributes=common_attrs,
        tags=common_tags,
        hardware_revision="v1.2",
        custom_location=custom_location,
    )

    # 5. Create SSE asset with maximum inputs
    asset_sse = run(
        f"az iot ops ns asset sse create --name {asset_name_sse} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name_sse} "
        "--description \"SSE Event Source\" --display-name \"Event Stream Processor\" "
        "--model \"EventProcessor-Y2\" --manufacturer \"EventCorp\" --serial-number \"EVT789012\" "
        "--documentation-uri \"https://example.com/docs/events\" "
        "--external-asset-id \"EXT-EVT-01\" --hardware-revision \"v2.1\" "
        f"--attribute {' '.join(common_attrs)} --tags {' '.join([f'{k}={v}' for k, v in common_tags.items()])}"
    )
    tracked_resources.append(asset_sse["id"])

    assert_asset_properties(
        asset_sse,
        name=asset_name_sse,
        device=device_name,
        endpoint=endpoint_name_sse,
        description="SSE Event Source",
        display_name="Event Stream Processor",
        model="EventProcessor-Y2",
        manufacturer="EventCorp",
        serial_number="EVT789012",
        documentation_uri="https://example.com/docs/events",
        external_asset_id="EXT-EVT-01",
        attributes=common_attrs,
        tags=common_tags,
        hardware_revision="v2.1",
        custom_location=custom_location,
    )

    # 6. Create MQTT asset with maximum inputs
    asset_mqtt = run(
        f"az iot ops ns asset mqtt create --name {asset_name_mqtt} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name_mqtt} "
        "--description \"In-cluster MQTT Stream\" --display-name \"Factory MQTT Subscriber\" "
        "--model \"MQTT-SUB-100\" --manufacturer \"BrokerCorp\" --serial-number \"MQTT-12345\" "
        "--documentation-uri \"https://example.com/docs/mqtt\" "
        "--external-asset-id \"EXT-MQTT-01\" --hardware-revision \"v1.0\" "
        f"--attribute {' '.join(common_attrs)} --tags {' '.join([f'{k}={v}' for k, v in common_tags.items()])}"
    )
    tracked_resources.append(asset_mqtt["id"])

    assert_asset_properties(
        asset_mqtt,
        name=asset_name_mqtt,
        device=device_name,
        endpoint=endpoint_name_mqtt,
        description="In-cluster MQTT Stream",
        display_name="Factory MQTT Subscriber",
        model="MQTT-SUB-100",
        manufacturer="BrokerCorp",
        serial_number="MQTT-12345",
        documentation_uri="https://example.com/docs/mqtt",
        external_asset_id="EXT-MQTT-01",
        attributes=common_attrs,
        tags=common_tags,
        hardware_revision="v1.0",
        custom_location=custom_location,
    )

    # 1. Update ONVIF asset
    updated_onvif = run(
        f"az iot ops ns asset onvif update --name {asset_name_onvif} --instance {instance_name} "
        f"-g {resource_group} --description \"Updated ONVIF Camera\" --display-name \"Main Entrance Camera\" "
        "--attribute location=entrance resolution=4K"
    )

    assert_asset_properties(
        updated_onvif,
        name=asset_name_onvif,
        description="Updated ONVIF Camera",
        display_name="Main Entrance Camera",
        attributes=["location=entrance", "resolution=4K", "floor=3"],
    )

    # 2. Update OPCUA asset
    updated_opcua = run(
        f"az iot ops ns asset opcua update --name {asset_name_opcua} --instance {instance_name} "
        f"-g {resource_group} --description \"Updated OPC UA Sensor\" "
        "--dataset-publish-int 500 --dataset-sampling-int 250 "
        "--model \"Sensor-T3000\" --manufacturer \"ContosoTech\" "
    )

    assert_asset_properties(
        updated_opcua,
        name=asset_name_opcua,
        description="Updated OPC UA Sensor",
        model="Sensor-T3000",
        manufacturer="ContosoTech",
    )

    # 3. Update Media asset
    updated_media = run(
        f"az iot ops ns asset media update --name {asset_name_media} --instance {instance_name} "
        f"-g {resource_group} --task-type \"snapshot-to-fs\" --task-format \"png\" --path \"/data/snapshots\" "
        "--serial-number \"MEDIA567890-UPDATED\" "
    )

    assert_asset_properties(
        updated_media,
        name=asset_name_media,
        serial_number="MEDIA567890-UPDATED",
    )

    # 4. Update Rest asset
    updated_rest = run(
        f"az iot ops ns asset rest update --name {asset_name_rest} --instance {instance_name} "
        f"-g {resource_group} --description \"Updated Rest Camera\" "
        "--sampling-int 500"
    )
    assert_asset_properties(
        updated_rest,
        name=asset_name_rest,
        description="Updated Rest Camera",
        sampling_int=500,
    )

    # 5. Update SSE asset
    updated_sse = run(
        f"az iot ops ns asset sse update --name {asset_name_sse} --instance {instance_name} "
        f"-g {resource_group} --description \"Updated SSE Event Source\""
    )
    assert_asset_properties(
        updated_sse,
        name=asset_name_sse,
        description="Updated SSE Event Source",
    )

    # 6. Update MQTT asset
    updated_mqtt = run(
        f"az iot ops ns asset mqtt update --name {asset_name_mqtt} --instance {instance_name} "
        f"-g {resource_group} --description \"Updated MQTT Stream\""
    )
    assert_asset_properties(
        updated_mqtt,
        name=asset_name_mqtt,
        description="Updated MQTT Stream",
    )


def assert_asset_properties(result, **expected):
    """Verify asset properties match expected values

    Note that the unit tests have coverage for all properties, so this function
    is used to assert general properties.
    """

    assert result["name"] == expected["name"]
    # Check custom location
    if "custom_location" in expected:
        assert result["extendedLocation"]["name"] == expected["custom_location"]

    result_props = result["properties"]

    if "attributes" in expected:
        assert result_props["attributes"] == parse_kvp_nargs(expected["attributes"])
    if "disabled" in expected:
        assert result_props["enabled"] is not expected["disabled"]
    if "displayName" in expected:
        assert result_props["displayName"] == expected["display_name"]
    if "device" in expected:
        assert result_props["deviceRef"]["deviceName"] == expected["device"]
    if "endpoint" in expected:
        assert result_props["deviceRef"]["endpointName"] == expected["endpoint"]
    if "documentation_uri" in expected:
        assert result_props["documentationUri"] == expected["documentation_uri"]
    if "external_asset_id" in expected:
        assert result_props["externalAssetId"] == expected["external_asset_id"]
    if "hardware_revision" in expected:
        assert result_props["hardwareRevision"] == expected["hardware_revision"]
    if "manufacturer" in expected:
        assert result_props["manufacturer"] == expected["manufacturer"]
    if "manufacturer_uri" in expected:
        assert result_props["manufacturerUri"] == expected["manufacturer_uri"]
    if "model" in expected:
        assert result_props["model"] == expected["model"]
    if "product_code" in expected:
        assert result_props["productCode"] == expected["product_code"]
    if "serial_number" in expected:
        assert result_props["serialNumber"] == expected["serial_number"]
    if "software_revision" in expected:
        assert result_props["softwareRevision"] == expected["software_revision"]
