# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from collections import defaultdict
from shlex import split
from typing import TYPE_CHECKING, Iterable, Optional

from azure.cli.core.azclierror import MutuallyExclusiveArgumentError, RequiredArgumentMissingError, AzCLIError
from knack.log import get_logger
from rich.console import Console

from azext_edge.edge.util.embedded_cli import EmbeddedCLI

from ....util.az_client import wait_for_terminal_state
from ....util.common import run_host_command, should_continue_prompt
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

        :param cmd: Command context.
        :param registry_name: Name of the registry endpoint to query.
        :param instance_name: Name of the IoT Operations instance.
        :param resource_group_name: Name of the resource group.
        :return: Iterable of image dictionaries.
        """

        # get all endpoints
        endpoints = (
            self.registry_endpoints.list_by_instance_resource(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
            )
            or []
            # Placeholder for testing
            # [{"properties": {"host": "https://aziotops.azurecr.io"}, "name": "azure iot operations registry"}]
        )
        graphs = defaultdict(list)
        embedded_cli = EmbeddedCLI(capture_stderr=True)

        # loop through each registry endpoint to get images
        for registry_endpoint in endpoints:
            # Extract host from registry endpoint properties
            host = registry_endpoint.get("properties", {}).get("host")
            # print(f"Processing registry endpoint: {registry_endpoint['name']} with host: {host}")

            # Parse the registry name from the host URL
            # Expected format: <registry-name>.azurecr.io or https://<registry-name>.azurecr.io
            registry_host = host.replace("https://", "").replace("http://", "")
            acr_name = registry_host.split(".")[0]

            # Execute az acr repository list command
            repository_list_command = f"acr repository list -n '{acr_name}'"
            # print(f"Running command: {repository_list_command}")
            repositories_result = embedded_cli.invoke(
                command=repository_list_command,
            )
            if repositories_result.success():
                repositories = repositories_result.as_json()
                repository_result = {}
                for repository in repositories:
                    # print(f"Processing repository: {repository} in registry: {acr_name}")
                    image_tags_command = f"acr repository show-tags --repository '{repository}' -n '{acr_name}'"
                    # print(f"Running command: {image_tags_command}")
                    image_tags_result = embedded_cli.invoke(
                        command=image_tags_command,
                    )
                    if image_tags_result.success():
                        tags = image_tags_result.as_json()
                        for tag in tags:
                            # print(f"Processing tag: {tag} for image: {repository} in registry: {acr_name}")
                            # command is in preview so don't show warning output
                            manifest_command = f"acr manifest show -r '{acr_name}' -n '{repository}:{tag}'"
                            # print(f"Running command: {manifest_command}")
                            manifest_result = embedded_cli.invoke(
                                command=manifest_command,
                                capture_stderr=True,  # Capture stderr to avoid printing warnings
                            )
                            if manifest_result.success():
                                manifest = manifest_result.as_json()
                                # print(f"Manifest for tag {tag} in repository {repository}: {manifest}")
                                if manifest.get("config", {}).get("mediaType") == DATAFLOW_GRAPH_MEDIA_TYPE:
                                    # print(f"Found dataflow graph for {repository}:{tag} in {acr_name}")
                                    repository_result.setdefault(repository, []).append(
                                        {
                                            "tag": tag,
                                            "name": manifest.get("annotations", {}).get(
                                                DATAFLOW_GRAPH_ANNOTATION_DISPLAY_NAME, ""
                                            ),
                                            "description": manifest.get("annotations", {}).get(
                                                DATAFLOW_GRAPH_ANNOTATION_DESCRIPTION, ""
                                            ),
                                        }
                                    )

                    else:
                        logger.warning(
                            f"Failed to list tags for image '{repository}' in registry '{acr_name}': {image_tags_result.error_message()}"
                        )

                graphs[acr_name] = repository_result
            else:
                raise AzCLIError(
                    f"Failed to list images for registry endpoint '{registry_endpoint['name']}': {repositories_result.error_message()}"
                )
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
