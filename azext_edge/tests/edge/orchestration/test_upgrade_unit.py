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

# TODO: see if variable naming can be used for key
VAR_TO_TYPE_MAP = {
    "secret_store": "microsoft.azure.secretstore",
    "container_storage": "microsoft.arc.containerstorage",
    "open_service_mesh": "microsoft.openservicemesh",
    "platform": "microsoft.iotoperations.platform",
    "iot_operations": "microsoft.iotoperations",
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


# @pytest.fixture
# def mocked_get_resource_client(mocker):
#     patched = mocker.patch("azext_edge.edge.providers.orchestration.upgrade.get_resource_client", autospec=True)
#     yield patched


@pytest.fixture
def mocked_wait_for_terminal_state(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.upgrade.wait_for_terminal_state", autospec=True)
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


def _assemble_template_mock(mocker, new_versions, new_trains):
    variable_to_key_map = {
        "secret_store": "secretStore",
        "container_storage": "containerStorage",
        "open_service_mesh": "openServiceMesh",
        "platform": "platform",
        "iot_operations": "iotOperations",
    }
    versions = {variable_to_key_map[v]: new_versions[v] for v in variable_to_key_map}
    trains = {variable_to_key_map[v]: new_trains[v] for v in variable_to_key_map}
    inst_temp_patch = mocker.patch("azext_edge.edge.providers.orchestration.template.M3_INSTANCE_TEMPLATE")
    inst_temp_patch.content = {
        "variables": {
            "VERSIONS": {"iotOperations": versions.pop("iotOperations")},
            "TRAINS": {"iotOperations": trains.pop("iotOperations")}
        }
    }

    enable_temp_patch = mocker.patch("azext_edge.edge.providers.orchestration.template.M3_ENABLEMENT_TEMPLATE")
    enable_temp_patch.content = {
        "variables": {
            "VERSIONS": versions,
            "TRAINS": trains
        }
    }


def _generate_extensions(**extension_version_map) -> dict:
    # if nothing is provided, "min" is used
    extensions = {}
    for key in VAR_TO_TYPE_MAP:
        version = extension_version_map.get(key, "0.0.0")
        extensions[key] = {
            "properties": {
                "extensionType": VAR_TO_TYPE_MAP[key],
                "version": version,
                "releaseTrain": "preview",
                "configurationSettings": {
                    "schemaRegistry.values.resourceId": generate_random_string()
                }
            },
            "name": generate_random_string(),
        }
    return extensions


def _generate_instance(instance_name: str, resource_group: str, m3: bool = False):
    mock_instance_record = {
        "extendedLocation": {
            "name": generate_random_string(),
            "type": "CustomLocation"
        },
        "id": f"/subscriptions/{get_zeroed_subscription()}/resourcegroups/{resource_group}"
            f"/providers/Microsoft.Kubernetes/connectedClusters/{instance_name}",
        "identity": {"type": "None"},
        "location": "eastus2",
        "name": instance_name,
        "properties": {
            "provisioningState": "Succeeded",
            "version": "0.7.31"
        },
        "resourceGroup": resource_group,
        "systemData": {
            generate_random_string(): generate_random_string(),
            generate_random_string(): generate_random_string(),
        },
        "type": "microsoft.iotoperations/instances"
    }
    if m3:
        mock_instance_record["properties"]["schemaRegistryRef"] = {"resource_id": generate_random_string()}
    else:
        mock_instance_record["properties"]["schemaRegistryName"] = generate_random_string()
        mock_instance_record["properties"]["components"] = {
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
        }
    return mock_instance_record

def _generate_versions(**versions) -> dict:
    # if version not provided, "max" is used
    return {key: versions.get(key, "255.255.255") for key in VAR_TO_TYPE_MAP}


def _generate_trains(**trains) -> dict:
    # if train is not provided, "max" is used
    return {key: trains.get(key, "stable") for key in VAR_TO_TYPE_MAP}


@pytest.mark.parametrize("no_progress", [False, True])
@pytest.mark.parametrize("require_instance_update", [False, True])
@pytest.mark.parametrize("current_extensions, new_versions, new_trains", [
    # update none
    (
        _generate_extensions(
            secret_store="255.255.255",
            container_storage="255.255.255",
            open_service_mesh="255.255.255",
            platform="255.255.255",
            iot_operations="255.255.255",
        ),
        _generate_versions(),
        _generate_trains(
            secret_store="preview",
            container_storage="preview",
            open_service_mesh="preview",
            platform="preview",
            iot_operations="preview",
        )
    ),
    # update aio (new train + realistic versions)
    (
        _generate_extensions(
            secret_store="1.10.0",
            container_storage="0.10.3-preview",
            open_service_mesh="0.9.1",
            platform="0.10.0",
            iot_operations="0.8.16",
        ),
        _generate_versions(
            secret_store="1.10.0",
            container_storage="0.10.3-preview",
            open_service_mesh="0.9.1",
            platform="0.10.0",
            iot_operations="0.8.16",
        ),
        _generate_trains(
            secret_store="preview",
            container_storage="preview",
            open_service_mesh="preview",
            iot_operations="preview",
        )
    ),
    # update aio, openmesh, container store (new versions)
    (
        _generate_extensions(
            secret_store="1.10.0",
            container_storage="0.10.3-preview",
            open_service_mesh="0.9.1",
            platform="0.10.0",
            iot_operations="0.7.31",
        ),
        _generate_versions(
            secret_store="1.10.0",
            container_storage="0.10.3",  # not sure if this will work
            open_service_mesh="0.10.2",
            platform="0.10.0",
            iot_operations="0.8.16",
        ),
        _generate_trains(
            secret_store="preview",
            container_storage="preview",
            open_service_mesh="preview",
            platform="preview",
            iot_operations="preview",
        )
    ),
    # update all
    (_generate_extensions(), _generate_versions(), _generate_trains())
])
@pytest.mark.parametrize("sr_resource_id", [None, generate_random_string()])
def test_upgrade_lifecycle(
    mocker,
    mocked_cmd: Mock,
    mocked_responses: responses,
    mocked_resource_map: Mock,
    # mocked_get_resource_client: Mock,
    mocked_wait_for_terminal_state: Mock,
    mocked_live_display: Mock,
    mocked_logger: Mock,
    spy_upgrade_manager: Dict[str, Mock],
    require_instance_update: bool,
    current_extensions: List[dict],
    new_versions: List[dict],
    new_trains: List[dict],
    sr_resource_id: Optional[str],
    no_progress: Optional[bool]
):
    from azext_edge.edge.providers.orchestration.upgrade import upgrade_ops_resources
    # scenarios to test:
    # instance name vs cluster name used - later
    # sr resource id provided vs extension fetched
    # extensions - all need updates, 3 need updates, none need updates
    # instance is m2 vs m3

    rg_name = generate_random_string()
    instance_name = generate_random_string()

    # mock extensions in resource map and template info
    mocked_resource_map().connected_cluster.extensions = list(current_extensions.values())
    _assemble_template_mock(mocker, new_versions=new_versions, new_trains=new_trains)

    # the get m2 instance call
    import pdb; pdb.set_trace()
    if require_instance_update:
        # note the resource client adds an extra / before instances for the parent path. The api doesnt care
        mocked_responses.add(
            method=responses.GET,
            url=f"https://management.azure.com/subscriptions/{get_zeroed_subscription()}/resourcegroups/{rg_name}"
            f"/providers/Microsoft.IoTOperations//instances/{instance_name}?api-version=2024-08-15-preview",
            json=_generate_instance(instance_name=instance_name, resource_group=rg_name),
            status=200,
            content_type="application/json",
        )
    else:
        mocked_responses.add(
            method=responses.GET,
            url=f"https://management.azure.com/subscriptions/{get_zeroed_subscription()}/resourcegroups/{rg_name}"
            f"/providers/Microsoft.IoTOperations//instances/{instance_name}?api-version=2024-08-15-preview",
            status=404,
            content_type="application/json",
        )
        mocked_responses.add(
            method=responses.GET,
            url=f"https://management.azure.com/subscriptions/{get_zeroed_subscription()}/resourcegroups/{rg_name}"
            f"/providers/Microsoft.IoTOperations/instances/{instance_name}?api-version=2024-09-15-preview",
            json=_generate_instance(instance_name=instance_name, resource_group=rg_name, m3=True),
            status=200,
            content_type="application/json",
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
    import pdb; pdb.set_trace()
    assert mocked_responses.calls

    extensions_to_update = {}
    for key, extension in current_extensions.items():
        if extension["properties"]["version"] != new_versions[key] or extension["properties"]["releaseTrain"] != new_trains[key]:
            extensions_to_update[key] = extension

    assert spy_upgrade_manager["_process"].called is bool(extensions_to_update)

    # expected_delete_calls: int = expected_resources_map["meta"].get("expected_delete_calls", 0)
    # if not include_dependencies and expected_delete_calls > 0:
    #     expected_delete_calls = expected_delete_calls - 1

    # spy_upgrade_manager["_display_resource_tree"].assert_called_once()
    # spy_upgrade_manager["_process"].assert_called_once()

    # if not any(
    #     [
    #         expected_resources_map["extensions"],
    #         expected_resources_map["custom locations"],
    #         expected_resources_map["resources"],
    #         expected_resources_map["resource sync rules"],
    #     ]
    # ):
    #     assert mocked_logger.warning.call_args[0][0] == "Nothing to delete :)"
    #     spy_upgrade_manager["_delete_batch"].assert_not_called()
    #     return

    # if expected_delete_calls > 0:
    #     spy_upgrade_manager["_render_display"].assert_called()
    #     spy_upgrade_manager["_stop_display"].assert_called_once()

    # assert spy_upgrade_manager["_delete_batch"].call_count == expected_delete_calls
    # assert mocked_live_display.call_count >= 1

    if kwargs["no_progress"]:
        mocked_live_display.assert_called_once_with(None, transient=False, refresh_per_second=8, auto_refresh=False)
