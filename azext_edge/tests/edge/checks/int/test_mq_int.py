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
    MqResourceKinds, MQTT_BROKER_API_V1B1
)
from .helpers import (
    assert_enumerate_resources,
    assert_general_eval_custom_resources,
    run_check_command
)
from ....helpers import get_kubectl_custom_items

logger = get_logger(__name__)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("resource_kind", [None, MqResourceKinds.BROKER.value, MqResourceKinds.BROKER_LISTENER.value])
# TODO: figure out if name match should be a general test vs each service (minimize test runs)
@pytest.mark.parametrize("resource_match", [None])
def test_mq_check(init_setup, detail_level, resource_match, resource_kind):
    post_deployment, broker_present = run_check_command(
        detail_level=detail_level,
        ops_service="broker",
        resource_api=MQTT_BROKER_API_V1B1,
        resource_kind=resource_kind,
        resource_match=resource_match
    )

    # overall api
    assert_enumerate_resources(
        post_deployment=post_deployment,
        description_name="MQTTBroker",
        key_name="Broker",
        resource_api=MQTT_BROKER_API_V1B1,
        resource_kinds=MqResourceKinds.list(),
        present=broker_present,
    )

    custom_resources = get_kubectl_custom_items(
        resource_api=MQTT_BROKER_API_V1B1,
        resource_match=resource_match,
        include_plural=True
    )
    assert_eval_broker(
        post_deployment=post_deployment,
        custom_resources=custom_resources,
        resource_kind=resource_kind
    )
    assert_eval_broker_listener(
        post_deployment=post_deployment,
        custom_resources=custom_resources,
        resource_kind=resource_kind
    )


def assert_eval_broker(
    post_deployment: Dict[str, Any],
    custom_resources: Dict[str, Any],
    resource_kind: str,
):
    resource_kind_present = resource_kind in [None, MqResourceKinds.BROKER.value]
    broker = custom_resources[MqResourceKinds.BROKER.value]
    assert_general_eval_custom_resources(
        post_deployment=post_deployment,
        items=broker,
        description_name="MQTT Broker",
        resource_api=MQTT_BROKER_API_V1B1,
        resource_kind_present=resource_kind_present
    )
    # TODO: add more as --as-object gets fixed, such as success conditions


def assert_eval_broker_listener(
    post_deployment: Dict[str, Any],
    custom_resources: Dict[str, Any],
    resource_kind: str,
):
    resource_kind_present = resource_kind in [None, MqResourceKinds.BROKER_LISTENER.value]
    instances = custom_resources[MqResourceKinds.BROKER_LISTENER.value]
    assert_general_eval_custom_resources(
        post_deployment=post_deployment,
        items=instances,
        description_name="MQTT Broker Listener",
        resource_api=MQTT_BROKER_API_V1B1,
        resource_kind_present=resource_kind_present,
    )
    # TODO: add more as --as-object gets fixed, such as success conditions
