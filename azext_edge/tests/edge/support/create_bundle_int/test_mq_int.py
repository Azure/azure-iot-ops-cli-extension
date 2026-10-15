# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import subprocess
from os import getenv
from zipfile import ZipFile

import pytest
import yaml
from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import MQ_ACTIVE_API
from azext_edge.edge.providers.support_bundle import COMPAT_MQTT_BROKER_APIS
from ....helpers import assert_broker_diagnostics_service_absent, get_multi_kubectl_workload_items, run
from ....settings import convert_flag
from .helpers import (
    check_cluster_label_coverage,
    check_custom_resource_files,
    check_workload_resource_files,
    get_all_kinds_from_manager,
    get_file_map,
    run_bundle_command,
)

logger = get_logger(__name__)

pytestmark = pytest.mark.e2e
MQ_PREFIXES = ["aio-broker", "aio-dmqtt", "otel-collector-service"]
MQ_WORKLOAD_TYPES = [
    "pod", "daemonset", "replicaset", "service", "statefulset", "job", "configmap", "vwc", "mwc"
]
MQ_LABEL = ("app.kubernetes.io/name", "microsoft-iotoperations-mqttbroker")


@pytest.mark.parametrize("mq_traces", [False, True])
def test_create_bundle_mq(cluster_connection, tracked_files, mq_traces):
    """Test for ensuring file names and content. ONLY CHECKS mq."""
    ops_service = OpsServiceType.mq.value
    pre_bundle_workload_items = get_multi_kubectl_workload_items(
        expected_workload_types=MQ_WORKLOAD_TYPES,
        prefixes=MQ_PREFIXES,
        expected_label=MQ_LABEL
    )
    mq_trace_pods_names = []
    if mq_traces:
        mq_trace_pods_names = _get_trace_pods()

    command = f"az iot ops support create-bundle --broker-traces {mq_traces} --ops-service {ops_service}"
    walk_result, bundle_path = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service, mq_traces=mq_traces)["aio"]
    traces = file_map.pop("traces", {})
    # diagnostic_metrics.txt
    diagnostic = file_map.pop("diagnostic_metrics", None)
    if diagnostic:
        assert len(diagnostic) == 1
        assert diagnostic[0]["extension"] == "txt"

    check_custom_resource_files(file_objs=file_map, resource_apis=COMPAT_MQTT_BROKER_APIS.resource_apis)

    expected_types = (
        set(MQ_WORKLOAD_TYPES).union({"vwc", "mwc"}).union(get_all_kinds_from_manager(COMPAT_MQTT_BROKER_APIS))
    )
    assert set(file_map.keys()).issubset(expected_types)

    # There is a chance that traces are not present even if mq_traces is true
    if not mq_traces:
        assert not traces

    if traces:
        # one trace should have two files - grab by id
        post_expected_pods = _get_trace_pods()
        id_check = {}
        for file in traces["trace"]:
            assert file["action"] in [
                "connect",
                "disconnect",
                "ping",
                "puback",
                "publish",
                "subscribe",
                "unsubscribe",
            ]
            assert (file["name"] in mq_trace_pods_names) or (file["name"] in post_expected_pods)

            # should be a json for each pb
            if file["identifier"] not in id_check:
                id_check[file["identifier"]] = {}
            assert file["extension"] not in id_check[file["identifier"]]
            # ex: id_check["b9c3173d9c2b97b75edfb6cf7cb482f2"]["json"]
            id_check[file["identifier"]][file["extension"]] = True

        for extension_dict in id_check.values():
            assert extension_dict.get("json")
            assert extension_dict.get("pb")

    check_workload_resource_files(
        file_objs=file_map,
        pre_bundle_items=pre_bundle_workload_items,
        prefixes=MQ_PREFIXES,
        bundle_path=bundle_path,
        expected_label=MQ_LABEL,
    )
    check_cluster_label_coverage(
        prefixes=MQ_PREFIXES,
        expected_label=MQ_LABEL,
        workload_types=MQ_WORKLOAD_TYPES,
        known_exclusions=["azure-iot-operations/aio-broker-generation-id"],
    )


def _get_trace_pods():
    return get_multi_kubectl_workload_items(expected_workload_types=["pod"], prefixes="aio-mq")["pod"]


@pytest.mark.skipif(
    not convert_flag(getenv("azext_edge_broker_diagnostics_removal")),
    reason="Requires the explicit broker-diagnostics-removal scenario and a removal-release backend.",
)
@pytest.mark.parametrize("mq_traces", [False, True])
def test_create_bundle_mq_diagnostics_removal(cluster_connection, tmp_path, mq_traces):
    brokers = run(
        ["kubectl", "get", f"brokers.{MQ_ACTIVE_API.group}", "-A", "-o", "json", "--request-timeout=20s"],
        shell_mode=False,
        timeout=30,
    )["items"]
    assert brokers, "The diagnostics-removal scenario requires a deployed broker; no brokers were found."
    namespaces = {broker["metadata"]["namespace"] for broker in brokers}
    before = assert_broker_diagnostics_service_absent(namespaces)
    nonempty_logs = _get_nonempty_broker_logs(before)
    result = subprocess.run(
        [
            "az", "iot", "ops", "support", "create-bundle", "--ops-service", "broker",
            "--broker-traces", str(mq_traces).lower(), "--bundle-dir", str(tmp_path), "-o", "json",
        ],
        check=False,
        shell=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    assert result.returncode == 0, f"Support bundle command failed:\n{result.stderr}"
    assert "Unable to collect broker traces" not in result.stderr, result.stderr
    if mq_traces:
        for namespace in namespaces:
            assert f"Broker traces unavailable in namespace '{namespace}'" in result.stderr, result.stderr
    else:
        assert "Broker traces unavailable" not in result.stderr, result.stderr
    bundle_path = json.loads(result.stdout)["bundlePath"]
    after = assert_broker_diagnostics_service_absent(namespaces)
    _assert_removal_bundle_contents(bundle_path, brokers, before, after, nonempty_logs)


def _get_nonempty_broker_logs(resources):
    nonempty_logs = {}
    for resource in resources:
        metadata = resource["metadata"]
        if (
            resource["kind"] != "Pod"
            or metadata.get("labels", {}).get(MQ_LABEL[0]) != MQ_LABEL[1]
            or resource.get("status", {}).get("phase") != "Running"
        ):
            continue
        for container in resource.get("status", {}).get("containerStatuses", []):
            if "running" not in container.get("state", {}):
                continue
            result = subprocess.run(
                [
                    "kubectl", "logs", metadata["name"], "-n", metadata["namespace"], "-c", container["name"],
                    "--since=23h", "--tail=1", "--request-timeout=20s",
                ],
                check=False, shell=False, capture_output=True, text=True, encoding="utf-8", timeout=30,
            )
            assert result.returncode == 0, f"Cannot establish broker log coverage:\n{result.stderr}"
            if result.stdout:
                key = metadata["namespace"], metadata["name"], metadata["uid"]
                nonempty_logs.setdefault(key, set()).add(container["name"])
    return nonempty_logs


def _assert_removal_bundle_contents(bundle_path, brokers, before, after, nonempty_logs):
    def identity(resource):
        metadata = resource["metadata"]
        return resource["kind"], metadata["namespace"], metadata["name"], metadata["uid"]

    surviving = {identity(resource) for resource in after}
    stable_resources = [
        resource for resource in before
        if identity(resource) in surviving
        and resource["metadata"].get("labels", {}).get(MQ_LABEL[0]) == MQ_LABEL[1]
    ]
    log_namespaces = {
        resource["metadata"]["namespace"] for resource in stable_resources
        if resource["kind"] == "Pod"
        and nonempty_logs.get((
            resource["metadata"]["namespace"], resource["metadata"]["name"], resource["metadata"]["uid"],
        ))
    }
    assert {broker["metadata"]["namespace"] for broker in brokers} <= log_namespaces, (
        "Each broker namespace must have a stable broker pod with non-empty running-container logs "
        "to verify log collection."
    )
    with ZipFile(bundle_path) as bundle:
        names = set(bundle.namelist())
        assert names, "The support bundle is empty."
        assert not any("aio-broker-diagnostics-service" in name or "/traces/" in name for name in names), names
        for resource in [*brokers, *stable_resources]:
            metadata = resource["metadata"]
            root = f"{metadata['namespace']}/broker/"
            kind = resource["kind"].lower()
            version = f"{MQ_ACTIVE_API.version}." if kind == "broker" else ""
            filename = f"{root}{kind}.{version}{metadata['name']}.yaml"
            assert filename in names, f"Missing resource in support bundle: {filename}"
            captured = yaml.safe_load(bundle.read(filename))
            assert captured["metadata"]["name"] == metadata["name"], filename
            assert captured["metadata"]["namespace"] == metadata["namespace"], filename
            if kind == "pod":
                key = metadata["namespace"], metadata["name"], metadata["uid"]
                for container in nonempty_logs.get(key, set()):
                    log_name = f"{root}pod.{metadata['name']}.{container}.log"
                    assert log_name in names, f"Missing broker container log: {log_name}"
                    assert bundle.read(log_name), f"Empty broker container log: {log_name}"
