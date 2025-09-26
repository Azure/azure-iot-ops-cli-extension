# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from base64 import b64decode
from pathlib import Path
from time import sleep
from azext_edge.tests.settings import EnvironmentVariables
from knack.log import get_logger
from typing import Dict, Iterable, List, Optional, Tuple, TypedDict, Union
from os import path
from zipfile import ZipFile
import pytest
from azure.cli.core.azclierror import CLIInternalError
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api.base import EdgeApiManager, EdgeResourceApi
from azext_edge.edge.providers.support.arcagents import ARC_AGENTS
from .......helpers import (
    PLURAL_KEY,
    find_extra_or_missing_names,
    get_kubectl_custom_items,
    get_kubectl_workload_items,
    run,
)
from .......generators import generate_random_string
from knack.log import get_logger
from time import sleep
from typing import List, Optional
from .......helpers import run
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography import x509
from cryptography.x509.oid import NameOID
import datetime

from azure.cli.core.azclierror import CLIInternalError

logger = get_logger(__name__)
ROLE_MAX_RETRIES = 5
ROLE_RETRY_INTERVAL = 15

def ensure_env_vars(settings):
    """
    Add required environment variables to config, and check for essential context.
    Fail or skip the test early if configuration is missing.
    """
    settings.add_to_config(EnvironmentVariables.rg.value)
    settings.add_to_config(EnvironmentVariables.instance.value)
    settings.add_to_config(EnvironmentVariables.kv.value)
    settings.add_to_config(EnvironmentVariables.user_assigned_mi_id.value)
    settings.add_to_config(EnvironmentVariables.sp_object_id.value)

    if not all([settings.env.azext_edge_instance, settings.env.azext_edge_rg]):
        raise AssertionError(
            f"Cannot run secretsync tests without an instance and resource group. Current settings:\n {settings}"
        )
    if not any([settings.env.azext_edge_kv, settings.env.azext_edge_sp_object_id]):
        pytest.skip(
            "Cannot run secretsync tests without a keyvault id or an object id. "
            "Object Id is needed to add 'Key Vault Secrets Officer' to a newly created key vault."
        )

def ensure_key_vault(settings):
    """
    Ensure a Key Vault exists and the role is assigned. Returns (kv_id, kv_name_if_created_else_None).
    """
    kv_id = settings.env.azext_edge_kv
    kv_name = None
    if not kv_id:
        kv_name = "spc" + generate_random_string(size=6)
        kv_id = run(f"az keyvault create -n {kv_name} -g {settings.env.azext_edge_rg}")["id"]
        run(
            "az role assignment create --role b86a8fe4-44ce-4948-aee5-eccb2c155cd7 "
            f"--assignee {settings.env.azext_edge_sp_object_id} --scope {kv_id}"
        )
    return kv_id, kv_name

def ensure_managed_identity(settings, tracked_resources):
    """
    Ensure a user assigned managed identity exists, creating it if not. Returns mi_id.
    """
    mi_id = settings.env.azext_edge_user_assigned_mi_id
    if not mi_id:
        mi_id = run(
            f"az identity create -n spc{generate_random_string(size=6)} -g {settings.env.azext_edge_rg}"
        )["id"]
        tracked_resources.append(mi_id)
    return mi_id

def restore_tracked_resources(settings, initial_list_result, instance_name, resource_group, kv_name):
    """
    Restore any resources created during the test.
    """
    # KV deletion/purging
    if kv_name:
        try:
            run(f"az keyvault delete -n {kv_name} -g {settings.env.azext_edge_rg}")
            sleep(ROLE_RETRY_INTERVAL)
            run(f"az keyvault purge -n {kv_name}")
        except CLIInternalError as e:
            logger.error(f"Failed to delete the keyvault {kv_name} properly. {e.error_msg}")

    # restoring previous state
    if initial_list_result:
        spc_results = [
            rec for rec in initial_list_result
            if rec["type"].lower() == "microsoft.secretsynccontroller/azurekeyvaultsecretproviderclasses"
        ]
        kv_name = spc_results[0]["properties"]["keyvaultName"]
        mi_client_id = spc_results[0]["properties"]["clientId"]
        spc_name = spc_results[0]["name"]
        try:
            kv_id = run(f"az keyvault show -n {kv_name}")["id"]
            mi_id = run(f"az identity list --query \"[?clientId=='{mi_client_id}']\"")[0]["id"]
            run(
                f"az iot ops secretsync enable -n {instance_name} -g {resource_group} "
                f"--mi-user-assigned {mi_id} --kv-resource-id {kv_id} --spc {spc_name} --skip-ra"
            )
        except (CLIInternalError, IndexError):
            logger.error("Could not reenable secretsync correctly.")

def assert_kv_secret_exists(kv_id: str, cert_file: str):
    kv_name = kv_id.rsplit("/", maxsplit=1)[-1]
    p = Path(cert_file)
    file_name_info = (p.stem, p.suffix)
    cert_extension = file_name_info[1].replace(".", "")
    secret_name = f"{file_name_info[0]}-{cert_extension}"
    # sometimes it takes a bit to get the secret to show up
    retries = 5
    while retries > 0:
        try:
            secret = run(f"az keyvault secret show --vault-name {kv_name} -n {secret_name}")
            assert secret
            return
        except (CLIInternalError, AssertionError):
            retries -= 1
            sleep(5)
    raise AssertionError(f"Secret {secret_name} not found in keyvault {kv_name} or invalid value.")

def assert_spc_secret_exists(spc_records: list, spc_name: str, instance_name: str, resource_group: str, cert_file: str):
    p = Path(cert_file)
    file_name_info = (p.stem, p.suffix)
    cert_extension = file_name_info[1].replace(".", "")
    secret_name = f"{file_name_info[0]}-{cert_extension}"
    spc_record = next((rec for rec in spc_records if rec["name"] == spc_name), None)
    assert spc_record
    objects = spc_record["properties"].get("objects", "")
    assert secret_name in objects
    return

def assert_ssc_secret_exists(
    secretsync_records: list,
    extended_location: str,
    resource_group: str,
    cert_file: str,
    ssc_name: Optional[str],
):
    p = Path(cert_file)
    file_name_info = (p.stem, p.suffix)
    cert_extension = file_name_info[1].replace(".", "")
    secret_name = f"{file_name_info[0]}-{cert_extension}"
    result = next((rec for rec in secretsync_records if rec["name"] == ssc_name), None)
    assert result["extendedLocation"]["name"] == extended_location
    assert result["resourceGroup"] == resource_group
    assert result["name"] == ssc_name
    secret_mappings = result["properties"].get("objectSecretMapping", [])
    assert any([mapping.get("sourcePath", "") == secret_name for mapping in secret_mappings])

def assert_cluster_side_secret_exists(
    spc_name: str,
    secret_sync_name: str,
    cert_file: str,
):
    p = Path(cert_file)
    secret_name = f"{p.stem}{p.suffix}"
    secret_value = p.read_bytes()
    # get the current secret provider class
    list_result = run("kubectl get secretproviderclass -A -o json")["items"]
    assert list_result
    spc_data = next(spc for spc in list_result if spc["metadata"]["name"] == spc_name)
    aio_namespace = spc_data["metadata"]["namespace"]
    secret_data = run(f"kubectl get secret {secret_sync_name} -n {aio_namespace} -o json")
    assert secret_name in secret_data["data"]
    # decode the secret value into bytes
    decoded = b64decode(secret_data["data"][secret_name])
    assert decoded == secret_value

def assert_kv_secret_not_exists(kv_id: str, cert_file: str):
    kv_name = kv_id.rsplit("/", maxsplit=1)[-1]
    p = Path(cert_file)
    file_name_info = (p.stem, p.suffix)
    cert_extension = file_name_info[1].replace(".", "")
    secret_name = f"{file_name_info[0]}-{cert_extension}"
    try:
        run(f"az keyvault secret show --vault-name {kv_name} -n {secret_name}")
    except CLIInternalError as e:
        if "SecretNotFound" in e.error_msg:
            return
        raise e
    raise AssertionError(f"Secret {secret_name} still found in keyvault {kv_name}.")

def assert_spc_secret_not_exists(secretsync_records: list, spc_name: str, instance_name: str, resource_group: str, cert_file: str):
    p = Path(cert_file)
    file_name_info = (p.stem, p.suffix)
    cert_extension = file_name_info[1].replace(".", "")
    secret_name = f"{file_name_info[0]}-{cert_extension}"
    secretsync_record = next((rec for rec in secretsync_records if rec["name"] == spc_name), None)
    assert secretsync_record
    objects = secretsync_record["properties"].get("objects", "")
    assert not secret_name in objects
    return

def assert_ssc_secret_not_exists(
    secretsync_records: list,
    instance_name: str,
    extended_location: str,
    resource_group: str,
    cert_file: str,
    ssc_name: Optional[str],
):
    p = Path(cert_file)
    file_name_info = (p.stem, p.suffix)
    cert_extension = file_name_info[1].replace(".", "")
    secret_name = f"{file_name_info[0]}-{cert_extension}"
    result = next((rec for rec in secretsync_records if rec["name"] == ssc_name), None)
    if not result:
        # when there is only one secret in secretsync resource, and it is removed, the resource itself is removed
        return
    else:
        assert result["extendedLocation"]["name"] == extended_location
        assert result["resourceGroup"] == resource_group
        assert result["name"] == ssc_name
        secret_mappings = result["properties"].get("objectSecretMapping", [])
        assert not any([mapping.get("sourcePath", "") == secret_name for mapping in secret_mappings])
        show_result = run(f"az iot ops secretsync show --name {ssc_name} -g {resource_group}")
        assert show_result["name"] == ssc_name
        assert show_result["extendedLocation"]["name"] == extended_location
        assert show_result["resourceGroup"] == resource_group
        assert not any([mapping.get("sourcePath", "") == secret_name for mapping in show_result["properties"].get("objectSecretMapping", [])])

def assert_cluster_side_secret_not_exists(
    spc_name: str,
    secret_sync_name: str,
):
    # get the current secret provider class
    list_result = run("kubectl get secretproviderclass -A -o json")["items"]
    assert list_result
    spc_data = next(spc for spc in list_result if spc["metadata"]["name"] == spc_name)
    aio_namespace = spc_data["metadata"]["namespace"]
    try:
        run(f"kubectl get secret {secret_sync_name} -n {aio_namespace} -o json")
    except CLIInternalError as e:
        if "NotFound" in e.error_msg:
            return
        raise e
    raise AssertionError(f"Secret {secret_sync_name} still found in namespace {aio_namespace}.")

def generate_self_signed_der_cert() -> Path:
    """
    Generate a self-signed X.509 certificate and save as DER in current directory.
    Returns the path of the generated file.
    """
    filename = "trusttest.der"
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, u"US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"California"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, u"San Francisco"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"Example Org"),
        x509.NameAttribute(NameOID.COMMON_NAME, u"example.org"),
    ])

    cert = x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(
        key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.now(datetime.timezone.utc)
    ).not_valid_after(
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
    ).sign(key, hashes.SHA256())

    out_path = Path.cwd() / filename
    out_path.write_bytes(cert.public_bytes(serialization.Encoding.DER))
    return out_path

def generate_ca_cert():
    """
    Generate a self-signed X.509 certificate and save as CRT in current directory.
    Returns the path of the generated file.
    """
    filename = "issuertest.crt"
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, u"US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"California"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, u"Redmond"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"Contoso"),
        x509.NameAttribute(NameOID.COMMON_NAME, u"contoso.com"),
    ])
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.now(datetime.timezone.utc)
    ).not_valid_after(
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
    )

    # Add basicConstraints (must have for CA/leaf detection!)
    cert = cert.add_extension(
        x509.BasicConstraints(ca=True, path_length=None),  # set ca=True for a CA certificate
        critical=True
    )

    cert = cert.sign(key, hashes.SHA256())
    out_path = Path.cwd() / filename
    with open(out_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    return out_path

def generate_self_signed_der_cert_with_uri() -> Path:
    """
    Generate a self-signed X.509 certificate and save as DER in current directory.
    Returns the path of the generated file.
    """
    filename = "clienttest.der"
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, u"US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"California"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, u"San Francisco"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"Example Org"),
        x509.NameAttribute(NameOID.COMMON_NAME, u"example.org"),
    ])

    cert = x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(
        key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.now(datetime.timezone.utc)
    ).not_valid_after(
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
    )

    uris = ["urn:example:client"]
    cert = cert.add_extension(
        x509.SubjectAlternativeName([x509.UniformResourceIdentifier(uri) for uri in uris]),
        critical=False
    )
    cert = cert.sign(key, hashes.SHA256())

    out_path = Path.cwd() / filename
    out_path.write_bytes(cert.public_bytes(serialization.Encoding.DER))
    return out_path

def generate_self_signed_pem_cert() -> Path:
    """
    Generate a self-signed X.509 certificate and save as PEM in current directory.
    Returns the path of the generated file.
    """
    filename = "clienttest.pem"
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, u"US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"California"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, u"San Francisco"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"Example Org"),
        x509.NameAttribute(NameOID.COMMON_NAME, u"example.org"),
    ])

    cert = x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(
        key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.now(datetime.timezone.utc)
    ).not_valid_after(
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
    ).sign(key, hashes.SHA256())

    out_path = Path.cwd() / filename
    out_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return out_path
