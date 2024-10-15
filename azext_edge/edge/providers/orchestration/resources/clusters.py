# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import TYPE_CHECKING, Iterable, Optional

from knack.log import get_logger

from ....util.az_client import (
    get_clusterconfig_mgmt_client,
    get_connectedk8s_mgmt_client,
)
from ....util.queryable import Queryable

logger = get_logger(__name__)


if TYPE_CHECKING:
    from ....vendor.clients.clusterconfigmgmt.operations import ExtensionsOperations
    from ....vendor.clients.connectedclustermgmt.operations import ConnectedClusterOperations


class ConnectedClusters(Queryable):
    def __init__(self, cmd, subscription_id: Optional[str] = None):
        super().__init__(cmd=cmd, subscriptions=[subscription_id] if subscription_id else None)
        self.connectedk8s_mgmt_client = get_connectedk8s_mgmt_client(
            subscription_id=self.subscriptions[0],
        )
        self.ops: "ConnectedClusterOperations" = self.connectedk8s_mgmt_client.connected_cluster
        self.extensions: ClusterExtensions = ClusterExtensions(cmd)

    def show(self, resource_group_name: str, cluster_name: str) -> dict:
        return self.ops.get(
            resource_group_name=resource_group_name,
            cluster_name=cluster_name,
        )


class ClusterExtensions(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.clusterconfig_mgmt_client = get_clusterconfig_mgmt_client(
            subscription_id=self.default_subscription_id,
        )
        self.ops: "ExtensionsOperations" = self.clusterconfig_mgmt_client.extensions

    def list(self, resource_group_name: str, cluster_name: str) -> Iterable[dict]:
        return self.ops.list(
            resource_group_name=resource_group_name,
            cluster_rp="Microsoft.Kubernetes",
            cluster_resource_name="connectedClusters",
            cluster_name=cluster_name,
        )

    def update(self, resource_group_name: str, cluster_name: str, extension_name: str, patch_extension: dict) -> dict:
        return self.ops.begin_update(
            resource_group_name=resource_group_name,
            cluster_rp="Microsoft.Kubernetes",
            cluster_resource_name="connectedClusters",
            cluster_name=cluster_name,
            extension_name=extension_name,
            patch_extension=patch_extension,
        )
