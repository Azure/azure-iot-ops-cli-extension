# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.common import CheckTaskStatus
from azext_edge.edge.providers.check.base.resource import enumerate_ops_service_resources
from azext_edge.edge.providers.check.common import ALL_NAMESPACES_TARGET
from azext_edge.edge.providers.edge_api import (
    AKRI_API_V0,
    AkriResourceKinds,
    MQ_ACTIVE_API,
    MqResourceKinds,
    OPCUA_API_V1,
    OpcuaResourceKinds,
)
from azext_edge.tests.edge.checks.conftest import generate_api_resource_list
# TODO: Add more test for resource.py


@pytest.mark.parametrize(
    "api_info, resource_kinds, check_name, check_desc,\
        excluded_resources, api_resources, expected_resource_map, status",
    [
        (MQ_ACTIVE_API, MqResourceKinds.list(), "mq", "MQ", None, [], {}, CheckTaskStatus.error.value),
        (
            AKRI_API_V0, AkriResourceKinds.list(), "akri", "AKRI", None,
            generate_api_resource_list
            (
                api_version=AKRI_API_V0.version,
                group_version=AKRI_API_V0.as_str(),
                resources=[
                    {
                        'categories': None,
                        'group': None,
                        'kind': 'Instance',
                        'name': 'instances',
                        'namespaced': True,
                        'short_names': ['akrii'],
                        'singular_name': 'instance',
                        'verbs': [
                            'delete',
                            'deletecollection',
                            'get',
                            'list',
                            'patch',
                            'create',
                            'update',
                            'watch'
                        ],
                    },
                    {
                        'categories': None,
                        'group': None,
                        'kind': 'Configuration',
                        'name': 'configurations',
                        'namespaced': True,
                        'short_names': ['akric'],
                        'singular_name': 'configuration',
                        'verbs': [
                            'delete',
                            'deletecollection',
                            'get',
                            'list',
                            'patch',
                            'create',
                            'update',
                            'watch'
                        ],
                    }
                ]
            ),
            {
                AkriResourceKinds.INSTANCE.value.capitalize(): True,
                AkriResourceKinds.CONFIGURATION.value.capitalize(): True
            },
            CheckTaskStatus.success.value
        ),
        (
            OPCUA_API_V1, OpcuaResourceKinds.list(), "opcua", "OPCUA", ["assettypes"],
            generate_api_resource_list(
                api_version=OPCUA_API_V1.version,
                group_version=OPCUA_API_V1.as_str(),
                resources=[
                    {
                        'categories': None,
                        'group': None,
                        'kind': 'AssetType',
                        'name': 'assettypes',
                        'namespaced': True,
                        'short_names': None,
                        'singular_name': 'assettype',
                        'storage_version_hash': 'FCPRUJA7s2I=',
                        'verbs': [
                            'delete',
                            'deletecollection',
                            'get',
                            'list',
                            'patch',
                            'create',
                            'update',
                            'watch'
                        ],
                        'version': None
                    },
                ]
            ),
            {},
            CheckTaskStatus.success.value
        ),
    ]
)
def test_enumerate_ops_service_resources(
    mock_get_cluster_custom_api,
    api_info,
    resource_kinds,
    api_resources,
    check_name,
    check_desc,
    excluded_resources,
    expected_resource_map,
    status,
):
    mock_get_cluster_custom_api.return_value = api_resources
    result, resource_map = enumerate_ops_service_resources(
        api_info=api_info,
        check_name=check_name,
        check_desc=check_desc,
        as_list=False,
        excluded_resources=excluded_resources,
    )
    assert len(result["targets"][api_info.as_str()]) == 1
    target_key = f"{api_info.group}/{api_info.version}"
    assert target_key in result["targets"]
    evaluation = result["targets"][api_info.as_str()][ALL_NAMESPACES_TARGET]
    assert evaluation["conditions"] is None
    assert evaluation["status"] == status
    assert len(evaluation["evaluations"]) == 1
    assert evaluation["evaluations"][0]["status"] == status
    assert resource_map == expected_resource_map

    if status == expected_resource_map:
        assert len(evaluation["evaluations"][0]["value"]) == len(resource_kinds)
        for kind in evaluation["evaluations"][0]["value"]:
            assert kind.lower() in resource_kinds
