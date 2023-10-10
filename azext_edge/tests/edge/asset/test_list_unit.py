# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import pytest

from ....edge.commands_assets import list_assets

from . import ASSETS_PATH
from ...helpers import parse_rest_command
from ...generators import generate_generic_id


@pytest.mark.parametrize("embedded_cli_client", [{
    "path": ASSETS_PATH,
    "as_json_result": {"value": {"result": generate_generic_id()}}
}], ids=["cli"], indirect=True)
@pytest.mark.parametrize("resource_group", [None, generate_generic_id()])
def test_list_assets(mocked_cmd, embedded_cli_client, request, resource_group):
    result = list_assets(
        cmd=mocked_cmd,
        resource_group_name=resource_group
    )
    assert result == next(embedded_cli_client.as_json.side_effect)["value"]

    request = embedded_cli_client.invoke.call_args[0][0]
    request_dict = parse_rest_command(request)
    assert request_dict["method"] == "GET"
    assert "/providers/Microsoft.DeviceRegistry/assets?api-version=" in request_dict["uri"]
    assert (f"/resourceGroups/{resource_group}" in request_dict["uri"]) is (resource_group is not None)
