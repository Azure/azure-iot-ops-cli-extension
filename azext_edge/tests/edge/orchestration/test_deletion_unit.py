# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, List, Optional, Union
from unittest.mock import Mock

import pytest

from azext_edge.edge.providers.orchestration.deletion import IoTOperationsResource
from azext_edge.edge.providers.orchestration.common import EXTENSION_TYPE_OPS
from azext_edge.tests.helpers import generate_ops_resource

from ...generators import generate_random_string


@pytest.fixture
def mocked_resource_map(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.deletion.Instances",
    )
    yield patched().get_resource_map


@pytest.fixture
def mocked_logger(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.deletion.logger",
    )
    yield patched


@pytest.fixture
def mocked_get_resource_client(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.deletion.get_resource_client", autospec=True)
    yield patched


@pytest.fixture
def mocked_wait_for_terminal_states(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.deletion.wait_for_terminal_states", autospec=True)
    yield patched


@pytest.fixture
def mocked_live_display(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.deletion.Live")
    yield patched


@pytest.fixture
def spy_deletion_manager(mocker):
    from azext_edge.edge.providers.orchestration.deletion import DeletionManager

    yield {
        "_process": mocker.spy(DeletionManager, "_process"),
        "_display_resource_tree": mocker.spy(DeletionManager, "_display_resource_tree"),
        "_render_display": mocker.spy(DeletionManager, "_render_display"),
        "_stop_display": mocker.spy(DeletionManager, "_stop_display"),
        "_delete_batch": mocker.spy(DeletionManager, "_delete_batch"),
    }


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
    resource_map_mock().connected_cluster.get_extensions_by_type.return_value = {
        EXTENSION_TYPE_OPS: {"id": "aio-ext-id"}
    }
    resource_map_mock().extensions.append(
        IoTOperationsResource(resource_id="aio-ext-id", display_name="aio-extension", api_version="aio-ext-api")
    )


@pytest.mark.parametrize(
    "expected_resources_map",
    [
        {
            "resources": None,
            "resource sync rules": None,
            "custom locations": None,
            "extensions": [],
            "meta": {
                "expected_total": 0,
            },
        },
        {
            "resources": [
                generate_ops_resource(4),
            ],
            "resource sync rules": [generate_ops_resource()],
            "custom locations": [generate_ops_resource()],
            "extensions": [generate_ops_resource()],
            "meta": {
                "expected_total": 4,
                "resource_batches": 1,
            },
        },
        {
            "resources": [
                generate_ops_resource(4),
                generate_ops_resource(4),
                generate_ops_resource(3),
                generate_ops_resource(1),
            ],
            "resource sync rules": [],
            "custom locations": [generate_ops_resource()],
            "extensions": [generate_ops_resource(), generate_ops_resource()],
            "meta": {
                "expected_total": 7,
                "resource_batches": 3,
            },
        },
    ],
)
def test_batch_resources(
    mocker,
    mocked_cmd: Mock,
    mocked_get_resource_client: Mock,
    mocked_resource_map: Mock,
    expected_resources_map: Dict[str, Union[dict, Optional[List[IoTOperationsResource]]]],
):
    from azext_edge.edge.providers.orchestration.deletion import DeletionManager

    instance_name = generate_random_string()
    rg_name = generate_random_string()

    deletion_manager = DeletionManager(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=rg_name,
    )
    batches = deletion_manager._batch_resources(
        resources=expected_resources_map["resources"],
        resource_sync_rules=expected_resources_map["resource sync rules"],
        custom_locations=expected_resources_map["custom locations"],
        extensions=expected_resources_map["extensions"],
    )

    actual_total = 0
    if expected_resources_map["resources"]:
        assert "resources" in batches
        assert expected_resources_map["meta"]["resource_batches"] == len(batches["resources"])
        for batch in batches["resources"]:
            actual_total += len(batch)
            segments_set = set([r.segments for r in batch])
            assert len(segments_set) == 1

    for map_key in ["resource sync rules", "custom locations", "extensions"]:
        if expected_resources_map[map_key]:
            assert map_key in batches
            for batch in batches[map_key]:
                actual_total += len(batch)

    assert actual_total == expected_resources_map["meta"]["expected_total"]


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
                "expected_delete_calls": 1,  # aio extension
            },
        },
        {
            "resources": [generate_ops_resource(4), generate_ops_resource(2)],
            "resource sync rules": [generate_ops_resource(), generate_ops_resource()],
            "custom locations": [generate_ops_resource()],
            "extensions": [generate_ops_resource()],
            "meta": {
                "expected_total": 5,
                "resource_batches": 2,
                "expected_delete_calls": 5,
            },
        },
        # Currently no associated custom location means no non-extensions get deleted
        {
            "resources": [generate_ops_resource(4), generate_ops_resource(2)],
            "resource sync rules": [generate_ops_resource()],
            "custom locations": [],
            "extensions": [generate_ops_resource()],
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
            "extensions": [generate_ops_resource()],
            "meta": {
                "expected_total": 1,
                "resource_batches": 0,
                "expected_delete_calls": 1,
                "no_progress": True,
            },
        },
    ],
)
@pytest.mark.parametrize("include_dependencies", [None, True])
def test_delete_lifecycle(
    mocker,
    mocked_cmd: Mock,
    mocked_resource_map: Mock,
    mocked_get_resource_client: Mock,
    mocked_wait_for_terminal_states: Mock,
    mocked_live_display: Mock,
    mocked_logger: Mock,
    spy_deletion_manager: Dict[str, Mock],
    expected_resources_map: Dict[str, Union[dict, Optional[List[IoTOperationsResource]]]],
    include_dependencies: Optional[bool],
):
    from azext_edge.edge.providers.orchestration.deletion import delete_ops_resources

    instance_name = generate_random_string()
    rg_name = generate_random_string()

    _assemble_resource_map_mock(
        resource_map_mock=mocked_resource_map,
        extensions=expected_resources_map["extensions"],
        custom_locations=expected_resources_map["custom locations"],
        resources=expected_resources_map["resources"],
        sync_rules=expected_resources_map["resource sync rules"],
    )

    kwargs = {
        "cmd": mocked_cmd,
        "instance_name": instance_name,
        "resource_group_name": rg_name,
        "confirm_yes": True,
        "no_progress": expected_resources_map["meta"].get("no_progress"),
        "include_dependencies": include_dependencies,
    }

    delete_ops_resources(**kwargs)

    expected_delete_calls: int = expected_resources_map["meta"].get("expected_delete_calls", 0)

    spy_deletion_manager["_display_resource_tree"].assert_called_once()
    spy_deletion_manager["_process"].assert_called_once()

    if not any(
        [
            expected_resources_map["extensions"],
            expected_resources_map["custom locations"],
            expected_resources_map["resources"],
            expected_resources_map["resource sync rules"],
        ]
    ):
        assert mocked_logger.warning.call_args[0][0] == "Nothing to delete :)"
        spy_deletion_manager["_delete_batch"].assert_not_called()
        return

    if expected_delete_calls > 0:
        spy_deletion_manager["_render_display"].assert_called()
        spy_deletion_manager["_stop_display"].assert_called_once()

    assert spy_deletion_manager["_delete_batch"].call_count == expected_delete_calls
    assert mocked_live_display.call_count >= 1

    if kwargs["no_progress"]:
        mocked_live_display.assert_called_once_with(None, transient=False, refresh_per_second=8, auto_refresh=False)
