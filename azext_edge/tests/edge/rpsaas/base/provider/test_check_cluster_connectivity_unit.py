# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.common import ResourceTypeMapping
from ...conftest import BP_PATH
from .....generators import generate_random_string


@pytest.mark.parametrize("mocked_build_query", [{
    "path": BP_PATH,
    "return_value": []
}], indirect=True)
def test_check_cluster_connectivity_no_location(mocked_cmd, mocked_build_query):
    from azext_edge.edge.providers.rpsaas.adr.base import ADRBaseProvider
    provider = ADRBaseProvider(mocked_cmd, generate_random_string())
    custom_location_id = generate_random_string()
    provider.check_cluster_connectivity(custom_location_id)
    assert mocked_build_query.call_count == 1

    cluster_query_kwargs = mocked_build_query.call_args.kwargs
    assert cluster_query_kwargs["type"] == ResourceTypeMapping.custom_location.full_resource_path
    assert cluster_query_kwargs["custom_query"] == f'| where id =~ "{custom_location_id}"'


@pytest.mark.parametrize("mocked_build_query", [
    {
        "path": BP_PATH,
        "side_effect": [
            [{
                "name": generate_random_string(),
                "properties": {
                    "hostResourceId": generate_random_string()
                }
            }],
            []
        ]
    },
    {
        "path": BP_PATH,
        "side_effect": [
            [{
                "name": generate_random_string(),
                "properties": {
                    "hostResourceId": generate_random_string()
                }
            }],
            [{
                "name": generate_random_string(),
                "properties": {
                    "connectivityStatus": "Connected"
                }
            }]
        ]
    },
    {
        "path": BP_PATH,
        "side_effect": [
            [{
                "name": generate_random_string(),
                "properties": {
                    "hostResourceId": generate_random_string()
                }
            }],
            [{
                "name": generate_random_string(),
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
    from azext_edge.edge.providers.rpsaas.adr.base import ADRBaseProvider
    provider = ADRBaseProvider(mocked_cmd, generate_random_string())
    custom_location_id = generate_random_string()
    provider.check_cluster_connectivity(custom_location_id)
    assert mocked_build_query.call_count == 2

    cluster_query_kwargs = mocked_build_query.call_args_list[0].kwargs
    assert cluster_query_kwargs["type"] == ResourceTypeMapping.custom_location.full_resource_path
    assert cluster_query_kwargs["custom_query"] == f'| where id =~ "{custom_location_id}"'

    cluster_id = mocked_build_query.side_effect_values[0][0]["properties"]["hostResourceId"]

    cluster_query_kwargs = mocked_build_query.call_args_list[1].kwargs
    assert cluster_query_kwargs["type"] == ResourceTypeMapping.connected_cluster.full_resource_path
    assert cluster_query_kwargs["custom_query"] == f'| where id =~ "{cluster_id}"'
