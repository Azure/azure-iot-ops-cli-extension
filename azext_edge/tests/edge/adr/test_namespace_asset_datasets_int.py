# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from typing import List

from ...generators import generate_random_string
from ...helpers import run, wait_for_expected_count
from .namespace_helpers import create_config_file, assert_point_properties, assert_dataset_properties


pytestmark = [pytest.mark.rpsaas, pytest.mark.long_running]


def test_namespace_custom_asset_dataset_lifecycle_operations(
    asset_factory, tracked_files: List[str]
):
    """Test complete lifecycle of custom asset dataset and datapoint operations."""
    # Setup from shared fixtures
    info = asset_factory("custom")
    asset_name = info["name"]
    instance_name = info["instanceName"]
    resource_group = info["resourceGroup"]
    dataset_name_1 = f"dataset{generate_random_string(6, force_lower=True)}"
    dataset_name_2 = f"dataset2{generate_random_string(6, force_lower=True)}"
    datapoint_name_1 = f"dp1-{generate_random_string(6, force_lower=True)}"
    datapoint_name_2 = f"dp2-{generate_random_string(6, force_lower=True)}"

    # 1. CREATE DATASET
    dataset_destinations = "topic=factory/temperature qos=Qos1 retain=Keep ttl=3600"
    custom_config_path, custom_config = create_config_file(tracked_files)

    # Add custom asset dataset
    dataset_result = run(
        f"az iot ops ns asset custom dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1} "
        f"--destination {dataset_destinations} "
        f"--config {custom_config_path}"
    )

    assert_dataset_properties(
        dataset_result,
        name=dataset_name_1,
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
    datapoints_list = wait_for_expected_count(
        list_cmd=(
            f"az iot ops ns asset custom datapoint list --asset {asset_name} "
            f"--instance {instance_name} -g {resource_group} --dataset {dataset_name_1}"
        ),
        expected_count=2,
        expected_names=[datapoint_name_1, datapoint_name_2],
        reissue_cmds={
            datapoint_name_1: (
                f"az iot ops ns asset custom datapoint add --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} --dataset {dataset_name_1} "
                f"--name {datapoint_name_1} --data-source {datapoint_data_source_1}"
            ),
            datapoint_name_2: (
                f"az iot ops ns asset custom datapoint add --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} --dataset {dataset_name_1} "
                f"--name {datapoint_name_2} --data-source {datapoint_data_source_2}"
            ),
        },
    )

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


def test_namespace_opcua_asset_dataset_lifecycle_operations(asset_factory):
    """Test complete lifecycle of OPCUA asset dataset and datapoint operations."""
    # Setup from shared fixtures
    info = asset_factory("opcua")
    asset_name = info["name"]
    instance_name = info["instanceName"]
    resource_group = info["resourceGroup"]
    dataset_name_1 = f"dataset{generate_random_string(6, force_lower=True)}"
    dataset_name_2 = f"dataset2{generate_random_string(6, force_lower=True)}"
    datapoint_name_1 = f"dp1-{generate_random_string(6, force_lower=True)}"
    datapoint_name_2 = f"dp2-{generate_random_string(6, force_lower=True)}"

    # 1. CREATE DATASET
    dataset_destinations = "topic=factory/opcua/temperature qos=Qos1 retain=Keep ttl=3600"

    # Add OPCUA asset dataset with specific OPCUA parameters
    start_instance = "ns=2;i=1001"
    dataset_result = run(
        f"az iot ops ns asset opcua dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1} "
        f"--destination {dataset_destinations} "
        f"--publish-int 1000 "
        f"--sampling-int 500 "
        f"--queue-size 10 "
        f"--key-frame-count 5 "
        f"--start-inst \"{start_instance}\" "
    )

    assert_dataset_properties(
        dataset_result,
        name=dataset_name_1,
        asset_type="opcua",
        publishing_interval=1000,
        opcua_configuration={"startInstance": start_instance},
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
    datapoints_list = wait_for_expected_count(
        list_cmd=(
            f"az iot ops ns asset opcua datapoint list --asset {asset_name} "
            f"--instance {instance_name} -g {resource_group} --dataset {dataset_name_1}"
        ),
        expected_count=2,
        expected_names=[datapoint_name_1, datapoint_name_2],
        reissue_cmds={
            datapoint_name_1: (
                f'az iot ops ns asset opcua datapoint add --asset {asset_name} '
                f'--instance {instance_name} -g {resource_group} --dataset {dataset_name_1} '
                f'--name {datapoint_name_1} --data-source "{datapoint_data_source_1}"'
            ),
            datapoint_name_2: (
                f'az iot ops ns asset opcua datapoint add --asset {asset_name} '
                f'--instance {instance_name} -g {resource_group} --dataset {dataset_name_1} '
                f'--name {datapoint_name_2} --data-source "{datapoint_data_source_2}"'
            ),
        },
    )

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


def test_namespace_rest_asset_dataset_lifecycle_operations(asset_factory):
    """Test complete lifecycle of REST asset dataset operations."""
    # Setup from shared fixtures
    info = asset_factory("rest")
    asset_name = info["name"]
    instance_name = info["instanceName"]
    resource_group = info["resourceGroup"]
    dataset_name_1 = f"dataset{generate_random_string(6, force_lower=True)}"

    # 1. CREATE DATASET
    dataset_destinations = "topic=factory/rest/temperature qos=Qos1 retain=Keep ttl=3600"

    # Add REST asset dataset with specific REST parameters
    dataset_result = run(
        f"az iot ops ns asset rest dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1} "
        f"--destination {dataset_destinations} "
        f"--sampling-int 5000"
    )

    assert_dataset_properties(
        dataset_result,
        name=dataset_name_1,
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


def test_namespace_sse_asset_dataset_lifecycle_operations(asset_factory):
    """Test complete lifecycle of SSE asset dataset operations."""
    # Setup from shared fixtures
    info = asset_factory("sse")
    asset_name = info["name"]
    instance_name = info["instanceName"]
    resource_group = info["resourceGroup"]
    dataset_name_1 = f"dataset{generate_random_string(6, force_lower=True)}"

    # 1. CREATE DATASET
    dataset_destinations = "topic=factory/sse/temperature qos=Qos1 retain=Keep ttl=3600"

    # Add SSE asset dataset (NOTE: No sampling interval since SSE is event-driven)
    dataset_result = run(
        f"az iot ops ns asset sse dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1} "
        f"--destination {dataset_destinations}"
    )

    assert_dataset_properties(
        dataset_result,
        name=dataset_name_1,
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


def test_namespace_mqtt_asset_dataset_lifecycle_operations(asset_factory):
    """Test complete lifecycle of MQTT asset dataset operations."""
    # Setup from shared fixtures
    info = asset_factory("mqtt")
    asset_name = info["name"]
    instance_name = info["instanceName"]
    resource_group = info["resourceGroup"]
    dataset_name_1 = f"dataset{generate_random_string(6, force_lower=True)}"

    # 1. CREATE DATASET
    dataset_destinations = "topic=telemetry/mqtt/temperature qos=Qos1 retain=Keep ttl=3600"

    # Add MQTT asset dataset (NOTE: MQTT datasets support BrokerStateStore and MQTT destinations only, no events)
    dataset_result = run(
        f"az iot ops ns asset mqtt dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1} "
        f"--destination {dataset_destinations}"
    )

    assert_dataset_properties(
        dataset_result,
        name=dataset_name_1,
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
