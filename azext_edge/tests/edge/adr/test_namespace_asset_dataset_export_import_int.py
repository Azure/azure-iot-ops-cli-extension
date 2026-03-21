# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json

import pytest
from typing import List

from ...generators import generate_random_string
from ...helpers import wait_for_expected_count
from ..._log import TestLog
from .export_import_helpers import (
    ensure_device_and_endpoint, ensure_asset_for_format_tests,
    validate_export_result, verify_items_by_name, do_replace_import_test,
)

pytestmark = [pytest.mark.rpsaas, pytest.mark.long_running]


@pytest.mark.parametrize("asset_type, endpoint_type, endpoint_address", [
    ("custom", "custom", "http://192.168.1.100:8000/custom/service"),
    ("opcua", "opcua", "opc.tcp://opcuaserver.local:4840"),
    ("rest", "rest", "https://api.example.com/rest"),
    ("sse", "sse", "https://events.example.com/stream"),
    ("mqtt", "mqtt", "aio-broker:18883"),
])
def test_namespace_asset_dataset_export_import(
    require_namespace_init_session, tracked_resources: List[str], tracked_files: List[str], tmp_path,
    shared_device: str, endpoint_cache: dict,
    asset_type: str, endpoint_type: str, endpoint_address: str
):
    """Test dataset export and import for all asset types."""
    instance_name = require_namespace_init_session["instanceName"]
    resource_group = require_namespace_init_session["resourceGroup"]
    output_dir = str(tmp_path)
    asset_name = f"{asset_type}-{generate_random_string(8, force_lower=True)}"
    ds_name_1 = f"ds1-{generate_random_string(6, force_lower=True)}"
    ds_name_2 = f"ds2-{generate_random_string(6, force_lower=True)}"
    ds_names = [ds_name_1, ds_name_2]
    field_values = {n: f"sensor/data/{n}" for n in ds_names}

    with TestLog(f"test_namespace_asset_dataset_export_import[{asset_type}]", total_steps=8) as log:

        with log.step(1, "Ensure Device + Endpoint"):
            device_name, endpoint_name = ensure_device_and_endpoint(
                log, instance_name, resource_group, asset_type, endpoint_type,
                endpoint_address, shared_device, endpoint_cache,
            )

        with log.step(2, f"Create {asset_type} Asset"):
            log.run_command(
                f"az iot ops ns asset {asset_type} create --name {asset_name} --instance {instance_name} "
                f"-g {resource_group} --device {device_name} --endpoint {endpoint_name}",
                tracked_resources=tracked_resources,
            )

        cmd_prefix = f"az iot ops ns asset {asset_type} dataset"
        cmd_args = f"--asset {asset_name} --instance {instance_name} -g {resource_group}"

        with log.step(3, "Add Datasets"):
            destinations = "topic=factory/test qos=Qos1 retain=Keep ttl=3600"
            for name in ds_names:
                log.run_command(
                    f"{cmd_prefix} add {cmd_args} --name {name} --data-source sensor/data/{name} "
                    f"--destination {destinations}"
                )
            result = log.run_command(f"{cmd_prefix} list {cmd_args}")
            log.check("2 datasets added", len(result) == 2, actual=len(result))

        with log.step(4, "Export Datasets (JSON)"):
            export_result = log.run_command(f"{cmd_prefix} export {cmd_args} -f json --output-dir {output_dir}")
            exported_file = validate_export_result(
                log, export_result, "dataset_count", 2, "json", tracked_files,
            )
            with open(exported_file, 'r', encoding='utf-8') as f:
                exported = json.load(f)
            items = verify_items_by_name(
                log, exported, ds_names, field_name="dataSource",
                field_values=field_values, label="exported",
            )
            for name in ds_names:
                log.check(f"{name} has destinations",
                          "destinations" in items[name] and len(items[name]["destinations"]) > 0)

        with log.step(5, "Remove Dataset & Verify"):
            log.run_command(f"{cmd_prefix} remove {cmd_args} --name {ds_name_1}")
            result = log.run_command(f"{cmd_prefix} list {cmd_args}")
            log.check("1 dataset remains", len(result) == 1, actual=len(result))

        with log.step(6, "Import Datasets"):
            imported = log.run_command(f"{cmd_prefix} import {cmd_args} --input-file {exported_file}")
            verify_items_by_name(
                log, imported, ds_names, field_name="dataSource",
                field_values=field_values, label="imported",
            )

        with log.step(7, "Verify Final State"):
            final = log.run_command(f"{cmd_prefix} list {cmd_args}")
            log.check("final count == 2", len(final) == 2, actual=len(final))

        with log.step(8, "Export Datasets (YAML)"):
            yaml_result = log.run_command(
                f"{cmd_prefix} export {cmd_args} -f yaml --replace --output-dir {output_dir}"
            )
            validate_export_result(log, yaml_result, "dataset_count", 2, "yaml", tracked_files)


@pytest.mark.parametrize("asset_type, endpoint_type, endpoint_address", [
    ("custom", "custom", "http://192.168.1.100:8000/custom/service"),
    ("opcua", "opcua", "opc.tcp://opcuaserver.local:4840"),
])
@pytest.mark.parametrize("export_format", ["json", "yaml", "csv"])
def test_namespace_asset_datapoint_export_import(
    require_namespace_init_session, tracked_resources: List[str], tracked_files: List[str], tmp_path,
    shared_device: str, endpoint_cache: dict, format_test_asset_cache: dict,
    asset_type: str, endpoint_type: str, endpoint_address: str, export_format: str
):
    """Test datapoint export and import for custom and opcua assets."""
    instance_name = require_namespace_init_session["instanceName"]
    resource_group = require_namespace_init_session["resourceGroup"]
    output_dir = str(tmp_path)
    dataset_name = f"ds-{generate_random_string(6, force_lower=True)}"
    dp_name_1 = f"dp1-{generate_random_string(6, force_lower=True)}"
    dp_name_2 = f"dp2-{generate_random_string(6, force_lower=True)}"
    dp_names = [dp_name_1, dp_name_2]
    field_values = {n: f"sensor/{n}" for n in dp_names}

    step_count = 9 if export_format == "json" else 7
    with TestLog(
        f"test_namespace_asset_datapoint_export_import[{export_format}-{asset_type}]",
        total_steps=step_count,
    ) as log:

        with log.step(1, "Ensure Device + Endpoint"):
            device_name, endpoint_name = ensure_device_and_endpoint(
                log, instance_name, resource_group, asset_type, endpoint_type,
                endpoint_address, shared_device, endpoint_cache,
            )

        with log.step(2, f"Ensure {asset_type} Asset + Create Dataset"):
            asset_name = ensure_asset_for_format_tests(
                log, instance_name, resource_group, asset_type, device_name,
                endpoint_name, tracked_resources, "datapoint", format_test_asset_cache,
            )
            log.run_command(
                f"az iot ops ns asset {asset_type} dataset add --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} --name {dataset_name} "
                f"--data-source sensor/dataset1"
            )

        cmd_prefix = f"az iot ops ns asset {asset_type} datapoint"
        cmd_args = (
            f"--asset {asset_name} --instance {instance_name} -g {resource_group}"
            f" --dataset {dataset_name}"
        )

        with log.step(3, "Add Datapoints"):
            add_tpl = f"{cmd_prefix} add {cmd_args} --name {{name}} --data-source sensor/{{name}}"
            for name in dp_names:
                log.run_command(add_tpl.format(name=name))
            wait_for_expected_count(
                list_cmd=f"{cmd_prefix} list {cmd_args}",
                expected_count=2, expected_names=dp_names,
                reissue_cmds={n: add_tpl.format(name=n) for n in dp_names},
                run_fn=log.run_command,
            )

        with log.step(4, f"Export Datapoints ({export_format})"):
            export_result = log.run_command(
                f"{cmd_prefix} export {cmd_args} -f {export_format} --output-dir {output_dir}"
            )
            exported_file = validate_export_result(
                log, export_result, "datapoint_count", 2, export_format, tracked_files,
            )
            if export_format == "json":
                with open(exported_file, 'r', encoding='utf-8') as f:
                    verify_items_by_name(
                        log, json.load(f), dp_names, field_name="dataSource",
                        field_values=field_values, label="exported",
                    )

        with log.step(5, "Remove All Datapoints"):
            rm_tpl = f"{cmd_prefix} remove {cmd_args} --name {{name}}"
            for name in dp_names:
                log.run_command(rm_tpl.format(name=name))
            wait_for_expected_count(
                list_cmd=f"{cmd_prefix} list {cmd_args}",
                expected_count=0, expected_names=dp_names,
                reissue_cmds={n: rm_tpl.format(name=n) for n in dp_names},
                reissue_on_missing=False, run_fn=log.run_command,
            )

        with log.step(6, "Import Datapoints"):
            imported = log.run_command(f"{cmd_prefix} import {cmd_args} --input-file {exported_file}")
            verify_items_by_name(
                log, imported, dp_names, field_name="dataSource",
                field_values=field_values, label="imported",
            )

        with log.step(7, "Verify Final State"):
            final = log.run_command(f"{cmd_prefix} list {cmd_args}")
            log.check("final count == 2", len(final) == 2, actual=len(final))

        if export_format == "json":
            do_replace_import_test(
                log, 8, 9, exported_file, tracked_files,
                import_cmd_base=f"{cmd_prefix} import {cmd_args}",
                field_name="dataSource", item_names=dp_names,
            )
