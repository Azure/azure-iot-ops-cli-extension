# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from base64 import b64decode
from azext_edge.edge.providers.orchestration.resources.connector.opcua.certs import OPCUA_CLIENT_CERT_SECRET_SYNC_NAME
from .helpers import assert_cluster_side_secret_exists, assert_cluster_side_secret_not_exists, assert_kv_secret_exists, assert_kv_secret_not_exists, assert_spc_secret_exists, assert_spc_secret_not_exists, assert_ssc_secret_exists, assert_ssc_secret_not_exists, ensure_env_vars, ensure_key_vault, ensure_managed_identity, generate_self_signed_der_cert_with_uri, generate_self_signed_pem_cert, restore_tracked_resources
import pytest
from pathlib import Path
from knack.log import get_logger
from time import sleep
from typing import List, Optional
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography import x509
from cryptography.x509.oid import NameOID
import datetime

from azure.cli.core.azclierror import CLIInternalError

from .......generators import generate_random_string
from .......helpers import run
from .......settings import EnvironmentVariables
from azext_edge.tests import settings

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

    # see if secretsync is already enabled, if so, skip enabling
    initial_list_result = run(f"az iot ops secretsync list -n {instance_name} -g {resource_group}")
    if not initial_list_result:
        spc_name = run(f"az iot ops secretsync enable -n {instance_name} -g {resource_group} --mi-user-assigned {mi_id} --kv-resource-id {kv_id}")["name"]
    else:
        # spc_results should be with "type": "microsoft.secretsynccontroller/azurekeyvaultsecretproviderclasses"
        spc_results = [rec for rec in initial_list_result if rec["type"].lower() == "microsoft.secretsynccontroller/azurekeyvaultsecretproviderclasses"]
        spc_name = spc_results[0]["name"]

    yield {
        "resourceGroup": resource_group,
        "instanceName": instance_name,
        "keyvaultId": kv_id,
        "userAssignedId": mi_id,
        "spcName": spc_name,
    }

    restore_tracked_resources(settings, initial_list_result, instance_name, resource_group, kv_name)


@pytest.mark.rpsaas
@pytest.mark.require_wlif_setup
def test_opcua_cert_client(cluster_connection, opcua_certs_client_test_setup, tracked_files: List[str]):
    resource_group = opcua_certs_client_test_setup["resourceGroup"]
    instance_name = opcua_certs_client_test_setup["instanceName"]
    kv_id = opcua_certs_client_test_setup["keyvaultId"]

    extended_loc = run(f"az iot ops show -g {resource_group} -n {instance_name}")["extendedLocation"]["name"]
    spc_name = run(f"az iot ops show -n {instance_name} -g {resource_group}")["properties"].get("defaultSecretProviderClassRef", {}).get("resourceId", "")
    # get last part of the id
    if spc_name:
        spc_name = spc_name.rsplit("/", maxsplit=1)[-1]
    
    # add cert to client certs
    # cert_file = Path(__file__).parent.joinpath("certificate.der")
    public_key_file = generate_self_signed_der_cert_with_uri()
    # create a private key file too with same name but .pem extension, copy the public key content into it
    private_key_file = generate_self_signed_pem_cert()
    result = run(f"az iot ops connector opcua client add --instance {instance_name} -g {resource_group} --public-key-file {public_key_file} --private-key-file {private_key_file} --overwrite-secret")
    secretsync_records = run(f"az iot ops secretsync list -i {instance_name} -g {resource_group}")

    # check kv secret has been created
    for cert_file in [public_key_file, private_key_file]:
        assert_kv_secret_exists(kv_id=kv_id, cert_file=cert_file)
        # check secret entry exist in spc
        assert_spc_secret_exists(spc_records=secretsync_records, spc_name=spc_name, instance_name=instance_name, resource_group=resource_group, cert_file=public_key_file)
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
    assert show_result["name"] == OPCUA_CLIENT_CERT_SECRET_SYNC_NAME

    # remove certs from client certs
    public_certificate_name = public_key_file.name
    private_certificate_name = private_key_file.name
    result = run(f"az iot ops connector opcua client remove --instance {instance_name} -g {resource_group} --certificate-names {public_certificate_name} {private_certificate_name} -y --include-secrets")
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
            instance_name=instance_name,
            resource_group=resource_group,
            cert_file=certificate_name
        )
        # check secret entry removed from secretsync
        assert_ssc_secret_not_exists(
            secretsync_records=secretsync_records,
            instance_name=instance_name,
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
