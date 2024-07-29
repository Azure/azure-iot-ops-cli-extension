# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from .....generators import generate_random_string


@pytest.mark.parametrize("mocked_send_raw_request", [
    {
        "return_value": {
            "value": [
                {"name": generate_random_string(), "result": generate_random_string()},
                {"name": generate_random_string(), "result": generate_random_string()}
            ]
        }
    }
], ids=["value"], indirect=True)
@pytest.mark.parametrize("resource_group", [None, generate_random_string()])
@pytest.mark.parametrize("parent_resource_path", ["", generate_random_string()])
def test_list_assets(
    mocked_cmd,
    mocked_send_raw_request,
    resource_group,
    parent_resource_path
):
    from azext_edge.edge.providers.rpsaas.base_provider import RPSaaSBaseProvider
    api_version = generate_random_string()
    resource_type = generate_random_string()
    provider_namespace = generate_random_string()
    provider = RPSaaSBaseProvider(
        cmd=mocked_cmd,
        api_version=api_version,
        provider_namespace=provider_namespace,
        resource_type=resource_type,
        parent_resource_path=parent_resource_path
    )
    result = provider.list(resource_group)

    assert result == mocked_send_raw_request.return_value.json.return_value["value"]
    mocked_send_raw_request.assert_called_once()
    call_kwargs = mocked_send_raw_request.call_args.kwargs
    assert call_kwargs["cli_ctx"] == mocked_cmd.cli_ctx
    assert call_kwargs["method"] == "GET"
    assert f"/providers/{provider_namespace}" in call_kwargs["url"]
    assert f"/{resource_type}?api-version={api_version}" in call_kwargs["url"]
    assert (f"/resourceGroups/{resource_group}" in call_kwargs["url"]) is (resource_group is not None)
    assert (f"/{parent_resource_path}" in call_kwargs["url"]) is (parent_resource_path is not None)
