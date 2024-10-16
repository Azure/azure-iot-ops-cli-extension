# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, List, Optional, Union
from unittest.mock import Mock

import pytest

from ...generators import generate_random_string


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
    custom_locations: Optional[List[dict]],
    resources: Optional[List[dict]],
    sync_rules: Optional[List[dict]],
):
    resource_map_mock().extensions = extensions
    resource_map_mock().custom_locations = custom_locations
    resource_map_mock().get_resources.return_value = resources
    resource_map_mock().get_resource_sync_rules.return_value = sync_rules


# IoTOperationsResourceMap returns empty array over None
# Order resources from segment size since resource map takes care of this.
@pytest.mark.parametrize(
    "expected_resources_map",
    [
        {
            "resources": [],
            "resource sync rules": [],
            "custom locations": [],
            "extensions": [],
            "meta": {
                "expected_total": 0,
            },
        },
        {
            "resources": [_generate_ops_resource(4), _generate_ops_resource(2)],
            "resource sync rules": [_generate_ops_resource(), _generate_ops_resource()],
            "custom locations": [_generate_ops_resource()],
            "extensions": [_generate_ops_resource()],
            "meta": {
                "expected_total": 5,
                "resource_batches": 2,
                "expected_delete_calls": 5,
            },
        },
        # Currently no associated custom location means no non-extensions get deleted
        {
            "resources": [_generate_ops_resource(4), _generate_ops_resource(2)],
            "resource sync rules": [_generate_ops_resource()],
            "custom locations": [],
            "extensions": [_generate_ops_resource()],
            "meta": {
                "expected_total": 4,
                "resource_batches": 2,
                "expected_delete_calls": 1,
            },
        },
        {
            "resources": [],
            "resource sync rules": [],
            "custom locations": [],
            "extensions": [_generate_ops_resource()],
            "meta": {
                "expected_total": 1,
                "resource_batches": 0,
                "expected_delete_calls": 1,
                "no_progress": True,
            },
        },
    ],
)
@pytest.mark.parametrize("instance_name", [None, generate_random_string()])
def test_upgrade_lifecycle(
    mocker,
    mocked_cmd: Mock,
    mocked_resource_map: Mock,
    mocked_get_resource_client: Mock,
    mocked_wait_for_terminal_states: Mock,
    mocked_live_display: Mock,
    mocked_logger: Mock,
    spy_upgrade_manager: Dict[str, Mock],
    expected_resources_map: Dict[str, Union[dict, Optional[List[IoTOperationsResource]]]],
    instance_name: Optional[str],
):
    from azext_edge.edge.providers.orchestration.upgrade import upgrade_ops_resources
    # scenarios to test:
    # instance name vs cluster name used
    # sr resource id provided
    # extensions - all need updates, 3 need updates, none need updates
    # instance is m2 vs m3

    cluster_name = None if instance_name else generate_random_string()
    rg_name = generate_random_string()
    sr_resource_id = generate_random_string()

    _assemble_resource_map_mock(
        resource_map_mock=mocked_resource_map,
        extensions=expected_resources_map["extensions"],
        custom_locations=expected_resources_map["custom locations"],
        resources=expected_resources_map["resources"],
    )

    kwargs = {
        "cmd": mocked_cmd,
        "instance_name": instance_name,
        "cluster_name": cluster_name,
        "resource_group_name": rg_name,
        "sr_resource_id": sr_resource_id,
        "confirm_yes": True,
        "no_progress": expected_resources_map["meta"].get("no_progress"),
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
