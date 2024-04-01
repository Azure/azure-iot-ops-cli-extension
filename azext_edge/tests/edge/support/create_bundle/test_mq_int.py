# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from .helpers import check_name, check_non_custom_file_objs, get_file_map, run_bundle_command

logger = get_logger(__name__)


@pytest.mark.parametrize("mq_traces", [False, True])
def test_create_bundle_mq(init_setup, tracked_files, mq_traces):
    """Test for ensuring file names and content. ONLY CHECKS mq."""
    mq_traces = True

    ops_service = OpsServiceType.mq.value
    command = f"az iot ops support create-bundle --mq-traces {mq_traces} --ops-service {ops_service}"
    walk_result = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service, mq_traces=mq_traces)
    traces = file_map.pop("trace", {})

    check_mq_types(file_map)

    expected_file_objs = {
        "deployment": [
            "aio-mq-diagnostics-service",
            "aio-mq-operator"
        ],
        "pod": [
            "aio-mq-diagnostics-probe",
            "aio-mq-diagnostics-service",
            "aio-mq-dmqtt-authentication",
            "aio-mq-dmqtt-backend",  # could have multiple
            "aio-mq-dmqtt-frontend",  # same
            "aio-mq-dmqtt-health-manager",
            "aio-mq-operator"
        ],
        "replicaset": [
            "aio-mq-diagnostics-service",
            "aio-mq-operator"
        ],
        "service": [
            "aio-mq-diagnostics-service",
            "aio-mq-dmqtt-authentication",
            "aio-mq-dmqtt-backend",
            "aio-mq-dmqtt-frontend",
            "aio-mq-dmqtt-health-manager"
        ],
        "statefulset": [
            "aio-mq-diagnostics-probe",
            "aio-mq-dmqtt-authentication",
            "aio-mq-dmqtt-backend",  # could have multiple
            "aio-mq-dmqtt-frontend",
            "aio-mq-dmqtt-health-manager"
        ]
    }

    check_non_custom_file_objs(file_map, expected_file_objs)

    if traces:
        id_check = {}
        for file in traces:
            assert file["action"] in ["connect", "ping", "puback", "publish", "subscribe", "unsubscribe"]
            check_name(file["name"], expected_file_objs["pod"])

            # should be a json for each pb
            if file["identifier"] not in id_check:
                id_check[file["identifier"]] = {}
            assert file["extension"] not in id_check[file["identifier"]]
            # ex: id_check["b9c3173d9c2b97b75edfb6cf7cb482f2"]["json"]
            id_check[file["identifier"]][file["extension"]] = True

        for extension_dict in id_check.values():
            assert extension_dict.get("json")
            assert extension_dict.get("pb")


def check_mq_types(file_map):
    # do we always have these? What cases do they have them vs not?
    # how can names change?
    for config in file_map["brokerauthentication"]:
        assert config["version"] == "v1beta1"
    for config in file_map.get("brokerauthorization", []):
        assert config["version"] == "v1beta1"
    # Expecting >=1 broker listeners per namespace
    for config in file_map["brokerlistener"]:
        assert config["version"] == "v1beta1"
    # Expecting 1 broker resource per namespace
    for config in file_map["broker"]:
        assert config["version"] == "v1beta1"
    for config in file_map.get("datalakeconnectortopicmap", []):
        assert config["version"] == "v1beta1"
    for config in file_map.get("datalakeconnector", []):
        assert config["version"] == "v1beta1"
    # Expecting 1 diagnostics service resource per namespace
    for config in file_map["diagnosticservice"]:
        assert config["version"] == "v1beta1"
    for config in file_map.get("iothubconnectorroutesmap", []):
        assert config["version"] == "v1beta1"
    for config in file_map.get("iothubconnector", []):
        assert config["version"] == "v1beta1"
    for config in file_map.get("kafkaconnectortopicmap", []):
        assert config["version"] == "v1beta1"
    for config in file_map.get("kafkaconnector", []):
        assert config["version"] == "v1beta1"
    for config in file_map.get("mqttbridgeconnector", []):
        assert config["version"] == "v1beta1"
    for config in file_map.get("mqttbridgetopicmap", []):
        assert config["version"] == "v1beta1"
