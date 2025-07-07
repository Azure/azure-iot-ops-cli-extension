# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List

from ....generators import generate_random_string
from ....helpers import run


def test_namespace_custom_asset_dataset_lifecycle_operations(require_init, tracked_resources: List[str]):
    """Test complete lifecycle of custom asset dataset and datapoint operations."""
    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"custom-{generate_random_string(8)}"
    asset_name = f"custom-{generate_random_string(8, force_lower=True)}"
    dataset_name = f"dataset-{generate_random_string(6, force_lower=True)}"
    datapoint_name_1 = f"dp1-{generate_random_string(6, force_lower=True)}"
    datapoint_name_2 = f"dp2-{generate_random_string(6, force_lower=True)}"

    # Create Device
    result = run(
        f"az iot ops ns device create - {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    # Create device endpoint
    run(
        f"az iot ops ns device endpoint inbound add custom - {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'http://192.168.1.100:8000/custom/service' "
        "--endpoint-type custom"
    )

    # Create Custom asset
    asset_custom = run(
        f"az iot ops ns asset custom create - {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name} "
        f"--description \"Custom Device for Dataset Testing\" --display \"Multi-Sensor Dataset\" "
        f"--model \"Custom-DS100\" --manufacturer \"CustomDevices\""
    )
    tracked_resources.append(asset_custom["id"])

    # 1. CREATE DATASET
    dataset_data_source = "sensor/temperature"
    dataset_destinations = "topic=factory/temperature qos=Qos1 retain=Keep ttl=3600"
    dataset_custom_config = '{"pollingInterval": 1000, "format": "json"}'

    # Add custom asset dataset
    dataset_result = run(
        f"az iot ops ns asset custom dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
        f"--dataset-data-source {dataset_data_source} "
        f"--dataset-destinations {dataset_destinations} "
        f"--dataset-custom-configuration '{dataset_custom_config}'"
    )

    assert_dataset_properties(
        dataset_result,
        name=dataset_name,
        data_source=dataset_data_source,
        asset_type="custom"
    )

    # 2. LIST DATASETS
    datasets_list = run(
        f"az iot ops ns asset custom dataset list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group}"
    )

    dataset_names = [dataset["name"] for dataset in datasets_list]
    assert dataset_name in dataset_names
    assert len(datasets_list) >= 1

    # 3. SHOW DATASET
    shown_dataset = run(
        f"az iot ops ns asset custom dataset show --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name}"
    )

    assert_dataset_properties(
        shown_dataset,
        name=dataset_name,
        data_source=dataset_data_source,
        asset_type="custom"
    )

    # 4. UPDATE DATASET
    updated_data_source = "sensor/temperature_updated"
    updated_destinations = "topic=factory/temperature_v2 qos=Qos0 retain=Never ttl=1800"
    updated_config = '{"pollingInterval": 2000, "format": "xml"}'

    updated_dataset = run(
        f"az iot ops ns asset custom dataset update custom --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
        f"--dataset-data-source {updated_data_source} "
        f"--dataset-destinations {updated_destinations} "
        f"--dataset-custom-configuration '{updated_config}'"
    )

    assert_dataset_properties(
        updated_dataset,
        name=dataset_name,
        data_source=updated_data_source,
        asset_type="custom"
    )

    # 5. TEST DATASET REPLACE FUNCTIONALITY
    # Replace dataset with --replace flag
    replaced_data_source = "sensor/temperature_replaced"
    replaced_config = '{"pollingInterval": 3000, "format": "binary"}'

    replaced_dataset = run(
        f"az iot ops ns asset custom dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
        f"--dataset-data-source {replaced_data_source} "
        f"--dataset-custom-configuration '{replaced_config}' --replace"
    )

    assert_dataset_properties(
        replaced_dataset,
        name=dataset_name,
        data_source=replaced_data_source,
        asset_type="custom"
    )

    # 6. ADD DATASET DATAPOINTS
    # Add first datapoint
    datapoint_data_source_1 = "sensor/temperature/value"
    datapoint_config_1 = '{"unit": "celsius", "precision": 2}'

    datapoint_result_1 = run(
        f"az iot ops ns asset custom dataset point add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
        f"--datapoint {datapoint_name_1} --data-source {datapoint_data_source_1} "
        f"--custom-configuration '{datapoint_config_1}'"
    )

    assert_datapoint_properties(
        datapoint_result_1,
        name=datapoint_name_1,
        data_source=datapoint_data_source_1
    )

    # Add second datapoint
    datapoint_data_source_2 = "sensor/humidity/value"
    datapoint_config_2 = '{"unit": "percent", "precision": 1}'

    datapoint_result_2 = run(
        f"az iot ops ns asset custom dataset point add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
        f"--datapoint {datapoint_name_2} --data-source {datapoint_data_source_2} "
        f"--custom-configuration '{datapoint_config_2}'"
    )

    assert_datapoint_properties(
        datapoint_result_2,
        name=datapoint_name_2,
        data_source=datapoint_data_source_2
    )

    # 7. LIST DATASET DATAPOINTS
    datapoints_list = run(
        f"az iot ops ns asset custom dataset point list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name}"
    )

    datapoint_names = [dp["name"] for dp in datapoints_list]
    assert datapoint_name_1 in datapoint_names
    assert datapoint_name_2 in datapoint_names
    assert len(datapoints_list) >= 2

    # 8. TEST DATAPOINT REPLACE FUNCTIONALITY
    # Replace first datapoint with --replace flag
    replaced_datapoint_data_source = "sensor/temperature/replaced_value"
    replaced_datapoint_config = '{"unit": "fahrenheit", "precision": 3}'

    replaced_datapoint = run(
        f"az iot ops ns asset custom dataset point add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
        f"--datapoint {datapoint_name_1} --data-source {replaced_datapoint_data_source} "
        f"--custom-configuration '{replaced_datapoint_config}' --replace"
    )

    assert_datapoint_properties(
        replaced_datapoint,
        name=datapoint_name_1,
        data_source=replaced_datapoint_data_source
    )

    # 9. REMOVE DATASET DATAPOINT
    run(
        f"az iot ops ns asset custom dataset point remove --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
        f"--datapoint {datapoint_name_2}"
    )

    # Verify datapoint removal
    datapoints_list_after_remove = run(
        f"az iot ops ns asset custom dataset point list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name}"
    )

    remaining_datapoint_names = [dp["name"] for dp in datapoints_list_after_remove]
    assert datapoint_name_1 in remaining_datapoint_names
    assert datapoint_name_2 not in remaining_datapoint_names

    # 10. REMOVE DATASET
    run(
        f"az iot ops ns asset custom dataset remove --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name}"
    )

    # Verify dataset removal
    datasets_list_after_remove = run(
        f"az iot ops ns asset custom dataset list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group}"
    )

    remaining_dataset_names = [dataset["name"] for dataset in datasets_list_after_remove]
    assert dataset_name not in remaining_dataset_names


def test_namespace_opcua_asset_dataset_lifecycle_operations(require_init, tracked_resources: List[str]):
    """Test complete lifecycle of OPCUA asset dataset and datapoint operations."""
    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"opcua-{generate_random_string(8)}"
    asset_name = f"opcua-{generate_random_string(8, force_lower=True)}"
    dataset_name = f"dataset-{generate_random_string(6, force_lower=True)}"
    datapoint_name_1 = f"dp1-{generate_random_string(6, force_lower=True)}"
    datapoint_name_2 = f"dp2-{generate_random_string(6, force_lower=True)}"

    # Create Device
    result = run(
        f"az iot ops ns device create - {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    # Create device endpoint
    run(
        f"az iot ops ns device endpoint inbound add opcua - {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-url 'opc.tcp://192.168.1.200:4840/OPCUA/Server'"
    )

    # Create OPCUA asset
    asset_opcua = run(
        f"az iot ops ns asset opcua create - {asset_name} --instance {instance_name} "
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
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
        f"--dataset-data-source {dataset_data_source} "
        f"--dataset-destinations {dataset_destinations} "
        f"--opcua-dataset-publishing-interval 1000 "
        f"--opcua-dataset-sampling-interval 500 "
        f"--opcua-dataset-queue-size 10 "
        f"--opcua-dataset-key-frame-count 5 "
        f"--opcua-dataset-start-instance 'ns=2;i=1000'"
    )

    assert_dataset_properties(
        dataset_result,
        name=dataset_name,
        data_source=dataset_data_source,
        asset_type="opcua"
    )

    # 2. LIST DATASETS
    datasets_list = run(
        f"az iot ops ns asset opcua dataset list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group}"
    )

    dataset_names = [dataset["name"] for dataset in datasets_list]
    assert dataset_name in dataset_names
    assert len(datasets_list) >= 1

    # 3. SHOW DATASET
    shown_dataset = run(
        f"az iot ops ns asset opcua dataset show --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name}"
    )

    assert_dataset_properties(
        shown_dataset,
        name=dataset_name,
        data_source=dataset_data_source,
        asset_type="opcua"
    )

    # 4. UPDATE DATASET
    updated_data_source = "ns=2;i=1002"
    updated_destinations = "topic=factory/opcua/temperature_v2 qos=Qos0 retain=Never ttl=1800"

    updated_dataset = run(
        f"az iot ops ns asset opcua dataset update opcua --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name} "
        f"--data-source {updated_data_source} "
        f"--destinations {updated_destinations} "
        f"--opcua-dataset-publishing-interval 2000 "
        f"--opcua-dataset-sampling-interval 1000 "
        f"--opcua-dataset-queue-size 20"
    )

    assert_dataset_properties(
        updated_dataset,
        name=dataset_name,
        data_source=updated_data_source,
        asset_type="opcua"
    )

    # 5. TEST DATASET REPLACE FUNCTIONALITY
    # Replace dataset with --replace flag
    replaced_data_source = "ns=2;i=1003"

    replaced_dataset = run(
        f"az iot ops ns asset opcua dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
        f"--dataset-data-source {replaced_data_source} "
        f"--opcua-dataset-publishing-interval 3000 --replace"
    )

    assert_dataset_properties(
        replaced_dataset,
        name=dataset_name,
        data_source=replaced_data_source,
        asset_type="opcua"
    )

    # 6. ADD DATASET DATAPOINTS
    # Add first datapoint
    datapoint_data_source_1 = "ns=2;i=2001"

    datapoint_result_1 = run(
        f"az iot ops ns asset opcua dataset point add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
        f"--datapoint {datapoint_name_1} --data-source {datapoint_data_source_1} "
        f"--queue-size 5 --sampling-interval 250"
    )

    assert_datapoint_properties(
        datapoint_result_1,
        name=datapoint_name_1,
        data_source=datapoint_data_source_1
    )

    # Add second datapoint
    datapoint_data_source_2 = "ns=2;i=2002"

    datapoint_result_2 = run(
        f"az iot ops ns asset opcua dataset point add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
        f"--datapoint {datapoint_name_2} --data-source {datapoint_data_source_2} "
        f"--queue-size 3 --sampling-interval 500"
    )

    assert_datapoint_properties(
        datapoint_result_2,
        name=datapoint_name_2,
        data_source=datapoint_data_source_2
    )

    # 7. LIST DATASET DATAPOINTS
    datapoints_list = run(
        f"az iot ops ns asset opcua dataset point list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name}"
    )

    datapoint_names = [dp["name"] for dp in datapoints_list]
    assert datapoint_name_1 in datapoint_names
    assert datapoint_name_2 in datapoint_names
    assert len(datapoints_list) >= 2

    # 8. TEST DATAPOINT REPLACE FUNCTIONALITY
    # Replace first datapoint with --replace flag
    replaced_datapoint_data_source = "ns=2;i=2003"

    replaced_datapoint = run(
        f"az iot ops ns asset opcua dataset point add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
        f"--datapoint {datapoint_name_1} --data-source {replaced_datapoint_data_source} "
        f"--queue-size 15 --sampling-interval 100 --replace"
    )

    assert_datapoint_properties(
        replaced_datapoint,
        name=datapoint_name_1,
        data_source=replaced_datapoint_data_source
    )

    # 9. REMOVE DATASET DATAPOINT
    run(
        f"az iot ops ns asset opcua dataset point remove --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
        f"--datapoint {datapoint_name_2}"
    )

    # Verify datapoint removal
    datapoints_list_after_remove = run(
        f"az iot ops ns asset opcua dataset point list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name}"
    )

    remaining_datapoint_names = [dp["name"] for dp in datapoints_list_after_remove]
    assert datapoint_name_1 in remaining_datapoint_names
    assert datapoint_name_2 not in remaining_datapoint_names

    # 10. REMOVE DATASET
    run(
        f"az iot ops ns asset opcua dataset remove --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name}"
    )

    # Verify dataset removal
    datasets_list_after_remove = run(
        f"az iot ops ns asset opcua dataset list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group}"
    )

    remaining_dataset_names = [dataset["name"] for dataset in datasets_list_after_remove]
    assert dataset_name not in remaining_dataset_names


def assert_dataset_properties(result, **expected):
    """Verify dataset properties match expected values."""
    assert result["name"] == expected["name"]

    if "data_source" in expected:
        assert result["dataSource"] == expected["data_source"]


def assert_datapoint_properties(result, **expected):
    """Verify datapoint properties match expected values."""
    assert result["name"] == expected["name"]

    if "data_source" in expected:
        assert result["dataSource"] == expected["data_source"]
