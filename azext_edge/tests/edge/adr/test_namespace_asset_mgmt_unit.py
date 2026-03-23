# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
import responses
import json
from copy import deepcopy
from random import randint
from typing import Optional
from azure.cli.core.azclierror import InvalidArgumentValueError
from azext_edge.edge.commands_namespaces import (
    add_namespace_custom_asset_management_group,
    add_namespace_opcua_asset_management_group,
    add_namespace_onvif_asset_management_group,
    list_namespace_asset_management_groups,
    show_namespace_asset_management_group,
    remove_namespace_asset_management_group,
    update_namespace_custom_asset_management_group,
    update_namespace_opcua_asset_management_group,
    update_namespace_onvif_asset_management_group,
    add_namespace_custom_asset_management_group_action,
    add_namespace_opcua_asset_management_group_action,
    list_namespace_asset_management_group_actions,
    remove_namespace_asset_management_group_action
)

from .test_namespace_assets_unit import (
    get_namespace_asset_mgmt_uri, get_namespace_asset_record, add_device_get_call
)
from ...generators import generate_random_string


def generate_management_group(
    group_name: Optional[str] = None,
    asset_type: str = "custom",
    num_actions: int = 0
) -> dict:
    """Generate a mock management group with the specified name and type."""
    group_name = group_name or f"group{generate_random_string(12)}"
    management_group = {
        "name": group_name,
        "dataSource": f"nsu=original;i={randint(1, 1000)}",
        "defaultTopic": f"/contoso/mgmt/{group_name}",
        "defaultTimeoutInSeconds": randint(1000, 10000),
        "actions": [
            generate_management_group_action(asset_type=asset_type)
            for _ in range(num_actions)
        ],
        "typeRef": None
    }

    if asset_type == "custom":
        # Generate custom management group configuration
        management_group["managementGroupConfiguration"] = json.dumps({
            "customProperty": f"value{randint(1, 100)}",
            "groupType": "custom-type"
        })
    return management_group


def generate_management_group_action(
    action_name: Optional[str] = None,
    asset_type: str = "custom"
) -> dict:
    """Generate a mock management group action with the specified name and type."""
    action_name = action_name or f"action{generate_random_string(12)}"
    action = {
        "name": action_name,
        "targetUri": f"ns=2;s=Action{randint(1, 100)}",
        "topic": f"/contoso/mgmt/action/{action_name}",
        "timeout": randint(500, 5000),
        "actionType": "Call"
    }

    if asset_type == "custom":
        action["actionConfiguration"] = json.dumps({
            "method": "execute",
            "parameters": {"param1": "value1"}
        })

    return action


@pytest.mark.parametrize("asset_type, command_func, mgmt_params", [
    # Custom asset management group tests
    (
        "custom",
        add_namespace_custom_asset_management_group,
        {
            "mgmt_custom_configuration": json.dumps({
                "customProperty": "testValue",
                "groupType": "management-ops",
                "operationMode": "async"
            }),
            "type_ref": f"custom.management{randint(0, 1000)}"
        },
    ),
    # OPC UA asset management group tests
    (
        "opcua",
        add_namespace_opcua_asset_management_group,
        {},  # No custom configuration for OPC UA
    ),
    # ONVIF asset management group tests
    (
        "onvif",
        add_namespace_onvif_asset_management_group,
        {},  # No custom configuration for ONVIF
    ),
])
@pytest.mark.parametrize("has_previous_groups, replace_group", [
    (False, False),  # No previous management groups, do not replace
    (True, False),   # Previous management groups exist, do not replace
    (True, True)     # Previous management groups exist, replace
])
@pytest.mark.parametrize("default_topic", [None, "/factory/mgmt/operations"])
@pytest.mark.parametrize("default_timeout", [None, 5000])
@pytest.mark.parametrize("data_source", [
    None,
    f"nsu=test;i={randint(1, 1000)}",
])
def test_add_namespace_asset_management_group(
    mocked_cmd,
    mocked_responses: responses,
    asset_type: str,
    command_func,
    mgmt_params: dict,
    has_previous_groups: bool,
    replace_group: bool,
    default_topic: Optional[str],
    default_timeout: Optional[int],
    data_source: Optional[str],
    mocked_check_cluster_connectivity,
    mocked_get_namespace_for_instance
):
    asset_name = f"test{asset_type.title()}Asset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"
    group_name = f"test{asset_type.title()}Group{generate_random_string(5)}"

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

    # Build expected management group
    expected_group = {
        "name": group_name,
        "actions": []
    }

    # Add default topic, timeout if provided
    if default_topic:
        expected_group["defaultTopic"] = default_topic
    if default_timeout:
        expected_group["defaultTimeoutInSeconds"] = default_timeout

    # Add custom configuration for custom assets
    if asset_type == "custom":
        expected_group["managementGroupConfiguration"] = mgmt_params.get("mgmt_custom_configuration")
        expected_group["typeRef"] = mgmt_params.get("type_ref")

    # Generate mock asset
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
    add_device_get_call(
        mocked_responses,
        resource_group_name=resource_group_name,
        namespace_name=namespace_name,
        device_name=mocked_asset["properties"]["deviceRef"]["deviceName"],
        endpoint_name=mocked_asset["properties"]["deviceRef"]["endpointName"],
        endpoint_type=asset_type
    )

    # Add previous management groups if needed for the test case
    if has_previous_groups:
        # Add existing management groups based on asset type
        previous_groups = [
            generate_management_group(asset_type=asset_type),
            generate_management_group(asset_type=asset_type)
        ]
        # If replacing, add a group with the same name
        if replace_group:
            previous_groups.append(generate_management_group(group_name=group_name, asset_type=asset_type))

        mocked_asset["properties"]["managementGroups"] = previous_groups

    # Mock the existing asset
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=mocked_asset,
        status=200
    )

    # Expected asset payload for patch request
    updated_asset = deepcopy(mocked_asset)
    updated_asset["properties"]["managementGroups"] = updated_asset["properties"].get("managementGroups", [])

    # If replacing, keep only non-matching management groups
    if replace_group:
        updated_asset["properties"]["managementGroups"] = [
            g for g in mocked_asset["properties"]["managementGroups"] if g["name"] != group_name
        ]

    updated_asset["properties"]["managementGroups"].append(expected_group)

    # Mock the asset patch response
    mocked_responses.add(
        method=responses.PATCH,
        url=get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        status=200
    )

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=updated_asset,
        status=200
    )

    # Execute the command
    result = command_func(
        cmd=mocked_cmd,
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        data_source=data_source,
        replace=replace_group,
        wait_sec=0,
        default_topic=default_topic,
        default_timeout=default_timeout,
        **mgmt_params,
    )

    # Verify the result
    assert result == expected_group

    # Verify API calls were made correctly
    expected_calls = 4  # device GET, asset GET, asset PATCH, asset GET
    assert len(mocked_responses.calls) == expected_calls
    assert mocked_responses.calls[0].request.method == "GET"  # device
    assert mocked_responses.calls[1].request.method == "GET"  # asset
    assert mocked_responses.calls[2].request.method == "PATCH"  # asset update
    assert mocked_responses.calls[3].request.method == "GET"  # asset

    # Verify the PATCH request body contains the expected management group structure
    patch_body = json.loads(mocked_responses.calls[2].request.body)
    assert "managementGroups" in patch_body["properties"]
    management_groups = patch_body["properties"]["managementGroups"]

    # Find our management group in the list
    added_group = next((g for g in management_groups if g["name"] == group_name), None)
    assert added_group is not None, "Added management group not found in the list of management groups"

    # Verify management group properties
    assert added_group["name"] == group_name
    if data_source:
        assert added_group["dataSource"] == data_source
    else:
        assert "dataSource" not in added_group
    assert added_group["typeRef"] == mgmt_params.get("type_ref")
    assert added_group["defaultTopic"] == default_topic
    assert added_group["defaultTimeoutInSeconds"] == default_timeout
    assert added_group["managementGroupConfiguration"] == mgmt_params.get("mgmt_custom_configuration")

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


@pytest.mark.parametrize("asset_type, command_func", [
    ("custom", add_namespace_custom_asset_management_group),
    ("opcua", add_namespace_opcua_asset_management_group),
    ("onvif", add_namespace_onvif_asset_management_group),
])
def test_add_namespace_asset_management_group_error(
    mocked_cmd,
    mocked_responses: responses,
    asset_type: str,
    command_func,
    mocked_check_cluster_connectivity,
    mocked_get_namespace_for_instance
):
    """Test error cases for adding asset management groups with different asset types.

    Tests the following scenarios:
    - Mismatch between asset type and device endpoint type
    - Management group exists but replace flag not set
    """
    asset_name = "testAsset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"
    group_name = f"test{generate_random_string(5)}"
    data_source = f"nsu=test;i={randint(1, 1000)}"

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

    # Create base parameters for all test cases
    base_params = {
        "cmd": mocked_cmd,
        "instance_name": instance_name,
        "instance_resource_group": instance_resource_group,
        "asset_name": asset_name,
        "group_name": group_name,
        "data_source": data_source,
        "wait_sec": 0
    }

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

    # Test device endpoint type mismatch - use a different endpoint type
    if asset_type != "custom":
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

        assert f"'microsoft.media', but expected 'microsoft.{asset_type}'." in str(excinfo.value).lower()

    mocked_responses.reset()

    # Replace device call with valid asset type
    add_device_get_call(
        mocked_responses,
        resource_group_name=resource_group_name,
        namespace_name=namespace_name,
        device_name=mocked_asset["properties"]["deviceRef"]["deviceName"],
        endpoint_name=mocked_asset["properties"]["deviceRef"]["endpointName"],
        endpoint_type=asset_type
    )

    # Test management group already exists
    mocked_asset["properties"]["managementGroups"] = [
        generate_management_group(group_name=group_name, asset_type=asset_type)
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

    assert f"Management group '{group_name}' already exists in asset '{asset_name}'. " in str(excinfo.value)

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


@pytest.mark.parametrize("num_management_groups", [0, 1, 3])
def test_list_namespace_asset_management_groups(
    mocked_cmd, mocked_responses: responses, num_management_groups: int, mocked_get_namespace_for_instance
):
    asset_name = "testAsset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

    expected_groups = [generate_management_group() for _ in range(num_management_groups)]
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    # ensure we can have the option of no managementGroups property
    if expected_groups:
        mocked_asset["properties"]["managementGroups"] = expected_groups

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

    management_groups = list_namespace_asset_management_groups(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        asset_name=asset_name
    )
    assert len(management_groups) == num_management_groups
    expected_group_map = {group["name"]: group for group in expected_groups}
    for group in management_groups:
        assert group["name"] in expected_group_map
        expected_group = expected_group_map[group["name"]]
        assert group["defaultTopic"] == expected_group["defaultTopic"]
        assert group["defaultTimeoutInSeconds"] == expected_group["defaultTimeoutInSeconds"]
        assert group["actions"] == expected_group["actions"]
        if "managementGroupConfiguration" in expected_group:
            assert group["managementGroupConfiguration"] == expected_group["managementGroupConfiguration"]

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


def test_show_namespace_asset_management_group(
    mocked_cmd, mocked_responses: responses, mocked_get_namespace_for_instance
):
    asset_name = "testAsset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"
    group_name = generate_random_string()

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

    expected_group = generate_management_group(group_name=group_name, asset_type="custom")
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
    mocked_asset["properties"]["managementGroups"] = [expected_group]

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

    management_group = show_namespace_asset_management_group(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        asset_name=asset_name,
        group_name=group_name
    )
    assert management_group["name"] == expected_group["name"]
    assert management_group["defaultTopic"] == expected_group["defaultTopic"]
    assert management_group["defaultTimeoutInSeconds"] == expected_group["defaultTimeoutInSeconds"]
    assert management_group["actions"] == expected_group["actions"]
    assert management_group["managementGroupConfiguration"] == expected_group["managementGroupConfiguration"]

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


@pytest.mark.parametrize("groups_present", [True, False])
@pytest.mark.parametrize("group_deleted", [True, False])
def test_remove_namespace_asset_management_group(
    mocked_cmd,
    mocked_responses: responses,
    groups_present: bool,
    group_deleted: bool,
    mocked_check_cluster_connectivity,
    mocked_get_namespace_for_instance
):
    asset_name = "testAsset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"
    group_name = generate_random_string()

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    # make some other management groups, have the managementGroups prop there
    if groups_present:
        mocked_asset["properties"]["managementGroups"] = [
            generate_management_group(asset_type="custom"),
            generate_management_group(asset_type="opcua")
        ]
    expected_groups = deepcopy(mocked_asset["properties"].get("managementGroups", []))

    # the remove should not fail even if the management group is not there
    if group_deleted:
        mocked_asset["properties"]["managementGroups"] = mocked_asset["properties"].get("managementGroups", [])
        mocked_asset["properties"]["managementGroups"].append(
            generate_management_group(group_name=group_name, asset_type="custom")
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

    if group_deleted:
        # Mock the PATCH request to update the asset
        updated_asset = deepcopy(mocked_asset)
        updated_asset["properties"]["managementGroups"] = expected_groups
        mocked_responses.add(
            responses.PATCH,
            get_namespace_asset_mgmt_uri(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name
            ),
            status=200
        )

        mocked_responses.add(
            method=responses.GET,
            url=get_namespace_asset_mgmt_uri(
                asset_name=asset_name,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name
            ),
            json=updated_asset,
            status=200,
            content_type="application/json",
        )

    result_management_groups = remove_namespace_asset_management_group(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        asset_name=asset_name,
        group_name=group_name,
        wait_sec=0
    )

    assert result_management_groups == expected_groups
    # Verify the number of expected API calls
    assert len(mocked_responses.calls) == (3 if group_deleted else 1)
    assert mocked_responses.calls[0].request.method == "GET"  # asset
    if group_deleted:
        assert mocked_responses.calls[1].request.method == "PATCH"  # asset update
        assert mocked_responses.calls[2].request.method == "GET"  # asset

        # Verify the PATCH request body contains the expected management group structure
        patch_body = json.loads(mocked_responses.calls[1].request.body)
        assert "managementGroups" in patch_body["properties"]
        mgmt_groups = patch_body["properties"]["managementGroups"]
        assert len(mgmt_groups) == len(expected_groups)

        # Verify the deleted management group is not in the PATCH request
        patch_group_names = [group["name"] for group in mgmt_groups]
        assert group_name not in patch_group_names

        # Should contain all other streams
        assert len(patch_group_names) == len(expected_groups)
        for expected_stream in expected_groups:
            assert expected_stream["name"] in patch_group_names

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


@pytest.mark.parametrize("asset_type, command_func, mgmt_params", [
    # Custom asset management group updates
    (
        "custom",
        update_namespace_custom_asset_management_group,
        {
            "mgmt_custom_configuration": json.dumps({
                "customProperty": "updatedValue",
                "groupType": "updated-management-ops",
                "operationMode": "sync"
            }),
            "type_ref": f"custom.management{randint(0, 1000)}"
        },
    ),
    (
        "custom",
        update_namespace_custom_asset_management_group,
        {},  # No configuration update, only default parameters
    ),
    # OPC UA asset management group updates
    (
        "opcua",
        update_namespace_opcua_asset_management_group,
        {},  # No custom configuration for OPC UA
    ),
    # ONVIF asset management group updates
    (
        "onvif",
        update_namespace_onvif_asset_management_group,
        {},  # No custom configuration for ONVIF
    ),
    # Partial updates - only some parameters
    (
        "custom",
        update_namespace_custom_asset_management_group,
        {
            "mgmt_custom_configuration": json.dumps({
                "partialUpdate": True,
                "newProperty": "newValue"
            })
        },
    ),
])
@pytest.mark.parametrize("data_source", [None, f"nsu=test;i={randint(1, 999)}"])
@pytest.mark.parametrize("default_topic", [None, "/factory/mgmt/operations", ""])
@pytest.mark.parametrize("default_timeout", [None, 5000, 0])
def test_update_namespace_asset_management_group(
    mocked_cmd,
    mocked_responses: responses,
    asset_type: str,
    command_func,
    mgmt_params: dict,
    data_source: Optional[str],
    default_topic: Optional[str],
    default_timeout: Optional[int],
    mocked_check_cluster_connectivity,
    mocked_get_namespace_for_instance
):
    asset_name = f"test{asset_type.title()}Asset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"
    group_name = f"test{asset_type.title()}Group{generate_random_string(5)}"

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

    initial_management_group = generate_management_group(
        group_name=group_name,
        asset_type=asset_type
    )

    # Create other management groups to ensure we only update the target one
    other_groups = [
        generate_management_group(asset_type=asset_type),
        generate_management_group(asset_type=asset_type)
    ]

    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
    mocked_asset["properties"]["managementGroups"] = other_groups + [initial_management_group]

    # Mock GET request to get the asset
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        json=mocked_asset,
        status=200
    )
    add_device_get_call(
        mocked_responses,
        resource_group_name=resource_group_name,
        namespace_name=namespace_name,
        device_name=mocked_asset["properties"]["deviceRef"]["deviceName"],
        endpoint_name=mocked_asset["properties"]["deviceRef"]["endpointName"],
        endpoint_type=asset_type
    )

    # Build expected updated management group
    expected_group = deepcopy(initial_management_group)

    # Update data source if provided
    if data_source:
        expected_group["dataSource"] = data_source

    # Update default topic if provided
    if default_topic == "":
        # Remove the property if empty string
        expected_group.pop("defaultTopic", None)
    elif default_topic:
        expected_group["defaultTopic"] = default_topic

    # Update default timeout if provided
    if default_timeout is not None:
        expected_group["defaultTimeoutInSeconds"] = default_timeout

    # Update custom configuration for custom assets
    if "mgmt_custom_configuration" in mgmt_params:
        expected_group["managementGroupConfiguration"] = mgmt_params["mgmt_custom_configuration"]
    if "type_ref" in mgmt_params:
        expected_group["typeRef"] = mgmt_params["type_ref"]

    # Create expected asset after update
    expected_asset_payload = deepcopy(mocked_asset)
    for i, group in enumerate(expected_asset_payload["properties"]["managementGroups"]):
        if group["name"] == group_name:
            expected_asset_payload["properties"]["managementGroups"][i] = expected_group
            break

    # Mock PATCH request
    mocked_responses.add(
        method=responses.PATCH,
        url=get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        status=200
    )

    # Mock final GET request to return updated asset
    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        ),
        json=expected_asset_payload,
        status=200,
        content_type="application/json",
    )

    # Execute the command
    result = command_func(
        cmd=mocked_cmd,
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        wait_sec=0,
        data_source=data_source,
        default_topic=default_topic,
        default_timeout=default_timeout,
        **mgmt_params
    )

    # Verify the result
    assert result == expected_group

    # Verify API calls were made correctly
    expected_calls = 4  # device GET, asset GET, asset PATCH, asset GET
    assert len(mocked_responses.calls) == expected_calls
    assert mocked_responses.calls[0].request.method == "GET"  # device
    assert mocked_responses.calls[1].request.method == "GET"  # asset
    assert mocked_responses.calls[2].request.method == "PATCH"  # asset update
    assert mocked_responses.calls[3].request.method == "GET"  # asset

    # Verify the PATCH request body contains the expected management group structure
    patch_body = json.loads(mocked_responses.calls[2].request.body)
    assert "managementGroups" in patch_body["properties"]
    management_groups = patch_body["properties"]["managementGroups"]

    # Find our updated management group in the list
    updated_group = next((g for g in management_groups if g["name"] == group_name), None)
    assert updated_group is not None, "Updated management group not found in the list of management groups"

    # Verify management group properties were updated correctly
    assert updated_group["name"] == group_name
    assert updated_group["actions"] == initial_management_group["actions"]  # Actions should remain unchanged

    assert updated_group.get("typeRef") == expected_group.get("typeRef")
    assert updated_group.get("dataSource") == expected_group.get("dataSource")
    assert updated_group.get("defaultTopic") == expected_group.get("defaultTopic")
    assert updated_group.get("defaultTimeoutInSeconds") == expected_group.get("defaultTimeoutInSeconds")
    assert updated_group.get("managementGroupConfiguration") == expected_group.get("managementGroupConfiguration")

    # Verify other management groups were not affected
    other_group_names = [g["name"] for g in management_groups if g["name"] != group_name]
    expected_other_names = [g["name"] for g in other_groups]
    assert set(other_group_names) == set(expected_other_names)

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


# Add these test functions at the end of the file (after the last existing test function)
@pytest.mark.parametrize("topic, action_type, timeout", [
    # Common requirement combinations
    (None, None, None),  # Minimal parameters
    ("/contoso/mgmt/actions", "Call", 5000),  # Full common parameters
    ("/factory/commands", "Execute", 10000),  # Different values
    ("", "Call", 0),  # Empty topic, zero timeout
])
@pytest.mark.parametrize("asset_type, command_func, config_params", [
    # Custom asset management group action with custom configuration
    (
        "custom",
        add_namespace_custom_asset_management_group_action,
        {
            "custom_configuration": json.dumps({"method": "execute", "parameters": {"param1": "value1"}}),
            "type_ref": f"custom.management{randint(0, 1000)}"
        }
    ),
    # Custom asset management group action without custom configuration
    (
        "custom",
        add_namespace_custom_asset_management_group_action,
        {}
    ),
    # OPCUA asset management group action
    (
        "opcua",
        add_namespace_opcua_asset_management_group_action,
        {}
    ),
])
@pytest.mark.parametrize("has_actions, replace", [
    (False, False),  # No previous actions, no replace
    (True, False),   # Has previous actions, no replace
    (True, True)     # Has previous actions, with replace
])
def test_add_namespace_asset_management_group_action(
    mocked_cmd,
    mocked_responses: responses,
    topic: Optional[str],
    action_type: Optional[str],
    timeout: Optional[int],
    asset_type: str,
    command_func,
    config_params: dict,
    has_actions: bool,
    replace: bool,
    mocked_check_cluster_connectivity,
    mocked_get_namespace_for_instance
):
    # Setup test variables
    asset_name = f"test{asset_type.title()}Asset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"
    group_name = f"test{asset_type.title()}Group{generate_random_string(5)}"
    action_name = f"testAction{generate_random_string(5)}"
    target_uri = f"ns=2;s=Action{randint(1, 1000)}"

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

    # Generate mock asset with a management group
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    # Create the management group within the asset
    management_group = generate_management_group(
        group_name=group_name,
        asset_type=asset_type,
        num_actions=randint(1, 3) if has_actions else 0
    )

    # Add action to replace if replace is True
    if replace:
        management_group["actions"].append({
            "name": action_name,
            "targetUri": f"ns=2;s=OldAction{randint(1, 1000)}",
            "topic": f"/old/topic/{action_name}",
            "timeout": randint(1000, 2000),
            "actionType": "OldType"
        })

    # Add the management group to the asset properties
    mocked_asset["properties"]["managementGroups"] = [management_group]

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

    # Create the expected action
    expected_action = {
        "name": action_name,
        "targetUri": target_uri,
        "topic": topic,
        "actionType": action_type,
        "timeoutInSeconds": timeout,
        "typeRef": config_params.get("type_ref")
    }

    # Add configuration based on asset type
    if asset_type == "custom" and "custom_configuration" in config_params:
        expected_action["actionConfiguration"] = config_params["custom_configuration"]

    # Create the updated asset for the mock response
    updated_asset = deepcopy(mocked_asset)
    updated_management_group = updated_asset["properties"]["managementGroups"][0]
    updated_management_group["actions"] = updated_management_group.get("actions", [])

    if replace:
        # If replacing, remove the existing action with the same name
        updated_management_group["actions"] = [
            action for action in updated_management_group["actions"]
            if action["name"] != action_name
        ]

    updated_management_group["actions"].append(expected_action)

    # Mock PATCH request
    mocked_responses.add(
        responses.PATCH,
        get_namespace_asset_mgmt_uri(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            asset_name=asset_name
        ),
        status=200
    )

    mocked_responses.add(
        method=responses.GET,
        url=get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        ),
        json=updated_asset,
        status=200,
        content_type="application/json",
    )

    # Execute the command
    result = command_func(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        asset_name=asset_name,
        group_name=group_name,
        action_name=action_name,
        target_uri=target_uri,
        topic=topic,
        action_type=action_type,
        timeout=timeout,
        replace=replace,
        wait_sec=0,
        **config_params
    )

    # Result should be the updated management group
    assert isinstance(result, list)
    assert result == updated_asset["properties"]["managementGroups"][0]["actions"]

    # Verify API calls were made correctly
    assert len(mocked_responses.calls) == 4  # GET device + GET asset + PATCH asset + GET asset
    assert mocked_responses.calls[0].request.method == "GET"  # Device GET call
    assert mocked_responses.calls[1].request.method == "GET"  # Asset GET call
    assert mocked_responses.calls[2].request.method == "PATCH"  # Asset PATCH call
    assert mocked_responses.calls[3].request.method == "GET"  # Asset GET call

    # Verify the PATCH request payload contains the expected action
    patch_body = json.loads(mocked_responses.calls[2].request.body)
    patch_management_group = patch_body["properties"]["managementGroups"][0]
    assert len(patch_management_group["actions"]) == len(updated_management_group["actions"])

    # Check the added action
    patched_action = next(
        (action for action in patch_management_group["actions"] if action["name"] == action_name),
        None
    )
    assert patched_action is not None, f"Action '{action_name}' not found in PATCH request"
    assert patched_action["targetUri"] == target_uri
    assert patched_action["topic"] == topic
    assert patched_action["actionType"] == action_type
    assert patched_action["timeoutInSeconds"] == timeout
    assert patched_action.get("typeRef") == expected_action.get("typeRef")

    if "actionConfiguration" in expected_action:
        assert patched_action["actionConfiguration"] == expected_action["actionConfiguration"]

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


@pytest.mark.parametrize("num_actions", [0, 1, 3])
def test_list_namespace_asset_management_group_actions(
    mocked_cmd,
    mocked_responses: responses,
    num_actions: int,
    mocked_get_namespace_for_instance
):
    asset_name = "testAsset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"
    group_name = "testGroup"

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

    # Generate management group with specified number of actions
    management_group = generate_management_group(
        group_name=group_name,
        asset_type="custom",
        num_actions=num_actions
    )

    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
    mocked_asset["properties"]["managementGroups"] = [management_group]

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

    # Test list management group actions
    actions = list_namespace_asset_management_group_actions(
        cmd=mocked_cmd,
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name
    )

    assert len(actions) == num_actions
    expected_action_map = {action["name"]: action for action in management_group["actions"]}
    for action in actions:
        assert action["name"] in expected_action_map
        expected_action = expected_action_map[action["name"]]
        assert action["targetUri"] == expected_action["targetUri"]
        assert action["topic"] == expected_action["topic"]
        assert action["timeout"] == expected_action["timeout"]
        assert action["actionType"] == expected_action["actionType"]
        if "actionConfiguration" in expected_action:
            assert action["actionConfiguration"] == expected_action["actionConfiguration"]

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


@pytest.mark.parametrize("actions_present", [True, False])
@pytest.mark.parametrize("action_deleted", [True, False])
def test_remove_namespace_asset_management_group_action(
    mocked_cmd,
    mocked_responses: responses,
    actions_present: bool,
    action_deleted: bool,
    mocked_check_cluster_connectivity,
    mocked_get_namespace_for_instance
):
    asset_name = "testAsset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"
    group_name = "testGroup"
    action_name = "testAction"

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    # Generate management group with multiple actions
    management_group = generate_management_group(
        group_name=group_name,
        asset_type="custom",
        num_actions=3 if actions_present else 0
    )

    expected_actions = deepcopy(management_group["actions"])
    if action_deleted:
        # Remove the action to be deleted from the expected actions
        management_group["actions"].append(generate_management_group_action(action_name=action_name))

    mocked_asset["properties"]["managementGroups"] = [management_group]

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

    if action_deleted:
        # Mock the PATCH request to update the asset
        updated_asset = deepcopy(mocked_asset)
        updated_management_group = updated_asset["properties"]["managementGroups"][0]
        updated_management_group["actions"] = expected_actions

        mocked_responses.add(
            responses.PATCH,
            get_namespace_asset_mgmt_uri(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name
            ),
            status=200
        )
        mocked_responses.add(
            responses.GET,
            get_namespace_asset_mgmt_uri(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                asset_name=asset_name
            ),
            json=updated_asset,
            status=200
        )

    # Test remove management group action
    result = remove_namespace_asset_management_group_action(
        cmd=mocked_cmd,
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        group_name=group_name,
        action_name=action_name,
        wait_sec=0
    )

    assert len(result) == len(expected_actions)

    assert len(mocked_responses.calls) == (3 if action_deleted else 1)
    assert mocked_responses.calls[0].request.method == "GET"

    if action_deleted:
        assert mocked_responses.calls[1].request.method == "PATCH"
        assert mocked_responses.calls[2].request.method == "GET"

        # Verify the PATCH request body
        patch_body = json.loads(mocked_responses.calls[1].request.body)
        patch_groups = patch_body["properties"]["managementGroups"]
        assert len(patch_groups) == 1

        # Check that the datapoints in the patch request match the expected datapoints
        patched_actions = patch_groups[0].get("actions", [])

        # The datapoint that was supposed to be deleted should not be in the request
        for action in patched_actions:
            assert action["name"] != action_name

        # All expected datapoints should be present
        assert len(patched_actions) == len(expected_actions)
        for action in expected_actions:
            assert action in patched_actions

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


@pytest.mark.parametrize("asset_type, export_func", [
    ("custom", "export_namespace_custom_asset_management_group"),
    ("opcua", "export_namespace_opcua_asset_management_group"),
    ("onvif", "export_namespace_onvif_asset_management_group"),
])
@pytest.mark.parametrize("extension", ["json", "yaml"])
def test_export_namespace_asset_management_groups(
    mocked_cmd,
    mocked_responses: responses,
    asset_type: str,
    export_func: str,
    extension: str,
    mocked_get_namespace_for_instance,
    tmp_path
):
    """Test management group export for all asset types."""
    from azext_edge.edge import commands_namespaces

    asset_name = "testAsset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"
    output_dir = str(tmp_path)

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

    # Create mock management groups
    mgmt_groups = [
        generate_management_group(f"mgmtGroup{i}", asset_type=asset_type, num_actions=2)
        for i in range(3)
    ]

    # Mock the asset GET call
    asset_record = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name
    )
    asset_record["properties"]["managementGroups"] = mgmt_groups

    mocked_responses.add(
        responses.GET,
        get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        ),
        json=asset_record,
        status=200
    )

    # Call export function
    func = getattr(commands_namespaces, export_func)
    result = func(
        cmd=mocked_cmd,
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        extension=extension,
        output_dir=output_dir,
        replace=False
    )

    # Verify result
    assert "file_path" in result
    assert "management_group_count" in result
    assert result["management_group_count"] == 3
    assert extension in result["file_path"]
    assert asset_name in result["file_path"]


@pytest.mark.parametrize("asset_type, import_func", [
    ("custom", "import_namespace_custom_asset_management_group"),
    ("opcua", "import_namespace_opcua_asset_management_group"),
    ("onvif", "import_namespace_onvif_asset_management_group"),
])
@pytest.mark.parametrize("replace", [True, False])
def test_import_namespace_asset_management_groups(
    mocked_cmd,
    mocked_responses: responses,
    asset_type: str,
    import_func: str,
    replace: bool,
    mocked_check_cluster_connectivity,
    mocked_get_namespace_for_instance,
    mocked_connector_metadata_validator,
    tmp_path
):
    """Test management group import with merge and replace modes."""
    from azext_edge.edge import commands_namespaces
    import json as json_module

    asset_name = "testAsset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

    # Create existing management groups
    existing_mgmt_groups = [
        generate_management_group(f"existingGroup{i}", asset_type=asset_type, num_actions=1)
        for i in range(2)
    ]
    existing_group_names = [mg["name"] for mg in existing_mgmt_groups]

    # Create management groups to import (one overlapping, one new)
    mgmt_groups_to_import = [
        generate_management_group(existing_group_names[0], asset_type=asset_type, num_actions=1),  # Overlapping
        generate_management_group("newGroup", asset_type=asset_type, num_actions=1),  # New
    ]

    # Create import file
    import_file = tmp_path / "mgmt_groups_import.json"
    with open(import_file, 'w', encoding='utf-8') as f:
        json_module.dump(mgmt_groups_to_import, f)

    # Mock the asset GET call
    asset_record = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name
    )
    asset_record["properties"]["managementGroups"] = existing_mgmt_groups

    mocked_responses.add(
        responses.GET,
        get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        ),
        json=asset_record,
        status=200
    )

    # Mock the PATCH call
    def check_patch_request(request):
        patch_body = json_module.loads(request.body)
        imported_groups = patch_body["properties"]["managementGroups"]

        # Both modes should have 3 groups (2 existing + 1 new, with overlap handled)
        assert len(imported_groups) == 3
        if replace:
            # Replace mode: overlapping group is overwritten
            updated_mg = next(
                (mg for mg in imported_groups if mg["name"] == existing_group_names[0]), None
            )
            assert updated_mg is not None
            assert updated_mg["dataSource"] == mgmt_groups_to_import[0]["dataSource"]
        # Both modes: second existing preserved, new group added
        assert any(mg["name"] == existing_group_names[1] for mg in imported_groups)
        assert any(mg["name"] == "newGroup" for mg in imported_groups)

        return (200, {}, json_module.dumps(asset_record))

    mocked_responses.add_callback(
        responses.PATCH,
        get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        ),
        callback=check_patch_request,
        content_type="application/json"
    )

    # Mock the final GET call
    asset_record["properties"]["managementGroups"] = mgmt_groups_to_import
    mocked_responses.add(
        responses.GET,
        get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        ),
        json=asset_record,
        status=200
    )

    # Call import function
    func = getattr(commands_namespaces, import_func)
    result = func(
        cmd=mocked_cmd,
        asset_name=asset_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        file_path=str(import_file),
        replace=replace
    )

    # Verify result is a list of management groups
    assert isinstance(result, list)
    assert len(result) > 0


@pytest.mark.parametrize("asset_type, export_func", [
    ("custom", "export_namespace_custom_asset_management_group_action"),
    ("opcua", "export_namespace_opcua_asset_management_group_action"),
])
@pytest.mark.parametrize("extension", ["json", "yaml"])
def test_export_namespace_asset_management_group_actions(
    mocked_cmd,
    mocked_responses: responses,
    asset_type: str,
    export_func: str,
    extension: str,
    mocked_get_namespace_for_instance,
    tmp_path
):
    """Test management group action export for custom and opcua asset types."""
    from azext_edge.edge import commands_namespaces

    asset_name = "testAsset"
    group_name = "testGroup"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"
    output_dir = str(tmp_path)

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

    # Create mock management group with actions
    mgmt_group = generate_management_group(group_name, asset_type=asset_type, num_actions=5)

    # Mock the asset GET call
    asset_record = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name
    )
    asset_record["properties"]["managementGroups"] = [mgmt_group]

    mocked_responses.add(
        responses.GET,
        get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        ),
        json=asset_record,
        status=200
    )

    # Call export function
    func = getattr(commands_namespaces, export_func)
    result = func(
        cmd=mocked_cmd,
        asset_name=asset_name,
        group_name=group_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        extension=extension,
        output_dir=output_dir,
        replace=False
    )

    # Verify result
    assert "file_path" in result
    assert "action_count" in result
    assert result["action_count"] == 5
    assert extension in result["file_path"]
    assert group_name in result["file_path"]


@pytest.mark.parametrize("asset_type, import_func", [
    ("custom", "import_namespace_custom_asset_management_group_action"),
    ("opcua", "import_namespace_opcua_asset_management_group_action"),
])
@pytest.mark.parametrize("replace", [True, False])
def test_import_namespace_asset_management_group_actions(
    mocked_cmd,
    mocked_responses: responses,
    asset_type: str,
    import_func: str,
    replace: bool,
    mocked_check_cluster_connectivity,
    mocked_get_namespace_for_instance,
    mocked_connector_metadata_validator,
    tmp_path
):
    """Test management group action import with merge and replace modes."""
    from azext_edge.edge import commands_namespaces
    import json as json_module

    asset_name = "testAsset"
    group_name = "testGroup"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource["name"]
    resource_group_name = namespace_resource["resource_group"]

    # Create existing management group with actions
    existing_mgmt_group = generate_management_group(group_name, asset_type=asset_type, num_actions=2)
    existing_action_names = [a["name"] for a in existing_mgmt_group["actions"]]

    # Create actions to import (one overlapping, one new)
    actions_to_import = [
        {
            "name": existing_action_names[0],  # Overlapping
            "targetUri": "ns=2;s=UpdatedAction1",
            "actionType": "Call",
            "timeout": 3000
        },
        {
            "name": "newAction",  # New
            "targetUri": "ns=2;s=NewAction",
            "actionType": "Call",
            "timeout": 2000
        }
    ]

    # Create import file
    import_file = tmp_path / "actions_import.json"
    with open(import_file, 'w', encoding='utf-8') as f:
        json_module.dump(actions_to_import, f)

    # Mock the asset GET call
    asset_record = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name
    )
    asset_record["properties"]["managementGroups"] = [existing_mgmt_group]

    mocked_responses.add(
        responses.GET,
        get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        ),
        json=asset_record,
        status=200
    )

    # Mock the PATCH call
    def check_patch_request(request):
        patch_body = json_module.loads(request.body)
        patched_groups = patch_body["properties"]["managementGroups"]

        # Find the group
        patched_group = next((g for g in patched_groups if g["name"] == group_name), None)
        assert patched_group is not None

        patched_actions = patched_group["actions"]

        # Verify action merge/replace behavior
        if replace:
            # Replace mode: merge with overwrite - all actions present, matching ones updated
            assert len(patched_actions) == 3  # 2 existing + 1 new
            updated_a = next((a for a in patched_actions if a["name"] == actions_to_import[0]["name"]), None)
            assert updated_a is not None
            assert updated_a["targetUri"] == "ns=2;s=UpdatedAction1"
            assert any(a["name"] == existing_action_names[1] for a in patched_actions)
            assert any(a["name"] == "newAction" for a in patched_actions)
        else:
            # Merge mode: all actions present, duplicate warning logged
            assert len(patched_actions) == 3
            assert any(a["name"] == "newAction" for a in patched_actions)

        return (200, {}, json_module.dumps(asset_record))

    mocked_responses.add_callback(
        responses.PATCH,
        get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        ),
        callback=check_patch_request,
        content_type="application/json"
    )

    # Mock the final GET call
    mocked_responses.add(
        responses.GET,
        get_namespace_asset_mgmt_uri(
            asset_name=asset_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name
        ),
        json=asset_record,
        status=200
    )

    # Call import function
    func = getattr(commands_namespaces, import_func)
    result = func(
        cmd=mocked_cmd,
        asset_name=asset_name,
        group_name=group_name,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        file_path=str(import_file),
        replace=replace
    )

    # Verify result is a list of actions
    assert isinstance(result, list)
    assert len(result) > 0
