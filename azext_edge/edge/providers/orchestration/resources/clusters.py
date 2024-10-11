# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import TYPE_CHECKING, Iterable, Optional

from knack.log import get_logger

from build.azext_edge.edge.util.az_client import wait_for_terminal_state

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

    # will be removed
    def update(
        self,
        resource_group_name: str,
        cluster_name: str,
        extension_name: str,
        new_version: str,
        new_train: str,
    ) -> Iterable[dict]:
        extension = self.ops.get(
            resource_group_name=resource_group_name,
            cluster_rp="Microsoft.Kubernetes",
            cluster_resource_name="connectedClusters",
            cluster_name=cluster_name,
            extension_name=extension_name,
        )
        current_version = extension["properties"].get("version", "0").replace("-preview", "")
        if current_version >= new_version.replace("-preview", ""):
            logger.info(f"Extension {extension_name} is already up to date.")
            return
        if extension_name.rsplit("-", maxsplit=1)[0] == "azure-iot-operations":
            new_version = "0.0.0-m3-webhooks.11"
            new_train = "dev"
            extension["properties"]["configurationSettings"] = {
                "akri.enabled": False,
                "connectors.enabled": False,
                "dataFlows.enabled": False,
                "schemaRegistry.enabled": False,
                "mqttBroker.enabled": False,
            }

        print("")
        print(f"Updating extension {extension_name}")
        extension_update = {
            "autoUpgradeMinorVersion": False,
            "releaseTrain": new_train,
            "version": new_version
        }

        # extension_update = wait_for_terminal_state(self.ops.begin_update(
        #     resource_group_name=resource_group_name,
        #     cluster_rp="Microsoft.Kubernetes",
        #     cluster_resource_name="connectedClusters",
        #     cluster_name=cluster_name,
        #     extension_name=extension_name,
        #     patch_extension=extension_update
        # ))
        # if extension_update["properties"]["currentVersion"] != new_version:
        extension["properties"]["version"] = new_version
        extension["properties"]["releaseTrain"] = new_train
        extension["properties"].pop("currentVersion")
        extension["properties"].pop("statuses")
        # wait_for_terminal_state(self.ops.begin_delete(
        #     resource_group_name=resource_group_name,
        #     cluster_rp="Microsoft.Kubernetes",
        #     cluster_resource_name="connectedClusters",
        #     cluster_name=cluster_name,
        #     extension_name=extension_name,
        # ))
        return wait_for_terminal_state(self.ops.begin_create(
            resource_group_name=resource_group_name,
            cluster_rp="Microsoft.Kubernetes",
            cluster_resource_name="connectedClusters",
            cluster_name=cluster_name,
            extension_name=extension_name,
            extension=extension
        ))
