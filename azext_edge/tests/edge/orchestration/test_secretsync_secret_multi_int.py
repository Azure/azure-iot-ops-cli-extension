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
