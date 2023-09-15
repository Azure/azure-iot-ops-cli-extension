# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import pytest
from . import (
    PROCESS_DP_ASSETS_PATH,
    PROCESS_EV_ASSETS_PATH,
    UPDATE_PROPERTIES_ASSETS_PATH
)


@pytest.fixture()
def asset_helpers_fixture(mocker, request):
    patched_dp = mocker.patch(PROCESS_DP_ASSETS_PATH)
    patched_dp.return_value = request.param["process_dp_result"]
    patched_ev = mocker.patch(PROCESS_EV_ASSETS_PATH)
    patched_ev.return_value = request.param["process_ev_result"]

    def mock_update_properties(properties, **kwargs):
        """Minimize how much to check by setting everything update properties should touch to None."""
        for k in kwargs:
            properties.pop(k, None)
        properties.pop("defaultDataPointsConfiguration", None)
        properties.pop("defaultEventsConfiguration", None)
        properties["result"] = request.param["update_properties_result"]

    patched_up = mocker.patch(UPDATE_PROPERTIES_ASSETS_PATH)
    patched_up.side_effect = mock_update_properties
    yield patched_dp, patched_ev, patched_up
