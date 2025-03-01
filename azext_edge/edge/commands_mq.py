# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Iterable, Optional

from knack.log import get_logger

from .providers.orchestration.resources import Brokers

logger = get_logger(__name__)


def show_broker(cmd, broker_name: str, instance_name: str, resource_group_name: str) -> dict:
    return Brokers(cmd).show(name=broker_name, instance_name=instance_name, resource_group_name=resource_group_name)


def list_brokers(cmd, instance_name: str, resource_group_name: str) -> Iterable[dict]:
    return Brokers(cmd).list(instance_name=instance_name, resource_group_name=resource_group_name)


def delete_broker(
    cmd, broker_name: str, instance_name: str, resource_group_name: str, confirm_yes: Optional[bool] = None, **kwargs
):
    return Brokers(cmd).delete(
        name=broker_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=confirm_yes,
        **kwargs,
    )


def show_broker_listener(
    cmd, listener_name: str, broker_name: str, instance_name: str, resource_group_name: str
) -> dict:
    return Brokers(cmd).listeners.show(
        name=listener_name,
        broker_name=broker_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )


def list_broker_listeners(cmd, broker_name: str, instance_name: str, resource_group_name: str) -> Iterable[dict]:
    return Brokers(cmd).listeners.list(
        broker_name=broker_name, instance_name=instance_name, resource_group_name=resource_group_name
    )


def delete_broker_listener(
    cmd,
    listener_name: str,
    broker_name: str,
    instance_name: str,
    resource_group_name: str,
    confirm_yes: Optional[bool] = None,
    **kwargs
):
    return Brokers(cmd).listeners.delete(
        name=listener_name,
        broker_name=broker_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=confirm_yes,
        **kwargs,
    )


def show_broker_authn(cmd, authn_name: str, broker_name: str, instance_name: str, resource_group_name: str) -> dict:
    return Brokers(cmd).authns.show(
        name=authn_name,
        broker_name=broker_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )


def list_broker_authns(cmd, broker_name: str, instance_name: str, resource_group_name: str) -> Iterable[dict]:
    return Brokers(cmd).authns.list(
        broker_name=broker_name, instance_name=instance_name, resource_group_name=resource_group_name
    )


def delete_broker_authn(
    cmd,
    authn_name: str,
    broker_name: str,
    instance_name: str,
    resource_group_name: str,
    confirm_yes: Optional[bool] = None,
    **kwargs
):
    return Brokers(cmd).authns.delete(
        name=authn_name,
        broker_name=broker_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=confirm_yes,
        **kwargs,
    )


def show_broker_authz(cmd, authz_name: str, broker_name: str, instance_name: str, resource_group_name: str) -> dict:
    return Brokers(cmd).authzs.show(
        name=authz_name,
        broker_name=broker_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )


def list_broker_authzs(cmd, broker_name: str, instance_name: str, resource_group_name: str) -> Iterable[dict]:
    return Brokers(cmd).authzs.list(
        broker_name=broker_name, instance_name=instance_name, resource_group_name=resource_group_name
    )


def delete_broker_authz(
    cmd,
    authz_name: str,
    broker_name: str,
    instance_name: str,
    resource_group_name: str,
    confirm_yes: Optional[bool] = None,
    **kwargs
):
    return Brokers(cmd).authzs.delete(
        name=authz_name,
        broker_name=broker_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=confirm_yes,
        **kwargs,
    )
