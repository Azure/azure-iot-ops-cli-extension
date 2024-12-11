# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, List, Optional

from knack.log import get_logger

from .providers.rpsaas.adr.asset_endpoint_profiles import AssetEndpointProfiles
from .common import AEPTypes

logger = get_logger(__name__)


def create_opcua_asset_endpoint_profile(
    cmd,
    asset_endpoint_profile_name: str,
    instance_name: str,
    resource_group_name: str,
    target_address: str,
    certificate_reference: Optional[str] = None,
    instance_resource_group: Optional[str] = None,
    instance_subscription: Optional[str] = None,
    location: Optional[str] = None,
    password_reference: Optional[str] = None,
    username_reference: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    application_name: Optional[str] = None,
    auto_accept_untrusted_server_certs: Optional[bool] = None,
    default_publishing_interval: Optional[int] = None,
    default_sampling_interval: Optional[int] = None,
    default_queue_size: Optional[int] = None,
    keep_alive: Optional[int] = None,
    run_asset_discovery: Optional[str] = None,
    session_timeout: Optional[int] = None,
    session_keep_alive: Optional[int] = None,
    session_reconnect_period: Optional[int] = None,
    session_reconnect_exponential_back_off: Optional[int] = None,
    security_policy: Optional[str] = None,
    security_mode: Optional[str] = None,
    sub_max_items: Optional[int] = None,
    sub_life_time: Optional[int] = None,
    **kwargs
) -> dict:
    return AssetEndpointProfiles(cmd).create(
        asset_endpoint_profile_name=asset_endpoint_profile_name,
        endpoint_profile_type=AEPTypes.opcua.value,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        target_address=target_address,
        certificate_reference=certificate_reference,
        instance_resource_group=instance_resource_group,
        instance_subscription=instance_subscription,
        location=location,
        password_reference=password_reference,
        username_reference=username_reference,
        tags=tags,
        application_name=application_name,
        auto_accept_untrusted_server_certs=auto_accept_untrusted_server_certs,
        default_publishing_interval=default_publishing_interval,
        default_sampling_interval=default_sampling_interval,
        default_queue_size=default_queue_size,
        keep_alive=keep_alive,
        run_asset_discovery=run_asset_discovery,
        session_timeout=session_timeout,
        session_keep_alive=session_keep_alive,
        session_reconnect_exponential_back_off=session_reconnect_exponential_back_off,
        session_reconnect_period=session_reconnect_period,
        security_policy=security_policy,
        security_mode=security_mode,
        sub_life_time=sub_life_time,
        sub_max_items=sub_max_items,
        **kwargs
    )


def create_custom_asset_endpoint_profile(
    cmd,
    asset_endpoint_profile_name: str,
    endpoint_profile_type: str,
    instance_name: str,
    resource_group_name: str,
    target_address: str,
    certificate_reference: Optional[str] = None,
    instance_resource_group: Optional[str] = None,
    instance_subscription: Optional[str] = None,
    location: Optional[str] = None,
    password_reference: Optional[str] = None,
    username_reference: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    additional_configuration: Optional[str] = None,
    **kwargs
) -> dict:
    return AssetEndpointProfiles(cmd).create(
        asset_endpoint_profile_name=asset_endpoint_profile_name,
        endpoint_profile_type=endpoint_profile_type,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        target_address=target_address,
        certificate_reference=certificate_reference,
        instance_resource_group=instance_resource_group,
        instance_subscription=instance_subscription,
        location=location,
        password_reference=password_reference,
        username_reference=username_reference,
        tags=tags,
        additional_configuration=additional_configuration,
        **kwargs
    )


def delete_asset_endpoint_profile(
    cmd,
    asset_endpoint_profile_name: str,
    resource_group_name: str,
    **kwargs
) -> dict:
    return AssetEndpointProfiles(cmd).delete(
        asset_endpoint_profile_name,
        resource_group_name=resource_group_name,
        **kwargs
    )


# TODO: add in once GA
def list_asset_endpoint_profiles(
    cmd,
    resource_group_name: str,
) -> dict:
    return AssetEndpointProfiles(cmd).list(
        resource_group_name=resource_group_name
    )


def query_asset_endpoint_profiles(
    cmd,
    asset_endpoint_profile_name: Optional[str] = None,
    auth_mode: Optional[str] = None,
    custom_query: Optional[str] = None,
    endpoint_profile_type: Optional[str] = None,
    instance_name: Optional[str] = None,
    instance_resource_group: Optional[str] = None,
    location: Optional[str] = None,
    resource_group_name: Optional[str] = None,
    target_address: Optional[str] = None,
) -> List[dict]:
    return AssetEndpointProfiles(cmd).query_asset_endpoint_profiles(
        asset_endpoint_profile_name=asset_endpoint_profile_name,
        auth_mode=auth_mode,
        custom_query=custom_query,
        endpoint_profile_type=endpoint_profile_type,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        location=location,
        resource_group_name=resource_group_name,
        target_address=target_address,
    )


def show_asset_endpoint_profile(
    cmd,
    asset_endpoint_profile_name: str,
    resource_group_name: str,
) -> dict:
    return AssetEndpointProfiles(cmd).show(
        asset_endpoint_profile_name,
        resource_group_name=resource_group_name
    )


def update_asset_endpoint_profile(
    cmd,
    asset_endpoint_profile_name: str,
    resource_group_name: str,
    target_address: Optional[str] = None,
    auth_mode: Optional[str] = None,
    username_reference: Optional[str] = None,
    password_reference: Optional[str] = None,
    certificate_reference: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    **kwargs
) -> dict:
    return AssetEndpointProfiles(cmd).update(
        asset_endpoint_profile_name,
        resource_group_name=resource_group_name,
        target_address=target_address,
        auth_mode=auth_mode,
        certificate_reference=certificate_reference,
        password_reference=password_reference,
        username_reference=username_reference,
        tags=tags,
        **kwargs
    )
