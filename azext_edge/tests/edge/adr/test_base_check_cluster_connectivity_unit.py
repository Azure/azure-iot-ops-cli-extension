# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.common import ResourceTypeMapping
from .conftest import RM_PATH
from ...generators import generate_generic_id


@pytest.mark.parametrize("mocked_build_query", [{
    "path": RM_PATH,
    "return_value": []
}], indirect=True)
def test_check_cluster_connectivity_no_location(mocked_cmd, mocked_build_query):
    from azext_edge.edge.providers.adr.base import ResourceManagementProvider
    provider = ResourceManagementProvider(mocked_cmd)
    custom_location_id = generate_generic_id()
    provider._check_cluster_connectivity(custom_location_id)
    assert mocked_build_query.call_count == 1

    cluster_query_kwargs = mocked_build_query.call_args.kwargs
    assert cluster_query_kwargs["type"] == ResourceTypeMapping.custom_location.value
    assert cluster_query_kwargs["custom_query"] == f'| where id =~ "{custom_location_id}"'


@pytest.mark.parametrize("mocked_build_query", [
    {
        "path": RM_PATH,
        "side_effect": [
            [{
                "name": generate_generic_id(),
                "properties": {
                    "hostResourceId": generate_generic_id()
                }
            }],
            []
        ]
    },
    {
        "path": RM_PATH,
        "side_effect": [
            [{
                "name": generate_generic_id(),
                "properties": {
                    "hostResourceId": generate_generic_id()
                }
            }],
            [{
                "name": generate_generic_id(),
                "properties": {
                    "connectivityStatus": "Connected"
                }
            }]
        ]
    },
    {
        "path": RM_PATH,
        "side_effect": [
            [{
                "name": generate_generic_id(),
                "properties": {
                    "hostResourceId": generate_generic_id()
                }
            }],
            [{
                "name": generate_generic_id(),
                "properties": {
                    "connectivityStatus": "Offline"
                }
            }]
        ]
    },
], ids=[
    "no cluster",
    "online cluster",
    "offline cluster"
], indirect=True)
def test_check_cluster_connectivity(mocked_cmd, mocked_build_query):
    from azext_edge.edge.providers.adr.base import ResourceManagementProvider
    provider = ResourceManagementProvider(mocked_cmd)
    custom_location_id = generate_generic_id()
    provider._check_cluster_connectivity(custom_location_id)
    assert mocked_build_query.call_count == 2

    cluster_query_kwargs = mocked_build_query.call_args_list[0].kwargs
    assert cluster_query_kwargs["type"] == ResourceTypeMapping.custom_location.value
    assert cluster_query_kwargs["custom_query"] == f'| where id =~ "{custom_location_id}"'

    cluster_id = mocked_build_query.side_effect_values[0][0]["properties"]["hostResourceId"]

    cluster_query_kwargs = mocked_build_query.call_args_list[1].kwargs
    assert cluster_query_kwargs["type"] == ResourceTypeMapping.connected_cluster.value
    assert cluster_query_kwargs["custom_query"] == f'| where id =~ "{cluster_id}"'
