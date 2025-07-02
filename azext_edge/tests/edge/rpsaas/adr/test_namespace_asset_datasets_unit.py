# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy
import pytest
import json
from random import randint
from typing import Dict, Optional
import responses
from azure.cli.core.azclierror import InvalidArgumentValueError
from azext_edge.edge.commands_namespaces import (
    add_namespace_custom_asset_dataset,
    add_namespace_opcua_asset_dataset,
    list_namespace_asset_datasets,
    remove_namespace_asset_dataset,
    show_namespace_asset_dataset,
    update_namespace_custom_asset_dataset,
    update_namespace_opcua_asset_dataset,
    add_namespace_custom_asset_dataset_point,
    add_namespace_opcua_asset_dataset_point,
    list_namespace_asset_dataset_points,
    remove_namespace_asset_dataset_point
)

from .namespace_helpers import check_dataset_configuration, check_destinations
from .test_namespace_assets_unit import (
    get_namespace_asset_mgmt_uri, get_namespace_asset_record, add_device_get_call
)
from ....generators import generate_random_string


def generate_dataset(dataset_name: Optional[str] = None, num_data_points: int = 0) -> dict:
    """Generates a dataset with the given name and number of data points."""
    dataset_name = dataset_name or generate_random_string()
    return {
        "name": dataset_name,
        "dataSource": f"nsu=http://microsoft.com/Opc/OpcPlc/Oven;i={randint(1, 1000)}",
        "typeRef": "datasetTypeRef",
        "datasetConfiguration": json.dumps({
            "publishingInterval": randint(1, 10),
            "samplingInterval": randint(1, 10),
            "queueSize": randint(1, 10)
        }),
        "destinations": [
            {
                "target": "Mqtt",
                "configuration": {
                    "topic": f"/contoso/{generate_random_string()}",
                    "retain": "Never",
                    "qos": "Qos1",
                    "ttl": randint(1, 60)
                }
            }
        ],
        "dataPoints": [
            {
                "name": f"{dataset_name}DataPoint{i + 1}",
                "dataSource": f"nsu=subtest;s=FastUInt{i + 1}",
                "dataPointConfiguration": json.dumps(
                    {
                        "publishingInterval": randint(1, 10),
                        "samplingInterval": randint(1, 10),
                        "queueSize": randint(1, 10)
                    }
                )
            }for i in range(num_data_points)
        ]
    }


@pytest.mark.parametrize("asset_type, command_func, config_params", [
    # Custom asset dataset with configuration
    ("custom", add_namespace_custom_asset_dataset, {
        "dataset_custom_configuration": json.dumps({
            "customSetting": "test",
            "priority": "high"
        })
    }),
    # Custom asset dataset with minimal config
    ("custom", add_namespace_custom_asset_dataset, {}),
    # OPCUA asset dataset with full parameters
    ("opcua", add_namespace_opcua_asset_dataset, {
        "opcua_dataset_publishing_interval": 1500,
        "opcua_dataset_sampling_interval": 750,
        "opcua_dataset_queue_size": 100,
        "opcua_dataset_key_frame_count": 3,
        "opcua_dataset_start_instance": "ns=1;i=2000"
    }),
    # OPCUA asset dataset with minimal config
    ("opcua", add_namespace_opcua_asset_dataset, {})
])
@pytest.mark.parametrize("destination_params", [
    {},  # No destinations
    # Single destination
    {
        "topic": "/contoso/test",
        "retain": "Keep",
        "qos": "Qos0",
        "ttl": 3600
    },
])
@pytest.mark.parametrize("previous_datasets, replace", [
    (False, True),  # No previous datasets, replace should not matter
    (False, False),
    (True, True),  # Previous datasets exist, replace should overwrite
])
def test_add_namespace_asset_dataset(
    mocked_cmd,
    mocked_responses: responses,
    asset_type: str,
    command_func,
    config_params: dict,
    destination_params: Dict[str, str],
    previous_datasets: bool,
    replace: bool,
    mocked_check_cluster_connectivity
):
    asset_name = "testAsset"
    namespace_name = "testNamespace"
    resource_group_name = "testResourceGroup"
    dataset_name = "default"  # Currently only one dataset with name "default" is supported
    data_source = f"nsu=http://microsoft.com/Opc/OpcPlc/Oven;i={randint(1, 1000)}"

    # Create the expected dataset
    expected_dataset = {
        "name": dataset_name,
        "dataSource": data_source,
        "dataPoints": []
    }

    config_params = deepcopy(config_params)
    # Add configuration based on asset type
    if config_params:
        if asset_type == "custom":
            expected_dataset["datasetConfiguration"] = config_params.get("dataset_custom_configuration")
        elif asset_type == "opcua":
            config = {}
            if "opcua_dataset_publishing_interval" in config_params:
                config["publishingInterval"] = config_params["opcua_dataset_publishing_interval"]
            if "opcua_dataset_sampling_interval" in config_params:
                config["samplingInterval"] = config_params["opcua_dataset_sampling_interval"]
            if "opcua_dataset_queue_size" in config_params:
                config["queueSize"] = config_params["opcua_dataset_queue_size"]
            if "opcua_dataset_key_frame_count" in config_params:
                config["keyFrameCount"] = config_params["opcua_dataset_key_frame_count"]
            if "opcua_dataset_start_instance" in config_params:
                config["startInstance"] = config_params["opcua_dataset_start_instance"]
            if config:
                expected_dataset["datasetConfiguration"] = json.dumps(config)

    # TODO: should be helper
    # Add destination if provided in either case
    if destination_params:
        dest = {}
        if "topic" in destination_params:
            dest = {"target": "Mqtt", "configuration": destination_params}
        expected_dataset["destinations"] = [dest]
        config_params["dataset_destinations"] = [f"{key}={value}" for key, value in dest["configuration"].items()]

    # Create mock asset record
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    # Add previous datasets if needed for the test case
    if previous_datasets:
        mocked_asset["properties"]["datasets"] = [generate_dataset(num_data_points=randint(0, 2))]

    # Mock the device endpoint check
    add_device_get_call(
        mocked_responses,
        resource_group_name=resource_group_name,
        namespace_name=namespace_name,
        device_name=mocked_asset["properties"]["deviceRef"]["deviceName"],
        endpoint_name=mocked_asset["properties"]["deviceRef"]["endpointName"],
        endpoint_type=asset_type
    )

    # Mock GET request to get the asset
    mocked_responses.add(
        responses.GET,
        get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=mocked_asset,
        status=200
    )

    # Create updated asset for mock response
    updated_asset = deepcopy(mocked_asset)

    # Since we have singular support for now
    updated_asset["properties"]["datasets"] = [expected_dataset]

    # Mock PATCH request
    mocked_responses.add(
        responses.PATCH,
        get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=updated_asset,
        status=200
    )

    # Call the function being tested
    result = command_func(
        cmd=mocked_cmd,
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        dataset_name=dataset_name,
        dataset_data_source=data_source,
        replace=replace,
        wait_sec=0,
        **config_params
    )

    # Verify the result matches the dataset we added
    assert result == expected_dataset

    # Verify API calls were made correctly
    assert len(mocked_responses.calls) == 3  # GET device + GET asset + PATCH asset
    assert mocked_responses.calls[0].request.method == "GET"  # Device GET call
    assert mocked_responses.calls[1].request.method == "GET"  # Asset GET call
    assert mocked_responses.calls[2].request.method == "PATCH"  # Asset PATCH call

    # Verify the PATCH request body contains the expected dataset structure
    patch_body = json.loads(mocked_responses.calls[2].request.body)

    # Datasets should be in the properties section
    assert "datasets" in patch_body["properties"]
    datasets = patch_body["properties"]["datasets"]

    # Count should match expected
    assert len(datasets) == len(updated_asset["properties"]["datasets"])

    # Find our dataset in the list
    added_dataset = next((d for d in datasets if d["name"] == dataset_name), None)
    assert added_dataset is not None, "Added dataset not found in the list of datasets"
    assert added_dataset["dataSource"] == data_source

    # Check configuration and destinations using helper functions
    check_dataset_configuration(added_dataset, expected_dataset)
    check_destinations(added_dataset, expected_dataset)

    # Verify all other datasets are preserved if applicable
    dataset_map = {d["name"]: d for d in updated_asset["properties"].get("datasets", [])}
    for dataset in datasets:
        assert dataset["name"] in dataset_map, f"Dataset {dataset['name']} not found in updated asset"


@pytest.mark.parametrize("asset_type, command_func", [
    ("custom", add_namespace_custom_asset_dataset),
    ("opcua", add_namespace_opcua_asset_dataset)
])
def test_add_namespace_asset_dataset_error(
    mocked_cmd,
    mocked_responses: responses,
    asset_type: str,
    command_func,
    mocked_check_cluster_connectivity
):
    """Test error cases for adding asset datasets with different asset types.

    Tests the following scenarios:
    - Adding dataset not named "default"
    - Mismatch between asset type and device endpoint type
    - Adding dataset to an asset where there is already an existing dataset (more than one dataset)
    """

    asset_name = "testAsset"
    namespace_name = "testNamespace"
    resource_group_name = "testResourceGroup"
    dataset_name = "default"
    data_source = f"nsu=http://microsoft.com/Opc/OpcPlc/Oven;i={randint(1, 1000)}"

    # Create base parameters for all test cases
    base_params = {
        "cmd": mocked_cmd,
        "resource_group_name": resource_group_name,
        "namespace_name": namespace_name,
        "asset_name": asset_name,
        "dataset_name": dataset_name,
        "dataset_data_source": data_source,
        "wait_sec": 0
    }

    # 1st non default dataset name
    with pytest.raises(InvalidArgumentValueError) as exc_info:
        command_func(
            # awkward dict update
            **{**base_params, "dataset_name": generate_random_string()}
        )
    error_msg = (
        "Currently only one dataset with the name 'default' is supported. "
        "Please use 'default' as the dataset name."
    )
    assert error_msg in str(exc_info.value)

    # 2nd mismatch between asset type and device endpoint type
    # Generate mock asset
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    mocked_responses.add(
        responses.GET,
        get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=mocked_asset,
        status=200
    )

    if asset_type != "custom":
        # use media since it is not a valid type for opcua
        add_device_get_call(
            mocked_responses,
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            device_name=mocked_asset["properties"]["deviceRef"]["deviceName"],
            endpoint_name=mocked_asset["properties"]["deviceRef"]["endpointName"],
            endpoint_type="media"
        )

        with pytest.raises(InvalidArgumentValueError) as excinfo:
            command_func(**base_params)

        assert f" is of type 'microsoft.media', but expected 'microsoft.{asset_type}'." in str(excinfo.value).lower()

    mocked_responses.reset()

    # 3rd adding dataset to an asset where there is already an existing dataset
    # replace device call with valid asset type
    add_device_get_call(
        mocked_responses,
        resource_group_name=resource_group_name,
        namespace_name=namespace_name,
        device_name=mocked_asset["properties"]["deviceRef"]["deviceName"],
        endpoint_name=mocked_asset["properties"]["deviceRef"]["endpointName"],
        endpoint_type=asset_type
    )

    mocked_asset["properties"]["datasets"] = [
        generate_dataset(dataset_name=dataset_name, num_data_points=randint(0, 2))
    ]

    mocked_responses.add(
        responses.GET,
        get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=mocked_asset,
        status=200
    )

    with pytest.raises(InvalidArgumentValueError) as excinfo:
        command_func(**base_params)

    error_msg += " If you want to update the dataset properties, please use the update command."
    assert error_msg in str(excinfo.value)


@pytest.mark.parametrize("num_datasets", [0, 1, 3])
def test_list_namespace_asset_datasets(mocked_cmd, mocked_responses: responses, num_datasets: int):
    asset_name = "testAsset"
    namespace_name = "testNamespace"
    resource_group_name = "testResourceGroup"

    # Generate expected datasets
    expected_datasets = [generate_dataset(num_data_points=randint(0, 2)) for _ in range(num_datasets)]

    # Create mock asset record
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    # Add datasets to the asset if any expected
    if expected_datasets:
        mocked_asset["properties"]["datasets"] = expected_datasets

    # Mock GET request to get the asset
    mocked_responses.add(
        responses.GET,
        get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=mocked_asset,
        status=200
    )

    # Call the function being tested
    datasets = list_namespace_asset_datasets(
        cmd=mocked_cmd,
        resource_group_name=resource_group_name,
        namespace_name=namespace_name,
        asset_name=asset_name
    )

    # Verify the result
    assert len(datasets) == num_datasets

    # Create a map of dataset name to dataset for easy lookup
    expected_dataset_map = {dataset["name"]: dataset for dataset in expected_datasets}

    # Verify each returned dataset matches the expected one
    for dataset in datasets:
        assert dataset["name"] in expected_dataset_map
        expected_dataset = expected_dataset_map[dataset["name"]]

        # Verify key properties
        assert dataset["dataSource"] == expected_dataset["dataSource"]
        assert dataset["datasetConfiguration"] == expected_dataset["datasetConfiguration"]
        assert dataset["destinations"] == expected_dataset["destinations"]

        # Check data points if any
        if "dataPoints" in expected_dataset:
            assert len(dataset.get("dataPoints", [])) == len(expected_dataset["dataPoints"])
            for dp in dataset.get("dataPoints", []):
                expected_dp = next(
                    (point for point in expected_dataset["dataPoints"] if point["name"] == dp["name"]), None
                )
                assert expected_dp is not None
                assert dp["dataSource"] == expected_dp["dataSource"]
                assert dp["dataPointConfiguration"] == expected_dp["dataPointConfiguration"]


@pytest.mark.parametrize("datasets_present", [True, False])
@pytest.mark.parametrize("dataset_deleted", [True, False])
def test_remove_namespace_asset_dataset(
    mocked_cmd,
    mocked_responses: responses,
    datasets_present: bool,
    dataset_deleted: bool,
    mocked_check_cluster_connectivity
):
    asset_name = "testAsset"
    namespace_name = "testNamespace"
    resource_group_name = "testResourceGroup"
    dataset_name = "default"  # Currently only one dataset with name "default" is supported

    # Create mock asset
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    # Add some other datasets that should remain after deletion (for future compatibility)
    # Currently only one dataset is supported, but the code should handle multiple datasets
    if datasets_present:
        mocked_asset["properties"]["datasets"] = [
            generate_dataset(f"otherDataset{i}", num_data_points=randint(0, 2))
            for i in range(2)
        ]
    expected_datasets = deepcopy(mocked_asset["properties"].get("datasets", []))

    # Add the dataset to be deleted if needed for testing
    if dataset_deleted:
        mocked_asset["properties"]["datasets"] = mocked_asset["properties"].get("datasets", [])
        mocked_asset["properties"]["datasets"].append(
            generate_dataset(dataset_name=dataset_name, num_data_points=randint(0, 2))
        )

    # Mock the GET request to get the asset
    mocked_responses.add(
        responses.GET,
        get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=mocked_asset,
        status=200
    )

    if dataset_deleted:
        # Mock the PATCH request to update the asset
        updated_asset = deepcopy(mocked_asset)
        updated_asset["properties"]["datasets"] = expected_datasets
        mocked_responses.add(
            responses.PATCH,
            get_namespace_asset_mgmt_uri(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name
            ),
            json=updated_asset,
            status=200
        )

    # Call the function being tested
    result = remove_namespace_asset_dataset(
        cmd=mocked_cmd,
        resource_group_name=resource_group_name,
        namespace_name=namespace_name,
        asset_name=asset_name,
        dataset_name=dataset_name,
        wait_sec=0
    )

    # Verify the result is the updated datasets list
    assert result == expected_datasets

    # Verify API calls were made correctly
    assert len(mocked_responses.calls) == (2 if dataset_deleted else 1)
    assert mocked_responses.calls[0].request.method == "GET"

    # If the dataset was deleted, there should be a PATCH request
    if dataset_deleted:
        assert mocked_responses.calls[1].request.method == "PATCH"

        # Verify the PATCH request body contains the expected datasets
        patch_body = json.loads(mocked_responses.calls[1].request.body)
        patch_datasets = patch_body["properties"]["datasets"]

        # The dataset that was supposed to be deleted should not be in the request
        for ds in patch_datasets:
            assert ds["name"] != dataset_name

        # All expected datasets should be present
        assert len(patch_datasets) == len(expected_datasets)
        for ds in expected_datasets:
            assert ds in patch_datasets


def test_show_namespace_asset_dataset(mocked_cmd, mocked_responses: responses):
    asset_name = "testAsset"
    namespace_name = "testNamespace"
    resource_group_name = "testResourceGroup"
    dataset_name = "default"  # Currently only one dataset with name "default" is supported

    # Generate expected dataset with random number of data points
    expected_dataset = generate_dataset(dataset_name=dataset_name, num_data_points=randint(0, 2))

    # Create mock asset record
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
    # Add the dataset to the asset
    mocked_asset["properties"]["datasets"] = [expected_dataset]

    # Mock GET request to get the asset
    mocked_responses.add(
        responses.GET,
        get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=mocked_asset,
        status=200
    )

    # Call the function being tested
    dataset = show_namespace_asset_dataset(
        cmd=mocked_cmd,
        resource_group_name=resource_group_name,
        namespace_name=namespace_name,
        asset_name=asset_name,
        dataset_name=dataset_name
    )

    # Verify the result matches the expected dataset
    assert dataset["name"] == expected_dataset["name"]
    assert dataset["dataSource"] == expected_dataset["dataSource"]
    assert dataset["datasetConfiguration"] == expected_dataset["datasetConfiguration"]
    assert dataset["destinations"] == expected_dataset["destinations"]

    # Check data points if any
    if "dataPoints" in expected_dataset:
        result_data_points = dataset.get("dataPoints", [])
        assert len(result_data_points) == len(expected_dataset["dataPoints"])
        expected_dp_map = {dp["name"]: dp for dp in expected_dataset["dataPoints"]}
        for dp in result_data_points:
            assert dp["name"] in expected_dp_map
            assert dp["dataSource"] == expected_dp_map[dp["name"]]["dataSource"]
            assert dp["dataPointConfiguration"] == expected_dp_map[dp["name"]]["dataPointConfiguration"]


@pytest.mark.parametrize("common_reqs", [
    # No specific common requirements
    {},
    # With dataset data source
    {"dataset_data_source": "nsu=http://microsoft.com/Opc/OpcPlc/Sensor;i=2000"},
    # Both data source and destinations
    {
        "dataset_destinations": "",  # TODO- change. currently will be set in the test
        "dataset_data_source": "nsu=http://microsoft.com/Opc/OpcPlc/Device;i=3000",
    }
])
@pytest.mark.parametrize("asset_type, command_func, unique_reqs", [
    # Custom asset dataset with no specific config
    ("custom", update_namespace_custom_asset_dataset, {}),
    # Custom asset dataset with custom configuration
    ("custom", update_namespace_custom_asset_dataset, {
        "dataset_custom_configuration": json.dumps({
            "customSetting": "updated",
            "priority": "critical"
        })
    }),
    # OPCUA asset dataset with basic parameters
    ("opcua", update_namespace_opcua_asset_dataset, {
        "opcua_dataset_publishing_interval": 2000,
        "opcua_dataset_queue_size": 10,
    }),
    # OPCUA asset dataset with full parameters
    ("opcua", update_namespace_opcua_asset_dataset, {
        "opcua_dataset_publishing_interval": 1500,
        "opcua_dataset_sampling_interval": 750,
        "opcua_dataset_queue_size": 100,
        "opcua_dataset_key_frame_count": 3,
        "opcua_dataset_start_instance": "ns=1;i=2000"
    })
])
def test_update_namespace_asset_dataset(
    mocked_cmd,
    mocked_responses: responses,
    asset_type: str,
    command_func,
    common_reqs: dict,
    unique_reqs: dict,
    mocked_check_cluster_connectivity
):
    asset_name = "testAsset"
    namespace_name = "testNamespace"
    resource_group_name = "testResourceGroup"
    dataset_name = "default"  # Currently only one dataset with name "default" is supported

    # Generate mock asset with the dataset already in it
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    # Add device endpoint check
    add_device_get_call(
        mocked_responses,
        resource_group_name=resource_group_name,
        namespace_name=namespace_name,
        device_name=mocked_asset["properties"]["deviceRef"]["deviceName"],
        endpoint_name=mocked_asset["properties"]["deviceRef"]["endpointName"],
        endpoint_type=asset_type
    )

    # Create the initial dataset with random data points
    initial_dataset = generate_dataset(dataset_name=dataset_name, num_data_points=randint(0, 2))

    # Add the dataset to the asset
    mocked_asset["properties"]["datasets"] = [initial_dataset]

    # Mock GET request to get the asset
    mocked_responses.add(
        responses.GET,
        get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=mocked_asset,
        status=200
    )

    # Create the expected updated dataset
    expected_dataset = deepcopy(initial_dataset)

    # Update data source if specified
    if "dataset_data_source" in common_reqs:
        expected_dataset["dataSource"] = common_reqs["dataset_data_source"]

    # Update configuration if specified
    if unique_reqs:
        if asset_type == "custom" and "dataset_custom_configuration" in unique_reqs:
            expected_dataset["datasetConfiguration"] = unique_reqs["dataset_custom_configuration"]
        elif asset_type == "opcua":
            config = json.loads(expected_dataset.get("datasetConfiguration", "{}"))

            if "opcua_dataset_publishing_interval" in unique_reqs:
                config["publishingInterval"] = unique_reqs["opcua_dataset_publishing_interval"]
            if "opcua_dataset_sampling_interval" in unique_reqs:
                config["samplingInterval"] = unique_reqs["opcua_dataset_sampling_interval"]
            if "opcua_dataset_queue_size" in unique_reqs:
                config["queueSize"] = unique_reqs["opcua_dataset_queue_size"]
            if "opcua_dataset_key_frame_count" in unique_reqs:
                config["keyFrameCount"] = unique_reqs["opcua_dataset_key_frame_count"]
            if "opcua_dataset_start_instance" in unique_reqs:
                config["startInstance"] = unique_reqs["opcua_dataset_start_instance"]

            expected_dataset["datasetConfiguration"] = json.dumps(config)

    # Update destinations if specified
    if "dataset_destinations" in common_reqs:
        destination = {
            "target": "Mqtt",
            "configuration": {
                "topic": "/contoso/datasets/updated",
                "retain": "Never",
                "qos": "Qos1",
                "ttl": randint(1, 60)  # Random TTL for testing
            }
        }
        expected_dataset["destinations"] = [destination]
        common_reqs["dataset_destinations"] = [
            f"{key}={value}" for key, value in destination["configuration"].items()
        ]

    # Create updated asset for mock response
    updated_asset = deepcopy(mocked_asset)
    updated_asset["properties"]["datasets"] = [expected_dataset]

    # Mock PATCH request
    mocked_responses.add(
        responses.PATCH,
        get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=updated_asset,
        status=200
    )

    # Call the function being tested
    result = command_func(
        cmd=mocked_cmd,
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        dataset_name=dataset_name,
        wait_sec=0,
        **common_reqs,
        **unique_reqs,
    )

    # Verify the result matches the expected dataset
    assert result == expected_dataset

    # Verify API calls were made correctly
    assert len(mocked_responses.calls) == 3
    assert mocked_responses.calls[0].request.method == "GET"  # Device endpoint check
    assert mocked_responses.calls[1].request.method == "GET"  # Asset get
    assert mocked_responses.calls[2].request.method == "PATCH"  # Update asset

    # Verify the PATCH request body contains the expected updated dataset
    patch_body = json.loads(mocked_responses.calls[2].request.body)

    # Datasets should be in the properties section
    assert "datasets" in patch_body["properties"]
    datasets = patch_body["properties"]["datasets"]

    # Verify there's only one dataset (the updated one)
    assert len(datasets) == 1

    # Check basic properties
    patch_dataset = datasets[0]
    assert patch_dataset["name"] == dataset_name

    # Check data source update if applicable
    if "dataset_data_source" in common_reqs:
        assert patch_dataset["dataSource"] == common_reqs["dataset_data_source"]
    else:
        assert patch_dataset["dataSource"] == initial_dataset["dataSource"]

    # Check configuration and destinations using helper functions
    check_dataset_configuration(patch_dataset, expected_dataset)
    check_destinations(patch_dataset, expected_dataset)

    # Check data points preservation
    assert len(patch_dataset["dataPoints"]) == len(initial_dataset["dataPoints"])
    data_points_map = {dp["name"]: dp for dp in initial_dataset["dataPoints"]}
    for dp in patch_dataset["dataPoints"]:
        assert dp["name"] in data_points_map
        assert dp["dataSource"] == data_points_map[dp["name"]]["dataSource"]
        assert dp["dataPointConfiguration"] == data_points_map[dp["name"]]["dataPointConfiguration"]


@pytest.mark.parametrize("asset_type, command_func, config_params", [
    # Custom asset dataset point
    ("custom", add_namespace_custom_asset_dataset_point, {
        "custom_configuration": json.dumps({
            "customSetting": "test",
            "priority": "high"
        })
    }),
    # Custom asset dataset point with minimal config
    ("custom", add_namespace_custom_asset_dataset_point, {}),
    # OPCUA asset dataset point with queue_size and sampling_interval
    ("opcua", add_namespace_opcua_asset_dataset_point, {
        "queue_size": 500,
        "sampling_interval": 1000
    }),
    # OPCUA asset dataset point with minimal config
    ("opcua", add_namespace_opcua_asset_dataset_point, {})
])
@pytest.mark.parametrize("has_points, replace", [
    (False, False),  # No previous points, no replace
    (True, False),   # Has previous points, no replace
    (True, True)     # Has previous points, with replace
])
def test_add_namespace_asset_dataset_point(
    mocked_cmd,
    mocked_responses: responses,
    asset_type: str,
    command_func,
    config_params: dict,
    has_points: bool,
    replace: bool,
    mocked_check_cluster_connectivity
):
    asset_name = "testAsset"
    namespace_name = "testNamespace"
    resource_group_name = "testResourceGroup"
    dataset_name = "default"  # Currently only one dataset with name "default" is supported
    datapoint_name = generate_random_string()
    data_source = f"nsu=test;s=DataPoint{generate_random_string()}"

    # Create mock asset record
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    # Create a dataset with the specified number of previous data points
    dataset = generate_dataset(
        dataset_name=dataset_name, num_data_points=randint(1, 3) if has_points else 0
    )
    mocked_asset["properties"]["datasets"] = [dataset]

    # If we're testing replace=True, add a datapoint with the same name to be replaced
    if replace:
        existing_point = {
            "name": datapoint_name,
            "dataSource": f"nsu=test;s=Existing{generate_random_string()}",
            "dataPointConfiguration": json.dumps(
                {
                    "publishingInterval": randint(1, 10),
                    "samplingInterval": randint(1, 10),
                    "queueSize": randint(1, 10)
                }
            )
        }
        mocked_asset["properties"]["datasets"][0]["dataPoints"].append(existing_point)

    # Mock the device endpoint check
    add_device_get_call(
        mocked_responses,
        resource_group_name=resource_group_name,
        namespace_name=namespace_name,
        device_name=mocked_asset["properties"]["deviceRef"]["deviceName"],
        endpoint_name=mocked_asset["properties"]["deviceRef"]["endpointName"],
        endpoint_type=asset_type
    )

    # Mock GET request to get the asset
    mocked_responses.add(
        responses.GET,
        get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=mocked_asset,
        status=200
    )

    # Create the expected data point
    expected_datapoint = {
        "name": datapoint_name,
        "dataSource": data_source
    }

    # Add configuration based on asset type
    if asset_type == "custom" and "custom_configuration" in config_params:
        expected_datapoint["dataPointConfiguration"] = config_params["custom_configuration"]
    elif asset_type == "opcua":
        config = {}
        if "queue_size" in config_params:
            config["queueSize"] = config_params["queue_size"]
        if "sampling_interval" in config_params:
            config["samplingInterval"] = config_params["sampling_interval"]
        if config:
            expected_datapoint["dataPointConfiguration"] = json.dumps(config)

    # Create the updated asset for the mock response
    updated_asset = deepcopy(mocked_asset)
    updated_dataset = updated_asset["properties"]["datasets"][0]

    # If replacing, remove the existing point with the same name
    if replace:
        updated_dataset["dataPoints"] = [
            dp for dp in updated_dataset["dataPoints"] if dp["name"] != datapoint_name
        ]

    updated_dataset["dataPoints"].append(expected_datapoint)

    # Mock PATCH request
    mocked_responses.add(
        responses.PATCH,
        get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=updated_asset,
        status=200
    )

    # Call the function being tested
    result = command_func(
        cmd=mocked_cmd,
        resource_group_name=resource_group_name,
        namespace_name=namespace_name,
        asset_name=asset_name,
        dataset_name=dataset_name,
        datapoint_name=datapoint_name,
        data_source=data_source,
        replace=replace,
        wait_sec=0,
        **config_params
    )

    # Result should be a list of datapoints from the patch response
    assert isinstance(result, list)
    assert result == updated_asset["properties"]["datasets"][0]["dataPoints"]

    # Verify API calls were made correctly
    assert len(mocked_responses.calls) == 3  # GET device + GET asset + PATCH asset
    assert mocked_responses.calls[0].request.method == "GET"  # Device GET call
    assert mocked_responses.calls[1].request.method == "GET"  # Asset GET call
    assert mocked_responses.calls[2].request.method == "PATCH"  # Asset PATCH call

    # Verify the PATCH request payload contains the expected data point
    patch_body = json.loads(mocked_responses.calls[2].request.body)
    patch_dataset = patch_body["properties"]["datasets"][0]
    assert len(patch_dataset["dataPoints"]) == len(updated_dataset["dataPoints"])

    # Check the added datapoint
    patched_point = next((p for p in patch_dataset["dataPoints"] if p["name"] == datapoint_name), None)
    assert patched_point is not None, f"Data point '{datapoint_name}' not found in PATCH request"
    assert patched_point["dataSource"] == data_source
    assert patched_point["dataPointConfiguration"] == expected_datapoint.get("dataPointConfiguration", "{}")

    # # Verify configuration
    # if asset_type == "custom" and "custom_configuration" in config_params:
    #     assert patched_point["dataPointConfiguration"] == config_params["custom_configuration"]
    # elif asset_type == "opcua" and (("queue_size" in config_params) or ("sampling_interval" in config_params)):
    #     patched_config = json.loads(patched_point["dataPointConfiguration"])
    #     if "queue_size" in config_params:
    #         assert patched_config["queueSize"] == config_params["queue_size"]
    #     if "sampling_interval" in config_params:
    #         assert patched_config["samplingInterval"] == config_params["sampling_interval"]


@pytest.mark.parametrize("num_points", [0, 1, 3])
def test_list_namespace_asset_dataset_points(
    mocked_cmd, mocked_responses: responses, num_points: int
):
    asset_name = "testAsset"
    namespace_name = "testNamespace"
    resource_group_name = "testResourceGroup"
    dataset_name = "default"  # Currently only one dataset with name "default" is supported

    # Create mock asset record
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    # Generate a dataset with the specified number of data points
    mocked_asset["properties"]["datasets"] = [generate_dataset(dataset_name=dataset_name, num_data_points=num_points)]
    expected_points = mocked_asset["properties"]["datasets"][0].get("dataPoints", [])

    # Mock GET request to get the asset
    mocked_responses.add(
        responses.GET,
        get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=mocked_asset,
        status=200
    )

    # Call the function being tested
    points = list_namespace_asset_dataset_points(
        cmd=mocked_cmd,
        resource_group_name=resource_group_name,
        namespace_name=namespace_name,
        asset_name=asset_name,
        dataset_name=dataset_name
    )

    # Verify the result
    assert len(points) == num_points

    # Create a map of point name to point for easy lookup
    expected_point_map = {point["name"]: point for point in expected_points}

    # Verify each returned point matches the expected one
    for point in points:
        assert point["name"] in expected_point_map
        expected_point = expected_point_map[point["name"]]
        assert point["dataSource"] == expected_point["dataSource"]
        assert point["dataPointConfiguration"] == expected_point["dataPointConfiguration"]


@pytest.mark.parametrize("points_present", [True, False])
@pytest.mark.parametrize("point_deleted", [True, False])
def test_remove_namespace_asset_dataset_point(
    mocked_cmd,
    mocked_responses: responses,
    points_present: bool,
    point_deleted: bool,
    mocked_check_cluster_connectivity
):
    asset_name = "testAsset"
    namespace_name = "testNamespace"
    resource_group_name = "testResourceGroup"
    dataset_name = "default"  # Currently only one dataset with name "default" is supported
    datapoint_name = generate_random_string()

    # Create mock asset with a dataset
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    # Create the dataset with or without datapoints
    dataset = generate_dataset(dataset_name=dataset_name)
    if points_present:
        # Add some other datapoints that should remain after deletion
        dataset["dataPoints"] = [
            {
                "name": f"otherDataPoint{i}",
                "dataSource": f"nsu=subtest;s=FastUInt{i}",
                "dataPointConfiguration": json.dumps(
                    {
                        "publishingInterval": randint(1, 10),
                        "samplingInterval": randint(1, 10),
                        "queueSize": randint(1, 10)
                    }
                )
            } for i in range(2)
        ]

    # Save the expected datapoints (the ones that should remain after deletion)
    expected_datapoints = deepcopy(dataset.get("dataPoints", []))

    # Add the datapoint to be deleted if needed for testing
    if point_deleted:
        dataset["dataPoints"].append({
            "name": datapoint_name,
            "dataSource": "nsu=subtest;s=ToBeDeleted",
            "dataPointConfiguration": json.dumps(
                {
                    "publishingInterval": randint(1, 10),
                    "samplingInterval": randint(1, 10),
                    "queueSize": randint(1, 10)
                }
            )
        })

    # Add the dataset to the asset
    mocked_asset["properties"]["datasets"] = [dataset]

    # Mock the GET request to get the asset
    mocked_responses.add(
        responses.GET,
        get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=mocked_asset,
        status=200
    )

    if point_deleted:
        # Mock the PATCH request to update the asset
        updated_asset = deepcopy(mocked_asset)
        updated_dataset = updated_asset["properties"]["datasets"][0]
        updated_dataset["dataPoints"] = expected_datapoints

        mocked_responses.add(
            responses.PATCH,
            get_namespace_asset_mgmt_uri(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name
            ),
            json=updated_asset,
            status=200
        )

    # Call the function being tested
    result = remove_namespace_asset_dataset_point(
        cmd=mocked_cmd,
        resource_group_name=resource_group_name,
        namespace_name=namespace_name,
        asset_name=asset_name,
        dataset_name=dataset_name,
        datapoint_name=datapoint_name,
        wait_sec=0
    )

    # Verify the result is the updated datapoints list
    assert result == expected_datapoints

    # Verify API calls were made correctly
    assert len(mocked_responses.calls) == (2 if point_deleted else 1)
    assert mocked_responses.calls[0].request.method == "GET"

    # If the point was deleted, there should be a PATCH request
    if point_deleted:
        assert mocked_responses.calls[1].request.method == "PATCH"

        # Verify the PATCH request body contains the expected datapoints
        patch_body = json.loads(mocked_responses.calls[1].request.body)
        patch_datasets = patch_body["properties"]["datasets"]
        assert len(patch_datasets) == 1

        # Find the dataset in the patch request
        patched_dataset = next((d for d in patch_datasets if d["name"] == dataset_name), None)
        assert patched_dataset is not None

        # Check that the datapoints in the patch request match the expected datapoints
        patched_datapoints = patched_dataset.get("dataPoints", [])

        # The datapoint that was supposed to be deleted should not be in the request
        for dp in patched_datapoints:
            assert dp["name"] != datapoint_name

        # All expected datapoints should be present
        assert len(patched_datapoints) == len(expected_datapoints)
        for dp in expected_datapoints:
            assert dp in patched_datapoints
