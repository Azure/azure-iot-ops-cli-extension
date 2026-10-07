# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from os import getenv
from shlex import split
from time import monotonic, sleep
from typing import Any, Dict
import pytest
from knack.log import get_logger
from azext_edge.edge.providers.check.common import ResourceOutputDetailLevel
from azext_edge.edge.providers.edge_api import (
    MqResourceKinds, MQ_ACTIVE_API
)
from .helpers import (
    assert_enumerate_resources,
    assert_general_eval_custom_resources,
    run_check_command
)
from ....helpers import assert_broker_diagnostics_service_absent, get_kubectl_custom_items, run
from ....settings import convert_flag

logger = get_logger(__name__)

pytestmark = pytest.mark.e2e

BROKER_RUNTIME_PREFIXES = (
    "aio-broker-diagnostics-probe",
    "aio-broker-frontend",
    "aio-broker-backend",
    "aio-broker-authentication",
    "aio-broker-health-manager",
    "aio-broker-operator",
)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("resource_kind", MqResourceKinds.list() + [None])
# TODO: figure out if name match should be a general test vs each service (minimize test runs)
@pytest.mark.parametrize("resource_match", [None])
def test_mq_check(cluster_connection, detail_level, resource_match, resource_kind):
    post_deployment, broker_present = run_check_command(
        detail_level=detail_level,
        ops_service="broker",
        resource_api=MQ_ACTIVE_API,
        resource_kind=resource_kind,
        resource_match=resource_match,
    )

    # overall api
    assert_enumerate_resources(
        post_deployment=post_deployment,
        description_name="MQTT Broker",
        key_name="Broker",
        resource_api=MQ_ACTIVE_API,
        resource_kinds=MqResourceKinds.list(),
        present=broker_present,
    )

    custom_resources = get_kubectl_custom_items(
        resource_api=MQ_ACTIVE_API,
        resource_match=resource_match,
        include_plural=True
    )
    assert_eval_broker(
        post_deployment=post_deployment,
        custom_resources=custom_resources,
        resource_kind=resource_kind
    )
    assert_eval_broker(post_deployment=post_deployment, custom_resources=custom_resources, resource_kind=resource_kind)
    assert_eval_broker_listener(
        post_deployment=post_deployment, custom_resources=custom_resources, resource_kind=resource_kind
    )


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
def test_mq_check_text_without_diagnostics_service(cluster_connection, detail_level):
    brokers = run(f"kubectl get brokers.{MQ_ACTIVE_API.group} -A -o json")
    if not brokers["items"]:
        pytest.skip("A deployed broker is required to check runtime health output.")

    output = run(
        "az iot ops check --post --svc broker --resources broker --resource-name '*' "
        f"--detail-level {detail_level}"
    )

    assert isinstance(output, str)
    assert "MQTT Brokers" in output
    assert "Runtime Health" in output
    assert "aio-broker-diagnostics-service" not in output
    assert "aio-broker-diagnostics-probe" in output


@pytest.mark.skipif(
    not convert_flag(getenv("azext_edge_broker_diagnostics_removal")),
    reason="Requires the explicit broker-diagnostics-removal scenario and a removal-release backend.",
)
def test_mq_check_diagnostics_removal(cluster_connection):
    brokers = run(
        split(f"kubectl get brokers.{MQ_ACTIVE_API.group} -A -o json --request-timeout=20s"),
        shell_mode=False,
        timeout=30,
    )
    assert brokers["items"], "The diagnostics-removal scenario requires a deployed broker; no brokers were found."
    namespaces = {broker["metadata"]["namespace"] for broker in brokers["items"]}
    assert_broker_diagnostics_service_absent(namespaces)
    _wait_for_broker_summary_health()

    for detail_level in ResourceOutputDetailLevel.list():
        command = (
            "az iot ops check --post --svc broker --resources broker --resource-name '*' "
            f"--detail-level {detail_level}"
        )
        result = run(split(f"{command} --as-object"), shell_mode=False, timeout=60)
        checks = [check for check in result["postDeployment"] if check["name"] == "evalBrokers"]
        assert len(checks) == 1, f"Expected one broker evaluation: {result}"
        broker_check = checks[0]
        assert broker_check["status"] == "success", f"Broker evaluation is not healthy: {broker_check}"
        targets = broker_check["targets"][f"brokers.{MQ_ACTIVE_API.group}"]
        assert set(targets) == namespaces, f"Broker evaluation namespaces do not match deployed brokers: {targets}"
        for target in targets.values():
            assert target["status"] == "success", f"Broker namespace is not healthy: {target}"
            evaluations = target["evaluations"]
            assert evaluations and all(evaluation["status"] == "success" for evaluation in evaluations), target
            names = {evaluation.get("name", "") for evaluation in evaluations}
            assert not any("aio-broker-diagnostics-service" in name for name in names), target
            for prefix in BROKER_RUNTIME_PREFIXES:
                assert any(name.startswith(f"pod/{prefix}-") for name in names), (
                    f"Missing runtime health evaluation for {prefix}: {target}"
                )
            assert any("spec.diagnostics" in evaluation.get("value", {}) for evaluation in evaluations), (
                f"Missing broker diagnostics configuration evaluation: {target}"
            )

        output = run(split(command), shell_mode=False, timeout=60)
        assert isinstance(output, str), f"Expected human-readable broker output: {output}"
        assert "aio-broker-diagnostics-service" not in output, output
        assert "Runtime Health" in output, output
        for prefix in BROKER_RUNTIME_PREFIXES:
            assert prefix in output, f"Missing {prefix} in runtime health output:\n{output}"
        if detail_level != ResourceOutputDetailLevel.summary.value:
            assert "Broker Diagnostics" in output, output

    assert_broker_diagnostics_service_absent(namespaces)


def _wait_for_broker_summary_health():
    deadline = monotonic() + 300
    broker_target = None
    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            pytest.fail(f"Broker summary did not become healthy within 300s. Last broker result: {broker_target}")
        result = run(split("az iot ops check --post --as-object"), shell_mode=False, timeout=min(60, remaining))
        checks = [check for check in result["postDeployment"] if check["name"] == "evalAIOSummary"]
        assert len(checks) == 1, f"Expected one service summary: {result}"
        broker_target = checks[0]["targets"][MQ_ACTIVE_API.as_str()]["_all_"]
        assert any("evalBrokers" in evaluation.get("value", {}) for evaluation in broker_target["evaluations"]), (
            f"Broker summary has no broker evaluation: {broker_target}"
        )
        if broker_target["status"] == "success":
            assert all(evaluation["status"] == "success" for evaluation in broker_target["evaluations"]), broker_target
            return
        logger.info("Waiting for broker health; current broker summary: %s", broker_target)
        sleep(min(10, max(0, deadline - monotonic())))


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
        resource_api=MQ_ACTIVE_API,
        resource_kind_present=resource_kind_present
    )
    if resource_kind_present:
        targets = post_deployment["evalBrokers"]["targets"][f"brokers.{MQ_ACTIVE_API.group}"]
        for namespace_target in targets.values():
            for evaluation in namespace_target["evaluations"]:
                assert "aio-broker-diagnostics-service" not in evaluation.get("name", "")


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
        resource_api=MQ_ACTIVE_API,
        resource_kind_present=resource_kind_present,
    )
    # TODO: add more as --as-object gets fixed, such as success conditions
