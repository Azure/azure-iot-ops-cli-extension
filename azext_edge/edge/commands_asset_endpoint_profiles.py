# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from typing import Dict, List, Optional

from knack.log import get_logger

from .providers.asset_endpoint_profiles import AssetEndpointProfileProvider

logger = get_logger(__name__)


def create_asset_endpoint_profile(
    cmd,
    asset_endpoint_profile_name: str,
    resource_group_name: str,
    target_address: str,
    additional_configuration: Optional[str] = None,
    auth_mode: Optional[str] = None,
    certificate_reference: Optional[List[str]] = None,
    cluster_name: Optional[str] = None,
    cluster_resource_group: Optional[str] = None,
    cluster_subscription: Optional[str] = None,
    custom_location_name: Optional[str] = None,
    custom_location_resource_group: Optional[str] = None,
    custom_location_subscription: Optional[str] = None,
    transport_authentication: Optional[str] = None,
    location: Optional[str] = None,
    password: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    username: Optional[str] = None,
):
    aep_provider = AssetEndpointProfileProvider(cmd)
    return aep_provider.create(
        asset_endpoint_profile_name=asset_endpoint_profile_name,
        resource_group_name=resource_group_name,
        target_address=target_address,
        additional_configuration=additional_configuration,
        auth_mode=auth_mode,
        certificate_reference=certificate_reference,
        cluster_name=cluster_name,
        cluster_resource_group=cluster_resource_group,
        cluster_subscription=cluster_subscription,
        custom_location_name=custom_location_name,
        custom_location_resource_group=custom_location_resource_group,
        custom_location_subscription=custom_location_subscription,
        transport_authentication=transport_authentication,
        location=location,
        password=password,
        username=username,
        tags=tags
    )


def delete_asset_endpoint_profile(
    cmd,
    asset_endpoint_profile_name: str,
    resource_group_name: str,
) -> dict:
    aep_provider = AssetEndpointProfileProvider(cmd)
    return aep_provider.delete(
        asset_endpoint_profile_name=asset_endpoint_profile_name,
        resource_group_name=resource_group_name
    )


def list_asset_endpoint_profiles(
    cmd,
    resource_group_name: Optional[str] = None,
) -> dict:
    aep_provider = AssetEndpointProfileProvider(cmd)
    return aep_provider.list(resource_group_name=resource_group_name)


def query_asset_endpoint_profiles(
    cmd,
    additional_configuration: Optional[str] = None,
    auth_mode: Optional[str] = None,
    custom_location_name: Optional[str] = None,
    location: Optional[str] = None,
    resource_group_name: Optional[str] = None,
    target_address: Optional[str] = None,
) -> dict:
    aep_provider = AssetEndpointProfileProvider(cmd)
    return aep_provider.query(
        additional_configuration=additional_configuration,
        auth_mode=auth_mode,
        custom_location_name=custom_location_name,
        location=location,
        resource_group_name=resource_group_name,
        target_address=target_address,
    )


def show_asset_endpoint_profile(
    cmd,
    asset_endpoint_profile_name: str,
    resource_group_name: str,
) -> dict:
    aep_provider = AssetEndpointProfileProvider(cmd)
    return aep_provider.show(
        asset_endpoint_profile_name=asset_endpoint_profile_name,
        resource_group_name=resource_group_name
    )


def update_asset_endpoint_profile(
    cmd,
    asset_endpoint_profile_name: str,
    resource_group_name: str,
    target_address: Optional[str] = None,
    additional_configuration: Optional[str] = None,
    auth_mode: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    certificate_reference: Optional[str] = None,
    transport_authentication: Optional[List[str]] = None,
    tags: Optional[Dict[str, str]] = None,
) -> dict:
    aep_provider = AssetEndpointProfileProvider(cmd)
    return aep_provider.update(
        asset_endpoint_profile_name=asset_endpoint_profile_name,
        resource_group_name=resource_group_name,
        target_address=target_address,
        additional_configuration=additional_configuration,
        auth_mode=auth_mode,
        certificate_reference=certificate_reference,
        transport_authentication=transport_authentication,
        password=password,
        username=username,
        tags=tags
    )
