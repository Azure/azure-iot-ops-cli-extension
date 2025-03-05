# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from azext_edge.edge.providers.check.common import ResourceOutputDetailLevel
from .helpers import (
    assert_eval_core_service_runtime,
    get_pods,
    run_check_command,
)
from ....generators import generate_names

logger = get_logger(__name__)

pytestmark = pytest.mark.e2e
AKRI_PREFIX = "aio-akri-"


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
# TODO: figure out if name match should be a general test vs each service (minimize test runs)
@pytest.mark.parametrize("resource_match", [None, "aio-akri*", generate_names()])
def test_akri_check(cluster_connection, detail_level, resource_match):
    pre_check_pods = get_pods(pod_prefix=AKRI_PREFIX, resource_match=resource_match)
    post_deployment, _ = run_check_command(
        detail_level=detail_level,
        ops_service="akri",
        resource_match=resource_match,
    )

    assert_eval_core_service_runtime(
        check_results=post_deployment,
        description_name="Akri",
        pod_prefix=AKRI_PREFIX,
        pre_check_pods=pre_check_pods,
        resource_match=resource_match,
    )
