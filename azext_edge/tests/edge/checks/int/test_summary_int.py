# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from azext_edge.edge.providers.check.common import ALL_NAMESPACES_TARGET
from azext_edge.edge.providers.edge_api import (
    DATAFLOW_API_V1,
    DEVICEREGISTRY_API_V1,
    MQ_ACTIVE_API,
    OPCUA_API_V1,
)

from ....helpers import run

pytestmark = pytest.mark.e2e


def test_summary_checks():
    command = "az iot ops check --as-object "
    result = run(command)
    assert result["title"] == "IoT Operations Summary"

    post = result.get("postDeployment")

    # assert only one check ran and overall status is success or skipped
    assert len(post) == 1
    checks = post[0]
    assert checks["description"] == "Service summary checks"
    # TODO - remove "warning" once dataflow profile no longer displays warning status by default for missing dataflows
    assert checks["status"] in ["success", "skipped", "warning"]

    # assert each service check is either success or skipped
    for api in ["Akri", MQ_ACTIVE_API, OPCUA_API_V1, DATAFLOW_API_V1, DEVICEREGISTRY_API_V1]:
        api_target = api.as_str() if api != "Akri" else "Akri"
        assert api_target in checks["targets"]
        service_checks = checks["targets"][api_target]

        valid_statuses = ["success", "skipped"]
        # TODO - remove once dataflow profile no longer displays warning status by default for missing dataflows
        if api == DATAFLOW_API_V1:
            valid_statuses.append("warning")
        assert service_checks.get(ALL_NAMESPACES_TARGET, {}).get("status") in valid_statuses
