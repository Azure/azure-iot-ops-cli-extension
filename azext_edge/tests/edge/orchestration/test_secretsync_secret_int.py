# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from typing import List
from uuid import uuid4

from azure.cli.core.azclierror import CLIInternalError

from ...generators import generate_random_string
from ...helpers import run, wait_for_expected_count

logger = get_logger(__name__)

# pytest mark for rpsaas (cloud-side) tests
pytestmark = pytest.mark.rpsaas


@pytest.fixture
def secretsync_secret_int_setup(settings, tracked_resources: List[str]):
    """
    Setup fixture that ensures:
    - An instance with secretsync enabled exists.
    - A test AKV secret is available for syncing.
    Returns dict with resourceGroup, instanceName, keyvaultName, etc.
    """
    from ...settings import EnvironmentVariables

    settings.add_to_config(EnvironmentVariables.rg.value)
    settings.add_to_config(EnvironmentVariables.instance.value)
    settings.add_to_config(EnvironmentVariables.kv.value)
    settings.add_to_config(EnvironmentVariables.user_assigned_mi_id.value)

    if not all([settings.env.azext_edge_instance, settings.env.azext_edge_rg]):
        pytest.skip("Cannot run secretsync secret tests without an instance and resource group.")
    if not settings.env.azext_edge_kv:
        pytest.skip("Cannot run secretsync secret tests without a keyvault id.")

    instance_name = settings.env.azext_edge_instance
    resource_group = settings.env.azext_edge_rg
    kv_id = settings.env.azext_edge_kv
    kv_name = kv_id.rsplit("/", maxsplit=1)[-1]

    # Verify secretsync is enabled; enable it with the provided identity when it is not.
    list_cmd = f"az iot ops secretsync list -n {instance_name} -g {resource_group}"
    list_result = run(list_cmd)
    mi_id = settings.env.azext_edge_user_assigned_mi_id
    if not list_result and mi_id:
        run(
            f"az iot ops secretsync enable -n {instance_name} -g {resource_group} "
            f"--mi-user-assigned {mi_id} --kv-resource-id {kv_id} --skip-ra"
        )
        list_result = wait_for_expected_count(list_cmd, expected_count=1, max_retries=20, initial_interval=5)
    if not list_result:
        pytest.skip("Secretsync is not enabled on the instance. Enable it first.")

    # Create test AKV secrets for use in tests
    test_secrets = {}
    for _ in range(3):
        secret_name = f"clitest{str(uuid4()).replace('-', '')[:12]}"
        secret_value = generate_random_string(size=32)
        try:
            run(
                f"az keyvault secret set --vault-name {kv_name} --name {secret_name} "
                f"--value {secret_value}"
            )
            test_secrets[secret_name] = secret_value
        except CLIInternalError as e:
            logger.warning(f"Failed to create test secret {secret_name}: {e.error_msg}")

    if len(test_secrets) < 2:
        pytest.skip("Could not create enough test secrets in the Key Vault.")

    yield {
        "resourceGroup": resource_group,
        "instanceName": instance_name,
        "keyvaultName": kv_name,
        "testSecrets": test_secrets,
    }

    # Cleanup: remove test secrets from AKV
    for secret_name in test_secrets:
        try:
            run(f"az keyvault secret delete --vault-name {kv_name} --name {secret_name}")
        except CLIInternalError:
            logger.warning(f"Failed to delete test secret {secret_name}")
            continue
        try:
            # Best-effort purge to avoid soft-delete accumulation and naming collisions on re-runs
            run(f"az keyvault secret purge --vault-name {kv_name} --name {secret_name}")
        except CLIInternalError:
            logger.warning(f"Failed to purge test secret {secret_name} (vault may not support purge)")


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
def test_secretsync_secret_set_multiple_at_once(
    cluster_connection,
    secretsync_secret_int_setup,
):
    """Test setting multiple secrets in a single command invocation."""
    resource_group = secretsync_secret_int_setup["resourceGroup"]
    instance_name = secretsync_secret_int_setup["instanceName"]
    test_secrets = secretsync_secret_int_setup["testSecrets"]
    secret_names = list(test_secrets.keys())

    sync_name = f"cli-test-multi-{generate_random_string(size=6, force_lower=True)}"

    try:
        # Set multiple secrets at once
        secret_args = " ".join(
            f"--secret-map {name}=key{i}" for i, name in enumerate(secret_names[:2])
        )
        set_result = run(
            f"az iot ops secretsync secret set "
            f"--instance {instance_name} -g {resource_group} "
            f"--secret-sync-name {sync_name} "
            f"{secret_args}"
        )
        assert set_result is not None
        mappings = set_result.get("properties", {}).get("objectSecretMapping", [])
        assert len(mappings) == 2

        # Cleanup: remove all secrets (last one deletes the SS)
        for name in secret_names[:2]:
            run(
                f"az iot ops secretsync secret remove "
                f"--instance {instance_name} -g {resource_group} "
                f"--secret-sync-name {sync_name} "
                f"--secret-name {name} -y"
            )

    except Exception:
        # Best effort cleanup
        for name in secret_names[:2]:
            try:
                run(
                    f"az iot ops secretsync secret remove "
                    f"--instance {instance_name} -g {resource_group} "
                    f"--secret-sync-name {sync_name} "
                    f"--secret-name {name} -y",
                    expect_failure=True,
                )
            except CLIInternalError:
                pass
        raise


@pytest.mark.require_wlif_setup
def test_secretsync_secret_set_multikey_mapping(
    cluster_connection,
    secretsync_secret_int_setup,
):
    """Test that the same AKV secret can be mapped to multiple target keys."""
    resource_group = secretsync_secret_int_setup["resourceGroup"]
    instance_name = secretsync_secret_int_setup["instanceName"]
    test_secrets = secretsync_secret_int_setup["testSecrets"]
    secret_names = list(test_secrets.keys())

    sync_name = f"cli-test-multikey-{generate_random_string(size=6, force_lower=True)}"
    first_secret = secret_names[0]

    try:
        # Set the same secret with targetKey "certificate"
        set_result = run(
            f"az iot ops secretsync secret set "
            f"--instance {instance_name} -g {resource_group} "
            f"--secret-sync-name {sync_name} "
            f"--secret-map {first_secret}=certificate"
        )
        mappings = set_result.get("properties", {}).get("objectSecretMapping", [])
        assert len(mappings) == 1

        # Set the same secret again with a different targetKey "cert-copy"
        merge_result = run(
            f"az iot ops secretsync secret set "
            f"--instance {instance_name} -g {resource_group} "
            f"--secret-sync-name {sync_name} "
            f"--secret-map {first_secret}=cert-copy"
        )
        merge_mappings = merge_result.get("properties", {}).get("objectSecretMapping", [])
        # Should have 2 entries: same sourcePath, different targetKeys
        assert len(merge_mappings) == 2
        target_keys = {m["targetKey"] for m in merge_mappings}
        assert "certificate" in target_keys
        assert "cert-copy" in target_keys
        assert all(m["sourcePath"] == first_secret for m in merge_mappings)

        # Idempotency: set the same sourcePath+targetKey combo again — should not duplicate
        idem_result = run(
            f"az iot ops secretsync secret set "
            f"--instance {instance_name} -g {resource_group} "
            f"--secret-sync-name {sync_name} "
            f"--secret-map {first_secret}=certificate"
        )
        idem_mappings = idem_result.get("properties", {}).get("objectSecretMapping", [])
        assert len(idem_mappings) == 2

        # Remove removes ALL mappings for the sourcePath
        remove_result = run(
            f"az iot ops secretsync secret remove "
            f"--instance {instance_name} -g {resource_group} "
            f"--secret-sync-name {sync_name} "
            f"--secret-name {first_secret} -y"
        )
        # All mappings removed, SecretSync should be deleted
        assert remove_result is None

    except Exception:
        try:
            run(
                f"az iot ops secretsync secret remove "
                f"--instance {instance_name} -g {resource_group} "
                f"--secret-sync-name {sync_name} "
                f"--secret-name {first_secret} -y",
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
