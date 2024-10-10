# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import os
from typing import TYPE_CHECKING, Iterable, List, Optional

from azure.cli.core.azclierror import ValidationError
from azure.core.paging import PageIterator
from azure.core.exceptions import ResourceNotFoundError
from azure.keyvault.secrets import SecretClient
from knack.log import get_logger
from rich.console import Console
import yaml

from azext_edge.edge.providers.orchestration.common import CUSTOM_LOCATIONS_API_VERSION
from azext_edge.edge.providers.orchestration.resources.instances import Instances
from build.lib.azext_edge.edge.util.az_client import get_iotops_mgmt_client, parse_resource_id

from ......util.az_client import (
    get_keyvault_client,
    get_ssc_mgmt_client,
)
from ......util.common import should_continue_prompt
from ......util.queryable import Queryable
from ....permissions import PermissionManager, ROLE_DEF_FORMAT_STR

logger = get_logger(__name__)

console = Console()


if TYPE_CHECKING:
    from ......vendor.clients.keyvaultmgmt.operations import KeyVaultClientOperationsMixin


class OPCUACERTS(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        # self.keyvault_client = get_keyvault_client(
        #     subscription_id=self.default_subscription_id,
        #     keyvault_name=keyvault_name,
        # )
        self.iotops_mgmt_client = get_iotops_mgmt_client(
            subscription_id=self.default_subscription_id,
        )
        self.instances = Instances(self.cmd)
        self.ssc_mgmt_client = get_ssc_mgmt_client(
            subscription_id=self.default_subscription_id,
        )

    def add(self, instance_name: str, resource_group: str, file: str, secret_name: Optional[str] = None) -> dict:
        self.instance = self.instances.show(name=instance_name, resource_group_name=resource_group)
        self.resource_map = self.instances.get_resource_map(self.instance)
        custom_location = self.resource_client.resources.get_by_id(
            resource_id=self.instance["extendedLocation"]["name"], api_version=CUSTOM_LOCATIONS_API_VERSION
        )

        cl_resources = self.resource_map.connected_cluster.get_aio_resources(custom_location_id=custom_location["id"])
        secretsync_spc = self._find_existing_spc(cl_resources)
        if not secretsync_spc:
            # status.stop()
            logger.error(
                f"Secret sync is not enabled for the instance {instance_name}. Please enable secret sync before adding a trusted certificate."
            )
            return

        # get properties from default spc
        spc_properties = secretsync_spc.get("properties", {})
        spc_client_id = spc_properties.get("clientId", "")
        spc_tenant_id = spc_properties.get("tenantId", "")
        spc_keyvault_name = spc_properties.get("keyvaultName", "")

        self.keyvault_client = get_keyvault_client(
            subscription_id=self.subscriptions[0],
            keyvault_name=spc_keyvault_name,
        )

        secrets: PageIterator = self.keyvault_client.list_properties_of_secrets()

        # get file extension
        file_name = os.path.basename(file)
        cert_extension = file_name.split(".")[-1]
        # get cert name by removing extension and path in front
        cert_name = file_name.split(".")[0].replace(".", "")

        if cert_extension not in ["der", "crt"]:
            raise ValidationError("Only .der and .crt files are supported.")

        secret_name = secret_name if secret_name else f"{cert_name}-{cert_extension}"

        # iterate over secrets to check if secret with same name exists
        # secrets.next() will return next page of secrets
        for secret in secrets:
            if secret.id.endswith(secret_name):
                # TODO: prompt user to overwrite existing secret
                should_continue_prompt
                import pdb

                pdb.set_trace()
                logger.error(f"Secret with name {secret_name} already exists in keyvault {spc_keyvault_name}.")
                return

        content_type = "application/pkix-cert" if cert_extension == "der" else "application/x-pem-file"

        # load hex encoded file content
        # TODO: change file name to indicates it's the content
        with open(file, "rb") as f:
            file = f.read().hex()
        secret = self.keyvault_client.set_secret(
            name=secret_name,
            value=file,
            content_type=content_type,
            tags={"file-encoding": "hex"},
        )

        # check if there is a spc called "opc-ua-connector", if not create one
        try:
            opcua_spc = self.ssc_mgmt_client.azure_key_vault_secret_provider_classes.get(
                resource_group_name=resource_group,
                azure_key_vault_secret_provider_class_name="opc-ua-connector",
            )
        except ResourceNotFoundError:
            opcua_spc = {}

        opcua_spc_properties = opcua_spc.get("properties", {})
        # stringified yaml array
        spc_object = opcua_spc_properties.get("objects", "")

        # convert yaml array to dict
        spc_object_dict = yaml.safe_load(spc_object)
        # add new secret to the list
        secret_entry = {
            "objectName": secret_name,
            "objectType": "secret",
            "objectEncoding": "hex",
        }

        if not spc_object_dict:
            spc_object_dict = {"array": []}
        spc_object_dict["array"].append(secret_entry)
        # convert dict back to yaml array
        spc_object = yaml.dump(spc_object_dict, indent=4, default_flow_style=False)

        if not opcua_spc:
            # create a new spc
            # get role definition id
            # role_def_id = self._get_role_def_id(resource_group)
            opcua_spc = {
                "location": self.instance["location"],
                "extendedLocation": self.instance["extendedLocation"],
                "properties": {
                    "clientId": spc_client_id,  # The client ID of the service principal
                    "keyvaultName": spc_keyvault_name,
                    "tenantId": spc_tenant_id,
                    "objects": spc_object,
                },
            }
            # opcua_spc_resource["clientId"] = spc_client_id
            # opcua_spc_resource["tenantId"] = spc_tenant_id
            # opcua_spc_resource["keyvaultName"] = spc_keyvault_name
            # opcua_spc_resource["objects"] = spc_object
            # create a new spc
        else:
            opcua_spc["properties"]["objects"] = spc_object

        self.ssc_mgmt_client.azure_key_vault_secret_provider_classes.begin_create_or_update(
            resource_group_name=resource_group,
            azure_key_vault_secret_provider_class_name="opc-ua-connector",
            resource=opcua_spc,
        )

        # check if there is a secret sync called "aio-opc-ua-broker-trust-list ", if not create one
        try:
            opcua_secret_sync = self.ssc_mgmt_client.secret_syncs.get(
                resource_group_name=resource_group,
                secret_sync_name="aio-opc-ua-broker-trust-list",
            )
        except ResourceNotFoundError:
            opcua_secret_sync = {}

        secret_mapping = opcua_secret_sync.get("properties", {}).get("objectSecretMapping", [])
        # add new secret to the list
        secret_mapping.append(
            {
                "sourcePath": secret_name,
                "targetKey": file_name,
            }
        )

        # find duplicate targetKey
        target_keys = [mapping["targetKey"] for mapping in secret_mapping]
        if len(target_keys) != len(set(target_keys)):
            logger.error("Cannot have duplicate targetKey in objectSecretMapping.")
            return

        if not opcua_secret_sync:
            opcua_secret_sync = {
                "location": self.instance["location"],
                "extendedLocation": self.instance["extendedLocation"],
                "properties": {
                    "kubernetesSecretType": "Opaque",
                    "secretProviderClassName": "opc-ua-connector",
                    "serviceAccountName": "aio-ssa-sa",
                    "objectSecretMapping": secret_mapping,
                },
            }
        else:
            opcua_secret_sync["properties"]["objectSecretMapping"] = secret_mapping

        # create a new secret sync
        self.ssc_mgmt_client.secret_syncs.begin_create_or_update(
            resource_group_name=resource_group,
            secret_sync_name="aio-opc-ua-broker-trust-list",
            resource=opcua_secret_sync,
        )

        return secret

    def _find_existing_spc(self, cl_resources: List[dict]) -> Optional[dict]:
        for resource in cl_resources:
            if resource["type"].lower() == "microsoft.secretsynccontroller/azurekeyvaultsecretproviderclasses":
                resource_id_container = parse_resource_id(resource["id"])
                return self.ssc_mgmt_client.azure_key_vault_secret_provider_classes.get(
                    resource_group_name=resource_id_container.resource_group_name,
                    azure_key_vault_secret_provider_class_name=resource_id_container.resource_name,
                )
