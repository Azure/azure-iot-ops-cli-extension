# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from ....helpers import get_multi_kubectl_workload_items
from .helpers import check_cluster_label_coverage, check_workload_resource_files, get_file_map, run_bundle_command

logger = get_logger(__name__)

pytestmark = pytest.mark.e2e
AKRI_LABEL = ("app.kubernetes.io/name", "microsoft-iotoperations-akri")
AKRI_PREFIXES = [
    "aio-akri",
    "aiomedia",
    "aioonvif",
    "media-connector-template",
    "onvif-connector-template",
    "rest-connector-template",
    "sse-connector-template"
]
# The default OPC UA connector template (and its connector) is captured by the akri bundle via the
# akri CRD APIs (AkriConnectorTemplate/AkriConnector), not by the akri name label. So it shows up as
# an accepted "extra" in the bundle contents but must be excluded from the label-coverage check,
# which asserts label presence for label-collected resources only.
OPCUA_CONNECTOR_PREFIX = "azureiotoperationsconnectorforopcua"
AKRI_BUNDLE_PREFIXES = AKRI_PREFIXES + [OPCUA_CONNECTOR_PREFIX]
AKRI_WORKLOAD_TYPES = [
    "deployment",
    "pod",
    "replicaset",
    "statefulset",
    "service",
    "vwc",
    "mwc",
    "connector",
    "connectortemplate",
    "discoveryhandler",
]


def test_create_bundle_akri(cluster_connection, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS AKRI."""
    ops_service = OpsServiceType.akri.value

    pre_bundle_workload_items = get_multi_kubectl_workload_items(
        expected_workload_types=AKRI_WORKLOAD_TYPES,
        prefixes=AKRI_PREFIXES,
        expected_label=AKRI_LABEL,
    )
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result, bundle_path = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service)["aio"]

    assert set(file_map.keys()).issubset(AKRI_WORKLOAD_TYPES)

    check_workload_resource_files(
        file_objs=file_map,
        pre_bundle_items=pre_bundle_workload_items,
        prefixes=AKRI_BUNDLE_PREFIXES,
        bundle_path=bundle_path,
        expected_label=AKRI_LABEL,
    )
    check_cluster_label_coverage(
        prefixes=AKRI_PREFIXES,
        expected_label=AKRI_LABEL,
        workload_types=AKRI_WORKLOAD_TYPES,
    )
