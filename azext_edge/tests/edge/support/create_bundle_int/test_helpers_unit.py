# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from typing import List
from .helpers import assert_file_names, convert_file_names, split_name


@pytest.mark.parametrize("input, expected", [
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
    [
        "pod.aio-job-0.1.0-preview-0.42.0.log",
        ["pod", "aio-job-0.1.0-preview-0.42.0", "log"]
    ]
])
def test_split_name(input: str, expected: List[str]):
    result = split_name(input)
    assert result == expected


@pytest.mark.parametrize("pod_name", [
    "aio-akri-upgrade-status-job-1.4.0-preview.2-lktm8",
    "aio-akri-upgrade-status-job-1.4.14-lktm8",
    "aio-akri-operator-0",
])
@pytest.mark.parametrize("suffix, descriptors, extension", [
    ("yaml", [], "yaml"),
    ("aio-akri-upgrade-status-job.log", ["aio-akri-upgrade-status-job"], "log"),
    ("aio-akri-upgrade-status-job.previous.log", ["aio-akri-upgrade-status-job", "previous"], "log"),
    ("aio-akri-upgrade-status-job.init.log", ["aio-akri-upgrade-status-job", "init"], "log"),
    ("metric.yaml", ["metric"], "yaml"),
])
def test_pod_filenames_preserve_versioned_names(pod_name, suffix, descriptors, extension):
    filename = f"pod.{pod_name}.{suffix}"
    assert split_name(filename) == ["pod", pod_name, *descriptors, extension]
    assert_file_names([filename])

    file_type = "podmetric" if suffix == "metric.yaml" else "pod"
    expected = {"name": pod_name, "full_name": filename, "extension": extension}
    if descriptors:
        expected["descriptor"] = descriptors[0]
    if len(descriptors) == 2:
        expected["sub_descriptor"] = descriptors[1]
    assert convert_file_names([filename]) == {file_type: [expected]}
