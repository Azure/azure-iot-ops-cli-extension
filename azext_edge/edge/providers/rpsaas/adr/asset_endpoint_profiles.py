# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, List, Optional

from knack.log import get_logger

from azure.cli.core.azclierror import (
    InvalidArgumentValueError,
    MutuallyExclusiveArgumentError,
    RequiredArgumentMissingError,

)
from .base import ADRBaseProvider
from .user_strings import (
    AUTH_REF_MISMATCH_ERROR,
    CERT_AUTH_NOT_SUPPORTED,
    GENERAL_AUTH_REF_MISMATCH_ERROR,
    MISSING_USERPASS_REF_ERROR,
    MISSING_TRANS_AUTH_PROP_ERROR,
    REMOVED_CERT_REF_MSG,
    REMOVED_USERPASS_REF_MSG
)
from ....util import assemble_nargs_to_dict, build_query
from ....common import ResourceTypeMapping, AEPAuthModes

logger = get_logger(__name__)


class AssetEndpointProfileProvider(ADRBaseProvider):
    def __init__(self, cmd):
        super(AssetEndpointProfileProvider, self).__init__(
            cmd=cmd,
            resource_type=ResourceTypeMapping.asset_endpoint_profile.value,
        )

    def create(
        self,
        asset_endpoint_profile_name: str,
        resource_group_name: str,
        target_address: str,
        additional_configuration: Optional[str] = None,
        certificate_reference: Optional[List[str]] = None,
        cluster_name: Optional[str] = None,
        cluster_resource_group: Optional[str] = None,
        cluster_subscription: Optional[str] = None,
        custom_location_name: Optional[str] = None,
        custom_location_resource_group: Optional[str] = None,
        custom_location_subscription: Optional[str] = None,
        transport_authentication: Optional[str] = None,
        location: Optional[str] = None,
        password_reference: Optional[str] = None,
        username_reference: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ):
        if certificate_reference:
            raise InvalidArgumentValueError(CERT_AUTH_NOT_SUPPORTED)
        extended_location = self._check_cluster_and_custom_location(
            custom_location_name=custom_location_name,
            custom_location_resource_group=custom_location_resource_group,
            custom_location_subscription=custom_location_subscription,
            cluster_name=cluster_name,
            cluster_resource_group=cluster_resource_group,
            cluster_subscription=cluster_subscription
        )

        # Location
        if not location:
            location = self.get_location(resource_group_name)

        auth_mode = None
        if not any([username_reference, password_reference, certificate_reference]):
            auth_mode = AEPAuthModes.anonymous.value

        # Properties - bandaid for UI so it processes no transport auth correctly
        properties = {"transportAuthentication": {"ownCertificates": []}}
        _update_properties(
            properties,
            target_address=target_address,
            additional_configuration=additional_configuration,
            auth_mode=auth_mode,
            username_reference=username_reference,
            password_reference=password_reference,
            certificate_reference=certificate_reference,
            transport_authentication=transport_authentication
        )

        resource_path = f"/subscriptions/{self.subscription}/resourceGroups/{resource_group_name}/providers/"\
            f"{self.resource_type}/{asset_endpoint_profile_name}"
        aep_body = {
            "extendedLocation": extended_location,
            "location": location,
            "properties": properties,
            "tags": tags,
        }
        poller = self.resource_client.resources.begin_create_or_update_by_id(
            resource_id=resource_path,
            api_version=self.api_version,
            parameters=aep_body
        )
        return poller

    def query(
        self,
        additional_configuration: Optional[str] = None,
        auth_mode: Optional[str] = None,
        custom_location_name: Optional[str] = None,
        location: Optional[str] = None,
        resource_group_name: Optional[str] = None,
        target_address: Optional[str] = None,
    ) -> dict:
        query = ""
        if additional_configuration:
            query += f"| where properties.additionalConfiguration =~ \"{additional_configuration}\""
        if auth_mode:
            query += f"| where properties.userAuthentication.mode =~ \"{auth_mode}\""
        if custom_location_name:
            query += f"| where extendedLocation.name contains \"{custom_location_name}\""
        if target_address:
            query += f"| where properties.targetAddress =~ \"{target_address}\""

        return build_query(
            self.cmd,
            subscription_id=self.subscription,
            custom_query=query,
            location=location,
            resource_group=resource_group_name,
            type=self.resource_type,
            additional_project="extendedLocation"
        )

    def update(
        self,
        asset_endpoint_profile_name: str,
        resource_group_name: str,
        target_address: Optional[str] = None,
        additional_configuration: Optional[str] = None,
        auth_mode: Optional[str] = None,
        username_reference: Optional[str] = None,
        password_reference: Optional[str] = None,
        certificate_reference: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ):
        # get the asset
        original_aep = self.show_and_check(
            asset_endpoint_profile_name,
            resource_group_name=resource_group_name
        )
        if tags:
            original_aep["tags"] = tags

        # modify the asset endpoint profile
        properties = original_aep.get("properties", {})
        _update_properties(
            properties,
            target_address=target_address,
            additional_configuration=additional_configuration,
            auth_mode=auth_mode,
            username_reference=username_reference,
            password_reference=password_reference,
            certificate_reference=certificate_reference,
        )

        poller = self.resource_client.resources.begin_create_or_update_by_id(
            resource_id=original_aep["id"],
            api_version=self.api_version,
            parameters=original_aep
        )
        return poller

    def add_transport_auth(
        self,
        asset_endpoint_profile_name: str,
        resource_group_name: str,
        password_reference: str,
        secret_reference: str,
        thumbprint: str,
    ):
        original_aep = self.show_and_check(
            asset_endpoint_profile_name,
            resource_group_name=resource_group_name
        )
        if original_aep["properties"].get("transportAuthentication") is None:
            original_aep["properties"]["transportAuthentication"] = {
                "ownCertificates": []
            }

        cert = {
            "certThumbprint": thumbprint,
            "certSecretReference": secret_reference,
            "certPasswordReference": password_reference,
        }
        original_aep["properties"]["transportAuthentication"]["ownCertificates"].append(cert)

        poller = self.resource_client.resources.begin_create_or_update_by_id(
            resource_id=original_aep["id"],
            api_version=self.api_version,
            parameters=original_aep,
        )
        poller.wait()
        original_aep = poller.result()
        if not isinstance(original_aep, dict):
            original_aep = original_aep.as_dict()
        return original_aep["properties"]["transportAuthentication"]

    def list_transport_auths(
        self,
        asset_endpoint_profile_name: str,
        resource_group_name: str
    ):
        original_aep = self.show(
            asset_endpoint_profile_name,
            resource_group_name=resource_group_name
        )

        return original_aep["properties"].get("transportAuthentication", {"ownCertificates": []})

    def remove_transport_auth(
        self,
        asset_endpoint_profile_name: str,
        thumbprint: str,
        resource_group_name: str,
    ):
        original_aep = self.show_and_check(
            asset_endpoint_profile_name,
            resource_group_name=resource_group_name
        )
        if original_aep["properties"].get("transportAuthentication") is None:
            original_aep["properties"]["transportAuthentication"] = {
                "ownCertificates": []
            }

        certs = original_aep["properties"]["transportAuthentication"]["ownCertificates"]
        certs = [cert for cert in certs if cert["certThumbprint"] != thumbprint]

        original_aep["properties"]["transportAuthentication"]["ownCertificates"] = certs

        poller = self.resource_client.resources.begin_create_or_update_by_id(
            resource_id=original_aep["id"],
            api_version=self.api_version,
            parameters=original_aep
        )
        poller.wait()
        original_aep = poller.result()
        if not isinstance(original_aep, dict):
            original_aep = original_aep.as_dict()
        return original_aep["properties"]["transportAuthentication"]


# Helpers
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
        auth_props["mode"] = AEPAuthModes.certificate.value
        auth_props["x509Credentials"] = {"certificateReference": certificate_reference}
        if auth_props.pop("usernamePasswordCredentials", None):
            logger.warning(REMOVED_USERPASS_REF_MSG)
    elif (username_reference or password_reference) and auth_mode in [None, AEPAuthModes.userpass.value]:
        auth_props["mode"] = AEPAuthModes.userpass.value
        user_creds = auth_props.get("usernamePasswordCredentials", {})
        user_creds["usernameReference"] = username_reference
        user_creds["passwordReference"] = password_reference
        if not all([user_creds["usernameReference"], user_creds["passwordReference"]]):
            raise RequiredArgumentMissingError(MISSING_USERPASS_REF_ERROR)
        auth_props["usernamePasswordCredentials"] = user_creds
        if auth_props.pop("x509Credentials", None):
            logger.warning(REMOVED_CERT_REF_MSG)
    elif auth_mode == AEPAuthModes.anonymous.value and not any(
        [certificate_reference, username_reference, password_reference]
    ):
        auth_props["mode"] = AEPAuthModes.anonymous.value
        if auth_props.pop("x509Credentials", None):
            logger.warning(REMOVED_CERT_REF_MSG)
        if auth_props.pop("usernamePasswordCredentials", None):
            logger.warning(REMOVED_USERPASS_REF_MSG)
    elif any([auth_mode, certificate_reference, username_reference, password_reference]):
        raise MutuallyExclusiveArgumentError(GENERAL_AUTH_REF_MISMATCH_ERROR)

    return auth_props


def _process_certificates(cert_list: Optional[List[List[str]]] = None) -> List[Dict[str, str]]:
    """This is for the main create/update endpoint commands"""
    if not cert_list:
        return []
    processed_certs = []
    for cert in cert_list:
        parsed_cert = assemble_nargs_to_dict(cert)
        if set(parsed_cert.keys()) != set(["password", "thumbprint", "secret"]):
            raise RequiredArgumentMissingError(MISSING_TRANS_AUTH_PROP_ERROR.format(cert))

        processed_point = {
            "certThumbprint": parsed_cert["thumbprint"],
            "certSecretReference": parsed_cert["secret"],
            "certPasswordReference": parsed_cert["password"],
        }
        processed_certs.append(processed_point)

    return processed_certs


def _update_properties(
    properties,
    target_address: Optional[str] = None,
    additional_configuration: Optional[str] = None,
    auth_mode: Optional[str] = None,
    username_reference: Optional[str] = None,
    password_reference: Optional[str] = None,
    certificate_reference: Optional[str] = None,
    transport_authentication: Optional[List[str]] = None,
):
    if additional_configuration:
        properties["additionalConfiguration"] = additional_configuration
    if target_address:
        properties["targetAddress"] = target_address
    if transport_authentication:
        properties["transportAuthentication"] = {
            "ownCertificates": _process_certificates(transport_authentication)
        }
    if any([auth_mode, username_reference, password_reference, certificate_reference]):
        auth_props = properties.get("userAuthentication", {})
        properties["userAuthentication"] = _process_authentication(
            auth_props=auth_props,
            auth_mode=auth_mode,
            certificate_reference=certificate_reference,
            username_reference=username_reference,
            password_reference=password_reference
        )
