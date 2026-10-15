# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from copy import deepcopy
from subprocess import CompletedProcess, TimeoutExpired
from zipfile import ZipFile

import pytest
import yaml

from ... import helpers
from .create_bundle_int import test_mq_int as live_bundles


@pytest.fixture
def removal_bundle(mocker, tmp_path):
    broker = {
        "kind": "Broker",
        "metadata": {"namespace": "ns", "name": "default", "uid": "broker-uid"},
    }
    pod = {
        "kind": "Pod",
        "metadata": {
            "namespace": "ns", "name": "aio-broker-backend-0", "uid": "pod-uid",
            "labels": {live_bundles.MQ_LABEL[0]: live_bundles.MQ_LABEL[1]},
        },
        "status": {
            "phase": "Running",
            "containerStatuses": [{"name": "backend", "state": {"running": {}}}],
        },
        "spec": {"containers": [{"name": "backend"}]},
    }
    service = {
        "kind": "Service",
        "metadata": {
            "namespace": "ns", "name": "aio-broker", "uid": "svc-uid",
            "labels": {live_bundles.MQ_LABEL[0]: live_bundles.MQ_LABEL[1]},
        },
    }
    statefulset = {
        "kind": "StatefulSet",
        "metadata": {
            "namespace": "ns", "name": "aio-broker-backend", "uid": "sts-uid",
            "labels": {live_bundles.MQ_LABEL[0]: live_bundles.MQ_LABEL[1]},
        },
    }
    files = {
        f"ns/broker/broker.{live_bundles.MQ_ACTIVE_API.version}.default.yaml": yaml.safe_dump(broker),
        "ns/broker/pod.aio-broker-backend-0.yaml": yaml.safe_dump(pod),
        "ns/broker/pod.aio-broker-backend-0.backend.log": "broker log",
        "ns/broker/service.aio-broker.yaml": yaml.safe_dump(service),
        "ns/broker/statefulset.aio-broker-backend.yaml": yaml.safe_dump(statefulset),
    }
    state = {
        "brokers": [broker],
        "resources": [pod, service, statefulset],
        "files": files,
        "warning": "WARNING: Broker traces unavailable in namespace 'ns'",
        "stderr": "",
        "returncode": 0,
        "logs": {"backend": "broker log"},
        "log_returncode": 0,
        "path": tmp_path / "bundle.zip",
    }

    def run(command, **kwargs):
        if command[2].startswith("brokers."):
            return {"items": state["brokers"]}
        return {"items": state["resources"]}

    def create_bundle(command, **kwargs):
        if command[0] == "kubectl":
            container = command[command.index("-c") + 1]
            return CompletedProcess(command, state["log_returncode"], state["logs"].get(container, ""), "log error")
        with ZipFile(state["path"], "w") as bundle:
            for name, content in state["files"].items():
                bundle.writestr(name, content)
        stderr = state["stderr"]
        if command[command.index("--broker-traces") + 1] == "true":
            stderr += state["warning"]
        return CompletedProcess(
            command, state["returncode"], json.dumps({"bundlePath": str(state["path"])}), stderr,
        )

    mocked_run = mocker.patch.object(live_bundles, "run", side_effect=run)
    mocker.patch.object(helpers, "run", mocked_run)
    state["run"] = mocked_run
    state["subprocess"] = mocker.patch.object(live_bundles.subprocess, "run", side_effect=create_bundle)
    return state


@pytest.mark.parametrize("mq_traces", [False, True])
def test_removal_bundle_exercises_each_trace_mode(removal_bundle, tmp_path, mq_traces):
    live_bundles.test_create_bundle_mq_diagnostics_removal(None, tmp_path, mq_traces)

    call = removal_bundle["subprocess"].call_args
    assert call.args[0][call.args[0].index("--broker-traces") + 1] == str(mq_traces).lower()
    assert call.kwargs["timeout"] == 300
    assert call.kwargs["shell"] is False
    assert call.kwargs["capture_output"] is True
    assert removal_bundle["run"].call_count == 3
    assert all(call.kwargs["timeout"] == 30 for call in removal_bundle["run"].call_args_list)


@pytest.mark.parametrize("kind", ["Service", "Pod", "StatefulSet"])
def test_removal_bundle_rejects_retired_resources(removal_bundle, tmp_path, kind):
    removal_bundle["resources"].append({
        "kind": kind, "metadata": {"namespace": "ns", "name": "aio-broker-diagnostics-service"},
    })

    with pytest.raises(AssertionError, match="Retired resources still present"):
        live_bundles.test_create_bundle_mq_diagnostics_removal(None, tmp_path, True)
    removal_bundle["subprocess"].assert_not_called()


def test_removal_bundle_requires_broker(removal_bundle, tmp_path):
    removal_bundle["brokers"] = []
    with pytest.raises(AssertionError, match="requires a deployed broker"):
        live_bundles.test_create_bundle_mq_diagnostics_removal(None, tmp_path, True)
    removal_bundle["subprocess"].assert_not_called()


def test_removal_bundle_rechecks_resource_absence_after_creation(removal_bundle, tmp_path):
    responses = [
        {"items": removal_bundle["brokers"]},
        {"items": removal_bundle["resources"]},
        {"items": [{
            "kind": "StatefulSet", "metadata": {"namespace": "ns", "name": "aio-broker-diagnostics-service"},
        }]},
    ]
    removal_bundle["run"].side_effect = responses
    with pytest.raises(AssertionError, match="Retired resources still present"):
        live_bundles.test_create_bundle_mq_diagnostics_removal(None, tmp_path, False)
    assert removal_bundle["subprocess"].call_count == 2


@pytest.mark.parametrize("filename", [
    "ns/broker/broker.v1.default.yaml",
    "ns/broker/pod.aio-broker-backend-0.yaml",
    "ns/broker/pod.aio-broker-backend-0.backend.log",
    "ns/broker/service.aio-broker.yaml",
    "ns/broker/statefulset.aio-broker-backend.yaml",
])
def test_removal_bundle_rejects_missing_resources_and_logs(removal_bundle, tmp_path, filename):
    del removal_bundle["files"][filename]
    with pytest.raises(AssertionError, match="Missing"):
        live_bundles.test_create_bundle_mq_diagnostics_removal(None, tmp_path, True)


@pytest.mark.parametrize("filename", [
    "ns/broker/traces/legacy.otlp.pb",
    "ns/broker/pod.aio-broker-diagnostics-service-0.yaml",
])
def test_removal_bundle_rejects_retired_files(removal_bundle, tmp_path, filename):
    removal_bundle["files"][filename] = "unexpected"
    with pytest.raises(AssertionError):
        live_bundles.test_create_bundle_mq_diagnostics_removal(None, tmp_path, True)


def test_removal_bundle_requires_running_pod(removal_bundle, tmp_path):
    removal_bundle["resources"][0]["status"]["phase"] = "Pending"
    with pytest.raises(AssertionError, match="stable broker pod with non-empty"):
        live_bundles.test_create_bundle_mq_diagnostics_removal(None, tmp_path, True)


@pytest.mark.parametrize("mq_traces", [False, True])
def test_removal_bundle_enforces_warning_contract(removal_bundle, tmp_path, mq_traces):
    removal_bundle["warning"] = ""
    removal_bundle["stderr"] = "" if mq_traces else "Broker traces unavailable"
    with pytest.raises(AssertionError):
        live_bundles.test_create_bundle_mq_diagnostics_removal(None, tmp_path, mq_traces)


def test_removal_bundle_rejects_collection_errors(removal_bundle, tmp_path):
    removal_bundle["stderr"] = "WARNING: Unable to collect broker traces in namespace 'ns': Forbidden"
    with pytest.raises(AssertionError, match="Unable to collect broker traces"):
        live_bundles.test_create_bundle_mq_diagnostics_removal(None, tmp_path, True)


def test_removal_bundle_rejects_failed_command(removal_bundle, tmp_path):
    removal_bundle["returncode"] = 1
    with pytest.raises(AssertionError, match="Support bundle command failed"):
        live_bundles.test_create_bundle_mq_diagnostics_removal(None, tmp_path, True)


def test_removal_bundle_has_timeout(removal_bundle, tmp_path):
    removal_bundle["subprocess"].side_effect = TimeoutExpired("az", 300)
    with pytest.raises(TimeoutExpired):
        live_bundles.test_create_bundle_mq_diagnostics_removal(None, tmp_path, True)


def test_removal_bundle_ignores_resources_replaced_during_collection(removal_bundle, tmp_path):
    removed_service = deepcopy(removal_bundle["resources"][1])
    removed_service["metadata"]["name"] = "old-service"
    before = [*removal_bundle["resources"], removed_service]
    live_bundles.test_create_bundle_mq_diagnostics_removal(None, tmp_path, False)

    live_bundles._assert_removal_bundle_contents(
        removal_bundle["path"], removal_bundle["brokers"], before, removal_bundle["resources"],
        {("ns", "aio-broker-backend-0", "pod-uid"): {"backend"}},
    )


def test_removal_bundle_accepts_omitted_empty_logs(removal_bundle, tmp_path):
    pod = removal_bundle["resources"][0]
    pod["spec"]["containers"].append({"name": "quiet"})
    pod["status"]["containerStatuses"].append({"name": "quiet", "state": {"running": {}}})

    live_bundles.test_create_bundle_mq_diagnostics_removal(None, tmp_path, True)

    assert removal_bundle["subprocess"].call_count == 3


def test_removal_bundle_requires_nonempty_log_coverage(removal_bundle, tmp_path):
    removal_bundle["logs"]["backend"] = ""
    del removal_bundle["files"]["ns/broker/pod.aio-broker-backend-0.backend.log"]
    with pytest.raises(AssertionError, match="stable broker pod with non-empty"):
        live_bundles.test_create_bundle_mq_diagnostics_removal(None, tmp_path, True)


def test_removal_bundle_rejects_empty_captured_logs(removal_bundle, tmp_path):
    removal_bundle["files"]["ns/broker/pod.aio-broker-backend-0.backend.log"] = ""
    with pytest.raises(AssertionError, match="Empty broker container log"):
        live_bundles.test_create_bundle_mq_diagnostics_removal(None, tmp_path, True)


def test_removal_bundle_does_not_probe_waiting_containers(removal_bundle, tmp_path):
    pod = removal_bundle["resources"][0]
    pod["spec"]["containers"].append({"name": "waiting"})
    pod["status"]["containerStatuses"].append({"name": "waiting", "state": {"waiting": {}}})

    live_bundles.test_create_bundle_mq_diagnostics_removal(None, tmp_path, False)

    assert removal_bundle["subprocess"].call_count == 2


def test_removal_bundle_log_discovery_errors_fail_explicitly(removal_bundle, tmp_path):
    removal_bundle["log_returncode"] = 1
    with pytest.raises(AssertionError, match="Cannot establish broker log coverage"):
        live_bundles.test_create_bundle_mq_diagnostics_removal(None, tmp_path, True)


def test_existing_bundle_test_honors_trace_parameter(mocker):
    get_resources = mocker.patch.object(live_bundles, "get_multi_kubectl_workload_items", return_value={})
    get_traces = mocker.patch.object(live_bundles, "_get_trace_pods")
    run_bundle = mocker.patch.object(live_bundles, "run_bundle_command", return_value=({}, "bundle.zip"))
    mocker.patch.object(live_bundles, "get_file_map", return_value={"aio": {}})
    mocker.patch.object(live_bundles, "check_custom_resource_files")
    mocker.patch.object(live_bundles, "get_all_kinds_from_manager", return_value=set())
    mocker.patch.object(live_bundles, "check_workload_resource_files")
    mocker.patch.object(live_bundles, "check_cluster_label_coverage")

    live_bundles.test_create_bundle_mq(None, [], False)

    assert "--broker-traces False" in run_bundle.call_args.kwargs["command"]
    get_traces.assert_not_called()
    get_resources.assert_called_once()
