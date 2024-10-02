# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Tuple

from azure.cli.core.azclierror import ValidationError
from knack.log import get_logger

from ..k8s.cluster_role_binding import get_bindings
from ..k8s.config_map import get_config_map
from .common import (
    ARC_CONFIG_MAP,
    ARC_NAMESPACE,
    CUSTOM_LOCATIONS_RP_APP_ID,
    EXTENDED_LOCATION_ROLE_BINDING,
    GRAPH_V1_SP_ENDPOINT,
)
from .connected_cluster import ConnectedCluster

logger = get_logger(__name__)


def verify_custom_locations_enabled(cmd):
    from azure.cli.core.util import send_raw_request

    target_bindings = get_bindings(field_selector=f"metadata.name=={EXTENDED_LOCATION_ROLE_BINDING}")
    if not target_bindings or (target_bindings and not target_bindings.get("items")):
        raise ValidationError(
            "The custom-locations feature is required but not enabled on the cluster. For guidance refer to:\n"
            "https://aka.ms/ArcK8sCustomLocationsDocsEnableFeature"
        )

    # See if we can verify the RP OID.
    try:
        cl_sp_response = send_raw_request(
            cli_ctx=cmd.cli_ctx,
            method="GET",
            url=f"{GRAPH_V1_SP_ENDPOINT}(appId='{CUSTOM_LOCATIONS_RP_APP_ID}')",
        ).json()
        cl_oid = cl_sp_response["id"].lower()
    except Exception:
        # If not, bail without throwing.
        return

    # We are expecting one binding. Field selector pattern is used due to AKS-EE issue.
    target_binding: dict = target_bindings["items"][0]
    for subject in target_binding.get("subjects", []):
        if "name" in subject and subject["name"].lower() == cl_oid:
            return

    raise ValidationError(f"Invalid OID used for custom locations feature enablement. Use '{cl_oid}'.")


# TODO: @digimaun - can be useful for cluster side checks.
def verify_arc_cluster_config(connected_cluster: ConnectedCluster):
    connect_config_map = get_config_map(name=ARC_CONFIG_MAP, namespace=ARC_NAMESPACE)
    if not connect_config_map:
        raise ValidationError(
            "Unable to verify cluster arc config. Please ensure the target cluster is arc-enabled and a "
            "corresponding kubeconfig context exists locally. "
        )

    connect_data_map: dict = connect_config_map.get("data", {})

    evaluations: Tuple[str, str, str] = [
        (connected_cluster.cluster_name, connect_data_map.get("AZURE_RESOURCE_NAME"), "cluster name"),
        (connected_cluster.resource_group_name, connect_data_map.get("AZURE_RESOURCE_GROUP"), "resource group"),
        (connected_cluster.subscription_id, connect_data_map.get("AZURE_SUBSCRIPTION_ID"), "subscription Id"),
    ]

    for evaluation in evaluations:
        cloud_value = evaluation[0].lower()
        arc_config_value = evaluation[1].lower()
        description = evaluation[2]
        if arc_config_value != cloud_value:
            raise ValidationError(
                f"The cluster-side arc config uses {arc_config_value} for {description}, "
                f"while the cloud target is {cloud_value}.\n"
                "Please ensure the local kubeconfig is up-to-date with the intended cluster for deployment."
            )


def verify_custom_location_namespace(connected_cluster: ConnectedCluster, custom_location_name: str, namespace: str):
    custom_location_ref = connected_cluster.get_custom_location_for_namespace(namespace=namespace)
    if custom_location_ref and custom_location_ref["name"] != custom_location_name:
        raise ValidationError(
            f"The intended namespace for deployment: {namespace}, is already referenced by "
            f"custom location: {custom_location_ref['name']}.\n"
            "A namespace can only be referenced by a single custom location. "
            "Please choose a different namespace via --cluster-namespace."
        )
