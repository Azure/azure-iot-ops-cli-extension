# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import logging
import pytest
from typing import List

from ...generators import generate_random_string
from ...helpers import run
from .namespace_helpers import create_config_file, assert_point_properties, assert_dataset_properties


logger = logging.getLogger(__name__)
pytestmark = pytest.mark.long_running


def test_namespace_custom_asset_dataset_lifecycle_operations(
    require_init, tracked_resources: List[str], tracked_files: List[str]
):
    """Test complete lifecycle of custom asset dataset and datapoint operations."""
    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"custom-{generate_random_string(8)}"
    asset_name = f"custom-{generate_random_string(8, force_lower=True)}"
    dataset_name_1 = f"dataset{generate_random_string(6, force_lower=True)}"
    dataset_name_2 = f"dataset2{generate_random_string(6, force_lower=True)}"
    datapoint_name_1 = f"dp1-{generate_random_string(6, force_lower=True)}"
    datapoint_name_2 = f"dp2-{generate_random_string(6, force_lower=True)}"

    # Create Device
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    # Create device endpoint
    run(
        f"az iot ops ns device endpoint inbound add custom --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'http://192.168.1.100:8000/custom/service' "
        "--endpoint-type custom"
    )

    # Create Custom asset
    asset_custom = run(
        f"az iot ops ns asset custom create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name} "
        f"--description \"Custom Device for Dataset Testing\" --display \"Multi-Sensor Dataset\" "
        f"--model \"Custom-DS100\" --manufacturer \"CustomDevices\""
    )
    tracked_resources.append(asset_custom["id"])

    # 1. CREATE DATASET
    dataset_data_source = "sensor/temperature"
    dataset_destinations = "topic=factory/temperature qos=Qos1 retain=Keep ttl=3600"
    custom_config_path, custom_config = create_config_file(tracked_files)

    # Add custom asset dataset
    dataset_result = run(
        f"az iot ops ns asset custom dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1} "
        f"--data-source {dataset_data_source} "
        f"--destination {dataset_destinations} "
        f"--config {custom_config_path}"
    )

    assert_dataset_properties(
        dataset_result,
        name=dataset_name_1,
        data_source=dataset_data_source,
        asset_type="custom",
        custom_configuration=custom_config
    )

    # 2. LIST DATASETS
    datasets_list = run(
        f"az iot ops ns asset custom dataset list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group}"
    )

    dataset_names = [dataset["name"] for dataset in datasets_list]
    assert dataset_name_1 in dataset_names
    assert len(datasets_list) >= 1

    # 3. SHOW DATASET
    shown_dataset = run(
        f"az iot ops ns asset custom dataset show --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1}"
    )

    assert_dataset_properties(
        shown_dataset,
        name=dataset_name_1,
        data_source=dataset_data_source,
        asset_type="custom"
    )

    # 4. UPDATE DATASET
    updated_data_source = "sensor/temperature_updated"
    updated_destinations = "topic=factory/temperature_v2 qos=Qos0 retain=Never ttl=1800"
    custom_config_path, custom_config = create_config_file(tracked_files)

    updated_dataset = run(
        f"az iot ops ns asset custom dataset update --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1} "
        f"--data-source {updated_data_source} "
        f"--destination {updated_destinations} "
        f"--config {custom_config_path}"
    )

    assert_dataset_properties(
        updated_dataset,
        name=dataset_name_1,
        data_source=updated_data_source,
        asset_type="custom",
        custom_configuration=custom_config
    )

    # 5a. TEST DATASET REPLACE FUNCTIONALITY
    # Replace dataset with --replace flag
    replaced_data_source = "sensor/temperature_replaced"
    custom_config_path, custom_config = create_config_file(tracked_files)

    replaced_dataset = run(
        f"az iot ops ns asset custom dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1} "
        f"--data-source {replaced_data_source} "
        f"--config {custom_config_path} --replace"
    )

    assert_dataset_properties(
        replaced_dataset,
        name=dataset_name_1,
        data_source=replaced_data_source,
        asset_type="custom",
        custom_configuration=custom_config
    )

    # 5b. TEST MULTIPLE DATASETS
    data_source = "sensor/temperature_replaced"

    dataset = run(
        f"az iot ops ns asset custom dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_2} "
        f"--data-source {data_source} "
        f"--config {custom_config_path} --replace"
    )

    assert_dataset_properties(
        dataset,
        name=dataset_name_2,
        data_source=data_source,
        asset_type="custom",
    )

    # 6. ADD DATASET DATAPOINTS
    # Add first datapoint
    datapoint_data_source_1 = "sensor/temperature/value"
    custom_config_path, custom_config = create_config_file(tracked_files)

    datapoint_result_1 = run(
        f"az iot ops ns asset custom datapoint add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name_1} "
        f"--name {datapoint_name_1} --data-source {datapoint_data_source_1} "
        f"--config {custom_config_path}"
    )

    assert_point_properties(
        datapoint_result_1,
        name=datapoint_name_1,
        data_source=datapoint_data_source_1
    )

    # Add second datapoint
    datapoint_data_source_2 = "sensor/humidity/value"
    custom_config_path, custom_config = create_config_file(tracked_files)

    datapoint_result_2 = run(
        f"az iot ops ns asset custom datapoint add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name_1} "
        f"--name {datapoint_name_2} --data-source {datapoint_data_source_2} "
        f"--config {custom_config_path}"
    )

    assert_point_properties(
        datapoint_result_2,
        name=datapoint_name_2,
        data_source=datapoint_data_source_2
    )

    # 7. LIST DATASET DATAPOINTS
    datapoints_list = run(
        f"az iot ops ns asset custom datapoint list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name_1}"
    )

    datapoint_names = [dp["name"] for dp in datapoints_list]
    assert datapoint_name_1 in datapoint_names
    assert datapoint_name_2 in datapoint_names
    assert len(datapoints_list) >= 2

    # 8. TEST DATAPOINT REPLACE FUNCTIONALITY
    # Replace first datapoint with --replace flag
    replaced_datapoint_data_source = "sensor/temperature/replaced_value"
    custom_config_path, custom_config = create_config_file(tracked_files)

    replaced_datapoint = run(
        f"az iot ops ns asset custom datapoint add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name_1} "
        f"--name {datapoint_name_1} --data-source {replaced_datapoint_data_source} "
        f"--config {custom_config_path} --replace"
    )

    assert_point_properties(
        replaced_datapoint,
        name=datapoint_name_1,
        data_source=replaced_datapoint_data_source
    )

    # 9. REMOVE DATASET DATAPOINT
    run(
        f"az iot ops ns asset custom datapoint remove --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name_1} "
        f"--name {datapoint_name_2}"
    )

    # Verify datapoint removal
    datapoints_list_after_remove = run(
        f"az iot ops ns asset custom datapoint list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name_1}"
    )

    remaining_datapoint_names = [dp["name"] for dp in datapoints_list_after_remove]
    assert datapoint_name_1 in remaining_datapoint_names
    assert datapoint_name_2 not in remaining_datapoint_names

    # 10. REMOVE DATASET
    run(
        f"az iot ops ns asset custom dataset remove --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1}"
    )

    # Verify dataset removal
    datasets_list_after_remove = run(
        f"az iot ops ns asset custom dataset list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group}"
    )

    remaining_dataset_names = [dataset["name"] for dataset in datasets_list_after_remove]
    assert dataset_name_1 not in remaining_dataset_names


def test_namespace_opcua_asset_dataset_lifecycle_operations(require_init, tracked_resources: List[str]):
    """Test complete lifecycle of OPCUA asset dataset and datapoint operations."""
    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"opcua-{generate_random_string(8)}"
    asset_name = f"opcua-{generate_random_string(8, force_lower=True)}"
    dataset_name_1 = f"dataset{generate_random_string(6, force_lower=True)}"
    dataset_name_2 = f"dataset2{generate_random_string(6, force_lower=True)}"
    datapoint_name_1 = f"dp1-{generate_random_string(6, force_lower=True)}"
    datapoint_name_2 = f"dp2-{generate_random_string(6, force_lower=True)}"

    # Create Device
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    # Create device endpoint
    run(
        f"az iot ops ns device endpoint inbound add opcua --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'opc.tcp://192.168.1.200:4840/OPCUA/Server'"
    )

    # Create OPCUA asset
    asset_opcua = run(
        f"az iot ops ns asset opcua create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name} "
        f"--description \"OPCUA Device for Dataset Testing\" --display \"OPC Temperature Sensor\" "
        f"--model \"OPC-DS200\" --manufacturer \"OPCDevices\""
    )
    tracked_resources.append(asset_opcua["id"])

    # 1. CREATE DATASET
    dataset_data_source = "ns=2;i=1001"
    dataset_destinations = "topic=factory/opcua/temperature qos=Qos1 retain=Keep ttl=3600"

    # Add OPCUA asset dataset with specific OPCUA parameters
    dataset_result = run(
        f"az iot ops ns asset opcua dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1} "
        f"--data-source \"{dataset_data_source}\" "
        f"--destination {dataset_destinations} "
        f"--publish-int 1000 "
        f"--sampling-int 500 "
        f"--queue-size 10 "
        f"--key-frame-count 5 "
    )

    assert_dataset_properties(
        dataset_result,
        name=dataset_name_1,
        data_source=dataset_data_source,
        asset_type="opcua",
        publishing_interval=1000,
    )

    # 2. LIST DATASETS
    datasets_list = run(
        f"az iot ops ns asset opcua dataset list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group}"
    )

    dataset_names = [dataset["name"] for dataset in datasets_list]
    assert dataset_name_1 in dataset_names
    assert len(datasets_list) >= 1

    # 3. SHOW DATASET
    shown_dataset = run(
        f"az iot ops ns asset opcua dataset show --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1}"
    )

    assert_dataset_properties(
        shown_dataset,
        name=dataset_name_1,
        data_source=dataset_data_source,
        asset_type="opcua",
        publishing_interval=1000,
    )

    # 4. UPDATE DATASET
    updated_data_source = "ns=2;i=1002"
    updated_destinations = "topic=factory/opcua/temperature_v2 qos=Qos0 retain=Never ttl=1800"

    updated_dataset = run(
        f"az iot ops ns asset opcua dataset update --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1} "
        f"--data-source \"{updated_data_source}\" "
        f"--destination {updated_destinations} "
        f"--publish-int 2000 "
        f"--sampling-int 1000 "
        f"--queue-size 20"
    )

    assert_dataset_properties(
        updated_dataset,
        name=dataset_name_1,
        data_source=updated_data_source,
        asset_type="opcua",
        publishing_interval=2000,
    )

    # 5a. TEST DATASET REPLACE FUNCTIONALITY
    # Replace dataset with --replace flag
    replaced_data_source = "ns=2;i=1003"

    replaced_dataset = run(
        f"az iot ops ns asset opcua dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1} "
        f"--data-source \"{replaced_data_source}\" "
        f"--publish-int 3000 --replace"
    )

    assert_dataset_properties(
        replaced_dataset,
        name=dataset_name_1,
        data_source=replaced_data_source,
        asset_type="opcua",
        publishing_interval=3000
    )

    # 5. TEST MULTIPLE DATASETS
    data_source = "ns=5;i=1005"

    dataset = run(
        f"az iot ops ns asset opcua dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_2} "
        f"--data-source \"{data_source}\" "
        f"--publish-int 3000 --replace"
    )

    assert_dataset_properties(
        dataset,
        name=dataset_name_2,
        data_source=data_source,
        asset_type="opcua",
        publishing_interval=3000
    )

    # 6. ADD DATASET DATAPOINTS
    # Add first datapoint
    datapoint_data_source_1 = "ns=2;i=2001"

    datapoint_result_1 = run(
        f"az iot ops ns asset opcua datapoint add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name_1} "
        f"--name {datapoint_name_1} --data-source \"{datapoint_data_source_1}\" "
        f"--queue-size 5 --sampling-int 250"
    )

    assert_point_properties(
        datapoint_result_1,
        name=datapoint_name_1,
        data_source=datapoint_data_source_1
    )

    # Add second datapoint
    datapoint_data_source_2 = "ns=2;i=2002"

    datapoint_result_2 = run(
        f"az iot ops ns asset opcua datapoint add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name_1} "
        f"--name {datapoint_name_2} --data-source \"{datapoint_data_source_2}\" "
        f"--queue-size 3 --sampling-int 500"
    )

    assert_point_properties(
        datapoint_result_2,
        name=datapoint_name_2,
        data_source=datapoint_data_source_2
    )

    # 7. LIST DATASET DATAPOINTS
    datapoints_list = run(
        f"az iot ops ns asset opcua datapoint list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name_1}"
    )

    datapoint_names = [dp["name"] for dp in datapoints_list]
    assert datapoint_name_1 in datapoint_names
    assert datapoint_name_2 in datapoint_names
    assert len(datapoints_list) >= 2

    # 8. TEST DATAPOINT REPLACE FUNCTIONALITY
    # Replace first datapoint with --replace flag
    replaced_datapoint_data_source = "ns=2;i=2003"

    replaced_datapoint = run(
        f"az iot ops ns asset opcua datapoint add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name_1} "
        f"--name {datapoint_name_1} --data-source \"{replaced_datapoint_data_source}\" "
        f"--queue-size 15 --sampling-int 100 --replace"
    )

    assert_point_properties(
        replaced_datapoint,
        name=datapoint_name_1,
        data_source=replaced_datapoint_data_source
    )

    # 9. REMOVE DATASET DATAPOINT
    run(
        f"az iot ops ns asset opcua datapoint remove --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name_1} "
        f"--name {datapoint_name_2}"
    )

    # Verify datapoint removal
    datapoints_list_after_remove = run(
        f"az iot ops ns asset opcua datapoint list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name_1}"
    )

    remaining_datapoint_names = [dp["name"] for dp in datapoints_list_after_remove]
    assert datapoint_name_1 in remaining_datapoint_names
    assert datapoint_name_2 not in remaining_datapoint_names

    # 10. REMOVE DATASET
    run(
        f"az iot ops ns asset opcua dataset remove --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1}"
    )

    # Verify dataset removal
    datasets_list_after_remove = run(
        f"az iot ops ns asset opcua dataset list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group}"
    )

    remaining_dataset_names = [dataset["name"] for dataset in datasets_list_after_remove]
    assert dataset_name_1 not in remaining_dataset_names


def test_namespace_rest_asset_dataset_lifecycle_operations(require_init, tracked_resources: List[str]):
    """Test complete lifecycle of REST asset dataset operations."""
    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"rest-{generate_random_string(8)}"
    asset_name = f"rest-{generate_random_string(8, force_lower=True)}"
    dataset_name_1 = f"dataset{generate_random_string(6, force_lower=True)}"

    # Create Device
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    # Create device endpoint
    run(
        f"az iot ops ns device endpoint inbound add rest --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'https://api.example.com/sensors/data'"
    )

    # Create REST asset
    asset_rest = run(
        f"az iot ops ns asset rest create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name} "
        f"--description \"REST API for Dataset Testing\" --display \"Temperature API\" "
        f"--model \"REST-API-v1\" --manufacturer \"APIDevices\""
    )
    tracked_resources.append(asset_rest["id"])

    # 1. CREATE DATASET
    dataset_data_source = "/api/temperature"
    dataset_destinations = "topic=factory/rest/temperature qos=Qos1 retain=Keep ttl=3600"

    # Add REST asset dataset with specific REST parameters
    dataset_result = run(
        f"az iot ops ns asset rest dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1} "
        f"--data-source {dataset_data_source} "
        f"--destination {dataset_destinations} "
        f"--sampling-int 5000"
    )

    assert_dataset_properties(
        dataset_result,
        name=dataset_name_1,
        data_source=dataset_data_source,
        asset_type="rest",
    )

    # 2. LIST DATASETS
    datasets_list = run(
        f"az iot ops ns asset rest dataset list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group}"
    )

    dataset_names = [dataset["name"] for dataset in datasets_list]
    assert dataset_name_1 in dataset_names
    assert len(datasets_list) >= 1

    # 3. SHOW DATASET
    shown_dataset = run(
        f"az iot ops ns asset rest dataset show --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1}"
    )

    assert_dataset_properties(
        shown_dataset,
        name=dataset_name_1,
        data_source=dataset_data_source,
        asset_type="rest",
    )

    # 4. UPDATE DATASET
    updated_destinations = "topic=factory/rest/temperature_v2 qos=Qos0 retain=Never ttl=1800"

    updated_dataset = run(
        f"az iot ops ns asset rest dataset update --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1} "
        f"--destination {updated_destinations} "
        f"--sampling-int 10000"
    )

    assert_dataset_properties(
        updated_dataset,
        name=dataset_name_1,
        asset_type="rest",
    )

    # 5. TEST DATASET REPLACE FUNCTIONALITY
    # Replace dataset with --replace flag
    replaced_data_source = "/api/temperature/replaced"
    broker_destinations = "key=rest-data-cache"

    replaced_dataset = run(
        f"az iot ops ns asset rest dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1} "
        f"--data-source {replaced_data_source} --dest {broker_destinations} "
        f"--sampling-int 15000 --replace"
    )

    assert_dataset_properties(
        replaced_dataset,
        name=dataset_name_1,
        data_source=replaced_data_source,
        asset_type="rest",
    )

    # Verify the destination was updated
    shown_broker_dataset = run(
        f"az iot ops ns asset rest dataset show --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1}"
    )

    # Check that destination target is BrokerStateStore
    destinations = shown_broker_dataset.get("destinations", [])
    assert len(destinations) == 1
    assert destinations[0]["target"] == "BrokerStateStore"
    assert destinations[0]["configuration"]["key"] == "rest-data-cache"

    # 7. TEST WITH MINIMAL CONFIGURATION
    # Test creating dataset with minimal parameters
    minimal_data_source = "/api/minimal"

    minimal_dataset = run(
        f"az iot ops ns asset rest dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1} "
        f"--data-source {minimal_data_source} --replace"
    )

    assert_dataset_properties(
        minimal_dataset,
        name=dataset_name_1,
        data_source=minimal_data_source,
        asset_type="rest"
    )

    # 8. REMOVE DATASET
    run(
        f"az iot ops ns asset rest dataset remove --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1}"
    )

    # Verify dataset removal
    datasets_list_after_remove = run(
        f"az iot ops ns asset rest dataset list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group}"
    )

    remaining_dataset_names = [dataset["name"] for dataset in datasets_list_after_remove]
    assert dataset_name_1 not in remaining_dataset_names


def test_namespace_sse_asset_dataset_lifecycle_operations(require_init, tracked_resources: List[str]):
    """Test complete lifecycle of SSE asset dataset operations."""
    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"sse-{generate_random_string(8)}"
    asset_name = f"sse-{generate_random_string(8, force_lower=True)}"
    dataset_name_1 = f"dataset{generate_random_string(6, force_lower=True)}"

    # Create Device
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    # Create device endpoint
    run(
        f"az iot ops ns device endpoint inbound add sse --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'https://events.example.com/stream'"
    )

    # Create SSE asset
    asset_sse = run(
        f"az iot ops ns asset sse create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name}"
    )
    tracked_resources.append(asset_sse["id"])

    # 1. CREATE DATASET
    dataset_data_source = "/events/temperature"
    dataset_destinations = "topic=factory/sse/temperature qos=Qos1 retain=Keep ttl=3600"

    # Add SSE asset dataset (NOTE: No sampling interval since SSE is event-driven)
    dataset_result = run(
        f"az iot ops ns asset sse dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1} "
        f"--data-source {dataset_data_source} "
        f"--destination {dataset_destinations}"
    )

    assert_dataset_properties(
        dataset_result,
        name=dataset_name_1,
        data_source=dataset_data_source,
        asset_type="sse",
    )

    # 2. LIST DATASETS
    datasets_list = run(
        f"az iot ops ns asset sse dataset list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group}"
    )

    dataset_names = [dataset["name"] for dataset in datasets_list]
    assert dataset_name_1 in dataset_names
    assert len(datasets_list) >= 1

    # 3. SHOW DATASET
    dataset_show = run(
        f"az iot ops ns asset sse dataset show --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1}"
    )

    assert_dataset_properties(
        dataset_show,
        name=dataset_name_1,
        data_source=dataset_data_source,
        asset_type="sse",
    )

    # 4. UPDATE DATASET
    updated_destinations = "topic=factory/sse/temperature_v2 qos=Qos0 retain=Never ttl=1800"

    updated_dataset = run(
        f"az iot ops ns asset sse dataset update --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1} "
        f"--destination {updated_destinations}"
    )

    assert_dataset_properties(
        updated_dataset,
        name=dataset_name_1,
        asset_type="sse",
    )

    # 5. TEST DATASET REPLACE FUNCTIONALITY
    # Replace dataset with --replace flag
    replaced_data_source = "/events/temperature/replaced"
    broker_destinations = "key=sse-data-cache"

    replaced_dataset = run(
        f"az iot ops ns asset sse dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1} "
        f"--data-source {replaced_data_source} --dest {broker_destinations} "
        f"--replace"
    )

    assert_dataset_properties(
        replaced_dataset,
        name=dataset_name_1,
        asset_type="sse",
    )

    # 6. SHOW REPLACED DATASET
    replaced_dataset_show = run(
        f"az iot ops ns asset sse dataset show --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1}"
    )

    assert_dataset_properties(
        replaced_dataset_show,
        name=dataset_name_1,
        data_source=replaced_data_source,
        asset_type="sse",
    )

    # 7. CREATE ADDITIONAL DATASET
    dataset_name_2 = f"dataset2{generate_random_string(6, force_lower=True)}"
    dataset_2_destinations = "topic=factory/sse/pressure qos=Qos1 retain=Keep ttl=7200"

    dataset_2_result = run(
        f"az iot ops ns asset sse dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_2} "
        f"--data-source /events/pressure "
        f"--destination {dataset_2_destinations}"
    )

    assert_dataset_properties(
        dataset_2_result,
        name=dataset_name_2,
        data_source="/events/pressure",
        asset_type="sse",
    )

    # 8. REMOVE DATASET
    run(
        f"az iot ops ns asset sse dataset remove --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1}"
    )

    # Verify dataset removal
    datasets_list_after_remove = run(
        f"az iot ops ns asset sse dataset list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group}"
    )

    remaining_dataset_names = [dataset["name"] for dataset in datasets_list_after_remove]
    assert dataset_name_1 not in remaining_dataset_names


def test_namespace_mqtt_asset_dataset_lifecycle_operations(require_init, tracked_resources: List[str]):
    """Test complete lifecycle of MQTT asset dataset operations."""
    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"mqtt-{generate_random_string(8)}"
    asset_name = f"mqtt-{generate_random_string(8, force_lower=True)}"
    dataset_name_1 = f"dataset{generate_random_string(6, force_lower=True)}"

    # Create Device
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    # Create device endpoint
    run(
        f"az iot ops ns device endpoint inbound add mqtt --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'aio-broker:18883'"
    )

    # Create MQTT asset
    asset_mqtt = run(
        f"az iot ops ns asset mqtt create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name}"
    )
    tracked_resources.append(asset_mqtt["id"])

    # 1. CREATE DATASET
    dataset_data_source = "factory/temperature"
    dataset_destinations = "topic=telemetry/mqtt/temperature qos=Qos1 retain=Keep ttl=3600"

    # Add MQTT asset dataset (NOTE: MQTT datasets support BrokerStateStore and MQTT destinations only, no events)
    dataset_result = run(
        f"az iot ops ns asset mqtt dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1} "
        f"--data-source {dataset_data_source} "
        f"--destination {dataset_destinations}"
    )

    assert_dataset_properties(
        dataset_result,
        name=dataset_name_1,
        data_source=dataset_data_source,
        asset_type="mqtt",
    )

    # 2. LIST DATASETS
    datasets_list = run(
        f"az iot ops ns asset mqtt dataset list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group}"
    )

    dataset_names = [dataset["name"] for dataset in datasets_list]
    assert dataset_name_1 in dataset_names
    assert len(datasets_list) >= 1

    # 3. SHOW DATASET
    dataset_show = run(
        f"az iot ops ns asset mqtt dataset show --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1}"
    )

    assert_dataset_properties(
        dataset_show,
        name=dataset_name_1,
        data_source=dataset_data_source,
        asset_type="mqtt",
    )

    # 4. UPDATE DATASET
    updated_destinations = "topic=telemetry/mqtt/temperature_v2 qos=Qos0 retain=Never ttl=1800"

    updated_dataset = run(
        f"az iot ops ns asset mqtt dataset update --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1} "
        f"--destination {updated_destinations}"
    )

    assert_dataset_properties(
        updated_dataset,
        name=dataset_name_1,
        asset_type="mqtt",
    )

    # 5. TEST DATASET REPLACE FUNCTIONALITY
    # Replace dataset with --replace flag
    replaced_data_source = "factory/temperature/replaced"
    broker_destinations = "key=mqtt-data-cache"

    replaced_dataset = run(
        f"az iot ops ns asset mqtt dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1} "
        f"--data-source {replaced_data_source} --dest {broker_destinations} "
        f"--replace"
    )

    assert_dataset_properties(
        replaced_dataset,
        name=dataset_name_1,
        asset_type="mqtt",
    )

    # 6. SHOW REPLACED DATASET
    replaced_dataset_show = run(
        f"az iot ops ns asset mqtt dataset show --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1}"
    )

    assert_dataset_properties(
        replaced_dataset_show,
        name=dataset_name_1,
        data_source=replaced_data_source,
        asset_type="mqtt",
    )

    # 7. CREATE ADDITIONAL DATASET
    dataset_name_2 = f"dataset2{generate_random_string(6, force_lower=True)}"
    dataset_2_destinations = "topic=telemetry/mqtt/pressure qos=Qos1 retain=Keep ttl=7200"

    dataset_2_result = run(
        f"az iot ops ns asset mqtt dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_2} "
        f"--data-source factory/pressure "
        f"--destination {dataset_2_destinations}"
    )

    assert_dataset_properties(
        dataset_2_result,
        name=dataset_name_2,
        data_source="factory/pressure",
        asset_type="mqtt",
    )

    # 8. REMOVE DATASET
    run(
        f"az iot ops ns asset mqtt dataset remove --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1}"
    )

    # Verify dataset removal
    datasets_list_after_remove = run(
        f"az iot ops ns asset mqtt dataset list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group}"
    )

    remaining_dataset_names = [dataset["name"] for dataset in datasets_list_after_remove]
    assert dataset_name_1 not in remaining_dataset_names


# ==================== EXPORT/IMPORT INTEGRATION TESTS ====================

def test_namespace_asset_datapoint_export_import_json_roundtrip(
    require_init, tracked_resources: List[str], tracked_files: List[str]
):
    """
    Test complete export/import workflow for datapoints in JSON format.
    WHY: Validates most common backup/restore workflow - ensures data integrity
    through full export → delete → import cycle.
    """
    logger.warning("Starting test_namespace_asset_datapoint_export_import_json_roundtrip")
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-export-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"custom-{generate_random_string(8)}"
    asset_name = f"asset-export-{generate_random_string(8, force_lower=True)}"
    dataset_name = f"dataset-{generate_random_string(6, force_lower=True)}"

    # Setup: Create device, endpoint, and asset
    logger.warning("Creating device...")
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    logger.warning("Creating endpoint...")
    run(
        f"az iot ops ns device endpoint inbound add custom --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'http://192.168.1.100:8000/api' --endpoint-type custom"
    )

    logger.warning("Creating asset...")
    asset = run(
        f"az iot ops ns asset custom create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name}"
    )
    tracked_resources.append(asset["id"])

    # Create dataset
    logger.warning("Creating dataset...")
    run(
        f"az iot ops ns asset custom dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name} "
        f"--data-source sensor/data"
    )

    # Add multiple datapoints with different properties
    custom_config_path, custom_config = create_config_file(tracked_files)

    datapoint_configs = [
        {"name": f"dp1-{generate_random_string(4)}", "source": "sensor/temp", "config": custom_config_path},
        {"name": f"dp2-{generate_random_string(4)}", "source": "sensor/humidity", "config": custom_config_path},
        {"name": f"dp3-{generate_random_string(4)}", "source": "sensor/pressure", "config": custom_config_path},
    ]

    logger.warning(f"Adding {len(datapoint_configs)} datapoints...")
    for dp in datapoint_configs:
        run(
            f"az iot ops ns asset custom datapoint add --asset {asset_name} "
            f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
            f"--name {dp['name']} --data-source {dp['source']} --config {dp['config']}"
        )

    # EXPORT datapoints to JSON
    logger.warning("Exporting datapoints...")
    export_result = run(
        f"az iot ops ns asset custom datapoint export --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
        f"--format json"
    )

    exported_file = export_result["file_path"]
    tracked_files.append(exported_file)
    logger.warning(f"Exported to {exported_file}")

    # Verify file exists and contains expected datapoints
    with open(exported_file, 'r') as f:
        exported_data = json.load(f)

    assert len(exported_data) == 3
    exported_names = [dp["name"] for dp in exported_data]
    assert all(dp["name"] in exported_names for dp in datapoint_configs)

    # Delete all datapoints
    logger.warning("Deleting datapoints...")
    for dp in datapoint_configs:
        run(
            f"az iot ops ns asset custom datapoint remove --asset {asset_name} "
            f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
            f"--name {dp['name']}"
        )

    # Verify datapoints deleted
    datapoints_after_delete = run(
        f"az iot ops ns asset custom datapoint list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name}"
    )
    assert len(datapoints_after_delete) == 0

    # IMPORT datapoints back from file
    logger.warning("Importing datapoints...")
    imported_datapoints = run(
        f"az iot ops ns asset custom datapoint import --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
        f"--input-file {exported_file}"
    )

    logger.warning("Verifying import...")
    # Verify all datapoints restored
    assert len(imported_datapoints) == 3
    imported_names = [dp["name"] for dp in imported_datapoints]
    assert all(dp["name"] in imported_names for dp in datapoint_configs)

    # Verify properties preserved
    for original_dp in datapoint_configs:
        restored_dp = next(dp for dp in imported_datapoints if dp["name"] == original_dp["name"])
        assert restored_dp["dataSource"] == original_dp["source"]

    logger.warning("Test completed successfully.")


def test_namespace_asset_datapoint_export_import_csv_format(
    require_init, tracked_resources: List[str], tracked_files: List[str]
):
    """
    Test CSV format export/import for DOE web UI compatibility.
    WHY: CSV is critical for interoperability with DOE web interface.
    """
    logger.warning("Starting test_namespace_asset_datapoint_export_import_csv_format")
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-csv-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"opcua-{generate_random_string(8)}"
    asset_name = f"asset-csv-{generate_random_string(8, force_lower=True)}"
    dataset_name = f"dataset-csv-{generate_random_string(6, force_lower=True)}"

    # Setup OPC UA asset (CSV commonly used with OPC UA)
    logger.warning("Creating device...")
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    logger.warning("Creating endpoint...")
    run(
        f"az iot ops ns device endpoint inbound add opcua --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'opc.tcp://192.168.1.200:4840'"
    )

    logger.warning("Creating asset...")
    asset = run(
        f"az iot ops ns asset opcua create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name}"
    )
    tracked_resources.append(asset["id"])

    # Create dataset and datapoints
    logger.warning("Creating dataset and datapoints...")
    run(
        f"az iot ops ns asset opcua dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name} "
        f"--data-source \"ns=2;i=1000\" --publish-int 1000"
    )

    datapoints = [
        {"name": f"temp-{generate_random_string(4)}", "source": "ns=2;i=2001"},
        {"name": f"pressure-{generate_random_string(4)}", "source": "ns=2;i=2002"},
    ]

    for dp in datapoints:
        run(
            f"az iot ops ns asset opcua datapoint add --asset {asset_name} "
            f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
            f"--name {dp['name']} --data-source \"{dp['source']}\" "
            f"--queue-size 5 --sampling-int 500"
        )

    # EXPORT to CSV
    logger.warning("Exporting to CSV...")
    export_result = run(
        f"az iot ops ns asset opcua datapoint export --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
        f"--format csv"
    )

    csv_file = export_result["file_path"]
    tracked_files.append(csv_file)
    logger.warning(f"Exported to {csv_file}")
    assert csv_file.endswith('.csv')

    # Delete datapoints
    logger.warning("Deleting datapoints...")
    for dp in datapoints:
        run(
            f"az iot ops ns asset opcua datapoint remove --asset {asset_name} "
            f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
            f"--name {dp['name']}"
        )

    # IMPORT from CSV
    logger.warning("Importing from CSV...")
    imported_datapoints = run(
        f"az iot ops ns asset opcua datapoint import --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
        f"--input-file {csv_file}"
    )

    # Verify CSV round-trip successful
    logger.warning("Verifying CSV round-trip...")
    assert len(imported_datapoints) == 2
    imported_names = [dp["name"] for dp in imported_datapoints]
    assert all(dp["name"] in imported_names for dp in datapoints)
    logger.warning("Test completed successfully.")


def test_namespace_asset_dataset_export_import_roundtrip(
    require_init, tracked_resources: List[str], tracked_files: List[str]
):
    """
    Test bulk dataset export/import workflow.
    WHY: Validates backup/restore of entire dataset configurations (without datapoints).
    """
    logger.warning("Starting test_namespace_asset_dataset_export_import_roundtrip")
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-bulk-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"rest-{generate_random_string(8)}"
    asset_name = f"asset-bulk-{generate_random_string(8, force_lower=True)}"

    # Setup REST asset
    logger.warning("Creating device...")
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    logger.warning("Creating endpoint...")
    run(
        f"az iot ops ns device endpoint inbound add rest --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'https://api.example.com/data'"
    )

    logger.warning("Creating asset...")
    asset = run(
        f"az iot ops ns asset rest create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name}"
    )
    tracked_resources.append(asset["id"])

    # Create multiple datasets with different configurations
    logger.warning("Creating datasets...")
    datasets = [
        {"name": f"dataset1-{generate_random_string(4)}", "source": "/api/temp", "sampling": 5000},
        {"name": f"dataset2-{generate_random_string(4)}", "source": "/api/humidity", "sampling": 10000},
        {"name": f"dataset3-{generate_random_string(4)}", "source": "/api/pressure", "sampling": 15000},
    ]

    for ds in datasets:
        run(
            f"az iot ops ns asset rest dataset add --asset {asset_name} "
            f"--instance {instance_name} -g {resource_group} --name {ds['name']} "
            f"--data-source {ds['source']} --sampling-int {ds['sampling']}"
        )

    # EXPORT all datasets to JSON
    logger.warning("Exporting datasets...")
    export_result = run(
        f"az iot ops ns asset rest dataset export --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --format json"
    )

    exported_file = export_result["file_path"]
    tracked_files.append(exported_file)
    logger.warning(f"Exported to {exported_file}")

    # Verify exported content
    with open(exported_file, 'r') as f:
        exported_datasets = json.load(f)

    assert len(exported_datasets) == 3
    # Verify dataPoints arrays removed in export
    for ds in exported_datasets:
        assert "dataPoints" not in ds
        assert "name" in ds
        assert "dataSource" in ds

    # Delete all datasets
    logger.warning("Deleting datasets...")
    for ds in datasets:
        run(
            f"az iot ops ns asset rest dataset remove --asset {asset_name} "
            f"--instance {instance_name} -g {resource_group} --name {ds['name']}"
        )

    # Verify datasets deleted
    datasets_after_delete = run(
        f"az iot ops ns asset rest dataset list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group}"
    )
    assert len(datasets_after_delete) == 0

    # IMPORT datasets back
    logger.warning("Importing datasets...")
    imported_datasets = run(
        f"az iot ops ns asset rest dataset import --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --input-file {exported_file}"
    )

    # Verify all datasets restored
    logger.warning("Verifying import...")
    assert len(imported_datasets) == 3
    imported_names = [ds["name"] for ds in imported_datasets]
    assert all(ds["name"] in imported_names for ds in datasets)
    logger.warning("Test completed successfully.")


def test_namespace_asset_datapoint_import_skip_duplicates(
    require_init, tracked_resources: List[str], tracked_files: List[str]
):
    """
    Test duplicate-skip behavior during datapoint import.
    WHY: Prevents data loss - ensures existing datapoints not overwritten accidentally.
    """
    logger.warning("Starting test_namespace_asset_datapoint_import_skip_duplicates")
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-dup-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"custom-{generate_random_string(8)}"
    asset_name = f"asset-dup-{generate_random_string(8, force_lower=True)}"
    dataset_name = f"dataset-dup-{generate_random_string(6, force_lower=True)}"

    # Setup
    logger.warning("Creating device...")
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    logger.warning("Creating endpoint...")
    run(
        f"az iot ops ns device endpoint inbound add custom --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'http://192.168.1.100:8000/api' --endpoint-type custom"
    )

    logger.warning("Creating asset...")
    asset = run(
        f"az iot ops ns asset custom create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name}"
    )
    tracked_resources.append(asset["id"])

    logger.warning("Creating dataset...")
    run(
        f"az iot ops ns asset custom dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name} "
        f"--data-source sensor/data"
    )

    # Add initial datapoints
    logger.warning("Adding initial datapoints...")
    custom_config_path, _ = create_config_file(tracked_files)

    initial_datapoints = [
        {"name": "dp1", "source": "sensor/temp"},
        {"name": "dp2", "source": "sensor/humidity"},
    ]

    for dp in initial_datapoints:
        run(
            f"az iot ops ns asset custom datapoint add --asset {asset_name} "
            f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
            f"--name {dp['name']} --data-source {dp['source']} --config {custom_config_path}"
        )

    # Export initial datapoints
    logger.warning("Exporting initial datapoints...")
    export_result = run(
        f"az iot ops ns asset custom datapoint export --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name}"
    )

    exported_file = export_result["file_path"]
    tracked_files.append(exported_file)
    logger.warning(f"Exported to {exported_file}")

    # Add more datapoints manually (creating a mixed state)
    logger.warning("Adding more datapoints manually...")
    run(
        f"az iot ops ns asset custom datapoint add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
        f"--name dp3 --data-source sensor/pressure --config {custom_config_path}"
    )

    # Now import from file (contains dp1, dp2 which exist + dp3 was added manually)
    logger.warning("Importing from file (should skip duplicates)...")
    imported_datapoints = run(
        f"az iot ops ns asset custom datapoint import --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
        f"--input-file {exported_file}"
    )

    # Verify: Should have all 3 datapoints (2 from file skipped as duplicates, manual dp3 preserved)
    logger.warning("Verifying results...")
    assert len(imported_datapoints) == 3
    datapoint_names = [dp["name"] for dp in imported_datapoints]
    assert "dp1" in datapoint_names
    assert "dp2" in datapoint_names
    assert "dp3" in datapoint_names
    logger.warning("Test completed successfully.")


def test_namespace_asset_dataset_export_yaml_format(
    require_init, tracked_resources: List[str], tracked_files: List[str]
):
    """
    Test YAML format export for datasets.
    WHY: YAML is human-readable and commonly used in DevOps workflows.
    """
    logger.warning("Starting test_namespace_asset_dataset_export_yaml_format")
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-yaml-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"custom-{generate_random_string(8)}"
    asset_name = f"asset-yaml-{generate_random_string(8, force_lower=True)}"

    # Setup
    logger.warning("Creating device...")
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    logger.warning("Creating endpoint...")
    run(
        f"az iot ops ns device endpoint inbound add custom --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'http://192.168.1.100:8000/api' --endpoint-type custom"
    )

    logger.warning("Creating asset...")
    asset = run(
        f"az iot ops ns asset custom create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name}"
    )
    tracked_resources.append(asset["id"])

    # Create dataset
    logger.warning("Creating dataset...")
    custom_config_path, _ = create_config_file(tracked_files)

    dataset_name = f"dataset-yaml-{generate_random_string(6)}"
    run(
        f"az iot ops ns asset custom dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name} "
        f"--data-source sensor/data --config {custom_config_path}"
    )

    # EXPORT to YAML
    logger.warning("Exporting to YAML...")
    export_result = run(
        f"az iot ops ns asset custom dataset export --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --format yaml"
    )

    yaml_file = export_result["file_path"]
    tracked_files.append(yaml_file)
    logger.warning(f"Exported to {yaml_file}")
    assert yaml_file.endswith('.yaml')

    # Delete dataset
    logger.warning("Deleting dataset...")
    run(
        f"az iot ops ns asset custom dataset remove --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name}"
    )

    # IMPORT from YAML
    logger.warning("Importing from YAML...")
    imported_datasets = run(
        f"az iot ops ns asset custom dataset import --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --input-file {yaml_file}"
    )

    # Verify YAML round-trip successful
    logger.warning("Verifying YAML round-trip...")
    assert len(imported_datasets) == 1
    assert imported_datasets[0]["name"] == dataset_name
    logger.warning("Test completed successfully.")
