# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import TYPE_CHECKING, Iterable, Optional, Callable

from knack.log import get_logger
from rich.console import Console

from ....util.az_client import wait_for_terminal_state
from ....util.common import should_continue_prompt
from ....util.queryable import Queryable
from .reskit import get_file_config
from .instances import Instances

logger = get_logger(__name__)


if TYPE_CHECKING:
    from ....vendor.clients.iotopsmgmt.operations import (
        BrokerAuthenticationOperations,
        BrokerAuthorizationOperations,
        BrokerListenerOperations,
        BrokerOperations,
    )

console = Console()


class Brokers(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.instances = Instances(cmd=cmd)
        self.iotops_mgmt_client = self.instances.iotops_mgmt_client

        self.ops: "BrokerOperations" = self.iotops_mgmt_client.broker
        self.listeners = BrokerListeners(self.iotops_mgmt_client.broker_listener, self.instances.get_ext_loc)
        self.authns = BrokerAuthn(self.iotops_mgmt_client.broker_authentication)
        self.authzs = BrokerAuthz(self.iotops_mgmt_client.broker_authorization)

    def show(self, name: str, instance_name: str, resource_group_name: str) -> dict:
        return self.ops.get(resource_group_name=resource_group_name, instance_name=instance_name, broker_name=name)

    def list(self, instance_name: str, resource_group_name: str) -> Iterable[dict]:
        return self.ops.list_by_resource_group(resource_group_name=resource_group_name, instance_name=instance_name)

    def delete(
        self, name: str, instance_name: str, resource_group_name: str, confirm_yes: Optional[bool] = None, **kwargs
    ):
        should_bail = not should_continue_prompt(confirm_yes=confirm_yes)
        if should_bail:
            return

        with console.status("Working..."):
            poller = self.ops.begin_delete(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                broker_name=name,
            )
            return wait_for_terminal_state(poller, **kwargs)


class BrokerListeners:
    def __init__(self, ops: "BrokerListenerOperations", get_ext_loc: Callable[[str, str], str]):
        self.ops = ops
        self.get_ext_loc = get_ext_loc

    def create(
        self, name: str, broker_name: str, instance_name: str, resource_group_name: str, config_file: str, **kwargs
    ) -> dict:
        listener_config = get_file_config(config_file)
        ext_loc = self.get_ext_loc(name=instance_name, resource_group_name=resource_group_name)
        resource = {}
        resource["extendedLocation"] = ext_loc
        resource["properties"] = listener_config

        with console.status("Working..."):
            poller = self.ops.begin_create_or_update(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                broker_name=broker_name,
                listener_name=name,
                resource=resource,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def show(self, name: str, broker_name: str, instance_name: str, resource_group_name: str) -> dict:
        return self.ops.get(
            listener_name=name,
            broker_name=broker_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )

    def list(self, broker_name: str, instance_name: str, resource_group_name: str) -> Iterable[dict]:
        return self.ops.list_by_resource_group(
            resource_group_name=resource_group_name, instance_name=instance_name, broker_name=broker_name
        )

    def delete(
        self,
        name: str,
        broker_name: str,
        instance_name: str,
        resource_group_name: str,
        confirm_yes: Optional[bool] = None,
        **kwargs
    ):
        should_bail = not should_continue_prompt(confirm_yes=confirm_yes)
        if should_bail:
            return

        with console.status("Working..."):
            poller = self.ops.begin_delete(
                listener_name=name,
                broker_name=broker_name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
            )
            return wait_for_terminal_state(poller, **kwargs)


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
        return self.ops.list_by_resource_group(
            resource_group_name=resource_group_name, instance_name=instance_name, broker_name=broker_name
        )

    def delete(
        self,
        name: str,
        broker_name: str,
        instance_name: str,
        resource_group_name: str,
        confirm_yes: Optional[bool] = None,
        **kwargs
    ):
        should_bail = not should_continue_prompt(confirm_yes=confirm_yes)
        if should_bail:
            return

        with console.status("Working..."):
            poller = self.ops.begin_delete(
                authentication_name=name,
                broker_name=broker_name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
            )
            return wait_for_terminal_state(poller, **kwargs)


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
        return self.ops.list_by_resource_group(
            resource_group_name=resource_group_name, instance_name=instance_name, broker_name=broker_name
        )

    def delete(
        self,
        name: str,
        broker_name: str,
        instance_name: str,
        resource_group_name: str,
        confirm_yes: Optional[bool] = None,
        **kwargs
    ):
        should_bail = not should_continue_prompt(confirm_yes=confirm_yes)
        if should_bail:
            return

        with console.status("Working..."):
            poller = self.ops.begin_delete(
                authorization_name=name,
                broker_name=broker_name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
            )
            return wait_for_terminal_state(poller, **kwargs)
