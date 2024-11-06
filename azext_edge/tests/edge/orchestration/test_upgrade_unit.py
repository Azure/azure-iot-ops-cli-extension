# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, List, Optional, OrderedDict
from unittest.mock import Mock
import pytest
from azure.cli.core.azclierror import (
    ArgumentUsageError,
    AzureResponseError,
)
from azure.core.exceptions import HttpResponseError

from ...generators import generate_random_string, get_zeroed_subscription

# Note this keeps the order
VAR_TO_TYPE_MAP = OrderedDict([
    ("platform", "microsoft.iotoperations.platform"),
    ("open_service_mesh", "microsoft.openservicemesh"),
    ("secret_store", "microsoft.azure.secretstore"),
    ("container_storage", "microsoft.arc.containerstorage"),
    ("iot_operations", "microsoft.iotoperations"),
])


@pytest.fixture
def mocked_instances(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.upgrade.Instances",
    )
    yield patched()


@pytest.fixture
def mocked_logger(mocker):
    yield mocker.patch(
        "azext_edge.edge.providers.orchestration.upgrade.logger",
    )


@pytest.fixture
def mocked_wait_for_terminal_state(mocker):
    yield mocker.patch("azext_edge.edge.providers.orchestration.upgrade.wait_for_terminal_state", autospec=True)


@pytest.fixture
def mocked_rich_print(mocker):
    yield mocker.patch("azext_edge.edge.providers.orchestration.upgrade.print")


@pytest.fixture
def mocked_live_display(mocker):
    yield mocker.patch("azext_edge.edge.providers.orchestration.upgrade.Live")


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
    # order doesnt matter here
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


def _generate_extensions(**extension_version_map) -> OrderedDict:
    # if nothing is provided, "min" is used
    # order is determined from the VAR_TO_TYPE_MAP - ensure order is kept
    extensions = OrderedDict()
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


def _generate_instance(instance_name: str, resource_group: str):
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
            "description": generate_random_string(),
            "provisioningState": "Succeeded",
            "version": "1.0.6",
            "schemaRegistryRef": {"resourceId": generate_random_string()}
        },
        "resourceGroup": resource_group,
        "systemData": {
            generate_random_string(): generate_random_string(),
            generate_random_string(): generate_random_string(),
        },
        "type": "microsoft.iotoperations/instances"
    }
    return mock_instance_record


def _generate_versions(**versions) -> dict:
    # if version not provided, "max" is used
    return {key: versions.get(key, "255.255.255") for key in VAR_TO_TYPE_MAP}


def _generate_trains(**trains) -> dict:
    # if train is not provided, "max" is used
    return {key: trains.get(key, "stable") for key in VAR_TO_TYPE_MAP}


@pytest.mark.parametrize("no_progress", [False, True])
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
    # update aio (version) + platform (train)
    (
        _generate_extensions(
            secret_store="1.10.0",
            container_storage="0.10.3-preview",
            open_service_mesh="0.9.1",
            platform="0.10.0",
            iot_operations="1.0.6",
        ),
        _generate_versions(
            secret_store="1.10.0",
            container_storage="0.10.3-preview",
            open_service_mesh="0.9.1",
            platform="0.10.0",
            iot_operations="1.2.0",
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
            iot_operations="1.0.6",
        ),
        _generate_versions(
            secret_store="1.10.0",
            container_storage="0.10.3",
            open_service_mesh="0.10.2",
            platform="0.10.0",
            iot_operations="1.0.9",
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
    (
        _generate_extensions(
            iot_operations="1.0.6",
        ),
        _generate_versions(),
        _generate_trains()
    )
])
def test_upgrade_lifecycle(
    mocker,
    mocked_cmd: Mock,
    mocked_instances: Mock,
    mocked_live_display: Mock,
    mocked_logger: Mock,
    mocked_rich_print: Mock,
    spy_upgrade_manager: Dict[str, Mock],
    current_extensions: List[dict],
    new_versions: List[dict],
    new_trains: List[dict],
    no_progress: Optional[bool]
):
    from azext_edge.edge.providers.orchestration.upgrade import upgrade_ops_resources

    rg_name = generate_random_string()
    instance_name = generate_random_string()

    # mock extensions in resource map and template info
    mocked_resource_map = mocked_instances.get_resource_map()
    mocked_resource_map.connected_cluster.extensions = list(current_extensions.values())
    extension_update_mock = mocked_resource_map.connected_cluster.clusters.extensions.update_cluster_extension
    _assemble_template_mock(mocker, new_versions=new_versions, new_trains=new_trains)
    instance_body = None
    # the get m2 instance call
    current_version = current_extensions["iot_operations"]["properties"]["version"]
    instance_body = _generate_instance(instance_name=instance_name, resource_group=rg_name)
    instance_body["properties"]["version"] = current_version
    mocked_instances.show.return_value = instance_body

    kwargs = {
        "cmd": mocked_cmd,
        "instance_name": instance_name,
        "resource_group_name": rg_name,
        "confirm_yes": True,
        "no_progress": no_progress,
    }

    upgrade_ops_resources(**kwargs)

    # extension update calls
    extensions_to_update = {}
    extension_update_calls = extension_update_mock.call_args_list
    call = 0
    try:
        from packaging import version
    except ImportError:
        pytest.fail("Import packaging failed.")
    for key, extension in current_extensions.items():
        if any([
            version.parse(extension["properties"]["version"]) < version.parse(new_versions[key]),
            extension["properties"]["releaseTrain"] != new_trains[key]
        ]):
            extensions_to_update[key] = extension
            # check the extension
            extension_call = extension_update_calls[call].kwargs
            assert extension_call["resource_group_name"] == rg_name
            assert extension_call["cluster_name"]
            assert extension_call["cluster_name"]
            payload = extension_call["update_payload"]
            assert payload["properties"]
            assert payload["properties"]["autoUpgradeMinorVersion"] == "false"
            assert payload["properties"]["releaseTrain"] == new_trains[key]
            assert payload["properties"]["version"] == new_versions[key]
            # calls should be ordered together
            call += 1

    assert len(extensions_to_update) == len(extension_update_calls)

    # overall upgrade call
    assert spy_upgrade_manager["_process"].called is bool(extension_update_calls)

    # make sure we tried to get the m3
    assert mocked_instances.show.call_count == (2 if extension_update_calls else 1)
    mocked_instances.iotops_mgmt_client.instance.begin_create_or_update.assert_not_called()

    # no progress check
    if no_progress:
        mocked_live_display.assert_called_once_with(None, transient=False, refresh_per_second=8, auto_refresh=False)
    assert mocked_rich_print.called == (not spy_upgrade_manager["_process"].called or not no_progress)


def test_upgrade_error(
    mocked_cmd: Mock,
    mocked_instances: Mock,
    mocked_live_display: Mock,
    mocked_logger: Mock,
    mocked_rich_print: Mock,
):
    from azext_edge.edge.providers.orchestration.upgrade import upgrade_ops_resources

    rg_name = generate_random_string()
    instance_name = generate_random_string()
    instance = _generate_instance(instance_name=instance_name, resource_group=rg_name)
    kwargs = {
        "cmd": mocked_cmd,
        "instance_name": instance_name,
        "resource_group_name": rg_name,
        "confirm_yes": True,
    }
    extensions = _generate_extensions()
    mocked_resource_map = mocked_instances.get_resource_map()
    mocked_resource_map.connected_cluster.extensions = list(extensions.values())
    mocked_instances.show.return_value = instance

    # slowly work backwards
    # some random extension has a hidden status error
    error_msg = generate_random_string()
    extensions["platform"]["properties"]["statuses"] = [{"code": "InstallationFailed", "message": error_msg}]
    extension_update_mock = mocked_resource_map.connected_cluster.clusters.extensions.update_cluster_extension
    extension_update_mock.return_value = extensions["platform"]
    with pytest.raises(AzureResponseError) as e:
        upgrade_ops_resources(**kwargs)
    assert error_msg in e.value.error_msg
    assert extensions["platform"]["name"] in e.value.error_msg

    # extension update fails
    error_msg = "extension update failed"
    extension_update_mock.side_effect = HttpResponseError(error_msg)
    with pytest.raises(HttpResponseError) as e:
        upgrade_ops_resources(**kwargs)
    assert error_msg in e.value.message

    # instance is an unreleased bug bash version
    instance["properties"]["version"] = "0.7.25"
    with pytest.raises(ArgumentUsageError):
        upgrade_ops_resources(**kwargs)

    # other instance get errors raise normally
    error_msg = "instance get failed"
    mocked_instances.show.side_effect = HttpResponseError(error_msg)
    with pytest.raises(HttpResponseError) as e:
        upgrade_ops_resources(**kwargs)
    assert error_msg in e.value.message

    # cannot get m2 or m3 because api spec validation
    mocked_instances.show.side_effect = HttpResponseError(
        "(HttpResponsePayloadAPISpecValidationFailed) instance get failed"
    )
    with pytest.raises(ArgumentUsageError):
        upgrade_ops_resources(**kwargs)
