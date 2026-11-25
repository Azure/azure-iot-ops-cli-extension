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
