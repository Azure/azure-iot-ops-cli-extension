# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import pytest
from . import ASSETS_PATH


@pytest.fixture()
def asset_helpers_fixture(mocker, request):
    # TODO: see if there is a nicer way to mass mock helper funcs
    helper_fixtures = []
    patched_sp = mocker.patch(f"{ASSETS_PATH}._process_asset_sub_points")
    patched_sp.return_value = request.param["process_asset_sub_points"]
    helper_fixtures.append(patched_sp)

    def mock_update_properties(properties, **kwargs):
        """Minimize how much to check by setting everything update properties should touch to None."""
        for k in kwargs:
            properties.pop(k, None)
        properties.pop("defaultDataPointsConfiguration", None)
        properties.pop("defaultEventsConfiguration", None)
        properties["result"] = request.param["update_properties"]

    patched_up = mocker.patch(f"{ASSETS_PATH}._update_properties")
    patched_up.side_effect = mock_update_properties
    helper_fixtures.append(patched_up)
    yield helper_fixtures


# @pytest.fixture()
# def show_asset_fixture(mocker, request):
#     patched_show = mocker.patch(SHOW_ASSETS_PATH)
#     copy = json.loads(json.dumps(request.param))
#     patched_show.return_value = copy
#     yield patched_show, request.param
