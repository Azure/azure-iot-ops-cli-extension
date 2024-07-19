# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Iterable

from knack.log import get_logger
from rich.console import Console

from ....util.az_client import get_iotops_mgmt_client
from ....util.queryable import Queryable

logger = get_logger(__name__)


class Brokers(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.iotops_mgmt_client = get_iotops_mgmt_client(
            subscription_id=self.default_subscription_id,
        )
        self.listeners = BrokerListeners(self.default_subscription_id)
        self.console = Console()

    def show(self, name: str, instance_name: str, resource_group_name: str) -> dict:
        return self.iotops_mgmt_client.broker.get(
            resource_group_name=resource_group_name, instance_name=instance_name, broker_name=name
        )

    def list(self, instance_name: str, resource_group_name: str) -> Iterable[dict]:
        return self.iotops_mgmt_client.broker.list_by_instance_resource(
            resource_group_name=resource_group_name, instance_name=instance_name
        )


class BrokerListeners:
    def __init__(self, subscription_id: str):
        self.iotops_mgmt_client = get_iotops_mgmt_client(
            subscription_id=subscription_id,
        )

    def show(self, name: str, broker_name: str, instance_name: str, resource_group_name: str) -> dict:
        return self.iotops_mgmt_client.broker_listener.get(
            listener_name=name,
            broker_name=broker_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )

    def list(self, broker_name: str, instance_name: str, resource_group_name: str) -> Iterable[dict]:
        return self.iotops_mgmt_client.broker_listener.list_by_broker_resource(
            resource_group_name=resource_group_name, instance_name=instance_name, broker_name=broker_name
        )
