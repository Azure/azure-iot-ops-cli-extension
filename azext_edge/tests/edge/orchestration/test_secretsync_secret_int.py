# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from azure.cli.core.azclierror import CLIInternalError

from ...generators import generate_random_string
from ...helpers import run

# pytest mark for rpsaas (cloud-side) tests
pytestmark = pytest.mark.rpsaas


@pytest.mark.require_wlif_setup
def test_secretsync_secret_set_list_unset(
    cluster_connection,
    secretsync_secret_int_setup,
):
    """End-to-end test: set, list, merge, remove secrets in SecretSync."""
    resource_group = secretsync_secret_int_setup["resourceGroup"]
    instance_name = secretsync_secret_int_setup["instanceName"]
    test_secrets = secretsync_secret_int_setup["testSecrets"]
    secret_names = list(test_secrets.keys())

    # Use a unique SecretSync name for this test
    sync_name = f"cli-test-sync-{generate_random_string(size=6, force_lower=True)}"

    try:
        # --- Step 1: Set a single secret ---
        first_secret = secret_names[0]
        set_result = run(
            f"az iot ops secretsync secret set "
            f"--instance {instance_name} -g {resource_group} "
            f"--secret-sync-name {sync_name} "
            f"--secret-map {first_secret}=certificate"
        )
        assert set_result is not None
        assert set_result["name"] == sync_name
        mappings = set_result.get("properties", {}).get("objectSecretMapping", [])
        assert len(mappings) == 1
        assert mappings[0]["sourcePath"] == first_secret
        assert mappings[0]["targetKey"] == "certificate"

        # --- Step 2: List secrets ---
        list_result = run(
            f"az iot ops secretsync secret list "
            f"--instance {instance_name} -g {resource_group} "
            f"--secret-sync-name {sync_name}"
        )
        assert list_result is not None
        assert len(list_result) == 1
        assert list_result[0]["sourcePath"] == first_secret

        # --- Step 3: Merge another secret into the same SecretSync ---
        second_secret = secret_names[1]
        merge_result = run(
            f"az iot ops secretsync secret set "
            f"--instance {instance_name} -g {resource_group} "
            f"--secret-sync-name {sync_name} "
            f"--secret-map {second_secret}=privateKey"
        )
        merge_mappings = merge_result.get("properties", {}).get("objectSecretMapping", [])
        assert len(merge_mappings) == 2
        source_paths = {m["sourcePath"] for m in merge_mappings}
        assert first_secret in source_paths
        assert second_secret in source_paths

        # --- Step 4: List again to verify both ---
        list_result2 = run(
            f"az iot ops secretsync secret list "
            f"--instance {instance_name} -g {resource_group} "
            f"--secret-sync-name {sync_name}"
        )
        assert len(list_result2) == 2

        # --- Step 5: Remove one secret ---
        remove_result = run(
            f"az iot ops secretsync secret remove "
            f"--instance {instance_name} -g {resource_group} "
            f"--secret-sync-name {sync_name} "
            f"--secret-name {first_secret} -y"
        )
        # Partial removal returns the updated SecretSync resource
        assert remove_result is not None
        remaining = remove_result.get("properties", {}).get("objectSecretMapping", [])
        assert len(remaining) == 1
        assert remaining[0]["sourcePath"] == second_secret

        # Verify via list
        list_result3 = run(
            f"az iot ops secretsync secret list "
            f"--instance {instance_name} -g {resource_group} "
            f"--secret-sync-name {sync_name}"
        )
        assert len(list_result3) == 1
        assert list_result3[0]["sourcePath"] == second_secret

        # --- Step 6: Remove the last secret (should delete the SecretSync) ---
        remove_last_result = run(
            f"az iot ops secretsync secret remove "
            f"--instance {instance_name} -g {resource_group} "
            f"--secret-sync-name {sync_name} "
            f"--secret-name {second_secret} -y"
        )
        # Full deletion returns None
        assert remove_last_result is None

    except Exception:
        # Best effort cleanup of the SecretSync if the test fails partway through
        try:
            run(
                f"az iot ops secretsync secret remove "
                f"--instance {instance_name} -g {resource_group} "
                f"--secret-sync-name {sync_name} "
                f"--secret-name {secret_names[0]} -y",
                expect_failure=True,
            )
        except CLIInternalError:
            pass
        try:
            run(
                f"az iot ops secretsync secret remove "
                f"--instance {instance_name} -g {resource_group} "
                f"--secret-sync-name {sync_name} "
                f"--secret-name {secret_names[1]} -y",
                expect_failure=True,
            )
        except CLIInternalError:
            pass
        raise


@pytest.mark.require_wlif_setup
def test_secretsync_secret_set_invalid_akv_secret(
    cluster_connection,
    secretsync_secret_int_setup,
):
    """Test that setting a nonexistent AKV secret raises an error."""
    resource_group = secretsync_secret_int_setup["resourceGroup"]
    instance_name = secretsync_secret_int_setup["instanceName"]

    sync_name = f"cli-test-invalid-{generate_random_string(size=6, force_lower=True)}"

    with pytest.raises(CLIInternalError, match="not found in Key Vault"):
        run(
            f"az iot ops secretsync secret set "
            f"--instance {instance_name} -g {resource_group} "
            f"--secret-sync-name {sync_name} "
            f"--secret-map nonexistentsecret{generate_random_string(size=8)}=certificate"
        )


@pytest.mark.require_wlif_setup
def test_secretsync_secret_remove_nonexistent(
    cluster_connection,
    secretsync_secret_int_setup,
):
    """Test that removing a nonexistent secret from an existing SecretSync raises an error."""
    resource_group = secretsync_secret_int_setup["resourceGroup"]
    instance_name = secretsync_secret_int_setup["instanceName"]
    test_secrets = secretsync_secret_int_setup["testSecrets"]
    secret_names = list(test_secrets.keys())

    sync_name = f"cli-test-remove-{generate_random_string(size=6, force_lower=True)}"

    try:
        # Create a SecretSync first
        run(
            f"az iot ops secretsync secret set "
            f"--instance {instance_name} -g {resource_group} "
            f"--secret-sync-name {sync_name} "
            f"--secret-map {secret_names[0]}=certificate"
        )

        # Try to remove a secret that doesn't exist in the SecretSync
        with pytest.raises(CLIInternalError, match="not found in SecretSync"):
            run(
                f"az iot ops secretsync secret remove "
                f"--instance {instance_name} -g {resource_group} "
                f"--secret-sync-name {sync_name} "
                f"--secret-name nonexistent_secret -y"
            )

    finally:
        # Cleanup
        try:
            run(
                f"az iot ops secretsync secret remove "
                f"--instance {instance_name} -g {resource_group} "
                f"--secret-sync-name {sync_name} "
                f"--secret-name {secret_names[0]} -y"
            )
        except CLIInternalError:
            pass
