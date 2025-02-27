# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import MQ_ACTIVE_API
from .helpers import (
    check_custom_resource_files,
    check_workload_resource_files,
    get_file_map,
    get_kubectl_workload_items,
    get_workload_resources,
    run_bundle_command,
)

logger = get_logger(__name__)

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("mq_traces", [False, True])
def test_create_bundle_mq(cluster_connection, tracked_files, mq_traces):
    """Test for ensuring file names and content. ONLY CHECKS mq."""
    mq_traces = True

    ops_service = OpsServiceType.mq.value
    expected_workload_types = [
        "pod", "daemonset", "replicaset", "service", "statefulset", "job", "configmap"
    ]
    prefixes = ["aio-broker", "aio-dmqtt", "otel-collector-service"]
    pre_bundle_workload_items = get_workload_resources(
        expected_workload_types=expected_workload_types,
        prefixes=prefixes,
        expected_label=("app.kubernetes.io/name", "microsoft-iotoperations-mqttbroker")
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

    check_custom_resource_files(file_objs=file_map, resource_api=MQ_ACTIVE_API)

    expected_types = set(expected_workload_types).union(MQ_ACTIVE_API.kinds)
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
        prefixes=prefixes,
        bundle_path=bundle_path,
        expected_label=("app.kubernetes.io/name", "microsoft-iotoperations-mqttbroker")
    )


def _get_trace_pods():
    return get_workload_resources(expected_workload_types=["pod"], prefixes="aio-mq")["pod"]
