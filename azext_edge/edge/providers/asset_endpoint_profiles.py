# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from typing import Dict, List, Optional

from knack.log import get_logger

from azure.cli.core.azclierror import (
    MutuallyExclusiveArgumentError,
    ResourceNotFoundError,
    RequiredArgumentMissingError,
    ValidationError
)

from ..util import assemble_nargs_to_dict, build_query
from ..common import ResourceTypeMapping, AEPAuthModes

logger = get_logger(__name__)

API_VERSION = "2023-08-01-preview"
# API_VERSION = "2023-10-01-preview"


class AssetEndpointProfileProvider():
    def __init__(self, cmd):
        from azure.cli.core.commands.client_factory import get_subscription_id
        from azure.identity import DefaultAzureCredential
        from azure.mgmt.resource import ResourceManagementClient

        self.cmd = cmd
        self.subscription = get_subscription_id(cmd.cli_ctx)
        self.resource_client = ResourceManagementClient(
            credential=DefaultAzureCredential(),
            subscription_id=self.subscription
        )
        self.resource_type = ResourceTypeMapping.asset_endpoint_profile.value

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
        password: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        username: Optional[str] = None,
    ):
        custom_location_id = self._check_cluster_and_custom_location(
            custom_location_name=custom_location_name,
            custom_location_resource_group=custom_location_resource_group,
            custom_location_subscription=custom_location_subscription,
            cluster_name=cluster_name,
            cluster_resource_group=cluster_resource_group,
            cluster_subscription=cluster_subscription
        )

        # extended location
        extended_location = {
            "type": "CustomLocation",
            "name": custom_location_id
        }
        # Location
        if not location:
            resource_group = self.resource_client.resource_groups.get(resource_group_name=resource_group_name)
            location = resource_group.as_dict()["location"]

        auth_mode = None
        if not any([username, password, certificate_reference]):
            auth_mode = AEPAuthModes.anonymous.value

        # Properties
        properties = {}
        _update_properties(
            properties,
            target_address=target_address,
            additional_configuration=additional_configuration,
            auth_mode=auth_mode,
            username=username,
            password=password,
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
            api_version=API_VERSION,
            parameters=aep_body
        )
        return poller

    def delete(
        self,
        asset_endpoint_profile_name: str,
        resource_group_name: str
    ):
        self.resource_client.resources.begin_delete(
            resource_group_name=resource_group_name,
            resource_provider_namespace=self.resource_type,
            parent_resource_path="",
            resource_type="",
            resource_name=asset_endpoint_profile_name,
            api_version=API_VERSION
        )

    def list(
        self,
        resource_group_name: Optional[str] = None,
    ) -> dict:
        # Note the usage of az rest/send_raw_request over resource
        # az resource list/resource_client.resources.list will omit properties
        from ..util.common import _process_raw_request
        uri = f"/subscriptions/{self.subscription}"
        if resource_group_name:
            uri += f"/resourceGroups/{resource_group_name}"
        uri += f"/providers/{self.resource_type}?api-version={API_VERSION}"
        return _process_raw_request(
            cmd=self.cmd, method="GET", url=uri, keyword="value"
        )

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

    def show(
        self,
        asset_endpoint_profile_name: str,
        resource_group_name: str
    ) -> dict:
        result = self.resource_client.resources.get(
            resource_group_name=resource_group_name,
            resource_provider_namespace=self.resource_type,
            parent_resource_path="",
            resource_type="",
            resource_name=asset_endpoint_profile_name,
            api_version=API_VERSION
        )
        return result.as_dict()

    def update(
        self,
        asset_endpoint_profile_name: str,
        resource_group_name: str,
        target_address: Optional[str] = None,
        additional_configuration: Optional[str] = None,
        auth_mode: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        certificate_reference: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ):
        # get the asset
        original_aep = self.show(
            asset_endpoint_profile_name=asset_endpoint_profile_name,
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
            username=username,
            password=password,
            certificate_reference=certificate_reference,
        )

        poller = self.resource_client.resources.begin_create_or_update_by_id(
            resource_id=original_aep["id"],
            api_version=API_VERSION,
            parameters=original_aep
        )
        return poller

    def add_transport_auth(
        self,
        asset_endpoint_profile_name: str,
        resource_group_name: str,
        password: str,
        secret: str,
        thumbprint: str,
    ):
        original_aep = self.show(
            asset_endpoint_profile_name=asset_endpoint_profile_name,
            resource_group_name=resource_group_name
        )
        if original_aep["properties"].get("transportAuthentication") is None:
            original_aep["properties"]["transportAuthentication"] = {
                "ownCertificates": []
            }

        cert = {
            "certThumbprint": thumbprint,
            "certSecretReference": secret,
            "certPasswordReference": password,
        }
        original_aep["properties"]["transportAuthentication"]["ownCertificates"].append(cert)

        poller = self.resource_client.resources.begin_create_or_update_by_id(
            resource_id=original_aep["id"],
            api_version=API_VERSION,
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
            asset_endpoint_profile_name=asset_endpoint_profile_name,
            resource_group_name=resource_group_name
        )

        return original_aep["properties"].get(
            "transportAuthentication",
            {"ownCertificates": []}
        )

    def remove_transport_auth(
        self,
        asset_endpoint_profile_name: str,
        thumbprint: str,
        resource_group_name: str,
    ):
        original_aep = self.show(
            asset_endpoint_profile_name=asset_endpoint_profile_name,
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
            api_version=API_VERSION,
            parameters=original_aep
        )
        poller.wait()
        original_aep = poller.result()
        if not isinstance(original_aep, dict):
            original_aep = original_aep.as_dict()
        return original_aep["properties"]["transportAuthentication"]

    def _check_cluster_connectivity(
        self,
        custom_location_id: str,
        cluster_subscription: str = None,
    ):
        if not cluster_subscription:
            cluster_subscription = custom_location_id.split("/")[2]
        query = f'| where id =~ "{custom_location_id}"'
        cluster_query_result = build_query(
            self.cmd,
            subscription_id=cluster_subscription,
            custom_query=query,
            type=ResourceTypeMapping.connected_cluster.value
        )
        if len(cluster_query_result) == 0:
            raise ValidationError(
                f"Cluster associated with the custom location {custom_location_id} not found. Please "
                "check if cluster exists."
            )
        cluster = cluster_query_result[0]
        if cluster["properties"]["connectivityStatus"] != "Online":
            raise ValidationError(
                f"Cluster {cluster['name']} is not online, asset endpoint profile commands may fail."
            )

    def _check_cluster_and_custom_location(
        self,
        custom_location_name: str = None,
        custom_location_resource_group: str = None,
        custom_location_subscription: str = None,
        cluster_name: str = None,
        cluster_resource_group: str = None,
        cluster_subscription: str = None,
    ):
        if not any([cluster_name, custom_location_name]):
            raise RequiredArgumentMissingError("Need to provide either cluster name or custom location")
        query = ""
        cluster = None
        if not custom_location_subscription:
            custom_location_subscription = self.subscription
        if not cluster_subscription:
            cluster_subscription = self.subscription

        # provide cluster name - start with checking for the cluster (if can)
        if cluster_name:
            cluster_query_result = build_query(
                self.cmd,
                subscription_id=cluster_subscription,
                type=ResourceTypeMapping.connected_cluster.value,
                name=cluster_name,
                resource_group=cluster_resource_group
            )
            if len(cluster_query_result) == 0:
                raise ResourceNotFoundError(f"Cluster {cluster_name} not found.")
            if len(cluster_query_result) > 1:
                raise ValidationError(
                    f"Found {len(cluster_query_result)} clusters with the name {cluster_name}. Please "
                    "provide the resource group for the cluster."
                )
            cluster = cluster_query_result[0]
            # reset query so the location query will ensure that the cluster is associated
            query = f"| where properties.hostResourceId =~ \"{cluster['id']}\" "

        # try to find location, either from given param and/or from cluster
        # if only location is provided, will look just by location name
        # if both cluster name and location are provided, should also include cluster id to narrow association
        location_query_result = build_query(
            self.cmd,
            subscription_id=custom_location_subscription,
            custom_query=query,
            type=ResourceTypeMapping.custom_location.value,
            name=custom_location_name,
            resource_group=custom_location_resource_group
        )
        if len(location_query_result) == 0:
            error_details = ""
            if custom_location_name:
                error_details += f"{custom_location_name} "
            if cluster_name:
                error_details += f"for cluster {cluster_name} "
            raise ResourceNotFoundError(f"Custom location {error_details}not found.")

        if len(location_query_result) > 1 and cluster_name is None:
            raise ValidationError(
                f"Found {len(location_query_result)} custom locations with the name {custom_location_name}. Please "
                "provide the resource group for the custom location."
            )
        # by this point there should be at least one custom location
        # if cluster name was given (and no custom_location_names), there can be more than one
        # otherwise, if no cluster name, needs to be only one

        # should trigger if only the location name was provided - there should be one location
        if not cluster_name:
            query = f'| where id =~ "{location_query_result[0]["properties"]["hostResourceId"]}"'
            cluster_query_result = build_query(
                self.cmd,
                subscription_id=cluster_subscription,
                custom_query=query,
                type=ResourceTypeMapping.connected_cluster.value
            )
            if len(cluster_query_result) == 0:
                raise ValidationError(
                    f"Cluster associated with custom location {custom_location_name} does not exist."
                )
            cluster = cluster_query_result[0]
        # by this point, cluster is populated

        possible_locations = []
        for location in location_query_result:
            usable = False
            for extension_id in location["properties"]["clusterExtensionIds"]:
                # extensions not findable in graph :(
                extension = self.resource_client.resources.get_by_id(
                    resource_id=extension_id,
                    api_version="2023-05-01",
                ).as_dict()
                if extension["properties"]["extensionType"] == "microsoft.deviceregistry.assets":
                    usable = True
                    break
            if usable:
                possible_locations.append(location["id"])

        # throw if there are no suitable extensions (in the cluster)
        if len(possible_locations) == 0:
            raise ValidationError(
                f"Cluster {cluster['name']} is missing the microsoft.deviceregistry.assets extension."
            )
        # here we warn about multiple custom locations (cluster name given, multiple locations possible)
        if len(possible_locations) > 1:
            possible_locations = "\n".join(possible_locations)
            raise ValidationError(
                f"The following custom locations were found for cluster {cluster['id']}: \n{possible_locations}. "
                "Please specify which custom location to use."
            )

        return possible_locations[0]


# Helpers
def _process_authentication(
    auth_mode: Optional[str] = None,
    auth_props: Optional[Dict[str, str]] = None,
    certificate_reference: Optional[str] = None,
    password: Optional[str] = None,
    username: Optional[str] = None
) -> Dict[str, str]:
    if not auth_props:
        auth_props = {}
    # add checking for ensuring auth mode is set with proper params
    if certificate_reference and (username or password):
        raise Exception("Please choose to use a certificate reference or a username/password for authentication.")

    if certificate_reference and auth_mode in [None, AEPAuthModes.certificate.value]:
        auth_props["mode"] = AEPAuthModes.certificate.value
        auth_props["x509Credentials"] = {"certificateReference": certificate_reference}
        if auth_props.pop("usernamePasswordCredentials", None):
            logger.warning("Previously used username and password references were removed.")

    elif (username or password) and auth_mode in [None, AEPAuthModes.userpass.value]:
        auth_props["mode"] = AEPAuthModes.userpass.value
        user_creds = auth_props.get("usernamePasswordCredentials", {})
        user_creds["usernameReference"] = username
        user_creds["passwordReference"] = password
        if not all([user_creds["usernameReference"], user_creds["passwordReference"]]):
            raise RequiredArgumentMissingError(
                "Please provide username and password reference for UsernamePassword authentication."
            )
        auth_props["usernamePasswordCredentials"] = user_creds
        if auth_props.pop("x509Credentials", None):
            logger.warning("Previously used certificate reference was removed.")
    elif auth_mode == AEPAuthModes.anonymous.value and not any([certificate_reference, username, password]):
        auth_props["mode"] = AEPAuthModes.anonymous.value
        if auth_props.pop("x509Credentials", None):
            logger.warning("Previously used certificate reference was removed.")
        if auth_props.pop("usernamePasswordCredentials", None):
            logger.warning("Previously used username and password references were removed.")
    elif any([auth_mode, certificate_reference, username, password]):
        raise MutuallyExclusiveArgumentError("Invalid combination of authentication mode and parameters.")

    return auth_props


def _process_certificates(cert_list: Optional[List[List[str]]] = None) -> List[Dict[str, str]]:
    """This is for the main create/update endpoint commands"""
    if not cert_list:
        return []
    processed_certs = []
    for cert in cert_list:
        parsed_cert = assemble_nargs_to_dict(cert)
        if set(parsed_cert.keys()) != set(["password", "thumbprint", "secret"]):
            raise RequiredArgumentMissingError(
                f"Transport authentication ({cert}) needs to have all of [password, thumbprint, and secret]."
            )

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
    username: Optional[str] = None,
    password: Optional[str] = None,
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
    if any([auth_mode, username, password, certificate_reference]):
        auth_props = properties.get("userAuthentication", {})
        properties["userAuthentication"] = _process_authentication(
            auth_props=auth_props,
            auth_mode=auth_mode,
            certificate_reference=certificate_reference,
            username=username,
            password=password
        )
