# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------


import json
import pytest
from azext_edge.edge.util import build_query
from ..generators import generate_generic_id


@pytest.mark.parametrize("custom_query", [None, generate_generic_id()])
@pytest.mark.parametrize("name", [None, generate_generic_id()])
@pytest.mark.parametrize("resource_group", [None, generate_generic_id()])
@pytest.mark.parametrize("location", [None, generate_generic_id()])
@pytest.mark.parametrize("type", [None, generate_generic_id()])
@pytest.mark.parametrize("additional_project", [None, generate_generic_id()])
def test_build_query(
    mocker,
    custom_query,
    name,
    resource_group,
    location,
    type,
    additional_project
):
    subscription_id = generate_generic_id()
    expected_result = generate_generic_id()
    mocked_process_query = mocker.patch("azext_edge.edge.util.common._process_raw_request")
    mocked_process_query.return_value = expected_result

    result = build_query(
        None,
        subscription_id,
        custom_query=custom_query,
        name=name,
        resource_group=resource_group,
        location=location,
        type=type,
        additional_project=additional_project
    )
    assert result == expected_result

    _, url, method, payload = mocked_process_query.call_args.args
    assert method == "POST"
    assert url == "/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01"
    assert payload["subscriptions"] == [subscription_id]

    query = payload["query"]
    if custom_query:
        assert custom_query in query
    if name:
        assert f'| where name =~ "{name}" ' in query
    if resource_group:
        assert f'| where resourceGroup =~ "{resource_group}" ' in query
    if location:
        assert f'| where location =~ "{location}" ' in query
    if type:
        assert f'| where type =~ "{type}" ' in query
    if additional_project:
        assert f', {additional_project}' in query


@pytest.mark.parametrize("mocked_send_raw_request", [
    {
        "return_value": {
            "data": [
                {"name": generate_generic_id(), "result": generate_generic_id()},
                {"name": generate_generic_id(), "result": generate_generic_id()}
            ]
        }
    },
    {
        "return_value": {
            "value": [
                {"name": generate_generic_id(), "result": generate_generic_id()},
                {"name": generate_generic_id(), "result": generate_generic_id()}
            ]
        }
    }
], ids=["data", "value"], indirect=True)
@pytest.mark.parametrize("url", [
    '/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01',
    generate_generic_id()
])
@pytest.mark.parametrize("method", ["POST", generate_generic_id()])
@pytest.mark.parametrize("payload", [
    None,
    {},
    {generate_generic_id(): generate_generic_id()}
])
def test_process_raw_request(mocked_cmd, mocked_send_raw_request, url, method, payload):
    from azext_edge.edge.util.common import _process_raw_request
    keyword = list(mocked_send_raw_request.return_value.json.return_value.keys())[0]

    result = _process_raw_request(
        mocked_cmd,
        url=url,
        method=method,
        payload=payload,
        keyword=keyword
    )
    assert result == mocked_send_raw_request.return_value.json.return_value[keyword]
    mocked_send_raw_request.assert_called_once()
    call_kwargs = mocked_send_raw_request.call_args.kwargs
    assert call_kwargs["cli_ctx"] == mocked_cmd.cli_ctx
    assert call_kwargs["method"] == method
    assert call_kwargs["url"] == url
    assert call_kwargs["body"] == (json.dumps(payload) if payload is not None else None)


@pytest.mark.parametrize("mocked_send_raw_request", [
    {
        "side_effect": [{
            "data": [
                {"result": generate_generic_id()},
                {"result": generate_generic_id()}
            ]
        }]
    },
    {
        "side_effect": [
            {
                "$skipToken": generate_generic_id(),
                "data": [
                    {"result": generate_generic_id()},
                    {"result": generate_generic_id()}
                ]
            },
            {
                "$skipToken": generate_generic_id(),
                "data": [
                    {"result": generate_generic_id()},
                    {"result": generate_generic_id()}
                ]
            },
            {
                "data": [
                    {"result": generate_generic_id()},
                    {"result": generate_generic_id()}
                ]
            }
        ]
    }
], ids=["one_page", "three_pages"], indirect=True)
@pytest.mark.parametrize("payload", [
    None,
    {},
    {generate_generic_id(): generate_generic_id()}
])
def test_process_raw_request_paging(mocked_cmd, mocked_send_raw_request, payload):
    from azext_edge.edge.util.common import _process_raw_request
    keyword = "data"
    url = generate_generic_id()
    method = generate_generic_id()
    expected_result = []
    side_effects = mocked_send_raw_request.return_value.json.side_effect_values
    for effect in side_effects:
        expected_result.extend(effect[keyword])

    result = _process_raw_request(
        mocked_cmd,
        url=url,
        method=method,
        payload=payload,
        keyword=keyword
    )
    assert result == expected_result
    mocked_send_raw_request.call_count == len(side_effects)
    skip_token = None
    for i in range(len(side_effects)):
        effect = side_effects[i]
        call_kwargs = mocked_send_raw_request.call_args_list[i].kwargs
        assert call_kwargs["cli_ctx"] == mocked_cmd.cli_ctx
        assert call_kwargs["method"] == method
        assert call_kwargs["url"] == url
        if payload is None and skip_token is None:
            assert call_kwargs["body"] is None
        else:
            loaded_body = json.loads(call_kwargs["body"])
            assert loaded_body.get("options", {}).get("$skipToken") == skip_token
        skip_token = effect.get("$skipToken")
