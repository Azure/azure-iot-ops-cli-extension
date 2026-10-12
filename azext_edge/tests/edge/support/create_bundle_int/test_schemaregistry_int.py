# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from os.path import basename
from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from ....helpers import get_multi_kubectl_workload_items
from .helpers import check_cluster_label_coverage, check_workload_resource_files, get_file_map, run_bundle_command

logger = get_logger(__name__)

pytestmark = pytest.mark.e2e
SCHEMA_PREFIXES = ["adr-schema-registry"]
SCHEMA_WORKLOAD_TYPES = ["configmap", "pod", "service", "statefulset", "pvc"]
SCHEMA_LABEL = ("app.kubernetes.io/name", "microsoft-iotoperations-schemas")
EDGE_REGISTRY_PREFIXES = ["aio-edge-registry"]
EDGE_REGISTRY_LABEL = ("app.kubernetes.io/name", "microsoft-iotoperations-registry")


@pytest.mark.parametrize("ops_service, prefixes, expected_label", [
    (OpsServiceType.schemaregistry.value, SCHEMA_PREFIXES, SCHEMA_LABEL),
    (OpsServiceType.edgeregistry.value, EDGE_REGISTRY_PREFIXES, EDGE_REGISTRY_LABEL),
])
def test_create_bundle_registries(cluster_connection, tracked_files, ops_service, prefixes, expected_label):
    pre_bundle_workload_items = get_multi_kubectl_workload_items(
        expected_workload_types=SCHEMA_WORKLOAD_TYPES,
        prefixes=prefixes,
    )
    check_cluster_label_coverage(
        prefixes=prefixes,
        expected_label=expected_label,
        workload_types=SCHEMA_WORKLOAD_TYPES,
    )
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result, bundle_path = run_bundle_command(command=command, tracked_files=tracked_files)
    if not any(pre_bundle_workload_items.values()):
        assert not any(basename(directory) == ops_service for directory in walk_result)
        return
    file_map = get_file_map(walk_result, ops_service)["aio"]

    assert set(file_map.keys()).issubset(set(SCHEMA_WORKLOAD_TYPES))

    check_workload_resource_files(
        file_objs=file_map,
        pre_bundle_items=pre_bundle_workload_items,
        prefixes=prefixes,
        bundle_path=bundle_path,
    )
