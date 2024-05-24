# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from azure.cli.core.azclierror import CLIInternalError
from azext_edge.edge.providers.check.common import ResourceOutputDetailLevel
from azext_edge.edge.providers.edge_api import (
    OpcuaResourceKinds, OPCUA_API_V1
)
from .helpers import assert_enumerate_resources, assert_eval_core_service_runtime, assert_general_eval_custom_resources
from ....helpers import get_kubectl_custom_items, run
from ....generators import generate_names

logger = get_logger(__name__)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("resource_kind", OpcuaResourceKinds.list() + [None])
# TODO: figure out if name match should be a general test vs each service (minimize test runs)
@pytest.mark.parametrize("resource_match", [None, "*opc-supervisor*", generate_names()])
def test_opcua_check(init_setup, detail_level, resource_match, resource_kind):
    try:
        aio_check = run(f"kubectl api-resources --api-group={OPCUA_API_V1.group}")
        opcua_present = OPCUA_API_V1.group in aio_check
    except CLIInternalError:
        opcua_present = OPCUA_API_V1.is_deployed()
    ops_service = "opcua"
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
        description_name="OPC UA broker",
        key_name="OpcUaBroker",
        resource_api=OPCUA_API_V1,
        resource_kinds=OpcuaResourceKinds,
        present=opcua_present,
    )

    if not resource_kind:
        assert_eval_core_service_runtime(
            post_deployment=post_deployment,
            description_name="OPC UA broker",
            pod_prefix=["aio-opc-", "opcplc-"],
            resource_match=resource_match,
        )
    else:
        assert "evalCoreServiceRuntime" not in post_deployment

    custom_resources = get_kubectl_custom_items(
        resource_api=OPCUA_API_V1,
        resource_match=resource_match,
        include_plural=True
    )
    assert_eval_asset_types(
        post_deployment=post_deployment,
        configurations=custom_resources[OpcuaResourceKinds.ASSET_TYPE.value],
        resource_kind_present=resource_kind in [None, OpcuaResourceKinds.ASSET_TYPE.value]
    )


def assert_eval_asset_types(
    post_deployment: dict,
    configurations: dict,
    resource_kind_present: bool,
):
    assert_general_eval_custom_resources(
        post_deployment=post_deployment,
        items=configurations,
        description_name="OPC UA broker",
        resource_api=OPCUA_API_V1,
        resource_kind_present=resource_kind_present
    )
    # TODO: add more as --as-object gets fixed
