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
    OpcuaResourceKinds, OPCUA_API_V1
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

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("resource_kind", OpcuaResourceKinds.list() + [None])
# TODO: figure out if name match should be a general test vs each service (minimize test runs)
@pytest.mark.parametrize("resource_match", [None, "*opc-supervisor*", generate_names()])
def test_opcua_check(init_setup, detail_level, resource_match, resource_kind):
    post_deployment, opcua_present = run_check_command(
        detail_level=detail_level,
        ops_service="opcua",
        resource_api=OPCUA_API_V1,
        resource_kind=resource_kind,
        resource_match=resource_match
    )

    # overall api
    assert_enumerate_resources(
        post_deployment=post_deployment,
        description_name="OPC UA broker",
        key_name="OpcUaBroker",
        resource_api=OPCUA_API_V1,
        resource_kinds=OpcuaResourceKinds.list(),
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
        custom_resources=custom_resources,
        resource_kind=resource_kind
    )


def assert_eval_asset_types(
    post_deployment: dict,
    custom_resources: Dict[str, Any],
    resource_kind: str,
):
    asset_types = custom_resources[OpcuaResourceKinds.ASSET_TYPE.value]
    resource_kind_present = resource_kind in [None, OpcuaResourceKinds.ASSET_TYPE.value]
    assert_general_eval_custom_resources(
        post_deployment=post_deployment,
        items=asset_types,
        description_name="OPC UA broker",
        resource_api=OPCUA_API_V1,
        resource_kind_present=resource_kind_present
    )
    # TODO: add more as --as-object gets fixed
