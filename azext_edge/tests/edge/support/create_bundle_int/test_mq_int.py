# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import MQ_ACTIVE_API, MqResourceKinds
from .helpers import (
    check_custom_resource_files,
    check_workload_resource_files,
    get_file_map,
    get_kubectl_items,
    run_bundle_command
)

logger = get_logger(__name__)


@pytest.mark.parametrize("mq_traces", [False, True])
def test_create_bundle_mq(init_setup, tracked_files, mq_traces):
    """Test for ensuring file names and content. ONLY CHECKS mq."""
    mq_traces = True

    ops_service = OpsServiceType.mq.value
    command = f"az iot ops support create-bundle --mq-traces {mq_traces} --ops-service {ops_service}"
    walk_result = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service, mq_traces=mq_traces)
    traces = file_map.pop("traces", {})
    # diagnostic_metrics.txt
    diagnostic = file_map.pop("diagnostic_metrics")
    assert len(diagnostic) == 1
    assert diagnostic[0]["extension"] == "txt"

    check_custom_resource_files(
        file_objs=file_map,
        resource_api=MQ_ACTIVE_API,
        resource_kinds=MqResourceKinds.list(),
    )

    expected_workload_types = ["deployment", "pod", "replicaset", "service", "statefulset"]
    expected_types = expected_workload_types + MqResourceKinds.list()
    assert set(file_map.keys()).issubset(set(expected_types))

    # There is a chance that traces are not present even if mq_traces is true
    if not mq_traces:
        assert not traces

    if traces:
        # one trace should have two files - grab by id
        expected_pods = get_kubectl_items("aio-mq", service_type="pod")
        expected_pod_names = [item["metadata"]["name"] for item in expected_pods]
        id_check = {}
        for file in traces["trace"]:
            assert file["action"] in ["connect", "ping", "puback", "publish", "subscribe", "unsubscribe"]
            assert file["name"] in expected_pod_names

            # should be a json for each pb
            if file["identifier"] not in id_check:
                id_check[file["identifier"]] = {}
            assert file["extension"] not in id_check[file["identifier"]]
            # ex: id_check["b9c3173d9c2b97b75edfb6cf7cb482f2"]["json"]
            id_check[file["identifier"]][file["extension"]] = True

        for extension_dict in id_check.values():
            assert extension_dict.get("json")
            assert extension_dict.get("pb")

    check_workload_resource_files(file_map, expected_workload_types, "aio-mq")
