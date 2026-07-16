# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from datetime import datetime, timezone
import re
from cryptography import x509
from pathlib import Path
from typing import List, Optional, Tuple, Union, cast

from azure.core.exceptions import ResourceNotFoundError, HttpResponseError
from azure.core.pipeline.transport import HttpTransport
from azure.cli.core.azclierror import InvalidArgumentValueError, ValidationError
from knack.log import get_logger
from rich.console import Console
import yaml

from ....common import CUSTOM_LOCATIONS_API_VERSION, EXTENSION_TYPE_OPS, X509FileExtension
from ...instances import SECRET_SYNC_RESOURCE_TYPE, Instances
from .....orchestration.upgrade2 import calculate_config_delta
from ......util.file_operations import read_file_content, validate_file_extension
from ......util.queryable import Queryable
from ......util.cloud_config import CloudConfig
from ......util.az_client import (
    get_keyvault_client,
    get_ssc_mgmt_client,
    wait_for_terminal_state,
)
from ......util.common import should_continue_prompt
from ......util.x509 import decode_x509_files

logger = get_logger(__name__)

console = Console()

OPCUA_SPC_NAME = "opc-ua-connector"
OPCUA_TRUST_LIST_SECRET_SYNC_NAME = "aio-opc-ua-broker-trust-list"
OPCUA_ISSUER_LIST_SECRET_SYNC_NAME = "aio-opc-ua-broker-issuer-list"
OPCUA_CLIENT_CERT_SECRET_SYNC_NAME = "aio-opc-ua-broker-client-certificate"
SERVICE_ACCOUNT_NAME = "aio-ssc-sa"
SECRET_DELETE_MAX_RETRIES = 10
SECRET_DELETE_RETRY_INTERVAL = 2
DEFAULT_SECRET_EXPIRATION_DAYS = 180  # Default to 180 days for governance policy compliance


class OpcUACerts(Queryable):

    def __init__(
        self,
        cmd,
        resource_group_name: str,
        instance_name: str,
    ):
        super().__init__(cmd=cmd)
        self.instances = Instances(self.cmd)
        self.ssc_mgmt_client = get_ssc_mgmt_client(
            **self._get_client_kwargs()
        )
        cloud_config = CloudConfig(self.cmd)
        self.keyvault_client = get_keyvault_client(
            subscription_id=self.default_subscription_id,
            keyvault_scope=cloud_config.keyvault_scope,
        )
        self._keyvault_dns_suffix = cloud_config.keyvault_dns_suffix
        self.instance_name = instance_name
        self.resource_group_name = resource_group_name

        instance = self.instances.show(name=self.instance_name, resource_group_name=self.resource_group_name)
        self.resource_map = self.instances.get_resource_map(instance)
        self.extended_location = instance["extendedLocation"]
        self.location = instance["location"]
        self.opcua_mode = instance.get("properties", {}).get("features", {}).get("opcua", {}).get("mode")

    def _build_vault_url(self, keyvault_name: str) -> str:
        """Build the Key Vault data-plane base URL for the active cloud."""
        return f"https://{keyvault_name}{self._keyvault_dns_suffix}/"

    def _assert_opcua_enabled(self) -> None:
        """Raise ValidationError if OPC UA is explicitly disabled on the instance."""
        if self.opcua_mode == "Disabled":
            raise ValidationError(
                f"OPC UA connector is disabled for instance '{self.instance_name}'. "
                "Enable it before managing OPC UA connector certificates:\n"
                f"  az iot ops update -n {self.instance_name} -g {self.resource_group_name} "
                "--feature opcua.mode=Stable"
            )

    def trust_add(
        self,
        file: str,
        overwrite_secret: bool = False,
        secret_name: Optional[str] = None,
        expiration_date: Optional[str] = None,
    ) -> dict:
        self._assert_opcua_enabled()
        default_spc = self.instances.get_default_spc(
            instance_name=self.instance_name,
            resource_group_name=self.resource_group_name,
        )
        spc_name = default_spc["name"]

        # get file extension
        file_name = Path(file).name
        cert_extension, _ = self._process_cert_content(
            file_path=file,
            file_name=file_name,
            expected_exts={X509FileExtension.DER.value, X509FileExtension.CRT.value},
        )

        # get properties from default spc
        spc_properties = default_spc.get("properties", {})
        spc_keyvault_name = spc_properties.get("keyvaultName", "")

        secret_name = secret_name if secret_name else file_name.replace(".", "-")

        # iterate over secrets to check if secret with same name exists
        secret_name = self._check_secret_name(
            secret_names=self._get_secret_names(spc_keyvault_name),
            secret_name=secret_name,
            spc_keyvault_name=spc_keyvault_name,
            flag="secret-name",
            overwrite_secret=overwrite_secret,
        )

        if not secret_name:
            return

        self._upload_to_key_vault(
            keyvault_name=spc_keyvault_name,
            secret_name=secret_name,
            file_path=file,
            cert_extension=cert_extension,
            expiration_date=expiration_date,
        )

        self._add_secrets_to_spc(
            secrets=[secret_name],
            spc=default_spc,
            resource_group=self.resource_group_name,
        )

        opcua_secret_sync = self._get_resource_by_name(
            resource_type=SECRET_SYNC_RESOURCE_TYPE,
            resource_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
        )

        return self._add_secrets_to_secret_sync(
            secrets=[(secret_name, file_name)],
            secret_sync=opcua_secret_sync,
            resource_group=self.resource_group_name,
            spc_name=spc_name,
            secret_sync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
        )

    def issuer_add(
        self,
        file: str,
        overwrite_secret: bool = False,
        secret_name: Optional[str] = None,
    ) -> dict:
        self._assert_opcua_enabled()
        # get default SPC
        default_spc = self.instances.get_default_spc(self.instance_name, self.resource_group_name)
        spc_name = default_spc["name"]

        # get file extension
        file_name = Path(file).name

        cert_extension, cert = self._process_cert_content(
            file_path=file,
            file_name=file_name,
            expected_exts={X509FileExtension.DER.value, X509FileExtension.CRT.value, X509FileExtension.CRL.value},
        )

        # see if should check if cert is CA if version is v3 and extension is .der or .crt
        # since there is no BasicConstraints if x509 version is not v3
        should_raise_ca_error = False
        if (
            cert_extension in {X509FileExtension.DER.value, X509FileExtension.CRT.value}
            and cert.version == x509.Version.v3
        ):
            should_raise_ca_error = not self._is_ca_cert(cert)
        if should_raise_ca_error:
            raise InvalidArgumentValueError(
                f"The certificate {file_name} is not a CA certificate. "
                "Only CA certificates can be added to the issuer list."
            )

        # get properties from default spc
        spc_properties = default_spc.get("properties", {})
        spc_keyvault_name = spc_properties.get("keyvaultName", "")

        # get cert name by removing extension
        cert_name = Path(file_name).stem

        opcua_secret_sync = self._get_resource_by_name(
            resource_type=SECRET_SYNC_RESOURCE_TYPE,
            resource_name=OPCUA_ISSUER_LIST_SECRET_SYNC_NAME,
        )

        if cert_extension == X509FileExtension.CRL.value:
            matched_names = []
            if opcua_secret_sync:
                secret_mapping = opcua_secret_sync.get("properties", {}).get("objectSecretMapping", [])
                possible_file_names = [
                    f"{cert_name}{X509FileExtension.CRT.value}",
                    f"{cert_name}{X509FileExtension.DER.value}",
                ]
                matched_names = [
                    mapping["targetKey"] for mapping in secret_mapping if mapping["targetKey"] in possible_file_names
                ]

            if not opcua_secret_sync or not matched_names:
                raise InvalidArgumentValueError(
                    f"Cannot add {X509FileExtension.CRL.value} {file_name} without corresponding "
                    f"{X509FileExtension.CRT.value} or {X509FileExtension.DER.value} file."
                )

        secret_name = secret_name if secret_name else file_name.replace(".", "-")

        # iterate over secrets to check if secret with same name exists
        secret_name = self._check_secret_name(
            secret_names=self._get_secret_names(spc_keyvault_name),
            secret_name=secret_name,
            spc_keyvault_name=spc_keyvault_name,
            flag="secret-name",
            overwrite_secret=overwrite_secret,
        )

        if not secret_name:
            return

        self._upload_to_key_vault(
            keyvault_name=spc_keyvault_name,
            secret_name=secret_name,
            file_path=file,
            cert_extension=cert_extension,
        )

        self._add_secrets_to_spc(
            secrets=[secret_name],
            spc=default_spc,
            resource_group=self.resource_group_name,
        )

        return self._add_secrets_to_secret_sync(
            secrets=[(secret_name, file_name)],
            secret_sync=opcua_secret_sync,
            resource_group=self.resource_group_name,
            spc_name=spc_name,
            secret_sync_name=OPCUA_ISSUER_LIST_SECRET_SYNC_NAME,
        )

    def client_add(
        self,
        public_key_file: str,
        private_key_file: str,
        overwrite_secret: bool = False,
        subject_name: Optional[str] = None,
        application_uri: Optional[str] = None,
        public_key_secret_name: Optional[str] = None,
        private_key_secret_name: Optional[str] = None,
    ) -> dict:
        self._assert_opcua_enabled()
        default_spc = self.instances.get_default_spc(
            instance_name=self.instance_name,
            resource_group_name=self.resource_group_name,
        )

        # process all the file validations before secret creations
        self._validate_key_files(public_key_file, private_key_file)

        # extract certificate information and validate if optional parameters are provided
        subject_name, application_uri = self._process_client_cert_content(
            public_key_file, subject_name, application_uri
        )

        # get properties from default spc
        spc_properties = default_spc.get("properties", {})
        spc_keyvault_name = spc_properties.get("keyvaultName", "")

        spc_name = default_spc["name"]

        # check if there is a secret sync called "aio-opc-ua-broker-client-certificate", if not create one
        opcua_secret_sync = self._get_resource_by_name(
            resource_type=SECRET_SYNC_RESOURCE_TYPE,
            resource_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
        )

        secrets_to_add = []
        secret_names = self._get_secret_names(spc_keyvault_name)
        for file in [public_key_file, private_key_file]:
            p = Path(file)
            file_name = p.name
            file_name_info = (p.stem, p.suffix)
            cert_extension = file_name_info[1].replace(".", "")
            secret_name = f"{file_name_info[0]}-{cert_extension}"

            file_type_map = {
                public_key_file: (
                    "public-key-secret-name",
                    public_key_secret_name if public_key_secret_name else secret_name,
                ),
                private_key_file: (
                    "private-key-secret-name",
                    private_key_secret_name if private_key_secret_name else secret_name,
                ),
            }

            # Iterate over secrets to check if a secret with the same name exists
            if file in file_type_map:
                flag, secret_name = file_type_map[file]
            secret_name = secret_name.replace(".", "-")
            secret_name = self._check_secret_name(
                secret_names=secret_names,
                secret_name=secret_name,
                spc_keyvault_name=spc_keyvault_name,
                flag=flag,
                overwrite_secret=overwrite_secret,
            )

            if not secret_name:
                return

            self._upload_to_key_vault(
                keyvault_name=spc_keyvault_name,
                secret_name=secret_name,
                file_path=file,
                cert_extension=cert_extension,
            )
            secrets_to_add.append((secret_name, file_name))

        # use secret sync to find certificate pair secret names to be replaces
        secrets_to_replace = []
        if opcua_secret_sync:
            secret_mapping = opcua_secret_sync.get("properties", {}).get("objectSecretMapping", [])
            secrets_to_replace = [mapping["sourcePath"] for mapping in secret_mapping]

        self._add_secrets_to_spc(
            secrets=[secret[0] for secret in secrets_to_add],
            spc=default_spc,
            resource_group=self.resource_group_name,
            secrets_to_replace=secrets_to_replace,
        )

        self._add_secrets_to_secret_sync(
            secrets=secrets_to_add,
            secret_sync=opcua_secret_sync,
            resource_group=self.resource_group_name,
            spc_name=spc_name,
            secret_sync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
            should_replace=True,
        )

        # update opcua extension
        return self._update_client_secret_to_extension(
            application_cert=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
            subject_name=subject_name,
            application_uri=application_uri,
        )

    def remove(
        self,
        secretsync_name: str,
        certificate_names: List[str],
        confirm_yes: Optional[bool] = False,
        force: Optional[bool] = False,
        include_secrets: Optional[bool] = False,
    ) -> dict:
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

        target_secretsync = self._get_resource_by_name(
            resource_type=SECRET_SYNC_RESOURCE_TYPE,
            resource_name=secretsync_name,
        )

        if not target_secretsync:
            raise ResourceNotFoundError(
                f"Secretsync resource {secretsync_name} not found. Please make sure secret "
                "sync is enabled and certificates are added in the target secretsync resource."
            )

        # find if input certificate names are valid
        secret_mapping = target_secretsync.get("properties", {}).get("objectSecretMapping", [])
        secret_to_remove = []
        for name in certificate_names:
            if name not in [mapping["targetKey"] for mapping in secret_mapping]:
                logger.warning(
                    f"Certificate {name} not found in secretsync resource {secretsync_name}. Skipping removal..."
                )
            else:
                # append corresponding "sourcePath" of matching "targetKey"
                secret_to_remove.append(
                    [mapping["sourcePath"] for mapping in secret_mapping if mapping["targetKey"] == name][0]
                )

        if not secret_to_remove:
            raise InvalidArgumentValueError("Please provide valid certificate name(s) to remove.")

        # check if spc exists
        target_spc = self.instances.get_default_spc(
            instance_name=self.instance_name,
            resource_group_name=self.resource_group_name,
        )

        # get properties from default spc
        spc_properties = target_spc.get("properties", {})
        spc_keyvault_name = spc_properties.get("keyvaultName", "")

        # remove secret reference from secret sync
        modified_secret_sync = self._remove_secrets_from_secret_sync(
            name=secretsync_name,
            secrets=secret_to_remove,
            secret_sync=target_secretsync,
            resource_group=self.resource_group_name,
        )

        self._remove_secrets_from_spc(secrets=secret_to_remove, spc=target_spc, resource_group=self.resource_group_name)

        if include_secrets:
            # verify the behaviour of non existed secret
            secret_names = self._get_secret_names(spc_keyvault_name)

            # remove secret from keyvault
            for name in secret_to_remove:
                # perform delete operation if name exists in secret_names(endwith)
                if any(secret_name.endswith(name) for secret_name in secret_names):
                    with console.status(f"Deleting and purging secret {name} from keyvault {spc_keyvault_name}..."):
                        self._begin_delete_secret(spc_keyvault_name, name)
                        self.keyvault_client.purge_deleted_secret(
                            vault_base_url=self._build_vault_url(spc_keyvault_name),
                            secret_name=name,
                        )
                else:
                    logger.warning(f"Secret {name} not found in keyvault {spc_keyvault_name}. Skipping removal...")

        return modified_secret_sync

    def show(self, secretsync_name: str) -> dict:
        # check if secret sync exists
        target_secretsync = self._get_resource_by_name(
            resource_type=SECRET_SYNC_RESOURCE_TYPE,
            resource_name=secretsync_name,
        )

        if not target_secretsync:
            raise ResourceNotFoundError(f"Secretsync resource {secretsync_name} not found.")

        return target_secretsync

    def _validate_key_files(self, public_key_file: str, private_key_file: str):
        # validate public key file end with .der
        _, cert = self._process_cert_content(
            file_path=public_key_file,
            file_name=Path(public_key_file).name,
            expected_exts={X509FileExtension.DER.value},
        )

        # warn if the certificate is not self-signed
        # inform user if the provided cert was issued by a CA, the CA cert must be added to the issuers list.
        if not self._is_cert_self_signed(cert):
            logger.warning(
                "If this certificate was issued by a CA, then please ensure that the CA certificate is "
                "added to issuer list."
            )
        # validate private key file end with .pem
        validate_file_extension(private_key_file, {X509FileExtension.PEM.value})

        # validate public key and private key has matching file name without extension
        public_key_name = Path(public_key_file).stem
        private_key_name = Path(private_key_file).stem

        if public_key_name != private_key_name:
            raise InvalidArgumentValueError(
                f"Public key file name {public_key_name} and private key file name {private_key_name} must match."
            )

    def _add_entry_to_fortos_yaml(
        self,
        object_text: str,
        secret_entry: Optional[dict] = None,
    ) -> str:
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
            entry_obj = yaml.safe_load(entry)
            if secret_name == entry_obj["objectName"]:
                objects_obj["array"].remove(entry)
                break

        if not objects_obj["array"]:
            return ""
        object_text = yaml.safe_dump(objects_obj, indent=6)
        # TODO: formatting will be removed once fortos service fixes the formatting issue
        return object_text.replace("\n- |", "\n    - |")

    def _get_cl_resources(self) -> List[dict]:
        custom_location = self.resource_client.resources.get_by_id(
            resource_id=self.extended_location["name"], api_version=CUSTOM_LOCATIONS_API_VERSION
        )
        cl_resources = self.resource_map.connected_cluster.get_aio_resources(custom_location_id=custom_location["id"])
        return cl_resources

    def _extract_cert_expiration(self, cert: x509.Certificate) -> datetime:
        """
        Extract the expiration date from a certificate, handling both old and new cryptography library versions.

        Args:
            cert: The certificate object

        Returns:
            datetime: UTC-aware datetime of the certificate's expiration
        """
        # Handle both old and new cryptography library versions
        try:
            expiry_date = cert.not_valid_after_utc
        except AttributeError:
            # Fallback for older cryptography versions (< 41.0)
            expiry_date = cert.not_valid_after
            # Convert to UTC-aware datetime if it's naive
            if expiry_date.tzinfo is None:
                expiry_date = expiry_date.replace(tzinfo=timezone.utc)

        return expiry_date

    def _check_secret_name(
        self,
        secret_names: List[str],
        secret_name: str,
        spc_keyvault_name: str,
        flag: str,
        overwrite_secret: bool = False,
    ) -> Optional[str]:
        from rich.prompt import Confirm

        new_secret_name = secret_name

        # check if secret matches regex
        regexp = r"^[0-9a-zA-Z-]+$"
        if not new_secret_name or not re.match(regexp, new_secret_name):
            raise InvalidArgumentValueError(
                f"Secret name {new_secret_name} is invalid. Secret name must be alphanumeric and can contain hyphens. "
                f"Please provide a valid secret name via --{flag}."
            )

        if any(name.endswith(secret_name) for name in secret_names):
            if not overwrite_secret and not Confirm.ask(
                f"Secret with name {secret_name} already exists in keyvault {spc_keyvault_name}. "
                "Do you want to overwrite the existing secret?"
            ):
                logger.warning(
                    "Secret overwrite operation cancelled. Please provide a different name " f"via --{flag}."
                )
                return

        return new_secret_name

    def _calculate_secret_expiration(
        self,
        file_path: str,
        cert_extension: str,
        expiration_date: Optional[str] = None,
    ) -> datetime:
        """
        Calculate the appropriate expiration date for a Key Vault secret.

        Priority order:
        1. If expiration_date is provided by user, use that
        2. For certificate files (.der, .crt), extract the certificate's expiration date
        3. Default to 180 days from now

        Args:
            file_path: Path to the certificate/key file
            cert_extension: File extension indicating the file type
            expiration_date: Optional expiration date string in ISO 8601 format (user-provided)

        Returns:
            datetime: UTC-aware datetime for secret expiration
        """
        from datetime import timedelta
        from dateutil import parser as date_parser

        # Priority 1: User-provided expiration date
        if expiration_date is not None:
            try:
                user_expiration = date_parser.isoparse(expiration_date)
                # Ensure it's UTC-aware
                if user_expiration.tzinfo is None:
                    user_expiration = user_expiration.replace(tzinfo=timezone.utc)

                # Validate it's in the future
                if user_expiration <= datetime.now(timezone.utc):
                    raise InvalidArgumentValueError(
                        f"Expiration date must be in the future. Provided: {expiration_date}"
                    )

                logger.info(
                    f"Using user-provided expiration date: {user_expiration.strftime('%Y-%m-%d %H:%M:%S UTC')} "
                    f"for Key Vault secret."
                )
                return user_expiration
            except (ValueError, TypeError) as e:
                raise InvalidArgumentValueError(
                    f"Invalid expiration date format. Expected ISO 8601 format (e.g., 2025-12-31T23:59:59Z). "
                    f"Provided: {expiration_date}. Error: {str(e)}"
                )

        # Priority 2: For certificate files, try to extract the certificate's actual expiration date
        if cert_extension in {X509FileExtension.DER.value, X509FileExtension.CRT.value}:
            try:
                cert_data = read_file_content(file_path=file_path, read_as_binary=True)
                expected_format = (
                    X509FileExtension.PEM.name if cert_extension == X509FileExtension.CRT.value
                    else X509FileExtension.DER.name
                )
                certs = decode_x509_files(cert_data, expected_format, cert_extension)

                if certs:
                    cert = certs[0]
                    expiry_date = self._extract_cert_expiration(cert)

                    logger.info(
                        f"Using certificate expiration date: {expiry_date.strftime('%Y-%m-%d %H:%M:%S UTC')} "
                        f"for Key Vault secret."
                    )
                    return expiry_date
            except Exception as e:
                # If certificate parsing fails, log warning and fall through to default
                logger.warning(
                    f"Could not extract expiration from certificate: {str(e)}. "
                    f"Using default expiration of {DEFAULT_SECRET_EXPIRATION_DAYS} days."
                )

        # Priority 3: Default to 180 days from now for:
        # - Private keys (.pem)
        # - Certificate Revocation Lists (.crl)
        # - Any files where certificate parsing failed
        default_expiration = datetime.now(timezone.utc) + timedelta(days=DEFAULT_SECRET_EXPIRATION_DAYS)
        logger.info(
            f"Using default expiration date: {default_expiration.strftime('%Y-%m-%d %H:%M:%S UTC')} "
            f"({DEFAULT_SECRET_EXPIRATION_DAYS} days) for Key Vault secret."
        )
        return default_expiration

    def _upload_to_key_vault(
        self,
        keyvault_name: str,
        secret_name: str,
        file_path: str,
        cert_extension: str,
        expiration_date: Optional[str] = None,
    ):
        """
        Upload a certificate or key file to Azure Key Vault as a secret with expiration date.

        This method ensures Key Vault governance policy compliance by setting an expiration
        date on the secret (required by many enterprise policies).

        Args:
            keyvault_name: Name of the Azure Key Vault
            secret_name: Name for the secret in Key Vault
            file_path: Path to the certificate/key file
            cert_extension: File extension indicating the file type
            expiration_date: Optional expiration date string in ISO 8601 format (user-provided via CLI)

        Returns:
            The Key Vault secret response
        """
        with console.status(f"Uploading certificate to keyvault as secret {secret_name}..."):
            content = read_file_content(file_path=file_path, read_as_binary=True).hex()

            # Determine content type based on file extension
            if cert_extension == X509FileExtension.CRL.value:
                content_type = "application/pkix-crl"
            elif cert_extension == X509FileExtension.DER.value:
                content_type = "application/pkix-cert"
            else:
                content_type = "application/x-pem-file"

            # Calculate expiration date for Key Vault compliance
            # Priority: user-provided > certificate expiration > 180-day default
            calculated_expiration = self._calculate_secret_expiration(file_path, cert_extension, expiration_date)

            # Build parameters with compliance attributes
            # Note: Key Vault API expects expiration in attributes.exp (Unix timestamp format)
            parameters = {
                "value": content,
                "contentType": content_type,
                "tags": {"file-encoding": "hex"},
                "attributes": {
                    "exp": int(calculated_expiration.timestamp()),  # Required by Key Vault governance policies
                },
            }

            logger.info(
                f"Creating Key Vault secret '{secret_name}' with expiration: "
                f"{calculated_expiration.strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )

            return self.keyvault_client.set_secret(
                vault_base_url=self._build_vault_url(keyvault_name),
                secret_name=secret_name,
                parameters=parameters,
            )

    def _add_secrets_to_spc(
        self,
        secrets: List[str],
        spc: dict,
        resource_group: str,
        secrets_to_replace: Optional[List[str]] = None,
    ):
        spc_properties = spc.get("properties", {})
        # stringified yaml array
        spc_object = spc_properties.get("objects", "")

        # first to remove the previous secrets from the list
        if secrets_to_replace:
            for secret_name in secrets_to_replace:
                spc_object = self._remove_entry_from_fortos_yaml(spc_object, secret_name)

        # add new secret to the list
        for secret_name in secrets:
            secret_entry = {
                "objectName": secret_name,
                "objectType": "secret",
                "objectEncoding": "hex",
            }

            spc_object = self._add_entry_to_fortos_yaml(
                object_text=spc_object,
                secret_entry=secret_entry,
            )

        spc["properties"]["objects"] = spc_object

        with console.status(f"Adding secret reference in Secret Provider Class resource {spc['name']}..."):
            poller = self.ssc_mgmt_client.azure_key_vault_secret_provider_classes.begin_create_or_update(
                resource_group_name=resource_group,
                azure_key_vault_secret_provider_class_name=spc["name"],
                resource=spc,
            )
            wait_for_terminal_state(poller)

    def _add_secrets_to_secret_sync(
        self,
        secrets: List[Tuple[str, str]],
        secret_sync: dict,
        resource_group: str,
        spc_name: str,
        secret_sync_name: str,
        should_replace: Optional[bool] = False,
    ) -> dict:
        # check if there is a secret sync called secret_sync_name, if not create one
        secret_sync = secret_sync or {}
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
            logger.warning(f"Secretsync resource {secret_sync_name} not found, creating new one...")
            secret_sync = {
                "location": self.location,
                "extendedLocation": self.extended_location,
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
        with console.status(f"Adding secret reference to secretsync resource {secret_sync_name}..."):
            poller = self.ssc_mgmt_client.secret_syncs.begin_create_or_update(
                resource_group_name=resource_group,
                secret_sync_name=secret_sync_name,
                resource=secret_sync,
            )
            return wait_for_terminal_state(poller)

    def _update_client_secret_to_extension(
        self,
        application_cert: str,
        subject_name: str,
        application_uri: str,
    ) -> dict:
        # get the opcua extension
        extensions = self.resource_map.connected_cluster.get_extensions_by_type(EXTENSION_TYPE_OPS)
        aio_extension = extensions.get(EXTENSION_TYPE_OPS)
        if not aio_extension:
            raise ResourceNotFoundError("IoT Operations extension not found.")

        properties = aio_extension["properties"]

        config_settings: dict = properties.get("configurationSettings", {})

        desired_config_settings = config_settings.copy()
        desired_config_settings["connectors.values.securityPki.applicationCert"] = application_cert
        desired_config_settings["connectors.values.securityPki.subjectName"] = subject_name
        desired_config_settings["connectors.values.securityPki.applicationUri"] = application_uri

        delta = calculate_config_delta(
            current=config_settings,
            target=desired_config_settings,
        )

        if delta:
            status_text = (
                f"Updating IoT Operations extension to use {application_cert}..."
                if application_cert
                else "Rollback client certificate from IoT Operations extension..."
            )

            with console.status(status_text):
                return self.resource_map.connected_cluster.update_aio_extension(
                    extension_name=aio_extension["name"],
                    properties={
                        "configurationSettings": delta,
                    },
                )
        else:
            logger.warning("No changes detected in IoT Operations extension. Skipping update...")
            return {}

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

        with console.status(f"Removing secret reference in Secret Provider Class resource {spc['name']}..."):
            poller = self.ssc_mgmt_client.azure_key_vault_secret_provider_classes.begin_create_or_update(
                resource_group_name=resource_group,
                azure_key_vault_secret_provider_class_name=spc["name"],
                resource=spc,
            )
            return wait_for_terminal_state(poller)

    def _remove_secrets_from_secret_sync(
        self, name: str, secrets: List[str], secret_sync: dict, resource_group: str
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
                result = wait_for_terminal_state(poller)

            if name == OPCUA_CLIENT_CERT_SECRET_SYNC_NAME:
                # rollback aio extension settings
                self._update_client_secret_to_extension(
                    application_cert="",
                    subject_name="",
                    application_uri="",
                )
            return result
        else:
            secret_sync["properties"]["objectSecretMapping"] = secret_mapping

            with console.status(f"Removing secret reference in secretsync resource {name}..."):
                poller = self.ssc_mgmt_client.secret_syncs.begin_create_or_update(
                    resource_group_name=resource_group,
                    secret_sync_name=name,
                    resource=secret_sync,
                )
                return wait_for_terminal_state(poller)

    def _get_secret_names(self, keyvault_name: str) -> List[str]:
        secret_iteratable = self.keyvault_client.get_secrets(
            vault_base_url=self._build_vault_url(keyvault_name)
        )
        return [secret["id"] for secret in secret_iteratable if "id" in secret]

    def _begin_delete_secret(self, keyvault_name: str, secret_name: str):
        # Construct vault URL
        vault_url = self._build_vault_url(keyvault_name)

        # Initiate deletion
        pipeline_response = self.keyvault_client.delete_secret(
            vault_base_url=vault_url,
            secret_name=secret_name,
            cls=lambda pipeline_response, _, __: pipeline_response,
        )

        for attempt in range(SECRET_DELETE_MAX_RETRIES):
            try:
                # Check if secret is deleted
                self.keyvault_client.get_deleted_secret(
                    vault_base_url=vault_url,
                    secret_name=secret_name,
                )
                return  # Exit if no exception, deletion confirmed
            except ResourceNotFoundError:
                # Secret not yet deleted; retry after delay
                transport: HttpTransport = cast(HttpTransport, pipeline_response.context.transport)
                transport.sleep(SECRET_DELETE_RETRY_INTERVAL)
                attempt += 1
            except HttpResponseError as e:
                if e.status_code == 403:
                    # Permission issue encountered; exit loop
                    break
                raise

        # Failed to confirm deletion after retries
        raise TimeoutError(f"Failed to delete secret '{secret_name}' within {SECRET_DELETE_MAX_RETRIES} retries.")

    def _extract_client_cert_content(
        self,
        public_key_file: str,
    ) -> Tuple[str, str]:
        from cryptography.x509.oid import NameOID, ExtensionOID

        der_data = read_file_content(file_path=public_key_file, read_as_binary=True)
        file_extension = Path(public_key_file).suffix.lower()
        certificate = decode_x509_files(der_data, X509FileExtension.DER.name, file_extension).pop()

        if not certificate:
            raise InvalidArgumentValueError(
                "Error decoding DER certificate. Please make sure the certificate is valid."
            )

        # Get the subject name and application uri from the certificate
        # and validate it with the provided values
        cert_subject_name = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value

        cert_application_uri = ""
        extension_value = certificate.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value

        uris = []
        for general_name in extension_value:
            if isinstance(general_name, x509.UniformResourceIdentifier):
                uris.append(general_name.value)

        if len(uris) > 1:
            # warning if multiple URIs are found
            logger.warning(
                "Multiple URIs detected in provided certificate, "
                "this might fail OPC UA stack validation going forward."
            )
        else:
            cert_application_uri = uris[0] if uris else ""

        for value, name in [(cert_subject_name, "subject name"), (cert_application_uri, "application URI")]:
            # if value is empty or space, raise error
            if not value or value.isspace():
                raise InvalidArgumentValueError(
                    f"Not able to extract {name} from the certificate. "
                    f"Please provide the correct {name} in certificate via --public-key-file."
                )

        return cert_subject_name, cert_application_uri

    def _process_client_cert_content(
        self,
        public_key_file: str,
        subject_name: Optional[str],
        application_uri: Optional[str],
    ) -> Tuple[str, str]:
        # extract subject name and application URI from public_key_file content
        cert_subject_name, cert_application_uri = self._extract_client_cert_content(public_key_file)

        if subject_name and subject_name != cert_subject_name:
            raise InvalidArgumentValueError(
                f"Given --subject-name {subject_name} does not match certificate subject name {cert_subject_name}. "
                "Please provide the correct subject name via --subject-name or correct certificate using "
                "--public-key-file."
            )

        if application_uri and application_uri != cert_application_uri:
            raise InvalidArgumentValueError(
                f"Given --application-uri {application_uri} does not match certificate application URI "
                f"{cert_application_uri}. Please provide the correct application URI via --application-uri "
                "or correct certificate using --public-key-file."
            )

        return cert_subject_name, cert_application_uri

    def _process_cert_content(
        self,
        file_path: str,
        file_name: str,
        expected_exts: set[str],
    ) -> Tuple[str, Union[x509.Certificate, x509.CertificateRevocationList]]:
        """
        Process the certificate content from the file, validate its extension,
        content format and if certificate expired, and return the certificate
        extension and decoded certificate object.
        """
        cert_extension = validate_file_extension(
            file_name,
            expected_exts,
        )
        # validate file content format by extension
        expected_content_format = (
            X509FileExtension.PEM.name if cert_extension == X509FileExtension.CRT.value else X509FileExtension.DER.name
        )
        certs = decode_x509_files(
            read_file_content(file_path, read_as_binary=True), expected_content_format, cert_extension
        )

        if not certs:
            raise InvalidArgumentValueError(
                f"Error decoding certificate from file '{file_name}'. Please make sure the file is "
                "a valid {expected_content_format} certificate."
            )

        # Only one certificate is expected in the PEM format.
        if expected_content_format == X509FileExtension.PEM.name and len(certs) > 1:
            raise InvalidArgumentValueError(
                f"Multiple certificates detected in file '{file_name}' in {expected_content_format} format. "
                f"Please provide a file with only one {expected_content_format} certificate."
            )
        cert = certs.pop()

        # check for certificate expiry
        if not cert_extension == X509FileExtension.CRL.value:
            # check if the certificate is expired
            expiry_date = self._extract_cert_expiration(cert)

            if expiry_date < datetime.now(timezone.utc):
                raise InvalidArgumentValueError(
                    f"Certificate in file '{file_name}' is expired. Please provide a valid certificate."
                )

        return cert_extension, cert

    def _is_cert_self_signed(self, cert: x509.Certificate) -> bool:
        # Check issuer and subject to determine if it's a self signed(non CA signed) certificate
        issuer = cert.issuer
        subject = cert.subject
        return issuer == subject

    def _is_ca_cert(
        self,
        cert: x509.Certificate,
    ) -> bool:
        # Check if it’s a CA cert
        from cryptography.x509.oid import ExtensionOID

        # this attribute only exist Version 3 of the X.509 standard
        basic_constraints: x509.BasicConstraints = cert.extensions.get_extension_for_oid(
            ExtensionOID.BASIC_CONSTRAINTS
        ).value

        if hasattr(basic_constraints, "ca"):
            # if the certificate is a CA certificate
            return basic_constraints.ca

        return False

    def _get_resource_by_name(
        self,
        resource_type: str,
        resource_name: str,
    ) -> Optional[dict]:
        """
        Get a specific resource by its name and type.
        """
        cl_resources = self.resource_map.connected_cluster.get_cl_resources_by_type(
            custom_location_id=self.extended_location["name"],
            resource_types={resource_type},
            show_properties=True,
        ).get(resource_type)

        if not cl_resources:
            return None

        resource = next((resource for resource in cl_resources if resource.get("name") == resource_name), {})

        # remove properties that are not accepted by ssc_mgmt_client
        if "apiVersion" in resource:
            del resource["apiVersion"]
        if "resourceGroup" in resource:
            del resource["resourceGroup"]

        return resource
