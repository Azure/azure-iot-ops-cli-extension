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
    MqResourceKinds, MQ_ACTIVE_API
)
from .helpers import (
    assert_enumerate_resources,
    assert_eval_core_service_runtime,
    assert_general_eval_custom_resources,
    run_check_command
)
from ....helpers import get_kubectl_custom_items, run
from ....generators import generate_names

logger = get_logger(__name__)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("resource_kind", [None] + MqResourceKinds.list())
# TODO: figure out if name match should be a general test vs each service (minimize test runs)
@pytest.mark.parametrize("resource_match", [None, "*mq-diagnostic*", generate_names()])
def test_mq_check(init_setup, detail_level, resource_match, resource_kind):
    post_deployment, mq_present = run_check_command(
        detail_level=detail_level,
        ops_service="mq",
        resource_api=MQ_ACTIVE_API,
        resource_kind=resource_kind,
        resource_match=resource_match
    )

    # overall api
    resource_list = MqResourceKinds.list()
    resource_list.remove("brokerdiagnostic")
    assert_enumerate_resources(
        post_deployment=post_deployment,
        description_name="MQ",
        key_name="Mq",
        resource_api=MQ_ACTIVE_API,
        resource_kinds=resource_list,
        present=mq_present,
    )

    # if not resource_kind:
    #     assert_eval_core_service_runtime(
    #         post_deployment=post_deployment,
    #         description_name="MQ",
    #         pod_prefix=["aio-opc-", "opcplc-"],
    #         resource_match=resource_match,
    #     )
    # else:
    #     assert "evalCoreServiceRuntime" not in post_deployment

    custom_resources = get_kubectl_custom_items(
        resource_api=MQ_ACTIVE_API,
        resource_match=resource_match,
        include_plural=True
    )
    assert_eval_brokers(
        post_deployment=post_deployment,
        custom_resources=custom_resources,
        resource_kind=resource_kind
    )


def assert_eval_brokers(
    post_deployment: Dict[str, Any],
    custom_resources: Dict[str, Any],
    resource_kind: str,
):
    resource_kind_present = resource_kind in [None, MqResourceKinds.BROKER.value]
    brokers = custom_resources[MqResourceKinds.BROKER.value]
    assert_general_eval_custom_resources(
        post_deployment=post_deployment,
        items=brokers,
        description_name="MQ",
        resource_api=MQ_ACTIVE_API,
        resource_kind_present=resource_kind_present
    )
    import pdb; pdb.set_trace()
    if not resource_kind_present:
        return

    namespace_dict = brokers["targets"]
    for namespace in namespace_dict.items():
        pass

    # TODO: add more as --as-object gets fixed, such as success conditions
