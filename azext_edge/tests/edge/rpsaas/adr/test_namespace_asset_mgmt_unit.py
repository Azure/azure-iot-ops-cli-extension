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
from azext_edge.edge.commands_namespaces import (
    list_namespace_asset_management_groups,
    show_namespace_asset_management_group,
    remove_namespace_asset_management_group,
)

from .test_namespace_assets_unit import (
    get_namespace_asset_mgmt_uri, get_namespace_asset_record
)
from ....generators import generate_random_string


def generate_management_group(
    group_name: Optional[str] = None,
    asset_type: str = "custom"
) -> dict:
    """Generate a mock management group with the specified name and type."""
    group_name = group_name or f"group{generate_random_string(12)}"

    if asset_type == "custom":
        # Generate custom management group configuration
        management_group = {
            "name": group_name,
            "defaultTopic": f"/contoso/mgmt/{group_name}",
            "defaultTimeout": randint(1000, 10000),
            "managementGroupConfiguration": json.dumps({
                "customProperty": f"value{randint(1, 100)}",
                "groupType": "management-ops"
            }),
            "actions": [
                {
                    "name": f"action{randint(1, 100)}",
                    "targetUri": f"ns=2;s=Action{randint(1, 100)}",
                    "topic": f"/contoso/mgmt/{group_name}/action",
                    "timeout": randint(500, 5000),
                    "actionType": "method",
                    "actionConfiguration": json.dumps({
                        "method": "execute",
                        "parameters": {"param1": "value1"}
                    })
                }
            ]
        }
    else:
        # Generate OPC UA/ONVIF management group configuration
        management_group = {
            "name": group_name,
            "defaultTopic": f"/contoso/mgmt/{group_name}",
            "defaultTimeout": randint(1000, 10000),
            "actions": [
                {
                    "name": f"action{randint(1, 100)}",
                    "targetUri": f"ns=2;s=Action{randint(1, 100)}",
                    "topic": f"/contoso/mgmt/{group_name}/action",
                    "timeout": randint(500, 5000),
                    "actionType": "method"
                }
            ]
        }

    return management_group


@pytest.mark.parametrize("num_management_groups", [0, 1, 3])
def test_list_namespace_asset_management_groups(
    mocked_cmd, mocked_responses: responses, num_management_groups: int, mocked_get_namespace_for_instance
):
    asset_name = "testAsset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource.name
    resource_group_name = namespace_resource.resource_group

    expected_management_groups = [generate_management_group() for _ in range(num_management_groups)]
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    # ensure we can have the option of no managementGroups property
    if expected_management_groups:
        mocked_asset["properties"]["managementGroups"] = expected_management_groups

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
    expected_group_map = {group["name"]: group for group in expected_management_groups}
    for group in management_groups:
        assert group["name"] in expected_group_map
        expected_group = expected_group_map[group["name"]]
        assert group["defaultTopic"] == expected_group["defaultTopic"]
        assert group["defaultTimeout"] == expected_group["defaultTimeout"]
        assert group["actions"] == expected_group["actions"]
        if "managementGroupConfiguration" in expected_group:
            assert group["managementGroupConfiguration"] == expected_group["managementGroupConfiguration"]

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


def test_show_namespace_asset_management_group(mocked_cmd, mocked_responses: responses, mocked_get_namespace_for_instance):
    asset_name = "testAsset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"
    group_name = generate_random_string()

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource.name
    resource_group_name = namespace_resource.resource_group

    expected_management_group = generate_management_group(group_name=group_name, asset_type="custom")
    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
    mocked_asset["properties"]["managementGroups"] = [expected_management_group]

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
    assert management_group["name"] == expected_management_group["name"]
    assert management_group["defaultTopic"] == expected_management_group["defaultTopic"]
    assert management_group["defaultTimeout"] == expected_management_group["defaultTimeout"]
    assert management_group["actions"] == expected_management_group["actions"]
    assert management_group["managementGroupConfiguration"] == expected_management_group["managementGroupConfiguration"]

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )


@pytest.mark.parametrize("management_groups_present", [True, False])
@pytest.mark.parametrize("management_group_deleted", [True, False])
def test_remove_namespace_asset_management_group(
    mocked_cmd,
    mocked_responses: responses,
    management_groups_present: bool,
    management_group_deleted: bool,
    mocked_check_cluster_connectivity,
    mocked_get_namespace_for_instance
):
    asset_name = "testAsset"
    instance_name = "testInstance"
    instance_resource_group = "testInstanceResourceGroup"
    group_name = generate_random_string()

    # Get the namespace from the mocked function
    namespace_resource = mocked_get_namespace_for_instance.return_value
    namespace_name = namespace_resource.name
    resource_group_name = namespace_resource.resource_group

    mocked_asset = get_namespace_asset_record(
        asset_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )

    # make some other management groups, have the managementGroups prop there
    if management_groups_present:
        mocked_asset["properties"]["managementGroups"] = [
            generate_management_group(asset_type="custom"),
            generate_management_group(asset_type="opcua")
        ]
    expected_management_groups = deepcopy(mocked_asset["properties"].get("managementGroups", []))

    # the remove should not fail even if the management group is not there
    if management_group_deleted:
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

    if management_group_deleted:
        # Mock the PATCH request to update the asset
        updated_asset = deepcopy(mocked_asset)
        updated_asset["properties"]["managementGroups"] = expected_management_groups
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

    # Verify the number of expected API calls
    if management_group_deleted:
        expected_calls = 3  # asset GET, asset PATCH, asset GET
        assert len(mocked_responses.calls) == expected_calls
        assert mocked_responses.calls[0].request.method == "GET"  # asset
        assert mocked_responses.calls[1].request.method == "PATCH"  # asset update
        assert mocked_responses.calls[2].request.method == "GET"  # asset

        # Verify the result contains the expected management groups (without the deleted one)
        assert len(result_management_groups) == len(expected_management_groups)
        group_names = [group["name"] for group in result_management_groups]
        assert group_name not in group_names

        # Verify the PATCH request body contains the expected management group structure
        patch_body = json.loads(mocked_responses.calls[1].request.body)
        assert "managementGroups" in patch_body["properties"]
        mgmt_groups = patch_body["properties"]["managementGroups"]
        assert len(mgmt_groups) == len(expected_management_groups)

        # Verify the deleted management group is not in the PATCH request
        patch_group_names = [group["name"] for group in mgmt_groups]
        assert group_name not in patch_group_names
    else:
        # If no management group to delete, only one GET call should be made
        expected_calls = 1  # asset GET only
        assert len(mocked_responses.calls) == expected_calls
        assert mocked_responses.calls[0].request.method == "GET"  # asset

        # Verify the result contains the expected management groups (unchanged)
        assert len(result_management_groups) == len(expected_management_groups)

    # Verify that mocked_get_namespace_for_instance was called with correct parameters
    mocked_get_namespace_for_instance.assert_called_once_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group
    )
