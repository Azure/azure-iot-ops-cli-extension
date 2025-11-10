# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from azext_edge.edge.providers.orchestration.resources.connector.opcua.certs import OPCUA_TRUST_LIST_SECRET_SYNC_NAME
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
    generate_self_signed_der_cert,
)
import pytest
from knack.log import get_logger
from typing import List

from .......helpers import run

logger = get_logger(__name__)
ROLE_MAX_RETRIES = 5
ROLE_RETRY_INTERVAL = 15


@pytest.fixture(scope="function")
def opcua_certs_trust_test_setup(settings, tracked_resources: List[str]):
    """Setup fixture for opcua certs trust tests."""

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
def test_opcua_cert_trust(cluster_connection, opcua_certs_trust_test_setup, tracked_files: List[str]):
    resource_group = opcua_certs_trust_test_setup["resourceGroup"]
    instance_name = opcua_certs_trust_test_setup["instanceName"]
    kv_id = opcua_certs_trust_test_setup["keyvaultId"]

    instance_info = run(f"az iot ops show -g {resource_group} -n {instance_name}")
    extended_loc = instance_info["extendedLocation"]["name"]  # type: ignore[index]
    spc_name = instance_info["properties"].get(  # type: ignore[union-attr]
        "defaultSecretProviderClassRef", {}
    ).get("resourceId", "")
    # get last part of the id
    if spc_name:
        spc_name = spc_name.rsplit("/", maxsplit=1)[-1]

    # add cert to trust list
    cert_file = generate_self_signed_der_cert()
    run(f"az iot ops connector opcua trust add --instance {instance_name} \
        -g {resource_group} --certificate-file {cert_file} --overwrite-secret")
    secretsync_records = run(f"az iot ops secretsync list -i {instance_name} -g {resource_group}")

    # check kv secret has been created
    assert_kv_secret_exists(kv_id=kv_id, cert_file=cert_file)
    # check secret entry exist in spc
    assert_spc_secret_exists(
        spc_records=secretsync_records,
        spc_name=spc_name,
        instance_name=instance_name,
        resource_group=resource_group,
        cert_file=cert_file
    )
    # check secret entry exist in secretsync
    assert_ssc_secret_exists(
        secretsync_records=secretsync_records,
        extended_location=extended_loc,
        resource_group=resource_group,
        cert_file=cert_file,
        ssc_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
    )
    # check cluster side secret is being synced
    assert_cluster_side_secret_exists(
        spc_name=spc_name,
        secret_sync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
        cert_file=cert_file,
    )

    # show secret sync
    show_result = run(f"az iot ops connector opcua trust show --instance {instance_name} -g {resource_group}")
    assert show_result["name"] == OPCUA_TRUST_LIST_SECRET_SYNC_NAME  # type: ignore[index]

    # remove cert from trust list
    certificate_name = cert_file.name
    run(f"az iot ops connector opcua trust remove --instance {instance_name} -g {resource_group} \
        --certificate-names {certificate_name} -y --include-secrets")
    # get refreshed secretsync records after removal
    secretsync_records = run(f"az iot ops secretsync list -i {instance_name} -g {resource_group}")
    # check kv secret has been removed
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
        ssc_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
    )
    # check cluster side secret is removed
    assert_cluster_side_secret_not_exists(
        spc_name=spc_name,
        secret_sync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
    )
    # clean up the cert file created
    cert_file.unlink(missing_ok=True)


@pytest.mark.require_wlif_setup
def test_opcua_cert_trust_with_user_expiration(
    cluster_connection, opcua_certs_trust_test_setup, tracked_files: List[str]
):
    """Test adding certificate with user-provided expiration date."""
    from datetime import datetime, timezone, timedelta

    resource_group = opcua_certs_trust_test_setup["resourceGroup"]
    instance_name = opcua_certs_trust_test_setup["instanceName"]
    kv_id = opcua_certs_trust_test_setup["keyvaultId"]
    kv_name = kv_id.rsplit("/", maxsplit=1)[-1]

    # Generate certificate
    cert_file = generate_self_signed_der_cert()

    # Set expiration date to 2 years from now
    expiration_date = (datetime.now(timezone.utc) + timedelta(days=730)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Add cert with expiration date
    run(f"az iot ops connector opcua trust add --instance {instance_name} \
        -g {resource_group} --certificate-file {cert_file} --expiration-date {expiration_date} --overwrite-secret")

    # Get secret name
    from pathlib import Path
    p = Path(cert_file)
    file_name_info = (p.stem, p.suffix)
    cert_extension = file_name_info[1].replace(".", "")
    secret_name = f"{file_name_info[0]}-{cert_extension}"

    # Verify secret exists with expiration date
    secret = run(f"az keyvault secret show --vault-name {kv_name} -n {secret_name}")
    assert "attributes" in secret, "Secret should have attributes"
    assert "expires" in secret["attributes"], "Secret attributes should have expires field"
    assert secret["attributes"]["expires"] is not None, "Expiration date should be set"

    # Verify the expiration date matches what we provided (allowing for timezone differences)
    from dateutil import parser as date_parser
    expected_expiration = date_parser.isoparse(expiration_date)
    if expected_expiration.tzinfo is None:
        expected_expiration = expected_expiration.replace(tzinfo=timezone.utc)
    actual_expiration = date_parser.isoparse(secret["attributes"]["expires"])

    # Allow 1 second difference due to rounding
    time_diff = abs((actual_expiration - expected_expiration).total_seconds())
    assert time_diff < 2, f"Expiration date should match. Expected: {expected_expiration}, Got: {actual_expiration}"

    logger.info(f"✅ User-provided expiration test passed. Expiration: {actual_expiration}")

    # Cleanup
    run(f"az iot ops connector opcua trust remove --instance {instance_name} -g {resource_group} \
        --certificate-names {cert_file.name} -y --include-secrets")
    cert_file.unlink(missing_ok=True)


@pytest.mark.require_wlif_setup
def test_opcua_cert_trust_with_cert_expiration(
    cluster_connection, opcua_certs_trust_test_setup, tracked_files: List[str]
):
    """Test adding certificate without user expiration - should extract from certificate."""
    resource_group = opcua_certs_trust_test_setup["resourceGroup"]
    instance_name = opcua_certs_trust_test_setup["instanceName"]
    kv_id = opcua_certs_trust_test_setup["keyvaultId"]
    kv_name = kv_id.rsplit("/", maxsplit=1)[-1]

    # Generate certificate (will have its own expiration date)
    cert_file = generate_self_signed_der_cert()

    # Get the certificate's expiration date
    cert_info = run(f"openssl x509 -inform DER -in {cert_file} -noout -enddate")
    # Parse the openssl output: "notAfter=Nov  6 00:34:25 2026 GMT"
    import re
    from datetime import datetime, timezone
    match = re.search(r"notAfter=(.+)", cert_info)
    assert match, "Could not parse certificate expiration"
    cert_expiration_str = match.group(1).strip()
    # Parse the date (format: "Nov  6 00:34:25 2026 GMT")
    cert_expiration = datetime.strptime(cert_expiration_str, "%b %d %H:%M:%S %Y %Z")
    cert_expiration = cert_expiration.replace(tzinfo=timezone.utc)

    # Add cert WITHOUT expiration date parameter
    run(f"az iot ops connector opcua trust add --instance {instance_name} \
        -g {resource_group} --certificate-file {cert_file} --overwrite-secret")

    # Get secret name
    from pathlib import Path
    p = Path(cert_file)
    file_name_info = (p.stem, p.suffix)
    cert_extension = file_name_info[1].replace(".", "")
    secret_name = f"{file_name_info[0]}-{cert_extension}"

    # Verify secret exists with expiration date
    secret = run(f"az keyvault secret show --vault-name {kv_name} -n {secret_name}")
    assert "attributes" in secret, "Secret should have attributes"
    assert "expires" in secret["attributes"], "Secret attributes should have expires field"
    assert secret["attributes"]["expires"] is not None, "Expiration date should be set"

    # Verify the expiration date matches the certificate's expiration
    from dateutil import parser as date_parser
    actual_expiration = date_parser.isoparse(secret["attributes"]["expires"])

    # Allow 2 seconds difference due to rounding and parsing
    time_diff = abs((actual_expiration - cert_expiration).total_seconds())
    assert time_diff < 2, f"Expiration should match certificate. Expected: {cert_expiration}, Got: {actual_expiration}"

    logger.info(f"✅ Certificate expiration extraction test passed. Expiration: {actual_expiration}")

    # Cleanup
    run(f"az iot ops connector opcua trust remove --instance {instance_name} -g {resource_group} \
        --certificate-names {cert_file.name} -y --include-secrets")
    cert_file.unlink(missing_ok=True)
