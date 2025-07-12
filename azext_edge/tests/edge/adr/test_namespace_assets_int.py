# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from time import sleep
from typing import List
from azext_edge.edge.util.common import parse_kvp_nargs

from ...generators import generate_random_string
from ...helpers import run

# TODO fix up tests to work with linux
# pytestmark = pytest.mark.rpsaas


def test_namespace_asset_lifecycle_operations(require_init, tracked_resources: List[str]):
    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    custom_location = require_init["customLocationId"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name_custom = f"custom-{generate_random_string(8)}"
    asset_name_custom = f"custom-{generate_random_string(8, force_lower=True)}"

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
        f"az iot ops ns asset custom create --name {asset_name_custom} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint-name {endpoint_name_custom} "
        f"--description \"Custom Device\" --display-name \"Multi-Sensor\" --model \"Custom-MS100\" "
        f"--manufacturer \"CustomDevices\" --serial-number \"CUST123456\" "
        f"--dataset-config \"{{\\\"publishingInterval\\\": 1000}}\" "
        f"--event-config \"{{\\\"queueSize\\\": 5}}\" "
        f"--dataset-dest topic=\"custom/data\" qos=Qos1 retain=Keep ttl=3600 "
        f"--event-dest topic=\"custom/events\" qos=Qos0 retain=Never ttl=3600 "
        f"--attribute {' '.join(common_attrs)} --tags {' '.join([f'{k}={v}' for k, v in common_tags.items()])}"
    )
    tracked_resources.append(asset_custom["id"])

    assert_asset_properties(
        asset_custom,
        name=asset_name_custom,
        device=device_name,
        endpoint=endpoint_name_custom,
        description="Custom Device",
        display_name="Multi-Sensor",
        custom_location=custom_location
    )

    # Test show operation for an asset
    shown_asset = run(
        f"az iot ops ns asset show --name {asset_name_custom} --instance {instance_name} "
        f"-g {resource_group}"
    )

    assert_asset_properties(
        shown_asset,
        name=asset_name_custom,
        device=device_name,
        endpoint=endpoint_name_custom,
    )

    # Update Custom asset
    updated_custom = run(
        f"az iot ops ns asset custom update --name {asset_name_custom} --instance {instance_name} "
        f"-g {resource_group} --dataset-config \"{{\\\"publishingInterval\\\": 2000}}\" "
        f"--event-config \"{{\\\"queueSize\\\": 10}}\" --software-revision \"v2.0\" "

    )

    assert_asset_properties(
        updated_custom,
        name=asset_name_custom,
        software_revision="v2.0",
    )

    # Test query operation
    queried_assets = run(
        "az iot ops ns asset query"
    )

    asset_names = [asset["name"] for asset in queried_assets]
    assert asset_name_custom in asset_names

    # Query by specific device
    device_assets = run(
        f"az iot ops ns asset query --device {device_name}"
    )

    asset_names = [asset["name"] for asset in device_assets]
    assert asset_name_custom in asset_names

    # Query by asset name
    named_asset = run(
        f"az iot ops ns asset query --name {asset_name_custom}"
    )

    assert len(named_asset) == 1
    assert named_asset[0]["name"] == asset_name_custom

    # Test delete operation
    run(
        f"az iot ops ns asset delete --name {asset_name_custom} --instance {instance_name} "
        f"-g {resource_group} -y"
    )

    sleep(30)  # Wait for deletion to propagate
    # Verify deletion by querying
    deleted_query = run(
        "az iot ops ns asset query"
    )

    asset_names = [asset["name"] for asset in deleted_query]
    assert asset_name_custom not in asset_names


def test_namespace_asset_1p_types(require_init, tracked_resources: List[str]):
    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    custom_location = require_init["customLocationId"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name_onvif = f"onvif-{generate_random_string(8)}"
    endpoint_name_opcua = f"opcua-{generate_random_string(8)}"
    endpoint_name_media = f"media-{generate_random_string(8)}"
    asset_name_onvif = f"onvif-{generate_random_string(8, force_lower=True)}"
    asset_name_opcua = f"opcua-{generate_random_string(8, force_lower=True)}"
    asset_name_media = f"media-{generate_random_string(8, force_lower=True)}"

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
    ]:
        command = (
            f"az iot ops ns device endpoint inbound add {endpoint_type} --name {endpoint_name} "
            f"--instance {instance_name} -g {resource_group} --device {device_name} "
            "--endpoint-address 'http://192.168.1.100:8000/onvif/device_service'"
        )
        if endpoint_type == "custom":
            command += " --endpoint-type custom"
        run(command)

    # 1. Create ONVIF asset with maximum inputs
    asset_onvif = run(
        f"az iot ops ns asset onvif create --name {asset_name_onvif} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint-name {endpoint_name_onvif} "
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
        f"-g {resource_group} --device {device_name} --endpoint-name {endpoint_name_opcua} "
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
        f"-g {resource_group} --device {device_name} --endpoint-name {endpoint_name_media} "
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
