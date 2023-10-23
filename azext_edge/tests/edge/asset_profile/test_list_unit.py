# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.commands_asset_endpoint_profiles import list_asset_endpoint_profiles
from azext_edge.edge.common import ResourceTypeMapping
from azext_edge.edge.providers.assets import API_VERSION

from ...generators import generate_generic_id


@pytest.mark.parametrize("mocked_send_raw_request", [
    {
        "return_value": {
            "value": [
                {"name": generate_generic_id(), "result": generate_generic_id()},
                {"name": generate_generic_id(), "result": generate_generic_id()}
            ]
        }
    }
], ids=["value"], indirect=True)
@pytest.mark.parametrize("resource_group", [None, generate_generic_id()])
def test_list_assets(
    mocked_cmd,
    mocked_send_raw_request,
    resource_group
):
    result = list_asset_endpoint_profiles(
        cmd=mocked_cmd,
        resource_group_name=resource_group
    )
    assert result == mocked_send_raw_request.return_value.json.return_value["value"]
    mocked_send_raw_request.assert_called_once()
    call_kwargs = mocked_send_raw_request.call_args.kwargs
    assert call_kwargs["cli_ctx"] == mocked_cmd.cli_ctx
    assert call_kwargs["method"] == "GET"
    typing = ResourceTypeMapping.asset_endpoint_profile.value
    assert f"/providers/{typing}?api-version={API_VERSION}" in call_kwargs["url"]
    assert (f"/resourceGroups/{resource_group}" in call_kwargs["url"]) is (resource_group is not None)
