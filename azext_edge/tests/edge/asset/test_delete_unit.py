# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.commands_assets import delete_asset

from . import ASSETS_PATH
from ...helpers import parse_rest_command
from ...generators import generate_generic_id


@pytest.mark.parametrize("embedded_cli_client", [{
    "path": ASSETS_PATH,
    "as_json_result": {"result": generate_generic_id()}
}], ids=["cli"], indirect=True)
@pytest.mark.parametrize("resource_group", [None, generate_generic_id()])
def test_delete_asset(mocked_cmd, embedded_cli_client, resource_group):
    asset_name = generate_generic_id()
    list_rg = generate_generic_id()
    if not resource_group:
        as_json_results = list(embedded_cli_client.as_json.side_effect)
        list_call = {"value": [{
            "name": asset_name,
            "resourceGroup": list_rg
        }]}
        as_json_results.insert(0, list_call)
        embedded_cli_client.as_json.side_effect = as_json_results

    result = delete_asset(
        cmd=mocked_cmd,
        asset_name=asset_name,
        resource_group_name=resource_group
    )
    assert result is None

    request = embedded_cli_client.invoke.call_args[0][-1]
    request_dict = parse_rest_command(request)
    assert request_dict["method"] == "DELETE"
    assert f"/providers/Microsoft.DeviceRegistry/assets/{asset_name}?api-version=" in request_dict["uri"]
    expected_rg = "/resourceGroups/" + (resource_group or list_rg)
    assert expected_rg in request_dict["uri"]
