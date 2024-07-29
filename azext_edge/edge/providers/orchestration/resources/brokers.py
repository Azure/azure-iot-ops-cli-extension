# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import TYPE_CHECKING, Iterable

from knack.log import get_logger

from ....util.az_client import get_iotops_mgmt_client
from ....util.queryable import Queryable

logger = get_logger(__name__)


if TYPE_CHECKING:
    from ....vendor.clients.iotopsmgmt.operations import (
        BrokerOperations,
        BrokerAuthenticationOperations,
        BrokerAuthorizationOperations,
        BrokerListenerOperations,
    )


class Brokers(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.iotops_mgmt_client = get_iotops_mgmt_client(
            subscription_id=self.default_subscription_id,
        )
        self.ops: "BrokerOperations" = self.iotops_mgmt_client.broker
        self.listeners = BrokerListeners(self.iotops_mgmt_client.broker_listener)
        self.authns = BrokerAuthn(self.iotops_mgmt_client.broker_authentication)
        self.authzs = BrokerAuthz(self.iotops_mgmt_client.broker_authorization)

    def show(self, name: str, instance_name: str, resource_group_name: str) -> dict:
        return self.ops.get(resource_group_name=resource_group_name, instance_name=instance_name, broker_name=name)

    def list(self, instance_name: str, resource_group_name: str) -> Iterable[dict]:
        return self.ops.list_by_instance_resource(resource_group_name=resource_group_name, instance_name=instance_name)


class BrokerListeners:
    def __init__(self, ops: "BrokerListenerOperations"):
        self.ops = ops

    def show(self, name: str, broker_name: str, instance_name: str, resource_group_name: str) -> dict:
        return self.ops.get(
            listener_name=name,
            broker_name=broker_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )

    def list(self, broker_name: str, instance_name: str, resource_group_name: str) -> Iterable[dict]:
        return self.ops.list_by_broker_resource(
            resource_group_name=resource_group_name, instance_name=instance_name, broker_name=broker_name
        )


class BrokerAuthn:
    def __init__(self, ops: "BrokerAuthenticationOperations"):
        self.ops = ops

    def show(self, name: str, broker_name: str, instance_name: str, resource_group_name: str) -> dict:
        return self.ops.get(
            authentication_name=name,
            broker_name=broker_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )

    def list(self, broker_name: str, instance_name: str, resource_group_name: str) -> Iterable[dict]:
        return self.ops.list_by_broker_resource(
            resource_group_name=resource_group_name, instance_name=instance_name, broker_name=broker_name
        )


class BrokerAuthz:
    def __init__(self, ops: "BrokerAuthorizationOperations"):
        self.ops = ops

    def show(self, name: str, broker_name: str, instance_name: str, resource_group_name: str) -> dict:
        return self.ops.get(
            authorization_name=name,
            broker_name=broker_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )

    def list(self, broker_name: str, instance_name: str, resource_group_name: str) -> Iterable[dict]:
        return self.ops.list_by_broker_resource(
            resource_group_name=resource_group_name, instance_name=instance_name, broker_name=broker_name
        )
