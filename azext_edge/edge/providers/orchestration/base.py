# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Tuple

from azure.cli.core.azclierror import ValidationError
from knack.log import get_logger

from ..k8s.config_map import get_config_map
from .common import (
    ARC_CONFIG_MAP,
    ARC_NAMESPACE,
)
from .connected_cluster import ConnectedCluster

logger = get_logger(__name__)


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
