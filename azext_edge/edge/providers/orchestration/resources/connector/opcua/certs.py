# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import os
from typing import List, Optional, Tuple

from azure.core.paging import PageIterator
from azure.core.exceptions import ResourceNotFoundError
from azure.cli.core.azclierror import InvalidArgumentValueError
from knack.log import get_logger
from rich.console import Console
import yaml

from azext_edge.edge.util.common import should_continue_prompt

from ....common import CUSTOM_LOCATIONS_API_VERSION
from ...instances import SECRET_SYNC_RESOURCE_TYPE, SPC_RESOURCE_TYPE, Instances
from ....work import IOT_OPS_EXTENSION_TYPE
from ......util.file_operations import read_file_content, validate_file_extension
from ......util.queryable import Queryable
from ......util.az_client import (
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
OPCUA_CLIENT_CERT_SECRET_SYNC_NAME = "aio-opc-ua-broker-client-certificate"
DEFAULT_SELF_SIGNED_CERT_NAME = "aio-opc-opcuabroker-default-application-cert"
SERVICE_ACCOUNT_NAME = "aio-ssc-sa"


class OpcUACerts(Queryable):

    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.instances = Instances(self.cmd)
        self.ssc_mgmt_client = get_ssc_mgmt_client(
            subscription_id=self.default_subscription_id,
        )

    def trust_add(
        self,
        instance_name: str,
        resource_group: str,
        file: str,
        secret_name: Optional[str] = None,
        overwrite_secret: Optional[bool] = False,
    ) -> dict:
        cl_resources = self._get_cl_resources(instance_name=instance_name, resource_group=resource_group)
        secretsync_spc = self._find_existing_spc(instance_name=instance_name, cl_resources=cl_resources)

        # get file extension
        file_name = os.path.basename(file)
        # get cert name by removing extension and path in front
        cert_extension = validate_file_extension(file_name, [".der", ".crt"])

        # get properties from default spc
        spc_properties = secretsync_spc.get("properties", {})
        spc_keyvault_name = spc_properties.get("keyvaultName", "")
        spc_tenant_id = spc_properties.get("tenantId", "")
        spc_client_id = spc_properties.get("clientId", "")

        self.keyvault_client = get_keyvault_client(
            subscription_id=self.default_subscription_id,
            keyvault_name=spc_keyvault_name,
        )

        secrets: PageIterator = self.keyvault_client.list_properties_of_secrets()

        secret_name = secret_name if secret_name else file_name.replace(".", "-")

        # iterate over secrets to check if secret with same name exists
        secret_name = self._check_secret_name(
            secrets=secrets,
            secret_name=secret_name,
            spc_keyvault_name=spc_keyvault_name,
            flag="secret-name",
            overwrite_secret=overwrite_secret,
        )

        if not secret_name:
            return

        self._upload_to_key_vault(secret_name, file, cert_extension)

        # check if there is a spc called "opc-ua-connector", if not create one
        opcua_spc = self.instances.find_existing_resources(
            cl_resources=cl_resources,
            resource_type=SPC_RESOURCE_TYPE,
            resource_name=OPCUA_SPC_NAME,
        )

        self._add_secrets_to_spc(
            secrets=[secret_name],
            spc=opcua_spc,
            resource_group=resource_group,
            spc_keyvault_name=spc_keyvault_name,
            spc_tenant_id=spc_tenant_id,
            spc_client_id=spc_client_id,
        )

        # check if there is a secret sync called "aio-opc-ua-broker-trust-list ", if not create one
        opcua_secret_sync = self.instances.find_existing_resources(
            cl_resources=cl_resources,
            resource_type=SECRET_SYNC_RESOURCE_TYPE,
            resource_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
        )

        return self._add_secrets_to_secret_sync(
            secrets=[(secret_name, file_name)],
            secret_sync=opcua_secret_sync,
            resource_group=resource_group,
            spc_name=OPCUA_SPC_NAME,
            secret_sync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
        )

    def issuer_add(
        self,
        instance_name: str,
        resource_group: str,
        file: str,
        secret_name: Optional[str] = None,
        overwrite_secret: Optional[bool] = False,
    ) -> dict:
        cl_resources = self._get_cl_resources(instance_name=instance_name, resource_group=resource_group)
        secretsync_spc = self._find_existing_spc(instance_name=instance_name, cl_resources=cl_resources)

        # get file extension
        file_name = os.path.basename(file)
        cert_extension = validate_file_extension(file_name, [".der", ".crt", ".crl"])

        # get properties from default spc
        spc_properties = secretsync_spc.get("properties", {})
        spc_keyvault_name = spc_properties.get("keyvaultName", "")
        spc_tenant_id = spc_properties.get("tenantId", "")
        spc_client_id = spc_properties.get("clientId", "")

        self.keyvault_client = get_keyvault_client(
            subscription_id=self.default_subscription_id,
            keyvault_name=spc_keyvault_name,
        )

        secrets: PageIterator = self.keyvault_client.list_properties_of_secrets()

        # get cert name by removing extension
        cert_name = os.path.splitext(file_name)[0]

        opcua_secret_sync = self.instances.find_existing_resources(
            cl_resources=cl_resources,
            resource_type=SECRET_SYNC_RESOURCE_TYPE,
            resource_name=OPCUA_ISSUER_LIST_SECRET_SYNC_NAME,
        )

        if cert_extension == ".crl":
            matched_names = []
            if opcua_secret_sync:
                secret_mapping = opcua_secret_sync.get("properties", {}).get("objectSecretMapping", [])
                possible_file_names = [f"{cert_name}.crt", f"{cert_name}.der"]
                matched_names = [
                    mapping["targetKey"] for mapping in secret_mapping if mapping["targetKey"] in possible_file_names
                ]

            if not opcua_secret_sync or not matched_names:
                raise InvalidArgumentValueError(
                    f"Cannot add .crl {file_name} without corresponding .crt or .der file."
                )

        secret_name = secret_name if secret_name else file_name.replace(".", "-")

        # iterate over secrets to check if secret with same name exists
        secret_name = self._check_secret_name(
            secrets=secrets,
            secret_name=secret_name,
            spc_keyvault_name=spc_keyvault_name,
            flag="secret-name",
            overwrite_secret=overwrite_secret,
        )

        if not secret_name:
            return

        self._upload_to_key_vault(secret_name, file, cert_extension)

        # check if there is a spc called "opc-ua-connector", if not create one
        opcua_spc = self.instances.find_existing_resources(
            cl_resources=cl_resources,
            resource_type=SPC_RESOURCE_TYPE,
            resource_name=OPCUA_SPC_NAME,
        )

        self._add_secrets_to_spc(
            secrets=[secret_name],
            spc=opcua_spc,
            resource_group=resource_group,
            spc_keyvault_name=spc_keyvault_name,
            spc_tenant_id=spc_tenant_id,
            spc_client_id=spc_client_id,
        )

        return self._add_secrets_to_secret_sync(
            secrets=[(secret_name, file_name)],
            secret_sync=opcua_secret_sync,
            resource_group=resource_group,
            spc_name=OPCUA_SPC_NAME,
            secret_sync_name=OPCUA_ISSUER_LIST_SECRET_SYNC_NAME,
        )

    def client_add(
        self,
        instance_name: str,
        resource_group: str,
        public_key_file: str,
        private_key_file: str,
        subject_name: str,
        application_uri: str,
        public_key_secret_name: Optional[str] = None,
        private_key_secret_name: Optional[str] = None,
        overwrite_secret: Optional[bool] = False,
    ) -> dict:
        # inform user if the provided cert was issued by a CA, the CA cert must be added to the issuers list.
        logger.warning("Please ensure the certificate must be added to the issuers list if it was issued by a CA. ")
        cl_resources = self._get_cl_resources(instance_name=instance_name, resource_group=resource_group)
        secretsync_spc = self._find_existing_spc(instance_name=instance_name, cl_resources=cl_resources)

        # process all the file validations before secret creations
        self._validate_key_files(public_key_file, private_key_file)

        # get properties from default spc
        spc_properties = secretsync_spc.get("properties", {})
        spc_keyvault_name = spc_properties.get("keyvaultName", "")
        spc_client_id = spc_properties.get("clientId", "")
        spc_tenant_id = spc_properties.get("tenantId", "")

        self.keyvault_client = get_keyvault_client(
            subscription_id=self.default_subscription_id,
            keyvault_name=spc_keyvault_name,
        )

        secrets: PageIterator = self.keyvault_client.list_properties_of_secrets()

        # check if there is a spc called "opc-ua-connector", if not create one
        opcua_spc = self.instances.find_existing_resources(
            cl_resources=cl_resources,
            resource_type=SPC_RESOURCE_TYPE,
            resource_name=OPCUA_SPC_NAME,
        )

        # check if there is a secret sync called "aio-opc-ua-broker-client-certificate", if not create one
        opcua_secret_sync = self.instances.find_existing_resources(
            cl_resources=cl_resources,
            resource_type=SECRET_SYNC_RESOURCE_TYPE,
            resource_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
        )

        secrets_to_add = []
        for file in [public_key_file, private_key_file]:
            file_name = os.path.basename(file)
            file_name_info = os.path.splitext(file_name)
            cert_extension = file_name_info[1].replace(".", "")
            secret_name = f"{file_name_info[0]}-{cert_extension}"

            file_type_map = {
                public_key_file: (
                    "public-key-secret-name", public_key_secret_name if public_key_secret_name else secret_name
                ),
                private_key_file: (
                    "private-key-secret-name", private_key_secret_name if private_key_secret_name else secret_name
                )
            }

            # Iterate over secrets to check if a secret with the same name exists
            if file in file_type_map:
                flag, secret_name = file_type_map[file]
            secret_name = secret_name.replace(".", "-")
            secret_name = self._check_secret_name(
                secrets=secrets,
                secret_name=secret_name,
                spc_keyvault_name=spc_keyvault_name,
                flag=flag,
                overwrite_secret=overwrite_secret,
            )

            if not secret_name:
                return

            self._upload_to_key_vault(secret_name, file, cert_extension)
            secrets_to_add.append((secret_name, file_name))

        self._add_secrets_to_spc(
            secrets=[secret[0] for secret in secrets_to_add],
            spc=opcua_spc,
            resource_group=resource_group,
            spc_keyvault_name=spc_keyvault_name,
            spc_tenant_id=spc_tenant_id,
            spc_client_id=spc_client_id,
            should_replace=True,
        )

        self._add_secrets_to_secret_sync(
            secrets=secrets_to_add,
            secret_sync=opcua_secret_sync,
            resource_group=resource_group,
            spc_name=OPCUA_SPC_NAME,
            secret_sync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
            should_replace=True,
        )

        # update opcua extension
        return self._update_client_secret_to_extension(
            applicationCert=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
            subject_name=subject_name,
            application_uri=application_uri,
        )

    def remove(
        self,
        instance_name: str,
        resource_group: str,
        secretsync_name: str,
        certificate_names: List[str],
        confirm_yes: Optional[bool] = False,
        force: Optional[bool] = False,
        include_secrets: Optional[bool] = False,
    ) -> dict:
        # check if secret sync exists
        cl_resources = self._get_cl_resources(instance_name=instance_name, resource_group=resource_group)

        # prompt for deletion
        should_bail = not should_continue_prompt(confirm_yes=confirm_yes)
        if should_bail:
            return

        if not force:
            if not self.resource_map.connected_cluster.connected:
                logger.warning(
                    "Removal cancelled. The cluster is not connected to Azure. "
                    "Use --force to continue anyway, which may lead to errors."
                )
                return

        target_secretsync = self.instances.find_existing_resources(
            cl_resources=cl_resources,
            resource_type=SECRET_SYNC_RESOURCE_TYPE,
            resource_name=secretsync_name,
        )

        if not target_secretsync:
            raise ResourceNotFoundError(f"Secret Sync resource {secretsync_name} not found. Please make sure secret "
                                        "sync is enabled and certificates are added in the target secret sync resource.")

        # find if input certificate names are valid
        target_secretsync = target_secretsync[0]
        secret_mapping = target_secretsync.get("properties", {}).get("objectSecretMapping", [])
        secret_to_remove = []
        for name in certificate_names:
            if name not in [mapping["targetKey"] for mapping in secret_mapping]:
                logger.warning(
                    f"Certificate {name} not found in secret sync {secretsync_name}. "
                    "Skipping removal of this certificate..."
                )
            else:
                # append corresponding "sourcePath" of matching "targetKey"
                secret_to_remove.append(
                    [mapping["sourcePath"] for mapping in secret_mapping if mapping["targetKey"] == name][0]
                )

        if not secret_to_remove:
            logger.warning("No valid certificates found to remove.")
            return

        # check if OPCUA_SPC_NAME spc exists
        target_spc = self.instances.find_existing_resources(
            cl_resources=cl_resources,
            resource_type=SPC_RESOURCE_TYPE,
            resource_name=OPCUA_SPC_NAME,
        )

        if not target_spc:
            raise ResourceNotFoundError(f"Secret Provider Class {OPCUA_SPC_NAME} not found.")

        # get properties from default spc
        target_spc = target_spc[0]
        spc_properties = target_spc.get("properties", {})
        spc_keyvault_name = spc_properties.get("keyvaultName", "")

        # remove secret reference from secret sync
        modified_secret_sync = self._remove_secrets_from_secret_sync(
            name=secretsync_name,
            secrets=secret_to_remove,
            secret_sync=target_secretsync,
            resource_group=resource_group
        )

        self._remove_secrets_from_spc(
            secrets=secret_to_remove,
            spc=target_spc,
            resource_group=resource_group
        )

        if include_secrets:
            # get keyvault client
            self.keyvault_client = get_keyvault_client(
                subscription_id=self.default_subscription_id,
                keyvault_name=spc_keyvault_name,
            )
            # verify the behaviour of non existed secret
            secrets: PageIterator = self.keyvault_client.list_properties_of_secrets()
            secret_names = [secret.id for secret in secrets]

            # remove secret from keyvault
            for name in secret_to_remove:
                # perform delete operation if name exists in secret_names(endwith)
                if any(secret_name.endswith(name) for secret_name in secret_names):
                    self.keyvault_client.begin_delete_secret(name)
                    self.keyvault_client.purge_deleted_secret(name)
                else:
                    logger.warning(f"Secret {name} not found in keyvault {spc_keyvault_name}. Skipping removal...")

        return modified_secret_sync

    def show(self, instance_name: str, resource_group: str, secretsync_name: str) -> dict:
        # check if secret sync exists
        cl_resources = self._get_cl_resources(instance_name=instance_name, resource_group=resource_group)
        target_secretsync = self.instances.find_existing_resources(
            cl_resources=cl_resources,
            resource_type=SECRET_SYNC_RESOURCE_TYPE,
            resource_name=secretsync_name,
        )

        if not target_secretsync:
            raise ResourceNotFoundError(
                f"Secret Sync {secretsync_name} not found. Please make sure secret sync enabled "
                "and certificates added in target secret sync."
            )

        return target_secretsync

    def _validate_key_files(self, public_key_file: str, private_key_file: str):
        # validate public key file end with .der
        validate_file_extension(public_key_file, [".der"])
        # validate private key file end with .pem
        validate_file_extension(private_key_file, [".pem"])

        # validate public key and private key has matching file name without extension
        public_key_name = os.path.basename(public_key_file)
        public_key_name = os.path.splitext(public_key_name)[0]
        private_key_name = os.path.basename(private_key_file)
        private_key_name = os.path.splitext(private_key_name)[0]

        if public_key_name != private_key_name:
            raise ValueError(f"Public key file {public_key_name} and private key file {private_key_name} must match.")

    def _add_entry_to_fortos_yaml(self, object_text: str, secret_entry: Optional[dict] = None) -> str:
        if object_text:
            objects_obj = yaml.safe_load(object_text)
        else:
            objects_obj = {"array": []}
        entry_text = yaml.safe_dump(secret_entry, indent=6)
        if entry_text not in objects_obj["array"]:
            objects_obj["array"].append(entry_text)
        object_text = yaml.safe_dump(objects_obj, indent=6)
        # TODO: formatting will be removed once fortos service fixes the formatting issue
        return object_text.replace("\n- |", "\n    - |")

    def _remove_entry_from_fortos_yaml(self, object_text: str, secret_name: str) -> str:
        if object_text:
            objects_obj = yaml.safe_load(object_text)
        else:
            objects_obj = {"array": []}

        for entry in objects_obj["array"]:
            if secret_name in entry:
                objects_obj["array"].remove(entry)
                break

        if not objects_obj["array"]:
            return ""
        object_text = yaml.safe_dump(objects_obj, indent=6)
        # TODO: formatting will be removed once fortos service fixes the formatting issue
        return object_text.replace("\n- |", "\n    - |")

    def _get_cl_resources(self, instance_name: str, resource_group: str) -> List[dict]:
        self.instance = self.instances.show(name=instance_name, resource_group_name=resource_group)
        self.resource_map = self.instances.get_resource_map(self.instance)
        custom_location = self.resource_client.resources.get_by_id(
            resource_id=self.instance["extendedLocation"]["name"], api_version=CUSTOM_LOCATIONS_API_VERSION
        )
        cl_resources = self.resource_map.connected_cluster.get_aio_resources(custom_location_id=custom_location["id"])
        return cl_resources

    def _find_existing_spc(self, instance_name: str, cl_resources: List[dict]) -> dict:
        # check if secret sync enabled by getting the default secretproviderclass
        secretsync_spc = None

        if cl_resources:
            secretsync_spc = self.instances.find_existing_resources(
                cl_resources=cl_resources,
                resource_type=SPC_RESOURCE_TYPE,
            )

        if not secretsync_spc:
            raise ResourceNotFoundError(
                f"Secret sync is not enabled for the instance {instance_name}. "
                "Please enable secret sync before adding certificate."
            )

        return secretsync_spc[0]

    # TODO: consider moving under instance as common method
    # def _find_resource_from_cl_resources(
    #     self,
    #     cl_resources: List[dict],
    #     resource_type: str,
    #     resource_name: Optional[str] = None,
    # ) -> dict:
    #     for resource in cl_resources:
    #         resource_id_container = parse_resource_id(resource["id"])
    #         cl_resource_name = resource_id_container.resource_name

    #         # Ensure both type and name (if specified) match the resource
    #         is_name_matched = resource_name is None or cl_resource_name == resource_name
    #         is_type_matched = resource["type"].lower() == resource_type

    #         if is_type_matched and is_name_matched:
    #             if resource_type == SPC_RESOURCE_TYPE:
    #                 return self.ssc_mgmt_client.azure_key_vault_secret_provider_classes.get(
    #                     resource_group_name=resource_id_container.resource_group_name,
    #                     azure_key_vault_secret_provider_class_name=cl_resource_name,
    #                 )
    #             elif resource_type == SECRET_SYNC_RESOURCE_TYPE:
    #                 return self.ssc_mgmt_client.secret_syncs.get(
    #                     resource_group_name=resource_id_container.resource_group_name,
    #                     secret_sync_name=cl_resource_name,
    #                 )

    #     return {}

    def _check_secret_name(
        self,
        secrets: PageIterator,
        secret_name: str,
        spc_keyvault_name: str,
        flag: str,
        overwrite_secret: Optional[bool] = False,
    ) -> str:
        from rich.prompt import Confirm

        new_secret_name = secret_name
        for secret in secrets:
            if secret.id.endswith(secret_name):
                if not overwrite_secret and not Confirm.ask(
                    f"Secret with name {secret_name} already exists in keyvault {spc_keyvault_name}. "
                    "Do you want to overwrite the existing secret?"
                ):
                    logger.warning(
                        "Secret overwrite operation cancelled. Please provide a different name "
                        f"via --{flag}."
                    )
                    return None

        return new_secret_name

    def _upload_to_key_vault(self, secret_name: str, file_path: str, cert_extension: str):
        with console.status(f"Uploading certificate to keyvault as secret {secret_name}..."):
            content = read_file_content(file_path=file_path, read_as_binary=True).hex()
            if cert_extension == ".crl":
                content_type = "application/pkix-crl"
            elif cert_extension == ".der":
                content_type = "application/pkix-cert"
            else:
                content_type = "application/x-pem-file"

            return self.keyvault_client.set_secret(
                name=secret_name, value=content, content_type=content_type, tags={"file-encoding": "hex"}
            )

    def _add_secrets_to_spc(
        self,
        secrets: List[str],
        spc: List[dict],
        resource_group: str,
        spc_keyvault_name: str,
        spc_tenant_id: str,
        spc_client_id: str,
        should_replace: Optional[bool] = False,
    ) -> dict:
        spc = spc[0] if spc else {}
        spc_properties = spc.get("properties", {})
        # stringified yaml array
        spc_object = "" if should_replace else spc_properties.get("objects", "")

        # add new secret to the list
        for secret_name in secrets:
            secret_entry = {
                "objectName": secret_name,
                "objectType": "secret",
                "objectEncoding": "hex",
            }

            spc_object = self._add_entry_to_fortos_yaml(object_text=spc_object, secret_entry=secret_entry)

        if not spc:
            logger.warning(f"Azure Key Vault Secret Provider Class {OPCUA_SPC_NAME} not found, creating new one...")
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

        with console.status(f"Adding secret reference in Secret Provider Class {OPCUA_SPC_NAME}..."):
            poller = self.ssc_mgmt_client.azure_key_vault_secret_provider_classes.begin_create_or_update(
                resource_group_name=resource_group,
                azure_key_vault_secret_provider_class_name=OPCUA_SPC_NAME,
                resource=spc,
            )
            wait_for_terminal_state(poller)

    def _add_secrets_to_secret_sync(
        self,
        secrets: List[Tuple[str, str]],
        secret_sync: List[dict],
        resource_group: str,
        spc_name: str,
        secret_sync_name: str,
        should_replace: Optional[bool] = False,
    ) -> dict:
        secret_sync = secret_sync[0] if secret_sync else {}
        # check if there is a secret sync called secret_sync_name, if not create one
        secret_mapping = [] if should_replace else secret_sync.get("properties", {}).get("objectSecretMapping", [])
        source_paths = [mapping["sourcePath"] for mapping in secret_mapping]
        # add new secret to the list
        for secret_name, file_name in secrets:
            if secret_name in source_paths:
                # update the targetKey value if secret already exists
                secret_mapping = [
                    {**mapping, "targetKey": file_name} if mapping["sourcePath"] == secret_name else mapping
                    for mapping in secret_mapping
                ]
            else:
                secret_mapping.append(
                    {
                        "sourcePath": secret_name,
                        "targetKey": file_name,
                    }
                )

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
        with console.status(f"Adding secret reference to secret sync {secret_sync_name}..."):
            poller = self.ssc_mgmt_client.secret_syncs.begin_create_or_update(
                resource_group_name=resource_group,
                secret_sync_name=secret_sync_name,
                resource=secret_sync,
            )
            return wait_for_terminal_state(poller)

    def _update_client_secret_to_extension(
        self,
        applicationCert: str,
        subject_name: str,
        application_uri: str,
    ):
        # get the opcua extension
        extensions = self.resource_map.connected_cluster.get_extensions_by_type(IOT_OPS_EXTENSION_TYPE)
        aio_extension = extensions.get(IOT_OPS_EXTENSION_TYPE)
        if not aio_extension:
            raise ResourceNotFoundError("IoT Operations extension not found.")

        properties = aio_extension["properties"]

        config_settings: dict = properties.get("configurationSettings", {})
        if not config_settings:
            properties["configurationSettings"] = {}

        if applicationCert == DEFAULT_SELF_SIGNED_CERT_NAME:
            # remove the securityPki properties
            config_settings["connectors.values.securityPki.applicationCert"] = ""
            config_settings["connectors.values.securityPki.subjectName"] = ""
            config_settings["connectors.values.securityPki.applicationUri"] = ""
        elif applicationCert == OPCUA_CLIENT_CERT_SECRET_SYNC_NAME:
            config_settings["connectors.values.securityPki.applicationCert"] = applicationCert
            config_settings["connectors.values.securityPki.subjectName"] = subject_name
            config_settings["connectors.values.securityPki.applicationUri"] = application_uri

        aio_extension["properties"]["configurationSettings"] = config_settings

        with console.status(
            f"Updating IoT Operations extension to use {applicationCert}..."
        ):
            return self.resource_map.connected_cluster.update_aio_extension(
                extension_name=aio_extension["name"],
                properties=properties,
            )

    def _remove_secrets_from_spc(self, secrets: List[str], spc: dict, resource_group: str) -> dict:
        spc_properties = spc.get("properties", {})
        # stringified yaml array
        spc_object = spc_properties.get("objects", "")

        # remove secret from the list
        for secret_name in secrets:
            spc_object = self._remove_entry_from_fortos_yaml(spc_object, secret_name)

        if not spc_object:
            # remove the objects property instead of delete there resource if no secrets are left
            # as this spc is used for all opcua certs config
            spc["properties"].pop("objects", None)
        else:
            spc["properties"]["objects"] = spc_object

        with console.status(f"Removing secret reference in Secret Provider Class {OPCUA_SPC_NAME}..."):
            poller = self.ssc_mgmt_client.azure_key_vault_secret_provider_classes.begin_create_or_update(
                resource_group_name=resource_group,
                azure_key_vault_secret_provider_class_name=OPCUA_SPC_NAME,
                resource=spc,
            )
            return wait_for_terminal_state(poller)

    def _remove_secrets_from_secret_sync(
        self,
        name: str,
        secrets: List[str],
        secret_sync: dict,
        resource_group: str
    ) -> dict:
        # check if there is a secret sync called secret_sync_name, if not create one
        secret_mapping = secret_sync.get("properties", {}).get("objectSecretMapping", [])
        # remove secret from the list
        for secret_name in secrets:
            secret_mapping = [mapping for mapping in secret_mapping if mapping["sourcePath"] != secret_name]

        if len(secret_mapping) == 0:
            # remove the secret sync since only updating "objectSecretMapping" with empty list is not allowed
            with console.status(f"Removing Secret Sync resource {name}, as no secrets left..."):
                poller = self.ssc_mgmt_client.secret_syncs.begin_delete(
                    resource_group_name=resource_group,
                    secret_sync_name=name,
                )
            wait_for_terminal_state(poller)

            # rollback aio extension settings
            return self._update_client_secret_to_extension(
                applicationCert=DEFAULT_SELF_SIGNED_CERT_NAME,
                subject_name="",
                application_uri="",
            )
        else:
            secret_sync["properties"]["objectSecretMapping"] = secret_mapping

        with console.status(f"Removing secret reference in Secret Sync {name}..."):
            poller = self.ssc_mgmt_client.secret_syncs.begin_create_or_update(
                resource_group_name=resource_group,
                secret_sync_name=name,
                resource=secret_sync,
            )
            return wait_for_terminal_state(poller)
