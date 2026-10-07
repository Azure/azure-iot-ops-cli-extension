# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy

import pytest
from azure.cli.core.azclierror import CLIInternalError

from ... import helpers
from .int import test_mq_int as live_checks


@pytest.fixture
def removal_cluster(mocker):
    broker_target = {
        "status": "success",
        "evaluations": [
            {"name": "default", "status": "success", "value": {"spec.diagnostics": {"logs": {"level": "info"}}}},
            *(
                {"name": f"pod/{prefix}-0", "status": "success"}
                for prefix in live_checks.BROKER_RUNTIME_PREFIXES
            ),
        ],
    }
    summary_target = {
        "status": "success",
        "evaluations": [{"status": "success", "value": {"evalBrokers": "success"}}],
    }
    responses = {
        "brokers": {"items": [{"metadata": {"name": "default", "namespace": "ns"}}]},
        "resources": {"items": []},
        "check": {
            "postDeployment": [{
                "name": "evalBrokers",
                "status": "success",
                "targets": {f"brokers.{live_checks.MQ_ACTIVE_API.group}": {"ns": broker_target}},
            }],
        },
        "summary": {
            "postDeployment": [{
                "name": "evalAIOSummary",
                "status": "error",
                "targets": {
                    live_checks.MQ_ACTIVE_API.as_str(): {"_all_": summary_target},
                    "unrelated-service": {"_all_": {"status": "error"}},
                },
            }],
        },
        "text": "Runtime Health\nBroker Diagnostics\n" + "\n".join(live_checks.BROKER_RUNTIME_PREFIXES),
    }

    def run(command, **kwargs):
        command = " ".join(command)
        if command.startswith("kubectl get brokers."):
            return responses["brokers"]
        if command.startswith("kubectl get services,pods"):
            return responses["resources"]
        if command == "az iot ops check --post --as-object":
            return responses["summary"]
        if command.endswith("--as-object"):
            return responses["check"]
        return responses["text"]

    mocked_run = mocker.patch.object(live_checks, "run", side_effect=run)
    mocker.patch.object(helpers, "run", mocked_run)
    return {
        "responses": responses,
        "broker_target": broker_target,
        "summary_target": summary_target,
        "run": mocked_run,
    }


def test_removal_regression_checks_all_modes_and_ignores_other_service_health(removal_cluster):
    live_checks.test_mq_check_diagnostics_removal(cluster_connection=None)

    calls = removal_cluster["run"].call_args_list
    assert len(calls) == 10
    assert all(0 < call.kwargs["timeout"] <= 60 for call in calls)
    assert all(call.kwargs["shell_mode"] is False for call in calls)
    commands = [" ".join(call.args[0]) for call in calls]
    assert sum(command.startswith("kubectl get services,pods") for command in commands) == 2
    for detail_level in ("0", "1", "2"):
        assert sum(f"--detail-level {detail_level}" in command for command in commands) == 2


@pytest.mark.parametrize(
    "kind, name",
    [
        ("Service", "aio-broker-diagnostics-service"),
        ("Pod", "aio-broker-diagnostics-service-abc"),
        ("StatefulSet", "aio-broker-diagnostics-service"),
    ],
)
def test_removal_regression_rejects_retired_resources(removal_cluster, kind, name):
    removal_cluster["responses"]["resources"]["items"] = [
        {"kind": kind, "metadata": {"namespace": "ns", "name": name}},
    ]

    with pytest.raises(AssertionError, match="Retired resources still present"):
        live_checks.test_mq_check_diagnostics_removal(cluster_connection=None)

    assert removal_cluster["run"].call_count == 2


def test_removal_regression_rejects_missing_broker(removal_cluster):
    removal_cluster["responses"]["brokers"]["items"] = []
    with pytest.raises(AssertionError, match="requires a deployed broker"):
        live_checks.test_mq_check_diagnostics_removal(cluster_connection=None)


@pytest.mark.parametrize(
    "missing_name",
    ["default", *(f"pod/{prefix}-0" for prefix in live_checks.BROKER_RUNTIME_PREFIXES)],
)
def test_removal_regression_rejects_missing_evaluations(removal_cluster, missing_name):
    target = removal_cluster["broker_target"]
    target["evaluations"] = [evaluation for evaluation in target["evaluations"] if evaluation["name"] != missing_name]
    with pytest.raises(AssertionError, match="Missing"):
        live_checks.test_mq_check_diagnostics_removal(cluster_connection=None)


def test_removal_regression_rejects_unhealthy_structured_result(removal_cluster):
    removal_cluster["responses"]["check"]["postDeployment"][0]["status"] = "warning"
    with pytest.raises(AssertionError, match="Broker evaluation is not healthy"):
        live_checks.test_mq_check_diagnostics_removal(cluster_connection=None)


def test_removal_regression_rejects_retired_evaluation(removal_cluster):
    removal_cluster["broker_target"]["evaluations"].append(
        {"name": "service/aio-broker-diagnostics-service", "status": "success"}
    )
    with pytest.raises(AssertionError):
        live_checks.test_mq_check_diagnostics_removal(cluster_connection=None)


def test_removal_regression_rejects_retired_text(removal_cluster):
    removal_cluster["responses"]["text"] += "\naio-broker-diagnostics-service not detected"
    with pytest.raises(AssertionError):
        live_checks.test_mq_check_diagnostics_removal(cluster_connection=None)


def test_broker_summary_readiness_retries_then_succeeds(mocker, removal_cluster):
    sleep = mocker.patch.object(live_checks, "sleep")
    healthy_result = removal_cluster["responses"]["summary"]
    pending_result = deepcopy(healthy_result)
    pending_result["postDeployment"][0]["targets"][live_checks.MQ_ACTIVE_API.as_str()]["_all_"]["status"] = "warning"
    removal_cluster["run"].side_effect = [pending_result, healthy_result]

    live_checks._wait_for_broker_summary_health()

    assert removal_cluster["run"].call_count == 2
    sleep.assert_called_once_with(10)


def test_broker_summary_readiness_has_a_deadline(mocker, removal_cluster):
    mocker.patch.object(live_checks, "monotonic", side_effect=[0, 0, 0, 300])
    sleep = mocker.patch.object(live_checks, "sleep")
    removal_cluster["summary_target"]["status"] = "warning"

    with pytest.raises(pytest.fail.Exception, match="did not become healthy within 300s"):
        live_checks._wait_for_broker_summary_health()

    removal_cluster["run"].assert_called_once_with(
        ["az", "iot", "ops", "check", "--post", "--as-object"], shell_mode=False, timeout=60
    )
    sleep.assert_called_once_with(10)


def test_broker_summary_readiness_does_not_hide_cli_errors(mocker, removal_cluster):
    sleep = mocker.patch.object(live_checks, "sleep")
    removal_cluster["run"].side_effect = CLIInternalError("Access denied")
    with pytest.raises(CLIInternalError, match="Access denied"):
        live_checks._wait_for_broker_summary_health()
    sleep.assert_not_called()


def test_broker_summary_readiness_rejects_empty_evaluations(removal_cluster):
    removal_cluster["summary_target"]["evaluations"] = []
    with pytest.raises(AssertionError, match="has no broker evaluation"):
        live_checks._wait_for_broker_summary_health()
