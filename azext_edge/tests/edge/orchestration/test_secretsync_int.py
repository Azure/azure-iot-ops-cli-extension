# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from base64 import b64decode
from copy import deepcopy
import json
import pytest
from knack.log import get_logger
from time import sleep
from typing import List, Optional

from azure.cli.core.azclierror import CLIInternalError

from ...generators import generate_random_string
from ...helpers import run

logger = get_logger(__name__)
ROLE_MAX_RETRIES = 5
ROLE_RETRY_INTERVAL = 15


@pytest.fixture
def secretsync_int_setup(settings, tracked_resources: List[str]):
    from ...settings import EnvironmentVariables

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

    mi_id = settings.env.azext_edge_user_assigned_mi_id
    if not mi_id:
        mi_id = run(
            f"az identity create -n {'spc' + generate_random_string(size=6)} -g {settings.env.azext_edge_rg}"
        )["id"]
        tracked_resources.append(mi_id)

    instance_name = settings.env.azext_edge_instance
    resource_group = settings.env.azext_edge_rg
    # list to track initial result if there is something
    initial_list_result = run(f"az iot ops secretsync list -n {instance_name} -g {resource_group}")
    if initial_list_result:
        run(f"az iot ops secretsync disable -n {instance_name} -g {resource_group} -y")

    yield {
        "resourceGroup": resource_group,
        "instanceName": instance_name,
        "keyvaultId": kv_id,
        "userAssignedId": mi_id,
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
def test_secretsync(cluster_connection, secretsync_int_setup, tracked_files: List[str]):
    resource_group = secretsync_int_setup["resourceGroup"]
    instance_name = secretsync_int_setup["instanceName"]
    kv_id = secretsync_int_setup["keyvaultId"]
    mi_id = secretsync_int_setup["userAssignedId"]
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

    initial_role_list = [
        role["roleDefinitionName"] for role in _get_role_list(kv_id, mi_client_id)
    ]

    # enable with skip ra + check if test can be run
    try:
        enable_result = run(
            f"az iot ops secretsync enable -n {instance_name} -g {resource_group} "
            f"--mi-user-assigned {mi_id} --kv-resource-id {kv_id} --skip-ra"
        )
    except CLIInternalError as e:
        if "not enabled as an oidc issuer or for workload identity federation." in e.error_msg:
            pytest.skip("Cluster is not enabled for secretsync.")
        elif "No issuerUrl is available." in e.error_msg:
            use_self_hosted_issuer = True
            enable_result = run(
                f"az iot ops secretsync enable -n {instance_name} -g {resource_group} "
                f"--mi-user-assigned {mi_id} --kv-resource-id {kv_id} --skip-ra --self-hosted-issuer"
            )
        else:
            raise e
    _assert_secret_sync_class(
        result=enable_result,
        **expected_result
    )
    _assert_role_assignments(
        initial_assignment_names=initial_role_list,
        kv_id=kv_id,
        mi_principal_id=mi_principal_id
    )
    _assert_cluster_side_sync(kv_id=kv_id, tracked_files=tracked_files, spc_name=enable_result["name"])

    # list
    list_result = run(f"az iot ops secretsync list -n {instance_name} -g {resource_group}")
    assert len(list_result) == 1
    _assert_secret_sync_class(
        result=list_result[0],
        **expected_result
    )

    # disable
    run(f"az iot ops secretsync disable -n {instance_name} -g {resource_group} -y")

    # second enable with custom name
    spc_name = generate_random_string(force_lower=True)
    enable_result = run(
        f"az iot ops secretsync enable -n {instance_name} -g {resource_group} "
        f"--mi-user-assigned {mi_id} --kv-resource-id {kv_id} --spc {spc_name} "
        f"--skip-ra false {'--self-hosted-issuer' if use_self_hosted_issuer else ''} "
    )
    # TODO: phase 2 - direct cluster connection for --self-hosted-issuer
    _assert_secret_sync_class(
        result=enable_result,
        spc_name=spc_name,
        **expected_result
    )
    _assert_role_assignments(
        initial_assignment_names=initial_role_list,
        kv_id=kv_id,
        mi_principal_id=mi_principal_id,
        expected_secretsync_roles=True
    )
    _assert_cluster_side_sync(kv_id=kv_id, tracked_files=tracked_files, spc_name=spc_name)

    # disable
    run(f"az iot ops secretsync disable -n {instance_name} -g {resource_group} -y")


def _assert_cluster_side_sync(kv_id: str, tracked_files: List[str], spc_name: str):
    # add secret to kv
    secret_name = f"clitest{generate_random_string()}"
    secret_value = generate_random_string(size=100)
    kv_name = kv_id.rsplit("/", maxsplit=1)[1]
    run(
        f"az keyvault secret set --vault-name {kv_name} --name {secret_name} "
        f"--value {secret_value}"
    )

    # get the current secret provider class
    list_result = run("kubectl get secretproviderclass -A -o json")["items"]
    assert list_result
    spc_data = next(spc for spc in list_result if (
        spc["metadata"]["name"] == spc_name if spc_name else spc["metadata"]["name"].startswith("spc-ops-")
    ))
    aio_namespace = spc_data["metadata"]["namespace"]

    # add in the reference for the secret (note that this is a stringified yaml in the json)
    object_string = "array:\n"
    if "objects" in spc_data["spec"]["parameters"]:
        object_string = spc_data["spec"]["parameters"]["objects"]
    object_string += f"    - |\n      objectName: {secret_name}\n      objectType: secret\n"
    spc_data["spec"]["parameters"]["objects"] = object_string

    temp_spc_json = f"temp{generate_random_string(size=6)}.json"
    tracked_files.append(temp_spc_json)
    with open(temp_spc_json, "w", encoding="utf-8") as f:
        json.dump(spc_data, f)

    # generate the secretsync
    secret_key_name = f"targetkey{generate_random_string()}"
    secret_sync_name = f"sync-{generate_random_string(size=6, force_lower=True)}"
    secret_sync_data = deepcopy(SECRET_SYNC_TEMPLATE)
    secret_sync_data["metadata"]["name"] = secret_sync_name
    secret_sync_data["metadata"]["namespace"] = aio_namespace
    secret_sync_data["spec"]["secretProviderClassName"] = spc_name
    secret_sync_data["spec"]["secretObject"]["data"].append({
        "sourcePath": secret_name,
        "targetKey": secret_key_name
    })
    temp_sync_json = f"temp{generate_random_string(size=6)}.json"
    tracked_files.append(temp_sync_json)
    with open(temp_sync_json, "w", encoding="utf-8") as f:
        json.dump(secret_sync_data, f)

    run(f"kubectl apply {temp_spc_json}")
    run(f"kubectl apply {temp_sync_json}")

    # wait a bit to populate secret
    sleep(5)

    # check the secret
    secret_data = run(f"kubectl get secret {secret_sync_name} -n {aio_namespace} -o json")
    assert secret_key_name in secret_data["data"]
    decoded = str(b64decode(secret_data["data"][secret_key_name]), encoding="utf-8")
    assert decoded == secret_value

    run(f"az keyvault secret delete --vault-name {kv_name} --name {secret_name}")


def _assert_secret_sync_class(
    result: dict,
    extended_location: str,
    resource_group: str,
    kv_name: str,
    mi_client_id: str,
    spc_name: Optional[str] = None,
):
    assert result["extendedLocation"]["name"] == extended_location
    assert result["resourceGroup"] == resource_group
    if spc_name:
        assert result["name"] == spc_name
    else:
        assert result["name"].startswith("spc-ops-")

    assert result["properties"]["keyvaultName"] == kv_name
    assert result["properties"]["clientId"] == mi_client_id


def _assert_role_assignments(
    initial_assignment_names: list,
    kv_id: str,
    mi_principal_id: str,
    expected_secretsync_roles: bool = False
):
    tries = 0
    while tries < ROLE_MAX_RETRIES:
        try:
            current_assignment_names = [
                role["roleDefinitionName"] for role in run(
                    f"az role assignment list --scope {kv_id} --assignee {mi_principal_id}"
                )
            ]
            if expected_secretsync_roles:
                assert "Key Vault Secrets User" in current_assignment_names
                assert "Key Vault Reader" in current_assignment_names
            else:
                # role could have been applied before - so just make sure nothing new was applied
                difference_roles = set(current_assignment_names).difference(set(initial_assignment_names))
                assert not difference_roles
            return
        except AssertionError as e:
            tries += 1
            sleep(ROLE_RETRY_INTERVAL)
            if tries == ROLE_MAX_RETRIES:
                raise e


def _get_role_list(
    kv_id: str,
    mi_client_id: str
):
    tries = 0
    while tries < ROLE_MAX_RETRIES:
        try:
            return run(f"az role assignment list --scope {kv_id} --assignee {mi_client_id}")
        except CLIInternalError:
            tries += 1
            sleep(ROLE_RETRY_INTERVAL)

    raise AssertionError("Failed to create user assigned identity. Please retry with a given identity.")


SECRET_SYNC_TEMPLATE = {
    "apiVersion": "secret-sync.x-k8s.io/v1alpha1",
    "kind": "SecretSync",
    "metadata": {
        "annotations": {},
        "generation": 1,
        "name": "",
        "namespace": "",
        "uid": "cbb0b6a9-2565-4e7a-930f-b4c5abc6464b"
    },
    "spec": {
        "secretObject": {
            "data": [],
            "type": "Opaque"
        },
        "secretProviderClassName": "",
        "secretSyncControllerName": "",
        "serviceAccountName": "aio-ssc-sa"
    }
}
