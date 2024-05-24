# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict
import pytest
from knack.log import get_logger
from azure.cli.core.azclierror import CLIInternalError
from azext_edge.edge.providers.check.common import ResourceOutputDetailLevel
from azext_edge.edge.providers.edge_api import (
    AkriResourceKinds, AKRI_API_V0
)
from .helpers import (
    assert_enumerate_resources, assert_eval_core_service_runtime, assert_general_eval_custom_resources
)
from ....helpers import get_kubectl_custom_items, run
from ....generators import generate_names

logger = get_logger(__name__)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("resource_kind", AkriResourceKinds.list() + [None])
# TODO: figure out if name match should be a general test vs each service (minimize test runs)
@pytest.mark.parametrize("resource_match", [None, "*otel*", "akri-opcua*", generate_names()])
def test_akri_check(init_setup, detail_level, resource_match, resource_kind):
    try:
        aio_check = run(f"kubectl api-resources --api-group={AKRI_API_V0.group}")
        akri_present = AKRI_API_V0.group in aio_check
    except CLIInternalError:
        akri_present = AKRI_API_V0.is_deployed()
    ops_service = "akri"
    # note that the text decoder really does not like the emojis
    command = f"az iot ops check --as-object --ops-service {ops_service} --detail-level {detail_level} "
    if resource_kind:
        command += f"--resources {resource_kind} "
    if resource_match:
        command += f"--resource-name {resource_match} "
    result = run(command)

    post_deployment = {cond["name"]: cond for cond in result["postDeployment"]}

    # overall api
    assert_enumerate_resources(
        post_deployment=post_deployment,
        description_name=ops_service.capitalize(),
        key_name=ops_service.capitalize(),
        resource_api=AKRI_API_V0,
        resource_kinds=AkriResourceKinds,
        present=akri_present,
    )

    if not resource_kind:
        assert_eval_core_service_runtime(
            post_deployment=post_deployment,
            description_name=ops_service.capitalize(),
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
        configurations=custom_resources[AkriResourceKinds.CONFIGURATION.value],
        resource_kind_present=resource_kind in [None, AkriResourceKinds.CONFIGURATION.value]
    )
    assert_eval_instances(
        post_deployment=post_deployment,
        instances=custom_resources[AkriResourceKinds.INSTANCE.value],
        resource_kind_present=resource_kind in [None, AkriResourceKinds.INSTANCE.value]
    )


def assert_eval_configurations(
    post_deployment: Dict[str, Any],
    configurations: Dict[str, Any],
    resource_kind_present: bool,
):
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
    instances: Dict[str, Any],
    resource_kind_present: bool,
):
    assert_general_eval_custom_resources(
        post_deployment=post_deployment,
        items=instances,
        description_name="Akri",
        resource_api=AKRI_API_V0,
        resource_kind_present=resource_kind_present,
        include_all_namespace=True
    )
    # TODO: add more as --as-object gets fixed, such as success conditions
