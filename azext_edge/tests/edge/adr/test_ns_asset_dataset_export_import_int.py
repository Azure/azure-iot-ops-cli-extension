# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import os

import pytest
from typing import List

from ...generators import generate_random_string
from ...helpers import wait_for_expected_count
from ..._log import TestLog
from ._export_import_helpers import _ensure_device_and_endpoint, _ensure_asset_for_format_tests

pytestmark = [pytest.mark.rpsaas, pytest.mark.long_running]


@pytest.mark.parametrize("asset_type, endpoint_type, endpoint_address", [
    ("custom", "custom", "http://192.168.1.100:8000/custom/service"),
    ("opcua", "opcua", "opc.tcp://opcuaserver.local:4840"),
    ("rest", "rest", "https://api.example.com/rest"),
    ("sse", "sse", "https://events.example.com/stream"),
    ("mqtt", "mqtt", "aio-broker:18883"),
])
def test_namespace_asset_dataset_export_import(
    require_namespace_init, tracked_resources: List[str], tracked_files: List[str], tmp_path,
    shared_device: str, endpoint_cache: dict,
    asset_type: str, endpoint_type: str, endpoint_address: str
):
    """Test dataset export and import for all asset types."""
    instance_name = require_namespace_init["instanceName"]
    resource_group = require_namespace_init["resourceGroup"]
    output_dir = str(tmp_path)
    asset_name = f"{asset_type}-{generate_random_string(8, force_lower=True)}"
    dataset_name_1 = f"ds1-{generate_random_string(6, force_lower=True)}"
    dataset_name_2 = f"ds2-{generate_random_string(6, force_lower=True)}"

    with TestLog(f"test_namespace_asset_dataset_export_import[{asset_type}]", total_steps=8) as log:

        # Step 1: Ensure Device + Endpoint
        with log.step(1, "Ensure Device + Endpoint"):
            device_name, endpoint_name = _ensure_device_and_endpoint(
                log, instance_name, resource_group, asset_type, endpoint_type,
                endpoint_address, shared_device, endpoint_cache,
            )

        # Step 2: Create asset
        with log.step(2, f"Create {asset_type} Asset"):
            log.run_command(
                f"az iot ops ns asset {asset_type} create --name {asset_name} --instance {instance_name} "
                f"-g {resource_group} --device {device_name} --endpoint {endpoint_name}",
                tracked_resources=tracked_resources,
            )

        # Step 3: Add datasets
        with log.step(3, "Add Datasets"):
            dataset_destinations = "topic=factory/test qos=Qos1 retain=Keep ttl=3600"
            for ds_name in [dataset_name_1, dataset_name_2]:
                log.run_command(
                    f"az iot ops ns asset {asset_type} dataset add --asset {asset_name} "
                    f"--instance {instance_name} -g {resource_group} --name {ds_name} "
                    f"--data-source sensor/data/{ds_name} "
                    f"--destination {dataset_destinations}"
                )
            log.detail(f"datasets: {dataset_name_1}, {dataset_name_2}")
            datasets_after_add = log.run_command(
                f"az iot ops ns asset {asset_type} dataset list --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group}"
            )
            log.check("2 datasets added", len(datasets_after_add) == 2, actual=len(datasets_after_add))

        # Step 4: Export datasets as JSON
        with log.step(4, "Export Datasets (JSON)"):
            export_result_json = log.run_command(
                f"az iot ops ns asset {asset_type} dataset export --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} -f json "
                f"--output-dir {output_dir}"
            )

            log.check("'file_path' in result", "file_path" in export_result_json)
            log.check("'dataset_count' in result", "dataset_count" in export_result_json)
            log.check("dataset_count == 2", export_result_json["dataset_count"] == 2,
                      actual=export_result_json.get("dataset_count"))
            log.check("file is .json", ".json" in export_result_json["file_path"])

            exported_file = export_result_json["file_path"]
            tracked_files.append(exported_file)

            log.check("exported file exists", os.path.exists(exported_file))
            with open(exported_file, 'r', encoding='utf-8') as f:
                exported_datasets = json.load(f)

            log.check("exported 2 datasets", len(exported_datasets) == 2, actual=len(exported_datasets))
            ds_dict = {ds["name"]: ds for ds in exported_datasets}
            log.check(f"{dataset_name_1} in export", dataset_name_1 in ds_dict)
            log.check(f"{dataset_name_2} in export", dataset_name_2 in ds_dict)
            for ds_name in [dataset_name_1, dataset_name_2]:
                ds = ds_dict[ds_name]
                log.check(f"{ds_name} dataSource", ds.get("dataSource") == f"sensor/data/{ds_name}",
                          actual=ds.get("dataSource"))
                log.check(f"{ds_name} has destinations", "destinations" in ds and len(ds["destinations"]) > 0)

        # Step 5: Remove one dataset
        with log.step(5, "Remove Dataset & Verify"):
            log.run_command(
                f"az iot ops ns asset {asset_type} dataset remove --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} --name {dataset_name_1}"
            )
            datasets_after_remove = log.run_command(
                f"az iot ops ns asset {asset_type} dataset list --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group}"
            )
            log.check("1 dataset remains", len(datasets_after_remove) == 1,
                      actual=len(datasets_after_remove))

        # Step 6: Import datasets back
        with log.step(6, "Import Datasets"):
            imported_datasets = log.run_command(
                f"az iot ops ns asset {asset_type} dataset import --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} --input-file {exported_file}"
            )

            log.check("imported 2 datasets", len(imported_datasets) == 2,
                      actual=len(imported_datasets))
            imp_dict = {ds["name"]: ds for ds in imported_datasets}
            log.check(f"{dataset_name_1} restored", dataset_name_1 in imp_dict)
            log.check(f"{dataset_name_2} restored", dataset_name_2 in imp_dict)
            for ds_name in [dataset_name_1, dataset_name_2]:
                ds = imp_dict[ds_name]
                log.check(f"{ds_name} dataSource intact", ds.get("dataSource") == f"sensor/data/{ds_name}",
                          actual=ds.get("dataSource"))

        # Step 7: Verify final state
        with log.step(7, "Verify Final State"):
            final_datasets = log.run_command(
                f"az iot ops ns asset {asset_type} dataset list --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group}"
            )
            log.check("final count == 2", len(final_datasets) == 2, actual=len(final_datasets))

        # Step 8: Export as YAML
        with log.step(8, "Export Datasets (YAML)"):
            export_result_yaml = log.run_command(
                f"az iot ops ns asset {asset_type} dataset export --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} -f yaml --replace "
                f"--output-dir {output_dir}"
            )

            log.check("'file_path' in result", "file_path" in export_result_yaml)
            log.check("file is .yaml", ".yaml" in export_result_yaml["file_path"])
            tracked_files.append(export_result_yaml["file_path"])


@pytest.mark.parametrize("asset_type, endpoint_type, endpoint_address", [
    ("custom", "custom", "http://192.168.1.100:8000/custom/service"),
    ("opcua", "opcua", "opc.tcp://opcuaserver.local:4840"),
])
@pytest.mark.parametrize("export_format", ["json", "yaml", "csv"])
def test_namespace_asset_datapoint_export_import(
    require_namespace_init, tracked_resources: List[str], tracked_files: List[str], tmp_path,
    shared_device: str, endpoint_cache: dict, format_test_asset_cache: dict,
    asset_type: str, endpoint_type: str, endpoint_address: str, export_format: str
):
    """Test datapoint export and import for custom and opcua assets."""
    instance_name = require_namespace_init["instanceName"]
    resource_group = require_namespace_init["resourceGroup"]
    output_dir = str(tmp_path)
    dataset_name = f"ds-{generate_random_string(6, force_lower=True)}"
    dp_name_1 = f"dp1-{generate_random_string(6, force_lower=True)}"
    dp_name_2 = f"dp2-{generate_random_string(6, force_lower=True)}"

    step_count = 9 if export_format == "json" else 7
    with TestLog(
        f"test_namespace_asset_datapoint_export_import[{export_format}-{asset_type}]",
        total_steps=step_count,
    ) as log:

        # Step 1: Ensure Device + Endpoint
        with log.step(1, "Ensure Device + Endpoint"):
            device_name, endpoint_name = _ensure_device_and_endpoint(
                log, instance_name, resource_group, asset_type, endpoint_type,
                endpoint_address, shared_device, endpoint_cache,
            )

        # Step 2: Ensure Asset + Create Dataset
        with log.step(2, f"Ensure {asset_type} Asset + Create Dataset"):
            asset_name = _ensure_asset_for_format_tests(
                log, instance_name, resource_group, asset_type, device_name,
                endpoint_name, tracked_resources, "datapoint", format_test_asset_cache,
            )
            log.run_command(
                f"az iot ops ns asset {asset_type} dataset add --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} --name {dataset_name} "
                f"--data-source sensor/dataset1"
            )

        # Step 3: Add datapoints
        with log.step(3, "Add Datapoints"):
            log.detail(f"datapoints: {dp_name_1}, {dp_name_2}")
            dp_add_tpl = (
                f"az iot ops ns asset {asset_type} datapoint add --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} "
                f"--dataset {dataset_name} --name {{name}} --data-source sensor/{{name}}"
            )
            for dp in [dp_name_1, dp_name_2]:
                log.run_command(dp_add_tpl.format(name=dp))
            wait_for_expected_count(
                list_cmd=(
                    f"az iot ops ns asset {asset_type} datapoint list --asset {asset_name} "
                    f"--instance {instance_name} -g {resource_group} "
                    f"--dataset {dataset_name}"
                ),
                expected_count=2,
                expected_names=[dp_name_1, dp_name_2],
                reissue_cmds={
                    dp_name_1: dp_add_tpl.format(name=dp_name_1),
                    dp_name_2: dp_add_tpl.format(name=dp_name_2),
                },
                run_fn=log.run_command,
            )
            log.detail("2 datapoints added")

        # Step 4: Export datapoints
        with log.step(4, f"Export Datapoints ({export_format})"):
            export_result = log.run_command(
                f"az iot ops ns asset {asset_type} datapoint export --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
                f"-f {export_format} --output-dir {output_dir}"
            )

            log.check("'file_path' in result", "file_path" in export_result)
            log.check("'datapoint_count' in result", "datapoint_count" in export_result)
            log.check("datapoint_count == 2", export_result["datapoint_count"] == 2,
                      actual=export_result.get("datapoint_count"))
            log.check(f"file is .{export_format}", f".{export_format}" in export_result["file_path"])

            exported_file = export_result["file_path"]
            tracked_files.append(exported_file)
            log.check("exported file exists", os.path.exists(exported_file))

            if export_format == "json":
                with open(exported_file, 'r', encoding='utf-8') as f:
                    exported_dps = json.load(f)
                log.check("exported 2 datapoints", len(exported_dps) == 2, actual=len(exported_dps))
                dp_dict = {dp["name"]: dp for dp in exported_dps}
                for dp_name in [dp_name_1, dp_name_2]:
                    log.check(f"{dp_name} in export", dp_name in dp_dict)
                    log.check(f"{dp_name} dataSource",
                              dp_dict[dp_name].get("dataSource") == f"sensor/{dp_name}",
                              actual=dp_dict[dp_name].get("dataSource"))

        # Step 5: Remove all datapoints
        with log.step(5, "Remove All Datapoints"):
            dp_rm_tpl = (
                f"az iot ops ns asset {asset_type} datapoint remove --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} "
                f"--dataset {dataset_name} --name {{name}}"
            )
            for dp in [dp_name_1, dp_name_2]:
                log.run_command(dp_rm_tpl.format(name=dp))
            wait_for_expected_count(
                list_cmd=(
                    f"az iot ops ns asset {asset_type} datapoint list --asset {asset_name} "
                    f"--instance {instance_name} -g {resource_group} "
                    f"--dataset {dataset_name}"
                ),
                expected_count=0,
                expected_names=[dp_name_1, dp_name_2],
                reissue_cmds={
                    dp_name_1: dp_rm_tpl.format(name=dp_name_1),
                    dp_name_2: dp_rm_tpl.format(name=dp_name_2),
                },
                reissue_on_missing=False,
                run_fn=log.run_command,
            )
            log.detail("0 datapoints remain")

        # Step 6: Import datapoints back
        with log.step(6, "Import Datapoints"):
            imported_datapoints = log.run_command(
                f"az iot ops ns asset {asset_type} datapoint import --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
                f"--input-file {exported_file}"
            )

            log.check("imported 2 datapoints", len(imported_datapoints) == 2,
                      actual=len(imported_datapoints))
            imp_dict = {dp["name"]: dp for dp in imported_datapoints}
            for dp_name in [dp_name_1, dp_name_2]:
                log.check(f"{dp_name} restored", dp_name in imp_dict)
                log.check(f"{dp_name} dataSource intact",
                          imp_dict[dp_name].get("dataSource") == f"sensor/{dp_name}",
                          actual=imp_dict[dp_name].get("dataSource"))

        # Step 7: Verify final state
        with log.step(7, "Verify Final State"):
            final_datapoints = log.run_command(
                f"az iot ops ns asset {asset_type} datapoint list --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} --dataset {dataset_name}"
            )
            log.check("final count == 2", len(final_datapoints) == 2,
                      actual=len(final_datapoints))

        # Steps 8-9: REPLACE mode (JSON only)
        if export_format == "json":
            with log.step(8, "Prepare Modified File"):
                with open(exported_file, 'r', encoding='utf-8') as f:
                    datapoints = json.load(f)

                modified_datapoints = [datapoints[0]]
                modified_datapoints[0]["dataSource"] = modified_datapoints[0]["dataSource"] + "_modified"

                modified_file = exported_file.replace(".json", "_modified.json")
                tracked_files.append(modified_file)
                with open(modified_file, 'w', encoding='utf-8') as f:
                    json.dump(modified_datapoints, f)
                log.detail(f"modified 1 datapoint: {dp_name_1}")
                log.detail(f"file: {modified_file}")

            with log.step(9, "Import with --replace"):
                replaced_datapoints = log.run_command(
                    f"az iot ops ns asset {asset_type} datapoint import --asset {asset_name} "
                    f"--instance {instance_name} -g {resource_group} --dataset {dataset_name} "
                    f"--input-file {modified_file} --replace"
                )

                log.check("still 2 datapoints", len(replaced_datapoints) == 2,
                          actual=len(replaced_datapoints))
                dp_dict = {dp["name"]: dp for dp in replaced_datapoints}
                log.check(f"{dp_name_1} modified", "_modified" in dp_dict[dp_name_1]["dataSource"])
                log.check(f"{dp_name_2} unchanged", "_modified" not in dp_dict[dp_name_2]["dataSource"])
