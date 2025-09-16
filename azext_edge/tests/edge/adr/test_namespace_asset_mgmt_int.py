# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from random import randint
from typing import List
import pytest

from ...generators import generate_random_string
from ...helpers import run
from .namespace_helpers import (
    create_config_file, assert_management_group_properties, assert_management_group_action_properties
)


pytestmark = pytest.mark.long_running


def test_namespace_custom_asset_management_group_lifecycle_operations(
    require_init, tracked_resources: List[str], tracked_files: List[str]
):
    """Test complete lifecycle of custom asset management group and action operations."""
    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"custom-{generate_random_string(8)}"
    asset_name = f"custom-{generate_random_string(8, force_lower=True)}"
    mgmt_group_name = f"mgmt-{generate_random_string(6, force_lower=True)}"
    action_name_1 = f"action1-{generate_random_string(6, force_lower=True)}"
    action_name_2 = f"action2-{generate_random_string(6, force_lower=True)}"

    # Create Device
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    # Create device endpoint
    run(
        f"az iot ops ns device endpoint inbound add custom --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'http://192.168.1.100:8000/custom/service' "
        "--endpoint-type custom"
    )

    # Create Custom asset
    asset_custom = run(
        f"az iot ops ns asset custom create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name} "
        f"--description \"Custom Device for Management Testing\" --display \"Multi-Sensor Management\" "
        f"--model \"Custom-MG100\" --manufacturer \"CustomDevices\""
    )
    tracked_resources.append(asset_custom["id"])

    # 1. CREATE MANAGEMENT GROUP
    default_topic = "factory/custom/management/responses"
    default_timeout = 30
    data_source = f"nsu=customNamespace;i={randint(1, 999)}"
    custom_config_path, custom_config = create_config_file(tracked_files)

    mgmt_group_result = run(
        f"az iot ops ns asset custom mgmt-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {mgmt_group_name} --data-source {data_source} "
        f"--default-topic {default_topic} --default-timeout {default_timeout} --config {custom_config_path}"
    )

    assert_management_group_properties(
        mgmt_group_result,
        name=mgmt_group_name,
        data_source=data_source,
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
        f"-g {resource_group} --name {mgmt_group_name} --default-topic {updated_default_topic} "
        f"--default-timeout {updated_default_timeout} --config {custom_config_path} "
        f"--data-source {updated_data_source}"
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
        f"-g {resource_group} --name {mgmt_group_name} --default-topic {replaced_default_topic} "
        f"--data-source {replaced_data_source} --replace"
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
    actions_list = run(
        f"az iot ops ns asset custom mgmt-action list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --group {mgmt_group_name}"
    )

    assert len(actions_list) >= 2
    action_names = [ac["name"] for ac in actions_list]
    assert action_name_1 in action_names
    assert action_name_2 in action_names

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


def test_namespace_opcua_asset_management_group_lifecycle_operations(require_init, tracked_resources: List[str]):
    """Test complete lifecycle of OPC UA asset management group operations."""
    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"opcua-{generate_random_string(8)}"
    asset_name = f"opcua-{generate_random_string(8, force_lower=True)}"
    mgmt_group_name = f"mgmt-{generate_random_string(6, force_lower=True)}"
    action_name = f"action-{generate_random_string(6, force_lower=True)}"

    # Create Device
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    # Create device endpoint
    run(
        f"az iot ops ns device endpoint inbound add opcua --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'opc.tcp://192.168.1.100:4840' "
    )

    # Create OPC UA asset
    asset_opcua = run(
        f"az iot ops ns asset opcua create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name} "
        f"--description \"OPC UA Device for Management Testing\" --display \"OPC UA Management Server\" "
        f"--model \"OPCUA-MG200\" --manufacturer \"OPCDevices\""
    )
    tracked_resources.append(asset_opcua["id"])

    # 1. CREATE MANAGEMENT GROUP WITH FULL OPCUA CONFIGURATION
    default_topic = "factory/opcua/management/responses"
    default_timeout = 45
    data_source = f"nsu=opcuaNamespace;i={randint(1, 999)}"

    mgmt_group_result = run(
        f"az iot ops ns asset opcua mgmt-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {mgmt_group_name} --default-topic {default_topic} "
        f"--default-timeout {default_timeout} --data-source {data_source}"
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
        f"-g {resource_group} --name {mgmt_group_name} --default-topic {updated_default_topic} "
        f"--default-timeout {updated_default_timeout}"
    )

    assert_management_group_properties(
        updated_mgmt_group,
        name=mgmt_group_name,
        data_source=data_source,
        default_topic=updated_default_topic,
        default_timeout=updated_default_timeout,
    )

    # 5. CREATE MANAGEMENT GROUP WITH REPLACE
    replaced_default_topic = "factory/opcua/management/replaced_responses"
    replaced_data_source = f"nsu=replacedNamespace;i={randint(1, 999)}"
    replaced_mgmt_group = run(
        f"az iot ops ns asset opcua mgmt-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {mgmt_group_name} --default-topic {replaced_default_topic} "
        f"--data-source {replaced_data_source} --replace"
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

    action_result = run(
        f"az iot ops ns asset opcua mgmt-action add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --group {mgmt_group_name} --name {action_name} "
        f"--target-uri {action_target_uri} --action-type {action_type} --timeout {action_timeout} "
        f"--topic {action_topic}"
    )

    assert_management_group_action_properties(
        action_result,
        name=action_name,
        target_uri=action_target_uri,
        action_type=action_type,
        timeout=action_timeout,
        topic=action_topic
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


def test_namespace_onvif_asset_management_group_lifecycle_operations(require_init, tracked_resources: List[str]):
    """Test complete lifecycle of ONVIF asset management group operations."""
    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"onvif-{generate_random_string(8)}"
    asset_name = f"onvif-{generate_random_string(8, force_lower=True)}"
    mgmt_group_name = f"mgmt-{generate_random_string(6, force_lower=True)}"

    # Create Device
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    # Create device endpoint
    run(
        f"az iot ops ns device endpoint inbound add onvif --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'http://192.168.1.100:8080/onvif/device' "
    )

    # Create ONVIF asset
    asset_onvif = run(
        f"az iot ops ns asset onvif create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name} "
        f"--description \"ONVIF Device for Management Testing\" --display \"ONVIF Management Camera\" "
        f"--model \"ONVIF-MG300\" --manufacturer \"ONVIFDevices\""
    )
    tracked_resources.append(asset_onvif["id"])

    # 1. CREATE MANAGEMENT GROUP
    default_topic = "factory/onvif/management/responses"
    default_timeout = 25
    data_source = f"nsu=onvifNamespace;i={randint(1, 999)}"

    mgmt_group_result = run(
        f"az iot ops ns asset onvif mgmt-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {mgmt_group_name} --default-topic {default_topic} "
        f"--default-timeout {default_timeout} --data-source {data_source}"
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
        f"-g {resource_group} --name {mgmt_group_name} --default-topic {updated_default_topic} "
        f"--default-timeout {updated_default_timeout} --data-source {updated_data_source}"
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
        f"-g {resource_group} --name {mgmt_group_name} --default-topic {replaced_default_topic} "
        f"--data-source {replaced_data_source} --replace"
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
