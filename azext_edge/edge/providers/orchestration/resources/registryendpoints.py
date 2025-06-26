# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import asyncio
from collections import defaultdict
from typing import TYPE_CHECKING, Iterable, Optional

from azure.cli.core.azclierror import MutuallyExclusiveArgumentError, RequiredArgumentMissingError
from knack.log import get_logger
from rich.console import Console

from ....util.az_client import wait_for_terminal_state
from ....util.common import should_continue_prompt
from ....util.queryable import Queryable
from ..common import (
    DATAFLOW_GRAPH_ANNOTATION_DESCRIPTION,
    DATAFLOW_GRAPH_ANNOTATION_DISPLAY_NAME,
    DATAFLOW_GRAPH_MEDIA_TYPE,
    REGISTRY_ENDPOINT_AUTHENTICATION_OPTIONAL_PARAMS,
    REGISTRY_ENDPOINT_AUTHENTICATION_PARAM_TEXT_MAP,
    REGISTRY_ENDPOINT_AUTHENTICATION_REQUIRED_PARAMS,
    REGISTRY_ENDPOINT_AUTHENTICATION_TYPE_SETTINGS,
    RegistryEndpointAuthenticationType,
)
from .instances import Instances

logger = get_logger(__name__)

console = Console()


if TYPE_CHECKING:
    from ....vendor.clients.iotopsmgmt.operations import RegistryEndpointOperations


class RegistryEndpoints(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.instances = Instances(cmd=cmd)
        self.iotops_mgmt_client = self.instances.iotops_mgmt_client
        self.registry_endpoints: "RegistryEndpointOperations" = self.iotops_mgmt_client.registry_endpoint

    def list(self, instance_name: str, resource_group_name: str) -> Iterable[dict]:
        """
        List all registry endpoints for the IoT Operations instance.

        :param instance_name: Name of the IoT Operations instance.
        :param resource_group_name: Name of the resource group.
        :return: Iterable of registry endpoint dictionaries.
        :rtype: Iterable[dict]
        """
        return self.registry_endpoints.list_by_instance_resource(
            resource_group_name=resource_group_name, instance_name=instance_name
        )

    def show(self, instance_name: str, resource_group_name: str, registry_endpoint_name: str) -> dict:
        """
        Get a specific registry endpoint for the IoT Operations instance.

        :param instance_name: Name of the IoT Operations instance.
        :param resource_group_name: Name of the resource group.
        :param registry_endpoint_name: Name of the registry endpoint to retrieve.
        :return: The registry endpoint dictionary.
        :rtype: dict
        """
        return self.registry_endpoints.get(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            registry_endpoint_name=registry_endpoint_name,
        )

    def list_dataflow_graphs(
        self,
        instance_name: str,
        resource_group_name: str,
    ) -> Iterable[dict]:
        """
        List available images from a specific registry endpoint.

        :param instance_name: Name of the IoT Operations instance.
        :param resource_group_name: Name of the resource group.
        :return: Iterable of image dictionaries."""
        from azure.cli.core._profile import Profile
        from azure.containerregistry import ContainerRegistryClient

        profile = Profile(cli_ctx=self.cmd.cli_ctx)
        credential, _, _ = profile.get_login_credentials()

        # Get the registry endpoints for the instance
        endpoints = self.registry_endpoints.list_by_instance_resource(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
        )
        graphs = defaultdict(dict)

        with console.status("Working...") as ctx:
            for registry_endpoint in endpoints:
                endpoint_name = registry_endpoint.get("name", "unknown")
                host = registry_endpoint.get("properties", {}).get("host")
                if not host:
                    logger.warning(f"Registry endpoint '{endpoint_name}' does not have a valid host.")
                    continue

                # Validate host format
                hostname = host.replace("https://", "")
                if not hostname.endswith(".azurecr.io"):
                    logger.warning(f"Invalid ACR host format: {host}")
                    continue

                try:
                    ctx.update(f"Collecting images from {hostname}...")

                    # Create Container Registry client
                    registry_url = f"https://{hostname}"
                    client = ContainerRegistryClient(endpoint=registry_url, credential=credential)

                    # Get all images in the container registry
                    images = list(client.list_repository_names())

                    async def find_dataflow_images():

                        # Check if each tag manifest is a dataflow graph
                        async def process_tag_manifest_async(image, tag):
                            """Process a single tag manifest asynchronously"""
                            try:
                                # Get the actual manifest content to check media type
                                manifest = await asyncio.to_thread(client.get_manifest, image, tag)

                                # Check if this is a dataflow graph by config media type
                                manifest_obj = manifest.manifest
                                manifest_config = manifest_obj.get("config", {})
                                media_type = manifest_config.get("mediaType", manifest.media_type)

                                if media_type == DATAFLOW_GRAPH_MEDIA_TYPE:
                                    # annotations = manifest_obj.get("annotations", {})
                                    return {
                                        "host": host,
                                        "digest": manifest.digest,
                                        "manifest": manifest_obj,
                                        "image": f"{image}:{tag}",
                                        # "name": annotations.get(DATAFLOW_GRAPH_ANNOTATION_DISPLAY_NAME, ""),
                                        # "description": annotations.get(DATAFLOW_GRAPH_ANNOTATION_DESCRIPTION, ""),
                                    }
                                return None
                            except Exception as e:
                                logger.warning(f"Failed to get manifest for {image}:{tag} in {host}: {e}")
                                return None

                        # Get all tags for an image
                        async def get_tags_for_image(image):
                            try:
                                tags = await asyncio.to_thread(
                                    lambda: [tag.name for tag in client.list_tag_properties(image)]
                                )
                                return [(image, tag_name) for tag_name in tags]
                            except Exception as e:
                                logger.warning(f"Failed to list tags for image '{image}' in registry '{host}': {e}")
                                return []

                        tag_lists = await asyncio.gather(
                            *[get_tags_for_image(image) for image in images], return_exceptions=True
                        )

                        all_tag_tasks = []
                        for tag_list in tag_lists:
                            if isinstance(tag_list, Exception):
                                logger.warning(f"Failed to collect tags: {tag_list}")
                                continue
                            all_tag_tasks.extend(tag_list)

                        if not all_tag_tasks:
                            logger.info(f"No tags found for any images in registry {hostname}")
                            return {}

                        dataflow_image_results = await asyncio.gather(
                            *[process_tag_manifest_async(image, tag) for image, tag in all_tag_tasks],
                            return_exceptions=True,
                        )

                        dataflow_images = []
                        for dataflow_image in dataflow_image_results:
                            if isinstance(dataflow_image, Exception):
                                logger.warning(f"Task failed with exception: {dataflow_image}")
                                continue

                            if dataflow_image:
                                dataflow_images.append(dataflow_image)

                        return dataflow_images

                    images = asyncio.run(find_dataflow_images())

                    if not images:
                        logger.info(f"No dataflow graphs found in registry {hostname}")
                        continue
                    graphs[hostname] = images

                except Exception as e:
                    logger.error(f"Failed to list images for registry endpoint '{endpoint_name}': {e}")
                    continue

        return graphs

    def _process_registry_endpoint_authentication(
        self,
        type: Optional[RegistryEndpointAuthenticationType] = None,
        secret_ref: Optional[str] = None,
        audience: Optional[str] = None,
        client_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> dict:
        """
        Process the authentication type for the registry endpoint.
        If the type is not provided, it will be determined based on the provided authentication settings.

        :param type: The type of authentication for the registry endpoint.
        :param secret_ref: Reference to the secret for authentication.
        :param audience: Audience for the authentication.
        :param client_id: Client ID for the authentication.
        :param tenant_id: Tenant ID for the authentication.
        :param scope: Scope for the authentication.
        :returns: The authentication configuration dictionary.
        :raises RequiredArgumentMissingError: If required parameters are missing for the authentication type.
        :raises MutuallyExclusiveArgumentError: If parameters from different authentication types are provided.
        """

        # Determine authentication type if not provided
        if type is None:
            type = self._identify_authentication_method(
                secret_ref=secret_ref,
                audience=audience,
                client_id=client_id,
                tenant_id=tenant_id,
                scope=scope,
            )

        # Validate required / mutually exclusive parameters
        self._validate_authentication_parameters(
            auth_type=type,
            secret_ref=secret_ref,
            audience=audience,
            client_id=client_id,
            tenant_id=tenant_id,
            scope=scope,
        )

        # Build authentication configuration
        auth_config = {"method": type.value}

        # Add type-specific settings
        settings_key = REGISTRY_ENDPOINT_AUTHENTICATION_TYPE_SETTINGS[type.value]
        auth_settings = {}

        if type == RegistryEndpointAuthenticationType.ANONYMOUS:
            # Anonymous settings is an empty object
            auth_settings = {}
        elif type == RegistryEndpointAuthenticationType.ARTIFACTPULLSECRET:
            auth_settings = {"secretRef": secret_ref}
        elif type == RegistryEndpointAuthenticationType.SYSTEMASSIGNED:
            if audience:
                auth_settings["audience"] = audience
        elif type == RegistryEndpointAuthenticationType.USERASSIGNED:
            auth_settings["clientId"] = client_id
            auth_settings["tenantId"] = tenant_id
            if scope:
                auth_settings["scope"] = scope

        auth_config[settings_key] = auth_settings
        return auth_config

    # TODO - support for trusted_signing_key / configmap property
    def add(
        self,
        instance_name: str,
        resource_group_name: str,
        registry_endpoint_name: str,
        host: str,
        auth_type: Optional[RegistryEndpointAuthenticationType] = None,
        secret_ref: Optional[str] = None,
        audience: Optional[str] = None,
        client_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        scope: Optional[str] = None,
        **kwargs,
    ) -> dict:
        """
        Add a registry endpoint to an IoT Operations instance.

        :param instance_name: Name of the IoT Operations instance.
        :param resource_group_name: Name of the resource group.
        :param registry_endpoint_name: Name of the registry endpoint to create or update.
        :param host: The Container Registry endpoint hostname.
        :param auth_type: The type of authentication for the registry endpoint.
        :param secret_ref: Reference to the secret for ArtifactPullSecret authentication.
        :param audience: Audience for SystemAssignedManagedIdentity authentication.
        :param client_id: Client ID for UserAssignedManagedIdentity authentication.
        :param tenant_id: Tenant ID for UserAssignedManagedIdentity authentication.
        :param scope: Scope for UserAssignedManagedIdentity authentication.
        :param kwargs: Additional keyword arguments for the operation.
        :returns: The created registry endpoint.
        """
        # Process authentication configuration
        auth_config = self._process_registry_endpoint_authentication(
            type=auth_type,
            secret_ref=secret_ref,
            audience=audience,
            client_id=client_id,
            tenant_id=tenant_id,
            scope=scope,
        )

        # Build the resource configuration
        resource = {
            "extendedLocation": self.instances.get_ext_loc(
                name=instance_name,
                resource_group_name=resource_group_name,
            ),
            "properties": {
                "host": host,
                "authentication": auth_config,
            },
        }

        with console.status("Working..."):
            poller = self.registry_endpoints.begin_create_or_update(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                registry_endpoint_name=registry_endpoint_name,
                registry_endpoint=resource,
            )
            return wait_for_terminal_state(poller, **kwargs)

    # TODO - support for trusted_signing_key / configmap property
    def update(
        self,
        instance_name: str,
        resource_group_name: str,
        registry_endpoint_name: str,
        host: Optional[str] = None,
        auth_type: Optional[RegistryEndpointAuthenticationType] = None,
        secret_ref: Optional[str] = None,
        audience: Optional[str] = None,
        client_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        scope: Optional[str] = None,
        **kwargs,
    ) -> dict:
        """
        Update an existing registry endpoint in an IoT Operations instance.

        :param instance_name: Name of the IoT Operations instance.
        :param resource_group_name: Name of the resource group.
        :param registry_endpoint_name: Name of the registry endpoint to update.
        :param host: The Container Registry endpoint hostname.
        :param auth_type: The type of authentication for the registry endpoint.
        :param secret_ref: Reference to the secret for ArtifactPullSecret authentication.
        :param audience: Audience for SystemAssignedManagedIdentity authentication.
        :param client_id: Client ID for UserAssignedManagedIdentity authentication.
        :param tenant_id: Tenant ID for UserAssignedManagedIdentity authentication.
        :param scope: Scope for UserAssignedManagedIdentity authentication.
        :returns: The updated registry endpoint.
        """

        # Get existing registry endpoint
        existing_endpoint = self.show(
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            registry_endpoint_name=registry_endpoint_name,
        )

        if host is not None:
            existing_endpoint["properties"]["host"] = host

        # Process authentication configuration
        if any([auth_type, secret_ref, audience, client_id, tenant_id, scope]):
            auth_config = self._process_registry_endpoint_authentication(
                type=auth_type,
                secret_ref=secret_ref,
                audience=audience,
                client_id=client_id,
                tenant_id=tenant_id,
                scope=scope,
            )
            existing_endpoint["properties"]["authentication"] = auth_config

        with console.status("Working..."):
            poller = self.registry_endpoints.begin_create_or_update(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                registry_endpoint_name=registry_endpoint_name,
                registry_endpoint=existing_endpoint,
                **kwargs,
            )
            return wait_for_terminal_state(poller)

    def remove(
        self,
        instance_name: str,
        resource_group_name: str,
        registry_endpoint_name: str,
        confirm_yes: Optional[bool] = None,
        **kwargs,
    ) -> None:
        """
        Remove a registry endpoint from an IoT Operations instance.

        :param instance_name: Name of the IoT Operations instance.
        :param resource_group_name: Name of the resource group.
        :param registry_endpoint_name: Name of the registry endpoint to delete.
        :param confirm_yes: Whether to skip confirmation prompt.
        :param kwargs: Additional keyword arguments for the operation.
        """
        should_bail = not should_continue_prompt(confirm_yes=confirm_yes)
        if should_bail:
            return

        with console.status(f"Removing registry endpoint '{registry_endpoint_name}'..."):
            poller = self.registry_endpoints.begin_delete(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                registry_endpoint_name=registry_endpoint_name,
            )
            wait_for_terminal_state(poller, **kwargs)
        logger.info(f"Registry endpoint '{registry_endpoint_name}' removed successfully.")

    def _identify_authentication_method(
        self,
        secret_ref: Optional[str] = None,
        audience: Optional[str] = None,
        client_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> RegistryEndpointAuthenticationType:
        """
        Identify the authentication method based on provided parameters.

        :param secret_ref: Reference to the secret for authentication.
        :param audience: Audience for the authentication.
        :param client_id: Client ID for the authentication.
        :param tenant_id: Tenant ID for the authentication.
        :param scope: Scope for the authentication.
        :returns: The identified authentication type.
        """
        # Check for ArtifactPullSecret parameters
        if secret_ref:
            return RegistryEndpointAuthenticationType.ARTIFACTPULLSECRET

        # Check for UserAssignedManagedIdentity parameters
        if client_id or tenant_id or scope:
            return RegistryEndpointAuthenticationType.USERASSIGNED

        # Check for SystemAssignedManagedIdentity parameters
        if audience:
            return RegistryEndpointAuthenticationType.SYSTEMASSIGNED

        # Default to Anonymous if no parameters provided
        return RegistryEndpointAuthenticationType.ANONYMOUS

    def _validate_authentication_parameters(
        self,
        auth_type: RegistryEndpointAuthenticationType,
        secret_ref: Optional[str] = None,
        audience: Optional[str] = None,
        client_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> None:
        """
        Validate that provided parameters are compatible with the chosen authentication type.

        :param auth_type: The authentication type.
        :param secret_ref: Reference to the secret for authentication.
        :param audience: Audience for the authentication.
        :param client_id: Client ID for the authentication.
        :param tenant_id: Tenant ID for the authentication.
        :param scope: Scope for the authentication.
        :raises MutuallyExclusiveArgumentError: If incompatible parameters are provided.
        :raises RequiredArgumentMissingError: If required parameters are missing for the authentication type.
        """
        provided_params = []
        if secret_ref:
            provided_params.append("secret_ref")
        if audience:
            provided_params.append("audience")
        if client_id:
            provided_params.append("client_id")
        if tenant_id:
            provided_params.append("tenant_id")
        if scope:
            provided_params.append("scope")

        required_params = REGISTRY_ENDPOINT_AUTHENTICATION_REQUIRED_PARAMS[auth_type.value]
        optional_params = REGISTRY_ENDPOINT_AUTHENTICATION_OPTIONAL_PARAMS[auth_type.value]

        # Construct valid parameter set for the given authentication type
        allowed_params = set(required_params) | set(optional_params)

        # Check for mutually exclusive parameters
        improper_params = set(provided_params) - allowed_params
        if improper_params:
            improper_params_text = ", ".join(
                REGISTRY_ENDPOINT_AUTHENTICATION_PARAM_TEXT_MAP.get(param, param) for param in improper_params
            )
            raise MutuallyExclusiveArgumentError(
                f"Parameters {improper_params_text} are not compatible with authentication type '{auth_type.value}'."
            )

        # Check for missing required parameters
        parameter_delta = required_params - provided_params
        if parameter_delta:
            missing_params = ", ".join(
                [REGISTRY_ENDPOINT_AUTHENTICATION_PARAM_TEXT_MAP.get(param, param) for param in parameter_delta]
            )
            raise RequiredArgumentMissingError(
                f"Authentication type '{auth_type.value}' requires the following parameters: {missing_params}"
            )
