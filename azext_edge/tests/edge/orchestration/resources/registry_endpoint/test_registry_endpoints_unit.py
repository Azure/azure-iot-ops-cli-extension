# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional

import pytest
import responses
from azure.cli.core.azclierror import MutuallyExclusiveArgumentError, RequiredArgumentMissingError

from azext_edge.edge.commands_registry_endpoints import (
    add_registry_endpoint,
    list_registry_endpoints,
    remove_registry_endpoint,
    show_registry_endpoint,
    update_registry_endpoint,
)
from azext_edge.edge.providers.orchestration.common import (
    REGISTRY_ENDPOINT_AUTHENTICATION_TYPE_SETTINGS,
    RegistryEndpointAuthenticationType,
)
from azext_edge.edge.providers.orchestration.resources import RegistryEndpoints
from azext_edge.tests.edge.orchestration.resources.conftest import get_base_endpoint, get_mock_resource
from azext_edge.tests.edge.orchestration.resources.test_instances_unit import (
    get_instance_endpoint,
    get_mock_instance_record,
)
from azext_edge.tests.generators import generate_random_string


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

    result = show_registry_endpoint(
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
        list_registry_endpoints(
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

    remove_registry_endpoint(
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
            expected = RegistryEndpointAuthenticationType.SYSTEMASSIGNED.value  # Default to SAMI

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
        "auth_type,secret_ref,audience,client_id,tenant_id,scope,"
        "expected_method,expected_settings_key,expected_settings",
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
            # SystemAssignedManagedIdentity - auto-detection (no parameters, default behavior)
            (
                None,  # auth_type
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

    def test_identify_authentication_method_no_auth(self, mocked_cmd):
        """Test _identify_authentication_method returns Anonymous when no_auth is True."""
        # Create a RegistryEndpoints instance for testing
        registry_endpoints = RegistryEndpoints(cmd=mocked_cmd)

        # Test with no_auth=True
        result = registry_endpoints._identify_authentication_method(no_auth=True)
        assert result == RegistryEndpointAuthenticationType.ANONYMOUS.value

        # Test with no_auth=True and other parameters (should still return Anonymous)
        result = registry_endpoints._identify_authentication_method(
            no_auth=True,
            audience="test-audience",
            client_id="test-client",
        )
        assert result == RegistryEndpointAuthenticationType.ANONYMOUS.value

    def test_process_registry_endpoint_authentication_defaults(self, mocked_cmd):
        """Test _process_registry_endpoint_authentication with no_auth parameter."""
        registry_endpoints = RegistryEndpoints(cmd=mocked_cmd)

        # Test with no_auth=True - should return Anonymous
        result = registry_endpoints._process_registry_endpoint_authentication(no_auth=True)
        expected = {"method": RegistryEndpointAuthenticationType.ANONYMOUS.value, "anonymousSettings": {}}
        assert result == expected

        # Test with no_auth=True and other parameters (should raise exception)
        with pytest.raises(MutuallyExclusiveArgumentError):
            registry_endpoints._process_registry_endpoint_authentication(
                no_auth=True, audience="test-audience", client_id="test-client"
            )

        # Test with no_auth=False (should use default SAMI)
        result = registry_endpoints._process_registry_endpoint_authentication(no_auth=False)
        expected_sami = {
            "method": RegistryEndpointAuthenticationType.SYSTEMASSIGNED.value,
            "systemAssignedManagedIdentitySettings": {},
        }
        assert result == expected_sami


def test_registry_endpoint_add_anonymous(mocked_cmd, mocked_responses: responses):
    """Test adding a registry endpoint with Anonymous authentication."""
    registry_endpoint_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    host = "myregistry.azurecr.io"

    # Mock the instance record for extended location retrieval
    mock_instance_record = get_mock_instance_record(
        name=instance_name,
        resource_group_name=resource_group_name,
    )

    # Mock the GET call to retrieve instance for extended location
    mocked_responses.add(
        method=responses.GET,
        url=get_instance_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
        ),
        json=mock_instance_record,
        status=200,
        content_type="application/json",
    )

    mock_registry_record = get_mock_registry_endpoint_record(
        registry_endpoint_name=registry_endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        host=host,
    )

    mocked_responses.add(
        method=responses.PUT,
        url=get_registry_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            registry_endpoint_name=registry_endpoint_name,
        ),
        json=mock_registry_record,
        status=200,
        content_type="application/json",
    )

    result = add_registry_endpoint(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        registry_endpoint_name=registry_endpoint_name,
        host=host,
        wait_sec=0,
    )

    assert result == mock_registry_record
    assert len(mocked_responses.calls) == 2  # GET instance + PUT registry


@pytest.mark.parametrize(
    "auth_type,secret_ref,audience,client_id,tenant_id,scope",
    [
        # ArtifactPullSecret
        (RegistryEndpointAuthenticationType.ARTIFACTPULLSECRET.value, "my-secret", None, None, None, None),
        (None, "my-secret", None, None, None, None),  # Auto-detection
        # SystemAssigned
        (RegistryEndpointAuthenticationType.SYSTEMASSIGNED.value, None, "my-audience", None, None, None),
        (None, None, "my-audience", None, None, None),  # Auto-detection
        # UserAssigned
        (RegistryEndpointAuthenticationType.USERASSIGNED.value, None, None, "my-client", "my-tenant", None),
        (RegistryEndpointAuthenticationType.USERASSIGNED.value, None, None, "my-client", "my-tenant", "my-scope"),
        (None, None, None, "my-client", "my-tenant", "my-scope"),  # Auto-detection
    ],
)
def test_registry_endpoint_add_with_auth(
    mocked_cmd, mocked_responses: responses, auth_type, secret_ref, audience, client_id, tenant_id, scope
):
    """Test adding a registry endpoint with various authentication types."""
    registry_endpoint_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    host = "myregistry.azurecr.io"

    # Determine expected auth method
    if secret_ref:
        expected_method = RegistryEndpointAuthenticationType.ARTIFACTPULLSECRET.value
    elif client_id or tenant_id or scope:
        expected_method = RegistryEndpointAuthenticationType.USERASSIGNED.value
    elif audience:
        expected_method = RegistryEndpointAuthenticationType.SYSTEMASSIGNED.value
    else:
        expected_method = RegistryEndpointAuthenticationType.ANONYMOUS.value

    # Mock the instance record for extended location retrieval
    mock_instance_record = get_mock_instance_record(
        name=instance_name,
        resource_group_name=resource_group_name,
    )

    # Mock the GET call to retrieve instance for extended location
    mocked_responses.add(
        method=responses.GET,
        url=get_instance_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
        ),
        json=mock_instance_record,
        status=200,
        content_type="application/json",
    )

    mock_registry_record = get_mock_registry_endpoint_record(
        registry_endpoint_name=registry_endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        host=host,
    )
    # Update the authentication method in the mock
    mock_registry_record["properties"]["authentication"]["method"] = expected_method

    mocked_responses.add(
        method=responses.PUT,
        url=get_registry_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            registry_endpoint_name=registry_endpoint_name,
        ),
        json=mock_registry_record,
        status=200,
        content_type="application/json",
    )

    result = add_registry_endpoint(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        registry_endpoint_name=registry_endpoint_name,
        host=host,
        auth_type=auth_type,
        secret_ref=secret_ref,
        audience=audience,
        client_id=client_id,
        tenant_id=tenant_id,
        scope=scope,
        wait_sec=0,
    )

    assert result == mock_registry_record
    assert len(mocked_responses.calls) == 2  # GET instance + PUT registry


def test_registry_endpoint_update_host_only(mocked_cmd, mocked_responses: responses):
    """Test updating a registry endpoint with only host change."""
    registry_endpoint_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    new_host = "newregistry.azurecr.io"

    # Mock the GET call to retrieve existing endpoint
    existing_record = get_mock_registry_endpoint_record(
        registry_endpoint_name=registry_endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        host="oldregistry.azurecr.io",
    )

    # Mock the updated record
    updated_record = get_mock_registry_endpoint_record(
        registry_endpoint_name=registry_endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        host=new_host,
    )

    mocked_responses.add(
        method=responses.GET,
        url=get_registry_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            registry_endpoint_name=registry_endpoint_name,
        ),
        json=existing_record,
        status=200,
        content_type="application/json",
    )

    mocked_responses.add(
        method=responses.PUT,
        url=get_registry_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            registry_endpoint_name=registry_endpoint_name,
        ),
        json=updated_record,
        status=200,
        content_type="application/json",
    )

    result = update_registry_endpoint(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        registry_endpoint_name=registry_endpoint_name,
        host=new_host,
        wait_sec=0,
    )

    assert result == updated_record
    assert len(mocked_responses.calls) == 2  # GET + PUT


@pytest.mark.parametrize(
    "auth_type,secret_ref,audience,client_id,tenant_id,scope",
    [
        # Update to ArtifactPullSecret
        (RegistryEndpointAuthenticationType.ARTIFACTPULLSECRET.value, "new-secret", None, None, None, None),
        # Update to SystemAssigned
        (RegistryEndpointAuthenticationType.SYSTEMASSIGNED.value, None, "new-audience", None, None, None),
        # Update to UserAssigned
        (RegistryEndpointAuthenticationType.USERASSIGNED.value, None, None, "new-client", "new-tenant", "new-scope"),
        # Auto-detection updates
        (None, "auto-secret", None, None, None, None),
        (None, None, "auto-audience", None, None, None),
        (None, None, None, "auto-client", "auto-tenant", None),
    ],
)
def test_registry_endpoint_update_auth(
    mocked_cmd, mocked_responses: responses, auth_type, secret_ref, audience, client_id, tenant_id, scope
):
    """Test updating a registry endpoint with authentication changes."""
    registry_endpoint_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    host = "myregistry.azurecr.io"

    # Mock the GET call to retrieve existing endpoint
    existing_record = get_mock_registry_endpoint_record(
        registry_endpoint_name=registry_endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        host=host,
    )

    # Determine expected auth method
    if secret_ref:
        expected_method = RegistryEndpointAuthenticationType.ARTIFACTPULLSECRET.value
    elif client_id or tenant_id or scope:
        expected_method = RegistryEndpointAuthenticationType.USERASSIGNED.value
    elif audience:
        expected_method = RegistryEndpointAuthenticationType.SYSTEMASSIGNED.value
    else:
        expected_method = RegistryEndpointAuthenticationType.ANONYMOUS.value

    # Mock the updated record
    updated_record = get_mock_registry_endpoint_record(
        registry_endpoint_name=registry_endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        host=host,
    )
    # Update the authentication method in the mock
    updated_record["properties"]["authentication"]["method"] = expected_method

    mocked_responses.add(
        method=responses.GET,
        url=get_registry_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            registry_endpoint_name=registry_endpoint_name,
        ),
        json=existing_record,
        status=200,
        content_type="application/json",
    )

    mocked_responses.add(
        method=responses.PUT,
        url=get_registry_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            registry_endpoint_name=registry_endpoint_name,
        ),
        json=updated_record,
        status=200,
        content_type="application/json",
    )

    result = update_registry_endpoint(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        registry_endpoint_name=registry_endpoint_name,
        auth_type=auth_type,
        secret_ref=secret_ref,
        audience=audience,
        client_id=client_id,
        tenant_id=tenant_id,
        scope=scope,
        wait_sec=0,
    )

    assert result == updated_record
    assert len(mocked_responses.calls) == 2  # GET + PUT


def test_registry_endpoint_update_host_and_auth(mocked_cmd, mocked_responses: responses):
    """Test updating a registry endpoint with both host and authentication changes."""
    registry_endpoint_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    new_host = "newregistry.azurecr.io"
    secret_ref = "new-secret"

    # Mock the GET call to retrieve existing endpoint
    existing_record = get_mock_registry_endpoint_record(
        registry_endpoint_name=registry_endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        host="oldregistry.azurecr.io",
    )

    # Mock the updated record
    updated_record = get_mock_registry_endpoint_record(
        registry_endpoint_name=registry_endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        host=new_host,
    )
    # Update the authentication method in the mock
    updated_record["properties"]["authentication"][
        "method"
    ] = RegistryEndpointAuthenticationType.ARTIFACTPULLSECRET.value

    mocked_responses.add(
        method=responses.GET,
        url=get_registry_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            registry_endpoint_name=registry_endpoint_name,
        ),
        json=existing_record,
        status=200,
        content_type="application/json",
    )

    mocked_responses.add(
        method=responses.PUT,
        url=get_registry_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            registry_endpoint_name=registry_endpoint_name,
        ),
        json=updated_record,
        status=200,
        content_type="application/json",
    )

    result = update_registry_endpoint(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        registry_endpoint_name=registry_endpoint_name,
        host=new_host,
        secret_ref=secret_ref,
        wait_sec=0,
    )

    assert result == updated_record
    assert len(mocked_responses.calls) == 2  # GET + PUT


class TestRegistryEndpointsCodeSigningCas:
    """Test class for RegistryEndpoints code signing CAs functionality."""

    def test_process_code_signing_cas_none(self, mocked_cmd):
        """Test _process_code_signing_cas returns None when no parameters provided."""
        registry_endpoints = RegistryEndpoints(cmd=mocked_cmd)

        result = registry_endpoints._process_code_signing_cas()
        assert result is None

    def test_process_code_signing_cas_configmap_refs(self, mocked_cmd):
        """Test _process_code_signing_cas with configmap references."""
        registry_endpoints = RegistryEndpoints(cmd=mocked_cmd)

        result = registry_endpoints._process_code_signing_cas(code_signing_configmap_refs=["configmap1", "configmap2"])

        expected = [
            {
                "type": "ConfigMap",
                "configMapRef": "configmap1",
            },
            {
                "type": "ConfigMap",
                "configMapRef": "configmap2",
            }
        ]
        assert result == expected

    def test_process_code_signing_cas_secret_refs(self, mocked_cmd):
        """Test _process_code_signing_cas with secret references."""
        registry_endpoints = RegistryEndpoints(cmd=mocked_cmd)

        result = registry_endpoints._process_code_signing_cas(code_signing_secret_refs=["secret1", "secret2"])

        expected = [
            {
                "type": "Secret",
                "secretRef": "secret1",
            },
            {
                "type": "Secret",
                "secretRef": "secret2",
            }
        ]
        assert result == expected

    def test_process_code_signing_cas_mixed_refs(self, mocked_cmd):
        """Test _process_code_signing_cas with both configmap and secret references."""
        registry_endpoints = RegistryEndpoints(cmd=mocked_cmd)

        result = registry_endpoints._process_code_signing_cas(
            code_signing_configmap_refs=["configmap1"],
            code_signing_secret_refs=["secret1"],
        )

        expected = [
            {
                "type": "ConfigMap",
                "configMapRef": "configmap1",
            },
            {
                "type": "Secret",
                "secretRef": "secret1",
            },
        ]
        assert result == expected


def test_registry_endpoint_add_with_code_signing_configmap(mocked_cmd, mocked_responses: responses):
    """Test adding a registry endpoint with code signing ConfigMap CAs."""
    registry_endpoint_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    host = "myregistry.azurecr.io"
    code_signing_configmaps = ["configmap1", "configmap2"]

    # Mock the instance record for extended location retrieval
    mock_instance_record = get_mock_instance_record(
        name=instance_name,
        resource_group_name=resource_group_name,
    )

    # Mock the GET call to retrieve instance for extended location
    mocked_responses.add(
        method=responses.GET,
        url=get_instance_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
        ),
        json=mock_instance_record,
        status=200,
        content_type="application/json",
    )

    # Create expected record with code signing CAs
    mock_registry_record = get_mock_registry_endpoint_record(
        registry_endpoint_name=registry_endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        host=host,
    )
    mock_registry_record["properties"]["codeSigningCas"] = [
        {
            "type": "ConfigMap",
            "configMapRef": "configmap1",
        },
        {
            "type": "ConfigMap",
            "configMapRef": "configmap2",
        }
    ]

    mocked_responses.add(
        method=responses.PUT,
        url=get_registry_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            registry_endpoint_name=registry_endpoint_name,
        ),
        json=mock_registry_record,
        status=200,
        content_type="application/json",
    )

    result = add_registry_endpoint(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        registry_endpoint_name=registry_endpoint_name,
        host=host,
        code_signing_configmap_refs=code_signing_configmaps,
        wait_sec=0,
    )

    assert result == mock_registry_record
    assert len(mocked_responses.calls) == 2  # GET instance + PUT registry

    # Verify code signing CAs in the result
    cas = result["properties"]["codeSigningCas"]
    assert len(cas) == 2
    assert cas[0]["configMapRef"] == "configmap1"
    assert cas[0]["type"] == "ConfigMap"
    assert cas[1]["configMapRef"] == "configmap2"
    assert cas[1]["type"] == "ConfigMap"


def test_registry_endpoint_add_with_code_signing_secret(mocked_cmd, mocked_responses: responses):
    """Test adding a registry endpoint with code signing Secret CAs."""
    registry_endpoint_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    host = "myregistry.azurecr.io"
    code_signing_secrets = ["secret1"]

    # Mock the instance record for extended location retrieval
    mock_instance_record = get_mock_instance_record(
        name=instance_name,
        resource_group_name=resource_group_name,
    )

    # Mock the GET call to retrieve instance for extended location
    mocked_responses.add(
        method=responses.GET,
        url=get_instance_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
        ),
        json=mock_instance_record,
        status=200,
        content_type="application/json",
    )

    # Create expected record with code signing CAs
    mock_registry_record = get_mock_registry_endpoint_record(
        registry_endpoint_name=registry_endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        host=host,
    )
    mock_registry_record["properties"]["codeSigningCas"] = [
        {
            "type": "Secret",
            "secretRef": "secret1",
        }
    ]

    mocked_responses.add(
        method=responses.PUT,
        url=get_registry_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            registry_endpoint_name=registry_endpoint_name,
        ),
        json=mock_registry_record,
        status=200,
        content_type="application/json",
    )

    result = add_registry_endpoint(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        registry_endpoint_name=registry_endpoint_name,
        host=host,
        code_signing_secret_refs=code_signing_secrets,
        wait_sec=0,
    )

    assert result == mock_registry_record
    assert len(mocked_responses.calls) == 2  # GET instance + PUT registry

    # Verify code signing CAs in the result
    cas = result["properties"]["codeSigningCas"]
    assert len(cas) == 1
    assert cas[0]["secretRef"] == "secret1"
    assert cas[0]["type"] == "Secret"


def test_registry_endpoint_update_with_code_signing_configmap(mocked_cmd, mocked_responses: responses):
    """Test updating a registry endpoint with code signing ConfigMap CAs."""
    registry_endpoint_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    code_signing_configmaps = ["configmap1"]

    # Mock existing registry endpoint
    existing_record = get_mock_registry_endpoint_record(
        registry_endpoint_name=registry_endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )

    # Mock the GET call to retrieve existing endpoint
    mocked_responses.add(
        method=responses.GET,
        url=get_registry_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            registry_endpoint_name=registry_endpoint_name,
        ),
        json=existing_record,
        status=200,
        content_type="application/json",
    )

    # Create updated record with code signing CAs
    updated_record = existing_record.copy()
    updated_record["properties"]["codeSigningCas"] = [
        {
            "type": "ConfigMap",
            "configMapRef": "configmap1",
        }
    ]

    # Mock the PUT call to update endpoint
    mocked_responses.add(
        method=responses.PUT,
        url=get_registry_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            registry_endpoint_name=registry_endpoint_name,
        ),
        json=updated_record,
        status=200,
        content_type="application/json",
    )

    result = update_registry_endpoint(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        registry_endpoint_name=registry_endpoint_name,
        code_signing_configmap_refs=code_signing_configmaps,
        wait_sec=0,
    )

    assert result == updated_record
    assert len(mocked_responses.calls) == 2  # GET + PUT

    # Verify code signing CAs in the result
    cas = result["properties"]["codeSigningCas"]
    assert len(cas) == 1
    assert cas[0]["configMapRef"] == "configmap1"
    assert cas[0]["type"] == "ConfigMap"


def test_registry_endpoint_update_with_code_signing_secret(mocked_cmd, mocked_responses: responses):
    """Test updating a registry endpoint with code signing Secret CAs."""
    registry_endpoint_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    code_signing_secrets = ["secret1"]

    # Mock existing registry endpoint
    existing_record = get_mock_registry_endpoint_record(
        registry_endpoint_name=registry_endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )

    # Mock the GET call to retrieve existing endpoint
    mocked_responses.add(
        method=responses.GET,
        url=get_registry_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            registry_endpoint_name=registry_endpoint_name,
        ),
        json=existing_record,
        status=200,
        content_type="application/json",
    )

    # Create updated record with code signing CAs
    updated_record = existing_record.copy()
    updated_record["properties"]["codeSigningCas"] = [
        {
            "type": "Secret",
            "secretRef": "secret1",
        }
    ]

    # Mock the PUT call to update endpoint
    mocked_responses.add(
        method=responses.PUT,
        url=get_registry_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            registry_endpoint_name=registry_endpoint_name,
        ),
        json=updated_record,
        status=200,
        content_type="application/json",
    )

    result = update_registry_endpoint(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        registry_endpoint_name=registry_endpoint_name,
        code_signing_secret_refs=code_signing_secrets,
        wait_sec=0,
    )

    assert result == updated_record
    assert len(mocked_responses.calls) == 2  # GET + PUT

    # Verify code signing CAs in the result
    cas = result["properties"]["codeSigningCas"]
    assert len(cas) == 1
    assert cas[0]["secretRef"] == "secret1"
    assert cas[0]["type"] == "Secret"
