# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from typing import TYPE_CHECKING, Dict, Iterable, Optional, Union

from knack.log import get_logger

from azure.cli.core.azclierror import (
    InvalidArgumentValueError,
    MutuallyExclusiveArgumentError,
    RequiredArgumentMissingError,
)
from .user_strings import (
    AUTH_REF_MISMATCH_ERROR,
    GENERAL_AUTH_REF_MISMATCH_ERROR,
    MISSING_USERPASS_REF_ERROR,
    REMOVED_CERT_REF_MSG,
    REMOVED_USERPASS_REF_MSG,
)
from ....util.az_client import get_registry_mgmt_client
from ....util.queryable import Queryable
from ....common import AEPAuthModes

if TYPE_CHECKING:
    from ....vendor.clients.deviceregistrymgmt.operations import (
        DiscoveredAssetEndpointProfilesOperations as DAEPOperations,
        AssetEndpointProfilesOperations as AEPOperations
    )

logger = get_logger(__name__)
AEP_RESOURCE_TYPE = "Microsoft.DeviceRegistry/assetEndpointProfiles"
DISCOVERED_AEP_RESOURCE_TYPE = "Microsoft.DeviceRegistry/discoveredAssetEndpointProfiless"


# TODO: soul searching to see if I should combine with assets class
class AssetEndpointProfiles(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.deviceregistry_mgmt_client = get_registry_mgmt_client(
            subscription_id=self.default_subscription_id
        )
        self.ops: "AEPOperations" = self.deviceregistry_mgmt_client.asset_endpoint_profiles
        self.discovered_ops: "DAEPOperations" = self.deviceregistry_mgmt_client.discovered_asset_endpoint_profiles
        self.update_ops: Optional[Union["AEPOperations", "DAEPOperations"]] = None

    def create(
        self,
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
        discovered: bool = False,  # for easy discovered debugging
        **additional_configuration
    ):
        from .helpers import get_extended_location
        extended_location = get_extended_location(
            cmd=self.cmd,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group or resource_group_name,
            instance_subscription=instance_subscription
        )
        cluster_location = extended_location.pop("cluster_location")

        auth_mode = None
        if not any([username_reference, password_reference, certificate_reference]):
            auth_mode = AEPAuthModes.anonymous.value

        # Properties
        properties = {"endpointProfileType": endpoint_profile_type}

        if endpoint_profile_type == "OPCUA":
            properties["additionalConfiguration"] = _build_opcua_config(**additional_configuration)
        # TODO: add other connector types in
        _update_properties(
            properties,
            target_address=target_address,
            auth_mode=auth_mode,
            username_reference=username_reference,
            password_reference=password_reference,
            certificate_reference=certificate_reference,
        )
        # discovered
        if discovered:
            self.ops = self.discovered_ops
            properties.pop("authentication", None)
            properties["version"] = 1
            properties["discoveryId"] = "discoveryid1"

        aep_body = {
            "extendedLocation": extended_location,
            "location": location or cluster_location,
            "properties": properties,
            "tags": tags,
        }
        return self.ops.begin_create_or_replace(
            resource_group_name,
            asset_endpoint_profile_name,
            resource=aep_body
        )

    def delete(self, asset_endpoint_profile_name: str, resource_group_name: str):
        self.show(
            asset_endpoint_profile_name=asset_endpoint_profile_name,
            resource_group_name=resource_group_name,
            check_cluster=True
        )
        return self.update_ops.begin_delete(
            resource_group_name,
            asset_endpoint_profile_name,
        )

    def show(
        self, asset_endpoint_profile_name: str, resource_group_name: str, check_cluster: bool = False
    ) -> dict:
        asset_endpoint = self.ops.get(
            resource_group_name=resource_group_name, asset_endpoint_profile_name=asset_endpoint_profile_name
        )
        self.update_ops = self.ops
        if check_cluster:
            from .helpers import check_cluster_connectivity
            check_cluster_connectivity(self.cmd, asset_endpoint)
        return asset_endpoint

    def list(self, resource_group_name: Optional[str] = None, discovered: bool = False) -> Iterable[dict]:
        if discovered:
            if resource_group_name:
                return self.discovered_ops.list_by_resource_group(resource_group_name=resource_group_name)
            return self.discovered_ops.list_by_subscription()

        if resource_group_name:
            return self.ops.list_by_resource_group(resource_group_name=resource_group_name)
        return self.ops.list_by_subscription()

    # TODO: unit test
    def query_asset_endpoint_profiles(
        self,
        asset_endpoint_profile_name: Optional[str] = None,
        auth_mode: Optional[str] = None,
        custom_query: Optional[str] = None,
        discovered: Optional[bool] = None,
        endpoint_profile_type: Optional[str] = None,
        instance_name: Optional[str] = None,
        instance_resource_group: Optional[str] = None,
        location: Optional[str] = None,
        resource_group_name: Optional[str] = None,
        target_address: Optional[str] = None,
    ) -> dict:
        query_body = custom_query or _build_query_body(
            asset_endpoint_profile_name=asset_endpoint_profile_name,
            auth_mode=auth_mode,
            endpoint_profile_type=endpoint_profile_type,
            location=location,
            resource_group_name=resource_group_name,
            target_address=target_address
        )

        if discovered is not None:
            resource_type = DISCOVERED_AEP_RESOURCE_TYPE if discovered else AEP_RESOURCE_TYPE
            query = f"Resources | where type =~\"{resource_type}\" " + query_body
        else:
            # we put the query body into the each type query and then union to avoid the union result from
            # becoming too big
            query = f"Resources | where type =~ \"{AEP_RESOURCE_TYPE}\" {query_body} "\
                f"| union (Resources | where type =~ \"{DISCOVERED_AEP_RESOURCE_TYPE}\" {query_body})"

        if any([instance_name, instance_resource_group]):
            instance_query = "Resources | where type =~ 'microsoft.iotoperations/instances' "
            if instance_name:
                instance_query += f"| where name =~ \"{instance_name}\""
            if instance_resource_group:
                instance_query += f"| where resourceGroup =~ \"{instance_resource_group}\""

            # fetch the custom location + join on innerunique. Then remove the extra customLocation1 generated
            query = f"{instance_query} | extend customLocation = tostring(extendedLocation.name) "\
                f"| project customLocation | join kind=innerunique ({query}) on customLocation "\
                "| project-away customLocation1"
        return self.query(query=query)

    def update(
        self,
        asset_endpoint_profile_name: str,
        resource_group_name: str,
        target_address: Optional[str] = None,
        auth_mode: Optional[str] = None,
        username_reference: Optional[str] = None,
        password_reference: Optional[str] = None,
        certificate_reference: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ):
        # get the asset
        original_aep = self.show(
            asset_endpoint_profile_name,
            resource_group_name=resource_group_name,
            check_cluster=True
        )
        if tags:
            original_aep["tags"] = tags

        # modify the asset endpoint profile
        properties = original_aep.get("properties", {})
        _update_properties(
            properties,
            target_address=target_address,
            auth_mode=auth_mode,
            username_reference=username_reference,
            password_reference=password_reference,
            certificate_reference=certificate_reference,
        )
        # use this over update since we want to make sure we get the tags in
        return self.update_ops.begin_create_or_replace(
            resource_group_name,
            asset_endpoint_profile_name,
            original_aep
        )


# Helpers
def _build_opcua_config(
    original_config: Optional[str] = None,
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
):
    config = json.loads(original_config) if original_config else {}

    if application_name:
        config["applicationName"] = application_name
    if keep_alive:
        # min 0?
        config["keepAliveMilliseconds"] = keep_alive
    if run_asset_discovery is not None:
        config["runAssetDiscovery"] = run_asset_discovery

    # defaults
    if any([
        default_publishing_interval, default_sampling_interval, default_queue_size
    ]) and not config.get("defaults"):
        config["defaults"] = {}
    if default_publishing_interval:
        # min 0
        config["defaults"]["publishingIntervalMilliseconds"] = default_publishing_interval
    if default_sampling_interval:
        # min 0
        config["defaults"]["samplingIntervalMilliseconds"] = default_sampling_interval
    if default_queue_size:
        # min 0
        config["defaults"]["queueSize"] = default_queue_size

    # session
    if any([
        session_timeout, session_reconnect_period, session_keep_alive, session_reconnect_exponential_back_off
    ]) and not config.get("session"):
        config["session"] = {}
    if session_timeout:
        config["session"]["timeoutMilliseconds"] = session_timeout
    if session_keep_alive:
        config["session"]["keepAliveIntervalMilliseconds"] = session_keep_alive
    if session_reconnect_period:
        config["session"]["reconnectPeriodMilliseconds"] = session_reconnect_period
    if session_reconnect_exponential_back_off:
        config["session"]["reconnectExponentialBackOffMilliseconds"] = session_reconnect_exponential_back_off

    # subscription
    if any([sub_life_time, sub_max_items]) and not config.get("subscription"):
        config["subscription"] = {}
    if sub_life_time:
        config["subscription"]["maxItems"] = sub_life_time
    if sub_max_items:
        config["subscription"]["lifeTimeMilliseconds"] = sub_max_items

    # security
    if any([
        auto_accept_untrusted_server_certs is not None, security_mode, security_policy
    ]) and not config.get("security"):
        config["security"] = {}
    if auto_accept_untrusted_server_certs is not None:
        config["security"]["autoAcceptUntrustedServerCertificates"] = auto_accept_untrusted_server_certs
    if security_mode:
        config["security"]["securityMode"] = security_mode
    if security_policy:
        config["security"]["securityPolicy"] = security_policy

    return json.dumps(config)


def assert_above_zero(param: str, number: int):
    if number < 0:
        raise InvalidArgumentValueError(f"The parameter {param} needs to be a non-negative integer.")


def _build_query_body(
    asset_endpoint_profile_name: Optional[str] = None,
    auth_mode: Optional[str] = None,
    endpoint_profile_type: Optional[str] = None,
    location: Optional[str] = None,
    resource_group_name: Optional[str] = None,
    target_address: Optional[str] = None,
) -> str:
    query_body = ""
    if resource_group_name:
        query_body += f"| where resourceGroup =~ \"{resource_group_name}\""
    if location:
        query_body += f"| where location =~ \"{location}\""
    if asset_endpoint_profile_name:
        query_body += f"| where name =~ \"{asset_endpoint_profile_name}\""
    if auth_mode:
        query_body += f"| where properties.authentication.method =~ \"{auth_mode}\""
    if endpoint_profile_type:
        query_body += f"| where properties.endpointProfileType =~ \"{endpoint_profile_type}\""
    if target_address:
        query_body += f"| where properties.targetAddress =~ \"{target_address}\""

    query_body += "| extend customLocation = tostring(extendedLocation.name) "\
        "| extend provisioningState = properties.provisioningState "\
        "| project id, customLocation, location, name, resourceGroup, provisioningState, tags, "\
        "type, subscriptionId "
    return query_body


def _process_authentication(
    auth_mode: Optional[str] = None,
    auth_props: Optional[Dict[str, str]] = None,
    certificate_reference: Optional[str] = None,
    password_reference: Optional[str] = None,
    username_reference: Optional[str] = None
) -> Dict[str, str]:
    if not auth_props:
        auth_props = {}
    # add checking for ensuring auth mode is set with proper params
    if certificate_reference and (username_reference or password_reference):
        raise MutuallyExclusiveArgumentError(AUTH_REF_MISMATCH_ERROR)

    if certificate_reference and auth_mode in [None, AEPAuthModes.certificate.value]:
        auth_props["method"] = AEPAuthModes.certificate.value
        auth_props["x509Credentials"] = {"certificateSecretName": certificate_reference}
        if auth_props.pop("usernamePasswordCredentials", None):
            logger.warning(REMOVED_USERPASS_REF_MSG)
    elif (username_reference or password_reference) and auth_mode in [None, AEPAuthModes.userpass.value]:
        auth_props["method"] = AEPAuthModes.userpass.value
        user_creds = auth_props.get("usernamePasswordCredentials", {})
        user_creds["usernameSecretName"] = username_reference
        user_creds["passwordSecretName"] = password_reference
        if not all([user_creds["usernameSecretName"], user_creds["passwordSecretName"]]):
            raise RequiredArgumentMissingError(MISSING_USERPASS_REF_ERROR)
        auth_props["usernamePasswordCredentials"] = user_creds
        if auth_props.pop("x509Credentials", None):
            logger.warning(REMOVED_CERT_REF_MSG)
    elif auth_mode == AEPAuthModes.anonymous.value and not any(
        [certificate_reference, username_reference, password_reference]
    ):
        auth_props["method"] = AEPAuthModes.anonymous.value
        if auth_props.pop("x509Credentials", None):
            logger.warning(REMOVED_CERT_REF_MSG)
        if auth_props.pop("usernamePasswordCredentials", None):
            logger.warning(REMOVED_USERPASS_REF_MSG)
    elif any([auth_mode, certificate_reference, username_reference, password_reference]):
        raise MutuallyExclusiveArgumentError(GENERAL_AUTH_REF_MISMATCH_ERROR)

    return auth_props


def _update_properties(
    properties,
    target_address: Optional[str] = None,
    additional_configuration: Optional[str] = None,
    auth_mode: Optional[str] = None,
    username_reference: Optional[str] = None,
    password_reference: Optional[str] = None,
    certificate_reference: Optional[str] = None,
):
    if additional_configuration:
        properties["additionalConfiguration"] = additional_configuration
    if target_address:
        properties["targetAddress"] = target_address
    if any([auth_mode, username_reference, password_reference, certificate_reference]):
        auth_props = properties.get("authentication", {})
        properties["authentication"] = _process_authentication(
            auth_props=auth_props,
            auth_mode=auth_mode,
            certificate_reference=certificate_reference,
            username_reference=username_reference,
            password_reference=password_reference
        )
