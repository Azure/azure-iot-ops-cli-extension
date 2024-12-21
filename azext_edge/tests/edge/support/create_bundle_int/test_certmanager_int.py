# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import CERTMANAGER_API_V1
from .helpers import check_custom_resource_files, check_workload_resource_files, get_file_map, run_bundle_command

logger = get_logger(__name__)


def test_create_bundle_certmanager(init_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS arcagents."""
    ops_service = OpsServiceType.certmanager.value

    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result, bundle_path = run_bundle_command(command=command, tracked_files=tracked_files)
    file_map = get_file_map(walk_result, ops_service)

    # cert-manager namespace
    certmanager_file_map = file_map[OpsServiceType.certmanager.value]
    check_custom_resource_files(
        file_objs=certmanager_file_map,
        resource_api=CERTMANAGER_API_V1,
        namespace=file_map["__namespaces__"]["certmanager"],
    )
    expected_workload_types = ["deployment", "pod", "replicaset", "service", "configmap"]
    expected_types = set(expected_workload_types).union(CERTMANAGER_API_V1.kinds)
    assert set(certmanager_file_map.keys()).issubset(expected_types)
    check_workload_resource_files(
        file_objs=certmanager_file_map,
        expected_workload_types=expected_workload_types,
        prefixes=["aio-cert-manager", "aio-trust-manager", "kube-root-ca"],
        bundle_path=bundle_path,
    )

    # aio namespace
    certmanager_aio_file_map = file_map["certmanager_aio"]
    check_custom_resource_files(
        file_objs=certmanager_aio_file_map,
        resource_api=CERTMANAGER_API_V1,
        namespace=file_map["__namespaces__"]["aio"],
        exclude_kinds=["clusterissuer"],
    )

    # acstor namespace if present
    certmanager_acstor_file_map = file_map.get("certmanager_acstor")
    if certmanager_acstor_file_map:
        check_custom_resource_files(
            file_objs=certmanager_acstor_file_map,
            resource_api=CERTMANAGER_API_V1,
            namespace=file_map["__namespaces__"]["acstor"],
        )
