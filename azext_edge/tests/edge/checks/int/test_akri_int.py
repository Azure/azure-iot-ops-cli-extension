# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict
import pytest
from knack.log import get_logger
from azext_edge.edge.providers.check.common import ResourceOutputDetailLevel
from azext_edge.edge.providers.edge_api import AKRI_API_V0
from .helpers import (
    assert_enumerate_resources,
    assert_eval_core_service_runtime,
    run_check_command,
)
from ....generators import generate_names

logger = get_logger(__name__)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
# TODO: figure out if name match should be a general test vs each service (minimize test runs)
@pytest.mark.parametrize("resource_match", [None, "aio-akri*", generate_names()])
def test_akri_check(init_setup, detail_level, resource_match):
    post_deployment, akri_present = run_check_command(
        detail_level=detail_level,
        ops_service="akri",
        resource_api=AKRI_API_V0,
        resource_match=resource_match,
    )

    # overall api
    assert_enumerate_resources(
        post_deployment=post_deployment,
        description_name="Akri",
        key_name="Akri",
        resource_api=AKRI_API_V0,
        resource_kinds=[],
        present=akri_present,
    )

    assert_eval_core_service_runtime(
        post_deployment=post_deployment,
        description_name="Akri",
        pod_prefix="aio-akri-",
        resource_match=resource_match,
    )
