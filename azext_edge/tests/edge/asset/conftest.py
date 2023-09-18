# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import pytest
import json
from . import (
    PROCESS_SUB_POINTS_ASSETS_PATH,
    UPDATE_PROPERTIES_ASSETS_PATH,
    SHOW_ASSETS_PATH
)


@pytest.fixture()
def asset_helpers_fixture(mocker, request):
    patched_sp = mocker.patch(PROCESS_SUB_POINTS_ASSETS_PATH)
    patched_sp.return_value = request.param["process_asset_sub_points"]

    def mock_update_properties(properties, **kwargs):
        """Minimize how much to check by setting everything update properties should touch to None."""
        for k in kwargs:
            properties.pop(k, None)
        properties.pop("defaultDataPointsConfiguration", None)
        properties.pop("defaultEventsConfiguration", None)
        properties["result"] = request.param["update_properties"]

    patched_up = mocker.patch(UPDATE_PROPERTIES_ASSETS_PATH)
    patched_up.side_effect = mock_update_properties
    yield patched_sp, patched_up


@pytest.fixture()
def show_asset_fixture(mocker, request):
    patched_show = mocker.patch(SHOW_ASSETS_PATH)
    copy = json.loads(json.dumps(request.param))
    patched_show.return_value = copy
    yield patched_show, request.param
