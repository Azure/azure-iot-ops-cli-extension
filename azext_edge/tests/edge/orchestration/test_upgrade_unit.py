# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, List, Optional, Union
from unittest.mock import Mock
import pytest
import responses

from ...generators import generate_random_string, get_zeroed_subscription


KEY_TO_TYPE_MAP = {
    "secretSyncController": "microsoft.azure.secretstore",
    "edgeStorageAccelerator": "microsoft.arc.containerstorage",
    "openServiceMesh": "microsoft.openservicemesh",
    "platform": "microsoft.iotoperations.platform",
    "aio": "microsoft.iotoperations",
}


@pytest.fixture
def mocked_resource_map(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.upgrade.Instances",
    )
    yield patched().get_resource_map


@pytest.fixture
def mocked_logger(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.upgrade.logger",
    )
    yield patched


@pytest.fixture
def mocked_get_resource_client(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.upgrade.get_resource_client", autospec=True)
    yield patched


@pytest.fixture
def mocked_wait_for_terminal_states(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.upgrade.wait_for_terminal_states", autospec=True)
    yield patched


@pytest.fixture
def mocked_live_display(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.upgrade.Live")
    yield patched


@pytest.fixture
def spy_upgrade_manager(mocker):
    from azext_edge.edge.providers.orchestration.upgrade import UpgradeManager

    yield {
        "_check_extensions": mocker.spy(UpgradeManager, "_check_extensions"),
        "_get_resource_map": mocker.spy(UpgradeManager, "_get_resource_map"),
        "_render_display": mocker.spy(UpgradeManager, "_render_display"),
        "_stop_display": mocker.spy(UpgradeManager, "_stop_display"),
        "_process": mocker.spy(UpgradeManager, "_process"),
    }


def _generate_extensions(aio_version: str = "0.0.0"):
    resource_id = ""
    for _ in range(segments):
        resource_id = f"{resource_id}/{generate_random_string()}"

    resource = IoTOperationsResource(
        resource_id=resource_id,
        display_name=resource_id.split("/")[-1],
        api_version=generate_random_string(),
    )

    return resource


def _assemble_resource_map_mock(
    resource_map_mock: Mock,
    extensions: Optional[List[dict]],
    # custom_locations: Optional[List[dict]],
    # resources: Optional[List[dict]],
    # sync_rules: Optional[List[dict]],
):
    resource_map_mock().connected_cluster.extensions = extensions
    # resource_map_mock().custom_locations = custom_locations
    # resource_map_mock().get_resources.return_value = resources
    # resource_map_mock().get_resource_sync_rules.return_value = sync_rules


def _generate_extension(
    extension_type: str,
    current_version: str
):
    return {
        "properties": {
            "extensionType": extension_type,
            "version": current_version
        },
        "name": generate_random_string()
    }


def _generate_extensions(
    **extension_version_map
):
    extensions = []
    for key in KEY_TO_TYPE_MAP:
        version = extension_version_map.get(key, "0.0.0")
        extensions.append({
            "properties": {
                "extensionType": KEY_TO_TYPE_MAP[key],
                "version": version
            },
            "name": generate_random_string(),
            "key": key
        })
    return extensions


def _generate_versions(**versions):
    return [versions.get(key, "255.255.255") for key in KEY_TO_TYPE_MAP]


@pytest.mark.parametrize("no_progress", [False, True])
@pytest.mark.parametrize("require_instance_update", [False, True])
@pytest.mark.parametrize("extensions_to_update", [
    {
        "currentExtensions": _generate_extension(),
        "newVersions": _generate_versions
    }
])
@pytest.mark.parametrize("instance_name", [generate_random_string()])
def test_upgrade_lifecycle(
    mocker,
    mocked_cmd: Mock,
    mocked_responses: responses,
    mocked_resource_map: Mock,
    mocked_get_resource_client: Mock,
    mocked_wait_for_terminal_states: Mock,
    mocked_live_display: Mock,
    mocked_logger: Mock,
    spy_upgrade_manager: Dict[str, Mock],
    require_instance_update: bool,
    extensions_to_update: Optional[List[str]],
    instance_name: Optional[str],
    no_progress: Optional[bool]
):
    from azext_edge.edge.providers.orchestration.upgrade import upgrade_ops_resources
    # scenarios to test:
    # instance name vs cluster name used - later
    # sr resource id provided
    # extensions - all need updates, 3 need updates, none need updates
    # instance is m2 vs m3

    rg_name = generate_random_string()
    sr_resource_id = generate_random_string()

    if require_instance_update:
        mock_instance_record = {
            "extendedLocation": {
                "name": "/subscriptions/2bd4119a-4d8d-4090-9183-f9e516c21723/resourceGroups/viliteastus2euap/providers/Microsoft.ExtendedLocation/customLocations/location-fkbiv",
                "type": "CustomLocation"
            },
            "id": f"/subscriptions/{get_zeroed_subscription()}/resourcegroups/{rg_name}/providers/Microsoft.Kubernetes/connectedClusters/{instance_name}",
            "identity": {
                "type": "None"
            },
            "location": "eastus2euap",
            "name": instance_name,
            "properties": {
                "components": {
                "adr": {
                    "state": "Enabled"
                },
                "akri": {
                    "state": "Enabled"
                },
                "connectors": {
                    "state": "Enabled"
                },
                "dataflows": {
                    "state": "Enabled"
                },
                "schemaRegistry": {
                    "state": "Enabled"
                }
                },
                "provisioningState": "Succeeded",
                "schemaRegistryNamespace": generate_random_string(),
                "version": "0.7.31"
            },
            "resourceGroup": "viliteastus2euap",
            "systemData": {
                "createdAt": "2024-10-17T00:01:53.1974981Z",
                "createdBy": "vilit@microsoft.com",
                "createdByType": "User",
                "lastModifiedAt": "2024-10-17T00:03:32.0887568Z",
                "lastModifiedBy": "319f651f-7ddb-4fc6-9857-7aef9250bd05",
                "lastModifiedByType": "Application"
            },
            "type": "microsoft.iotoperations/instances"
        }
        mocked_responses.add(
            method=responses.GET,
            url=f"https://management.azure.com/subscriptions/{get_zeroed_subscription()}/resourcegroups/{rg_name}/providers/Microsoft.Kubernetes/connectedClusters/{instance_name}?api-version=2024-07-15-preview",
            json=mock_instance_record,
            status=200,
            content_type="application/json",
        )
    else:
        mocked_responses.add(
            method=responses.GET,
            url=f"https://management.azure.com/subscriptions/{get_zeroed_subscription()}/resourcegroups/{rg_name}/providers/Microsoft.Kubernetes/connectedClusters/{instance_name}?api-version=2024-07-15-preview",
            status=404,
            content_type="application/json",
        )

    _assemble_resource_map_mock(
        resource_map_mock=mocked_resource_map,
        extensions=expected_resources_map["extensions"],
        custom_locations=expected_resources_map["custom locations"],
        resources=expected_resources_map["resources"],
    )

    kwargs = {
        "cmd": mocked_cmd,
        "instance_name": instance_name,
        "resource_group_name": rg_name,
        "sr_resource_id": sr_resource_id,
        "confirm_yes": True,
        "no_progress": no_progress,
    }

    upgrade_ops_resources(**kwargs)

    expected_delete_calls: int = expected_resources_map["meta"].get("expected_delete_calls", 0)
    if not include_dependencies and expected_delete_calls > 0:
        expected_delete_calls = expected_delete_calls - 1

    spy_upgrade_manager["_display_resource_tree"].assert_called_once()
    spy_upgrade_manager["_process"].assert_called_once()

    if not any(
        [
            expected_resources_map["extensions"],
            expected_resources_map["custom locations"],
            expected_resources_map["resources"],
            expected_resources_map["resource sync rules"],
        ]
    ):
        assert mocked_logger.warning.call_args[0][0] == "Nothing to delete :)"
        spy_upgrade_manager["_delete_batch"].assert_not_called()
        return

    if expected_delete_calls > 0:
        spy_upgrade_manager["_render_display"].assert_called()
        spy_upgrade_manager["_stop_display"].assert_called_once()

    assert spy_upgrade_manager["_delete_batch"].call_count == expected_delete_calls
    assert mocked_live_display.call_count >= 1

    if kwargs["no_progress"]:
        mocked_live_display.assert_called_once_with(None, transient=False, refresh_per_second=8, auto_refresh=False)
