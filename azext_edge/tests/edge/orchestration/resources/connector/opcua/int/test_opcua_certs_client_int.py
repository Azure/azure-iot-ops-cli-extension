# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from azext_edge.edge.providers.orchestration.resources.connector.opcua.certs import OPCUA_CLIENT_CERT_SECRET_SYNC_NAME
from .helpers import (
    assert_cluster_side_secret_exists,
    assert_cluster_side_secret_not_exists,
    assert_kv_secret_exists,
    assert_kv_secret_not_exists,
    assert_spc_secret_exists,
    assert_spc_secret_not_exists,
    assert_ssc_secret_exists,
    assert_ssc_secret_not_exists,
    cleanup_test_resources,
    ensure_env_vars,
    ensure_key_vault,
    ensure_managed_identity,
    ensure_secretsync_enabled,
    generate_self_signed_der_cert_with_uri,
    generate_self_signed_pem_cert,
)
import pytest
from knack.log import get_logger
from typing import List

from .......helpers import run

logger = get_logger(__name__)
ROLE_MAX_RETRIES = 5
ROLE_RETRY_INTERVAL = 15


@pytest.fixture(scope="function")
def opcua_certs_client_test_setup(settings, tracked_resources: List[str]):
    """Setup fixture for opcua certs client tests."""

    ensure_env_vars(settings)
    kv_id, kv_name = ensure_key_vault(settings)
    mi_id = ensure_managed_identity(settings, tracked_resources)
    instance_name = settings.env.azext_edge_instance
    resource_group = settings.env.azext_edge_rg

    # Ensure secretsync is enabled with a valid Key Vault
    spc_name = ensure_secretsync_enabled(settings, instance_name, resource_group, kv_id, mi_id)

    yield {
        "resourceGroup": resource_group,
        "instanceName": instance_name,
        "keyvaultId": kv_id,
        "userAssignedId": mi_id,
        "spcName": spc_name,
    }

    # Clean up only the resources we created during this test
    cleanup_test_resources(settings, kv_name)


@pytest.mark.require_wlif_setup
def test_opcua_cert_client(cluster_connection, opcua_certs_client_test_setup, tracked_files: List[str]):
    resource_group = opcua_certs_client_test_setup["resourceGroup"]
    instance_name = opcua_certs_client_test_setup["instanceName"]
    kv_id = opcua_certs_client_test_setup["keyvaultId"]

    instance_info = run(f"az iot ops show -g {resource_group} -n {instance_name}")
    extended_loc = instance_info["extendedLocation"]["name"]  # type: ignore[index]
    spc_name = instance_info["properties"].get(  # type: ignore[union-attr]
        "defaultSecretProviderClassRef", {}
    ).get("resourceId", "")
    # get last part of the id
    if spc_name:
        spc_name = spc_name.rsplit("/", maxsplit=1)[-1]

    # add cert to client certs
    public_key_file = generate_self_signed_der_cert_with_uri()
    # create a private key file too with same name but .pem extension, copy the public key content into it
    private_key_file = generate_self_signed_pem_cert()
    run(f"az iot ops connector opcua client add --instance {instance_name} -g {resource_group} \
        --public-key-file {public_key_file} --private-key-file {private_key_file} --overwrite-secret")
    secretsync_records = run(f"az iot ops secretsync list -i {instance_name} -g {resource_group}")

    # check kv secret has been created
    for cert_file in [public_key_file, private_key_file]:
        assert_kv_secret_exists(kv_id=kv_id, cert_file=cert_file)
        # check secret entry exist in spc
        assert_spc_secret_exists(
            spc_records=secretsync_records,
            spc_name=spc_name,
            instance_name=instance_name,
            resource_group=resource_group,
            cert_file=public_key_file
        )
        # check secret entry exist in secretsync
        assert_ssc_secret_exists(
            secretsync_records=secretsync_records,
            extended_location=extended_loc,
            resource_group=resource_group,
            cert_file=cert_file,
            ssc_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
        )
        # check cluster side secret is being synced
        assert_cluster_side_secret_exists(
            spc_name=spc_name,
            secret_sync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
            cert_file=public_key_file,
        )

    # show secret sync
    show_result = run(f"az iot ops connector opcua client show --instance {instance_name} -g {resource_group}")
    assert show_result["name"] == OPCUA_CLIENT_CERT_SECRET_SYNC_NAME  # type: ignore[index]

    # remove certs from client certs
    public_certificate_name = public_key_file.name
    private_certificate_name = private_key_file.name
    run(
        f"az iot ops connector opcua client remove --instance {instance_name} \
          -g {resource_group} --certificate-names {public_certificate_name} {private_certificate_name} \
          -y --include-secrets"
    )
    # get refreshed secretsync records after removal
    secretsync_records = run(f"az iot ops secretsync list -i {instance_name} -g {resource_group}")
    # check kv secret has been removed
    for cert_file in [public_key_file, private_key_file]:
        certificate_name = cert_file.name
        assert_kv_secret_not_exists(kv_id=kv_id, cert_file=certificate_name)
        # check secret entry removed from spc
        assert_spc_secret_not_exists(
            secretsync_records=secretsync_records,
            spc_name=spc_name,
            cert_file=certificate_name
        )
        # check secret entry removed from secretsync
        assert_ssc_secret_not_exists(
            secretsync_records=secretsync_records,
            extended_location=extended_loc,
            resource_group=resource_group,
            cert_file=certificate_name,
            ssc_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
        )
        # # check cluster side secret is removed
        assert_cluster_side_secret_not_exists(
            spc_name=spc_name,
            secret_sync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
        )

    # clean up the cert files created
    for cert_file in [public_key_file, private_key_file]:
        cert_file.unlink(missing_ok=True)
