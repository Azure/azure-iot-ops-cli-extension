# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from typing import List
from .helpers import split_name


@pytest.mark.parametrize("input, expected",[
    [
        "pod.aio-dataflow-upgrade-status-job-0.1.0-preview-rc9-4q4pg.aio-dataflow-upgrade-status-job.log",
        ["pod", "aio-dataflow-upgrade-status-job-0.1.0-preview-rc9-4q4pg", "aio-dataflow-upgrade-status-job", "log"]
    ],
    [
        "random.instance.pod.log",
        ["random", "instance", "pod", "log"]
    ],
    [
        "pod.aio-job-0.1.0-preview-0.42.0-instance.aio-upgrade-status-job.log",
        ["pod", "aio-job-0.1.0-preview-0.42.0-instance", "aio-upgrade-status-job", "log"]
    ],
])
def test_split_name(input: str, expected: List[str]):
    result = split_name(input)
    assert result == expected