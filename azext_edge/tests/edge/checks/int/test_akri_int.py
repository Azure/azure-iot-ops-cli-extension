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
    AkriResourceKinds, AKRI_API_V0
)
from .helpers import (
    assert_enumerate_resources,
    assert_eval_core_service_runtime,
    assert_general_eval_custom_resources,
    run_check_command
)
from ....helpers import get_kubectl_custom_items
from ....generators import generate_names

logger = get_logger(__name__)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("resource_kind", AkriResourceKinds.list() + [None])
# TODO: figure out if name match should be a general test vs each service (minimize test runs)
@pytest.mark.parametrize("resource_match", [None, "*otel*", "akri-opcua*", generate_names()])
def test_akri_check(init_setup, detail_level, resource_match, resource_kind):
    post_deployment, akri_present = run_check_command(
        detail_level=detail_level,
        ops_service="akri",
        resource_api=AKRI_API_V0,
        resource_kind=resource_kind,
        resource_match=resource_match
    )

    # overall api
    assert_enumerate_resources(
        post_deployment=post_deployment,
        description_name="Akri",
        key_name="Akri",
        resource_api=AKRI_API_V0,
        resource_kinds=AkriResourceKinds.list(),
        present=akri_present,
    )

    if not resource_kind:
        assert_eval_core_service_runtime(
            post_deployment=post_deployment,
            description_name="Akri",
            pod_prefix="aio-akri-",
            resource_match=resource_match,
        )
    else:
        assert "evalCoreServiceRuntime" not in post_deployment

    custom_resources = get_kubectl_custom_items(
        resource_api=AKRI_API_V0,
        resource_match=resource_match,
        include_plural=True
    )
    assert_eval_configurations(
        post_deployment=post_deployment,
        custom_resources=custom_resources,
        resource_kind=resource_kind
    )
    assert_eval_instances(
        post_deployment=post_deployment,
        instances=custom_resources,
        resource_kind=resource_kind
    )


def assert_eval_configurations(
    post_deployment: Dict[str, Any],
    custom_resources: Dict[str, Any],
    resource_kind: str,
):
    resource_kind_present = resource_kind in [None, AkriResourceKinds.CONFIGURATION.value]
    configurations = custom_resources[AkriResourceKinds.CONFIGURATION.value]
    assert_general_eval_custom_resources(
        post_deployment=post_deployment,
        items=configurations,
        description_name="Akri",
        resource_api=AKRI_API_V0,
        resource_kind_present=resource_kind_present
    )
    # TODO: add more as --as-object gets fixed, such as success conditions


def assert_eval_instances(
    post_deployment: Dict[str, Any],
    custom_resources: Dict[str, Any],
    resource_kind: str,
):
    resource_kind_present = resource_kind in [None, AkriResourceKinds.INSTANCE.value]
    instances = custom_resources[AkriResourceKinds.INSTANCE.value]
    assert_general_eval_custom_resources(
        post_deployment=post_deployment,
        items=instances,
        description_name="Akri",
        resource_api=AKRI_API_V0,
        resource_kind_present=resource_kind_present,
        include_all_namespace=True
    )
    # TODO: add more as --as-object gets fixed, such as success conditions
