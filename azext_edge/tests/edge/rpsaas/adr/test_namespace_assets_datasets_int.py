# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List

from ....generators import generate_random_string
from ....helpers import run


def test_namespace_asset_dataset_lifecycle_operations(require_init, tracked_resources: List[str]):
    """Test dataset operations for namespace assets."""
    # TODO: remove when service is ready
    location = "eastus2euap"

    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    namespace_name = f"ns-{generate_random_string(8)}"
    device_name = f"dev-{generate_random_string(8)}"
    endpoint_name_custom = f"custom-{generate_random_string(8)}"
    asset_name_custom = f"custom-{generate_random_string(8)}"
    asset_name_opcua = f"opcua-{generate_random_string(8)}"

    # Dataset names
    dataset_name_custom = f"customDataset-{generate_random_string(8)}"
    dataset_name_opcua = f"opcuaDataset-{generate_random_string(8)}"

    # Create namespace
    result = run(
        f"az iot ops ns create -n {namespace_name} -g {resource_group} --mi-system-assigned"
        f"--location {location}"
    )
    tracked_resources.append(result["id"])

    # Create Device
    run(
        f"az iot ops ns device create --name {device_name} --namespace {namespace_name} "
        f"-g {resource_group} --instance {instance_name} --template-id dtmi:sample:device;1"
    )

    # Create device endpoint (can just use custom for testing)
    run(
        f"az iot ops ns device endpoint inbound add custom --device {device_name} "
        f"--namespace {namespace_name} -g {resource_group} --endpoint-name {endpoint_name_custom} "
        f"--endpoint-address http://test-server:8080"
    )

    # Create assets - TODO: we should be able to get away with just custom asset creation
    run(
        f"az iot ops ns asset custom create --name {asset_name_custom} --namespace {namespace_name} "
        f"-g {resource_group} --device {device_name} --endpoint-name {endpoint_name_custom} "
        f"--description 'Custom Asset for Dataset Testing'"
    )

    run(
        f"az iot ops ns asset opcua create --name {asset_name_opcua} --namespace {namespace_name} "
        f"-g {resource_group} --device {device_name} --endpoint-name {endpoint_name_custom} "
        f"--description 'OPC UA Asset for Dataset Testing'"
    )

    # Test 1: Add Custom Dataset
    custom_dataset = run(
        f"az iot ops ns asset custom dataset add --asset {asset_name_custom} --namespace {namespace_name} "
        f"-g {resource_group} --name {dataset_name_custom} --data-source temperature.sensor1 "
        f"--dataset-config '{{\"publishingInterval\": 1000}}' "
        f"--dataset-dest topic=factory/custom/data qos=1 retain=true ttl=3600"
    )

    assert_dataset_properties(
        custom_dataset,
        name=dataset_name_custom,
        data_source="temperature.sensor1"
    )

    # Test 2: Add OPC UA Dataset with full configuration
    opcua_dataset = run(
        f"az iot ops ns asset opcua dataset add --asset {asset_name_opcua} --namespace {namespace_name} "
        f"-g {resource_group} --name {dataset_name_opcua} --data-source ns=2;s=Temperature "
        f"--dataset-publish-int 500 --dataset-sampling-int 250 --dataset-queue-size 10 "
        f"--dataset-key-frame-count 5 --dataset-start-inst ns=2;i=1000 "
        f"--dataset-dest topic=factory/opcua/data qos=2 retain=false ttl=7200"
    )

    assert_dataset_properties(
        opcua_dataset,
        name=dataset_name_opcua,
        data_source="ns=2;s=Temperature"
    )

    # Test 3: List datasets
    custom_datasets = run(
        f"az iot ops ns asset custom dataset list --asset {asset_name_custom} "
        f"--namespace {namespace_name} -g {resource_group}"
    )

    assert len(custom_datasets) >= 1
    dataset_names = [ds["name"] for ds in custom_datasets]
    assert dataset_name_custom in dataset_names

    opcua_datasets = run(
        f"az iot ops ns asset opcua dataset list --asset {asset_name_opcua} "
        f"--namespace {namespace_name} -g {resource_group}"
    )

    assert len(opcua_datasets) >= 1
    dataset_names = [ds["name"] for ds in opcua_datasets]
    assert dataset_name_opcua in dataset_names

    # Test 4: Show dataset details
    shown_custom_dataset = run(
        f"az iot ops ns asset custom dataset show --asset {asset_name_custom} "
        f"--namespace {namespace_name} -g {resource_group} --name {dataset_name_custom}"
    )

    assert_dataset_properties(
        shown_custom_dataset,
        name=dataset_name_custom,
        data_source="temperature.sensor1"
    )

    shown_opcua_dataset = run(
        f"az iot ops ns asset opcua dataset show --asset {asset_name_opcua} "
        f"--namespace {namespace_name} -g {resource_group} --name {dataset_name_opcua}"
    )

    assert_dataset_properties(
        shown_opcua_dataset,
        name=dataset_name_opcua,
        data_source="ns=2;s=Temperature"
    )

    # Test 5: Update datasets
    updated_custom_dataset = run(
        f"az iot ops ns asset custom dataset update --asset {asset_name_custom} "
        f"--namespace {namespace_name} -g {resource_group} --name {dataset_name_custom} "
        f"--data-source temperature.sensor1.updated "
        f"--dataset-config '{{\"publishingInterval\": 2000}}'"
    )

    assert_dataset_properties(
        updated_custom_dataset,
        name=dataset_name_custom,
        data_source="temperature.sensor1.updated"
    )

    updated_opcua_dataset = run(
        f"az iot ops ns asset opcua dataset update --asset {asset_name_opcua} "
        f"--namespace {namespace_name} -g {resource_group} --name {dataset_name_opcua} "
        f"--data-source ns=3;s=UpdatedTemperature --dataset-publish-int 1000 "
        f"--dataset-sampling-int 500 --dataset-queue-size 15"
    )

    assert_dataset_properties(
        updated_opcua_dataset,
        name=dataset_name_opcua,
        data_source="ns=3;s=UpdatedTemperature"
    )

    # Test 6: Add dataset with replace flag
    replaced_custom_dataset = run(
        f"az iot ops ns asset custom dataset add --asset {asset_name_custom} --namespace {namespace_name} "
        f"-g {resource_group} --name {dataset_name_custom} --data-source temperature.sensor1.replaced "
        f"--replace"
    )

    assert_dataset_properties(
        replaced_custom_dataset,
        name=dataset_name_custom,
        data_source="temperature.sensor1.replaced"
    )

    # Test 7: Remove dataset
    run(
        f"az iot ops ns asset custom dataset remove --asset {asset_name_custom} "
        f"--namespace {namespace_name} -g {resource_group} --name {dataset_name_custom}"
    )

    # Verify removal by listing
    remaining_datasets = run(
        f"az iot ops ns asset custom dataset list --asset {asset_name_custom} "
        f"--namespace {namespace_name} -g {resource_group}"
    )

    dataset_names = [ds["name"] for ds in remaining_datasets]
    assert dataset_name_custom not in dataset_names


def test_namespace_asset_dataset_point_lifecycle_operations(require_init, tracked_resources: List[str]):
    """Test dataset point operations for namespace assets."""
    # TODO: remove when service is ready
    location = "eastus2euap"

    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    namespace_name = f"ns-{generate_random_string(8)}"
    device_name = f"dev-{generate_random_string(8)}"
    endpoint_name_custom = f"custom-{generate_random_string(8)}"
    endpoint_name_opcua = f"opcua-{generate_random_string(8)}"
    asset_name_custom = f"custom-{generate_random_string(8)}"
    asset_name_opcua = f"opcua-{generate_random_string(8)}"

    # Dataset and datapoint names
    dataset_name_custom = f"customDataset-{generate_random_string(8)}"
    dataset_name_opcua = f"opcuaDataset-{generate_random_string(8)}"
    datapoint_name_custom = f"customPoint-{generate_random_string(8)}"
    datapoint_name_opcua = f"opcuaPoint-{generate_random_string(8)}"

    # Create namespace
    result = run(
        f"az iot ops ns create -n {namespace_name} -g {resource_group} --mi-system-assigned"
        f"--location {location}"
    )
    tracked_resources.append(result["id"])

    # Create Device
    run(
        f"az iot ops ns device create --name {device_name} --namespace {namespace_name} "
        f"-g {resource_group} --instance {instance_name} --template-id dtmi:sample:device;1"
    )

    # Create device endpoints
    for endpoint_name, endpoint_type in [
        (endpoint_name_custom, "custom"),
        (endpoint_name_opcua, "opcua")
    ]:
        run(
            f"az iot ops ns device endpoint inbound add {endpoint_type} --device {device_name} "
            f"--namespace {namespace_name} -g {resource_group} --endpoint-name {endpoint_name} "
            f"--endpoint-address http://test-server:8080"
        )

    # Create assets
    run(
        f"az iot ops ns asset custom create --name {asset_name_custom} --namespace {namespace_name} "
        f"-g {resource_group} --device {device_name} --endpoint-name {endpoint_name_custom}"
    )

    run(
        f"az iot ops ns asset opcua create --name {asset_name_opcua} --namespace {namespace_name} "
        f"-g {resource_group} --device {device_name} --endpoint-name {endpoint_name_opcua}"
    )

    # Create datasets first
    run(
        f"az iot ops ns asset custom dataset add --asset {asset_name_custom} --namespace {namespace_name} "
        f"-g {resource_group} --name {dataset_name_custom} --data-source temperature.sensor"
    )

    run(
        f"az iot ops ns asset opcua dataset add --asset {asset_name_opcua} --namespace {namespace_name} "
        f"-g {resource_group} --name {dataset_name_opcua} --data-source ns=2;s=Temperature"
    )

    # Test 1: Add Custom Dataset Point
    custom_datapoint = run(
        f"az iot ops ns asset custom dataset point add --asset {asset_name_custom} "
        f"--namespace {namespace_name} -g {resource_group} --dataset {dataset_name_custom} "
        f"--name {datapoint_name_custom} --data-source temperature.value "
        f"--custom-config '{{\"observabilityMode\": \"log\"}}'"
    )

    assert_datapoint_properties(
        custom_datapoint,
        name=datapoint_name_custom,
        data_source="temperature.value"
    )

    # Test 2: Add OPC UA Dataset Point with full configuration
    opcua_datapoint = run(
        f"az iot ops ns asset opcua dataset point add --asset {asset_name_opcua} "
        f"--namespace {namespace_name} -g {resource_group} --dataset {dataset_name_opcua} "
        f"--name {datapoint_name_opcua} --data-source ns=2;s=TempValue "
        f"--queue-size 5 --sampling-int 1000"
    )

    assert_datapoint_properties(
        opcua_datapoint,
        name=datapoint_name_opcua,
        data_source="ns=2;s=TempValue"
    )

    # Test 3: List dataset points
    custom_datapoints = run(
        f"az iot ops ns asset custom dataset point list --asset {asset_name_custom} "
        f"--namespace {namespace_name} -g {resource_group} --dataset {dataset_name_custom}"
    )

    assert len(custom_datapoints) >= 1
    point_names = [dp["name"] for dp in custom_datapoints]
    assert datapoint_name_custom in point_names

    opcua_datapoints = run(
        f"az iot ops ns asset opcua dataset point list --asset {asset_name_opcua} "
        f"--namespace {namespace_name} -g {resource_group} --dataset {dataset_name_opcua}"
    )

    assert len(opcua_datapoints) >= 1
    point_names = [dp["name"] for dp in opcua_datapoints]
    assert datapoint_name_opcua in point_names

    # Test 4: Add datapoint with replace flag
    replaced_custom_datapoint = run(
        f"az iot ops ns asset custom dataset point add --asset {asset_name_custom} "
        f"--namespace {namespace_name} -g {resource_group} --dataset {dataset_name_custom} "
        f"--name {datapoint_name_custom} --data-source temperature.value.replaced --replace"
    )

    assert_datapoint_properties(
        replaced_custom_datapoint,
        name=datapoint_name_custom,
        data_source="temperature.value.replaced"
    )

    # Test 5: Remove dataset points
    run(
        f"az iot ops ns asset custom dataset point remove --asset {asset_name_custom} "
        f"--namespace {namespace_name} -g {resource_group} --dataset {dataset_name_custom} "
        f"--name {datapoint_name_custom}"
    )

    # Verify removal by listing
    remaining_datapoints = run(
        f"az iot ops ns asset custom dataset point list --asset {asset_name_custom} "
        f"--namespace {namespace_name} -g {resource_group} --dataset {dataset_name_custom}"
    )

    point_names = [dp["name"] for dp in remaining_datapoints]
    assert datapoint_name_custom not in point_names

    run(
        f"az iot ops ns asset opcua dataset point remove --asset {asset_name_opcua} "
        f"--namespace {namespace_name} -g {resource_group} --dataset {dataset_name_opcua} "
        f"--name {datapoint_name_opcua}"
    )

    # Verify removal by listing
    remaining_opcua_datapoints = run(
        f"az iot ops ns asset opcua dataset point list --asset {asset_name_opcua} "
        f"--namespace {namespace_name} -g {resource_group} --dataset {dataset_name_opcua}"
    )

    point_names = [dp["name"] for dp in remaining_opcua_datapoints]
    assert datapoint_name_opcua not in point_names


def assert_dataset_properties(result, **expected):
    """Verify dataset properties match expected values."""

    assert result["name"] == expected["name"]

    result_props = result.get("properties", {})

    if "data_source" in expected:
        assert result_props.get("dataSource") == expected["data_source"]

    if "publishing_interval" in expected:
        config = result_props.get("datasetConfiguration", {})
        assert config.get("publishingInterval") == expected["publishing_interval"]

    if "sampling_interval" in expected:
        config = result_props.get("datasetConfiguration", {})
        assert config.get("samplingInterval") == expected["sampling_interval"]

    if "queue_size" in expected:
        config = result_props.get("datasetConfiguration", {})
        assert config.get("queueSize") == expected["queue_size"]

    if "key_frame_count" in expected:
        config = result_props.get("datasetConfiguration", {})
        assert config.get("keyFrameCount") == expected["key_frame_count"]

    if "start_instance" in expected:
        config = result_props.get("datasetConfiguration", {})
        assert config.get("startInstance") == expected["start_instance"]

    # Check MQTT destination if present
    if "mqtt_topic" in expected:
        destinations = result_props.get("destinations", [])
        if destinations:
            mqtt_dest = destinations[0].get("mqtt", {})
            assert mqtt_dest.get("topic") == expected["mqtt_topic"]

    if "mqtt_qos" in expected:
        destinations = result_props.get("destinations", [])
        if destinations:
            mqtt_dest = destinations[0].get("mqtt", {})
            assert mqtt_dest.get("qos") == expected["mqtt_qos"]

    if "mqtt_retain" in expected:
        destinations = result_props.get("destinations", [])
        if destinations:
            mqtt_dest = destinations[0].get("mqtt", {})
            assert mqtt_dest.get("retain") == expected["mqtt_retain"]


def assert_datapoint_properties(result, **expected):
    """Verify datapoint properties match expected values."""

    assert result["name"] == expected["name"]

    result_props = result.get("properties", {})

    if "data_source" in expected:
        assert result_props.get("dataSource") == expected["data_source"]

    if "observability_mode" in expected:
        assert result_props.get("observabilityMode") == expected["observability_mode"]

    if "queue_size" in expected:
        config = result_props.get("dataPointConfiguration", {})
        assert config.get("queueSize") == expected["queue_size"]

    if "sampling_interval" in expected:
        config = result_props.get("dataPointConfiguration", {})
        assert config.get("samplingInterval") == expected["sampling_interval"]

    # Check custom configuration for custom assets
    if "custom_config" in expected:
        config = result_props.get("dataPointConfiguration", {})
        custom_config = config.get("customConfiguration")
        if custom_config:
            # Parse JSON if it's a string
            import json
            if isinstance(custom_config, str):
                custom_config = json.loads(custom_config)
            assert custom_config == expected["custom_config"]
