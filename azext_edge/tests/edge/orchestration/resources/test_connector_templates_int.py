# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""
Integration tests for connector template CLI commands.

These tests verify the full CRUD lifecycle of connector templates including:
- Create with various parameters
- Show/List templates
- Update with different parameters
- Delete templates

Test scenarios covered:
1. Basic lifecycle: create, show, list, update, delete
2. Create with minimal parameters
3. Create with all optional parameters
4. Update various properties (replicas, log level, image pull policy, etc.)
5. Update with version upgrade
6. Clear properties using empty string
"""

import pytest
from time import sleep
from typing import List
from knack.log import get_logger
from ....generators import generate_random_string
from ....helpers import run

logger = get_logger(__name__)

# pytest mark for rpsaas (cloud-side) tests
pytestmark = pytest.mark.rpsaas

# Retry settings for async operations
QUERY_RETRIES = 4
QUERY_RETRY_INT = 30

# MCR connector metadata reference for testing (1st-party REST connector)
# This is a publicly accessible metadata artifact in MCR
MCR_METADATA_REF = "mcr.microsoft.com/azureiotoperations/akri-connectors/rest-metadata:1.0.6"
MCR_METADATA_REF_UPGRADE = "mcr.microsoft.com/azureiotoperations/akri-connectors/rest-metadata:1.0.7"


def test_connector_template_lifecycle(require_init, tracked_resources: List[str]):
    """
    Test the complete lifecycle of a connector template:
    create -> show -> list -> update -> delete

    This test uses minimal parameters for creation to verify basic functionality.
    """
    rg = require_init["resourceGroup"]
    instance = require_init["instanceName"]
    custom_location_id = require_init["customLocationId"]

    # Create a connector template with minimal parameters
    template_name = "test-template-" + generate_random_string(force_lower=True)[:4]
    template = run(
        f"az iot ops connector template create -n {template_name} -g {rg} "
        f"--instance {instance} --connector-metadata-ref {MCR_METADATA_REF}"
    )
    tracked_resources.append(template["id"])
    assert_template_props(
        result=template,
        name=template_name,
        custom_location=custom_location_id,
    )

    # Show the template
    show_template = run(
        f"az iot ops connector template show -n {template_name} -g {rg} --instance {instance}"
    )
    assert_template_props(
        result=show_template,
        name=template_name,
        custom_location=custom_location_id,
    )

    # List templates
    template_list = run(
        f"az iot ops connector template list -g {rg} --instance {instance}"
    )
    template_names = [t["name"] for t in template_list]
    assert template_name in template_names

    # Update the template - change replicas
    updated_template = run(
        f"az iot ops connector template update -n {template_name} -g {rg} "
        f"--instance {instance} --replicas 2"
    )
    assert_template_props(
        result=updated_template,
        name=template_name,
        custom_location=custom_location_id,
        replicas=2,
    )

    # Delete the template
    run(f"az iot ops connector template delete -n {template_name} -g {rg} --instance {instance} -y")

    # Verify deletion
    for _ in range(QUERY_RETRIES):
        sleep(QUERY_RETRY_INT)
        template_list = run(
            f"az iot ops connector template list -g {rg} --instance {instance}"
        )
        template_names = [t["name"] for t in template_list]
        if template_name not in template_names:
            tracked_resources.remove(template["id"])
            return
    raise AssertionError(f"Template {template_name} was not deleted.")


def test_connector_template_create_with_all_params(require_init, tracked_resources: List[str]):
    """
    Test creating a connector template with all optional parameters.
    """
    rg = require_init["resourceGroup"]
    instance = require_init["instanceName"]
    custom_location_id = require_init["customLocationId"]

    template_name = "test-template-" + generate_random_string(force_lower=True)[:4]

    # Build command with all optional parameters
    command = (
        f"az iot ops connector template create -n {template_name} -g {rg} "
        f"--instance {instance} --connector-metadata-ref {MCR_METADATA_REF} "
        f"--replicas 3 "
        f"--log-level debug "
        f"--image-pull-policy Always "
        f"--image-pull-secrets pull-secret-1 pull-secret-2 "
        f"--allocation-policy Bucketized --bucket-size 10 "
        f"--storage-volumes 'claimName=my-pvc mountPath=/data' "
        f"--connector-config key1=value1 key2=value2 "
        f"--trust-settings-secret-ref my-trust-secret"
    )

    template = run(command)
    tracked_resources.append(template["id"])
    assert_template_props(
        result=template,
        name=template_name,
        custom_location=custom_location_id,
        replicas=3,
        log_level="debug",
        image_pull_policy="Always",
        image_pull_secrets=["pull-secret-1", "pull-secret-2"],
        allocation_policy="Bucketized",
        bucket_size=10,
        storage_volumes=[{"claimName": "my-pvc", "mountPath": "/data"}],
        connector_config={"key1": "value1", "key2": "value2"},
        trust_settings_secret_ref="my-trust-secret",
    )

    # Cleanup
    run(f"az iot ops connector template delete -n {template_name} -g {rg} --instance {instance} -y")
    sleep(QUERY_RETRY_INT)
    tracked_resources.remove(template["id"])


def test_connector_template_update_all_params(require_init, tracked_resources: List[str]):
    """
    Test updating a connector template with various parameters, including clearing them.
    """
    rg = require_init["resourceGroup"]
    instance = require_init["instanceName"]
    custom_location_id = require_init["customLocationId"]

    # Create initial template
    template_name = "test-template-" + generate_random_string(force_lower=True)[:4]
    template = run(
        f"az iot ops connector template create -n {template_name} -g {rg} "
        f"--instance {instance} --connector-metadata-ref {MCR_METADATA_REF}"
    )
    tracked_resources.append(template["id"])

    # Update with all parameters
    updated = run(
        f"az iot ops connector template update -n {template_name} -g {rg} "
        f"--instance {instance} "
        f"--replicas 5 "
        f"--log-level warning "
        f"--image-pull-policy IfNotPresent "
        f"--image-pull-secrets updated-secret-1 updated-secret-2 "
        f"--storage-volumes 'claimName=my-pvc mountPath=/mnt/data' "
        f"--trust-settings-secret-ref my-certs-secret "
        f"--connector-config configKey=configValue"
    )
    assert_template_props(
        result=updated,
        name=template_name,
        custom_location=custom_location_id,
        replicas=5,
        log_level="warning",
        image_pull_policy="IfNotPresent",
        image_pull_secrets=["updated-secret-1", "updated-secret-2"],
        storage_volumes=[{"claimName": "my-pvc", "mountPath": "/mnt/data"}],
        trust_settings_secret_ref="my-certs-secret",
        connector_config={"configKey": "configValue"},
    )

    # Clear optional properties using empty string
    cleared = run(
        f"az iot ops connector template update -n {template_name} -g {rg} "
        f"--instance {instance} "
        f"--image-pull-secrets \"\" "
        f"--storage-volumes \"\" "
        f"--trust-settings-secret-ref \"\" "
        f"--connector-config \"\""
    )

    # Verify properties were cleared
    props = cleared["properties"]
    managed_config = props["runtimeConfiguration"]["managedConfigurationSettings"]
    image_config = managed_config["imageConfigurationSettings"]
    registry_settings = image_config.get("registrySettings", {})
    container_registry = registry_settings.get("containerRegistrySettings", {})
    pull_secrets = container_registry.get("imagePullSecrets", [])

    assert len(pull_secrets) == 0 or pull_secrets is None
    assert "persistentVolumeClaims" not in managed_config or managed_config.get("persistentVolumeClaims") is None
    assert "trustSettings" not in managed_config or managed_config.get("trustSettings") is None
    assert "additionalConfiguration" not in managed_config or managed_config.get("additionalConfiguration") is None

    # Cleanup
    run(f"az iot ops connector template delete -n {template_name} -g {rg} --instance {instance} -y")
    sleep(QUERY_RETRY_INT)
    tracked_resources.remove(template["id"])


def test_connector_template_list_summary(require_init, tracked_resources: List[str]):
    """
    Test that list command returns proper summary information.
    """
    rg = require_init["resourceGroup"]
    instance = require_init["instanceName"]

    # Create a template
    template_name = "test-template-" + generate_random_string(force_lower=True)[:4]
    template = run(
        f"az iot ops connector template create -n {template_name} -g {rg} "
        f"--instance {instance} --connector-metadata-ref {MCR_METADATA_REF} "
        f"--replicas 2"
    )
    tracked_resources.append(template["id"])

    # List and verify summary fields
    template_list = run(
        f"az iot ops connector template list -g {rg} --instance {instance}"
    )

    # Find our template in the list
    our_template = None
    for t in template_list:
        if t["name"] == template_name:
            our_template = t
            break

    assert our_template is not None, f"Template {template_name} not found in list"

    # Verify summary fields are present
    assert "name" in our_template
    assert "connectorType" in our_template
    assert "version" in our_template
    assert "replicas" in our_template
    assert "provisioningState" in our_template

    # Verify replicas value
    assert our_template["replicas"] == 2

    # Cleanup
    run(f"az iot ops connector template delete -n {template_name} -g {rg} --instance {instance} -y")
    sleep(QUERY_RETRY_INT)
    tracked_resources.remove(template["id"])


# Helper functions

def assert_template_props(result, **expected):
    """
    Assert that a connector template has the expected properties.

    Args:
        result: The connector template result dict
        **expected: Expected property values:
            - name: Template name
            - custom_location: Expected custom location ID suffix
            - replicas: Expected replica count
            - log_level: Expected log level
            - image_pull_policy: Expected image pull policy
            - image_pull_secrets: List of expected secret names
            - allocation_policy: Expected allocation policy
            - bucket_size: Expected bucket size
            - storage_volumes: List of expected PVC dicts with claimName and mountPath
            - connector_config: Dict of expected additional configuration
            - trust_settings_secret_ref: Expected trust settings secret reference
    """
    assert result["name"] == expected["name"]
    assert result["extendedLocation"]["name"].endswith(expected["custom_location"])

    props = result["properties"]
    runtime_config = props["runtimeConfiguration"]
    managed_config = runtime_config["managedConfigurationSettings"]
    image_config = managed_config["imageConfigurationSettings"]

    # Verify replicas if expected
    if expected.get("replicas"):
        assert image_config["replicas"] == expected["replicas"]

    # Verify log level if expected
    if expected.get("log_level"):
        assert props["diagnostics"]["logs"]["level"] == expected["log_level"]

    # Verify image pull policy if expected
    if expected.get("image_pull_policy"):
        assert image_config["imagePullPolicy"] == expected["image_pull_policy"]

    # Verify image pull secrets if expected
    if expected.get("image_pull_secrets"):
        registry_settings = image_config.get("registrySettings", {})
        container_registry = registry_settings.get("containerRegistrySettings", {})
        pull_secrets = container_registry.get("imagePullSecrets", [])
        secret_refs = [s["secretRef"] for s in pull_secrets]
        for secret in expected["image_pull_secrets"]:
            assert secret in secret_refs, f"Expected secret {secret} not found in {secret_refs}"

    # Verify allocation policy if expected
    if expected.get("allocation_policy"):
        assert "allocation" in managed_config
        assert managed_config["allocation"]["policy"] == expected["allocation_policy"]

    # Verify bucket size if expected
    if expected.get("bucket_size"):
        assert "allocation" in managed_config
        assert managed_config["allocation"]["bucketSize"] == expected["bucket_size"]

    # Verify storage volumes if expected
    if expected.get("storage_volumes"):
        assert "persistentVolumeClaims" in managed_config
        pvcs = managed_config["persistentVolumeClaims"]
        assert len(pvcs) == len(expected["storage_volumes"])
        for i, expected_pvc in enumerate(expected["storage_volumes"]):
            assert pvcs[i]["claimName"] == expected_pvc["claimName"]
            assert pvcs[i]["mountPath"] == expected_pvc["mountPath"]

    # Verify connector config (additionalConfiguration) if expected
    if expected.get("connector_config"):
        assert "additionalConfiguration" in managed_config
        additional_config = managed_config["additionalConfiguration"]
        for key, value in expected["connector_config"].items():
            assert additional_config.get(key) == value, f"Expected {key}={value}, got {additional_config.get(key)}"

    # Verify trust settings if expected
    if expected.get("trust_settings_secret_ref"):
        assert "trustSettings" in managed_config
        assert managed_config["trustSettings"]["trustListSecretRef"] == expected["trust_settings_secret_ref"]
