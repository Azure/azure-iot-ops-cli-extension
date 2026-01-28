# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from typing import List

from ...generators import generate_random_string
from ...helpers import run

pytestmark = [pytest.mark.rpsaas, pytest.mark.long_running]


# Export/Import Integration Tests
@pytest.mark.parametrize("asset_type, endpoint_type, endpoint_address", [
    ("custom", "custom", "http://192.168.1.100:8000/custom/service"),
    ("opcua", "opcua", "opc.tcp://opcuaserver.local:4840"),
    ("rest", "rest", "https://api.example.com/rest"),
    ("sse", "sse", "https://events.example.com/stream"),
    ("mqtt", "mqtt", "aio-broker:18883"),
])
def test_namespace_asset_dataset_export_import(
    require_init, tracked_resources: List[str], tracked_files: List[str], asset_type: str,
    endpoint_type: str, endpoint_address: str
):
    """Test dataset export and import for all asset types."""
    import os
    import json

    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"{asset_type}-{generate_random_string(8)}"
    asset_name = f"{asset_type}-{generate_random_string(8, force_lower=True)}"
    dataset_name_1 = f"ds1-{generate_random_string(6, force_lower=True)}"
    dataset_name_2 = f"ds2-{generate_random_string(6, force_lower=True)}"

    # Create Device
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    # Create device endpoint
    endpoint_cmd = (
        f"az iot ops ns device endpoint inbound add {endpoint_type} --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address '{endpoint_address}'"
    )
    if endpoint_type == "custom":
        endpoint_cmd += " --endpoint-type custom"
    run(endpoint_cmd)

    # Create asset
    asset_result = run(
        f"az iot ops ns asset {asset_type} create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name}"
    )
    tracked_resources.append(asset_result["id"])

    # Add datasets
    dataset_destinations = "topic=factory/test qos=Qos1 retain=Keep ttl=3600"

    for ds_name in [dataset_name_1, dataset_name_2]:
        run(
            f"az iot ops ns asset {asset_type} dataset add --asset {asset_name} "
            f"--instance {instance_name} -g {resource_group} --name {ds_name} "
            f"--data-source sensor/data/{ds_name} "
            f"--destination {dataset_destinations}"
        )

    # EXPORT datasets as JSON
    export_result_json = run(
        f"az iot ops ns asset {asset_type} dataset export --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --extension json"
    )

    assert "file_path" in export_result_json
    assert "dataset_count" in export_result_json
    assert export_result_json["dataset_count"] == 2
    assert ".json" in export_result_json["file_path"]

    exported_file = export_result_json["file_path"]
    tracked_files.append(exported_file)

    # Verify exported file content
    assert os.path.exists(exported_file)
    with open(exported_file, 'r') as f:
        exported_datasets = json.load(f)

    assert len(exported_datasets) == 2
    exported_names = [ds["name"] for ds in exported_datasets]
    assert dataset_name_1 in exported_names
    assert dataset_name_2 in exported_names

    # Remove one dataset
    run(
        f"az iot ops ns asset {asset_type} dataset remove --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name_1}"
    )

    # Verify only one dataset remains
    datasets_after_remove = run(
        f"az iot ops ns asset {asset_type} dataset list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group}"
    )
    assert len(datasets_after_remove) == 1

    # IMPORT datasets back (should restore both)
    imported_datasets = run(
        f"az iot ops ns asset {asset_type} dataset import --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --file-path {exported_file}"
    )

    assert len(imported_datasets) == 2
    imported_names = [ds["name"] for ds in imported_datasets]
    assert dataset_name_1 in imported_names
    assert dataset_name_2 in imported_names

    # Verify datasets were imported correctly
    final_datasets = run(
        f"az iot ops ns asset {asset_type} dataset list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group}"
    )
    assert len(final_datasets) == 2

    # EXPORT as YAML
    export_result_yaml = run(
        f"az iot ops ns asset {asset_type} dataset export --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --extension yaml --replace"
    )

    assert "file_path" in export_result_yaml
    assert ".yaml" in export_result_yaml["file_path"]
    tracked_files.append(export_result_yaml["file_path"])


@pytest.mark.parametrize("asset_type, endpoint_type, endpoint_address", [
    ("custom", "custom", "http://192.168.1.100:8000/custom/service"),
    ("opcua", "opcua", "opc.tcp://opcuaserver.local:4840"),
])
@pytest.mark.parametrize("export_format", ["json", "yaml", "csv"])
def test_namespace_asset_datapoint_export_import(
    require_init, tracked_resources: List[str], tracked_files: List[str],
    asset_type: str, endpoint_type: str, endpoint_address: str, export_format: str
):
    """Test datapoint export and import for custom and opcua assets."""
    import os
    import json

    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"{asset_type}-{generate_random_string(8)}"
    asset_name = f"{asset_type}-{generate_random_string(8, force_lower=True)}"
    dataset_name = f"ds-{generate_random_string(6, force_lower=True)}"
    dp_name_1 = f"dp1-{generate_random_string(6, force_lower=True)}"
    dp_name_2 = f"dp2-{generate_random_string(6, force_lower=True)}"
    dp_name_3 = f"dp3-{generate_random_string(6, force_lower=True)}"

    # Create Device
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    # Create device endpoint
    endpoint_cmd = (
        f"az iot ops ns device endpoint inbound add {endpoint_type} --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address '{endpoint_address}'"
    )
    if endpoint_type == "custom":
        endpoint_cmd += " --endpoint-type custom"
    run(endpoint_cmd)

    # Create asset
    asset_result = run(
        f"az iot ops ns asset {asset_type} create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name}"
    )
    tracked_resources.append(asset_result["id"])

    # Add dataset
    run(
        f"az iot ops ns asset {asset_type} dataset add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {dataset_name} "
        f"--data-source sensor/dataset1"
    )

    # Add datapoints
    for dp_name in [dp_name_1, dp_name_2, dp_name_3]:
        run(
            f"az iot ops ns asset {asset_type} datapoint add --asset {asset_name} "
            f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
            f"--name {dp_name} --data-source sensor/{dp_name}"
        )

    # EXPORT datapoints
    export_result = run(
        f"az iot ops ns asset {asset_type} datapoint export --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
        f"--extension {export_format}"
    )

    assert "file_path" in export_result
    assert "datapoint_count" in export_result
    assert export_result["datapoint_count"] == 3
    assert f".{export_format}" in export_result["file_path"]

    exported_file = export_result["file_path"]
    tracked_files.append(exported_file)

    # Verify exported file exists
    assert os.path.exists(exported_file)

    # Remove all datapoints
    for dp_name in [dp_name_1, dp_name_2, dp_name_3]:
        run(
            f"az iot ops ns asset {asset_type} datapoint remove --asset {asset_name} "
            f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
            f"--name {dp_name}"
        )

    # Verify no datapoints remain
    datapoints_after_remove = run(
        f"az iot ops ns asset {asset_type} datapoint list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name}"
    )
    assert len(datapoints_after_remove) == 0

    # IMPORT datapoints back
    imported_datapoints = run(
        f"az iot ops ns asset {asset_type} datapoint import --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
        f"--file-path {exported_file}"
    )

    assert len(imported_datapoints) == 3
    imported_names = [dp["name"] for dp in imported_datapoints]
    assert dp_name_1 in imported_names
    assert dp_name_2 in imported_names
    assert dp_name_3 in imported_names

    # Verify datapoints were imported correctly
    final_datapoints = run(
        f"az iot ops ns asset {asset_type} datapoint list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --dataset {dataset_name}"
    )
    assert len(final_datapoints) == 3

    # Test REPLACE mode
    # replace=True means: merge with overwrite on collision (overwrites matching names from file)
    if export_format == "json":
        with open(exported_file, 'r') as f:
            datapoints = json.load(f)

        # Modify first 2 datapoints' data sources
        modified_datapoints = datapoints[:2]
        for dp in modified_datapoints:
            dp["dataSource"] = dp["dataSource"] + "_modified"

        modified_file = exported_file.replace(".json", "_modified.json")
        tracked_files.append(modified_file)
        with open(modified_file, 'w') as f:
            json.dump(modified_datapoints, f)

        # Import with replace - should overwrite the 2 matching datapoints and keep the 3rd
        replaced_datapoints = run(
            f"az iot ops ns asset {asset_type} datapoint import --asset {asset_name} "
            f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
            f"--file-path {modified_file} --replace"
        )

        # Should still have 3 datapoints (2 modified from file + 1 original untouched)
        assert len(replaced_datapoints) == 3

        # Verify the first 2 were modified, 3rd is unchanged
        dp_dict = {dp["name"]: dp for dp in replaced_datapoints}
        assert "_modified" in dp_dict[dp_name_1]["dataSource"]
        assert "_modified" in dp_dict[dp_name_2]["dataSource"]
        assert "_modified" not in dp_dict[dp_name_3]["dataSource"]
