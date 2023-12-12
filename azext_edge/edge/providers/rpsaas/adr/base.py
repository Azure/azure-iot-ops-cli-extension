# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict, Optional
from knack.log import get_logger
from azure.cli.core.azclierror import (
    ResourceNotFoundError,
    RequiredArgumentMissingError,
    ValidationError
)

from .constants import (
    CUSTOM_LOCATION_DOES_NOT_EXIST_ERROR,
    CUSTOM_LOCATION_NOT_FOUND_ERROR,
    CLUSTER_NOT_FOUND_ERROR,
    CLUSTER_OFFLINE,
    MISSING_CLUSTER_CUSTOM_LOCATION_ERROR,
    MISSING_EXTENSION_ERROR,
    MULTIPLE_CUSTOM_LOCATIONS_ERROR,
    MULTIPLE_POSSIBLE_ITEMS_ERROR
)
from ..base_provider import RPSaaSBaseProvider
from ....util import build_query
from ....common import ResourceTypeMapping

logger = get_logger(__name__)
API_VERSION = "2023-11-01-preview"


# @vilit - prob generalize this even more
class ADRBaseProvider(RPSaaSBaseProvider):
    def __init__(
        self, cmd, resource_type: str
    ):
        super(ADRBaseProvider, self).__init__(
            cmd=cmd,
            api_version=API_VERSION,
            resource_type=resource_type,
            required_extension="microsoft.deviceregistry.assets"
        )

    def delete(
        self,
        resource_name: str,
        resource_group_name: str
    ):
        self.show_and_check(
            resource_name=resource_name,
            resource_group_name=resource_group_name
        )
        return self.resource_client.resources.begin_delete(
            resource_group_name=resource_group_name,
            resource_provider_namespace=self.resource_type,
            parent_resource_path="",
            resource_type="",
            resource_name=resource_name,
            api_version=self.api_version
        )

    def show_and_check(
        self,
        resource_name: str,
        resource_group_name: str
    ) -> Dict[str, Any]:
        result = self.show(resource_name, resource_group_name)
        self._check_cluster_connectivity(
            result["extendedLocation"]["name"]
        )
        return result

    def _check_cluster_connectivity(
        self,
        custom_location_id: str,
    ):
        query = f'| where id =~ "{custom_location_id}"'
        custom_location_query_result = build_query(
            self.cmd,
            custom_query=query,
            type=ResourceTypeMapping.custom_location.value
        )
        if len(custom_location_query_result) == 0:
            logger.warning(CUSTOM_LOCATION_NOT_FOUND_ERROR.format(custom_location_id))
            return
        query = f'| where id =~ "{custom_location_query_result[0]["properties"]["hostResourceId"]}"'
        cluster_query_result = build_query(
            self.cmd,
            custom_query=query,
            type=ResourceTypeMapping.connected_cluster.value
        )
        # TODO: add option to fail on these
        if len(cluster_query_result) == 0:
            logger.warning(CLUSTER_NOT_FOUND_ERROR.format(custom_location_id))
            return
        cluster = cluster_query_result[0]
        if cluster["properties"]["connectivityStatus"].lower() != "connected":
            logger.warning(CLUSTER_OFFLINE.format(cluster["name"]))

    def _check_cluster_and_custom_location(
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
            logger.warning(CLUSTER_OFFLINE.format(cluster["name"]))

        possible_locations = []
        for location in location_query_result:
            usable = False
            for extension_id in location["properties"]["clusterExtensionIds"]:
                # extensions not findable in graph :(
                extension = self.resource_client.resources.get_by_id(
                    resource_id=extension_id,
                    api_version="2023-05-01",
                ).as_dict()
                if extension["properties"]["extensionType"] == self.required_extension:
                    usable = True
                    break
            if usable:
                possible_locations.append(location["id"])

        # throw if there are no suitable extensions (in the cluster)
        if len(possible_locations) == 0:
            raise ValidationError(MISSING_EXTENSION_ERROR.format(cluster["name"], self.required_extension))
        # here we warn about multiple custom locations (cluster name given, multiple locations possible)
        if len(possible_locations) > 1:
            possible_locations = "\n".join(possible_locations)
            raise ValidationError(MULTIPLE_CUSTOM_LOCATIONS_ERROR.format(cluster['id'], possible_locations))

        extended_location = {
            "type": "CustomLocation",
            "name": possible_locations[0]
        }

        return extended_location
