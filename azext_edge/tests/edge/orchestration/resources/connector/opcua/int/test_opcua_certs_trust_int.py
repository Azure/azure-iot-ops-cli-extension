# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from base64 import b64decode
from copy import deepcopy
import json
from azext_edge.edge.providers.orchestration.resources.connector.opcua.certs import OPCUA_TRUST_LIST_SECRET_SYNC_NAME
import pytest
from pathlib import Path
from knack.log import get_logger
from time import sleep
from typing import List, Optional

from azure.cli.core.azclierror import CLIInternalError

from .......generators import generate_random_string
from .......helpers import run
from .......settings import EnvironmentVariables

logger = get_logger(__name__)
ROLE_MAX_RETRIES = 5
ROLE_RETRY_INTERVAL = 15


@pytest.fixture(scope="function")
def opcua_certs_trust_test_setup(settings, tracked_resources: List[str]):
    """Setup fixture for opcua certs trust tests."""

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
            "Cannot run secretsync tests without a keyvault id or a object id. Object Id is needed to add "
            "'Key Vault Secrets Officer' to a newly created key vault."
        )

    # create kv if not existing, track the name to delete later
    kv_id = settings.env.azext_edge_kv
    kv_name = None
    if not kv_id:
        kv_name = "spc" + generate_random_string(size=6)
        kv_id = run(f"az keyvault create -n {kv_name} -g {settings.env.azext_edge_rg}")["id"]
        # add "Key Vault Secrets Officer" role
        run(
            "az role assignment create --role b86a8fe4-44ce-4948-aee5-eccb2c155cd7 "
            f"--assignee {settings.env.azext_edge_sp_object_id} --scope {kv_id}"
        )

    # create mi if not existing, track the name to delete later
    mi_id = settings.env.azext_edge_user_assigned_mi_id
    if not mi_id:
        mi_id = run(
            f"az identity create -n {'spc' + generate_random_string(size=6)} -g {settings.env.azext_edge_rg}"
        )["id"]
        tracked_resources.append(mi_id)

    instance_name = settings.env.azext_edge_instance
    resource_group = settings.env.azext_edge_rg
    # see if secretsync is already enabled, if so, skip enabling
    initial_list_result = run(f"az iot ops secretsync list -n {instance_name} -g {resource_group}")
    if not initial_list_result:
        spc_name = run(f"az iot ops secretsync enable -n {instance_name} -g {resource_group} --mi-user-assigned {mi_id} --kv-resource-id {kv_id}")["name"]
    else:
        spc_name = initial_list_result[0]["name"]

    yield {
        "resourceGroup": resource_group,
        "instanceName": instance_name,
        "keyvaultId": kv_id,
        "userAssignedId": mi_id,
        "spcName": spc_name,
    }

    # note that you need to purge the kv too...
    if kv_name:
        try:
            run(f"az keyvault delete -n {kv_name} -g {settings.env.azext_edge_rg}")
            # sometimes it takes a bit to get the deleted list to update
            sleep(ROLE_RETRY_INTERVAL)
            run(f"az keyvault purge -n {kv_name}")
        except CLIInternalError as e:
            logger.error(f"Failed to delete the keyvault {kv_name} properly. {e.error_msg}")

    # if it was enabled before, reenable
    if initial_list_result:
        kv_name = initial_list_result[0]["properties"]["keyvaultName"]
        mi_client_id = initial_list_result[0]["properties"]["clientId"]
        spc_name = initial_list_result[0]["name"]
        try:
            kv_id = run(f"az keyvault show -n {kv_name}")["id"]
            mi_id = run(f"az identity list --query \"[?clientId=='{mi_client_id}']\"")[0]["id"]
            # if the role assignments were applied, they should still exist
            # TODO: phase 2 - direct cluster connection for --self-hosted-issuer
            run(
                f"az iot ops secretsync enable -n {instance_name} -g {resource_group} "
                f"--mi-user-assigned {mi_id} --kv-resource-id {kv_id} --spc {spc_name} --skip-ra"
            )
        except (CLIInternalError, IndexError):
            logger.error("Could not reenable secretsync correctly.")


@pytest.mark.rpsaas
@pytest.mark.require_wlif_setup
def test_opcua_cert_trust(cluster_connection, opcua_certs_trust_test_setup, tracked_files: List[str]):
    resource_group = opcua_certs_trust_test_setup["resourceGroup"]
    instance_name = opcua_certs_trust_test_setup["instanceName"]
    kv_id = opcua_certs_trust_test_setup["keyvaultId"]
    mi_id = opcua_certs_trust_test_setup["userAssignedId"]
    spc_name = opcua_certs_trust_test_setup["spcName"]
    use_self_hosted_issuer = False

    extended_loc = run(f"az iot ops show -g {resource_group} -n {instance_name}")["extendedLocation"]["name"]
    mi_client_id = run(f"az identity show --ids {mi_id}")["clientId"]
    mi_principal_id = run(f"az identity show --ids {mi_id}")["principalId"]
    expected_result = {
        "extended_location": extended_loc,
        "resource_group": resource_group,
        "kv_name": kv_id.rsplit("/", maxsplit=1)[-1],
        "mi_client_id": mi_client_id,
    }

    # initial_role_list = [
    #     role["roleDefinitionName"] for role in _get_role_list(kv_id, mi_client_id)
    # ]

    # # enable with skip ra + check if test can be run
    # try:
    #     enable_result = run(
    #         f"az iot ops secretsync enable -n {instance_name} -g {resource_group} "
    #         f"--mi-user-assigned {mi_id} --kv-resource-id {kv_id} --skip-ra"
    #     )
    # except CLIInternalError as e:
    #     if "not enabled as an oidc issuer or for workload identity federation." in e.error_msg:
    #         pytest.skip("Cluster is not enabled for secretsync.")
    #     elif "No issuerUrl is available." in e.error_msg:
    #         use_self_hosted_issuer = True
    #         enable_result = run(
    #             f"az iot ops secretsync enable -n {instance_name} -g {resource_group} "
    #             f"--mi-user-assigned {mi_id} --kv-resource-id {kv_id} --skip-ra --self-hosted-issuer"
    #         )
    #     else:
    #         raise e
    # _assert_secret_sync_class(
    #     result=enable_result,
    #     **expected_result
    # )
    # _assert_role_assignments(
    #     initial_assignment_names=initial_role_list,
    #     kv_id=kv_id,
    #     mi_principal_id=mi_principal_id
    # )
    # # note that --skip-ra results in the role assignments not applied, the secrets will not be synced

    # # list
    # list_result = run(f"az iot ops secretsync list -n {instance_name} -g {resource_group}")
    # assert len(list_result) == 1
    # _assert_secret_sync_class(
    #     result=list_result[0],
    #     **expected_result
    # )

    # # disable
    # run(f"az iot ops secretsync disable -n {instance_name} -g {resource_group} -y")

    # # second enable with custom name
    # spc_name = generate_random_string(force_lower=True)
    # enable_result = run(
    #     f"az iot ops secretsync enable -n {instance_name} -g {resource_group} "
    #     f"--mi-user-assigned {mi_id} --kv-resource-id {kv_id} --spc {spc_name} "
    #     f"--skip-ra false {'--self-hosted-issuer' if use_self_hosted_issuer else ''} "
    # )
    # # TODO: phase 2 - direct cluster connection for --self-hosted-issuer
    # _assert_secret_sync_class(
    #     result=enable_result,
    #     spc_name=spc_name,
    #     **expected_result
    # )
    # _assert_role_assignments(
    #     initial_assignment_names=initial_role_list,
    #     kv_id=kv_id,
    #     mi_principal_id=mi_principal_id,
    #     expected_secretsync_roles=True
    # )
    # _assert_cluster_side_sync(kv_id=kv_id, tracked_files=tracked_files, spc_name=spc_name)

    # # disable
    # run(f"az iot ops secretsync disable -n {instance_name} -g {resource_group} -y")
    
    # add cert to trust list
    cert_file = Path(__file__).parent.joinpath("certificate.der")
    result = run(f"az iot ops connector opcua trust add --instance {instance_name} -g {resource_group} --certificate-file {cert_file} --overwrite-secret")

    # check kv secret has been created
    _assert_kv_secret_exists(kv_id=kv_id, cert_file="certificate.der")
    # check secret entry exist in spc
    _assert_spc_secret_exists(spc_name=spc_name, resource_group=resource_group, cert_file="certificate.der")
    # check secret entry exist in secretsync
    _assert_ssc_secret_exists(result=result, instance_name=instance_name, resource_group=resource_group, cert_file="certificate.der")
    # check cluster side secret is being synced

    # show secret sync
    show_result = run(f"az iot ops connector opcua trust show --instance {instance_name} -g {resource_group}")
    assert show_result["name"] == OPCUA_TRUST_LIST_SECRET_SYNC_NAME

    # remove cert from trust list
    result = run(f"az iot ops connector opcua trust remove --instance {instance_name} -g {resource_group} --certificate-names 'certificate-der' -y --include-secrets")
    # check kv secret has been removed
    _assert_kv_secret_not_exists(kv_id=kv_id, cert_file="certificate.der")
    # check secret entry removed from spc
    _assert_spc_secret_not_exists(spc_name=spc_name, resource_group=resource_group, cert_file="certificate.der")
    # check secret entry removed from secretsync
    _assert_ssc_secret_not_exists(instance_name=instance_name, resource_group=resource_group, cert_file="certificate.der")
    # # check cluster side secret is removed
    # _assert_cluster_side_secret_not_exists(instance_name=instance_name, resource_group=resource_group, cert_file="certificate.der")

def _assert_kv_secret_exists(kv_id: str, cert_file: str):
    kv_name = kv_id.rsplit("/", maxsplit=1)[-1]
    p = Path(cert_file)
    # file_name = p.name
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

def _assert_spc_secret_exists(spc_name: str, resource_group: str, cert_file: str):
    p = Path(cert_file)
    # file_name = p.name
    file_name_info = (p.stem, p.suffix)
    cert_extension = file_name_info[1].replace(".", "")
    secret_name = f"{file_name_info[0]}-{cert_extension}"
    spc_record = run(f"az iot ops secretsync show -n {spc_name} -g {resource_group}")
    assert spc_record
    objects = spc_record["properties"].get("objects", "")
    assert any([obj.get("objectName", "") == secret_name for obj in objects])
    return

def _assert_ssc_secret_exists(
    result: dict,
    extended_location: str,
    resource_group: str,
    kv_name: str,
    mi_client_id: str,
    cert_file: str,
    ssc_name: Optional[str] = None,
):
    p = Path(cert_file)
    # file_name = p.name
    file_name_info = (p.stem, p.suffix)
    cert_extension = file_name_info[1].replace(".", "")
    secret_name = f"{file_name_info[0]}-{cert_extension}"
    assert result["extendedLocation"]["name"] == extended_location
    assert result["resourceGroup"] == resource_group
    if ssc_name:
        assert result["name"] == ssc_name
    else:
        assert result["name"].startswith("spc-ops-")
    secret_mappings = result["properties"].get("secretMappings", [])
    assert any([mapping.get("secretName", "") == secret_name for mapping in secret_mappings])

    assert result["properties"]["keyvaultName"] == kv_name
    assert result["properties"]["clientId"] == mi_client_id

def _assert_kv_secret_not_exists(kv_id: str, cert_file: str):
    kv_name = kv_id.rsplit("/", maxsplit=1)[-1]
    p = Path(cert_file)
    # file_name = p.name
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

def _assert_spc_secret_not_exists(spc_name: str, resource_group: str, cert_file: str):
    p = Path(cert_file)
    # file_name = p.name
    file_name_info = (p.stem, p.suffix)
    cert_extension = file_name_info[1].replace(".", "")
    secret_name = f"{file_name_info[0]}-{cert_extension}"
    spc_record = run(f"az iot ops secretsync show -n {spc_name} -g {resource_group}")
    assert spc_record
    objects = spc_record["properties"].get("objects", "")
    assert not any([obj.get("objectName", "") == secret_name for obj in objects])
    return

def _assert_ssc_secret_not_exists(
    result: dict,
    extended_location: str,
    resource_group: str,
    kv_name: str,
    mi_client_id: str,
    cert_file: str,
    ssc_name: Optional[str] = None,
):
    p = Path(cert_file)
    # file_name = p.name
    file_name_info = (p.stem, p.suffix)
    cert_extension = file_name_info[1].replace(".", "")
    secret_name = f"{file_name_info[0]}-{cert_extension}"
    assert result["extendedLocation"]["name"] == extended_location
    assert result["resourceGroup"] == resource_group
    secret_mappings = result["properties"].get("secretMappings", [])
    assert not any([mapping.get("secretName", "") == secret_name for mapping in secret_mappings])
    if ssc_name:
        assert result["name"] == ssc_name
    else:
        assert result["name"].startswith("spc-ops-")
    assert result["properties"]["keyvaultName"] == kv_name
    assert result["properties"]["clientId"] == mi_client_id
