# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from os import mkdir
from typing import Dict, Union

import pytest
from knack.log import get_logger

from ....generators import generate_random_string
from ....helpers import run
from .dataflow_helper import assert_dataflow_profile_args
from .helper import assert_init_result, strip_quotes
from .mq_helper import assert_broker_args
from .opcua_helper import assert_simulate_plc_args
from .orchestrator_helper import assert_orchestrator_args

logger = get_logger(__name__)


@pytest.fixture(scope="function")
def init_test_setup(cluster_connection, settings, tracked_resources):
    from ....settings import EnvironmentVariables

    settings.add_to_config(EnvironmentVariables.rg.value)
    settings.add_to_config(EnvironmentVariables.kv.value)
    settings.add_to_config(EnvironmentVariables.cluster.value)
    settings.add_to_config(EnvironmentVariables.sp_app_id.value, is_secret=True)
    settings.add_to_config(EnvironmentVariables.sp_object_id.value, is_secret=True)
    settings.add_to_config(EnvironmentVariables.sp_secret.value, is_secret=True)
    settings.add_to_config(EnvironmentVariables.init_args.value)
    settings.add_to_config(EnvironmentVariables.aio_cleanup.value)
    settings.add_to_config(EnvironmentVariables.init_continue_on_error.value)

    instance_name = f"testcli{generate_random_string(force_lower=True, size=6)}"
    # set up registry
    storage_account_name = f"teststore{generate_random_string(force_lower=True, size=6)}"
    registry_name = f"test-registry-{generate_random_string(force_lower=True, size=6)}"
    registry_namespace1 = f"test-namespace-{generate_random_string(force_lower=True, size=6)}"
    storage_account = run(
        f"az storage account create -n {storage_account_name} -g {settings.env.azext_edge_rg} "
        "--enable-hierarchical-namespace --public-network-access Disabled "
        "--allow-shared-key-access false --allow-blob-public-access false --default-action Deny"
    )
    tracked_resources.append(storage_account['id'])
    registry = run(
        f"az iot ops schema registry create -n {registry_name} -g {settings.env.azext_edge_rg} "
        f"--rn {registry_namespace1} --sa-resource-id {storage_account['id']} "
        "--location eastus2euap"  # TODO: remove once avaliable in all regions
    )
    tracked_resources.append(registry["id"])

    if not all([settings.env.azext_edge_cluster, settings.env.azext_edge_rg, settings.env.azext_edge_kv]):
        raise AssertionError(
            "Cannot run init tests without a connected cluster, resource group, and precreated keyvault. "
            f"Current settings:\n {settings}"
        )

    yield {
        "clusterName": settings.env.azext_edge_cluster,
        "resourceGroup": settings.env.azext_edge_rg,
        "schemaRegistryId": registry["id"],
        "instanceName": instance_name,
        "keyVault": settings.env.azext_edge_kv,
        "servicePrincipalAppId": settings.env.azext_edge_sp_app_id,
        "servicePrincipalObjectId": settings.env.azext_edge_sp_object_id,
        "servicePrincipalSecret": settings.env.azext_edge_sp_secret,
        "additionalCreateArgs": strip_quotes(settings.env.azext_edge_create_args),
        "additionalInitArgs": strip_quotes(settings.env.azext_edge_init_args),
        "continueOnError": settings.env.azext_edge_init_continue_on_error or False
    }
    if settings.env.azext_edge_aio_cleanup:
        run(
            f"az iot ops delete --name {instance_name} -g {settings.env.azext_edge_rg} "
            "-y --no-progress --force --include-deps"
        )


@pytest.mark.init_scenario_test
def test_init_scenario(
    init_test_setup, tracked_files
):
    additional_init_args = init_test_setup["additionalInitArgs"] or ""
    init_arg_dict = _process_additional_args(additional_init_args)
    additional_create_args = init_test_setup["additionalCreateArgs"] or ""
    create_arg_dict = _process_additional_args(additional_create_args)

    # if "ca_dir" in arg_dict:
    #     try:
    #         mkdir(arg_dict["ca_dir"])
    #         tracked_files.append(arg_dict["ca_dir"])
    #     except FileExistsError:
    #         pass
    # elif all(["ca_key_file" not in arg_dict, "ca_file" not in arg_dict]):
    #     tracked_files.append("aio-test-ca.crt")
    #     tracked_files.append("aio-test-private.key")

    cluster_name = init_test_setup["clusterName"]
    resource_group = init_test_setup["resourceGroup"]
    registry_id = init_test_setup["schemaRegistryId"]
    instance_name = init_test_setup["instanceName"]
    # key_vault = init_test_setup["keyVault"]
    # sp_app_id = init_test_setup["servicePrincipalAppId"]
    # sp_object_id = init_test_setup["servicePrincipalObjectId"]
    # sp_secret = init_test_setup["servicePrincipalSecret"]

    command = f"az iot ops init -g {resource_group} --cluster {cluster_name} "\
        f"--sr-resource-id {registry_id} --no-progress {init_arg_dict} "
    #     f"--kv-id {key_vault} --no-progress {additional_args} "
    # if sp_app_id:
    #     command += f"--sp-app-id {sp_app_id} "
    # if sp_object_id:
    #     command += f"--sp-object-id {sp_object_id} "
    # if sp_secret:
    #     command += f"--sp-secret {sp_secret} "

    result = run(command)
    # TODO: add in commands to make sure init succeeded

    create_command = f"az iot ops create -g {resource_group} --cluster {cluster_name} "\
        f"-n {instance_name} --no-progress {create_arg_dict} "

    try:
        assert_init_result(
            result=result,
            cluster_name=cluster_name,
            key_vault=key_vault,
            resource_group=resource_group,
            arg_dict=arg_dict,
            sp_app_id=sp_app_id,
            sp_object_id=sp_object_id
        )

        for assertion in [
            assert_simulate_plc_args,
            assert_broker_args,
            assert_dataflow_profile_args,
            assert_orchestrator_args
        ]:
            assertion(
                namespace=result["clusterNamespace"],
                cluster_name=cluster_name,
                resource_group=resource_group,
                init_resources=result["deploymentState"]["resources"],
                **arg_dict
            )
    except Exception as e:  # pylint: disable=broad-except
        # Note we have this since there are multiple Exceptions that can occur:
        # AssertionError: normal assert error (assuming the expression can get evaluated)
        # CLIInternalError: a run to check existance fails
        # KeyError: one of the expected keys in the result is not present
        # TypeError: one of the values changes expected types and cannot be evaluated correctly (ex: len(None))
        # and more
        if init_test_setup["continueOnError"]:
            pytest.skip(f"Deployment succeeded but init assertions failed. \n{e}")
        raise e


def _process_additional_args(additional_args: str) -> Dict[str, Union[str, bool]]:
    arg_dict = {}
    for arg in additional_args.split("--")[1:]:
        arg = arg.strip().split(" ", maxsplit=1)
        # --simulate-plc vs --desc "potato cluster"
        arg[0] = arg[0].replace("-", "_")
        if len(arg) == 1 or arg[1].lower() == "true":
            arg_dict[arg[0]] = True
        elif arg[1].lower() == "false":
            arg_dict[arg[0]] = False
        else:
            arg_dict[arg[0]] = arg[1]
    return arg_dict
