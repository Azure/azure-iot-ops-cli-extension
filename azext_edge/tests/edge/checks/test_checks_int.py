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
    AkriResourceKinds,
    DataProcessorResourceKinds,
    LnmResourceKinds,
    MqResourceKinds,
    OpcuaResourceKinds,
)
from ...helpers import run

logger = get_logger(__name__)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("services_map", [
    ("akri", AkriResourceKinds.list()),
    ("dataprocessor", DataProcessorResourceKinds.list()),
    ("lnm", LnmResourceKinds.list()),
    ("mq", [
        MqResourceKinds.BROKER.value,
        MqResourceKinds.BROKER_LISTENER.value,
        MqResourceKinds.DIAGNOSTIC_SERVICE.value,
        MqResourceKinds.KAFKA_CONNECTOR.value,
    ]),
    ("opcua", OpcuaResourceKinds.list())
])
@pytest.mark.parametrize("post", [None, False, True])
@pytest.mark.parametrize("pre", [None, False, True])
def test_check(init_setup, detail_level, services_map, post, pre):
    ops_service, resources = services_map
    resources = " ".join(resources)
    command = f"az iot ops check --as-object --detail-level {detail_level} --ops-service {ops_service} "\
        f"--resources {resources}"
    if pre is not None:
        command += f" --pre {pre}"
    if post is not None:
        command += f" --post {post}"
    result = run(command)

    expected_title = "Evaluation for {[bright_blue]" + ops_service + "[/bright_blue]} service deployment"
    expected_precheck_title = "[bright_blue]IoT Operations readiness[/bright_blue]"
    expected_pre = not post if pre is None else pre
    expected_post = not pre if post is None else post
    assert result["title"] == expected_title if expected_post else expected_precheck_title
    
    if pre is None and not post:
        try:
            aio_check = run("kubectl api-resources --api-group=orchestrator.iotoperations.azure.com")
            expected_pre = "orchestrator.iotoperations.azure.com" not in aio_check
        except CLIInternalError:
            from azext_edge.edge.providers.edge_api.orc import ORC_API_V1
            expected_pre = not ORC_API_V1.is_deployed()

    assert bool(result.get("preDeployment")) == expected_pre
    assert bool(result.get("postDeployment")) == expected_post

    # TODO: see how specific to get - for now keep it simple
