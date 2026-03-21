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
