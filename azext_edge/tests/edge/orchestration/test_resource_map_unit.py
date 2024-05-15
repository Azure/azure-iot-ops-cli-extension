# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List, Optional
from unittest.mock import Mock
from random import randint

import pytest
from rich.tree import Tree

from azext_edge.edge.providers.orchestration.resource_map import IoTOperationsResource

from ...generators import generate_random_string, get_zeroed_subscription


@pytest.fixture
def mocked_connected_cluster(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.resource_map.ConnectedCluster",
    )
    yield patched


def _generate_records(count: int = 1) -> List[dict]:
    result = []

    for i in range(count):
        high = randint(5, 10)
        low = randint(1, 4)
        segments = high if i % 2 == 0 else low

        resource_id = ""
        for _ in range(segments):
            resource_id = f"{resource_id}/{generate_random_string()}"
        result.append({"id": resource_id, "name": resource_id.split("/")[-1], "apiVersion": generate_random_string()})

    return result


def _assemble_connected_cluster_mock(
    cluster_mock: Mock,
    extensions: Optional[List[dict]],
    custom_locations: Optional[List[dict]],
    resources: Optional[List[dict]],
    sync_rules: Optional[List[dict]],
):
    cluster_mock().get_aio_extensions.return_value = extensions
    cluster_mock().get_aio_custom_locations.return_value = custom_locations
    cluster_mock().get_aio_resources.return_value = resources
    cluster_mock().get_resource_sync_rules.return_value = sync_rules


@pytest.mark.parametrize(
    "expected_extensions",
    [None, _generate_records()],
)
@pytest.mark.parametrize(
    "expected_custom_locations",
    [None, _generate_records()],
)
@pytest.mark.parametrize("expected_resources", [None, _generate_records(5)])
@pytest.mark.parametrize("expected_resource_sync_rules", [None, _generate_records()])
def test_resource_map(
    mocker,
    mocked_cmd: Mock,
    mocked_connected_cluster: Mock,
    expected_extensions: Optional[List[dict]],
    expected_custom_locations: Optional[List[dict]],
    expected_resources: Optional[List[dict]],
    expected_resource_sync_rules: Optional[List[dict]],
):
    from azext_edge.edge.providers.orchestration.resource_map import (
        IoTOperationsResourceMap,
    )

    _assemble_connected_cluster_mock(
        cluster_mock=mocked_connected_cluster,
        extensions=expected_extensions,
        custom_locations=expected_custom_locations,
        resources=expected_resources,
        sync_rules=expected_resource_sync_rules,
    )

    sub = get_zeroed_subscription()
    cluster_name = generate_random_string()
    rg_name = generate_random_string()

    resource_map = IoTOperationsResourceMap(cmd=mocked_cmd, cluster_name=cluster_name, resource_group_name=rg_name)

    assert resource_map.subscription_id == sub
    mocked_connected_cluster().get_aio_extensions.assert_called_once()
    _assert_ops_resource_eq(resource_map.extensions, expected_extensions)

    mocked_connected_cluster().get_aio_custom_locations.assert_called_once()
    _assert_ops_resource_eq(resource_map.custom_locations, expected_custom_locations)

    cl_count = 0 if not expected_custom_locations else len(expected_custom_locations)
    assert mocked_connected_cluster().get_aio_resources.call_count == cl_count
    assert mocked_connected_cluster().get_resource_sync_rules.call_count == cl_count

    if expected_custom_locations:
        for cl in expected_custom_locations:
            _assert_ops_resource_eq(
                resource_map.get_resources(cl["id"]), expected_resources, verify_segment_order=True
            )
            _assert_ops_resource_eq(resource_map.get_resource_sync_rules(cl["id"]), expected_resource_sync_rules)

    _assert_tree(
        resource_map.build_tree(),
        cluster_name=cluster_name,
        expected_aio_extensions=expected_extensions,
        expected_aio_custom_locations=expected_custom_locations,
        expected_aio_resources=expected_resources,
        expected_resource_sync_rules=expected_resource_sync_rules,
    )


def _assert_ops_resource_eq(
    actual: List[IoTOperationsResource], expected: List[dict], verify_segment_order: bool = False
):
    if verify_segment_order and actual:
        last_segments: int = 999
        ids = {record["id"] for record in expected}
        for i in range(len(actual)):
            assert isinstance(actual[i].segments, int)
            assert actual[i].segments <= last_segments
            last_segments = actual[i].segments
            # Serves as membership assertion, removing non-member throws KeyError
            ids.remove(actual[i].resource_id)
        assert not ids
        return

    for i in range(len(actual)):
        assert actual[i].resource_id == expected[i]["id"]
        assert actual[i].display_name == expected[i]["name"]
        assert actual[i].api_version == expected[i]["apiVersion"]


def _assert_tree(
    tree: Tree,
    cluster_name: str,
    expected_aio_extensions: Optional[List[dict]],
    expected_aio_custom_locations: Optional[List[dict]],
    expected_aio_resources: Optional[List[dict]],
    expected_resource_sync_rules: Optional[List[dict]],
):
    assert tree.label == f"[green]{cluster_name}"

    assert tree.children[0].label == "[red]extensions"
    if expected_aio_extensions:
        for i in range(len(expected_aio_extensions)):
            tree.children[0].children[i].label == expected_aio_extensions[i]["name"]

    assert tree.children[1].label == "[red]customLocations"
    if expected_aio_custom_locations:
        for i in range(len(expected_aio_custom_locations)):
            tree.children[1].children[i].label == expected_aio_custom_locations[i]["name"]

            if expected_resource_sync_rules:
                assert tree.children[1].children[i].children[0].label == "[red]resourceSyncRules"
                for j in range(len(expected_resource_sync_rules)):
                    tree.children[1].children[i].children[0].children[j].label == expected_resource_sync_rules[i][
                        "name"
                    ]

            if expected_aio_resources:
                assert tree.children[1].children[i].children[1].label == "[red]resources"
                for j in range(len(expected_aio_resources)):
                    tree.children[1].children[i].children[1].children[j].label == expected_aio_resources[i]["name"]
