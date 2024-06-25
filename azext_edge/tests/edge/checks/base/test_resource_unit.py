# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.providers.check.base.resource import enumerate_ops_service_resources
from azext_edge.edge.providers.check.common import ALL_NAMESPACES_TARGET
from azext_edge.edge.providers.edge_api import (
    AKRI_API_V0,
    AkriResourceKinds,
    MQ_ACTIVE_API,
    MqResourceKinds,
)


@pytest.mark.parametrize(
    "api_info,resource_kinds, check_name, check_desc, excluded_resources, api_resources, expected_resource_map, status",
    [
        (MQ_ACTIVE_API, MqResourceKinds.list(), "mq", "MQ", None, [], {}, "error"),
        (AKRI_API_V0, AkriResourceKinds.list(), "akri", "AKRI", None, {
                'api_version': 'v1',
                'group_version': 'akri.sh/v0',
                'kind': 'APIResourceList',
                'resources': [
                        {
                            'categories': None,
                            'group': None,
                            'kind': 'Instance',
                            'name': 'instances',
                            'namespaced': True,
                            'short_names': ['akrii'],
                            'singular_name': 'instance',
                            'storage_version_hash': 'NYs6qye9tw0=',
                            'verbs': ['delete',
                                    'deletecollection',
                                    'get',
                                    'list',
                                    'patch',
                                    'create',
                                    'update',
                                    'watch'],
                            'version': None
                        },
                        {
                            'categories': None,
                            'group': None,
                            'kind': 'Configuration',
                            'name': 'configurations',
                            'namespaced': True,
                            'short_names': ['akric'],
                            'singular_name': 'configuration',
                            'storage_version_hash': 'O7uZF5TGfBY=',
                            'verbs': ['delete',
                                    'deletecollection',
                                    'get',
                                    'list',
                                    'patch',
                                    'create',
                                    'update',
                                    'watch'],
                            'version': None
                        }
                    ]
            },
            {AkriResourceKinds.INSTANCE.value: True, AkriResourceKinds.CONFIGURATION.value: True},
            "success"
        ),
    ]
)
def test_enumerate_ops_service_resources(
    mocked_check_manager,
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
    api_info._kinds()
    assert len(result["targets"][api_info.as_str()]) == 1
    target_key = f"{api_info.group}/{api_info.version}"
    assert target_key in result["targets"]
    evaluation = result["targets"][api_info.as_str()][ALL_NAMESPACES_TARGET]
    assert evaluation["conditions"] is None
    assert evaluation["status"] == status
    assert len(evaluation["evaluations"]) == 1
    assert evaluation["evaluations"][0]["status"] == status
    assert resource_map == expected_resource_map

    if status == "success":
        assert len(evaluation["evaluations"][0]["value"]) == len(resource_kinds)
        for kind in evaluation["evaluations"][0]["value"]:
            assert kind.lower() in resource_kinds


