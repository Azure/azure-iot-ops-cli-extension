# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from azext_edge.edge.providers.check.common import ALL_NAMESPACES_TARGET

from ....helpers import run


def test_summary_checks():
    command = "az iot ops check --as-object "
    result = run(command)
    assert result["title"] == "IoT Operations Summary"

    post = result.get("postDeployment")

    # assert only one check ran and overall status is success or skipped
    assert len(post) == 1
    checks = post[0]
    assert checks["description"] == "AIO components"
    assert checks["status"] in ["success", "skipped"]

    # assert each service check is either success or skipped
    for service in ["Akri", "Broker", "OPCUA", "Dataflow", "DeviceRegistry"]:
        assert service in checks["targets"]
        service_checks = checks["targets"][service]
        assert service_checks.get(ALL_NAMESPACES_TARGET, {}).get("status") in ["success", "skipped"]
