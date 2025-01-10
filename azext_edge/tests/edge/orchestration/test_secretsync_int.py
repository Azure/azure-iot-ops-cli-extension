# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from time import sleep
from typing import Optional

from azure.cli.core.azclierror import CLIInternalError
from ...generators import generate_random_string
from ...helpers import run

logger = get_logger(__name__)
ROLE_MAX_RETRIES = 5
ROLE_RETRY_INTERVAL = 15


@pytest.fixture
def secretsync_int_setup(settings, tracked_resources):
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
        logger.warning(f"Created KV {kv_name}")
        # add "Key Vault Secrets Officer" role
        run(
            "az role assignment create --role b86a8fe4-44ce-4948-aee5-eccb2c155cd7 "
            f"--assignee {settings.env.azext_edge_sp_object_id} --scope {kv_id}"
        )
        logger.warning("Assigned KV Secrets Officer")

    mi_id = settings.env.azext_edge_user_assigned_mi_id
    if not mi_id:
        mi_id = run(
            f"az identity create -n {'spc' + generate_random_string(size=6)} -g {settings.env.azext_edge_rg}"
        )["id"]
        tracked_resources.append(mi_id)
        logger.warning(f"Created MI {mi_id}")

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
        run(f"az keyvault delete -n {kv_name} -g {settings.env.azext_edge_rg}")
        logger.warning(f"Deleted KV {kv_name}")
        # sometimes it takes a bit to get the deleted list to update
        sleep(ROLE_RETRY_INTERVAL)
        run(f"az keyvault purge -n {kv_name}")
        logger.warning(f"Purged KV {kv_name}")

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
@pytest.mark.secretsync_test
def test_secretsync(secretsync_int_setup):
    resource_group = secretsync_int_setup["resourceGroup"]
    instance_name = secretsync_int_setup["instanceName"]
    kv_id = secretsync_int_setup["keyvaultId"]
    mi_id = secretsync_int_setup["userAssignedId"]
    extended_loc = run(f"az iot ops show -g {resource_group} -n {instance_name}")["extendedLocation"]["name"]
    mi_client_id = run(f"az identity show --ids {mi_id}")["clientId"]
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
    _assert_secret_sync_class(
        result=enable_result,
        **expected_result
    )
    _assert_role_assignments(
        initial_assignment_names=initial_role_list,
        kv_id=kv_id,
        mi_client_id=mi_client_id
    )

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
        "--skip-ra false"
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
        mi_client_id=mi_client_id,
        expected_secretsync_roles=True
    )

    # disable
    run(f"az iot ops secretsync disable -n {instance_name} -g {resource_group} -y")


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
    mi_client_id: str,
    expected_secretsync_roles: bool = False
):
    tries = 0
    while tries < ROLE_MAX_RETRIES:
        try:
            current_assignment_names = [
                role["roleDefinitionName"] for role in run(
                    f"az role assignment list --scope {kv_id} --assignee {mi_client_id}"
                )
            ]
            logger.warning(f"Expected secret sync roles: {expected_secretsync_roles}")
            logger.warning(f"Role Definition list: {current_assignment_names}")
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
