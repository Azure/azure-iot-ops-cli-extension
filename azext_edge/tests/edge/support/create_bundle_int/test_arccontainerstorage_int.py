# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import ARCCONTAINERSTORAGE_API_V1, CONTAINERSTORAGE_API_V1
from azext_edge.tests.helpers import get_kubectl_workload_items
from .helpers import (
    check_custom_resource_files,
    check_workload_resource_files,
    get_file_map,
    get_workload_resources,
    run_bundle_command,
)

logger = get_logger(__name__)

pytestmark = pytest.mark.e2e


def test_create_bundle_arccontainerstorage(cluster_connection, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS arccontainerstorage."""
    ops_service = OpsServiceType.arccontainerstorage.value

    # ACS azure-arc-containerstorage
    expected_acs_workload_types = ["daemonset", "deployment", "pod", "pvc", "replicaset", "service"]
    acs_workload_resource_prefixes = [
        "acsa-otel",
        "csi-wyvern-controller",
        "csi-wyvern-node",
        "config-operator",
        "edgevolume-mounthelper",
        "wyvern-operator",
    ]
    pre_bundle_acs_workload_items = get_workload_resources(
        expected_workload_types=expected_acs_workload_types,
        prefixes=acs_workload_resource_prefixes,
    )

    schemas_pods = get_kubectl_workload_items(
        prefixes="adr-schema-registry",
        service_type="pod",
        label_match=("app.kubernetes.io/name", "microsoft-iotoperations-schemas"),
    )

    # add following workload prefixes if schema registry is deployed
    if len(schemas_pods.items()) > 0:
        acs_workload_resource_prefixes.extend(
            [
                "w-adr-schema-registry",
                "adr-schema-registry-cache-claimsrv",
                "adr-schema-registry-cache-claim-user-pvc",
                "adr-schema-registry-cache-claim-system-pvc",
            ]
        )

    # ACSTOR
    expected_acstor_workload_types = ["daemonset", "deployment", "pod", "replicaset", "service", "configmap"]
    workload_acstor_resource_prefixes = [
        "acstor",
        "capacity-provisioner",
        "diskpool-worker",
        "etcd-acstor",
        "etcdr",
        "fluentd",
        "geneva",
        "gcstenant",
        "kube-root-ca",
        "overlay-etcd",
        "webhook",
    ]
    pre_bundle_acstor_workload_items = get_workload_resources(
        expected_workload_types=expected_acstor_workload_types,
        prefixes=workload_acstor_resource_prefixes,
    )

    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result, bundle_path = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service)

    # ACS azure-arc-containerstorage
    acs_file_map = file_map["acs"]

    expected_types = set(expected_acs_workload_types).union(ARCCONTAINERSTORAGE_API_V1.kinds)
    assert set(acs_file_map.keys()).issubset(set(expected_types))
    import pdb; pdb.set_trace()
    check_workload_resource_files(
        file_objs=acs_file_map,
        pre_bundle_items=pre_bundle_acstor_workload_items,
        prefixes=pre_bundle_acs_workload_items,
        bundle_path=bundle_path,
    )
    check_custom_resource_files(file_objs=acs_file_map, resource_api=ARCCONTAINERSTORAGE_API_V1)

    # ACSTOR validate azure-arc-acstor if exists
    if "acstor" not in file_map:
        # TODO: add assertion that this does not exist
        return
    acstor_file_map = file_map["acstor"]
    expected_types = set(expected_acstor_workload_types).union(CONTAINERSTORAGE_API_V1.kinds)
    assert set(acstor_file_map.keys()).issubset(set(expected_types))

    check_workload_resource_files(
        file_objs=acstor_file_map,
        pre_bundle_items=pre_bundle_acstor_workload_items,
        prefixes=workload_acstor_resource_prefixes,
        bundle_path=bundle_path,
    )

    check_custom_resource_files(file_objs=acstor_file_map, resource_api=CONTAINERSTORAGE_API_V1)
