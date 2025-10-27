# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from contextlib import nullcontext
from typing import TYPE_CHECKING, Iterable, Optional

from azure.cli.core.azclierror import (
    MutuallyExclusiveArgumentError,
    RequiredArgumentMissingError,
)
from knack.log import get_logger
from rich.console import Console

from ....util.az_client import wait_for_terminal_state
from ....util.common import should_continue_prompt
from ....util.queryable import Queryable
from ..common import (
    REGISTRY_ENDPOINT_AUTHENTICATION_OPTIONAL_PARAMS,
    REGISTRY_ENDPOINT_AUTHENTICATION_PARAM_TEXT_MAP,
    REGISTRY_ENDPOINT_AUTHENTICATION_REQUIRED_PARAMS,
    REGISTRY_ENDPOINT_AUTHENTICATION_TYPE_SETTINGS,
    RegistryEndpointAuthenticationType,
    TrustedSigningKeyType,
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
        Get a specific registry endpoint of the IoT Operations instance.

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

    def _process_registry_endpoint_authentication(
        self,
        type: Optional[str] = None,
        secret_ref: Optional[str] = None,
        audience: Optional[str] = None,
        client_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        scope: Optional[str] = None,
        no_auth: Optional[bool] = None,
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
        :param no_auth: Whether to use anonymous authentication.
        :returns: The authentication configuration dictionary.
        :raises RequiredArgumentMissingError: If required parameters are missing for the authentication type.
        :raises MutuallyExclusiveArgumentError: If parameters from different authentication types are provided.
        """

        # Determine authentication type if not provided
        if not type:
            type = self._identify_authentication_method(
                secret_ref=secret_ref,
                audience=audience,
                client_id=client_id,
                tenant_id=tenant_id,
                scope=scope,
                no_auth=no_auth,
            )

        # Validate required / mutually exclusive parameters
        self._validate_authentication_parameters(
            auth_type=type,
            secret_ref=secret_ref,
            audience=audience,
            client_id=client_id,
            tenant_id=tenant_id,
            scope=scope,
            no_auth=no_auth,
        )

        # Build authentication configuration
        auth_config = {"method": type}

        # Add type-specific settings
        settings_key = REGISTRY_ENDPOINT_AUTHENTICATION_TYPE_SETTINGS[type]
        auth_settings = {}

        if type == RegistryEndpointAuthenticationType.ANONYMOUS.value:
            # Anonymous settings is an empty object
            auth_settings = {}
        elif type == RegistryEndpointAuthenticationType.ARTIFACTPULLSECRET.value:
            auth_settings = {"secretRef": secret_ref}
        elif type == RegistryEndpointAuthenticationType.SYSTEMASSIGNED.value:
            if audience:
                auth_settings["audience"] = audience
        elif type == RegistryEndpointAuthenticationType.USERASSIGNED.value:
            auth_settings["clientId"] = client_id
            auth_settings["tenantId"] = tenant_id
            if scope:
                auth_settings["scope"] = scope

        auth_config[settings_key] = auth_settings
        return auth_config

    def _process_code_signing_cas(
        self,
        code_signing_configmap_refs: Optional[list] = None,
        code_signing_secret_refs: Optional[list] = None,
    ) -> list:
        """
        Process code signing CA configuration for registry endpoints.

        :param code_signing_configmap_refs: List of ConfigMap references for code signing CAs.
        :param code_signing_secret_refs: List of Secret references for code signing CAs.
        :returns: List of code signing CA objects
        """
        if not code_signing_configmap_refs and not code_signing_secret_refs:
            return None

        cas = []

        # Add ConfigMap references
        if code_signing_configmap_refs:
            cas += [
                {
                    "type": TrustedSigningKeyType.CONFIGMAP.value,
                    "configMapRef": configmap_ref,
                }
                for configmap_ref in code_signing_configmap_refs
            ]

        # Add Secret references
        if code_signing_secret_refs:
            cas += [
                {
                    "type": TrustedSigningKeyType.SECRET.value,
                    "secretRef": secret_ref,
                }
                for secret_ref in code_signing_secret_refs
            ]

        return cas

    def add(
        self,
        instance_name: str,
        resource_group_name: str,
        registry_endpoint_name: str,
        host: str,
        auth_type: Optional[str] = None,
        secret_ref: Optional[str] = None,
        audience: Optional[str] = None,
        client_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        scope: Optional[str] = None,
        no_auth: Optional[bool] = None,
        code_signing_configmap_refs: Optional[list] = None,
        code_signing_secret_refs: Optional[list] = None,
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
        :param no_auth: Whether to use anonymous authentication.
        :param code_signing_configmap_refs: List of code signing CA config map references.
        :param code_signing_secret_refs: List of code signing CA secret references.
        :param kwargs: Additional keyword arguments for the operation.
        :returns: The created registry endpoint.
        """

        status_text = kwargs.pop("status_text", "Working...")
        no_status = kwargs.pop("no_status", False)
        headers = kwargs.pop("headers", None)
        operation_kwargs = {"headers": headers or {"CommandName": "iot ops registry add"}}

        # Process authentication configuration
        auth_config = self._process_registry_endpoint_authentication(
            type=auth_type,
            secret_ref=secret_ref,
            audience=audience,
            client_id=client_id,
            tenant_id=tenant_id,
            scope=scope,
            no_auth=no_auth,
        )

        # Process code signing CAs configuration
        code_signing_cas = self._process_code_signing_cas(
            code_signing_configmap_refs=code_signing_configmap_refs,
            code_signing_secret_refs=code_signing_secret_refs,
        )

        # Build the resource configuration
        properties = {
            "host": host,
            "authentication": auth_config,
        }

        # Add code signing CAs if provided
        if code_signing_cas:
            properties["codeSigningCas"] = code_signing_cas

        resource = {
            "extendedLocation": self.instances.get_ext_loc(
                name=instance_name,
                resource_group_name=resource_group_name,
            ),
            "properties": properties,
        }

        status_context = nullcontext() if no_status else console.status(status_text)
        with status_context:
            poller = self.registry_endpoints.begin_create_or_update(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                registry_endpoint_name=registry_endpoint_name,
                resource=resource,
                **operation_kwargs,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def update(
        self,
        instance_name: str,
        resource_group_name: str,
        registry_endpoint_name: str,
        host: Optional[str] = None,
        auth_type: Optional[str] = None,
        secret_ref: Optional[str] = None,
        audience: Optional[str] = None,
        client_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        scope: Optional[str] = None,
        no_auth: Optional[bool] = None,
        code_signing_configmap_refs: Optional[list] = None,
        code_signing_secret_refs: Optional[list] = None,
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
        :param no_auth: Whether to use anonymous authentication.
        :param code_signing_configmap_refs: List of code signing CA config map references.
        :param code_signing_secret_refs: List of code signing CA secret references.
        :param kwargs: Additional keyword arguments for the operation.
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
        if any([auth_type, secret_ref, audience, client_id, tenant_id, scope, no_auth]):
            auth_config = self._process_registry_endpoint_authentication(
                type=auth_type,
                secret_ref=secret_ref,
                audience=audience,
                client_id=client_id,
                tenant_id=tenant_id,
                scope=scope,
                no_auth=no_auth,
            )
            existing_endpoint["properties"]["authentication"] = auth_config

        # Process code signing CAs configuration if provided
        if code_signing_configmap_refs is not None or code_signing_secret_refs is not None:
            existing_endpoint["properties"]["codeSigningCas"] = self._process_code_signing_cas(
                code_signing_configmap_refs=code_signing_configmap_refs,
                code_signing_secret_refs=code_signing_secret_refs,
            )

        with console.status("Working..."):
            poller = self.registry_endpoints.begin_create_or_update(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                registry_endpoint_name=registry_endpoint_name,
                resource=existing_endpoint,
            )
            return wait_for_terminal_state(poller, **kwargs)

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
        should_bail = not should_continue_prompt(confirm_yes=confirm_yes, context="Removal")
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
        no_auth: Optional[bool] = None,
    ) -> str:
        """
        Identify the authentication method based on provided parameters.

        :param secret_ref: Reference to the secret for authentication.
        :param audience: Audience for the authentication.
        :param client_id: Client ID for the authentication.
        :param tenant_id: Tenant ID for the authentication.
        :param scope: Scope for the authentication.
        :param no_auth: Whether to use anonymous authentication.
        :returns: The identified authentication type.
        """
        # Check for explicit no authentication request
        if no_auth:
            return RegistryEndpointAuthenticationType.ANONYMOUS.value

        # Check for ArtifactPullSecret parameters
        if secret_ref:
            return RegistryEndpointAuthenticationType.ARTIFACTPULLSECRET.value

        # Check for UserAssignedManagedIdentity parameters
        if client_id or tenant_id or scope:
            return RegistryEndpointAuthenticationType.USERASSIGNED.value

        # Check for SystemAssignedManagedIdentity parameters
        if audience:
            return RegistryEndpointAuthenticationType.SYSTEMASSIGNED.value

        # Default to SystemAssignedManagedIdentity if no parameters provided
        return RegistryEndpointAuthenticationType.SYSTEMASSIGNED.value

    def _validate_authentication_parameters(
        self,
        auth_type: str,
        secret_ref: Optional[str] = None,
        audience: Optional[str] = None,
        client_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        scope: Optional[str] = None,
        no_auth: Optional[bool] = None,
    ) -> None:
        """
        Validate that provided parameters are compatible with the chosen authentication type.

        :param auth_type: The authentication type.
        :param secret_ref: Reference to the secret for authentication.
        :param audience: Audience for the authentication.
        :param client_id: Client ID for the authentication.
        :param tenant_id: Tenant ID for the authentication.
        :param scope: Scope for the authentication.
        :param no_auth: Whether to use anonymous authentication.
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

        # Check for mutually exclusive no_auth parameter
        if no_auth and provided_params:
            raise MutuallyExclusiveArgumentError(
                "The --no-auth parameter cannot be used with other authentication parameters."
            )

        required_params = REGISTRY_ENDPOINT_AUTHENTICATION_REQUIRED_PARAMS[auth_type]
        optional_params = REGISTRY_ENDPOINT_AUTHENTICATION_OPTIONAL_PARAMS[auth_type]

        # Construct valid parameter set for the given authentication type
        allowed_params = set(required_params) | set(optional_params)

        # Check for mutually exclusive parameters
        improper_params = set(provided_params) - allowed_params
        if improper_params:
            improper_params_text = ", ".join(
                REGISTRY_ENDPOINT_AUTHENTICATION_PARAM_TEXT_MAP.get(param, param) for param in improper_params
            )
            raise MutuallyExclusiveArgumentError(
                f"Parameters {improper_params_text} are not compatible with authentication type '{auth_type}'."
            )

        # Check for missing required parameters
        parameter_delta = required_params - set(provided_params)
        if parameter_delta:
            missing_params = ", ".join(
                [REGISTRY_ENDPOINT_AUTHENTICATION_PARAM_TEXT_MAP.get(param, param) for param in parameter_delta]
            )
            raise RequiredArgumentMissingError(
                f"Authentication type '{auth_type}' requires the following parameters: {missing_params}"
            )
