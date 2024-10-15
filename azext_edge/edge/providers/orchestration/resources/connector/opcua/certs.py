# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import os
from typing import List, Optional

from azure.core.paging import PageIterator
from azure.core.exceptions import ResourceNotFoundError
from knack.log import get_logger
from rich.console import Console
import yaml

from azext_edge.edge.providers.orchestration.common import CUSTOM_LOCATIONS_API_VERSION
from azext_edge.edge.providers.orchestration.resources.instances import Instances
from azext_edge.edge.util.file_operations import validate_file_extension
from azext_edge.edge.util.queryable import Queryable
from azext_edge.edge.util.az_client import (
    parse_resource_id,
    get_keyvault_client,
    get_ssc_mgmt_client,
    wait_for_terminal_state,
)

logger = get_logger(__name__)

console = Console()

OPCUA_SPC_NAME = "opc-ua-connector"
OPCUA_TRUST_LIST_SECRET_SYNC_NAME = "aio-opc-ua-broker-trust-list"
OPCUA_ISSUER_LIST_SECRET_SYNC_NAME = "aio-opc-ua-broker-issuer-list"
SERVICE_ACCOUNT_NAME = "aio-ssc-sa"


class OpcUACerts(Queryable):

    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.instances = Instances(self.cmd)
        self.ssc_mgmt_client = get_ssc_mgmt_client(
            subscription_id=self.default_subscription_id,
        )

    def trust_add(self, instance_name: str, resource_group: str, file: str, secret_name: Optional[str] = None) -> dict:
        cl_resources = self._get_cl_resources(instance_name=instance_name, resource_group=resource_group)
        secretsync_spc = self._find_existing_spc(instance_name=instance_name, cl_resources=cl_resources)
        if not secretsync_spc:
            return

        # get properties from default spc
        spc_properties = secretsync_spc.get("properties", {})
        spc_keyvault_name = spc_properties.get("keyvaultName", "")

        self.keyvault_client = get_keyvault_client(
            subscription_id=self.default_subscription_id,
            keyvault_name=spc_keyvault_name,
        )

        secrets: PageIterator = self.keyvault_client.list_properties_of_secrets()

        # get file extension
        file_name = os.path.basename(file)
        # get cert name by removing extension and path in front
        cert_name = file_name.split(".")[0].replace(".", "")
        cert_extension = validate_file_extension(file_name, ["der", "crt"])

        secret_name = secret_name if secret_name else f"{cert_name}-{cert_extension}"

        # iterate over secrets to check if secret with same name exists
        secret_name = self._check_and_update_secret_name(secrets, secret_name, spc_keyvault_name)
        self._upload_to_key_vault(secret_name, file, cert_extension)

        # check if there is a spc called "opc-ua-connector", if not create one
        try:
            opcua_spc = self.ssc_mgmt_client.azure_key_vault_secret_provider_classes.get(
                resource_group_name=resource_group,
                azure_key_vault_secret_provider_class_name=OPCUA_SPC_NAME,
            )
        except ResourceNotFoundError:
            opcua_spc = {}

        self._add_secret_to_spc(
            secret_name=secret_name,
            spc=opcua_spc,
            resource_group=resource_group,
            spc_keyvault_name=spc_keyvault_name,
        )

        # check if there is a secret sync called "aio-opc-ua-broker-trust-list ", if not create one
        try:
            opcua_secret_sync = self.ssc_mgmt_client.secret_syncs.get(
                resource_group_name=resource_group,
                secret_sync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
            )
        except ResourceNotFoundError:
            opcua_secret_sync = {}

        return self._add_secret_to_secret_sync(
            secret_name=secret_name,
            file_name=file_name,
            secret_sync=opcua_secret_sync,
            resource_group=resource_group,
            spc_name=OPCUA_SPC_NAME,
            secret_sync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
        )

    def issuer_add(
        self, instance_name: str, resource_group: str, file: str, secret_name: Optional[str] = None
    ) -> dict:
        cl_resources = self._get_cl_resources(instance_name=instance_name, resource_group=resource_group)
        secretsync_spc = self._find_existing_spc(instance_name=instance_name, cl_resources=cl_resources)
        if not secretsync_spc:
            return

        # get properties from default spc
        spc_properties = secretsync_spc.get("properties", {})
        spc_keyvault_name = spc_properties.get("keyvaultName", "")

        self.keyvault_client = get_keyvault_client(
            subscription_id=self.default_subscription_id,
            keyvault_name=spc_keyvault_name,
        )

        secrets: PageIterator = self.keyvault_client.list_properties_of_secrets()

        # get file extension
        file_name = os.path.basename(file)
        # get cert name by removing extension and path in front
        cert_name = file_name.split(".")[0].replace(".", "")

        cert_extension = validate_file_extension(file_name, ["der", "crt", "crl"])

        try:
            opcua_secret_sync = self.ssc_mgmt_client.secret_syncs.get(
                resource_group_name=resource_group,
                secret_sync_name=OPCUA_ISSUER_LIST_SECRET_SYNC_NAME,
            )
        except ResourceNotFoundError:
            opcua_secret_sync = {}

        if cert_extension == "crl":
            # TODO: add check that same name should exist for crt and der
            secret_mapping = opcua_secret_sync.get("properties", {}).get("objectSecretMapping", [])
            possible_file_name = [f"{cert_name}.crt", f"{cert_name}.der"]
            found_file_name = [
                mapping["targetKey"] for mapping in secret_mapping if mapping["targetKey"] in possible_file_name
            ]

            if not found_file_name:
                logger.error(f"Cannot add .crl {file_name} without corresponding .crt or .der file.")
                return

        secret_name = secret_name if secret_name else f"{cert_name}-{cert_extension}"

        # iterate over secrets to check if secret with same name exists
        secret_name = self._check_and_update_secret_name(secrets, secret_name, spc_keyvault_name)
        self._upload_to_key_vault(secret_name, file, cert_extension)

        # check if there is a spc called "opc-ua-connector", if not create one
        try:
            opcua_spc = self.ssc_mgmt_client.azure_key_vault_secret_provider_classes.get(
                resource_group_name=resource_group,
                azure_key_vault_secret_provider_class_name=OPCUA_SPC_NAME,
            )
        except ResourceNotFoundError:
            opcua_spc = {}

        self._add_secret_to_spc(
            secret_name=secret_name,
            spc=opcua_spc,
            resource_group=resource_group,
            spc_keyvault_name=spc_keyvault_name,
        )

        return self._add_secret_to_secret_sync(
            secret_name=secret_name,
            file_name=file_name,
            secret_sync=opcua_secret_sync,
            resource_group=resource_group,
            spc_name=OPCUA_SPC_NAME,
            secret_sync_name=OPCUA_ISSUER_LIST_SECRET_SYNC_NAME,
        )

    def _process_fortos_yaml(self, object_text: str, secret_entry: Optional[dict] = None) -> str:
        if object_text:
            # TODO: formatting will be removed once fortos service fixes the formatting issue
            object_text.replace("\n    - |", "\n- |")
            objects_obj = yaml.safe_load(object_text)
        else:
            objects_obj = {"array": []}
        entry_text = yaml.safe_dump(secret_entry, indent=6)
        objects_obj["array"].append(entry_text)
        object_text = yaml.safe_dump(objects_obj, indent=6)
        return object_text.replace("\n- |", "\n    - |")

    def _get_cl_resources(self, instance_name: str, resource_group: str) -> dict:
        self.instance = self.instances.show(name=instance_name, resource_group_name=resource_group)
        self.resource_map = self.instances.get_resource_map(self.instance)
        custom_location = self.resource_client.resources.get_by_id(
            resource_id=self.instance["extendedLocation"]["name"], api_version=CUSTOM_LOCATIONS_API_VERSION
        )
        cl_resources = self.resource_map.connected_cluster.get_aio_resources(custom_location_id=custom_location["id"])
        return cl_resources

    def _find_existing_spc(self, instance_name: str, cl_resources: List[dict]) -> dict:
        secretsync_spc = None

        if cl_resources:
            for resource in cl_resources:
                if resource["type"].lower() == "microsoft.secretsynccontroller/azurekeyvaultsecretproviderclasses":
                    resource_id_container = parse_resource_id(resource["id"])
                    secretsync_spc = self.ssc_mgmt_client.azure_key_vault_secret_provider_classes.get(
                        resource_group_name=resource_id_container.resource_group_name,
                        azure_key_vault_secret_provider_class_name=resource_id_container.resource_name,
                    )
                    break

        if not secretsync_spc:
            logger.error(
                f"Secret sync is not enabled for the instance {instance_name}. "
                "Please enable secret sync before adding a trusted certificate."
            )
            return

        return secretsync_spc

    def _check_and_update_secret_name(self, secrets: PageIterator, secret_name: str, spc_keyvault_name: str) -> str:
        from rich.prompt import Confirm, Prompt

        new_secret_name = secret_name
        for secret in secrets:
            if secret.id.endswith(secret_name):
                # Prompt user to decide on overwriting the secret
                should_bail = not Confirm.ask(
                    f"Secret with name {secret_name} already exists in keyvault {spc_keyvault_name}. "
                    "Do you want to overwrite the secret name?",
                )

                if should_bail:
                    return new_secret_name

                return Prompt.ask("Please enter the new secret name")

        return new_secret_name

    def _upload_to_key_vault(self, secret_name: str, file_path: str, cert_extension: str):
        with console.status(f"Uploading certificate to keyvault as secret {secret_name}..."), open(
            file_path, "rb"
        ) as read_file:
            if cert_extension == "crl":
                content_type = "application/pkix-crl"
            elif cert_extension == "der":
                content_type = "application/pkix-cert"
            else:
                content_type = "application/x-pem-file"

            content = read_file.read().hex()
            return self.keyvault_client.set_secret(
                name=secret_name, value=content, content_type=content_type, tags={"file-encoding": "hex"}
            )

    def _add_secret_to_spc(
        self,
        secret_name: str,
        spc: dict,
        resource_group: str,
        spc_keyvault_name: str,
    ) -> dict:
        spc_properties = spc.get("properties", {})
        # stringified yaml array
        spc_object = spc_properties.get("objects", "")

        # add new secret to the list
        secret_entry = {
            "objectName": secret_name,
            "objectType": "secret",
            "objectEncoding": "hex",
        }

        spc_object = self._process_fortos_yaml(object_text=spc_object, secret_entry=secret_entry)

        if not spc:
            logger.warning(f"Azure Key Vault Secret Provider Class {OPCUA_SPC_NAME} not found, creating new one...")
            spc_client_id = spc_properties.get("clientId", "")
            spc_tenant_id = spc_properties.get("tenantId", "")
            spc = {
                "location": self.instance["location"],
                "extendedLocation": self.instance["extendedLocation"],
                "properties": {
                    "clientId": spc_client_id,  # The client ID of the service principal
                    "keyvaultName": spc_keyvault_name,
                    "tenantId": spc_tenant_id,
                    "objects": spc_object,
                },
            }
        else:
            spc["properties"]["objects"] = spc_object

        with console.status(f"Updating secret reference in Secret Provider Class {OPCUA_SPC_NAME}..."):
            poller = self.ssc_mgmt_client.azure_key_vault_secret_provider_classes.begin_create_or_update(
                resource_group_name=resource_group,
                azure_key_vault_secret_provider_class_name=OPCUA_SPC_NAME,
                resource=spc,
            )
            wait_for_terminal_state(poller)

    def _add_secret_to_secret_sync(
        self,
        secret_name: str,
        file_name: str,
        secret_sync: dict,
        resource_group: str,
        spc_name: str,
        secret_sync_name: str,
    ) -> dict:
        # check if there is a secret sync called secret_sync_name, if not create one
        secret_mapping = secret_sync.get("properties", {}).get("objectSecretMapping", [])
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

        if not secret_sync:
            logger.warning(f"Secret Sync {secret_sync_name} not found, creating new one...")
            secret_sync = {
                "location": self.instance["location"],
                "extendedLocation": self.instance["extendedLocation"],
                "properties": {
                    "kubernetesSecretType": "Opaque",
                    "secretProviderClassName": spc_name,
                    "serviceAccountName": SERVICE_ACCOUNT_NAME,
                    "objectSecretMapping": secret_mapping,
                },
            }
        else:
            secret_sync["properties"]["objectSecretMapping"] = secret_mapping

        # create a new secret sync
        with console.status("Updating Secret Sync..."):
            poller = self.ssc_mgmt_client.secret_syncs.begin_create_or_update(
                resource_group_name=resource_group,
                secret_sync_name=secret_sync_name,
                resource=secret_sync,
            )
            return wait_for_terminal_state(poller)
