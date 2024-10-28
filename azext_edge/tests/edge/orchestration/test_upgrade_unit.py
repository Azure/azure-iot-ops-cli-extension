# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from packaging import version
from typing import Dict, List, Optional, OrderedDict
from unittest.mock import Mock
import pytest
import responses
from azure.cli.core.azclierror import (
    ArgumentUsageError,
    AzureResponseError,
    RequiredArgumentMissingError,
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
            "description": generate_random_string(),
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
        mock_instance_record["properties"]["schemaRegistryNamespace"] = generate_random_string()
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
# @pytest.mark.parametrize("require_instance_update", [False, True])
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
            iot_operations="0.8.16",
        ),
        _generate_versions(
            secret_store="1.10.0",
            container_storage="0.10.3-preview",
            open_service_mesh="0.9.1",
            platform="0.10.0",
            iot_operations="0.8.20",
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
            container_storage="0.10.3",
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
    mocked_instances: Mock,
    mocked_wait_for_terminal_state: Mock,
    mocked_live_display: Mock,
    mocked_logger: Mock,
    mocked_rich_print: Mock,
    spy_upgrade_manager: Dict[str, Mock],
    # require_instance_update: bool,
    current_extensions: List[dict],
    new_versions: List[dict],
    new_trains: List[dict],
    sr_resource_id: Optional[str],
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
    if current_version == "0.7.31":
        instance_body = _generate_instance(instance_name=instance_name, resource_group=rg_name)
        # note the resource client adds an extra / before instances for the parent path. The api doesnt care
        mocked_responses.add(
            method=responses.GET,
            url=f"https://management.azure.com/subscriptions/{get_zeroed_subscription()}/resourcegroups/{rg_name}"
            f"/providers/Microsoft.IoTOperations//instances/{instance_name}?api-version=2024-08-15-preview",
            json=instance_body,
            status=200,
            content_type="application/json",
        )
    else:
        instance_body = _generate_instance(instance_name=instance_name, resource_group=rg_name, m3=True)
        mocked_responses.add(
            method=responses.GET,
            url=f"https://management.azure.com/subscriptions/{get_zeroed_subscription()}/resourcegroups/{rg_name}"
            f"/providers/Microsoft.IoTOperations//instances/{instance_name}?api-version=2024-08-15-preview",
            status=404,
            content_type="application/json",
        )
        instance_body["properties"]["version"] = current_version
        mocked_instances.show.return_value = instance_body

    kwargs = {
        "cmd": mocked_cmd,
        "instance_name": instance_name,
        "resource_group_name": rg_name,
        "sr_resource_id": sr_resource_id,
        "confirm_yes": True,
        "no_progress": no_progress,
    }

    upgrade_ops_resources(**kwargs)

    # no matter what, we always try the m2 get
    assert len(mocked_responses.calls) == 1
    # extension update calls
    extensions_to_update = {}
    extension_update_calls = extension_update_mock.call_args_list
    call = 0
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

            if key == "microsoft.openservicemesh":
                assert payload["properties"]["configurationSettings"]
            # calls should be ordered together
            call += 1

    assert len(extensions_to_update) == len(extension_update_calls)

    # overall upgrade call
    require_instance_update = any([
        current_version == "0.7.31",
        version.parse(current_version) < version.parse(new_versions["iot_operations"])
    ])
    assert spy_upgrade_manager["_process"].called is any([extensions_to_update, require_instance_update])

    if require_instance_update:
        update_args = mocked_instances.iotops_mgmt_client.instance.begin_create_or_update.call_args.kwargs
        update_body = update_args["resource"]

        # props that were kept the same
        for prop in ["extendedLocation", "id", "name", "location", "resourceGroup", "type"]:
            assert update_body[prop] == instance_body[prop]
        for prop in ["description", "provisioningState"]:
            assert update_body["properties"][prop] == instance_body["properties"][prop]

        # props that were removed
        assert "systemData" not in update_body
        assert "schemaRegistryNamespace" not in update_body["properties"]
        assert "components" not in update_body["properties"]

        # props that were added/changed - also ensure right sr id is used
        assert update_body["properties"]["version"] == new_versions["iot_operations"]
        aio_ext_props = current_extensions["iot_operations"]["properties"]
        assert update_body["properties"]["schemaRegistryRef"]["resourceId"] == (
            sr_resource_id or aio_ext_props["configurationSettings"]["schemaRegistry.values.resourceId"]
        )
    else:
        # make sure we tried to get the m3
        mocked_instances.show.assert_called()
        mocked_instances.iotops_mgmt_client.instance.begin_create_or_update.assert_not_called()

    # no progress check
    if kwargs["no_progress"]:
        mocked_live_display.assert_called_once_with(None, transient=False, refresh_per_second=8, auto_refresh=False)


def test_upgrade_error(
    mocker,
    mocked_cmd: Mock,
    mocked_responses: responses,
    mocked_instances: Mock,
    mocked_wait_for_terminal_state: Mock,
    mocked_live_display: Mock,
    mocked_logger: Mock,
    mocked_rich_print: Mock,
):
    from azext_edge.edge.providers.orchestration.upgrade import upgrade_ops_resources

    rg_name = generate_random_string()
    instance_name = generate_random_string()
    m2_instance = _generate_instance(instance_name=instance_name, resource_group=rg_name)
    kwargs = {
        "cmd": mocked_cmd,
        "instance_name": instance_name,
        "resource_group_name": rg_name,
        "confirm_yes": True,
    }
    extensions = _generate_extensions()
    mocked_resource_map = mocked_instances.get_resource_map()
    mocked_resource_map.connected_cluster.extensions = list(extensions.values())

    # slowly work backwards
    # instance update fails
    mocked_responses.add(
        method=responses.GET,
        url=f"https://management.azure.com/subscriptions/{get_zeroed_subscription()}/resourcegroups/{rg_name}"
        f"/providers/Microsoft.IoTOperations//instances/{instance_name}?api-version=2024-08-15-preview",
        json=m2_instance,
        status=200,
        content_type="application/json",
    )
    mocked_instances.iotops_mgmt_client.instance.begin_create_or_update.side_effect = HttpResponseError(
        "instance update failed"
    )
    with pytest.raises(HttpResponseError) as e:
        upgrade_ops_resources(**kwargs)

    # some random extension has a hidden status error
    mocked_responses.add(
        method=responses.GET,
        url=f"https://management.azure.com/subscriptions/{get_zeroed_subscription()}/resourcegroups/{rg_name}"
        f"/providers/Microsoft.IoTOperations//instances/{instance_name}?api-version=2024-08-15-preview",
        json=m2_instance,
        status=200,
        content_type="application/json",
    )
    error_msg = generate_random_string()
    extensions["platform"]["properties"]["statuses"] = [{"code": "InstallationFailed", "message": error_msg}]
    extension_update_mock = mocked_resource_map.connected_cluster.clusters.extensions.update_cluster_extension
    extension_update_mock.return_value = extensions["platform"]
    with pytest.raises(AzureResponseError) as e:
        upgrade_ops_resources(**kwargs)
    assert error_msg in e.value.error_msg
    assert extensions["platform"]["name"] in e.value.error_msg

    # extension update fails
    mocked_responses.add(
        method=responses.GET,
        url=f"https://management.azure.com/subscriptions/{get_zeroed_subscription()}/resourcegroups/{rg_name}"
        f"/providers/Microsoft.IoTOperations//instances/{instance_name}?api-version=2024-08-15-preview",
        json=m2_instance,
        status=200,
        content_type="application/json",
    )
    extension_update_mock.side_effect = HttpResponseError(
        "extension update failed"
    )
    with pytest.raises(HttpResponseError):
        upgrade_ops_resources(**kwargs)

    # need to update the instance but cannot get the sr resource id
    mocked_responses.add(
        method=responses.GET,
        url=f"https://management.azure.com/subscriptions/{get_zeroed_subscription()}/resourcegroups/{rg_name}"
        f"/providers/Microsoft.IoTOperations//instances/{instance_name}?api-version=2024-08-15-preview",
        json=m2_instance,
        status=200,
        content_type="application/json",
    )
    [ext["properties"].pop("configurationSettings") for ext in mocked_resource_map.connected_cluster.extensions]

    with pytest.raises(RequiredArgumentMissingError):
        upgrade_ops_resources(**kwargs)

    # instance is an unreleased bug bash version
    m2_instance["properties"]["version"] = "0.7.25"
    mocked_responses.add(
        method=responses.GET,
        url=f"https://management.azure.com/subscriptions/{get_zeroed_subscription()}/resourcegroups/{rg_name}"
        f"/providers/Microsoft.IoTOperations//instances/{instance_name}?api-version=2024-08-15-preview",
        json=m2_instance,
        status=200,
        content_type="application/json",
    )
    with pytest.raises(ArgumentUsageError):
        upgrade_ops_resources(**kwargs)

    # cannot get m2 or m3
    mocked_responses.add(
        method=responses.GET,
        url=f"https://management.azure.com/subscriptions/{get_zeroed_subscription()}/resourcegroups/{rg_name}"
        f"/providers/Microsoft.IoTOperations//instances/{instance_name}?api-version=2024-08-15-preview",
        status=404,
        content_type="application/json",
    )
    mocked_instances.show.side_effect = HttpResponseError("instance get failed")
    with pytest.raises(ArgumentUsageError):
        upgrade_ops_resources(**kwargs)
