# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, Union
import pytest
from os import mkdir

from ....helpers import run
from .mq_helper import assert_mq_args
from .opcua_helper import assert_simulate_plc_args
from .orchestrator_helper import assert_orchestrator_args
from .helper import assert_init_result


@pytest.fixture(scope="function")
def init_test_setup(cluster_connection, settings):
    from ....settings import EnvironmentVariables
    settings.add_to_config(EnvironmentVariables.rg.value)
    settings.add_to_config(EnvironmentVariables.kv.value)
    settings.add_to_config(EnvironmentVariables.cluster.value)
    settings.add_to_config(EnvironmentVariables.sp_app_id.value, is_secret=True)
    settings.add_to_config(EnvironmentVariables.sp_object_id.value, is_secret=True)
    settings.add_to_config(EnvironmentVariables.sp_secret.value, is_secret=True)
    settings.add_to_config(EnvironmentVariables.init_args.value)
    settings.add_to_config(EnvironmentVariables.aio_cleanup.value)

    if not all([settings.env.azext_edge_cluster, settings.env.azext_edge_rg, settings.env.azext_edge_kv]):
        raise AssertionError(
            "Cannot run init tests without a connected cluster, resource group, and precreated keyvault. "
            f"Current settings:\n {settings}"
        )
    yield {
        "clusterName": settings.env.azext_edge_cluster,
        "resourceGroup": settings.env.azext_edge_rg,
        "keyVault": settings.env.azext_edge_kv,
        "servicePrincipalAppId": settings.env.azext_edge_sp_app_id,
        "servicePrincipalObjectId": settings.env.azext_edge_sp_object_id,
        "servicePrincipalSecret": settings.env.azext_edge_sp_secret,
        "additionalArgs": settings.env.azext_edge_init_args.strip('"')
    }
    if settings.env.azext_edge_aio_cleanup:
        run(
            f"az iot ops delete --cluster {settings.env.azext_edge_cluster} -g {settings.env.azext_edge_rg} "
            "-y --no-progress --force"
        )


@pytest.mark.init_scenario_test
def test_init_scenario(
    init_test_setup, tracked_files
):
    additional_args = init_test_setup["additionalArgs"]
    arg_dict = _process_additional_args(additional_args)

    if "ca_dir" in arg_dict:
        try:
            mkdir(arg_dict["ca_dir"])
            tracked_files.append(arg_dict["ca_dir"])
        except FileExistsError:
            pass
    elif all(["ca_key_file" not in arg_dict, "ca_file" not in arg_dict]):
        tracked_files.append("aio-test-ca.crt")
        tracked_files.append("aio-test-private.key")

    cluster_name = init_test_setup["clusterName"]
    resource_group = init_test_setup["resourceGroup"]
    key_vault = init_test_setup["keyVault"]
    sp_app_id = init_test_setup["servicePrincipalAppId"]
    sp_object_id = init_test_setup["servicePrincipalObjectId"]
    sp_secret = init_test_setup["servicePrincipalSecret"]

    command = f"az iot ops init -g {resource_group} --cluster {cluster_name} "\
        f"--kv-id {key_vault} --no-progress {additional_args} "
    if sp_app_id:
        command += f"--sp-app-id {sp_app_id} "
    if sp_object_id:
        command += f"--sp-object-id {sp_object_id} "
    if sp_secret:
        command += f"--sp-secret {sp_secret} "

    result = run(command)
    assert_init_result(
        result=result,
        cluster_name=cluster_name,
        key_vault=key_vault,
        resource_group=resource_group,
        arg_dict=arg_dict,
        sp_app_id=sp_app_id,
        sp_object_id=sp_object_id
    )

    custom_location = sorted(result["deploymentState"]["resources"])[0]
    for assertion in [
        assert_simulate_plc_args,
        assert_mq_args,
        assert_orchestrator_args
    ]:
        assertion(
            namespace=result["clusterNamespace"],
            cluster_name=cluster_name,
            custom_location=custom_location,
            resource_group=resource_group,
            init_resources=result["deploymentState"]["resources"],
            **arg_dict
        )


def _process_additional_args(additional_args: str) -> Dict[str, Union[str, bool]]:
    arg_dict = {}
    for arg in additional_args.split("--")[1:]:
        arg = arg.strip().split(" ", maxsplit=1)
        # --simualte-plc vs --dp-instance dp-name
        arg[0] = arg[0].replace("-", "_")
        if len(arg) == 1 or arg[1].lower() == "true":
            arg_dict[arg[0]] = True
        elif arg[1].lower() == "false":
            arg_dict[arg[0]] = False
        else:
            arg_dict[arg[0]] = arg[1]
    return arg_dict
