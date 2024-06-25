# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict
import pytest
from knack.log import get_logger
from azext_edge.edge.providers.check.common import ResourceOutputDetailLevel
from azext_edge.edge.providers.edge_api import (
    DataProcessorResourceKinds, DATA_PROCESSOR_API_V1
)
from .helpers import (
    assert_enumerate_resources,
    run_check_command
)
from ....generators import generate_names

logger = get_logger(__name__)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("resource_kind", DataProcessorResourceKinds.list() + [None])
# TODO: figure out if name match should be a general test vs each service (minimize test runs)
@pytest.mark.parametrize("resource_match", [None, "*refdata*", "aio-dp*", generate_names()])
def test_akri_check(init_setup, detail_level, resource_match, resource_kind):
    post_deployment, dp_present = run_check_command(
        detail_level=detail_level,
        ops_service="dataprocessor",
        resource_api=DATA_PROCESSOR_API_V1,
        resource_kind=resource_kind,
        resource_match=resource_match
    )

    # overall api
    assert_enumerate_resources(
        post_deployment=post_deployment,
        description_name="Data Processor",
        key_name="DataProcessor",
        resource_api=DATA_PROCESSOR_API_V1,
        resource_kinds=DataProcessorResourceKinds.list(),
        present=dp_present,
    )