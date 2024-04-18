# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import itertools
import json
from unittest.mock import Mock

import pytest

from ..generators import generate_random_string, get_zeroed_subscription


@pytest.mark.parametrize(
    "test_scenario",
    [
        {
            "subscriptions": [],
            "response": {"data": []},
        },
        {
            "subscriptions": [get_zeroed_subscription(), get_zeroed_subscription()],
            "response": {"data": [{generate_random_string(): generate_random_string()}]},
        },
        {
            "subscriptions": [get_zeroed_subscription()],
            "response": {
                "data": [
                    {generate_random_string(): generate_random_string()},
                    {generate_random_string(): generate_random_string()},
                ]
            },
        },
        {
            "subscriptions": [get_zeroed_subscription()],
            "page_size": 7,
            "response": [
                {
                    "data": [
                        {generate_random_string(): generate_random_string()},
                    ],
                    "$skipToken": generate_random_string(),
                },
                {
                    "data": [
                        {generate_random_string(): generate_random_string()},
                    ]
                },
            ],
        },
    ],
)
def test_query_resources(mocker, mocked_cmd, test_scenario: dict):
    mocked_send_raw_request: Mock = mocker.patch("azext_edge.edge.util.resource_graph.send_raw_request")

    mock_response = mocker.MagicMock()
    if isinstance(test_scenario["response"], dict):
        mock_response.json.return_value = test_scenario["response"]
    if isinstance(test_scenario["response"], list):
        mock_response.json.side_effect = test_scenario["response"]

    mocked_send_raw_request.return_value = mock_response

    from azext_edge.edge.util.resource_graph import GRAPH_RESOURCE_PATH, ResourceGraph

    resource_graph = ResourceGraph(cmd=mocked_cmd, subscriptions=test_scenario["subscriptions"])
    assert resource_graph.subscriptions == test_scenario["subscriptions"]  # TODO when nothing passed in []

    expected_query = f"""
    Resources
    | where type == 'microsoft.extendedlocation/customlocations'
    | where tolower(properties.hostResourceId) == tolower('{generate_random_string()}')
    | where tolower(properties.namespace) == tolower('{generate_random_string()}')
    | project id, name, location, properties
    """

    page_size = test_scenario.get("page_size")
    result = resource_graph.query_resources(query=expected_query, page_size=page_size)
    assert "data" in result

    if isinstance(test_scenario["response"], dict):
        assert result["data"] == test_scenario["response"]["data"]
    if isinstance(test_scenario["response"], list):
        assert result["data"] == list(itertools.chain.from_iterable([r["data"] for r in test_scenario["response"]]))

    expected_request_body = {
        "subscriptions": resource_graph.subscriptions,
        "query": expected_query,
        "options": {},
    }
    if page_size:
        expected_request_body["options"]["$top"] = page_size

    expected_send_raw_request_call = {
        "cli_ctx": mocked_cmd.cli_ctx,
        "url": GRAPH_RESOURCE_PATH,
        "body": json.dumps(expected_request_body),
        "method": "POST",
    }

    # Initial request
    assert mocked_send_raw_request.call_args_list[0].kwargs == expected_send_raw_request_call

    # Follow on request if necessary
    total_send_raw_request_calls = 1
    if isinstance(test_scenario["response"], list):
        for i in range(0, len(test_scenario["response"])):
            if not i:
                total_send_raw_request_calls += 1
            if "$skipToken" in test_scenario["response"][i]:
                expected_request_body["options"] = {"$skipToken": test_scenario["response"][i]["$skipToken"]}
                expected_send_raw_request_call["body"] = json.dumps(expected_request_body)
                assert mocked_send_raw_request.call_args_list[i + 1].kwargs == expected_send_raw_request_call

    assert mocked_send_raw_request.call_count == total_send_raw_request_calls
