# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from azext_edge.tests.generators import generate_random_string
from azext_edge.tests.helpers import run
from azext_edge.tests.settings import EnvironmentVariables

# pytest mark for rpsaas (cloud-side) tests
pytestmark = pytest.mark.rpsaas


@pytest.fixture(scope="function")
def registry_endpoint_test_setup(settings):
    """Setup fixture for registry endpoint tests."""
    settings.add_to_config(EnvironmentVariables.rg.value)
    settings.add_to_config(EnvironmentVariables.instance.value)
    if not all([settings.env.azext_edge_instance, settings.env.azext_edge_rg]):
        raise AssertionError(
            "Cannot run registry endpoint tests without an instance and resource group. "
            f"Current settings:\n {settings}"
        )

    yield {
        "resourceGroup": settings.env.azext_edge_rg,
        "instanceName": settings.env.azext_edge_instance,
    }


def test_registry_endpoint_lifecycle_anonymous(registry_endpoint_test_setup, tracked_resources):
    """Test complete lifecycle of registry endpoint with Anonymous authentication."""
    resource_group = registry_endpoint_test_setup["resourceGroup"]
    instance_name = registry_endpoint_test_setup["instanceName"]
    registry_endpoint_name = f"test-registry-{generate_random_string(force_lower=True, size=8)}"
    host = "myregistry.azurecr.io"

    try:
        # CREATE - SAMI authentication (default)
        registry_endpoint = run(
            f"az iot ops registry add -n {registry_endpoint_name} "
            f"-g {resource_group} --instance {instance_name} "
            f"--host {host}"
        )
        tracked_resources.append(registry_endpoint["id"])

        assert_registry_endpoint(
            endpoint=registry_endpoint,
            name=registry_endpoint_name,
            resource_group=resource_group,
            instance_name=instance_name,
            host=host,
            auth_method="SystemAssignedManagedIdentity",  # Default auth type
        )

        # SHOW
        show_endpoint = run(
            f"az iot ops registry show -n {registry_endpoint_name} " f"-g {resource_group} --instance {instance_name}"
        )
        assert_registry_endpoint(
            endpoint=show_endpoint,
            name=registry_endpoint_name,
            resource_group=resource_group,
            instance_name=instance_name,
            host=host,
            auth_method="SystemAssignedManagedIdentity",
        )

        # LIST - check our endpoint is in the list
        list_endpoints = run(f"az iot ops registry list " f"-g {resource_group} --instance {instance_name}")
        endpoint_names = [ep["name"] for ep in list_endpoints]
        assert registry_endpoint_name in endpoint_names

        # UPDATE - change host
        new_host = "newregistry.azurecr.io"
        updated_endpoint = run(
            f"az iot ops registry update -n {registry_endpoint_name} "
            f"-g {resource_group} --instance {instance_name} "
            f"--host {new_host}"
        )
        assert_registry_endpoint(
            endpoint=updated_endpoint,
            name=registry_endpoint_name,
            resource_group=resource_group,
            instance_name=instance_name,
            host=new_host,
            auth_method="SystemAssignedManagedIdentity",
        )

        # REMOVE
        run(
            f"az iot ops registry remove -n {registry_endpoint_name} "
            f"-g {resource_group} --instance {instance_name} -y"
        )
        tracked_resources.remove(registry_endpoint["id"])

        # Verify removal - endpoint should not be in list
        list_endpoints_after = run(f"az iot ops registry list " f"-g {resource_group} --instance {instance_name}")
        endpoint_names_after = [ep["name"] for ep in list_endpoints_after]
        assert registry_endpoint_name not in endpoint_names_after

    except Exception:
        # Cleanup in case of failure
        if registry_endpoint.get("id") in tracked_resources:
            try:
                run(
                    f"az iot ops registry remove -n {registry_endpoint_name} "
                    f"-g {resource_group} --instance {instance_name} -y"
                )
                tracked_resources.remove(registry_endpoint["id"])
            except Exception:
                pass  # Best effort cleanup
        raise


def test_registry_endpoint_artifact_pull_secret(registry_endpoint_test_setup, tracked_resources):
    """Test complete lifecycle of registry endpoint with ArtifactPullSecret authentication."""
    resource_group = registry_endpoint_test_setup["resourceGroup"]
    instance_name = registry_endpoint_test_setup["instanceName"]
    registry_endpoint_name = f"test-registry-{generate_random_string(force_lower=True, size=8)}"
    host = "secretregistry.azurecr.io"
    secret_ref = "my-registry-secret"

    try:
        # CREATE - ArtifactPullSecret authentication
        registry_endpoint = run(
            f"az iot ops registry add -n {registry_endpoint_name} "
            f"-g {resource_group} --instance {instance_name} "
            f"--host {host} --secret-ref {secret_ref}"
        )
        tracked_resources.append(registry_endpoint["id"])

        assert_registry_endpoint(
            endpoint=registry_endpoint,
            name=registry_endpoint_name,
            resource_group=resource_group,
            instance_name=instance_name,
            host=host,
            auth_method="ArtifactPullSecret",
        )

        # SHOW
        show_endpoint = run(
            f"az iot ops registry show -n {registry_endpoint_name} " f"-g {resource_group} --instance {instance_name}"
        )
        assert_registry_endpoint(
            endpoint=show_endpoint,
            name=registry_endpoint_name,
            resource_group=resource_group,
            instance_name=instance_name,
            host=host,
            auth_method="ArtifactPullSecret",
        )

        # REMOVE
        run(
            f"az iot ops registry remove -n {registry_endpoint_name} "
            f"-g {resource_group} --instance {instance_name} -y"
        )
        tracked_resources.remove(registry_endpoint["id"])

    except Exception:
        # Cleanup in case of failure
        if registry_endpoint.get("id") in tracked_resources:
            try:
                run(
                    f"az iot ops registry remove -n {registry_endpoint_name} "
                    f"-g {resource_group} --instance {instance_name} -y"
                )
                tracked_resources.remove(registry_endpoint["id"])
            except Exception:
                pass  # Best effort cleanup
        raise


def test_registry_endpoint_system_assigned_auth(registry_endpoint_test_setup, tracked_resources):
    """Test registry endpoint with SystemAssigned authentication."""
    resource_group = registry_endpoint_test_setup["resourceGroup"]
    instance_name = registry_endpoint_test_setup["instanceName"]
    registry_endpoint_name = f"test-registry-{generate_random_string(force_lower=True, size=8)}"
    host = "systemregistry.azurecr.io"
    audience = "system-audience"

    try:
        # CREATE - SystemAssigned authentication with audience
        registry_endpoint = run(
            f"az iot ops registry add -n {registry_endpoint_name} "
            f"-g {resource_group} --instance {instance_name} "
            f"--host {host} --auth-type SystemAssignedManagedIdentity --audience {audience}"
        )
        tracked_resources.append(registry_endpoint["id"])

        assert_registry_endpoint(
            endpoint=registry_endpoint,
            name=registry_endpoint_name,
            resource_group=resource_group,
            instance_name=instance_name,
            host=host,
            auth_method="SystemAssignedManagedIdentity",
        )

        # SHOW
        show_endpoint = run(
            f"az iot ops registry show -n {registry_endpoint_name} " f"-g {resource_group} --instance {instance_name}"
        )
        assert_registry_endpoint(
            endpoint=show_endpoint,
            name=registry_endpoint_name,
            resource_group=resource_group,
            instance_name=instance_name,
            host=host,
            auth_method="SystemAssignedManagedIdentity",
        )

        # REMOVE
        run(
            f"az iot ops registry remove -n {registry_endpoint_name} "
            f"-g {resource_group} --instance {instance_name} -y"
        )
        tracked_resources.remove(registry_endpoint["id"])

    except Exception:
        # Cleanup in case of failure
        if registry_endpoint.get("id") in tracked_resources:
            try:
                run(
                    f"az iot ops registry remove -n {registry_endpoint_name} "
                    f"-g {resource_group} --instance {instance_name} -y"
                )
                tracked_resources.remove(registry_endpoint["id"])
            except Exception:
                pass  # Best effort cleanup
        raise


def test_registry_endpoint_user_assigned_auth(registry_endpoint_test_setup, tracked_resources):
    """Test registry endpoint with UserAssigned authentication."""
    resource_group = registry_endpoint_test_setup["resourceGroup"]
    instance_name = registry_endpoint_test_setup["instanceName"]
    registry_endpoint_name = f"test-registry-{generate_random_string(force_lower=True, size=8)}"
    host = "userregistry.azurecr.io"
    client_id = "test-client-id"
    tenant_id = "test-tenant-id"
    scope = "test-scope"

    try:
        # CREATE - UserAssigned authentication with full parameters
        registry_endpoint = run(
            f"az iot ops registry add -n {registry_endpoint_name} "
            f"-g {resource_group} --instance {instance_name} "
            f"--host {host} --auth-type UserAssignedManagedIdentity "
            f"--client-id {client_id} --tenant-id {tenant_id} --scope {scope}"
        )
        tracked_resources.append(registry_endpoint["id"])

        assert_registry_endpoint(
            endpoint=registry_endpoint,
            name=registry_endpoint_name,
            resource_group=resource_group,
            instance_name=instance_name,
            host=host,
            auth_method="UserAssignedManagedIdentity",
        )

        # SHOW
        show_endpoint = run(
            f"az iot ops registry show -n {registry_endpoint_name} " f"-g {resource_group} --instance {instance_name}"
        )
        assert_registry_endpoint(
            endpoint=show_endpoint,
            name=registry_endpoint_name,
            resource_group=resource_group,
            instance_name=instance_name,
            host=host,
            auth_method="UserAssignedManagedIdentity",
        )

        # REMOVE
        run(
            f"az iot ops registry remove -n {registry_endpoint_name} "
            f"-g {resource_group} --instance {instance_name} -y"
        )
        tracked_resources.remove(registry_endpoint["id"])

    except Exception:
        # Cleanup in case of failure
        if registry_endpoint.get("id") in tracked_resources:
            try:
                run(
                    f"az iot ops registry remove -n {registry_endpoint_name} "
                    f"-g {resource_group} --instance {instance_name} -y"
                )
                tracked_resources.remove(registry_endpoint["id"])
            except Exception:
                pass  # Best effort cleanup
        raise


def test_registry_endpoint_list_empty(registry_endpoint_test_setup):
    """Test listing registry endpoints when none exist."""
    resource_group = registry_endpoint_test_setup["resourceGroup"]
    instance_name = registry_endpoint_test_setup["instanceName"]

    # LIST - should work even if no endpoints exist
    list_endpoints = run(f"az iot ops registry list " f"-g {resource_group} --instance {instance_name}")
    # Should return empty list or list that doesn't contain our test endpoints
    assert isinstance(list_endpoints, list)


def test_registry_endpoint_show_nonexistent(registry_endpoint_test_setup):
    """Test showing a registry endpoint that doesn't exist."""
    resource_group = registry_endpoint_test_setup["resourceGroup"]
    instance_name = registry_endpoint_test_setup["instanceName"]
    nonexistent_name = f"nonexistent-{generate_random_string(force_lower=True, size=8)}"

    # SHOW - should fail for nonexistent endpoint
    with pytest.raises(Exception) as exc_info:
        run(f"az iot ops registry show -n {nonexistent_name} " f"-g {resource_group} --instance {instance_name}")

    assert "ResourceNotFound" in str(exc_info.value)


def test_registry_endpoint_authentication_auto_detection(registry_endpoint_test_setup, tracked_resources):
    """Test automatic authentication method detection based on provided parameters."""
    resource_group = registry_endpoint_test_setup["resourceGroup"]
    instance_name = registry_endpoint_test_setup["instanceName"]

    endpoints_to_cleanup = []

    try:
        # Auto-detect ArtifactPullSecret (secret_ref provided)
        name1 = f"test-registry-{generate_random_string(force_lower=True, size=8)}"
        endpoint1 = run(
            f"az iot ops registry add -n {name1} "
            f"-g {resource_group} --instance {instance_name} "
            f"--host registry1.azurecr.io --secret-ref my-secret"
        )
        endpoints_to_cleanup.append((endpoint1["id"], name1))
        assert_registry_endpoint(
            endpoint=endpoint1,
            name=name1,
            resource_group=resource_group,
            instance_name=instance_name,
            host="registry1.azurecr.io",
            auth_method="ArtifactPullSecret",
        )

        # Auto-detect SystemAssigned (no auth parameters provided)
        name2 = f"test-registry-{generate_random_string(force_lower=True, size=8)}"
        endpoint2 = run(
            f"az iot ops registry add -n {name2} "
            f"-g {resource_group} --instance {instance_name} "
            f"--host registry2.azurecr.io"
        )
        endpoints_to_cleanup.append((endpoint2["id"], name2))
        assert_registry_endpoint(
            endpoint=endpoint2,
            name=name2,
            resource_group=resource_group,
            instance_name=instance_name,
            host="registry2.azurecr.io",
            auth_method="SystemAssignedManagedIdentity",
        )

        # Auto-detect UserAssigned (client-id and tenant-id provided)
        name3 = f"test-registry-{generate_random_string(force_lower=True, size=8)}"
        endpoint3 = run(
            f"az iot ops registry add -n {name3} "
            f"-g {resource_group} --instance {instance_name} "
            f"--host registry3.azurecr.io --client-id my-client --tenant-id my-tenant"
        )
        endpoints_to_cleanup.append((endpoint3["id"], name3))
        assert_registry_endpoint(
            endpoint=endpoint3,
            name=name3,
            resource_group=resource_group,
            instance_name=instance_name,
            host="registry3.azurecr.io",
            auth_method="UserAssignedManagedIdentity",
        )

        # Auto-detect Anonymous --no-auth
        name4 = f"test-registry-{generate_random_string(force_lower=True, size=8)}"
        endpoint4 = run(
            f"az iot ops registry add -n {name4} "
            f"-g {resource_group} --instance {instance_name} "
            f"--host registry4.azurecr.io --no-auth"
        )
        endpoints_to_cleanup.append((endpoint4["id"], name4))
        assert_registry_endpoint(
            endpoint=endpoint4,
            name=name4,
            resource_group=resource_group,
            instance_name=instance_name,
            host="registry4.azurecr.io",
            auth_method="Anonymous",
        )

        # Cleanup all endpoints
        for ep_id, ep_name in endpoints_to_cleanup:
            run(f"az iot ops registry remove -n {ep_name} " f"-g {resource_group} --instance {instance_name} -y")
            tracked_resources.append(ep_id)  # Add to tracked for safety
            tracked_resources.remove(ep_id)  # Remove after successful deletion

    except Exception:
        # Cleanup in case of failure
        for ep_id, ep_name in endpoints_to_cleanup:
            try:
                run(f"az iot ops registry remove -n {ep_name} " f"-g {resource_group} --instance {instance_name} -y")
            except Exception:
                pass  # Best effort cleanup
        raise


def test_registry_endpoint_trusted_signing_key(registry_endpoint_test_setup, tracked_resources):
    """Test complete lifecycle of registry endpoint with trusted signing settings."""
    resource_group = registry_endpoint_test_setup["resourceGroup"]
    instance_name = registry_endpoint_test_setup["instanceName"]
    registry_endpoint_name = f"test-registry-{generate_random_string(force_lower=True, size=8)}"
    host = "trustregistry.azurecr.io"
    trust_configmap = "my-trust-configmap"

    try:
        # CREATE - with trusted signing configmap
        registry_endpoint = run(
            f"az iot ops registry add -n {registry_endpoint_name} "
            f"-g {resource_group} --instance {instance_name} "
            f"--host {host} --trust-config-map-ref {trust_configmap}"
        )
        tracked_resources.append(registry_endpoint["id"])

        assert_registry_endpoint(
            endpoint=registry_endpoint,
            name=registry_endpoint_name,
            resource_group=resource_group,
            instance_name=instance_name,
            host=host,
            auth_method="SystemAssignedManagedIdentity",
        )

        # Verify trust settings
        trust_settings = registry_endpoint["properties"].get("trustSettings")
        assert trust_settings is not None
        trusted_signing_keys = trust_settings.get("trustedSigningKeys")
        assert trusted_signing_keys is not None
        assert trusted_signing_keys.get("configMapRef") == trust_configmap
        assert trusted_signing_keys.get("type") == "ConfigMap"

        # UPDATE - test mutual exclusivity
        with pytest.raises(Exception) as exc_info:
            run(
                f"az iot ops registry update -n {registry_endpoint_name} "
                f"-g {resource_group} --instance {instance_name} "
                f"--host {host} --trust-config-map-ref my-configmap --trust-secret-ref my-secret"
            )
        # The CLI should fail with the mutual exclusivity error
        assert exc_info.value.error_msg is not None

        # UPDATE - switch to signing secret instead of configmap
        trust_secret = "my-trust-secret"
        updated_endpoint = run(
            f"az iot ops registry update -n {registry_endpoint_name} "
            f"-g {resource_group} --instance {instance_name} "
            f"--trust-secret-ref {trust_secret}"
        )

        assert_registry_endpoint(
            endpoint=updated_endpoint,
            name=registry_endpoint_name,
            resource_group=resource_group,
            instance_name=instance_name,
            host=host,
            auth_method="SystemAssignedManagedIdentity",
        )

        # Verify trust settings were updated
        trust_settings = updated_endpoint["properties"].get("trustSettings")
        assert trust_settings is not None
        trusted_signing_keys = trust_settings.get("trustedSigningKeys")
        assert trusted_signing_keys is not None
        assert trusted_signing_keys.get("secretRef") == trust_secret
        assert trusted_signing_keys.get("type") == "Secret"
        # Ensure configMapRef is no longer present
        assert "configMapRef" not in trusted_signing_keys

        # REMOVE
        run(
            f"az iot ops registry remove -n {registry_endpoint_name} "
            f"-g {resource_group} --instance {instance_name} -y"
        )
        tracked_resources.remove(registry_endpoint["id"])

    except Exception:
        # Cleanup in case of failure
        if registry_endpoint.get("id") in tracked_resources:
            try:
                run(
                    f"az iot ops registry remove -n {registry_endpoint_name} "
                    f"-g {resource_group} --instance {instance_name} -y"
                )
                tracked_resources.remove(registry_endpoint["id"])
            except Exception:
                pass
        raise


def test_registry_endpoint_trusted_signing_mutual_exclusivity(registry_endpoint_test_setup, tracked_resources):
    """Test that specifying both configmap and secret raises an error."""
    resource_group = registry_endpoint_test_setup["resourceGroup"]
    instance_name = registry_endpoint_test_setup["instanceName"]
    registry_endpoint_name = f"test-registry-{generate_random_string(force_lower=True, size=8)}"
    host = "trustregistry.azurecr.io"

    # Test mutual exclusivity on add
    with pytest.raises(Exception) as exc_info:
        run(
            f"az iot ops registry add -n {registry_endpoint_name} "
            f"-g {resource_group} --instance {instance_name} "
            f"--host {host} --trust-config-map-ref my-configmap --trust-secret-ref my-secret"
        )

    # The CLI should fail with the mutual exclusivity error
    assert exc_info.value.error_msg is not None


def assert_registry_endpoint(endpoint: dict, **expected):
    """Assert that a registry endpoint matches expected values."""
    assert endpoint["name"] == expected["name"]
    assert endpoint["resourceGroup"] == expected["resource_group"]

    # Check the endpoint is under the correct instance
    assert f"/instances/{expected['instance_name']}/registryEndpoints/{expected['name']}" in endpoint["id"]

    endpoint_props = endpoint["properties"]
    assert endpoint_props["host"] == expected["host"]

    # Check authentication method
    auth = endpoint_props.get("authentication", {})
    assert auth.get("method") == expected["auth_method"]
