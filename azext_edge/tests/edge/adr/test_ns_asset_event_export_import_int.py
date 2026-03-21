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
from ._export_import_helpers import (
    _parse_exported_file, _validate_exported_items,
    _ensure_device_and_endpoint, _ensure_asset_for_format_tests,
)

pytestmark = [pytest.mark.rpsaas, pytest.mark.long_running]


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
