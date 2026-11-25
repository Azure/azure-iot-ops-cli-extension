# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from .helpers import (
    assert_cluster_side_secret_exists,
    assert_cluster_side_secret_not_exists,
    assert_kv_secret_exists,
    assert_kv_secret_not_exists,
    assert_spc_secret_exists,
    assert_spc_secret_not_exists,
    assert_ssc_secret_exists,
    assert_ssc_secret_not_exists,
    certificate_sync_name,
    ensure_env_vars,
    ensure_key_vault,
    ensure_managed_identity,
    ensure_secretsync_enabled,
    generate_self_signed_der_cert,
    prepare_opcua_secretsync,
)
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import pytest
from dateutil import parser as date_parser
from typing import List

from .......helpers import run


@pytest.fixture(scope="function")
def opcua_certs_trust_test_setup(settings, tracked_resources: List[str], request):
    """Setup fixture for opcua certs trust tests."""

    ensure_env_vars(settings)
    kv_id, _ = ensure_key_vault(settings, request)
    sync_name = certificate_sync_name(settings.env.azext_edge_instance, "trust")
    request.addfinalizer(prepare_opcua_secretsync(settings, sync_name, certificate_type="trust"))
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
        "secretSyncName": sync_name,
    }


def _kv_expiration(kv_name: str, cert_file: Path) -> datetime:
    secret_name = f"{cert_file.stem}-{cert_file.suffix.lstrip('.')}"
    secret = run(f"az keyvault secret show --vault-name {kv_name} -n {secret_name}")
    expires = secret.get("attributes", {}).get("expires")  # type: ignore[union-attr]
    assert expires, f"Secret {secret_name} should have an expiration date."
    return date_parser.isoparse(expires)


def _cert_expiration(cert_file: Path) -> datetime:
    # openssl output: "notAfter=Nov  6 00:34:25 2026 GMT"
    match = re.search(r"notAfter=(.+)", run(f"openssl x509 -inform DER -in {cert_file} -noout -enddate"))
    assert match, "Could not parse certificate expiration"
    return datetime.strptime(match.group(1).strip(), "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)


@pytest.mark.require_wlif_setup
def test_opcua_cert_trust(cluster_connection, opcua_certs_trust_test_setup, tracked_files: List[str]):
    """One trust list lifecycle: certificate and user expirations, show, partial and final removal."""
    resource_group = opcua_certs_trust_test_setup["resourceGroup"]
    instance_name = opcua_certs_trust_test_setup["instanceName"]
    sync_name = opcua_certs_trust_test_setup["secretSyncName"]
    kv_id = opcua_certs_trust_test_setup["keyvaultId"]
    kv_name = kv_id.rsplit("/", maxsplit=1)[-1]
    trust = f"az iot ops connector opcua trust {{}} --instance {instance_name} -g {resource_group} " \
        f"--secret-sync-name {sync_name}"
    secretsync_list = f"az iot ops secretsync list -i {instance_name} -g {resource_group}"

    instance_info = run(f"az iot ops show -g {resource_group} -n {instance_name}")
    extended_loc = instance_info["extendedLocation"]["name"]  # type: ignore[index]
    spc_name = instance_info["properties"].get(  # type: ignore[union-attr]
        "defaultSecretProviderClassRef", {}
    ).get("resourceId", "")
    # get last part of the id
    if spc_name:
        spc_name = spc_name.rsplit("/", maxsplit=1)[-1]
    ssc_args = {
        "extended_location": extended_loc, "instance_name": instance_name,
        "resource_group": resource_group, "ssc_name": sync_name,
    }

    # Certificate A: the Key Vault expiration comes from the certificate itself.
    cert_a = generate_self_signed_der_cert("trusttesta.der")
    run(trust.format("add") + f" --certificate-file {cert_a} --overwrite-secret")
    secretsync_records = run(secretsync_list)
    assert_kv_secret_exists(kv_id=kv_id, cert_file=cert_a)
    assert_spc_secret_exists(
        spc_records=secretsync_records, spc_name=spc_name, instance_name=instance_name,
        resource_group=resource_group, cert_file=cert_a,
    )
    assert_ssc_secret_exists(secretsync_records=secretsync_records, cert_file=cert_a, **ssc_args)
    assert_cluster_side_secret_exists(spc_name=spc_name, secret_sync_name=sync_name, cert_file=cert_a)
    expected, actual = _cert_expiration(cert_a), _kv_expiration(kv_name, cert_a)
    assert abs((actual - expected).total_seconds()) < 2, f"Expected expiration {expected}, got {actual}."

    # Certificate B: a user expiration date, added to the same SecretSync.
    cert_b = generate_self_signed_der_cert("trusttestb.der")
    expiration_date = (datetime.now(timezone.utc) + timedelta(days=730)).strftime("%Y-%m-%dT%H:%M:%SZ")
    run(trust.format("add") + f" --certificate-file {cert_b} --expiration-date {expiration_date} --overwrite-secret")
    secretsync_records = run(secretsync_list)
    assert_kv_secret_exists(kv_id=kv_id, cert_file=cert_b)
    assert_spc_secret_exists(
        spc_records=secretsync_records, spc_name=spc_name, instance_name=instance_name,
        resource_group=resource_group, cert_file=cert_b,
    )
    assert_ssc_secret_exists(secretsync_records=secretsync_records, cert_file=cert_b, **ssc_args)
    expected, actual = date_parser.isoparse(expiration_date), _kv_expiration(kv_name, cert_b)
    assert abs((actual - expected).total_seconds()) < 2, f"Expected expiration {expected}, got {actual}."

    show_result = run(trust.format("show"))
    assert show_result["name"] == sync_name  # type: ignore[index]

    # Removing B keeps A in the SecretSync.
    run(trust.format("remove") + f" --certificate-names {cert_b.name} -y --include-secrets")
    secretsync_records = run(secretsync_list)
    assert_kv_secret_not_exists(kv_id=kv_id, cert_file=cert_b.name)
    assert_spc_secret_not_exists(secretsync_records=secretsync_records, spc_name=spc_name, cert_file=cert_b.name)
    assert_ssc_secret_not_exists(secretsync_records=secretsync_records, cert_file=cert_b.name, **ssc_args)
    assert_ssc_secret_exists(secretsync_records=secretsync_records, cert_file=cert_a, **ssc_args)

    # Removing the last certificate removes the SecretSync.
    run(trust.format("remove") + f" --certificate-names {cert_a.name} -y --include-secrets")
    secretsync_records = run(secretsync_list)
    assert_kv_secret_not_exists(kv_id=kv_id, cert_file=cert_a.name)
    assert_spc_secret_not_exists(secretsync_records=secretsync_records, spc_name=spc_name, cert_file=cert_a.name)
    assert_ssc_secret_not_exists(secretsync_records=secretsync_records, cert_file=cert_a.name, **ssc_args)
    assert_cluster_side_secret_not_exists(spc_name=spc_name, secret_sync_name=sync_name)
    cert_a.unlink(missing_ok=True)
    cert_b.unlink(missing_ok=True)
