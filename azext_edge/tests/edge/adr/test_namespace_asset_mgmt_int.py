# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from random import randint
from typing import List
import pytest

from ...generators import generate_random_string
from ...helpers import run, wait_for_expected_count
from .namespace_helpers import (
    create_config_file, assert_management_group_properties, assert_management_group_action_properties,
    _save_json_to_file, _try_show_template
)


pytestmark = [pytest.mark.rpsaas, pytest.mark.long_running]


def test_namespace_custom_asset_management_group_lifecycle_operations(
    asset_factory, tracked_files: List[str]
):
    """Test complete lifecycle of custom asset management group and action operations."""
    # Setup from shared fixtures
    info = asset_factory("custom")
    asset_name = info["name"]
    instance_name = info["instanceName"]
    resource_group = info["resourceGroup"]
    mgmt_group_name = f"mgmt-{generate_random_string(6, force_lower=True)}"
    action_name_1 = f"action1-{generate_random_string(6, force_lower=True)}"
    action_name_2 = f"action2-{generate_random_string(6, force_lower=True)}"

    # 1. CREATE MANAGEMENT GROUP
    default_topic = "factory/custom/management/responses"
    default_timeout = 30
    custom_config_path, custom_config = create_config_file(tracked_files)

    mgmt_group_result = run(
        f"az iot ops ns asset custom mgmt-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {mgmt_group_name} "
        f"--default-topic '{default_topic}' --default-timeout {default_timeout} --config {custom_config_path}"
    )

    assert_management_group_properties(
        mgmt_group_result,
        name=mgmt_group_name,
        default_topic=default_topic,
        default_timeout=default_timeout,
        custom_configuration=custom_config,
    )

    # 2. LIST MANAGEMENT GROUPS
    mgmt_groups_list = run(
        f"az iot ops ns asset custom mgmt-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )

    assert len(mgmt_groups_list) >= 1
    mgmt_group_names = [mg["name"] for mg in mgmt_groups_list]
    assert mgmt_group_name in mgmt_group_names

    # 3. SHOW MANAGEMENT GROUP
    mgmt_group_show = run(
        f"az iot ops ns asset custom mgmt-group show --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {mgmt_group_name}"
    )

    assert_management_group_properties(
        mgmt_group_show,
        name=mgmt_group_name,
        default_topic=default_topic,
        default_timeout=default_timeout
    )

    # 4. UPDATE MANAGEMENT GROUP
    updated_default_topic = "factory/custom/management/updated_responses"
    updated_default_timeout = 45
    updated_data_source = f"nsu=updatedNamespace;i={randint(1, 999)}"
    custom_config_path, custom_config = create_config_file(tracked_files)

    updated_mgmt_group = run(
        f"az iot ops ns asset custom mgmt-group update --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {mgmt_group_name} --default-topic '{updated_default_topic}' "
        f"--default-timeout {updated_default_timeout} --config {custom_config_path} "
        f"--data-source '{updated_data_source}'"
    )

    assert_management_group_properties(
        updated_mgmt_group,
        name=mgmt_group_name,
        data_source=updated_data_source,
        default_topic=updated_default_topic,
        default_timeout=updated_default_timeout,
        custom_configuration=custom_config,
    )

    # 5. CREATE MANAGEMENT GROUP WITH REPLACE
    replaced_default_topic = "factory/custom/management/replaced_responses"
    replaced_data_source = f"nsu=replacedNamespace;i={randint(1, 999)}"
    replaced_mgmt_group = run(
        f"az iot ops ns asset custom mgmt-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {mgmt_group_name} --default-topic '{replaced_default_topic}' "
        f"--data-source '{replaced_data_source}' --replace"
    )

    assert_management_group_properties(
        replaced_mgmt_group,
        name=mgmt_group_name,
        data_source=replaced_data_source,
        default_topic=replaced_default_topic,
    )

    # 6. ADD MANAGEMENT GROUP ACTION
    action_target_uri = "/mgmt/device_service?profile=startmethod"
    action_type = "Call"
    action_timeout = 60
    action_topic = "factory/custom/actions/control"
    custom_config_path, custom_config = create_config_file(tracked_files)

    action_result = run(
        f"az iot ops ns asset custom mgmt-action add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --group {mgmt_group_name} --name {action_name_1} "
        f"--target-uri {action_target_uri} --action-type {action_type} --timeout {action_timeout} "
        f"--topic {action_topic} --config {custom_config_path}"
    )

    assert_management_group_action_properties(
        action_result,
        name=action_name_1,
        target_uri=action_target_uri,
        action_type=action_type,
        timeout=action_timeout,
        topic=action_topic,
        custom_configuration=custom_config
    )

    # 7. ADD ANOTHER MANAGEMENT GROUP ACTION
    action_target_uri_2 = "/mgmt/device_service?profile=stopmethod"
    action_type_2 = "Read"
    action_timeout_2 = 45
    custom_config_path, custom_config = create_config_file(tracked_files)

    action_result_2 = run(
        f"az iot ops ns asset custom mgmt-action add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --group {mgmt_group_name} --name {action_name_2} "
        f"--target-uri {action_target_uri_2} --action-type {action_type_2} --timeout {action_timeout_2} "
        f"--config {custom_config_path}"
    )

    assert_management_group_action_properties(
        action_result_2,
        name=action_name_2,
        target_uri=action_target_uri_2,
        action_type=action_type_2,
        timeout=action_timeout_2,
        custom_configuration=custom_config
    )

    # 8. LIST MANAGEMENT GROUP ACTIONS
    actions_list = wait_for_expected_count(
        list_cmd=(
            f"az iot ops ns asset custom mgmt-action list --asset {asset_name} --instance {instance_name} "
            f"-g {resource_group} --group {mgmt_group_name}"
        ),
        expected_count=2,
        expected_names=[action_name_1, action_name_2],
    )

    assert len(actions_list) >= 2

    # 9. REPLACE MANAGEMENT GROUP ACTION
    replaced_action_target_uri = "/mgmt/device_service?profile=Profile1"
    replaced_action = run(
        f"az iot ops ns asset custom mgmt-action add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --group {mgmt_group_name} --name {action_name_1} "
        f"--target-uri {replaced_action_target_uri} --action-type {action_type} --replace"
    )

    assert_management_group_action_properties(
        replaced_action,
        name=action_name_1,
        target_uri=replaced_action_target_uri,
        action_type=action_type
    )

    # 10. REMOVE MANAGEMENT GROUP ACTION
    run(
        f"az iot ops ns asset custom mgmt-action remove --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --group {mgmt_group_name} --name {action_name_1}"
    )

    # Verify removal by listing
    remaining_actions = run(
        f"az iot ops ns asset custom mgmt-action list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --group {mgmt_group_name}"
    )

    remaining_action_names = [ac["name"] for ac in remaining_actions]
    assert action_name_1 not in remaining_action_names
    assert action_name_2 in remaining_action_names

    # 11. REMOVE MANAGEMENT GROUP
    run(
        f"az iot ops ns asset custom mgmt-group remove --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {mgmt_group_name}"
    )

    # Verify removal by listing
    remaining_mgmt_groups = run(
        f"az iot ops ns asset custom mgmt-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )

    remaining_mgmt_group_names = [mg["name"] for mg in remaining_mgmt_groups]
    assert mgmt_group_name not in remaining_mgmt_group_names


def test_namespace_opcua_asset_management_group_lifecycle_operations(
    asset_factory,
):
    """Test complete lifecycle of OPC UA asset management group operations."""
    # Setup from shared fixtures
    info = asset_factory("opcua")
    asset_name = info["name"]
    instance_name = info["instanceName"]
    resource_group = info["resourceGroup"]
    mgmt_group_name = f"mgmt-{generate_random_string(6, force_lower=True)}"
    action_name = f"action-{generate_random_string(6, force_lower=True)}"

    # 1. CREATE MANAGEMENT GROUP WITH ONLY REQUIRED PARAMS (no data-source)
    default_topic = "factory/opcua/management/responses"
    default_timeout = 45

    mgmt_group_result = run(
        f"az iot ops ns asset opcua mgmt-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {mgmt_group_name} --default-topic '{default_topic}' "
        f"--default-timeout {default_timeout}"
    )

    assert_management_group_properties(
        mgmt_group_result,
        name=mgmt_group_name,
        default_topic=default_topic,
        default_timeout=default_timeout,
    )

    # 2. LIST MANAGEMENT GROUPS
    mgmt_groups_list = run(
        f"az iot ops ns asset opcua mgmt-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )

    assert len(mgmt_groups_list) >= 1
    mgmt_group_names = [mg["name"] for mg in mgmt_groups_list]
    assert mgmt_group_name in mgmt_group_names

    # 3. SHOW MANAGEMENT GROUP
    mgmt_group_show = run(
        f"az iot ops ns asset opcua mgmt-group show --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {mgmt_group_name}"
    )

    assert_management_group_properties(
        mgmt_group_show,
        name=mgmt_group_name,
        default_topic=default_topic,
        default_timeout=default_timeout
    )

    # 4. UPDATE MANAGEMENT GROUP
    updated_default_topic = "factory/opcua/management/updated_responses"
    updated_default_timeout = 60

    updated_mgmt_group = run(
        f"az iot ops ns asset opcua mgmt-group update --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {mgmt_group_name} --default-topic '{updated_default_topic}' "
        f"--default-timeout {updated_default_timeout}"
    )

    assert_management_group_properties(
        updated_mgmt_group,
        name=mgmt_group_name,
        default_topic=updated_default_topic,
        default_timeout=updated_default_timeout,
    )

    # 5. CREATE MANAGEMENT GROUP WITH REPLACE (with optional data-source)
    replaced_default_topic = "factory/opcua/management/replaced_responses"
    replaced_data_source = f"nsu=replacedNamespace;i={randint(1, 999)}"
    replaced_mgmt_group = run(
        f"az iot ops ns asset opcua mgmt-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {mgmt_group_name} --default-topic '{replaced_default_topic}' "
        f"--data-source '{replaced_data_source}' --replace"
    )

    assert_management_group_properties(
        replaced_mgmt_group,
        name=mgmt_group_name,
        data_source=replaced_data_source,
        default_topic=replaced_default_topic
    )

    # 6. ADD MANAGEMENT GROUP ACTION
    action_target_uri = "/mgmt/device_service?profile=startProduction"
    action_type = "Call"
    action_timeout = 30
    action_topic = "factory/opcua/actions/production"
    action_type_ref = "ns=2;i=1234"

    action_result = run(
        f"az iot ops ns asset opcua mgmt-action add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --group {mgmt_group_name} --name {action_name} "
        f"--target-uri {action_target_uri} --action-type {action_type} --timeout {action_timeout} "
        f"--topic {action_topic} --type-ref '{action_type_ref}'"
    )

    assert_management_group_action_properties(
        action_result,
        name=action_name,
        target_uri=action_target_uri,
        action_type=action_type,
        timeout=action_timeout,
        topic=action_topic,
        type_ref=action_type_ref
    )

    # 7. LIST MANAGEMENT GROUP ACTIONS
    actions_list = run(
        f"az iot ops ns asset opcua mgmt-action list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --group {mgmt_group_name}"
    )

    assert len(actions_list) >= 1
    action_names = [ac["name"] for ac in actions_list]
    assert action_name in action_names

    # 8. REPLACE MANAGEMENT GROUP ACTION
    replaced_action_target_uri = "/mgmt/device_service?profile=stopProduction"
    replaced_action = run(
        f"az iot ops ns asset opcua mgmt-action add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --group {mgmt_group_name} --name {action_name} "
        f"--target-uri {replaced_action_target_uri} --action-type {action_type} --replace"
    )

    assert_management_group_action_properties(
        replaced_action,
        name=action_name,
        target_uri=replaced_action_target_uri,
        action_type=action_type
    )

    # 9. REMOVE MANAGEMENT GROUP ACTION
    run(
        f"az iot ops ns asset opcua mgmt-action remove --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --group {mgmt_group_name} --name {action_name}"
    )

    # Verify removal by listing
    remaining_actions = run(
        f"az iot ops ns asset opcua mgmt-action list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --group {mgmt_group_name}"
    )

    remaining_action_names = [ac["name"] for ac in remaining_actions]
    assert action_name not in remaining_action_names

    # 10. REMOVE MANAGEMENT GROUP
    run(
        f"az iot ops ns asset opcua mgmt-group remove --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {mgmt_group_name}"
    )

    # Verify removal by listing
    remaining_mgmt_groups = run(
        f"az iot ops ns asset opcua mgmt-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )

    remaining_mgmt_group_names = [mg["name"] for mg in remaining_mgmt_groups]
    assert mgmt_group_name not in remaining_mgmt_group_names


def test_namespace_onvif_asset_management_group_lifecycle_operations(
    asset_factory,
):
    """Test complete lifecycle of ONVIF asset management group operations."""
    # Setup from shared fixtures
    info = asset_factory("onvif")
    asset_name = info["name"]
    instance_name = info["instanceName"]
    resource_group = info["resourceGroup"]
    mgmt_group_name = f"mgmt-{generate_random_string(6, force_lower=True)}"

    # 1. CREATE MANAGEMENT GROUP
    default_topic = "factory/onvif/management/responses"
    default_timeout = 25
    data_source = f"nsu=onvifNamespace;i={randint(1, 999)}"

    mgmt_group_result = run(
        f"az iot ops ns asset onvif mgmt-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {mgmt_group_name} --default-topic '{default_topic}' "
        f"--default-timeout {default_timeout} --data-source '{data_source}'"
    )

    assert_management_group_properties(
        mgmt_group_result,
        name=mgmt_group_name,
        data_source=data_source,
        default_topic=default_topic,
        default_timeout=default_timeout,
    )

    # 2. LIST MANAGEMENT GROUPS
    mgmt_groups_list = run(
        f"az iot ops ns asset onvif mgmt-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )

    assert len(mgmt_groups_list) >= 1
    mgmt_group_names = [mg["name"] for mg in mgmt_groups_list]
    assert mgmt_group_name in mgmt_group_names

    # 3. SHOW MANAGEMENT GROUP
    mgmt_group_show = run(
        f"az iot ops ns asset onvif mgmt-group show --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {mgmt_group_name}"
    )

    assert_management_group_properties(
        mgmt_group_show,
        name=mgmt_group_name,
        default_topic=default_topic,
        default_timeout=default_timeout
    )

    # 4. UPDATE MANAGEMENT GROUP
    updated_default_topic = "factory/onvif/management/updated_responses"
    updated_default_timeout = 40
    updated_data_source = f"nsu=updatedNamespace;i={randint(1, 999)}"

    updated_mgmt_group = run(
        f"az iot ops ns asset onvif mgmt-group update --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {mgmt_group_name} --default-topic '{updated_default_topic}' "
        f"--default-timeout {updated_default_timeout} --data-source '{updated_data_source}'"
    )

    assert_management_group_properties(
        updated_mgmt_group,
        name=mgmt_group_name,
        data_source=updated_data_source,
        default_topic=updated_default_topic,
        default_timeout=updated_default_timeout,
    )

    # 5. CREATE MANAGEMENT GROUP WITH REPLACE
    replaced_default_topic = "factory/onvif/management/replaced_responses"
    replaced_data_source = f"nsu=replacedNamespace;i={randint(1, 999)}"
    replaced_mgmt_group = run(
        f"az iot ops ns asset onvif mgmt-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {mgmt_group_name} --default-topic '{replaced_default_topic}' "
        f"--data-source '{replaced_data_source}' --replace"
    )

    assert_management_group_properties(
        replaced_mgmt_group,
        name=mgmt_group_name,
        data_source=replaced_data_source,
        default_topic=replaced_default_topic
    )

    # 6. REMOVE MANAGEMENT GROUP
    run(
        f"az iot ops ns asset onvif mgmt-group remove --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {mgmt_group_name}"
    )

    # Verify removal by listing
    remaining_mgmt_groups = run(
        f"az iot ops ns asset onvif mgmt-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )

    remaining_mgmt_group_names = [mg["name"] for mg in remaining_mgmt_groups]
    assert mgmt_group_name not in remaining_mgmt_group_names


# ---------------------------------------------------------------------------
# Generalized (connector-agnostic) management group / action commands
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("asset_type", ["opcua", "custom"])
def test_generalized_management_lifecycle(asset_factory, tracked_files: List[str], asset_type: str):
    """Full lifecycle of the generalized (connector-agnostic) mgmt-group + mgmt-action commands.

    The connector type is detected automatically from the asset's device endpoint. A connector
    template must exist for --show-template / --mgmt-group-config / --action-config to resolve
    connector metadata. When no config schema is available (OPC UA bundles empty management
    schemas, custom may have no template installed), --show-template returns an empty config and
    the test exercises the metadata-free path (no config payload).
    """
    info = asset_factory(asset_type)
    asset_name = info["name"]
    instance_name = info["instanceName"]
    resource_group = info["resourceGroup"]
    mg_name = f"gen-mg-{generate_random_string(6, force_lower=True)}"
    mg_name_2 = f"gen-mg2-{generate_random_string(6, force_lower=True)}"
    action_name = f"gen-act-{generate_random_string(6, force_lower=True)}"
    target_uri = (
        "nsu=http://microsoft.com/Opc/OpcPlc/Boiler;i=7019"
        if asset_type == "opcua"
        else "/mgmt/device_service?profile=startmethod"
    )

    # 1. SHOW-TEMPLATE mgmt-group (may be empty when no config schema is available)
    mg_template = _try_show_template(
        f"az iot ops ns asset mgmt-group add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} "
        f"--name {mg_name} --show-template config"
    )
    mg_config_arg = ""
    if mg_template and mg_template.get("mgmtGroupConfig", {}).get("managementGroupConfiguration"):
        assert "connectorType" in mg_template
        mg_config_file = _save_json_to_file(mg_template, tracked_files)
        mg_config_arg = f"--mgmt-group-config {mg_config_file}"

    # 2. ADD mgmt-group
    default_topic = "factory/mgmt/responses"
    default_timeout = 30
    added_mg = run(
        f"az iot ops ns asset mgmt-group add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {mg_name} "
        f"--default-topic '{default_topic}' --default-timeout {default_timeout} {mg_config_arg}"
    )
    assert_management_group_properties(
        added_mg, name=mg_name, default_topic=default_topic, default_timeout=default_timeout
    )

    # 3. SHOW mgmt-group
    shown_mg = run(
        f"az iot ops ns asset mgmt-group show --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {mg_name}"
    )
    assert_management_group_properties(shown_mg, name=mg_name, default_topic=default_topic)

    # 4. LIST mgmt-groups
    mg_list = run(
        f"az iot ops ns asset mgmt-group list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group}"
    )
    assert any(mg["name"] == mg_name for mg in mg_list)

    # 5. ADD a second mgmt-group (minimal)
    added_mg_2 = run(
        f"az iot ops ns asset mgmt-group add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {mg_name_2}"
    )
    assert_management_group_properties(added_mg_2, name=mg_name_2)
    mg_names = [mg["name"] for mg in run(
        f"az iot ops ns asset mgmt-group list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group}"
    )]
    assert mg_name in mg_names and mg_name_2 in mg_names

    # 6. UPDATE mgmt-group
    updated_topic = "factory/mgmt/updated_responses"
    updated_timeout = 45
    updated_mg = run(
        f"az iot ops ns asset mgmt-group update --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --name {mg_name} "
        f"--default-topic '{updated_topic}' --default-timeout {updated_timeout}"
    )
    assert_management_group_properties(
        updated_mg, name=mg_name, default_topic=updated_topic, default_timeout=updated_timeout
    )

    # 7. SHOW-TEMPLATE action (may be empty)
    act_template = _try_show_template(
        f"az iot ops ns asset mgmt-action add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --group {mg_name} "
        f"--name {action_name} --target-uri '{target_uri}' --show-template config"
    )
    act_config_arg = ""
    if act_template and act_template.get("actionConfig", {}).get("actionConfiguration"):
        assert "connectorType" in act_template
        act_config_file = _save_json_to_file(act_template, tracked_files)
        act_config_arg = f"--action-config {act_config_file}"

    # 8. ADD action
    action_type = "Call"
    action_timeout = 60
    added_actions = run(
        f"az iot ops ns asset mgmt-action add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --group {mg_name} "
        f"--name {action_name} --target-uri '{target_uri}' --action-type {action_type} "
        f"--timeout {action_timeout} {act_config_arg}"
    )
    assert_management_group_action_properties(
        added_actions, name=action_name, target_uri=target_uri,
        action_type=action_type, timeout=action_timeout,
    )

    # 9. LIST actions
    act_list = run(
        f"az iot ops ns asset mgmt-action list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --group {mg_name}"
    )
    assert any(a["name"] == action_name for a in act_list)

    # 10. REPLACE action
    replaced_actions = run(
        f"az iot ops ns asset mgmt-action add --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --group {mg_name} "
        f"--name {action_name} --target-uri '{target_uri}' --replace"
    )
    assert_management_group_action_properties(replaced_actions, name=action_name)

    # 11. EXPORT mgmt-groups
    mg_export = run(
        f"az iot ops ns asset mgmt-group export --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --output-dir /tmp --replace"
    )
    assert mg_export["management_group_count"] >= 1
    tracked_files.append(mg_export["file_path"])

    # 12. EXPORT actions
    act_export = run(
        f"az iot ops ns asset mgmt-action export --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --group {mg_name} "
        f"--output-dir /tmp --replace"
    )
    assert act_export["action_count"] >= 1
    tracked_files.append(act_export["file_path"])

    # 13. REMOVE action
    run(
        f"az iot ops ns asset mgmt-action remove --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --group {mg_name} --name {action_name}"
    )
    act_list_after = run(
        f"az iot ops ns asset mgmt-action list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group} --group {mg_name}"
    )
    assert not any(a["name"] == action_name for a in (act_list_after or []))

    # 14. REMOVE mgmt-groups
    for mg in [mg_name, mg_name_2]:
        run(
            f"az iot ops ns asset mgmt-group remove --asset {asset_name} "
            f"--instance {instance_name} -g {resource_group} --name {mg}"
        )
    remaining = [mg["name"] for mg in (run(
        f"az iot ops ns asset mgmt-group list --asset {asset_name} "
        f"--instance {instance_name} -g {resource_group}"
    ) or [])]
    assert mg_name not in remaining and mg_name_2 not in remaining
