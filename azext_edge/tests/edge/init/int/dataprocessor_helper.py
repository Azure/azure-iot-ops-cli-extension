# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List, Optional
from .helper import get_resource_from_partial_id, ResourceKeys


def assert_dataprocessor_args(
    resource_group: str,
    cluster_name: str,
    init_resources: List[str],
    include_dp: Optional[bool] = None,
    dp_instance: Optional[str] = None,
    **_
):
    include_dp = include_dp or False
    resources = [res for res in init_resources if res.startswith(ResourceKeys.dataprocessor.value)]
    assert bool(resources) is include_dp
    if not include_dp:
        return

    expected_name = dp_instance or (f"{cluster_name}-ops-init-processor")
    assert len(resources) == 1
    assert resources[0].endswith(expected_name)
    # nothing interesting here.
    get_resource_from_partial_id(resources[0], resource_group)
