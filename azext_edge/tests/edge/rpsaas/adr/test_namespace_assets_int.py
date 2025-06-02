# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List
from azext_edge.edge.util.common import parse_kvp_nargs

from ....generators import generate_random_string
from ....helpers import run


def test_namespace_asset_lifecycle_operations(require_init, tracked_resources: List[str]):
    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    custom_location = require_init["customLocationId"]
    namespace_name = f"ns-{generate_random_string(8)}"
    device_name_1 = f"dev-{generate_random_string(8)}"
    device_template_id = "dtmi:sample:device;1"
    endpoint_name_onvif = f"onvif-{generate_random_string(8)}"
    endpoint_name_opcua = f"opcua-{generate_random_string(8)}"
    endpoint_name_media = f"media-{generate_random_string(8)}"
    endpoint_name_custom = f"custom-{generate_random_string(8)}"
    asset_name_onvif = f"onvif-{generate_random_string(8)}"
    asset_name_opcua = f"opcua-{generate_random_string(8)}"
    asset_name_media = f"media-{generate_random_string(8)}"
    asset_name_custom = f"custom-{generate_random_string(8)}"

# Tags and attributes
    common_tags = {"env": "test", "purpose": "automation"}
    common_attrs = ["location=building1", "floor=3"]

    # Create namespace
    result = run(f"az iot ops namespace create -n {namespace_name} -g {resource_group} --mi-system-assigned")
    tracked_resources.append(result["id"])  # only track namespace - deletion of it should delete devices too

    # Create Device
    result = run(
        f"az iot ops namespace device create --name {device_name_1} --namespace {namespace_name} "
        f"-g {resource_group} --instance {instance_name} --template-id {device_template_id}"
    )

    # Create device endpoints
    for endpoint_name, endpoint_type in [
        (endpoint_name_onvif, "onvif"),
        (endpoint_name_opcua, "opcua"),
        (endpoint_name_media, "media"),
        (endpoint_name_custom, "custom")
    ]:
        run(
            f"az iot ops namespace device endpoint create --name {endpoint_name} --namespace {namespace_name} "
            f"-g {resource_group} --instance {instance_name} --device {device_name_1} --type {endpoint_type}"
        )

    # 1. Create ONVIF asset with maximum inputs
    asset_onvif = run(
        f"az iot ops namespace asset create onvif --name {asset_name_onvif} --namespace {namespace_name} "
        f"-g {resource_group} --device {device_name_1} --endpoint-name {endpoint_name_onvif} "
        f"--description 'ONVIF Camera' --display-name 'Entrance Camera' --model 'Camera-X1' "
        f"--manufacturer 'SecurityCo' --serial-number 'CAM123456' "
        f"--documentation-uri 'https://example.com/docs/camera' "
        f"--external-asset-id 'EXT-CAM-01' --hardware-revision 'v1.2' "
        f"--attribute {' '.join(common_attrs)} --tags {' '.join([f'{k}={v}' for k, v in common_tags.items()])}"
    )

    assert_asset_properties(
        asset_onvif,
        name=asset_name_onvif,
        device=device_name_1,
        endpoint=endpoint_name_onvif,
        description="ONVIF Camera",
        display_name="Entrance Camera",
        asset_type="Microsoft.Onvif"
    )

    # 2. Create OPCUA asset with maximum inputs
    asset_opcua = run(
        f"az iot ops namespace asset create opcua --name {asset_name_opcua} --namespace {namespace_name} "
        f"-g {resource_group} --device {device_name_1} --endpoint-name {endpoint_name_opcua} "
        f"--description 'OPC UA Sensor' --display-name 'Temperature Sensor' --model 'Sensor-T2000' "
        f"--manufacturer 'Contoso' --serial-number 'OPCUA987654' "
        f"--dataset-publish-interval 2000 --dataset-sampling-interval 1000 --dataset-queue-size 5 "
        f"--dataset-key-frame-count 2 --dataset-start-instance 'ns=1;i=1234' "
        f"--events-publish-interval 3000 --events-queue-size 10 --events-start-instance 'ns=1;i=5678' "
        f"--events-filter-clause path='ns=1;i=1000' type='String' field='Temperature' "
        f"--datasets-destinations topic='factory/data' qos=1 retain=true ttl=3600 "
        f"--events-destinations topic='factory/events' qos=1 retain=false ttl=7200 "
        f"--attribute {' '.join(common_attrs)} --tags {' '.join([f'{k}={v}' for k, v in common_tags.items()])}"
    )

    assert_asset_properties(
        asset_opcua,
        name=asset_name_opcua,
        device=device_name_1,
        endpoint=endpoint_name_opcua,
        description="OPC UA Sensor",
        display_name="Temperature Sensor",
        asset_type="Microsoft.OpcUa"
    )

    # 3. Create Media asset with maximum inputs
    asset_media = run(
        f"az iot ops namespace asset create media --name {asset_name_media} --namespace {namespace_name} "
        f"-g {resource_group} --device {device_name_1} --endpoint-name {endpoint_name_media} "
        f"--description 'Media Camera' --display-name 'Monitoring Camera' --model 'MediaCam-4K' "
        f"--manufacturer 'MediaCorp' --serial-number 'MEDIA567890' "
        f"--task-type 'snapshot-to-mqtt' --task-format 'jpeg' --snapshots-per-second 1 "
        f"--streams-destinations topic='security/cameras/main' qos=1 retain=false ttl=300 "
        f"--attribute {' '.join(common_attrs)} --tags {' '.join([f'{k}={v}' for k, v in common_tags.items()])}"
    )

    assert_asset_properties(
        asset_media,
        name=asset_name_media,
        device=device_name_1,
        endpoint=endpoint_name_media,
        description="Media Camera",
        display_name="Monitoring Camera",
        asset_type="Microsoft.Media"
    )

    # 4. Create Custom asset with maximum inputs
    asset_custom = run(
        f"az iot ops namespace asset create custom --name {asset_name_custom} --namespace {namespace_name} "
        f"-g {resource_group} --device {device_name_1} --endpoint-name {endpoint_name_custom} "
        f"--description 'Custom Device' --display-name 'Multi-Sensor' --model 'Custom-MS100' "
        f"--manufacturer 'CustomDevices' --serial-number 'CUST123456' "
        f"--datasets-config \"{{\\\"publishingInterval\\\": 1000}}\" "
        f"--events-config \"{{\\\"queueSize\\\": 5}}\" "
        f"--datasets-destination topic='custom/data' qos=1 retain=true ttl=3600 "
        f"--events-destination topic='custom/events' qos=1 retain=false ttl=3600 "
        f"--attribute {' '.join(common_attrs)} --tags {' '.join([f'{k}={v}' for k, v in common_tags.items()])}"
    )

    assert_asset_properties(
        asset_custom,
        name=asset_name_custom,
        device=device_name_1,
        endpoint=endpoint_name_custom,
        description="Custom Device",
        display_name="Multi-Sensor",
        asset_type="custom"
    )

    # Test show operation for an asset
    shown_asset = run(
        f"az iot ops namespace asset show --name {asset_name_onvif} --namespace {namespace_name} "
        f"-g {resource_group}"
    )

    assert_asset_properties(
        shown_asset,
        name=asset_name_onvif,
        device=device_name_1,
        endpoint=endpoint_name_onvif,
        description="ONVIF Camera",
        display_name="Entrance Camera",
        asset_type="Microsoft.Onvif"
    )

    print("Testing asset 'update' operations...")

    # Test update operation for each asset type
    # 1. Update ONVIF asset
    updated_onvif = run(
        f"az iot ops namespace asset update onvif --name {asset_name_onvif} --namespace {namespace_name} "
        f"-g {resource_group} --description 'Updated ONVIF Camera' --display-name 'Main Entrance Camera' "
        f"--attribute location=entrance resolution=4K"
    )

    assert_asset_properties(
        updated_onvif,
        name=asset_name_onvif,
        description="Updated ONVIF Camera",
        display_name="Main Entrance Camera",
        asset_type="Microsoft.Onvif"
    )

    # 2. Update OPCUA asset
    updated_opcua = run(
        f"az iot ops namespace asset update opcua --name {asset_name_opcua} --namespace {namespace_name} "
        f"-g {resource_group} --description 'Updated OPC UA Sensor' "
        f"--dataset-publish-interval 500 --dataset-sampling-interval 250"
    )

    assert_asset_properties(
        updated_opcua,
        name=asset_name_opcua,
        description="Updated OPC UA Sensor",
        asset_type="Microsoft.OpcUa"
    )

    # 3. Update Media asset
    updated_media = run(
        f"az iot ops namespace asset update media --name {asset_name_media} --namespace {namespace_name} "
        f"-g {resource_group} --task-type 'snapshot-to-fs' --task-format 'png' --path '/data/snapshots'"
    )

    assert_asset_properties(
        updated_media,
        name=asset_name_media,
        asset_type="Microsoft.Media"
    )

    # 4. Update Custom asset
    updated_custom = run(
        f"az iot ops namespace asset update custom --name {asset_name_custom} --namespace {namespace_name} "
        f"-g {resource_group} --datasets-config \"{{\\\"publishingInterval\\\": 2000}}\" "
        f"--events-config \"{{\\\"queueSize\\\": 10}}\""
    )

    assert_asset_properties(
        updated_custom,
        name=asset_name_custom,
        asset_type="custom"
    )

    # Test query operation
    queried_assets = run(
        f"az iot ops namespace asset query -g {resource_group}"
    )

    assert len(queried_assets) >= 4

    # Query by specific device
    device_assets = run(
        f"az iot ops namespace asset query -g {resource_group} --device {device_name_1}"
    )

    assert len(device_assets) >= 4

    # Query by asset name
    named_asset = run(
        f"az iot ops namespace asset query -g {resource_group} --name {asset_name_onvif}"
    )

    assert len(named_asset) == 1
    assert named_asset[0]["name"] == asset_name_onvif

    # Test delete operation
    run(
        f"az iot ops namespace asset delete --name {asset_name_custom} --namespace {namespace_name} "
        f"-g {resource_group} -y"
    )

    # Verify deletion by querying - should return no results
    deleted_query = run(
        f"az iot ops namespace asset query -g {resource_group} --name {asset_name_custom}"
    )

    assert len(deleted_query) == 0


def assert_asset_properties(result, **expected):
    """Verify asset properties match expected values"""

    assert result["name"] == expected["name"]

    if "device" in expected:
        assert result["properties"]["device"]["name"] == expected["device"]

    if "endpoint" in expected:
        assert result["properties"]["endpoint"]["name"] == expected["endpoint"]

    if "description" in expected:
        assert result["properties"]["description"] == expected["description"]

    if "display_name" in expected:
        assert result["properties"]["displayName"] == expected["display_name"]

    if "asset_type" in expected:
        assert result["properties"]["assetType"] == expected["asset_type"]
