# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, List, Optional, Union
from unittest.mock import Mock

import pytest

from azext_edge.edge.providers.orchestration.deletion import IoTOperationsResource

from ...generators import generate_random_string


@pytest.fixture
def mocked_resource_map(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.deletion.IoTOperationsResourceMap",
    )
    yield patched


def _generate_ops_resource(segments: int = 1) -> IoTOperationsResource:
    resource_id = ""
    for _ in range(segments):
        resource_id = f"{resource_id}/{generate_random_string()}"

    resource = IoTOperationsResource(
        resource_id=resource_id,
        display_name=resource_id.split("/")[-1],
        api_version=generate_random_string(),
        segments=segments,
    )

    return resource


@pytest.mark.parametrize(
    "expected_resources_map",
    [
        {
            "resources": None,
            "resource sync rules": None,
            "custom locations": None,
            "extensions": None,
            "meta": {
                "expected_total": 0,
            },
        },
        {
            "resources": [
                _generate_ops_resource(4),
            ],
            "resource sync rules": [_generate_ops_resource()],
            "custom locations": [_generate_ops_resource()],
            "extensions": [_generate_ops_resource()],
            "meta": {
                "expected_total": 4,
                "resource_batches": 1,
            },
        },
        {
            "resources": [
                _generate_ops_resource(4),
                _generate_ops_resource(4),
                _generate_ops_resource(3),
                _generate_ops_resource(1),
            ],
            "resource sync rules": [],
            "custom locations": [_generate_ops_resource()],
            "extensions": [_generate_ops_resource(), _generate_ops_resource()],
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
    mocked_resource_map: Mock,
    mocked_get_resource_client: Mock,
    expected_resources_map: Dict[str, Union[dict, Optional[List[IoTOperationsResource]]]],
):
    from azext_edge.edge.providers.orchestration.deletion import DeletionManager

    cluster_name = generate_random_string()
    rg_name = generate_random_string()

    deletion_manager = DeletionManager(cmd=mocked_cmd, cluster_name=cluster_name, resource_group_name=rg_name)
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
