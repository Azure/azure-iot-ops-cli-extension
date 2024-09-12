# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy
from typing import Iterable, List, Optional

from azure.cli.core.azclierror import ValidationError
from knack.log import get_logger
from rich import print
from rich.console import Console

from ....util.az_client import (
    get_iotops_mgmt_client,
    get_msi_mgmt_client,
    parse_resource_id,
    wait_for_terminal_state,
    ResourceIdContainer,
)
from ....util.queryable import Queryable
from ..common import CUSTOM_LOCATIONS_API_VERSION
from ..resource_map import IoTOperationsResourceMap

logger = get_logger(__name__)

console = Console()


class Instances(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.iotops_mgmt_client = get_iotops_mgmt_client(
            subscription_id=self.default_subscription_id,
        )
        self.msi_mgmt_client = get_msi_mgmt_client(
            subscription_id=self.default_subscription_id,
        )

    def show(self, name: str, resource_group_name: str, show_tree: Optional[bool] = None) -> Optional[dict]:
        result = self.iotops_mgmt_client.instance.get(instance_name=name, resource_group_name=resource_group_name)

        if show_tree:
            self._show_tree(result)
            return

        return result

    def list(self, resource_group_name: Optional[str] = None) -> Iterable[dict]:
        if resource_group_name:
            return self.iotops_mgmt_client.instance.list_by_resource_group(resource_group_name=resource_group_name)

        return self.iotops_mgmt_client.instance.list_by_subscription()

    def _show_tree(self, instance: dict):
        resource_map = self.get_resource_map(instance)
        with console.status("Working..."):
            resource_map.refresh_resource_state()
        print(resource_map.build_tree(category_color="cyan"))

    def _get_associated_cl(self, instance: dict) -> dict:
        return self.resource_client.resources.get_by_id(
            resource_id=instance["extendedLocation"]["name"], api_version=CUSTOM_LOCATIONS_API_VERSION
        )

    def get_resource_map(self, instance: dict) -> IoTOperationsResourceMap:
        custom_location = self._get_associated_cl(instance)
        resource_id_container = parse_resource_id(custom_location["properties"]["hostResourceId"])

        return IoTOperationsResourceMap(
            cmd=self.cmd,
            cluster_name=resource_id_container.resource_name,
            resource_group_name=resource_id_container.resource_group_name,
            defer_refresh=True,
        )

    def update(
        self,
        name: str,
        resource_group_name: str,
        tags: Optional[dict] = None,
        description: Optional[str] = None,
        **kwargs: dict,
    ) -> dict:
        instance = kwargs.pop("instance", None) or self.show(name=name, resource_group_name=resource_group_name)

        if description:
            instance["properties"]["description"] = description

        if tags or tags == {}:
            instance["tags"] = tags

        with console.status("Working..."):
            poller = self.iotops_mgmt_client.instance.begin_create_or_update(
                instance_name=name,
                resource_group_name=resource_group_name,
                resource=instance,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def remove_mi_user_assigned(self, name: str, resource_group_name: str, mi_user_assigned: str):
        mi_resource_id_container = parse_resource_id(mi_user_assigned)
        instance = self.show(name=name, resource_group_name=resource_group_name)
        identity = instance.get("identity", {})
        if not identity:
            raise ValidationError("No identities are associated with the instance.")

        if mi_user_assigned not in identity["userAssignedIdentities"]:
            raise ValidationError("The identity is not associated with the instance.")

        del identity["userAssignedIdentities"][mi_user_assigned]

        # Check if we deleted them all.
        if not identity["userAssignedIdentities"]:
            identity["type"] = "None"

        instance["identity"] = identity
        updated_instance = self.update(name=name, resource_group_name=resource_group_name, instance=instance)
        self.unfederate_msi(mi_resource_id_container)
        return updated_instance

    def add_mi_user_assigned(self, name: str, resource_group_name: str, mi_user_assigned: str):
        """
        Responsible for federating and building the instance identity object.
        """
        mi_resource_id_container = parse_resource_id(mi_user_assigned)
        instance = self.show(name=name, resource_group_name=resource_group_name)
        cluster_resource = self.get_resource_map(instance).connected_cluster.resource
        if "oidcIssuerProfile" not in cluster_resource["properties"] or not cluster_resource["properties"][
            "oidcIssuerProfile"
        ].get("enabled"):
            raise ValidationError(
                f"The cluster '{cluster_resource['name']}' is not enabled as an oidc issuer.\n"
                "Please enable via 'az connectedk8s connect --enable-oidc-issuer'."
            )
        self.federate_msi(mi_resource_id_container, cluster_resource["properties"]["oidcIssuerProfile"]["issuerUrl"])

        identity: dict = instance.get("identity", {})
        if not identity or identity.get("type") == "None":
            identity["type"] = "UserAssigned"
            identity["userAssignedIdentities"] = {}
        identity["userAssignedIdentities"][mi_user_assigned] = {}

        instance["identity"] = identity
        return self.update(name=name, resource_group_name=resource_group_name, instance=instance)

    def federate_msi(
        self,
        mi_resource_id_container: ResourceIdContainer,
        oidc_issuer: str,
        namespace: str = "azure-iot-operations",
        service_account_name: str = "aio-dataflow",
    ):
        self.msi_mgmt_client.federated_identity_credentials.create_or_update(
            resource_group_name=mi_resource_id_container.resource_group_name,
            resource_name=mi_resource_id_container.resource_name,
            federated_identity_credential_resource_name=mi_resource_id_container.resource_name,
            parameters={
                "properties": {
                    "subject": f"system:serviceaccount:{namespace}:{service_account_name}",
                    "audiences": ["api://AzureADTokenExchange"],
                    "issuer": oidc_issuer,
                }
            },
        )

    def unfederate_msi(
        self,
        mi_resource_id_container: ResourceIdContainer,
    ):
        self.msi_mgmt_client.federated_identity_credentials.delete(
            resource_group_name=mi_resource_id_container.resource_group_name,
            resource_name=mi_resource_id_container.resource_name,
            federated_identity_credential_resource_name=mi_resource_id_container.resource_name,
        )
