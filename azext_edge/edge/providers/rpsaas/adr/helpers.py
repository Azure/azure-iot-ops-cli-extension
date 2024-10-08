# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger
from typing import Dict, Optional
from ...orchestration.resources import Instances

logger = get_logger(__name__)


def check_cluster_connectivity(cmd, resource: dict):
    """
    Uses the resource's extended location to get the cluster and checks connectivity.
    Use this for commands that require the cluster to be connected to succeed.

    resource: dict representing an object that has the extended location property.

    """
    connected_cluster = Instances(cmd=cmd).get_resource_map(resource).connected_cluster
    if not connected_cluster.connected:
        logger.warning(f"Cluster {connected_cluster.cluster_name} is not connected.")


def get_extended_location(
    cmd,
    instance_name: str,
    instance_resource_group: str,
    instance_subscription: Optional[str] = None
) -> Dict[str, str]:
    """
    Returns the extended location object with cluster location.

    Will also check for instance existance and whether the associated cluster is connected.

    instance_name: str representing the instance name
    instance_resource_group: str representing the instance resource group
    instance_subscription: str representing the instance subscription
        (if it is different from the current one)
    """
    instance_provider = Instances(cmd=cmd, subscription_id=instance_subscription)
    # instance should exist
    instance = instance_provider.show(
        name=instance_name, resource_group_name=instance_resource_group
    )
    resource_map = instance_provider.get_resource_map(instance=instance)
    connected_cluster = resource_map.connected_cluster
    if not connected_cluster.connected:
        logger.warning(f"Cluster {connected_cluster.cluster_name} is not connected.")

    return {
        "type": "CustomLocation",
        "name": instance["extendedLocation"]["name"],
        "cluster_location": connected_cluster.location
    }
