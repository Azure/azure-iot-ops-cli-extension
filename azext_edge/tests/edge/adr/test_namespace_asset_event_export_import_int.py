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
    parse_exported_file, validate_exported_items,
    ensure_device_and_endpoint, ensure_asset_for_format_tests,
    validate_export_result, verify_items_by_name, do_replace_import_test,
)

pytestmark = [pytest.mark.rpsaas, pytest.mark.long_running]


@pytest.mark.parametrize("asset_type, endpoint_type, endpoint_address", [
    ("custom", "custom", "http://192.168.1.100:8000/custom/service"),
    ("opcua", "opcua", "opc.tcp://opcuaserver.local:4840"),
    ("onvif", "onvif", "http://192.168.1.200:8080/onvif"),
    ("sse", "sse", "https://events.example.com/stream"),
])
def test_namespace_asset_event_group_export_import(
    require_namespace_init_session, tracked_resources: List[str], tracked_files: List[str], tmp_path,
    shared_device: str, endpoint_cache: dict,
    asset_type: str, endpoint_type: str, endpoint_address: str
):
    """Test event-group export and import for all asset types."""
    instance_name = require_namespace_init_session["instanceName"]
    resource_group = require_namespace_init_session["resourceGroup"]
    output_dir = str(tmp_path)
    asset_name = f"{asset_type}-{generate_random_string(8, force_lower=True)}"
    eg_name_1 = f"eg1-{generate_random_string(6, force_lower=True)}"
    eg_name_2 = f"eg2-{generate_random_string(6, force_lower=True)}"
    eg_names = [eg_name_1, eg_name_2]
    field_values = {n: f"events/source/{n}" for n in eg_names}

    with TestLog(
        f"test_namespace_asset_event_group_export_import[{asset_type}]", total_steps=8,
    ) as log:

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

        cmd_prefix = f"az iot ops ns asset {asset_type} event-group"
        cmd_args = f"--asset {asset_name} --instance {instance_name} -g {resource_group}"

        with log.step(3, "Add Event Groups"):
            for name in eg_names:
                log.run_command(
                    f"{cmd_prefix} add {cmd_args} --name {name} --data-source events/source/{name}"
                )
            result = log.run_command(f"{cmd_prefix} list {cmd_args}")
            log.check("2 event-groups added", len(result) == 2, actual=len(result))

        with log.step(4, "Export Event Groups (JSON)"):
            export_result = log.run_command(f"{cmd_prefix} export {cmd_args} -f json --output-dir {output_dir}")
            exported_file = validate_export_result(
                log, export_result, "event_group_count", 2, "json", tracked_files,
            )
            with open(exported_file, 'r', encoding='utf-8') as f:
                verify_items_by_name(
                    log, json.load(f), eg_names, field_name="dataSource",
                    field_values=field_values, label="exported",
                )

        with log.step(5, "Remove Event Group & Verify"):
            log.run_command(f"{cmd_prefix} remove {cmd_args} --name {eg_name_1}")
            result = log.run_command(f"{cmd_prefix} list {cmd_args}")
            log.check("1 event-group remains", len(result) == 1, actual=len(result))

        with log.step(6, "Import Event Groups"):
            imported = log.run_command(f"{cmd_prefix} import {cmd_args} --input-file {exported_file}")
            verify_items_by_name(
                log, imported, eg_names, field_name="dataSource",
                field_values=field_values, label="imported",
            )

        with log.step(7, "Verify Final State"):
            final = log.run_command(f"{cmd_prefix} list {cmd_args}")
            log.check("final count == 2", len(final) == 2, actual=len(final))

        with log.step(8, "Export Event Groups (YAML)"):
            yaml_result = log.run_command(
                f"{cmd_prefix} export {cmd_args} -f yaml --replace --output-dir {output_dir}"
            )
            validate_export_result(log, yaml_result, "event_group_count", 2, "yaml", tracked_files)


@pytest.mark.parametrize("asset_type, endpoint_type, endpoint_address", [
    ("custom", "custom", "http://192.168.1.100:8000/custom/service"),
    ("opcua", "opcua", "opc.tcp://opcuaserver.local:4840"),
    ("sse", "sse", "https://events.example.com/stream"),
])
@pytest.mark.parametrize("export_format", ["json", "yaml", "csv"])
def test_namespace_asset_event_export_import(
    require_namespace_init_session, tracked_resources: List[str], tracked_files: List[str], tmp_path,
    shared_device: str, endpoint_cache: dict, format_test_asset_cache: dict,
    asset_type: str, endpoint_type: str, endpoint_address: str, export_format: str
):
    """Test event export and import for custom, opcua, and sse assets."""
    instance_name = require_namespace_init_session["instanceName"]
    resource_group = require_namespace_init_session["resourceGroup"]
    output_dir = str(tmp_path)
    event_group_name = f"eg-{generate_random_string(6, force_lower=True)}"
    ev_name_1 = f"ev1-{generate_random_string(6, force_lower=True)}"
    ev_name_2 = f"ev2-{generate_random_string(6, force_lower=True)}"
    ev_names = [ev_name_1, ev_name_2]
    field_values = {n: f"events/{n}" for n in ev_names}

    step_count = 9 if export_format == "json" else 7
    with TestLog(
        f"test_namespace_asset_event_export_import[{export_format}-{asset_type}]",
        total_steps=step_count,
    ) as log:

        with log.step(1, "Ensure Device + Endpoint"):
            device_name, endpoint_name = ensure_device_and_endpoint(
                log, instance_name, resource_group, asset_type, endpoint_type,
                endpoint_address, shared_device, endpoint_cache,
            )

        with log.step(2, f"Ensure {asset_type} Asset + Create Event Group"):
            asset_name = ensure_asset_for_format_tests(
                log, instance_name, resource_group, asset_type, device_name,
                endpoint_name, tracked_resources, "event", format_test_asset_cache,
            )
            log.run_command(
                f"az iot ops ns asset {asset_type} event-group add --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} --name {event_group_name} "
                f"--data-source events/group1"
            )

        cmd_prefix = f"az iot ops ns asset {asset_type} event"
        cmd_args = (
            f"--asset {asset_name} --instance {instance_name} -g {resource_group}"
            f" --event-group {event_group_name}"
        )

        with log.step(3, "Add Events"):
            add_tpl = f"{cmd_prefix} add {cmd_args} --name {{name}} --data-source events/{{name}}"
            for name in ev_names:
                log.run_command(add_tpl.format(name=name))
            wait_for_expected_count(
                list_cmd=f"{cmd_prefix} list {cmd_args}",
                expected_count=2, expected_names=ev_names,
                reissue_cmds={n: add_tpl.format(name=n) for n in ev_names},
                run_fn=log.run_command,
            )

        with log.step(4, f"Export Events ({export_format})"):
            export_result = log.run_command(
                f"{cmd_prefix} export {cmd_args} -f {export_format} --output-dir {output_dir}"
            )
            exported_file = validate_export_result(
                log, export_result, "event_count", 2, export_format, tracked_files,
            )
            exported_items = parse_exported_file(exported_file, export_format)
            validate_exported_items(
                log, exported_items, ev_names,
                export_format=export_format, item_label="event",
            )
            if export_format == "json":
                ev_dict = {ev["name"]: ev for ev in exported_items}
                for name in ev_names:
                    log.check(f"{name} dataSource",
                              ev_dict[name].get("dataSource") == field_values[name],
                              actual=ev_dict[name].get("dataSource"))

        with log.step(5, "Remove All Events"):
            rm_tpl = f"{cmd_prefix} remove {cmd_args} --name {{name}}"
            for name in ev_names:
                log.run_command(rm_tpl.format(name=name))
            wait_for_expected_count(
                list_cmd=f"{cmd_prefix} list {cmd_args}",
                expected_count=0, expected_names=ev_names,
                reissue_cmds={n: rm_tpl.format(name=n) for n in ev_names},
                reissue_on_missing=False, run_fn=log.run_command,
            )

        with log.step(6, "Import Events"):
            imported = log.run_command(f"{cmd_prefix} import {cmd_args} --input-file {exported_file}")
            verify_items_by_name(
                log, imported, ev_names, field_name="dataSource",
                field_values=field_values, label="imported",
            )

        with log.step(7, "Verify Final State"):
            final = log.run_command(f"{cmd_prefix} list {cmd_args}")
            log.check("final count == 2", len(final) == 2, actual=len(final))

        if export_format == "json":
            do_replace_import_test(
                log, 8, 9, exported_file, tracked_files,
                import_cmd_base=f"{cmd_prefix} import {cmd_args}",
                field_name="dataSource", item_names=ev_names,
            )
