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
    mocked_process_query = mocker.patch("azext_edge.edge.util.common._process_query")
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
        "data": [
            {"name": generate_generic_id(), "result": generate_generic_id()},
            {"name": generate_generic_id(), "result": generate_generic_id()}
        ]
    }
], ids=["data"], indirect=True)
@pytest.mark.parametrize("url", [
    '/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01',
    generate_generic_id()
])
@pytest.mark.parametrize("method", ["POST", generate_generic_id()])
@pytest.mark.parametrize("payload", [
    {},
    {generate_generic_id(): generate_generic_id()}
])
def test_process_query(mocked_cmd, mocked_send_raw_request, url, method, payload):
    from azext_edge.edge.util.common import _process_query

    result = _process_query(
        mocked_cmd,
        url=url,
        method=method,
        payload=payload
    )
    assert result == mocked_send_raw_request.return_value.json.return_value["data"]
    mocked_send_raw_request.assert_called_once()
    call_kwargs = mocked_send_raw_request.call_args.kwargs
    assert call_kwargs["cli_ctx"] == mocked_cmd.cli_ctx
    assert call_kwargs["method"] == method
    assert call_kwargs["url"] == url
    assert call_kwargs["body"] == json.dumps(payload)
