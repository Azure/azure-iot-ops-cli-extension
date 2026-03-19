# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import csv
import json
import os

import pytest
import yaml
from typing import List

from ...generators import generate_random_string
from ...helpers import wait_for_expected_count
from ..._log import TestLog

pytestmark = [pytest.mark.rpsaas, pytest.mark.long_running]


def _parse_exported_file(file_path: str, export_format: str) -> list:
    """Parse an exported file and return the list of items as dicts."""
    with open(file_path, 'r', encoding='utf-8') as f:
        if export_format == "json":
            return json.load(f)
        elif export_format == "yaml":
            return yaml.safe_load(f)
        elif export_format == "csv":
            # CSV DictReader returns flat string values only;
            # sufficient for name/dataSource checks but not nested fields.
            return list(csv.DictReader(f))
    return []


def _validate_exported_items(log, items: list, expected_names: list, export_format: str,
                             item_label: str = "item"):
    """Validate exported items have required fields and no incomplete destinations."""
    log.check(f"exported {len(expected_names)} {item_label}s",
              len(items) == len(expected_names), actual=len(items))
    # CSV uses portal-friendly column names instead of "name"
    _csv_name_keys = {"event": "EventName", "datapoint": "TagName"}
    if export_format == "csv":
        name_key = _csv_name_keys.get(item_label, "name")
    else:
        name_key = "name"
    actual_names = {item.get(name_key) for item in items}
    for name in expected_names:
        log.check(f"{name} in export", name in actual_names)
    # Destination structure checks only apply to JSON/YAML where nested dicts are preserved
    if export_format in ("json", "yaml"):
        for item in items:
            name = item.get("name", "<unknown>")
            destinations = item.get("destinations")
            if isinstance(destinations, list):
                for dest in destinations:
                    if isinstance(dest, dict) and "target" in dest:
                        log.check(
                            f"{name} destination has 'configuration'",
                            "configuration" in dest,
                            actual=list(dest.keys())
                        )


def _ensure_device_and_endpoint(
    log, instance_name, resource_group, asset_type, endpoint_type,
    endpoint_address, shared_device, endpoint_cache,
):
    """Reuse the shared device and add each endpoint type once via endpoint_cache."""
    log.detail(f"Reusing shared device={shared_device}")

    ep_key = (endpoint_type, endpoint_address)
    if ep_key in endpoint_cache:
        endpoint_name = endpoint_cache[ep_key]
        log.detail(f"Reusing endpoint={endpoint_name}")
        return shared_device, endpoint_name

    endpoint_name = f"{asset_type}-{generate_random_string(8)}"
    endpoint_cmd = (
        f"az iot ops ns device endpoint inbound add {endpoint_type} --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {shared_device} "
        f"--endpoint-address '{endpoint_address}'"
    )
    if endpoint_type == "custom":
        endpoint_cmd += " --endpoint-type custom"
    log.run_command(endpoint_cmd)

    endpoint_cache[ep_key] = endpoint_name
    return shared_device, endpoint_name


def _ensure_asset_for_format_tests(
    log, instance_name, resource_group, asset_type, device_name,
    endpoint_name, tracked_resources, test_category, format_test_asset_cache,
):
    """Create or reuse an asset shared across format variants of the same test_category+asset_type."""
    cache_key = (asset_type, test_category)
    if cache_key in format_test_asset_cache:
        asset_name = format_test_asset_cache[cache_key]
        log.detail(f"Reusing shared asset={asset_name}")
        return asset_name

    asset_name = f"{asset_type}-{generate_random_string(8, force_lower=True)}"
    log.run_command(
        f"az iot ops ns asset {asset_type} create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name}",
        tracked_resources=tracked_resources,
    )

    format_test_asset_cache[cache_key] = asset_name
    return asset_name


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


@pytest.mark.parametrize("asset_type, endpoint_type, endpoint_address", [
    ("custom", "custom", "http://192.168.1.100:8000/custom/service"),
    ("opcua", "opcua", "opc.tcp://opcuaserver.local:4840"),
    ("onvif", "onvif", "http://192.168.1.200:8080/onvif"),
    ("sse", "sse", "https://events.example.com/stream"),
])
def test_namespace_asset_event_group_export_import(
    require_namespace_init, tracked_resources: List[str], tracked_files: List[str], tmp_path,
    shared_device: str, endpoint_cache: dict,
    asset_type: str, endpoint_type: str, endpoint_address: str
):
    """Test event-group export and import for all asset types."""
    instance_name = require_namespace_init["instanceName"]
    resource_group = require_namespace_init["resourceGroup"]
    output_dir = str(tmp_path)
    asset_name = f"{asset_type}-{generate_random_string(8, force_lower=True)}"
    event_group_name_1 = f"eg1-{generate_random_string(6, force_lower=True)}"
    event_group_name_2 = f"eg2-{generate_random_string(6, force_lower=True)}"

    with TestLog(
        f"test_namespace_asset_event_group_export_import[{asset_type}]",
        total_steps=8,
    ) as log:

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

        # Step 3: Add event-groups
        with log.step(3, "Add Event Groups"):
            for eg_name in [event_group_name_1, event_group_name_2]:
                log.run_command(
                    f"az iot ops ns asset {asset_type} event-group add --asset {asset_name} "
                    f"--instance {instance_name} -g {resource_group} --name {eg_name} "
                    f"--data-source events/source/{eg_name}"
                )
            egs_after_add = log.run_command(
                f"az iot ops ns asset {asset_type} event-group list --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group}"
            )
            log.check("2 event-groups added", len(egs_after_add) == 2, actual=len(egs_after_add))

        # Step 4: Export event-groups as JSON
        with log.step(4, "Export Event Groups (JSON)"):
            export_result_json = log.run_command(
                f"az iot ops ns asset {asset_type} event-group export --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} -f json "
                f"--output-dir {output_dir}"
            )

            log.check("'file_path' in result", "file_path" in export_result_json)
            log.check("'event_group_count' in result", "event_group_count" in export_result_json)
            log.check("event_group_count == 2", export_result_json["event_group_count"] == 2,
                      actual=export_result_json.get("event_group_count"))
            log.check("file is .json", ".json" in export_result_json["file_path"])

            exported_file = export_result_json["file_path"]
            tracked_files.append(exported_file)

            log.check("exported file exists", os.path.exists(exported_file))
            with open(exported_file, 'r', encoding='utf-8') as f:
                exported_event_groups = json.load(f)
            log.check("exported 2 event-groups", len(exported_event_groups) == 2,
                      actual=len(exported_event_groups))
            eg_dict = {eg["name"]: eg for eg in exported_event_groups}
            log.check(f"{event_group_name_1} in export", event_group_name_1 in eg_dict)
            log.check(f"{event_group_name_2} in export", event_group_name_2 in eg_dict)
            for eg_name in [event_group_name_1, event_group_name_2]:
                log.check(f"{eg_name} dataSource",
                          eg_dict[eg_name].get("dataSource") == f"events/source/{eg_name}",
                          actual=eg_dict[eg_name].get("dataSource"))

        # Step 5: Remove one event-group & verify
        with log.step(5, "Remove Event Group & Verify"):
            log.run_command(
                f"az iot ops ns asset {asset_type} event-group remove --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} --name {event_group_name_1}"
            )
            event_groups_after_remove = log.run_command(
                f"az iot ops ns asset {asset_type} event-group list --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group}"
            )
            log.check("1 event-group remains", len(event_groups_after_remove) == 1,
                      actual=len(event_groups_after_remove))

        # Step 6: Import event-groups back
        with log.step(6, "Import Event Groups"):
            imported_event_groups = log.run_command(
                f"az iot ops ns asset {asset_type} event-group import --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} --input-file {exported_file}"
            )
            log.check("imported 2 event-groups", len(imported_event_groups) == 2,
                      actual=len(imported_event_groups))
            imp_dict = {eg["name"]: eg for eg in imported_event_groups}
            log.check(f"{event_group_name_1} restored", event_group_name_1 in imp_dict)
            log.check(f"{event_group_name_2} restored", event_group_name_2 in imp_dict)
            for eg_name in [event_group_name_1, event_group_name_2]:
                log.check(f"{eg_name} dataSource intact",
                          imp_dict[eg_name].get("dataSource") == f"events/source/{eg_name}",
                          actual=imp_dict[eg_name].get("dataSource"))

        # Step 7: Verify final state
        with log.step(7, "Verify Final State"):
            final_event_groups = log.run_command(
                f"az iot ops ns asset {asset_type} event-group list --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group}"
            )
            log.check("final count == 2", len(final_event_groups) == 2,
                      actual=len(final_event_groups))

        # Step 8: Export as YAML
        with log.step(8, "Export Event Groups (YAML)"):
            export_result_yaml = log.run_command(
                f"az iot ops ns asset {asset_type} event-group export --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} -f yaml --replace "
                f"--output-dir {output_dir}"
            )
            log.check("'file_path' in result", "file_path" in export_result_yaml)
            log.check("file is .yaml", ".yaml" in export_result_yaml["file_path"])
            tracked_files.append(export_result_yaml["file_path"])


@pytest.mark.parametrize("asset_type, endpoint_type, endpoint_address", [
    ("custom", "custom", "http://192.168.1.100:8000/custom/service"),
    ("opcua", "opcua", "opc.tcp://opcuaserver.local:4840"),
    ("sse", "sse", "https://events.example.com/stream"),
])
@pytest.mark.parametrize("export_format", ["json", "yaml", "csv"])
def test_namespace_asset_event_export_import(
    require_namespace_init, tracked_resources: List[str], tracked_files: List[str], tmp_path,
    shared_device: str, endpoint_cache: dict, format_test_asset_cache: dict,
    asset_type: str, endpoint_type: str, endpoint_address: str, export_format: str
):
    """Test event export and import for custom, opcua, and sse assets."""
    instance_name = require_namespace_init["instanceName"]
    resource_group = require_namespace_init["resourceGroup"]
    output_dir = str(tmp_path)
    event_group_name = f"eg-{generate_random_string(6, force_lower=True)}"
    ev_name_1 = f"ev1-{generate_random_string(6, force_lower=True)}"
    ev_name_2 = f"ev2-{generate_random_string(6, force_lower=True)}"

    step_count = 9 if export_format == "json" else 7
    with TestLog(
        f"test_namespace_asset_event_export_import[{export_format}-{asset_type}]",
        total_steps=step_count,
    ) as log:

        # Step 1: Ensure Device + Endpoint
        with log.step(1, "Ensure Device + Endpoint"):
            device_name, endpoint_name = _ensure_device_and_endpoint(
                log, instance_name, resource_group, asset_type, endpoint_type,
                endpoint_address, shared_device, endpoint_cache,
            )

        # Step 2: Ensure Asset + Create Event Group
        with log.step(2, f"Ensure {asset_type} Asset + Create Event Group"):
            asset_name = _ensure_asset_for_format_tests(
                log, instance_name, resource_group, asset_type, device_name,
                endpoint_name, tracked_resources, "event", format_test_asset_cache,
            )
            log.run_command(
                f"az iot ops ns asset {asset_type} event-group add --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} --name {event_group_name} "
                f"--data-source events/group1"
            )

        # Step 3: Add events
        with log.step(3, "Add Events"):
            log.detail(f"events: {ev_name_1}, {ev_name_2}")
            ev_add_tpl = (
                f"az iot ops ns asset {asset_type} event add --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} "
                f"--event-group {event_group_name} --name {{name}} --data-source events/{{name}}"
            )
            for ev in [ev_name_1, ev_name_2]:
                log.run_command(ev_add_tpl.format(name=ev))
            wait_for_expected_count(
                list_cmd=(
                    f"az iot ops ns asset {asset_type} event list --asset {asset_name} "
                    f"--instance {instance_name} -g {resource_group} "
                    f"--event-group {event_group_name}"
                ),
                expected_count=2,
                expected_names=[ev_name_1, ev_name_2],
                reissue_cmds={
                    ev_name_1: ev_add_tpl.format(name=ev_name_1),
                    ev_name_2: ev_add_tpl.format(name=ev_name_2),
                },
                run_fn=log.run_command,
            )
            log.detail("2 events added")

        # Step 4: Export events
        with log.step(4, f"Export Events ({export_format})"):
            export_result = log.run_command(
                f"az iot ops ns asset {asset_type} event export --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} --event-group {event_group_name} "
                f"-f {export_format} --output-dir {output_dir}"
            )

            log.check("'file_path' in result", "file_path" in export_result)
            log.check("'event_count' in result", "event_count" in export_result)
            log.check("event_count == 2", export_result["event_count"] == 2,
                      actual=export_result.get("event_count"))
            log.check(f"file is .{export_format}", f".{export_format}" in export_result["file_path"])

            exported_file = export_result["file_path"]
            tracked_files.append(exported_file)
            log.check("exported file exists", os.path.exists(exported_file))

            exported_items = _parse_exported_file(exported_file, export_format)
            _validate_exported_items(
                log, exported_items, [ev_name_1, ev_name_2],
                export_format=export_format, item_label="event"
            )

            if export_format == "json":
                ev_dict = {ev["name"]: ev for ev in exported_items}
                for ev_name in [ev_name_1, ev_name_2]:
                    log.check(f"{ev_name} dataSource",
                              ev_dict[ev_name].get("dataSource") == f"events/{ev_name}",
                              actual=ev_dict[ev_name].get("dataSource"))

        # Step 5: Remove all events
        with log.step(5, "Remove All Events"):
            ev_rm_tpl = (
                f"az iot ops ns asset {asset_type} event remove --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} "
                f"--event-group {event_group_name} --name {{name}}"
            )
            for ev in [ev_name_1, ev_name_2]:
                log.run_command(ev_rm_tpl.format(name=ev))
            wait_for_expected_count(
                list_cmd=(
                    f"az iot ops ns asset {asset_type} event list --asset {asset_name} "
                    f"--instance {instance_name} -g {resource_group} "
                    f"--event-group {event_group_name}"
                ),
                expected_count=0,
                expected_names=[ev_name_1, ev_name_2],
                reissue_cmds={
                    ev_name_1: ev_rm_tpl.format(name=ev_name_1),
                    ev_name_2: ev_rm_tpl.format(name=ev_name_2),
                },
                reissue_on_missing=False,
                run_fn=log.run_command,
            )
            log.detail("0 events remain")

        # Step 6: Import events back
        with log.step(6, "Import Events"):
            try:
                imported_events = log.run_command(
                    f"az iot ops ns asset {asset_type} event import --asset {asset_name} "
                    f"--instance {instance_name} -g {resource_group} --event-group {event_group_name} "
                    f"--input-file {exported_file}"
                )
            except Exception as import_err:
                # Log exported file contents to aid debugging
                try:
                    with open(exported_file, 'r', encoding='utf-8') as f:
                        log.detail(f"Exported file contents:\n{f.read()[:2000]}")
                except Exception:
                    pass
                raise import_err

            log.check("imported 2 events", len(imported_events) == 2,
                      actual=len(imported_events))
            imp_dict = {ev["name"]: ev for ev in imported_events}
            for ev_name in [ev_name_1, ev_name_2]:
                log.check(f"{ev_name} restored", ev_name in imp_dict)
                log.check(f"{ev_name} dataSource intact",
                          imp_dict[ev_name].get("dataSource") == f"events/{ev_name}",
                          actual=imp_dict[ev_name].get("dataSource"))

        # Step 7: Verify final state
        with log.step(7, "Verify Final State"):
            final_events = log.run_command(
                f"az iot ops ns asset {asset_type} event list --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} --event-group {event_group_name}"
            )
            log.check("final count == 2", len(final_events) == 2,
                      actual=len(final_events))

        # Steps 8-9: REPLACE mode (JSON only)
        if export_format == "json":
            with log.step(8, "Prepare Modified File"):
                with open(exported_file, 'r', encoding='utf-8') as f:
                    events = json.load(f)

                modified_events = [events[0]]
                modified_events[0]["dataSource"] = modified_events[0]["dataSource"] + "_modified"

                modified_file = exported_file.replace(".json", "_modified.json")
                tracked_files.append(modified_file)
                with open(modified_file, 'w', encoding='utf-8') as f:
                    json.dump(modified_events, f)
                log.detail(f"modified 1 event: {ev_name_1}")
                log.detail(f"file: {modified_file}")

            with log.step(9, "Import with --replace"):
                replaced_events = log.run_command(
                    f"az iot ops ns asset {asset_type} event import --asset {asset_name} "
                    f"--instance {instance_name} -g {resource_group} --event-group {event_group_name} "
                    f"--input-file {modified_file} --replace"
                )

                log.check("still 2 events", len(replaced_events) == 2,
                          actual=len(replaced_events))
                ev_dict = {ev["name"]: ev for ev in replaced_events}
                log.check(f"{ev_name_1} modified", "_modified" in ev_dict[ev_name_1]["dataSource"])
                log.check(f"{ev_name_2} unchanged", "_modified" not in ev_dict[ev_name_2]["dataSource"])


@pytest.mark.parametrize("asset_type, endpoint_type, endpoint_address", [
    ("custom", "custom", "http://192.168.1.100:8000/custom/service"),
    ("media", "media", "rtsp://192.168.1.200:554/stream"),
])
def test_namespace_asset_stream_export_import(
    require_namespace_init, tracked_resources: List[str], tracked_files: List[str], tmp_path,
    shared_device: str, endpoint_cache: dict,
    asset_type: str, endpoint_type: str, endpoint_address: str
):
    """Test stream export and import for custom and media assets."""
    instance_name = require_namespace_init["instanceName"]
    resource_group = require_namespace_init["resourceGroup"]
    output_dir = str(tmp_path)
    asset_name = f"{asset_type}-{generate_random_string(8, force_lower=True)}"
    stream_name_1 = f"str1-{generate_random_string(6, force_lower=True)}"
    stream_name_2 = f"str2-{generate_random_string(6, force_lower=True)}"

    with TestLog(
        f"test_namespace_asset_stream_export_import[{asset_type}]",
        total_steps=6,
    ) as log:

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

        # Step 3: Add streams
        with log.step(3, "Add Streams"):
            for stream_name in [stream_name_1, stream_name_2]:
                log.run_command(
                    f"az iot ops ns asset {asset_type} stream add --asset {asset_name} "
                    f"--instance {instance_name} -g {resource_group} --name {stream_name}"
                )
            streams_after_add = log.run_command(
                f"az iot ops ns asset {asset_type} stream list --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group}"
            )
            log.check("2 streams added", len(streams_after_add) == 2, actual=len(streams_after_add))

        # Step 4: Export streams as JSON
        with log.step(4, "Export Streams (JSON)"):
            export_result_json = log.run_command(
                f"az iot ops ns asset {asset_type} stream export --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} -f json "
                f"--output-dir {output_dir}"
            )

            log.check("'file_path' in result", "file_path" in export_result_json)
            log.check("'stream_count' in result", "stream_count" in export_result_json)
            log.check("stream_count == 2", export_result_json["stream_count"] == 2,
                      actual=export_result_json.get("stream_count"))
            log.check("file is .json", ".json" in export_result_json["file_path"])

            exported_file = export_result_json["file_path"]
            tracked_files.append(exported_file)

            log.check("exported file exists", os.path.exists(exported_file))
            with open(exported_file, 'r', encoding='utf-8') as f:
                exported_streams = json.load(f)
            log.check("exported 2 streams", len(exported_streams) == 2,
                      actual=len(exported_streams))
            exported_names = [s["name"] for s in exported_streams]
            log.check(f"{stream_name_1} in export", stream_name_1 in exported_names)
            log.check(f"{stream_name_2} in export", stream_name_2 in exported_names)
            for stream in exported_streams:
                log.check(f"no 'destinations' in {stream['name']}", "destinations" not in stream)

        # Step 5: Remove one stream & verify
        with log.step(5, "Remove Stream & Verify"):
            log.run_command(
                f"az iot ops ns asset {asset_type} stream remove --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} --name {stream_name_1}"
            )
            streams_after_remove = log.run_command(
                f"az iot ops ns asset {asset_type} stream list --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group}"
            )
            log.check("1 stream remains", len(streams_after_remove) == 1,
                      actual=len(streams_after_remove))

        # Step 6: Import streams back
        with log.step(6, "Import Streams"):
            imported_streams = log.run_command(
                f"az iot ops ns asset {asset_type} stream import --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} --input-file {exported_file}"
            )
            log.check("imported 2 streams", len(imported_streams) == 2,
                      actual=len(imported_streams))
            imported_names = [s["name"] for s in imported_streams]
            log.check(f"{stream_name_1} restored", stream_name_1 in imported_names)
            log.check(f"{stream_name_2} restored", stream_name_2 in imported_names)


@pytest.mark.parametrize("asset_type, endpoint_type, endpoint_address", [
    ("custom", "custom", "http://192.168.1.100:8000/custom/service"),
    ("opcua", "opcua", "opc.tcp://opcuaserver.local:4840"),
    ("onvif", "onvif", "http://192.168.1.200:8080/onvif"),
])
def test_namespace_asset_management_group_export_import(
    require_namespace_init, tracked_resources: List[str], tracked_files: List[str], tmp_path,
    shared_device: str, endpoint_cache: dict,
    asset_type: str, endpoint_type: str, endpoint_address: str
):
    """Test management group export and import for all asset types."""
    instance_name = require_namespace_init["instanceName"]
    resource_group = require_namespace_init["resourceGroup"]
    output_dir = str(tmp_path)
    asset_name = f"{asset_type}-{generate_random_string(8, force_lower=True)}"
    group_name_1 = f"grp1-{generate_random_string(6, force_lower=True)}"
    group_name_2 = f"grp2-{generate_random_string(6, force_lower=True)}"

    with TestLog(
        f"test_namespace_asset_management_group_export_import[{asset_type}]",
        total_steps=6,
    ) as log:

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

        # Step 3: Add management groups
        with log.step(3, "Add Management Groups"):
            for group_name in [group_name_1, group_name_2]:
                log.run_command(
                    f"az iot ops ns asset {asset_type} mgmt-group add --asset {asset_name} "
                    f"--instance {instance_name} -g {resource_group} --name {group_name} "
                    f"--data-source mgmt/{group_name}"
                )
            groups_after_add = log.run_command(
                f"az iot ops ns asset {asset_type} mgmt-group list --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group}"
            )
            log.check("2 mgmt-groups added", len(groups_after_add) == 2, actual=len(groups_after_add))

        # Step 4: Export management groups as JSON
        with log.step(4, "Export Management Groups (JSON)"):
            export_result_json = log.run_command(
                f"az iot ops ns asset {asset_type} mgmt-group export --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} -f json "
                f"--output-dir {output_dir}"
            )

            log.check("'file_path' in result", "file_path" in export_result_json)
            log.check("'management_group_count' in result", "management_group_count" in export_result_json)
            log.check("management_group_count == 2", export_result_json["management_group_count"] == 2,
                      actual=export_result_json.get("management_group_count"))
            log.check("file is .json", ".json" in export_result_json["file_path"])

            exported_file = export_result_json["file_path"]
            tracked_files.append(exported_file)

            log.check("exported file exists", os.path.exists(exported_file))
            with open(exported_file, 'r', encoding='utf-8') as f:
                exported_groups = json.load(f)
            log.check("exported 2 groups", len(exported_groups) == 2,
                      actual=len(exported_groups))
            grp_dict = {g["name"]: g for g in exported_groups}
            log.check(f"{group_name_1} in export", group_name_1 in grp_dict)
            log.check(f"{group_name_2} in export", group_name_2 in grp_dict)
            for grp_name in [group_name_1, group_name_2]:
                grp = grp_dict[grp_name]
                log.check(f"no 'actions' in {grp_name}", "actions" not in grp)
                log.check(f"{grp_name} dataSource",
                          grp.get("dataSource") == f"mgmt/{grp_name}",
                          actual=grp.get("dataSource"))

        # Step 5: Remove one group & verify
        with log.step(5, "Remove Management Group & Verify"):
            log.run_command(
                f"az iot ops ns asset {asset_type} mgmt-group remove --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} --name {group_name_1}"
            )
            groups_after_remove = log.run_command(
                f"az iot ops ns asset {asset_type} mgmt-group list --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group}"
            )
            log.check("1 group remains", len(groups_after_remove) == 1,
                      actual=len(groups_after_remove))

        # Step 6: Import management groups back
        with log.step(6, "Import Management Groups"):
            imported_groups = log.run_command(
                f"az iot ops ns asset {asset_type} mgmt-group import --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} --input-file {exported_file}"
            )
            log.check("imported 2 groups", len(imported_groups) == 2,
                      actual=len(imported_groups))
            imp_dict = {g["name"]: g for g in imported_groups}
            log.check(f"{group_name_1} restored", group_name_1 in imp_dict)
            log.check(f"{group_name_2} restored", group_name_2 in imp_dict)
            for grp_name in [group_name_1, group_name_2]:
                log.check(f"{grp_name} dataSource intact",
                          imp_dict[grp_name].get("dataSource") == f"mgmt/{grp_name}",
                          actual=imp_dict[grp_name].get("dataSource"))


@pytest.mark.parametrize("asset_type, endpoint_type, endpoint_address", [
    ("custom", "custom", "http://192.168.1.100:8000/custom/service"),
    ("opcua", "opcua", "opc.tcp://opcuaserver.local:4840"),
])
@pytest.mark.parametrize("export_format", ["json", "yaml", "csv"])
def test_namespace_asset_management_action_export_import(
    require_namespace_init, tracked_resources: List[str], tracked_files: List[str], tmp_path,
    shared_device: str, endpoint_cache: dict, format_test_asset_cache: dict,
    asset_type: str, endpoint_type: str, endpoint_address: str, export_format: str
):
    """Test management action export and import for custom and opcua assets."""
    instance_name = require_namespace_init["instanceName"]
    resource_group = require_namespace_init["resourceGroup"]
    output_dir = str(tmp_path)
    group_name = f"grp-{generate_random_string(6, force_lower=True)}"
    action_name_1 = f"act1-{generate_random_string(6, force_lower=True)}"
    action_name_2 = f"act2-{generate_random_string(6, force_lower=True)}"

    step_count = 9 if export_format == "json" else 7
    with TestLog(
        f"test_namespace_asset_management_action_export_import[{export_format}-{asset_type}]",
        total_steps=step_count,
    ) as log:

        # Step 1: Ensure Device + Endpoint
        with log.step(1, "Ensure Device + Endpoint"):
            device_name, endpoint_name = _ensure_device_and_endpoint(
                log, instance_name, resource_group, asset_type, endpoint_type,
                endpoint_address, shared_device, endpoint_cache,
            )

        # Step 2: Ensure Asset + Create Management Group
        with log.step(2, f"Ensure {asset_type} Asset + Create Management Group"):
            asset_name = _ensure_asset_for_format_tests(
                log, instance_name, resource_group, asset_type, device_name,
                endpoint_name, tracked_resources, "mgmt_action", format_test_asset_cache,
            )
            log.run_command(
                f"az iot ops ns asset {asset_type} mgmt-group add --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} --name {group_name} "
                f"--data-source mgmt/{group_name}"
            )

        # Step 3: Add actions
        with log.step(3, "Add Management Actions"):
            log.detail(f"actions: {action_name_1}, {action_name_2}")
            act_add_tpl = (
                f"az iot ops ns asset {asset_type} mgmt-action add --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} "
                f"--group {group_name} --name {{name}} --target-uri 'ns=2;s={{name}}'"
            )
            for act in [action_name_1, action_name_2]:
                log.run_command(act_add_tpl.format(name=act))
            wait_for_expected_count(
                list_cmd=(
                    f"az iot ops ns asset {asset_type} mgmt-action list --asset {asset_name} "
                    f"--instance {instance_name} -g {resource_group} "
                    f"--group {group_name}"
                ),
                expected_count=2,
                expected_names=[action_name_1, action_name_2],
                reissue_cmds={
                    action_name_1: act_add_tpl.format(name=action_name_1),
                    action_name_2: act_add_tpl.format(name=action_name_2),
                },
                run_fn=log.run_command,
            )
            log.detail("2 actions added")

        # Step 4: Export actions
        with log.step(4, f"Export Management Actions ({export_format})"):
            export_result = log.run_command(
                f"az iot ops ns asset {asset_type} mgmt-action export --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} --group {group_name} "
                f"-f {export_format} --output-dir {output_dir}"
            )

            log.check("'file_path' in result", "file_path" in export_result)
            log.check("'action_count' in result", "action_count" in export_result)
            log.check("action_count == 2", export_result["action_count"] == 2,
                      actual=export_result.get("action_count"))
            log.check(f"file is .{export_format}", f".{export_format}" in export_result["file_path"])

            exported_file = export_result["file_path"]
            tracked_files.append(exported_file)
            log.check("exported file exists", os.path.exists(exported_file))

            if export_format == "json":
                with open(exported_file, 'r', encoding='utf-8') as f:
                    exported_acts = json.load(f)
                log.check("exported 2 actions", len(exported_acts) == 2, actual=len(exported_acts))
                act_dict = {a["name"]: a for a in exported_acts}
                for act_name in [action_name_1, action_name_2]:
                    log.check(f"{act_name} in export", act_name in act_dict)
                    log.check(f"{act_name} targetUri",
                              act_dict[act_name].get("targetUri") == f"ns=2;s={act_name}",
                              actual=act_dict[act_name].get("targetUri"))

        # Step 5: Remove all actions
        with log.step(5, "Remove All Actions"):
            act_rm_tpl = (
                f"az iot ops ns asset {asset_type} mgmt-action remove --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} "
                f"--group {group_name} --name {{name}}"
            )
            for act in [action_name_1, action_name_2]:
                log.run_command(act_rm_tpl.format(name=act))
            wait_for_expected_count(
                list_cmd=(
                    f"az iot ops ns asset {asset_type} mgmt-action list --asset {asset_name} "
                    f"--instance {instance_name} -g {resource_group} "
                    f"--group {group_name}"
                ),
                expected_count=0,
                expected_names=[action_name_1, action_name_2],
                reissue_cmds={
                    action_name_1: act_rm_tpl.format(name=action_name_1),
                    action_name_2: act_rm_tpl.format(name=action_name_2),
                },
                reissue_on_missing=False,
                run_fn=log.run_command,
            )
            log.detail("0 actions remain")

        # Step 6: Import actions back
        with log.step(6, "Import Management Actions"):
            imported_actions = log.run_command(
                f"az iot ops ns asset {asset_type} mgmt-action import --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} --group {group_name} "
                f"--input-file {exported_file}"
            )

            log.check("imported 2 actions", len(imported_actions) == 2,
                      actual=len(imported_actions))
            imp_dict = {a["name"]: a for a in imported_actions}
            for act_name in [action_name_1, action_name_2]:
                log.check(f"{act_name} restored", act_name in imp_dict)
                log.check(f"{act_name} targetUri intact",
                          imp_dict[act_name].get("targetUri") == f"ns=2;s={act_name}",
                          actual=imp_dict[act_name].get("targetUri"))

        # Step 7: Verify final state
        with log.step(7, "Verify Final State"):
            final_actions = log.run_command(
                f"az iot ops ns asset {asset_type} mgmt-action list --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} --group {group_name}"
            )
            log.check("final count == 2", len(final_actions) == 2,
                      actual=len(final_actions))

        # Steps 8-9: REPLACE mode (JSON only)
        if export_format == "json":
            with log.step(8, "Prepare Modified File"):
                with open(exported_file, 'r', encoding='utf-8') as f:
                    actions = json.load(f)

                modified_actions = [actions[0]]
                modified_actions[0]["targetUri"] = modified_actions[0]["targetUri"] + "_modified"

                modified_file = exported_file.replace(".json", "_modified.json")
                tracked_files.append(modified_file)
                with open(modified_file, 'w', encoding='utf-8') as f:
                    json.dump(modified_actions, f)
                log.detail(f"modified 1 action: {action_name_1}")
                log.detail(f"file: {modified_file}")

            with log.step(9, "Import with --replace"):
                replaced_actions = log.run_command(
                    f"az iot ops ns asset {asset_type} mgmt-action import --asset {asset_name} "
                    f"--instance {instance_name} -g {resource_group} --group {group_name} "
                    f"--input-file {modified_file} --replace"
                )

                log.check("still 2 actions", len(replaced_actions) == 2,
                          actual=len(replaced_actions))
                action_dict = {a["name"]: a for a in replaced_actions}
                log.check(f"{action_name_1} modified", "_modified" in action_dict[action_name_1]["targetUri"])
                log.check(f"{action_name_2} unchanged", "_modified" not in action_dict[action_name_2]["targetUri"])
