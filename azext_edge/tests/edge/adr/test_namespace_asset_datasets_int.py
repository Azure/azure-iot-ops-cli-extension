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

def test_custom_asset_datapoint_export_import_json_roundtrip(
    require_init, tracked_resources: List[str], tracked_files: List[str]
):
    """
    Test complete export/import workflow for Custom asset datapoints in JSON format.
    WHY: Validates most common backup/restore workflow - ensures data integrity
    through full export → delete → import cycle.
    """
    logger.warning("Starting test_custom_asset_datapoint_export_import_json_roundtrip")
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


def test_opcua_asset_datapoint_export_import_csv_format(
    require_init, tracked_resources: List[str], tracked_files: List[str]
):
    """
    Test CSV format export/import for OPC UA asset datapoints and DOE web UI compatibility.
    WHY: CSV is critical for interoperability with DOE web interface.
    """
    logger.warning("Starting test_opcua_asset_datapoint_export_import_csv_format")
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


def test_rest_asset_dataset_export_import_roundtrip(
    require_init, tracked_resources: List[str], tracked_files: List[str]
):
    """
    Test bulk REST asset dataset export/import workflow.
    WHY: Validates backup/restore of entire dataset configurations for REST assets.
    NOTE: REST assets don't have datapoints - datasets are the data items.
    """
    logger.warning("Starting test_rest_asset_dataset_export_import_roundtrip")
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


def test_custom_asset_datapoint_import_skip_duplicates(
    require_init, tracked_resources: List[str], tracked_files: List[str]
):
    """
    Test duplicate-skip behavior during Custom asset datapoint import.
    WHY: Prevents data loss - ensures existing datapoints not overwritten accidentally.
    """
    logger.warning("Starting test_custom_asset_datapoint_import_skip_duplicates")
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


def test_custom_asset_dataset_export_yaml_format(
    require_init, tracked_resources: List[str], tracked_files: List[str]
):
    """
    Test YAML format export for Custom asset datasets.
    WHY: YAML is human-readable and commonly used in DevOps workflows.
    """
    logger.warning("Starting test_custom_asset_dataset_export_yaml_format")
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


# ==================== VALIDATION INTEGRATION TESTS ====================

def test_custom_asset_datapoint_import_with_malformed_json_rejected(
    require_init, tracked_resources: List[str], tracked_files: List[str]
):
    """
    Test that Custom asset datapoint import file with malformed JSON is rejected immediately.
    WHY: File parsing errors must be caught before network calls.
    Priority: HIGH - Basic input validation
    """
    logger.warning("Starting test_custom_asset_datapoint_import_with_malformed_json_rejected")
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-malformed-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"custom-{generate_random_string(8)}"
    asset_name = f"asset-malformed-{generate_random_string(8, force_lower=True)}"
    dataset_name = f"dataset-{generate_random_string(6, force_lower=True)}"

    # Setup: Create device, endpoint, asset, and dataset
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

    # Create malformed JSON file
    import tempfile
    import os
    malformed_json_content = '[{"name": "dp1", "dataSource": "source1"'  # Missing closing brackets
    
    fd, malformed_file = tempfile.mkstemp(suffix='.json', text=True)
    tracked_files.append(malformed_file)
    try:
        os.write(fd, malformed_json_content.encode('utf-8'))
    finally:
        os.close(fd)

    logger.warning(f"Created malformed JSON file: {malformed_file}")

    # Attempt import - should fail
    logger.warning("Attempting to import malformed JSON...")
    
    try:
        run(
            f"az iot ops ns asset custom datapoint import --asset {asset_name} "
            f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
            f"--input-file {malformed_file}",
            expect_failure=True
        )
        # If we get here without exception, the command didn't fail as expected
        assert False, "Import should have failed with malformed JSON"
    except Exception as e:
        error_msg = str(e).lower()
        # Verify error mentions JSON parsing
        assert "json" in error_msg or "parse" in error_msg or "invalid" in error_msg, \
            f"Error should mention JSON/parsing issue: {e}"
        logger.warning(f"Import correctly rejected with error: {e}")

    # Verify no datapoints were created
    datapoints_list = run(
        f"az iot ops ns asset custom datapoint list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name}"
    )
    assert len(datapoints_list) == 0, "No datapoints should be created when JSON is malformed"

    logger.warning("Test completed successfully - malformed JSON was rejected.")


def test_datapoint_import_with_invalid_configuration_rejected_opcua(
    require_init, tracked_resources: List[str], tracked_files: List[str]
):
    """
    Test that OPC UA datapoints with invalid configuration are rejected.
    WHY: End-to-end validation that bad data is caught before persistence.
    
    Validation rules (OPC UA connector metadata JSON schema):
    - samplingInterval: minimum -1 (so -1000 is INVALID, -1 is VALID)
    - queueSize: minimum 0 (so negative is INVALID)
    
    Priority: HIGH - Invalid configuration rejection
    """
    logger.warning("Starting test_datapoint_import_with_invalid_configuration_rejected_opcua")
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-invalid-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"opcua-{generate_random_string(8)}"
    asset_name = f"asset-invalid-{generate_random_string(8, force_lower=True)}"
    dataset_name = f"dataset-{generate_random_string(6, force_lower=True)}"

    # Setup: Create OPC UA asset
    logger.warning("Creating device...")
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    logger.warning("Creating OPC UA endpoint...")
    run(
        f"az iot ops ns device endpoint inbound add opcua --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'opc.tcp://192.168.1.200:4840'"
    )

    logger.warning("Creating OPC UA asset...")
    asset = run(
        f"az iot ops ns asset opcua create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name}"
    )
    tracked_resources.append(asset["id"])

    logger.warning("Creating dataset...")
    run(
        f"az iot ops ns asset opcua dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name} "
        f"--data-source \"ns=2;i=1000\" --publish-int 1000"
    )

    # Create JSON file with invalid configuration (negative samplingInterval)
    import tempfile
    import os
    
    invalid_datapoints = [
        {
            "name": "temp_invalid",
            "dataSource": "ns=2;i=2001",
            "dataPointConfiguration": json.dumps({"samplingInterval": -1000, "queueSize": 10})  # -1000 < -1 (minimum), INVALID!
        }
    ]
    
    fd, invalid_file = tempfile.mkstemp(suffix='.json', text=True)
    tracked_files.append(invalid_file)
    try:
        os.write(fd, json.dumps(invalid_datapoints).encode('utf-8'))
    finally:
        os.close(fd)

    logger.warning(f"Created file with invalid configuration: {invalid_file}")

    # Attempt import - should fail with validation error
    logger.warning("Attempting to import datapoints with invalid configuration...")
    
    try:
        run(
            f"az iot ops ns asset opcua datapoint import --asset {asset_name} "
            f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
            f"--input-file {invalid_file}",
            expect_failure=True
        )
        assert False, "Import should have failed with invalid configuration"
    except Exception as e:
        error_msg = str(e).lower()
        # Verify error mentions validation
        assert "validat" in error_msg, f"Error should mention validation: {e}"
        logger.warning(f"Import correctly rejected with validation error: {e}")

    # Verify no datapoints were created
    datapoints_list = run(
        f"az iot ops ns asset opcua datapoint list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name}"
    )
    assert len(datapoints_list) == 0, "No datapoints should be created when validation fails"

    logger.warning("Test completed successfully - invalid configuration was rejected.")


def test_opcua_datapoint_add_with_invalid_configuration_rejected(
    require_init, tracked_resources: List[str]
):
    """
    Test that adding an OPC UA datapoint with invalid configuration via CLI is rejected.
    WHY: Validation should work for direct add operations, not just import.
    
    Validation rules (OPC UA):
    - samplingInterval: minimum -1 (so -500 is INVALID, -1 is VALID)
    
    Priority: HIGH - Validation in all entry points
    """
    logger.warning("Starting test_opcua_datapoint_add_with_invalid_configuration_rejected")
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-add-invalid-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"opcua-{generate_random_string(8)}"
    asset_name = f"asset-add-{generate_random_string(8, force_lower=True)}"
    dataset_name = f"dataset-{generate_random_string(6, force_lower=True)}"

    # Setup
    logger.warning("Creating device...")
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    logger.warning("Creating OPC UA endpoint...")
    run(
        f"az iot ops ns device endpoint inbound add opcua --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'opc.tcp://192.168.1.200:4840'"
    )

    logger.warning("Creating OPC UA asset...")
    asset = run(
        f"az iot ops ns asset opcua create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name}"
    )
    tracked_resources.append(asset["id"])

    logger.warning("Creating dataset...")
    run(
        f"az iot ops ns asset opcua dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name} "
        f"--data-source \"ns=2;i=1000\" --publish-int 1000"
    )

    # Attempt to add datapoint with negative sampling interval
    logger.warning("Attempting to add datapoint with negative sampling interval...")
    
    try:
        run(
            f"az iot ops ns asset opcua datapoint add --asset {asset_name} "
            f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
            f"--name temp_invalid --data-source \"ns=2;i=2001\" "
            f"--sampling-int -500 --queue-size 10",  # -500 < -1 (minimum), INVALID!
            expect_failure=True
        )
        assert False, "Add should have failed with negative sampling interval"
    except Exception as e:
        error_msg = str(e).lower()
        # Verify error mentions validation or negative value
        assert ("validat" in error_msg or "negative" in error_msg or 
                "minimum" in error_msg or "invalid" in error_msg), \
                f"Error should mention validation issue: {e}"
        logger.warning(f"Add correctly rejected with error: {e}")

    # Verify no datapoints were created
    datapoints_list = run(
        f"az iot ops ns asset opcua datapoint list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name}"
    )
    assert len(datapoints_list) == 0, "No datapoints should be created when validation fails"

    logger.warning("Test completed successfully - invalid add was rejected.")


def test_opcua_dataset_import_with_invalid_configuration_rejected(
    require_init, tracked_resources: List[str], tracked_files: List[str]
):
    """
    Test that OPC UA datasets with invalid configuration are rejected during import.
    WHY: Dataset-level validation must work end-to-end.
    
    Validation rules (OPC UA):
    - publishingInterval: minimum -1 (so -1000 is INVALID, -1 is VALID)
    
    Priority: HIGH - Dataset validation
    """
    logger.warning("Starting test_opcua_dataset_import_with_invalid_configuration_rejected")
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-ds-invalid-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"opcua-{generate_random_string(8)}"
    asset_name = f"asset-ds-{generate_random_string(8, force_lower=True)}"

    # Setup
    logger.warning("Creating device...")
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    logger.warning("Creating OPC UA endpoint...")
    run(
        f"az iot ops ns device endpoint inbound add opcua --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'opc.tcp://192.168.1.200:4840'"
    )

    logger.warning("Creating OPC UA asset...")
    asset = run(
        f"az iot ops ns asset opcua create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name}"
    )
    tracked_resources.append(asset["id"])

    # Create JSON file with invalid dataset configuration
    import tempfile
    import os
    
    invalid_datasets = [
        {
            "name": f"dataset-invalid-{generate_random_string(6)}",
            "dataSource": "ns=2;i=1000",
            "datasetConfiguration": json.dumps({
                "publishingInterval": -1000,  # -1000 < -1 (minimum), INVALID!
                "samplingInterval": 500
            }),
            "dataPoints": []
        }
    ]
    
    fd, invalid_file = tempfile.mkstemp(suffix='.json', text=True)
    tracked_files.append(invalid_file)
    try:
        os.write(fd, json.dumps(invalid_datasets).encode('utf-8'))
    finally:
        os.close(fd)

    logger.warning(f"Created file with invalid dataset configuration: {invalid_file}")

    # Attempt import - should fail with validation error
    logger.warning("Attempting to import dataset with invalid configuration...")
    
    try:
        run(
            f"az iot ops ns asset opcua dataset import --asset {asset_name} "
            f"--instance {instance_name} -g {resource_group} --input-file {invalid_file}",
            expect_failure=True
        )
        assert False, "Import should have failed with invalid dataset configuration"
    except Exception as e:
        error_msg = str(e).lower()
        # Verify error mentions validation
        assert "validat" in error_msg, f"Error should mention validation: {e}"
        logger.warning(f"Import correctly rejected with validation error: {e}")

    # Verify no datasets were created
    datasets_list = run(
        f"az iot ops ns asset opcua dataset list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group}"
    )
    assert len(datasets_list) == 0, "No datasets should be created when validation fails"

    logger.warning("Test completed successfully - invalid dataset configuration was rejected.")


def test_opcua_datapoint_import_with_mixed_valid_invalid_rejected(
    require_init, tracked_resources: List[str], tracked_files: List[str]
):
    """
    Test that OPC UA import with mixed valid/invalid datapoints rejects entire batch.
    WHY: Validation should be atomic - all or nothing to prevent partial state.
    
    Validation rules (OPC UA):
    - samplingInterval: minimum -1 (so -500 in mixed batch is INVALID)
    
    Priority: HIGH - Atomic validation
    """
    logger.warning("Starting test_opcua_datapoint_import_with_mixed_valid_invalid_rejected")
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-mixed-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"opcua-{generate_random_string(8)}"
    asset_name = f"asset-mixed-{generate_random_string(8, force_lower=True)}"
    dataset_name = f"dataset-{generate_random_string(6, force_lower=True)}"

    # Setup
    logger.warning("Creating device...")
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    logger.warning("Creating OPC UA endpoint...")
    run(
        f"az iot ops ns device endpoint inbound add opcua --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'opc.tcp://192.168.1.200:4840'"
    )

    logger.warning("Creating OPC UA asset...")
    asset = run(
        f"az iot ops ns asset opcua create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name}"
    )
    tracked_resources.append(asset["id"])

    logger.warning("Creating dataset...")
    run(
        f"az iot ops ns asset opcua dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name} "
        f"--data-source \"ns=2;i=1000\" --publish-int 1000"
    )

    # Create file with 3 datapoints: 2 valid, 1 invalid
    import tempfile
    import os
    
    mixed_datapoints = [
        {
            "name": "temp_valid",
            "dataSource": "ns=2;i=2001",
            "dataPointConfiguration": json.dumps({"samplingInterval": 1000, "queueSize": 10})
        },
        {
            "name": "pressure_invalid",
            "dataSource": "ns=2;i=2002",
            "dataPointConfiguration": json.dumps({"samplingInterval": -500, "queueSize": 5})  # -500 < -1, INVALID!
        },
        {
            "name": "humidity_valid",
            "dataSource": "ns=2;i=2003",
            "dataPointConfiguration": json.dumps({"samplingInterval": 2000, "queueSize": 8})
        }
    ]
    
    fd, mixed_file = tempfile.mkstemp(suffix='.json', text=True)
    tracked_files.append(mixed_file)
    try:
        os.write(fd, json.dumps(mixed_datapoints).encode('utf-8'))
    finally:
        os.close(fd)

    logger.warning(f"Created file with mixed valid/invalid datapoints: {mixed_file}")

    # Attempt import - should fail due to one invalid datapoint
    logger.warning("Attempting to import mixed valid/invalid datapoints...")
    
    try:
        run(
            f"az iot ops ns asset opcua datapoint import --asset {asset_name} "
            f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
            f"--input-file {mixed_file}",
            expect_failure=True
        )
        assert False, "Import should have failed due to invalid datapoint in batch"
    except Exception as e:
        error_msg = str(e)
        error_msg_lower = error_msg.lower()
        # Verify error mentions validation and the invalid datapoint
        assert "validat" in error_msg_lower, f"Error should mention validation: {e}"
        assert "pressure_invalid" in error_msg or "1 data point" in error_msg, \
            f"Error should identify the invalid datapoint: {e}"
        logger.warning(f"Import correctly rejected entire batch: {e}")

    # Verify NO datapoints were created (atomic failure)
    datapoints_list = run(
        f"az iot ops ns asset opcua datapoint list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name}"
    )
    assert len(datapoints_list) == 0, \
        "No datapoints should be created when batch contains invalid items (atomic validation)"

    logger.warning("Test completed successfully - entire batch was rejected atomically.")


def test_opcua_datapoint_import_with_valid_configuration_succeeds(
    require_init, tracked_resources: List[str], tracked_files: List[str]
):
    """
    Test that valid OPC UA datapoints pass validation and are imported successfully.
    WHY: Verify validation doesn't break valid scenarios (positive test).
    Priority: HIGH - Regression prevention
    """
    logger.warning("Starting test_opcua_datapoint_import_with_valid_configuration_succeeds")
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-valid-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"opcua-{generate_random_string(8)}"
    asset_name = f"asset-valid-{generate_random_string(8, force_lower=True)}"
    dataset_name = f"dataset-{generate_random_string(6, force_lower=True)}"

    # Setup
    logger.warning("Creating device...")
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    logger.warning("Creating OPC UA endpoint...")
    run(
        f"az iot ops ns device endpoint inbound add opcua --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'opc.tcp://192.168.1.200:4840'"
    )

    logger.warning("Creating OPC UA asset...")
    asset = run(
        f"az iot ops ns asset opcua create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name}"
    )
    tracked_resources.append(asset["id"])

    logger.warning("Creating dataset...")
    run(
        f"az iot ops ns asset opcua dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name} "
        f"--data-source \"ns=2;i=1000\" --publish-int 1000"
    )

    # Create file with valid datapoints
    import tempfile
    import os
    
    valid_datapoints = [
        {
            "name": "temp_valid",
            "dataSource": "ns=2;i=2001",
            "dataPointConfiguration": json.dumps({"samplingInterval": 1000, "queueSize": 10})
        },
        {
            "name": "pressure_valid",
            "dataSource": "ns=2;i=2002",
            "dataPointConfiguration": json.dumps({"samplingInterval": 500, "queueSize": 5})
        }
    ]
    
    fd, valid_file = tempfile.mkstemp(suffix='.json', text=True)
    tracked_files.append(valid_file)
    try:
        os.write(fd, json.dumps(valid_datapoints).encode('utf-8'))
    finally:
        os.close(fd)

    logger.warning(f"Created file with valid datapoints: {valid_file}")

    # Import should succeed
    logger.warning("Importing valid datapoints...")
    imported = run(
        f"az iot ops ns asset opcua datapoint import --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
        f"--input-file {valid_file}"
    )

    # Verify datapoints were created
    assert len(imported) == 2, f"Should import 2 datapoints, got {len(imported)}"
    datapoint_names = [dp["name"] for dp in imported]
    assert "temp_valid" in datapoint_names
    assert "pressure_valid" in datapoint_names

    logger.warning("Test completed successfully - valid datapoints were imported.")


def test_opcua_datapoint_import_with_negative_one_sampling_interval_succeeds(
    require_init, tracked_resources: List[str], tracked_files: List[str]
):
    """
    Test that OPC UA samplingInterval: -1 is VALID (special value meaning "use default").
    WHY: Schema defines minimum: -1, so -1 should pass but -2 or lower should fail.
    Priority: HIGH - Edge case validation
    """
    logger.warning("Starting test_opcua_datapoint_import_with_negative_one_sampling_interval_succeeds")
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-neg1-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"opcua-{generate_random_string(8)}"
    asset_name = f"asset-neg1-{generate_random_string(8, force_lower=True)}"
    dataset_name = f"dataset-{generate_random_string(6, force_lower=True)}"

    # Setup
    logger.warning("Creating device...")
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    logger.warning("Creating OPC UA endpoint...")
    run(
        f"az iot ops ns device endpoint inbound add opcua --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'opc.tcp://192.168.1.200:4840'"
    )

    logger.warning("Creating OPC UA asset...")
    asset = run(
        f"az iot ops ns asset opcua create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name}"
    )
    tracked_resources.append(asset["id"])

    logger.warning("Creating dataset...")
    run(
        f"az iot ops ns asset opcua dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name} "
        f"--data-source \"ns=2;i=1000\" --publish-int 1000"
    )

    # Create file with samplingInterval: -1 (valid - means "use default")
    import tempfile
    import os
    
    datapoints_with_neg1 = [
        {
            "name": "temp_default",
            "dataSource": "ns=2;i=2001",
            "dataPointConfiguration": json.dumps({"samplingInterval": -1, "queueSize": 10})  # -1 is VALID
        },
        {
            "name": "pressure_default",
            "dataSource": "ns=2;i=2002",
            "dataPointConfiguration": json.dumps({"samplingInterval": -1, "queueSize": 5})
        }
    ]
    
    fd, neg1_file = tempfile.mkstemp(suffix='.json', text=True)
    tracked_files.append(neg1_file)
    try:
        os.write(fd, json.dumps(datapoints_with_neg1).encode('utf-8'))
    finally:
        os.close(fd)

    logger.warning(f"Created file with samplingInterval: -1 (use default): {neg1_file}")

    # Import should SUCCEED (samplingInterval: -1 is valid per schema minimum: -1)
    logger.warning("Importing datapoints with samplingInterval: -1...")
    imported = run(
        f"az iot ops ns asset opcua datapoint import --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
        f"--input-file {neg1_file}"
    )

    # Verify datapoints were created successfully
    assert len(imported) == 2, f"Should import 2 datapoints, got {len(imported)}"
    datapoint_names = [dp["name"] for dp in imported]
    assert "temp_default" in datapoint_names
    assert "pressure_default" in datapoint_names

    logger.warning("Test completed successfully - samplingInterval: -1 was accepted as valid.")




