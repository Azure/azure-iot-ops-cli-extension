# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""
Connector template management provider.

This module provides functionality for managing connector templates in Azure IoT Operations.
Templates are created from connector metadata references (MCR for 1st-party connectors,
ACR for 3rd-party connectors), automatically populating connector-specific configuration
while allowing user customization of deployment parameters.
"""

import io
import json
import os
import re
import shutil
import tarfile
import tempfile
from typing import TYPE_CHECKING, List, Optional

from azure.cli.core.azclierror import (
    InvalidArgumentValueError,
    RequiredArgumentMissingError,
    ResourceNotFoundError,
    ValidationError,
    CLIInternalError,
)
from knack.log import get_logger
from rich.console import Console

from ..common import DEFAULT_REGISTRY_HOST
from ....util import assemble_nargs_to_dict
from ....util.common import should_continue_prompt
from ....util.az_client import wait_for_terminal_state
from ....util.oci_client import get_oci_client
from ....util.queryable import Queryable
from .instances import Instances

if TYPE_CHECKING:
    from ....vendor.clients.iotopsmgmt.operations import (
        AkriConnectorTemplateOperations,
    )

console = Console()
logger = get_logger(__name__)

DEFAULT_LOG_LEVEL = "info"

# Valid enum values
VALID_IMAGE_PULL_POLICIES = ["Always", "IfNotPresent", "Never"]
VALID_ALLOCATION_POLICIES = ["Bucketized"]


class ConnectorTemplates(Queryable):
    """Provider for connector template operations."""

    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.instances = Instances(cmd=cmd)
        self.iotops_mgmt_client = self.instances.iotops_mgmt_client
        self.ops: "AkriConnectorTemplateOperations" = (
            self.iotops_mgmt_client.akri_connector_template
        )

    def get_endpoint_version_for_type(
        self,
        instance_name: str,
        instance_resource_group: str,
        endpoint_type: str,
        is_custom_command: bool = False,
    ) -> Optional[str]:
        """
        Returns the endpoint version from a connector template if one exists for the endpoint type.

        Looks up connector templates for the specified instance and returns the version
        from the matching template's deviceInboundEndpointTypes. If multiple templates
        match the endpoint type, the one with the latest version is selected.

        For 1P commands (opcua, rest, mqtt, etc.), only MCR templates are considered.
        For custom commands (is_custom_command=True), only non-MCR (3P) templates are considered.

        Args:
            instance_name: IoT Operations instance name.
            instance_resource_group: Resource group containing the instance.
            endpoint_type: The device endpoint type (e.g., "Microsoft.OpcUa").
            is_custom_command: If True, this is the 'custom' command which should look for 3P templates.
                               If False, this is a 1P command (rest, opcua, etc.) which should look for MCR templates.

        Returns:
            The endpoint version string if found in a connector template, None otherwise.
        """
        from ....util.machinery import scoped_semver_import

        # Custom command always looks for 3P templates, 1P commands look for MCR templates
        look_for_mcr = not is_custom_command

        try:
            connector_templates = list(
                self.ops.list_by_instance_resource(
                    resource_group_name=instance_resource_group,
                    instance_name=instance_name,
                )
            )

            # Collect all matching templates with their versions
            # Each entry: (tag_version for comparison, endpoint_type_version to return, template_name)
            matching_templates = []

            for template in connector_templates:
                template_name = template.get("name")
                properties = template.get("properties", {})
                connector_metadata_ref = properties.get("connectorMetadataRef", "")
                device_endpoint_types = properties.get("deviceInboundEndpointTypes", [])

                # Filter templates based on whether we're looking for 1P (MCR) or 3P (non-MCR)
                is_mcr_template = connector_metadata_ref.startswith(DEFAULT_REGISTRY_HOST)
                if look_for_mcr and not is_mcr_template:
                    continue
                if not look_for_mcr and is_mcr_template:
                    continue

                # Get tag version from tagDigestSettings.tag (for comparison)
                runtime_config = properties.get("runtimeConfiguration", {})
                managed_config = runtime_config.get("managedConfigurationSettings", {})
                image_config = managed_config.get("imageConfigurationSettings", {})
                tag_settings = image_config.get("tagDigestSettings", {})
                tag_version = tag_settings.get("tag")

                if not tag_version:
                    continue

                for endpoint_type_info in device_endpoint_types:
                    et = endpoint_type_info.get("endpointType")
                    endpoint_type_version = endpoint_type_info.get("version")

                    # Match endpoint type (case-insensitive)
                    if et and et.lower() == endpoint_type.lower():
                        matching_templates.append((tag_version, endpoint_type_version, template_name))

            if not matching_templates:
                logger.info(
                    f"No connector template found for endpoint type '{endpoint_type}'. "
                    "Endpoint version will be None."
                )
                return None

            # If only one matching template, return its endpoint type version
            if len(matching_templates) == 1:
                tag_version, endpoint_type_version, template_name = matching_templates[0]
                logger.info(
                    f"Found endpoint version '{endpoint_type_version}' from connector template "
                    f"'{template_name}' (tag: {tag_version}) for endpoint type '{endpoint_type}'"
                )
                return endpoint_type_version

            # Multiple matching templates - compare using tag version to find the latest
            semver = scoped_semver_import()
            latest_tag_version = None
            latest_endpoint_type_version = None
            latest_template_name = None

            for tag_version, endpoint_type_version, template_name in matching_templates:
                try:
                    parsed_version = semver.parse(tag_version)
                    if latest_tag_version is None:
                        latest_tag_version = tag_version
                        latest_endpoint_type_version = endpoint_type_version
                        latest_template_name = template_name
                    elif parsed_version > semver.parse(latest_tag_version):
                        latest_tag_version = tag_version
                        latest_endpoint_type_version = endpoint_type_version
                        latest_template_name = template_name
                except (ValueError, AttributeError):
                    # If version can't be parsed, use as fallback
                    logger.debug(
                        f"Could not parse tag version '{tag_version}' from template '{template_name}' for comparison"
                    )
                    if latest_tag_version is None:
                        latest_tag_version = tag_version
                        latest_endpoint_type_version = endpoint_type_version
                        latest_template_name = template_name

            logger.info(
                f"Found {len(matching_templates)} matching templates for endpoint type '{endpoint_type}'. "
                f"Selected endpoint version '{latest_endpoint_type_version}' from template "
                f"'{latest_template_name}' (tag: {latest_tag_version}, latest)."
            )
            return latest_endpoint_type_version

        except Exception as e:
            logger.warning(f"Failed to retrieve connector templates: {e}. Endpoint version will be None.")
            return None

    def create(
        self,
        template_name: str,
        resource_group_name: str,
        instance_name: str,
        connector_metadata_ref: str,
        replicas: Optional[int] = None,
        log_level: Optional[str] = None,
        image_pull_policy: Optional[str] = None,
        image_pull_secrets: Optional[List[str]] = None,
        allocation_policy: Optional[str] = None,
        bucket_size: Optional[int] = None,
        secrets: Optional[List[str]] = None,
        storage_volumes: Optional[List[str]] = None,
        connector_config: Optional[List[str]] = None,
        trust_settings_secret_ref: Optional[str] = None,
    ) -> dict:
        """
        Create a new connector template.

        Args:
            template_name: Name of the template
            resource_group_name: Instance resource group name
            instance_name: IoT Operations instance name
            connector_metadata_ref: URL to connector metadata JSON
            replicas: Number of connector pod replicas
            log_level: Log level for connector pods
            image_pull_policy: Kubernetes image pull policy
            image_pull_secrets: List of Kubernetes secret names for image pulling
            allocation_policy: Device endpoint allocation policy
            bucket_size: Bucket size for Bucketized allocation policy (required when allocation_policy is Bucketized)
            secrets: Connector application secrets
            storage_volumes: Storage volumes configuration
            connector_config: Additional connector-specific configurations
            trust_settings_secret_ref: Secret reference for certificates to trust

        Returns:
            dict: Created connector template resource
        """
        # Fetch and parse connector metadata
        metadata = self._fetch_connector_metadata(connector_metadata_ref)
        logger.debug(f"Fetched metadata: {json.dumps(metadata, indent=2)}")

        # Validate required metadata fields
        self._validate_metadata(metadata, connector_metadata_ref)

        # Get extended location for the instance
        from ...adr.helpers import get_extended_location

        extended_location = get_extended_location(
            cmd=self.cmd,
            instance_name=instance_name,
            instance_resource_group=resource_group_name,
            instance_subscription=None,
        )
        # Remove fields that the API doesn't accept in the template resource
        extended_location.pop("cluster_location", None)
        extended_location.pop("namespace", None)

        # Build template properties from metadata and user inputs
        properties = self._build_template_properties(
            metadata=metadata,
            connector_metadata_ref=connector_metadata_ref,
            replicas=replicas,
            log_level=log_level,
            image_pull_policy=image_pull_policy,
            image_pull_secrets=image_pull_secrets,
            allocation_policy=allocation_policy,
            bucket_size=bucket_size,
            secrets=secrets,
            storage_volumes=storage_volumes,
            connector_config=connector_config,
            trust_settings_secret_ref=trust_settings_secret_ref,
        )

        # Validate secret sync is enabled if secrets are provided
        if secrets:
            self._check_secret_sync_enabled(
                instance_name=instance_name,
                resource_group_name=resource_group_name,
            )

        # Construct the template resource (location not allowed per API)
        template_resource = {
            "extendedLocation": extended_location,
            "properties": properties,
        }

        logger.info(
            "Creating connector template '%s' in instance '%s'",
            template_name,
            instance_name,
        )

        with console.status(f"Creating {template_name}..."):
            poller = self.ops.begin_create_or_update(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                akri_connector_template_name=template_name,
                resource=template_resource,
            )
            return wait_for_terminal_state(poller=poller, logger=logger)

    def update(  # noqa: C901
        self,
        template_name: str,
        resource_group_name: str,
        instance_name: str,
        connector_metadata_ref: Optional[str] = None,
        replicas: Optional[int] = None,
        log_level: Optional[str] = None,
        image_pull_policy: Optional[str] = None,
        image_pull_secrets: Optional[List[str]] = None,
        allocation_policy: Optional[str] = None,
        bucket_size: Optional[int] = None,
        secrets: Optional[List[str]] = None,
        storage_volumes: Optional[List[str]] = None,
        connector_config: Optional[List[str]] = None,
        trust_settings_secret_ref: Optional[str] = None,
    ) -> dict:
        """
        Update an existing connector template.

        Args:
            template_name: Name of the template
            resource_group_name: Azure resource group name
            instance_name: Azure IoT Operations instance name
            connector_metadata_ref: Optional new connector metadata URL
            replicas: Number of connector pod replicas
            log_level: Log level for connector pods
            image_pull_policy: Kubernetes image pull policy
            image_pull_secrets: List of Kubernetes secret names for image pulling
            allocation_policy: Device endpoint allocation policy
            bucket_size: Bucket size for Bucketized allocation policy (required when allocation_policy is Bucketized)
            secrets: Connector application secrets
            storage_volumes: Storage volumes configuration
            connector_config: Additional connector-specific configurations
            trust_settings_secret_ref: Secret reference for certificates to trust

        Returns:
            dict: Updated connector template resource
        """
        # Get existing template
        existing_template = self.show(
            template_name=template_name,
            resource_group_name=resource_group_name,
            instance_name=instance_name,
        )

        # If metadata ref is being updated, validate version upgrade
        if connector_metadata_ref:
            new_metadata = self._fetch_connector_metadata(connector_metadata_ref)

            # Extract current version from the existing template
            # Version is stored in tagDigestSettings.tag within imageConfigurationSettings
            runtime_config = existing_template["properties"]["runtimeConfiguration"]
            current_managed_config = runtime_config.get("managedConfigurationSettings", {})
            current_image_config = current_managed_config.get("imageConfigurationSettings", {})
            current_tag_settings = current_image_config.get("tagDigestSettings", {})
            current_version = current_tag_settings.get("tag", "0.0.0")
            new_version = new_metadata.get("version")

            if not self._is_valid_version_upgrade(current_version, new_version):
                raise ValidationError(
                    f"Invalid version upgrade from {current_version} to {new_version}. "
                    "Only patch and minor version updates are allowed. "
                    "Major version updates require creating a new template."
                )

            # Validate endpoint type matches
            # Endpoint type is stored in deviceInboundEndpointTypes[0].endpointType
            device_endpoint_types = existing_template["properties"].get("deviceInboundEndpointTypes", [])
            current_endpoint_type = device_endpoint_types[0].get("endpointType") if device_endpoint_types else None
            new_endpoint_type = (
                new_metadata.get("inboundEndpoints", [{}])[0].get("endpointType")
            )
            if current_endpoint_type and new_endpoint_type and current_endpoint_type != new_endpoint_type:
                raise ValidationError(
                    f"Endpoint type mismatch. Current: {current_endpoint_type}, "
                    f"New: {new_endpoint_type}. Cannot change endpoint type during update."
                )

            # Update image configuration settings from new metadata
            new_image_settings = new_metadata.get("imageConfigurationSettings", {})
            default_image = current_image_config.get("imageName", "")
            current_image_config["imageName"] = new_image_settings.get("imageName", default_image)

            # Update tag/digest settings
            if "tag" in new_image_settings:
                current_image_config["tagDigestSettings"] = {
                    "tagDigestType": "Tag",
                    "tag": new_image_settings["tag"]
                }
            elif "digest" in new_image_settings:
                current_image_config["tagDigestSettings"] = {
                    "tagDigestType": "Digest",
                    "digest": new_image_settings["digest"]
                }

            # Update aioMetadata if present
            if "aioMetadata" in new_metadata:
                existing_template["properties"]["aioMetadata"] = new_metadata["aioMetadata"]

            # Update deviceInboundEndpointTypes from metadata
            new_endpoint_types = []
            for endpoint in new_metadata.get("inboundEndpoints", []):
                endpoint_type_obj = {
                    "endpointType": endpoint.get("endpointType", "")
                }
                if "version" in endpoint:
                    endpoint_type_obj["version"] = endpoint["version"]
                new_endpoint_types.append(endpoint_type_obj)
            if new_endpoint_types:
                existing_template["properties"]["deviceInboundEndpointTypes"] = new_endpoint_types

            # Update connectorMetadataRef to store the metadata reference
            existing_template["properties"]["connectorMetadataRef"] = connector_metadata_ref

        # Update user-configurable properties
        # Access the managed configuration settings
        managed_config = existing_template["properties"]["runtimeConfiguration"].get("managedConfigurationSettings", {})
        image_config_settings = managed_config.get("imageConfigurationSettings", {})

        if replicas is not None:
            image_config_settings["replicas"] = replicas

        if log_level is not None:
            if "diagnostics" not in existing_template["properties"]:
                existing_template["properties"]["diagnostics"] = {"logs": {}}
            existing_template["properties"]["diagnostics"]["logs"]["level"] = log_level

        if image_pull_policy is not None:
            image_config_settings["imagePullPolicy"] = image_pull_policy

        if image_pull_secrets is not None:
            if self._is_clear_signal(image_pull_secrets):
                # Clear image pull secrets
                if "registrySettings" in image_config_settings:
                    if "containerRegistrySettings" in image_config_settings["registrySettings"]:
                        container_settings = image_config_settings["registrySettings"]["containerRegistrySettings"]
                        container_settings.pop("imagePullSecrets", None)
            else:
                # Ensure we have ContainerRegistry type settings
                if "registrySettings" not in image_config_settings:
                    image_config_settings["registrySettings"] = {
                        "registrySettingsType": "ContainerRegistry",
                        "containerRegistrySettings": {}
                    }
                if "containerRegistrySettings" not in image_config_settings["registrySettings"]:
                    image_config_settings["registrySettings"]["containerRegistrySettings"] = {}
                image_config_settings["registrySettings"]["containerRegistrySettings"]["imagePullSecrets"] = [
                    {"secretRef": secret} for secret in image_pull_secrets if secret
                ]

        if allocation_policy is not None or bucket_size is not None:
            # Normalize allocation policy if provided (case-insensitive)
            if allocation_policy is not None:
                normalized_policy = None
                for valid_policy in VALID_ALLOCATION_POLICIES:
                    if allocation_policy.lower() == valid_policy.lower():
                        normalized_policy = valid_policy
                        break

                if normalized_policy is None:
                    raise InvalidArgumentValueError(
                        f"Invalid allocation policy: {allocation_policy}. "
                        f"Valid values are: {', '.join(VALID_ALLOCATION_POLICIES)} (case-insensitive)"
                    )
                allocation_policy = normalized_policy

            # Get or create allocation dict
            if "allocation" not in managed_config:
                managed_config["allocation"] = {}

            allocation_dict = managed_config["allocation"]

            # Update allocation policy if provided
            if allocation_policy is not None:
                allocation_dict["policy"] = allocation_policy

            # Handle bucket size for Bucketized policy
            current_policy = allocation_dict.get("policy", "")
            if current_policy == "Bucketized" or (allocation_policy is not None and allocation_policy == "Bucketized"):
                # Use provided bucket size or fail if missing
                final_bucket_size = bucket_size

                if final_bucket_size is None and allocation_policy is not None:
                    # Bucket size is required when setting allocation policy to Bucketized
                    raise RequiredArgumentMissingError(
                        "Bucket size is required when allocation policy is 'Bucketized'. "
                        "Provide it via --bucket-size parameter."
                    )

                if final_bucket_size is not None:
                    allocation_dict["bucketSize"] = final_bucket_size

        if connector_config is not None:
            if self._is_clear_signal(connector_config):
                # Clear additional configuration
                managed_config.pop("additionalConfiguration", None)
            else:
                if "additionalConfiguration" not in managed_config:
                    managed_config["additionalConfiguration"] = {}
                managed_config["additionalConfiguration"].update(assemble_nargs_to_dict(connector_config))

        # Update secrets if provided (at managedConfigurationSettings level per API schema)
        if secrets is not None:
            is_clear = self._is_clear_signal(secrets) or (
                isinstance(secrets, list) and len(secrets) == 1 and self._is_clear_signal(secrets[0])
            )
            if is_clear:
                # Clear secrets
                managed_config.pop("secrets", None)
            else:
                # Validate secret sync is enabled
                self._check_secret_sync_enabled(
                    instance_name=instance_name,
                    resource_group_name=resource_group_name,
                )
                parsed_secrets = self._parse_secrets(secrets)
                if parsed_secrets:
                    managed_config["secrets"] = parsed_secrets

        # Update storage volumes if provided (at managedConfigurationSettings level per API schema)
        if storage_volumes is not None:
            if self._is_clear_signal(storage_volumes):
                # Clear persistent volume claims
                managed_config.pop("persistentVolumeClaims", None)
            else:
                parsed_volumes = self._parse_storage_volumes(storage_volumes)
                if parsed_volumes:
                    managed_config["persistentVolumeClaims"] = parsed_volumes

        # Update trust settings if provided
        if trust_settings_secret_ref is not None:
            if self._is_clear_signal(trust_settings_secret_ref):
                # Clear trust settings
                managed_config.pop("trustSettings", None)
            else:
                managed_config["trustSettings"] = {
                    "trustListSecretRef": trust_settings_secret_ref
                }

        logger.info(
            "Updating connector template '%s' in instance '%s'",
            template_name,
            instance_name,
        )

        with console.status(f"Updating {template_name}..."):
            poller = self.ops.begin_create_or_update(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                akri_connector_template_name=template_name,
                resource=existing_template,
            )
            return wait_for_terminal_state(poller=poller, logger=logger)

    def show(
        self,
        template_name: str,
        resource_group_name: str,
        instance_name: str,
    ) -> dict:
        """
        Display a connector template.

        Args:
            template_name: Name of the template
            resource_group_name: Azure resource group name
            instance_name: Azure IoT Operations instance name

        Returns:
            dict: Connector template resource
        """
        logger.info(
            "Retrieving connector template '%s' from instance '%s'",
            template_name,
            instance_name,
        )

        result = self.ops.get(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            akri_connector_template_name=template_name,
        )
        return result

    def delete(
        self,
        template_name: str,
        resource_group_name: str,
        instance_name: str,
        confirm_yes: bool = False,
        **kwargs,
    ) -> dict:
        """
        Delete a connector template.

        Args:
            template_name: Name of the template
            resource_group_name: Azure resource group name
            instance_name: Azure IoT Operations instance name
            confirm_yes: Skip confirmation prompt

        Returns:
            dict: Deletion result
        """
        # Check if template exists
        try:
            self.show(
                template_name=template_name,
                resource_group_name=resource_group_name,
                instance_name=instance_name,
            )
        except ResourceNotFoundError:
            raise

        # Confirm deletion
        should_bail = not should_continue_prompt(confirm_yes=confirm_yes)
        if should_bail:
            return

        logger.info(
            "Deleting connector template '%s' from instance '%s'",
            template_name,
            instance_name,
        )

        with console.status(f"Deleting {template_name}..."):
            poller = self.ops.begin_delete(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                akri_connector_template_name=template_name,
            )
            return wait_for_terminal_state(poller=poller, logger=logger, **kwargs)

    def list(
        self,
        resource_group_name: str,
        instance_name: str,
    ) -> List[dict]:
        """
        List all connector templates with summary information.

        Args:
            resource_group_name: Azure resource group name
            instance_name: Azure IoT Operations instance name

        Returns:
            List[dict]: List of connector template summaries with:
                - name: Template name
                - connectorType: Endpoint type (e.g., Microsoft.Http, Microsoft.Mqtt)
                - version: Connector version
                - replicas: Number of replicas configured
                - createdAt: Creation timestamp
                - lastModifiedAt: Last modification timestamp
                - provisioningState: Current provisioning state
        """
        logger.info(
            "Listing connector templates for instance '%s'",
            instance_name,
        )

        results = self.ops.list_by_instance_resource(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
        )

        summaries = []
        for template in results:
            summary = self._extract_template_summary(template)
            summaries.append(summary)

        return summaries

    # Helper methods

    def _extract_template_summary(self, template: dict) -> dict:
        """Extract summary information from a connector template resource.

        Args:
            template: Full connector template resource dict

        Returns:
            dict: Summary with key fields for list display
        """
        properties = template.get("properties", {})
        system_data = template.get("systemData", {})

        # Extract endpoint type from deviceInboundEndpointTypes
        endpoint_types = properties.get("deviceInboundEndpointTypes", [])
        connector_type = ""
        version = ""
        if endpoint_types:
            first_endpoint = endpoint_types[0]
            connector_type = first_endpoint.get("endpointType", "")
            version = first_endpoint.get("version", "")

        # Extract replicas and tag from runtime configuration
        runtime_config = properties.get("runtimeConfiguration", {})
        managed_settings = runtime_config.get("managedConfigurationSettings", {})
        image_settings = managed_settings.get("imageConfigurationSettings", {})
        replicas = image_settings.get("replicas", 1)

        # Get tag as version if endpoint version not specified
        if not version:
            tag_settings = image_settings.get("tagDigestSettings", {})
            version = tag_settings.get("tag", "")

        return {
            "name": template.get("name", ""),
            "connectorType": connector_type,
            "version": version,
            "replicas": replicas,
            "createdAt": system_data.get("createdAt", ""),
            "lastModifiedAt": system_data.get("lastModifiedAt", ""),
            "provisioningState": properties.get("provisioningState", ""),
        }

    @staticmethod
    def _is_clear_signal(value) -> bool:
        """Check if the value indicates user wants to clear the property.

        Azure CLI convention: Use '' (empty string) to clear list-type properties.
        This handles various forms the empty signal might come in.
        """
        if value is None:
            return False
        if isinstance(value, list):
            # Empty list or list with single empty string
            return len(value) == 0 or (len(value) == 1 and value[0] == "")
        if isinstance(value, str):
            return value == ""
        return False

    def _validate_metadata(self, metadata: dict, metadata_ref: str) -> None:
        """Validate required fields in connector metadata.

        Ensures the metadata contains all required fields for creating a valid
        connector template.

        Args:
            metadata: Parsed connector metadata JSON
            metadata_ref: Original metadata reference URL (for error messages)

        Raises:
            ValidationError: If required fields are missing
        """
        required_fields = ["name", "version", "imageConfigurationSettings", "inboundEndpoints"]
        missing_fields = []

        for field in required_fields:
            if field not in metadata or not metadata[field]:
                missing_fields.append(field)

        if missing_fields:
            raise ValidationError(
                f"Connector metadata at '{metadata_ref}' is missing required fields: "
                f"{', '.join(missing_fields)}. Please ensure the metadata JSON includes: "
                "name, version, imageConfigurationSettings, and inboundEndpoints."
            )

        # Validate imageConfigurationSettings has required subfields
        image_config = metadata.get("imageConfigurationSettings", {})
        if not image_config.get("imageName"):
            raise ValidationError(
                f"Connector metadata at '{metadata_ref}' is missing 'imageConfigurationSettings.imageName'. "
                "This field is required to specify the connector image path."
            )

    def _fetch_connector_metadata(self, metadata_ref: str) -> dict:
        """
        Fetch connector metadata from the registry using OciRegistryClient.

        Handles both public registries (MCR) and private registries (ACR).
        For MCR (1st-party connectors): Uses anonymous access
        For ACR (3rd-party connectors): Uses Azure AD authentication

        The metadata artifact uses format: {connector-type}-metadata:{version}
        For example: mcr.microsoft.com/azureiotoperations/akri-connectors/rest-metadata:1.0.6

        Args:
            metadata_ref: Registry reference in format registry/path/{type}-metadata:{version}

        Returns:
            dict: Parsed connector metadata JSON

        Raises:
            RequiredArgumentMissingError: If metadata_ref is empty
            InvalidArgumentValueError: If metadata_ref format is invalid
        """
        # Validate metadata reference format
        if not metadata_ref:
            raise RequiredArgumentMissingError(
                "Connector metadata reference is required."
            )

        pattern = r"^[a-zA-Z0-9\-\.]+/[\w\-\./]+-metadata:[a-zA-Z0-9\.\-_]+$"
        if not re.match(pattern, metadata_ref):
            raise InvalidArgumentValueError(
                f"Invalid connector metadata reference format: {metadata_ref}. "
                "Expected format: registry.com/path/connector-type-metadata:version"
            )

        logger.info(f"Fetching connector metadata from: {metadata_ref}")

        try:
            # Use OciRegistryClient to fetch the first layer (metadata blob)
            oci_client = get_oci_client()
            artifact_info = oci_client.fetch_first_layer(
                image_ref=metadata_ref,
                cmd=self.cmd,
            )

            # Extract metadata from the blob content
            return self._parse_metadata_blob(artifact_info.content, metadata_ref)

        except ValidationError:
            # Re-raise validation errors from OciRegistryClient
            raise
        except Exception as e:
            if isinstance(e, (ValidationError, InvalidArgumentValueError, CLIInternalError)):
                raise
            logger.debug(f"Unexpected error fetching metadata: {str(e)}")
            raise CLIInternalError(
                f"Failed to fetch connector metadata from {metadata_ref}: {str(e)}"
            )

    def _parse_metadata_blob(self, blob_content: bytes, metadata_ref: str) -> dict:
        """
        Parse connector metadata from blob content.

        Handles multiple formats:
        - Direct JSON content
        - tar.gz archive containing connector-metadata.json
        - tar archive containing connector-metadata.json

        Args:
            blob_content: Raw blob content from registry
            metadata_ref: Original metadata reference (for error messages)

        Returns:
            dict: Parsed connector metadata JSON
        """
        logger.debug(f"Parsing metadata blob, size: {len(blob_content)} bytes")

        # First, check if it's already a JSON file
        try:
            metadata = json.loads(blob_content.decode('utf-8'))
            if "name" in metadata:
                logger.info(f"Blob is already JSON metadata for connector: {metadata.get('name')}")
                return metadata
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        # Try to extract from tar archive
        temp_dir = tempfile.mkdtemp(prefix="akri_metadata_")

        try:
            # Try to extract as tar.gz
            try:
                logger.debug("Attempting to extract as tar.gz")
                with tarfile.open(fileobj=io.BytesIO(blob_content), mode="r:gz") as tar:
                    tar.extractall(temp_dir)
            except (tarfile.ReadError, OSError):
                # Try as plain tar
                try:
                    logger.debug("tar.gz failed, attempting to extract as plain tar")
                    with tarfile.open(fileobj=io.BytesIO(blob_content), mode="r") as tar:
                        tar.extractall(temp_dir)
                except (tarfile.ReadError, OSError) as e:
                    raise CLIInternalError(
                        f"Failed to extract artifact from {metadata_ref}. "
                        f"The blob format is not recognized (not JSON, tar, or tar.gz): {str(e)}"
                    )

            # Find connector-metadata.json
            metadata_file = None
            for root, _dirs, files in os.walk(temp_dir):
                for file in files:
                    if file == "connector-metadata.json":
                        metadata_file = os.path.join(root, file)
                        break
                if metadata_file:
                    break

            if not metadata_file:
                raise CLIInternalError(
                    f"Could not find connector-metadata.json in artifact from {metadata_ref}"
                )

            # Read and parse metadata
            logger.debug(f"Reading metadata from {metadata_file}")
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

            logger.info(f"Successfully fetched metadata for connector: {metadata.get('name', 'unknown')}")
            return metadata

        finally:
            # Clean up
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    def _split_image_reference(self, metadata_ref: str) -> tuple:
        """Split image reference into registry and image name.

        Expected format: registry/path/{type}-metadata:{version}
        Returns: (registry, image_name)

        Examples:
            mcr.microsoft.com/azureiotoperations/akri-connectors/rest-metadata:1.0.6
            -> ('mcr.microsoft.com', 'azureiotoperations/akri-connectors/rest')

            acrname.azurecr.io/connectors/test-metadata:1.0.0
            -> ('acrname.azurecr.io', 'connectors/test')
        """
        try:
            # Remove the tag portion first
            without_tag = metadata_ref.split(":")[0]
            # Remove -metadata suffix
            if without_tag.endswith("-metadata"):
                without_tag = without_tag[:-len("-metadata")]

            # Split into registry and image path
            # Registry is the first part before the first /
            parts = without_tag.split("/", 1)
            if len(parts) == 2:
                registry = parts[0]
                image_name = parts[1]
            else:
                # No registry specified (shouldn't happen but handle it)
                registry = ""
                image_name = without_tag

            return (registry, image_name)
        except Exception:
            # Fallback: return empty registry and full ref as image name
            return ("", metadata_ref)

    def _is_valid_version_upgrade(
        self, current_version: str, new_version: str
    ) -> bool:
        """
        Validate if version upgrade is allowed.

        Allows:
        - Patch updates: 1.0.5 -> 1.0.6
        - Minor updates: 1.0.6 -> 1.1.0

        Blocks:
        - Major updates: 1.0.6 -> 2.0.0
        - Downgrades: 1.0.6 -> 1.0.5
        """
        from ....util.machinery import scoped_semver_import

        try:
            semver = scoped_semver_import()
            current_semver = semver.parse(current_version)
            new_semver = semver.parse(new_version)

            # Block major version changes
            if new_semver.major != current_semver.major:
                return False

            # Block downgrades (but allow same version for re-applying metadata ref)
            if new_semver < current_semver:
                return False

            return True

        except (ValueError, AttributeError):
            logger.warning(
                "Could not parse versions for comparison: %s -> %s",
                current_version,
                new_version,
            )
            return False

    def _build_template_properties(  # noqa: C901
        self,
        metadata: dict,
        connector_metadata_ref: str,
        replicas: Optional[int],
        log_level: Optional[str],
        image_pull_policy: Optional[str],
        image_pull_secrets: Optional[List[str]],
        allocation_policy: Optional[str],
        bucket_size: Optional[int],
        secrets: Optional[List[str]],
        storage_volumes: Optional[List[str]],
        connector_config: Optional[List[str]],
        trust_settings_secret_ref: Optional[str] = None,
    ) -> dict:
        """Build template properties from metadata and user inputs matching API schema.

        Args:
            metadata: Parsed connector metadata JSON
            connector_metadata_ref: URL to connector metadata reference
            replicas: Number of connector pod replicas
            log_level: Log level for connector pods
            image_pull_policy: Kubernetes image pull policy
            image_pull_secrets: List of Kubernetes secret names for image pulling
            allocation_policy: Device endpoint allocation policy
            bucket_size: Bucket size for Bucketized allocation policy
            secrets: Connector application secrets
            storage_volumes: Storage volumes configuration
            connector_config: Additional connector-specific configurations
            trust_settings_secret_ref: Secret reference for certificates to trust

        Returns:
            dict: Template properties structure
        """
        # Normalize and validate image pull policy (case-insensitive)
        if image_pull_policy is not None:
            # Find matching policy case-insensitively
            normalized_policy = None
            for valid_policy in VALID_IMAGE_PULL_POLICIES:
                if image_pull_policy.lower() == valid_policy.lower():
                    normalized_policy = valid_policy
                    break

            if normalized_policy is None:
                raise InvalidArgumentValueError(
                    f"Invalid image pull policy: {image_pull_policy}. "
                    f"Valid values are: {', '.join(VALID_IMAGE_PULL_POLICIES)} (case-insensitive)"
                )
            image_pull_policy = normalized_policy

        # Normalize and validate allocation policy (case-insensitive)
        if allocation_policy is not None:
            # Find matching policy case-insensitively
            normalized_policy = None
            for valid_policy in VALID_ALLOCATION_POLICIES:
                if allocation_policy.lower() == valid_policy.lower():
                    normalized_policy = valid_policy
                    break

            if normalized_policy is None:
                raise InvalidArgumentValueError(
                    f"Invalid allocation policy: {allocation_policy}. "
                    f"Valid values are: {', '.join(VALID_ALLOCATION_POLICIES)} (case-insensitive)"
                )
            allocation_policy = normalized_policy

        # Extract image settings from metadata
        registry, image_name = self._split_image_reference(connector_metadata_ref)
        image_tag = metadata.get("version", "")

        # Build image configuration settings
        # API expects imageName WITHOUT registry reference
        image_config_settings = {
            "imageName": image_name,
            "tagDigestSettings": {
                "tagDigestType": "Tag",
                "tag": image_tag
            }
        }

        # Add registry settings if we have a registry
        if registry:
            # Use ContainerRegistry type with the registry URL
            registry_settings = {
                "registrySettingsType": "ContainerRegistry",
                "containerRegistrySettings": {
                    "registry": registry
                }
            }

            # Add image pull secrets if provided (optional)
            if image_pull_secrets:
                registry_settings["containerRegistrySettings"]["imagePullSecrets"] = [
                    {"secretRef": secret} for secret in image_pull_secrets
                ]

            image_config_settings["registrySettings"] = registry_settings

        # Set replicas if provided or use metadata recommendation
        if replicas is not None:
            image_config_settings["replicas"] = replicas
        elif "recommendedReplicas" in metadata:
            image_config_settings["replicas"] = metadata["recommendedReplicas"]

        # Set image pull policy if provided
        if image_pull_policy is not None:
            image_config_settings["imagePullPolicy"] = image_pull_policy

        # Build managed configuration settings
        managed_config = {
            "managedConfigurationType": "ImageConfiguration",
            "imageConfigurationSettings": image_config_settings
        }

        # Add allocation policy only if explicitly provided by user
        allocation_dict = {}
        if allocation_policy is not None:
            allocation_dict["policy"] = allocation_policy

            # Add bucketSize if policy is Bucketized
            if allocation_policy == "Bucketized":
                if bucket_size is None:
                    # Bucket size is required when allocation policy is Bucketized
                    raise RequiredArgumentMissingError(
                        "Bucket size is required when allocation policy is 'Bucketized'. "
                        "Provide it via --bucket-size parameter."
                    )

                allocation_dict["bucketSize"] = bucket_size

        if allocation_dict:
            managed_config["allocation"] = allocation_dict

        # Add additional configuration if provided
        if connector_config:
            connector_config_dict = assemble_nargs_to_dict(connector_config)
            managed_config["additionalConfiguration"] = connector_config_dict

        # Parse and add secrets if provided (at managedConfigurationSettings level per API schema)
        if secrets:
            parsed_secrets = self._parse_secrets(secrets)
            if parsed_secrets:
                managed_config["secrets"] = parsed_secrets

        # Parse and add storage volumes if provided (at managedConfigurationSettings level per API schema)
        if storage_volumes:
            parsed_volumes = self._parse_storage_volumes(storage_volumes)
            if parsed_volumes:
                managed_config["persistentVolumeClaims"] = parsed_volumes

        # Add trust settings if provided
        if trust_settings_secret_ref:
            managed_config["trustSettings"] = {
                "trustListSecretRef": trust_settings_secret_ref
            }

        # Build runtime configuration
        runtime_config = {
            "runtimeConfigurationType": "ManagedConfiguration",
            "managedConfigurationSettings": managed_config
        }

        # Build device inbound endpoint types from metadata
        device_endpoint_types = []
        inbound_endpoints = metadata.get("inboundEndpoints", [])
        for endpoint in inbound_endpoints:
            endpoint_type_obj = {
                "endpointType": endpoint.get("endpointType", "")
            }
            # Add version if available
            if "version" in endpoint:
                endpoint_type_obj["version"] = endpoint["version"]
            # Add configuration schema refs if available
            if "configurationSchemaRefs" in endpoint:
                endpoint_type_obj["configurationSchemaRefs"] = endpoint["configurationSchemaRefs"]
            device_endpoint_types.append(endpoint_type_obj)

        # Build diagnostics settings
        diagnostics = {
            "logs": {
                "level": log_level if log_level is not None else DEFAULT_LOG_LEVEL
            }
        }

        # Build aioMetadata
        aio_metadata = metadata.get("aioMetadata", {})

        # Assemble complete properties
        properties = {
            "connectorMetadataRef": connector_metadata_ref,
            "runtimeConfiguration": runtime_config,
            "deviceInboundEndpointTypes": device_endpoint_types,
            "aioMetadata": aio_metadata,
            "diagnostics": diagnostics
        }

        return properties

    def _parse_secrets(self, secrets_list: List[str]) -> List[dict]:
        """Parse secrets from CLI argument format to structured format.

        Expected format: secretRef=mySecret secretKey=password secretAlias=dbPassword

        Validates:
        - secretRef: Azure Key Vault secret name (1-127 chars, alphanumeric and hyphens)
        - secretKey: Key within the secret (alphanumeric, underscores, hyphens)
        - secretAlias: Application alias (alphanumeric, underscores, hyphens)
        - Uniqueness of secretAlias within the list
        - Uniqueness of secretKey within the list (to avoid mount path conflicts)
        - All secrets must use the same secretRef (single Secret Provider Class)

        Args:
            secrets_list: List of secret definitions. With action="append", this is a list of lists
                         where each inner list contains key=value pairs for one secret.
                         For backward compatibility, also handles flat list of key=value pairs.

        Returns:
            List of secret dictionaries with secretRef, secretKey, and secretAlias
        """
        import re

        if not secrets_list:
            return []
        # Validation patterns
        # Pattern: ^[0-9a-zA-Z-]+$ (alphanumeric and hyphens only)
        # Length: 1-127 characters (practical Azure naming convention limit)
        secret_ref_pattern = re.compile(r'^[0-9a-zA-Z-]{1,127}$')
        # Keys and aliases: application-level identifiers, using safe character set
        # (alphanumeric, underscores, hyphens)
        identifier_pattern = re.compile(r'^[a-zA-Z0-9_-]+$')

        parsed_secrets = []
        seen_aliases = set()
        seen_secret_keys = set()
        secret_ref_values = set()

        # Handle both list of lists (from action="append") and flat list (backward compatibility)
        # If first item is a list, we have action="append" format
        if secrets_list and isinstance(secrets_list[0], list):
            # List of lists - each inner list is one secret definition
            secret_groups = secrets_list
        else:
            # Flat list - treat entire list as one secret definition
            secret_groups = [secrets_list]

        for secret_group in secret_groups:
            # Handle case where user wrapped everything in quotes:
            # "secretRef=x secretKey=y secretAlias=z" becomes a single string
            # We need to split it by spaces to get individual key=value pairs
            if len(secret_group) == 1 and ' ' in secret_group[0]:
                # Single string with spaces - split it
                secret_group = secret_group[0].split()

            secret_dict = assemble_nargs_to_dict(secret_group)

            # Validate required fields
            secret_ref = secret_dict.get("secretRef", "").strip()
            secret_key = secret_dict.get("secretKey", "").strip()
            secret_alias = secret_dict.get("secretAlias", "").strip()

            if not secret_ref:
                raise RequiredArgumentMissingError(
                    "secretRef is required for each secret. "
                    "Format: secretRef=mySecret secretKey=password secretAlias=dbPassword"
                )
            if not secret_key:
                raise RequiredArgumentMissingError(
                    "secretKey is required for each secret. "
                    "Format: secretRef=mySecret secretKey=password secretAlias=dbPassword"
                )
            if not secret_alias:
                raise RequiredArgumentMissingError(
                    "secretAlias is required for each secret. "
                    "Format: secretRef=mySecret secretKey=password secretAlias=dbPassword"
                )

            # Validate format
            if not secret_ref_pattern.match(secret_ref):
                raise InvalidArgumentValueError(
                    f"Invalid secretRef '{secret_ref}'. Must be 1-127 characters, "
                    "alphanumeric and hyphens only (Azure Key Vault secret name format)."
                )

            if not identifier_pattern.match(secret_key):
                raise InvalidArgumentValueError(
                    f"Invalid secretKey '{secret_key}'. Must contain only "
                    "alphanumeric characters, underscores, and hyphens."
                )

            if not identifier_pattern.match(secret_alias):
                raise InvalidArgumentValueError(
                    f"Invalid secretAlias '{secret_alias}'. Must contain only "
                    "alphanumeric characters, underscores, and hyphens."
                )

            # Check for duplicate aliases (each alias must be unique to avoid env var conflicts)
            if secret_alias in seen_aliases:
                raise InvalidArgumentValueError(
                    f"Duplicate secretAlias '{secret_alias}'. Each alias must be unique within the template."
                )
            seen_aliases.add(secret_alias)

            # Check for duplicate secretKey values (each key must be unique to avoid mount path conflicts)
            if secret_key in seen_secret_keys:
                raise InvalidArgumentValueError(
                    f"Duplicate secretKey '{secret_key}'. Each secretKey must be unique within the template. "
                    "Using the same secretKey multiple times causes conflicting mount paths in the pod."
                )
            seen_secret_keys.add(secret_key)

            # Track secretRef values and ensure all are the same (single Secret Provider Class)
            secret_ref_values.add(secret_ref)
            if len(secret_ref_values) > 1:
                raise InvalidArgumentValueError(
                    f"All secrets must use the same secretRef value. "
                    f"Found multiple values: {', '.join(sorted(secret_ref_values))}. "
                    "All secrets must reference the same Kubernetes secret created by the Secret Provider Class."
                )

            parsed_secrets.append(
                {
                    "secretRef": secret_ref,
                    "secretKey": secret_key,
                    "secretAlias": secret_alias,
                }
            )
        return parsed_secrets

    def _parse_storage_volumes(self, volumes_list: List[str]) -> List[dict]:
        """Parse storage volumes from CLI argument format to structured format.

        Expected format: claimName=myPVC mountPath=/data

        Returns persistent volume claim references matching API schema:
        {
            "claimName": "str",  # Name of the PersistentVolumeClaim
            "mountPath": "str"   # Mount path in the container
        }
        """
        if not volumes_list:
            return []

        parsed_volumes = []
        for volume_str in volumes_list:
            # Handle case where user wrapped everything in quotes:
            # "claimName=x mountPath=y" becomes a single string
            # We need to split it by spaces to get individual key=value pairs
            if isinstance(volume_str, str) and ' ' in volume_str and '=' in volume_str:
                # Single string with spaces - split it
                volume_parts = volume_str.split()
            else:
                volume_parts = [volume_str] if isinstance(volume_str, str) else volume_str

            volume_dict = assemble_nargs_to_dict(volume_parts)
            claim_name = volume_dict.get("claimName", "").strip()
            mount_path = volume_dict.get("mountPath", "").strip()

            if not claim_name:
                raise RequiredArgumentMissingError(
                    "claimName is required for each storage volume. "
                    "Format: claimName=myPVC mountPath=/data"
                )
            if not mount_path:
                raise RequiredArgumentMissingError(
                    "mountPath is required for each storage volume. "
                    "Format: claimName=myPVC mountPath=/data"
                )

            parsed_volumes.append(
                {
                    "claimName": claim_name,
                    "mountPath": mount_path,
                }
            )
        return parsed_volumes

    def _check_secret_sync_enabled(
        self,
        instance_name: str,
        resource_group_name: str,
    ) -> None:
        """Check if secret sync is enabled and fail if not.

        Secrets require secret sync to be enabled on the instance. This method
        validates that the instance has a defaultSecretProviderClassRef configured.

        Args:
            instance_name: Name of the IoT Operations instance
            resource_group_name: Resource group name

        Raises:
            ValidationError: If secret sync is not enabled on the instance
        """
        # get_default_spc raises ValidationError if secret sync is not enabled
        self.instances.get_default_spc(
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )
