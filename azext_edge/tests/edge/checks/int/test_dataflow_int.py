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
    DataflowResourceKinds, DATAFLOW_API_V1B1
)
from .helpers import (
    assert_enumerate_resources,
    assert_eval_core_service_runtime,
    assert_general_eval_custom_resources,
    run_check_command
)
from ....helpers import get_kubectl_custom_items

logger = get_logger(__name__)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("resource_kind", DataflowResourceKinds.list() + [None])
def test_dataflow_check(init_setup, detail_level, resource_kind):
    post_deployment, dataflow_present = run_check_command(
        detail_level=detail_level,
        ops_service="dataflow",
        resource_api=DATAFLOW_API_V1B1,
        resource_kind=resource_kind
    )

    # overall api
    assert_enumerate_resources(
        post_deployment=post_deployment,
        description_name="Dataflow",
        key_name="Dataflow",
        resource_api=DATAFLOW_API_V1B1,
        resource_kinds=DataflowResourceKinds.list(),
        present=dataflow_present,
    )

    if not resource_kind:
        assert_eval_core_service_runtime(
            post_deployment=post_deployment,
            description_name="Dataflow",
            pod_prefix="aio-dataflow-operator-",
        )
    else:
        assert "evalCoreServiceRuntime" not in post_deployment

    custom_resources = get_kubectl_custom_items(
        resource_api=DATAFLOW_API_V1B1,
        include_plural=True
    )
    assert_eval_dataflows(
        post_deployment=post_deployment,
        custom_resources=custom_resources,
        resource_kind=resource_kind
    )
    assert_eval_dataflow_endpoints(
        post_deployment=post_deployment,
        custom_resources=custom_resources,
        resource_kind=resource_kind
    )
    assert_eval_dataflow_profiles(
        post_deployment=post_deployment,
        custom_resources=custom_resources,
        resource_kind=resource_kind
    )


def assert_eval_dataflows(
    post_deployment: Dict[str, Any],
    custom_resources: Dict[str, Any],
    resource_kind: str,
):
    resource_kind_present = resource_kind in [None, DataflowResourceKinds.DATAFLOW.value]
    dataflows = custom_resources[DataflowResourceKinds.DATAFLOW.value]
    assert_general_eval_custom_resources(
        post_deployment=post_deployment,
        items=dataflows,
        description_name="Dataflows",
        resource_api=DATAFLOW_API_V1B1,
        resource_kind_present=resource_kind_present
    )
    # TODO: add more as --as-object gets fixed, such as success conditions


def assert_eval_dataflow_endpoints(
    post_deployment: Dict[str, Any],
    custom_resources: Dict[str, Any],
    resource_kind: str,
):
    resource_kind_present = resource_kind in [None, DataflowResourceKinds.DATAFLOWENDPOINT.value]
    endpoints = custom_resources[DataflowResourceKinds.DATAFLOWENDPOINT.value]
    assert_general_eval_custom_resources(
        post_deployment=post_deployment,
        items=endpoints,
        description_name="Dataflow Endpoints",
        resource_api=DATAFLOW_API_V1B1,
        resource_kind_present=resource_kind_present,
    )
    # TODO: add more as --as-object gets fixed, such as success conditions


def assert_eval_dataflow_profiles(
    post_deployment: Dict[str, Any],
    custom_resources: Dict[str, Any],
    resource_kind: str,
):
    resource_kind_present = resource_kind in [None, DataflowResourceKinds.DATAFLOWPROFILE.value]
    profiles = custom_resources[DataflowResourceKinds.DATAFLOWPROFILE.value]
    assert_general_eval_custom_resources(
        post_deployment=post_deployment,
        items=profiles,
        description_name="Dataflow Profiles",
        resource_api=DATAFLOW_API_V1B1,
        resource_kind_present=resource_kind_present,
    )
    # TODO: add more as --as-object gets fixed, such as success conditions
