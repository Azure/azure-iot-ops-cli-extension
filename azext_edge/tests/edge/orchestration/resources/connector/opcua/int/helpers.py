# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from base64 import b64decode
from pathlib import Path
from shlex import quote
from time import sleep
from typing import Callable
from azure.cli.core import AzCommandsLoader, get_default_cli
from azure.cli.core.commands import AzCliCommand
from azure.core.exceptions import AzureError, ResourceNotFoundError
from azext_edge.edge.providers.orchestration.common import CUSTOM_LOCATIONS_API_VERSION
from azext_edge.edge.providers.orchestration.resources.connector.opcua.certs import (
    OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
    OpcUACerts,
)
from azext_edge.edge.util.az_client import get_resource_client, get_ssc_mgmt_client
from azext_edge.edge.util.id_tools import is_valid_resource_id, parse_resource_id
from azext_edge.tests.settings import EnvironmentVariables
from azext_edge.edge.providers.orchestration.resources.instances import SPC_RESOURCE_TYPE
from azext_edge.edge.util.common import url_safe_hash_phrase
from typing import Any, Dict, Optional, cast
from uuid import uuid4
import pytest
from azure.cli.core.azclierror import CLIInternalError
from knack.log import get_logger
from knack.util import CLIError
from .......helpers import run, wait_for_expected_count
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography import x509
from cryptography.x509.oid import NameOID
import datetime

logger = get_logger(__name__)
ROLE_MAX_RETRIES = 5
ROLE_RETRY_INTERVAL = 15
SECRETSYNC_MAX_RETRIES = 20
SECRETSYNC_RETRY_INTERVAL = 5


def certificate_sync_name(instance_name: str, certificate_type: str) -> str:
    return f"{certificate_type}-{url_safe_hash_phrase(instance_name.lower())[:16]}"


def run_json(command: str, **kwargs) -> Dict[str, Any]:
    """
    Run a command and return the result as a dictionary.
    Asserts that the result is not None and is a dict.
    """
    result = run(command, **kwargs)
    assert isinstance(result, dict), f"Expected dict from command, got {type(result)}"
    return cast(Dict[str, Any], result)


def _custom_location(resource: dict) -> str:
    extended_location = resource.get("extendedLocation")
    location = extended_location.get("name") if isinstance(extended_location, dict) else None
    if not isinstance(location, str) or not is_valid_resource_id(location):
        raise CLIInternalError(f"Cannot safely clean up resource with invalid custom location: {resource}")
    parts = parse_resource_id(location)
    if (
        parts.get("namespace", "").lower() != "microsoft.extendedlocation"
        or parts.get("resource_type", "").lower() != "customlocations"
        or not parts.get("resource_group")
        or parts.get("last_child_num")
    ):
        raise CLIInternalError(f"Cannot safely clean up resource with invalid custom location: {location}")
    return location


def _delete_opcua_secretsync(client, resource_group: str, name: str) -> None:
    logger.info("Deleting test SecretSync %s in resource group %s", name, resource_group)
    try:
        poller = client.secret_syncs.begin_delete(resource_group_name=resource_group, secret_sync_name=name)
    except ResourceNotFoundError:
        return
    poller.wait(timeout=120)
    if not poller.done():
        raise TimeoutError(f"Timed out deleting SecretSync {name} in {resource_group}")
    poller.result()
    _wait_for_opcua_secretsync_deletion(client, resource_group, name)


def _wait_for_opcua_secretsync_deletion(client, resource_group: str, name: str) -> None:
    for attempt in range(SECRETSYNC_MAX_RETRIES):
        try:
            client.secret_syncs.get(resource_group_name=resource_group, secret_sync_name=name)
        except ResourceNotFoundError:
            return
        if attempt + 1 < SECRETSYNC_MAX_RETRIES:
            sleep(SECRETSYNC_RETRY_INTERVAL)
    raise TimeoutError(f"SecretSync {name} still exists in {resource_group} after deletion")


def prepare_opcua_secretsync(settings, name: str, certificate_type: Optional[str] = None) -> Callable[[], None]:
    """Remove an orphaned test SecretSync and return an ownership-checked finalizer."""
    resource_group = settings.env.azext_edge_rg
    instance_name = settings.env.azext_edge_instance
    instance = run_json(f"az iot ops show -g {quote(resource_group)} -n {quote(instance_name)}")
    location = _custom_location(instance)
    subscription = parse_resource_id(location)["subscription"]
    cli_ctx = get_default_cli()
    endpoint = cli_ctx.cloud.endpoints.resource_manager
    client = get_ssc_mgmt_client(subscription_id=subscription, endpoint=endpoint)

    try:
        existing = client.secret_syncs.get(resource_group_name=resource_group, secret_sync_name=name)
    except ResourceNotFoundError:
        existing = None
    if existing is not None:
        owner = _custom_location(existing)
        if owner.lower() == location.lower():
            raise CLIInternalError(
                f"SecretSync {name} already belongs to the test instance. "
                "Use a clean test instance; existing certificate resources will not be deleted."
            )
        owner_client = get_resource_client(
            subscription_id=parse_resource_id(owner)["subscription"], endpoint=endpoint,
        )
        try:
            owner_client.resources.get_by_id(owner, api_version=CUSTOM_LOCATIONS_API_VERSION)
        except ResourceNotFoundError:
            logger.warning("Removing orphaned OPC UA SecretSync %s whose custom location %s is missing", name, owner)
            _delete_opcua_secretsync(client, resource_group, name)
        else:
            raise CLIInternalError(
                f"SecretSync {name} belongs to another custom location: {owner}. "
                "Refusing to delete resources owned by another deployment; use a separate resource group."
            )

    def cleanup() -> None:
        try:
            try:
                resource = client.secret_syncs.get(resource_group_name=resource_group, secret_sync_name=name)
            except ResourceNotFoundError:
                return
            owner = _custom_location(resource)
            if owner.lower() != location.lower():
                raise CLIInternalError(f"Refusing to delete SecretSync {name}: ownership changed to {owner}")
            certs = None
            kind = certificate_type or ("client" if name == OPCUA_CLIENT_CERT_SECRET_SYNC_NAME else None)
            if kind:
                cmd = AzCliCommand(
                    loader=AzCommandsLoader(cli_ctx=cli_ctx),
                    name=f"iot ops connector opcua {kind} cleanup",
                    handler=None,
                )
                certs = OpcUACerts(cmd=cmd, resource_group_name=resource_group, instance_name=instance_name)
                if _custom_location({"extendedLocation": certs.extended_location}).lower() != location.lower():
                    raise CLIInternalError(f"Refusing certificate rollback: instance {instance_name} moved")
            _delete_opcua_secretsync(client, resource_group, name)
            if certs is not None:
                certs._reset_certificate_reference(name, kind)
        except (AzureError, CLIError, TimeoutError) as error:
            logger.warning("OPC UA teardown could not clean up SecretSync %s in %s: %s", name, resource_group, error)

    return cleanup


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


def ensure_key_vault(settings, request):
    """
    Ensure a Key Vault exists and the role is assigned. Returns (kv_id, kv_name_if_created_else_None).
    """
    kv_id = settings.env.azext_edge_kv
    kv_name = None
    if not kv_id:
        kv_name = "spc" + uuid4().hex[:16]
        kv_id = run_json(f"az keyvault create -n {kv_name} -g {settings.env.azext_edge_rg}")["id"]
        request.addfinalizer(lambda: cleanup_test_resources(settings, kv_name))
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
        mi_id = run_json(
            f"az identity create -n spc{uuid4().hex[:16]} -g {settings.env.azext_edge_rg}"
        )["id"]
        tracked_resources.append(mi_id)
    return mi_id


def cleanup_test_resources(settings, kv_name):
    """
    Clean up any resources created during the test.
    """
    # KV deletion/purging - only delete if we created it during the test
    if kv_name:
        try:
            instance_name = settings.env.azext_edge_instance
            resource_group = settings.env.azext_edge_rg
            resources = run(f"az iot ops secretsync list -n {instance_name} -g {resource_group}") or []
            spcs = [rec for rec in resources if rec["type"].lower() == SPC_RESOURCE_TYPE]
            owned_spcs = [
                spc for spc in spcs if spc["properties"]["keyvaultName"].lower() == kv_name.lower()
            ]
            if owned_spcs:
                assert len(owned_spcs) == len(spcs), (
                    "Refusing to disable SecretSync resources associated with another fixture's Key Vault."
                )
                _disable_secretsync_and_wait(instance_name, resource_group)
            run(f"az keyvault delete -n {kv_name} -g {settings.env.azext_edge_rg}")
            sleep(ROLE_RETRY_INTERVAL)
            run(f"az keyvault purge -n {kv_name}")
            logger.info(f"Successfully deleted and purged Key Vault {kv_name}")
        except CLIInternalError as e:
            logger.error(f"Failed to delete the keyvault {kv_name} properly. {e.error_msg}")
            raise


def _disable_secretsync_and_wait(instance_name, resource_group):
    run(f"az iot ops secretsync disable -n {instance_name} -g {resource_group} -y")
    # Enable uses Resource Graph too, whose index can lag successful ARM deletes.
    wait_for_expected_count(
        f"az iot ops secretsync list -n {instance_name} -g {resource_group}",
        expected_count=0,
        max_retries=SECRETSYNC_MAX_RETRIES,
        initial_interval=SECRETSYNC_RETRY_INTERVAL,
        run_fn=run,
    )


def ensure_secretsync_enabled(settings, instance_name, resource_group, kv_id, mi_id):
    """
    Ensure secretsync is enabled for the instance. Returns the SPC name.
    Reuses an existing SPC only when it references the requested Key Vault.
    Otherwise, enables secretsync with the provided Key Vault and managed identity.
    """
    try:
        secretsync_list = run(f"az iot ops secretsync list -n {instance_name} -g {resource_group}")
        if secretsync_list:
            spc_results = [rec for rec in secretsync_list if rec["type"].lower() == SPC_RESOURCE_TYPE]
            kv_name = kv_id.rsplit("/", maxsplit=1)[-1]
            if len(spc_results) == 1 and spc_results[0]["properties"]["keyvaultName"].lower() == kv_name.lower():
                spc_name = spc_results[0]["name"]
                run(f"az keyvault show --id {kv_id}")
                logger.info(f"Secretsync already enabled with Key Vault {kv_name}, reusing SPC {spc_name}")
                return spc_name
            logger.info("Replacing SecretSync resources that do not reference the fixture's Key Vault")
            _disable_secretsync_and_wait(instance_name, resource_group)

        # Enable secretsync with the provided Key Vault
        spc_name = run_json(
            f"az iot ops secretsync enable -n {instance_name} -g {resource_group} "
            f"--mi-user-assigned {mi_id} --kv-resource-id {kv_id}"
        )["name"]
        logger.info(f"Enabled secretsync with Key Vault, SPC name: {spc_name}")
        return spc_name

    except CLIInternalError as e:
        logger.error(f"Failed to ensure secretsync is enabled: {str(e)}")
        raise


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
    instance_name: str,
    resource_group: str,
    cert_file: str,
    ssc_name: Optional[str],
):
    p = Path(cert_file)
    file_name_info = (p.stem, p.suffix)
    cert_extension = file_name_info[1].replace(".", "")
    secret_name = f"{file_name_info[0]}-{cert_extension}"
    result = next((rec for rec in secretsync_records if rec["name"] == ssc_name), None)

    for attempt in range(SECRETSYNC_MAX_RETRIES):
        if result:
            assert result["extendedLocation"]["name"] == extended_location
            assert result["resourceGroup"] == resource_group
            assert result["name"] == ssc_name
            secret_mappings = result["properties"].get("objectSecretMapping", [])
            if any(mapping.get("sourcePath", "") == secret_name for mapping in secret_mappings):
                return
        if attempt < SECRETSYNC_MAX_RETRIES - 1:
            sleep(SECRETSYNC_RETRY_INTERVAL)
            refreshed_records = run(f"az iot ops secretsync list -i {instance_name} -g {resource_group}")
            result = next((rec for rec in refreshed_records if rec["name"] == ssc_name), None)

    raise AssertionError(f"SecretSync record '{ssc_name}' did not contain secret {secret_name}.")


def assert_cluster_side_secret_exists(
    spc_name: str,
    secret_sync_name: str,
    cert_file: str,
):
    p = Path(cert_file)
    secret_name = f"{p.stem}{p.suffix}"
    secret_value = p.read_bytes()
    # get the current secret provider class
    list_result = run_json("kubectl get secretproviderclass -A -o json")["items"]
    assert list_result
    spc_data = next(spc for spc in list_result if spc["metadata"]["name"] == spc_name)
    aio_namespace = spc_data["metadata"]["namespace"]
    secret_data = run_json(f"kubectl get secret {secret_sync_name} -n {aio_namespace} -o json")
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
        run(f"az keyvault secret show --vault-name {kv_name} -n {secret_name}", expect_failure=True)
        # If we get here, the command failed (as expected), meaning the secret doesn't exist
        return
    except CLIInternalError as e:
        # The command succeeded when we expected failure - meaning the secret still exists!
        if "did not fail as expected" in e.error_msg:
            raise AssertionError(f"Secret {secret_name} still found in keyvault {kv_name}.")
        # Some other unexpected error, re-raise
        raise


def assert_spc_secret_not_exists(
    secretsync_records: list,
    spc_name: str,
    cert_file: str
):
    p = Path(cert_file)
    file_name_info = (p.stem, p.suffix)
    cert_extension = file_name_info[1].replace(".", "")
    secret_name = f"{file_name_info[0]}-{cert_extension}"
    secretsync_record = next((rec for rec in secretsync_records if rec["name"] == spc_name), None)
    assert secretsync_record
    objects = secretsync_record["properties"].get("objects", "")
    assert secret_name not in objects
    return


def assert_ssc_secret_not_exists(
    secretsync_records: list,
    extended_location: str,
    resource_group: str,
    cert_file: str,
    ssc_name: Optional[str],
    instance_name: str,
):
    p = Path(cert_file)
    file_name_info = (p.stem, p.suffix)
    cert_extension = file_name_info[1].replace(".", "")
    secret_name = f"{file_name_info[0]}-{cert_extension}"
    for attempt in range(SECRETSYNC_MAX_RETRIES + 1):
        assert isinstance(secretsync_records, list), "Expected a SecretSync resource list."
        result = next((rec for rec in secretsync_records if rec["name"] == ssc_name), None)
        if not result:
            return
        assert result["extendedLocation"]["name"] == extended_location
        assert result["resourceGroup"] == resource_group
        assert result["name"] == ssc_name
        secret_mappings = result["properties"].get("objectSecretMapping", [])
        if not any(mapping.get("sourcePath", "") == secret_name for mapping in secret_mappings):
            return
        assert attempt < SECRETSYNC_MAX_RETRIES, f"Secret {secret_name} still appears in SecretSync {ssc_name}."
        # SecretSync list uses Resource Graph, which can lag successful ARM deletion.
        logger.info("Waiting for Resource Graph to remove %s from %s.", secret_name, ssc_name)
        sleep(SECRETSYNC_RETRY_INTERVAL)
        secretsync_records = run(
            f"az iot ops secretsync list -i {quote(instance_name)} -g {quote(resource_group)}"
        )


def assert_cluster_side_secret_not_exists(
    spc_name: str,
    secret_sync_name: str,
    max_retries: int = 10,
    retry_interval: int = 5,
):
    # get the current secret provider class
    list_result = run_json("kubectl get secretproviderclass -A -o json")["items"]
    assert list_result
    spc_data = next(spc for spc in list_result if spc["metadata"]["name"] == spc_name)
    aio_namespace = spc_data["metadata"]["namespace"]

    for attempt in range(max_retries):
        try:
            run(f"kubectl get secret {secret_sync_name} -n {aio_namespace} -o json", expect_failure=True)
            # If we get here, the command failed (as expected), meaning the secret doesn't exist
            return
        except CLIInternalError as e:
            # The command succeeded when we expected failure - meaning the secret still exists!
            if "did not fail as expected" in e.error_msg:
                if attempt < max_retries - 1:
                    sleep(retry_interval)
                    continue
                raise AssertionError(
                    f"Secret {secret_sync_name} still found in namespace {aio_namespace} "
                    f"after {max_retries} attempts."
                )
            # Some other unexpected error, re-raise
            raise


def generate_self_signed_cert(
    filename: str,
    issuer_attrs=None,
    validity_days: int = 1,
    basic_constraints: x509.BasicConstraints = None,
    san_uris=None,
    encoding: serialization.Encoding = serialization.Encoding.DER,
    is_ca: bool = False
) -> Path:
    """
    Generic helper: Generate a self-signed X.509 certificate and save as DER/PEM in current directory.
    Allows custom subject, issuer, basicConstraints, SAN URIs, and encoding.
    Returns the Path of the generated file.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Use same for subject and issuer if issuer_attrs is not specified
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Washington"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Redmond"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Example Org"),
        x509.NameAttribute(NameOID.COMMON_NAME, "example.org"),
    ])
    issuer = x509.Name(issuer_attrs) if issuer_attrs else subject

    builder = x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(
        key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.now(datetime.timezone.utc)
    ).not_valid_after(
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=validity_days)
    )

    # Optionally add basicConstraints extension
    if basic_constraints:
        builder = builder.add_extension(basic_constraints, critical=True)
    elif is_ca:
        builder = builder.add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)

    # Optionally add SAN URIs extension
    if san_uris:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.UniformResourceIdentifier(uri) for uri in san_uris]),
            critical=False
        )

    cert = builder.sign(key, hashes.SHA256())

    out_path = Path.cwd() / filename
    out_path.write_bytes(cert.public_bytes(encoding))
    return out_path


def generate_self_signed_der_cert() -> Path:
    return generate_self_signed_cert("trusttest.der")


def generate_ca_cert() -> Path:
    return generate_self_signed_cert(
        "issuertest.crt",
        basic_constraints=x509.BasicConstraints(ca=True, path_length=None),
        encoding=serialization.Encoding.PEM
    )


def generate_self_signed_der_cert_with_uri() -> Path:
    return generate_self_signed_cert(
        "clienttest.der",
        san_uris=["urn:example:client"],
    )


def generate_self_signed_pem_cert() -> Path:
    return generate_self_signed_cert(
        "clienttest.pem",
        encoding=serialization.Encoding.PEM
    )
