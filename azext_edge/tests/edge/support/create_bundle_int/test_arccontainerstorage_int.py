# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import ARCCONTAINERSTORAGE_API_V1, CONTAINERSTORAGE_API_V1
from azext_edge.tests.helpers import get_kubectl_workload_items
from .helpers import (
    check_custom_resource_files,
    check_workload_resource_files,
    get_file_map,
    run_bundle_command,
)

logger = get_logger(__name__)


def test_create_bundle_arccontainerstorage(init_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS arccontainerstorage."""
    # dir for unpacked files
    ops_service = OpsServiceType.arccontainerstorage.value
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result, bundle_path = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service)

    # azure-arc-containerstorage
    acs_file_map = file_map["acs"]

    check_custom_resource_files(file_objs=acs_file_map, resource_api=ARCCONTAINERSTORAGE_API_V1)

    expected_workload_types = ["daemonset", "deployment", "pod", "pvc", "replicaset", "service"]
    expected_types = set(expected_workload_types).union(ARCCONTAINERSTORAGE_API_V1.kinds)
    assert set(acs_file_map.keys()).issubset(set(expected_types))

    workload_resource_prefixes = [
        "acsa-otel",
        "csi-wyvern-controller",
        "csi-wyvern-node",
        "config-operator",
        "edgevolume-mounthelper",
        "wyvern-operator",
    ]

    schemas_pods = get_kubectl_workload_items(
        prefixes="adr-schema-registry",
        service_type="pod",
        label_match=("app.kubernetes.io/name", "microsoft-iotoperations-schemas"),
    )

    # add following workload prefixes if schema registry is deployed
    if len(schemas_pods.items()) > 0:
        workload_resource_prefixes.extend(
            [
                "w-adr-schema-registry",
                "adr-schema-registry-cache-claimsrv",
                "adr-schema-registry-cache-claim-user-pvc",
                "adr-schema-registry-cache-claim-system-pvc",
            ]
        )

    check_workload_resource_files(
        file_objs=acs_file_map,
        expected_workload_types=expected_workload_types,
        prefixes=workload_resource_prefixes,
        bundle_path=bundle_path,
    )

    # validate azure-arc-acstor if exists

    if "acstor" not in file_map:
        return

    acstor_file_map = file_map["acstor"]

    expected_workload_types = ["daemonset", "deployment", "pod", "replicaset", "service", "configmap"]
    expected_types = set(expected_workload_types).union(CONTAINERSTORAGE_API_V1.kinds)
    assert set(acstor_file_map.keys()).issubset(set(expected_types))

    workload_resource_prefixes = [
        "acstor-action",
        "acstor-agent",
        "acstor-api-rest",
        "acstor-capacity",
        "acstor-cert-manager",
        "acstor-crd",
        "acstor-csi",
        "acstor-etcd",
        "acstor-io",
        "acstor-ndm",
        "acstor-operator",
        "acstor-prereq",
        "acstor-scripts",
        "acstor-support-bundle",
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

    check_workload_resource_files(
        file_objs=acstor_file_map,
        expected_workload_types=expected_workload_types,
        prefixes=workload_resource_prefixes,
        bundle_path=bundle_path,
    )

    check_custom_resource_files(file_objs=acstor_file_map, resource_api=CONTAINERSTORAGE_API_V1)
