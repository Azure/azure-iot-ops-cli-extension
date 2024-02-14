# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from ...helpers import run


@pytest.mark.parametrize("raw", [False, True])
def test_stats(init_setup, raw):
    # TODO: add in other params
    # TODO: figure out optimal init setup so trace dir can yield non empty zips
    command = "az iot ops mq stats"
    if raw:
        command += " --raw"
    result = run(command)
    if raw:
        # string result
        assert result.startswith("# TYPE")
        assert result.strip().endswith("# EOF")
    else:
        # dict result
        assert result["connected_sessions"]
        assert result["publishes_received_per_second"]
        assert result["publishes_sent_per_second"]
        assert result["total_subscriptions"]

        for value in result.values():
            assert value["description"]
            assert value["displayName"]
            assert value["value"] is not None
