# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict, List, Optional
from knack.log import get_logger
from azure.cli.core.azclierror import (
    ResourceNotFoundError,
    RequiredArgumentMissingError,
    ValidationError
)

from .user_strings import (
    CUSTOM_LOCATION_DOES_NOT_EXIST_ERROR,
    CUSTOM_LOCATION_NOT_FOUND_MSG,
    CLUSTER_NOT_FOUND_MSG,
    CLUSTER_OFFLINE_MSG,
    MISSING_CLUSTER_CUSTOM_LOCATION_ERROR,
    MISSING_EXTENSION_ERROR,
    MULTIPLE_CUSTOM_LOCATIONS_ERROR,
    MULTIPLE_POSSIBLE_ITEMS_ERROR,
    NO_EXTENDED_LOCATION_TO_CHECK_MSG
)
from ...util import build_query
from ...common import ResourceTypeMapping

logger = get_logger(__name__)
EXTENSION_API_VERSION = "2023-05-01"


class RPSaaSBaseProvider:
    def __init__(
        self,
        cmd,
        api_version: str,
        resource_type: str,
        required_extension: str,
    ):
        from azure.cli.core.commands.client_factory import get_subscription_id
        from ...util.az_client import get_resource_client

        self.cmd = cmd
        self.subscription = get_subscription_id(cmd.cli_ctx)
        self.resource_client = get_resource_client(subscription_id=self.subscription)
        self.api_version = api_version
        self.resource_type = resource_type
        self.required_extension = required_extension

    def delete(
        self,
        resource_name: str,
        resource_group_name: str,
        check_cluster_connectivity: bool = False,
    ):
        # Note that delete should not break if the item does not exist so checking is not required
        if check_cluster_connectivity:
            self.show(
                resource_name=resource_name,
                resource_group_name=resource_group_name,
                check_cluster_connectivity=check_cluster_connectivity
            )
        return self.resource_client.resources.begin_delete(
            resource_group_name=resource_group_name,
            resource_provider_namespace="",
            parent_resource_path="",
            resource_type=self.resource_type,
            resource_name=resource_name,
            api_version=self.api_version
        )

    def get_location(
        self,
        resource_group_name: str
    ) -> str:
        resource_group = self.resource_client.resource_groups.get(resource_group_name=resource_group_name)
        return resource_group.as_dict()["location"]

    def list(
        self,
        resource_group_name: Optional[str] = None,
    ) -> List[Any]:
        # Note the usage of az rest/send_raw_request over resource
        # az resource list/resource_client.resources.list will omit properties
        from ...util.common import _process_raw_request
        uri = f"/subscriptions/{self.subscription}"
        if resource_group_name:
            uri += f"/resourceGroups/{resource_group_name}"
        uri += f"/providers/{self.resource_type}?api-version={self.api_version}"
        return _process_raw_request(
            cmd=self.cmd, method="GET", url=uri, keyword="value"
        )

    def show(
        self,
        resource_name: str,
        resource_group_name: str,
        check_cluster_connectivity: bool = False,
    ) -> Dict[str, Any]:
        result = self.resource_client.resources.get(
            resource_group_name=resource_group_name,
            resource_provider_namespace="",
            parent_resource_path="",
            resource_type=self.resource_type,
            resource_name=resource_name,
            api_version=self.api_version
        )
        # serialize takes out id
        # as_dict turns extendedLocation into extended_location
        # fix as_dict here
        result = result.as_dict()
        extended_location = result.pop("extended_location", None)
        if extended_location:
            result["extendedLocation"] = extended_location

        if check_cluster_connectivity:
            self.check_cluster_connectivity(
                result.get("extendedLocation", {}).get("name")
            )
        return result

    def check_cluster_connectivity(
        self,
        custom_location_id: Optional[str],
    ):
        if not custom_location_id:
            logger.warning(NO_EXTENDED_LOCATION_TO_CHECK_MSG)
            return
        query = f'| where id =~ "{custom_location_id}"'
        custom_location_query_result = build_query(
            self.cmd,
            custom_query=query,
            type=ResourceTypeMapping.custom_location.value
        )
        if not custom_location_query_result:
            logger.warning(CUSTOM_LOCATION_NOT_FOUND_MSG.format(custom_location_id))
            return
        query = f'| where id =~ "{custom_location_query_result[0]["properties"]["hostResourceId"]}"'
        cluster_query_result = build_query(
            self.cmd,
            custom_query=query,
            type=ResourceTypeMapping.connected_cluster.value
        )
        # TODO: add option to fail on these
        if not cluster_query_result:
            logger.warning(CLUSTER_NOT_FOUND_MSG.format(custom_location_id))
            return
        cluster = cluster_query_result[0]
        if cluster["properties"]["connectivityStatus"].lower() != "connected":
            logger.warning(CLUSTER_OFFLINE_MSG.format(cluster["name"]))

    def check_cluster_and_custom_location(
        self,
        custom_location_name: Optional[str] = None,
        custom_location_resource_group: Optional[str] = None,
        custom_location_subscription: Optional[str] = None,
        cluster_name: Optional[str] = None,
        cluster_resource_group: Optional[str] = None,
        cluster_subscription: Optional[str] = None,
    ) -> Dict[str, str]:
        if not any([cluster_name, custom_location_name]):
            raise RequiredArgumentMissingError(MISSING_CLUSTER_CUSTOM_LOCATION_ERROR)
        query = ""
        cluster = None

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
                    MULTIPLE_POSSIBLE_ITEMS_ERROR.format(len(cluster_query_result), "cluster", cluster_name)
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
                MULTIPLE_POSSIBLE_ITEMS_ERROR.format(
                    len(location_query_result),
                    "custom location",
                    custom_location_name
                )
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
                raise ValidationError(CUSTOM_LOCATION_DOES_NOT_EXIST_ERROR.format(custom_location_name))
            cluster = cluster_query_result[0]
        # by this point, cluster is populated

        if cluster["properties"]["connectivityStatus"].lower() != "connected":
            logger.warning(CLUSTER_OFFLINE_MSG.format(cluster["name"]))

        possible_locations = []
        for location in location_query_result:
            usable = False
            for extension_id in location["properties"]["clusterExtensionIds"]:
                # extensions not findable in graph :(
                extension = self.resource_client.resources.get_by_id(
                    resource_id=extension_id,
                    api_version=EXTENSION_API_VERSION,
                ).as_dict()
                if extension["properties"]["extensionType"] == self.required_extension:
                    usable = True
                    break
            if usable:
                possible_locations.append(location["id"])

        # throw if there are no suitable extensions (in the cluster)
        if len(possible_locations) == 0:
            raise ValidationError(MISSING_EXTENSION_ERROR.format(cluster["name"], self.required_extension))
        # throw if multiple custom locations (cluster name given, multiple locations possible)
        if len(possible_locations) > 1:
            possible_locations = "\n".join(possible_locations)
            raise ValidationError(MULTIPLE_CUSTOM_LOCATIONS_ERROR.format(cluster['id'], possible_locations))

        extended_location = {
            "type": "CustomLocation",
            "name": possible_locations[0]
        }

        return extended_location
