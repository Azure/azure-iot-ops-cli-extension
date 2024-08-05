# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List
from .helper import ResourceKeys


def assert_orchestrator_args(
    cluster_name: str,
    init_resources: List[str],
    **_
):
    resources = [res for res in init_resources if res.startswith(ResourceKeys.orchestrator.value)]
    assert len(resources) == 1

    assert resources[0].endswith(f"{cluster_name}-observability")
