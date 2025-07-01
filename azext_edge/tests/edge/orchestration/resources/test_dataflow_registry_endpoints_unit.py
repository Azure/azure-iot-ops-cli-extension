# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional

import pytest
import responses
from azure.cli.core.azclierror import MutuallyExclusiveArgumentError, RequiredArgumentMissingError

from azext_edge.edge.commands_dataflow import (
    list_dataflow_graph_registries,
    remove_dataflow_graph_registry,
    show_dataflow_graph_registry,
)
from azext_edge.edge.providers.orchestration.common import (
    REGISTRY_ENDPOINT_AUTHENTICATION_TYPE_SETTINGS,
    RegistryEndpointAuthenticationType,
)
from azext_edge.edge.providers.orchestration.resources import RegistryEndpoints

from ....generators import generate_random_string
from .conftest import get_base_endpoint, get_mock_resource


def get_registry_endpoint_endpoint(
    instance_name: str, resource_group_name: str, registry_endpoint_name: Optional[str] = None
) -> str:
    resource_path = f"/instances/{instance_name}/registryEndpoints"
    if registry_endpoint_name:
        resource_path += f"/{registry_endpoint_name}"
    return get_base_endpoint(resource_group_name=resource_group_name, resource_path=resource_path)


def get_mock_registry_endpoint_record(
    registry_endpoint_name: str, instance_name: str, resource_group_name: str, host: str = "myregistry.azurecr.io"
) -> dict:
    return get_mock_resource(
        name=registry_endpoint_name,
        resource_path=f"/instances/{instance_name}/registryEndpoints/{registry_endpoint_name}",
        properties={
            "host": host,
            "authentication": {"method": "Anonymous"},
            "provisioningState": "Succeeded",
        },
        resource_group_name=resource_group_name,
        qualified_type="microsoft.iotoperations/instances/registryendpoints",
        is_proxy_resource=True,
    )


def test_registry_endpoint_show(mocked_cmd, mocked_responses: responses):
    registry_endpoint_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_registry_record = get_mock_registry_endpoint_record(
        registry_endpoint_name=registry_endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )

    mocked_responses.add(
        method=responses.GET,
        url=get_registry_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            registry_endpoint_name=registry_endpoint_name,
        ),
        json=mock_registry_record,
        status=200,
        content_type="application/json",
    )

    result = show_dataflow_graph_registry(
        cmd=mocked_cmd,
        registry_endpoint_name=registry_endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )

    assert result == mock_registry_record
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize("records", [0, 2])
def test_registry_endpoint_list(mocked_cmd, mocked_responses: responses, records: int):
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_registry_records = {
        "value": [
            get_mock_registry_endpoint_record(
                registry_endpoint_name=generate_random_string(),
                instance_name=instance_name,
                resource_group_name=resource_group_name,
                host=f"registry{i}.azurecr.io",
            )
            for i in range(records)
        ]
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_registry_endpoint_endpoint(instance_name=instance_name, resource_group_name=resource_group_name),
        json=mock_registry_records,
        status=200,
        content_type="application/json",
    )

    result = list(
        list_dataflow_graph_registries(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )
    )

    assert result == mock_registry_records["value"]
    assert len(mocked_responses.calls) == 1


def test_registry_endpoint_remove(mocked_cmd, mocked_responses: responses):
    registry_endpoint_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mocked_responses.add(
        method=responses.DELETE,
        url=get_registry_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            registry_endpoint_name=registry_endpoint_name,
        ),
        status=204,
    )

    remove_dataflow_graph_registry(
        cmd=mocked_cmd,
        registry_endpoint_name=registry_endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=True,
        wait_sec=0,
    )

    assert len(mocked_responses.calls) == 1


# Tests for RegistryEndpoints authentication methods
class TestRegistryEndpointsAuthentication:
    """Test class for RegistryEndpoints authentication method identification and validation."""

    @pytest.mark.parametrize("secret_ref", [None, "my-secret"])
    @pytest.mark.parametrize("audience", [None, "my-audience"])
    @pytest.mark.parametrize("client_id", [None, "my-client-id"])
    @pytest.mark.parametrize("tenant_id", [None, "my-tenant-id"])
    @pytest.mark.parametrize("scope", [None, "my-scope"])
    def test_identify_authentication_method(self, mocked_cmd, secret_ref, audience, client_id, tenant_id, scope):
        """Test _identify_authentication_method returns correct auth type for all parameter combinations."""
        # Create a RegistryEndpoints instance for testing
        registry_endpoints = RegistryEndpoints(cmd=mocked_cmd)

        # Call the method under test
        result = registry_endpoints._identify_authentication_method(
            secret_ref=secret_ref,
            audience=audience,
            client_id=client_id,
            tenant_id=tenant_id,
            scope=scope,
        )

        # Determine expected authentication type based on priority
        if secret_ref:
            expected = RegistryEndpointAuthenticationType.ARTIFACTPULLSECRET.value
        elif client_id or tenant_id or scope:
            expected = RegistryEndpointAuthenticationType.USERASSIGNED.value
        elif audience:
            expected = RegistryEndpointAuthenticationType.SYSTEMASSIGNED.value
        else:
            expected = RegistryEndpointAuthenticationType.ANONYMOUS.value

        # Assert the result matches expected authentication type
        assert result == expected

    @pytest.mark.parametrize(
        "auth_type",
        [
            RegistryEndpointAuthenticationType.ANONYMOUS.value,
            RegistryEndpointAuthenticationType.ARTIFACTPULLSECRET.value,
            RegistryEndpointAuthenticationType.SYSTEMASSIGNED.value,
            RegistryEndpointAuthenticationType.USERASSIGNED.value,
        ],
    )
    @pytest.mark.parametrize("secret_ref", [None, "my-secret"])
    @pytest.mark.parametrize("audience", [None, "my-audience"])
    @pytest.mark.parametrize("client_id", [None, "my-client-id"])
    @pytest.mark.parametrize("tenant_id", [None, "my-tenant-id"])
    @pytest.mark.parametrize("scope", [None, "my-scope"])
    def test_validate_authentication_parameters(
        self, mocked_cmd, auth_type, secret_ref, audience, client_id, tenant_id, scope
    ):
        """Test _validate_authentication_parameters for all auth types and parameter combinations."""
        # Create a RegistryEndpoints instance for testing
        registry_endpoints = RegistryEndpoints(cmd=mocked_cmd)

        # Determine if this combination should raise an exception
        should_raise_exception = False

        # Define what parameters are provided
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

        # Check for invalid parameter combinations based on auth type
        if auth_type == RegistryEndpointAuthenticationType.ANONYMOUS.value:
            # Anonymous should not have any auth parameters
            if provided_params:
                should_raise_exception = True
        elif auth_type == RegistryEndpointAuthenticationType.ARTIFACTPULLSECRET.value:
            # ArtifactPullSecret requires secret_ref and no other auth params
            if not secret_ref:
                should_raise_exception = True  # Missing required parameter
            if audience or client_id or tenant_id or scope:
                should_raise_exception = True  # Mutually exclusive parameters
        elif auth_type == RegistryEndpointAuthenticationType.SYSTEMASSIGNED.value:
            # SystemAssigned allows only audience parameter
            if secret_ref or client_id or tenant_id or scope:
                should_raise_exception = True  # Mutually exclusive parameters
        elif auth_type == RegistryEndpointAuthenticationType.USERASSIGNED.value:
            # UserAssigned requires at least one of client_id or tenant_id
            if not client_id or not tenant_id:
                should_raise_exception = True  # Missing required parameters
            if secret_ref or audience:
                should_raise_exception = True  # Mutually exclusive parameter

        if should_raise_exception:
            # Expect an exception to be raised
            with pytest.raises((MutuallyExclusiveArgumentError, RequiredArgumentMissingError)):
                registry_endpoints._validate_authentication_parameters(
                    auth_type=auth_type,
                    secret_ref=secret_ref,
                    audience=audience,
                    client_id=client_id,
                    tenant_id=tenant_id,
                    scope=scope,
                )
        else:
            # Should not raise any exception
            registry_endpoints._validate_authentication_parameters(
                auth_type=auth_type,
                secret_ref=secret_ref,
                audience=audience,
                client_id=client_id,
                tenant_id=tenant_id,
                scope=scope,
            )

    @pytest.mark.parametrize(
        "auth_type,secret_ref,audience,client_id,tenant_id,scope,expected_method,expected_settings_key,expected_settings",
        [
            # Anonymous - explicit type
            (
                RegistryEndpointAuthenticationType.ANONYMOUS.value,  # auth_type
                None,  # secret_ref
                None,  # audience
                None,  # client_id
                None,  # tenant_id
                None,  # scope
                RegistryEndpointAuthenticationType.ANONYMOUS.value,  # expected_method
                REGISTRY_ENDPOINT_AUTHENTICATION_TYPE_SETTINGS[
                    RegistryEndpointAuthenticationType.ANONYMOUS.value
                ],  # expected_settings_key
                {},  # expected_settings
            ),
            # Anonymous - auto-detection (no parameters)
            (
                None,  # auth_type
                None,  # secret_ref
                None,  # audience
                None,  # client_id
                None,  # tenant_id
                None,  # scope
                RegistryEndpointAuthenticationType.ANONYMOUS.value,  # expected_method
                REGISTRY_ENDPOINT_AUTHENTICATION_TYPE_SETTINGS[
                    RegistryEndpointAuthenticationType.ANONYMOUS.value
                ],  # expected_settings_key
                {},  # expected_settings
            ),
            # ArtifactPullSecret - explicit type
            (
                RegistryEndpointAuthenticationType.ARTIFACTPULLSECRET.value,  # auth_type
                "my-secret",  # secret_ref
                None,  # audience
                None,  # client_id
                None,  # tenant_id
                None,  # scope
                RegistryEndpointAuthenticationType.ARTIFACTPULLSECRET.value,  # expected_method
                REGISTRY_ENDPOINT_AUTHENTICATION_TYPE_SETTINGS[
                    RegistryEndpointAuthenticationType.ARTIFACTPULLSECRET.value
                ],  # expected_settings_key
                {"secretRef": "my-secret"},  # expected_settings
            ),
            # ArtifactPullSecret - auto-detection
            (
                None,  # auth_type
                "my-secret",  # secret_ref
                None,  # audience
                None,  # client_id
                None,  # tenant_id
                None,  # scope
                RegistryEndpointAuthenticationType.ARTIFACTPULLSECRET.value,  # expected_method
                REGISTRY_ENDPOINT_AUTHENTICATION_TYPE_SETTINGS[
                    RegistryEndpointAuthenticationType.ARTIFACTPULLSECRET.value
                ],  # expected_settings_key
                {"secretRef": "my-secret"},  # expected_settings
            ),
            # SystemAssigned - explicit type with audience
            (
                RegistryEndpointAuthenticationType.SYSTEMASSIGNED.value,  # auth_type
                None,  # secret_ref
                "my-audience",  # audience
                None,  # client_id
                None,  # tenant_id
                None,  # scope
                RegistryEndpointAuthenticationType.SYSTEMASSIGNED.value,  # expected_method
                REGISTRY_ENDPOINT_AUTHENTICATION_TYPE_SETTINGS[
                    RegistryEndpointAuthenticationType.SYSTEMASSIGNED.value
                ],  # expected_settings_key
                {"audience": "my-audience"},  # expected_settings
            ),
            # SystemAssigned - explicit type without audience
            (
                RegistryEndpointAuthenticationType.SYSTEMASSIGNED.value,  # auth_type
                None,  # secret_ref
                None,  # audience
                None,  # client_id
                None,  # tenant_id
                None,  # scope
                RegistryEndpointAuthenticationType.SYSTEMASSIGNED.value,  # expected_method
                REGISTRY_ENDPOINT_AUTHENTICATION_TYPE_SETTINGS[
                    RegistryEndpointAuthenticationType.SYSTEMASSIGNED.value
                ],  # expected_settings_key
                {},  # expected_settings
            ),
            # SystemAssigned - auto-detection
            (
                None,  # auth_type
                None,  # secret_ref
                "my-audience",  # audience
                None,  # client_id
                None,  # tenant_id
                None,  # scope
                RegistryEndpointAuthenticationType.SYSTEMASSIGNED.value,  # expected_method
                REGISTRY_ENDPOINT_AUTHENTICATION_TYPE_SETTINGS[
                    RegistryEndpointAuthenticationType.SYSTEMASSIGNED.value
                ],  # expected_settings_key
                {"audience": "my-audience"},  # expected_settings
            ),
            # UserAssigned - explicit type with client_id and tenant_id
            (
                RegistryEndpointAuthenticationType.USERASSIGNED.value,  # auth_type
                None,  # secret_ref
                None,  # audience
                "my-client-id",  # client_id
                "my-tenant-id",  # tenant_id
                None,  # scope
                RegistryEndpointAuthenticationType.USERASSIGNED.value,  # expected_method
                REGISTRY_ENDPOINT_AUTHENTICATION_TYPE_SETTINGS[
                    RegistryEndpointAuthenticationType.USERASSIGNED.value
                ],  # expected_settings_key
                {"clientId": "my-client-id", "tenantId": "my-tenant-id"},  # expected_settings
            ),
            # UserAssigned - explicit type with all parameters
            (
                RegistryEndpointAuthenticationType.USERASSIGNED.value,  # auth_type
                None,  # secret_ref
                None,  # audience
                "my-client-id",  # client_id
                "my-tenant-id",  # tenant_id
                "my-scope",  # scope
                RegistryEndpointAuthenticationType.USERASSIGNED.value,  # expected_method
                REGISTRY_ENDPOINT_AUTHENTICATION_TYPE_SETTINGS[
                    RegistryEndpointAuthenticationType.USERASSIGNED.value
                ],  # expected_settings_key
                {"clientId": "my-client-id", "tenantId": "my-tenant-id", "scope": "my-scope"},  # expected_settings
            ),
            # UserAssigned - auto-detection with all parameters
            (
                None,  # auth_type
                None,  # secret_ref
                None,  # audience
                "my-client-id",  # client_id
                "my-tenant-id",  # tenant_id
                "my-scope",  # scope
                RegistryEndpointAuthenticationType.USERASSIGNED.value,  # expected_method
                REGISTRY_ENDPOINT_AUTHENTICATION_TYPE_SETTINGS[
                    RegistryEndpointAuthenticationType.USERASSIGNED.value
                ],  # expected_settings_key
                {"clientId": "my-client-id", "tenantId": "my-tenant-id", "scope": "my-scope"},  # expected_settings
            ),
        ],
    )
    def test_process_registry_endpoint_authentication(
        self,
        mocked_cmd,
        auth_type,
        secret_ref,
        audience,
        client_id,
        tenant_id,
        scope,
        expected_method,
        expected_settings_key,
        expected_settings,
    ):
        """Test _process_registry_endpoint_authentication for all authentication types."""
        registry_endpoints = RegistryEndpoints(cmd=mocked_cmd)

        # Call the method under test
        result = registry_endpoints._process_registry_endpoint_authentication(
            type=auth_type,
            secret_ref=secret_ref,
            audience=audience,
            client_id=client_id,
            tenant_id=tenant_id,
            scope=scope,
        )

        # Verify the expected structure
        expected = {"method": expected_method, expected_settings_key: expected_settings}
        assert result == expected
