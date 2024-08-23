# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import TYPE_CHECKING, Iterable

from knack.log import get_logger

from ....util.az_client import get_connectedk8s_mgmt_client
from ....util.queryable import Queryable

logger = get_logger(__name__)


if TYPE_CHECKING:
    from ....vendor.clients.conectedclustermgmt.operations import ConnectedClusterOperations


class ConnectedClusters(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.connectedk8s_mgmt_client = get_connectedk8s_mgmt_client(
            subscription_id=self.default_subscription_id,
        )
        self.ops: "ConnectedClusterOperations" = self.connectedk8s_mgmt_client.connected_cluster

    def show(self, resource_group_name: str, cluster_name: str) -> dict:
        return self.ops.get(
            resource_group_name=resource_group_name, cluster_name=cluster_name,
        )
