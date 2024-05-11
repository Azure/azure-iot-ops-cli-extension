# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, List, Optional
from unittest.mock import Mock
from random import randint

import pytest

from azext_edge.edge.providers.orchestration.deletion import IoTOperationsResource

from ...generators import generate_random_string


@pytest.fixture
def mocked_resource_map(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.deletion.IoTOperationsResourceMap",
    )
    yield patched


def _generate_iot_ops_resources(count: int = 1) -> List[IoTOperationsResource]:
    result = []
    segments = sorted([randint(1, 10) for _ in range(count)], key=int, reverse=True)

    for i in range(count):
        result.append(
            IoTOperationsResource(
                resource_id=generate_random_string(),
                display_name=generate_random_string(),
                api_version=generate_random_string(),
                segments=segments[i],
            )
        )

    return result


@pytest.mark.parametrize(
    "expected_resources_map",
    [
        {"resources": None, "resource_sync_rules": None, "custom_locations": None, "extensions": None},
        {
            "resources": _generate_iot_ops_resources(),
            "resource_sync_rules": _generate_iot_ops_resources(),
            "custom_locations": _generate_iot_ops_resources(),
            "extensions": _generate_iot_ops_resources(),
        },
    ],
)
def test_batch_resources(
    mocker,
    mocked_cmd: Mock,
    mocked_resource_map: Mock,
    mocked_get_resource_client: Mock,
    expected_resources_map: Dict[str, Optional[List[IoTOperationsResource]]],
):
    from azext_edge.edge.providers.orchestration.deletion import DeletionManager

    cluster_name = generate_random_string()
    rg_name = generate_random_string()

    deletion_manager = DeletionManager(cmd=mocked_cmd, cluster_name=cluster_name, resource_group_name=rg_name)
    batch = deletion_manager._batch_resources(
        resources=expected_resources_map["resources"],
        resource_sync_rules=expected_resources_map["resource_sync_rules"],
        custom_locations=expected_resources_map["custom_locations"],
        extensions=expected_resources_map["extensions"],
    )

    if expected_resources_map["resources"]:
        assert "resources" in batch
    if expected_resources_map["resource_sync_rules"]:
        assert "resource sync rules" in batch
    if expected_resources_map["custom_locations"]:
        assert "custom locations" in batch
    if expected_resources_map["extensions"]:
        assert "extensions" in batch

    # import pdb; pdb.set_trace()
    pass
