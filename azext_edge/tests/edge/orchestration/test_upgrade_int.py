# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import random
from copy import deepcopy
from typing import Any, Dict, List

import pytest

from azext_edge.edge.providers.orchestration.common import (
    EXTENSION_ALIAS_TO_TYPE_MAP,
)
from azext_edge.edge.util import parse_kvp_nargs

from ...generators import generate_random_string
from ...helpers import process_additional_args, run, strip_quotes

EXTENSION_TYPE_TO_ALIAS_MAP = {val: key for key, val in EXTENSION_ALIAS_TO_TYPE_MAP.items()}
EXTENSIONS = list(EXTENSION_TYPE_TO_ALIAS_MAP.values())


@pytest.fixture
def upgrade_int_setup(settings):
    from ...settings import EnvironmentVariables

    settings.add_to_config(EnvironmentVariables.rg.value)
    settings.add_to_config(EnvironmentVariables.instance.value)
    settings.add_to_config(EnvironmentVariables.upgrade_args.value)

    if not all([settings.env.azext_edge_instance, settings.env.azext_edge_rg]):
        raise AssertionError(
            f"Cannot run init tests without an instance and resource group. Current settings:\n {settings}"
        )

    yield {
        "resourceGroup": settings.env.azext_edge_rg,
        "instanceName": settings.env.azext_edge_instance,
        "additionalUpgradeArgs": strip_quotes(settings.env.azext_edge_upgrade_args),
    }


@pytest.mark.rpsaas
def test_upgrade(upgrade_int_setup):
    additional_args = upgrade_int_setup["additionalUpgradeArgs"] or ""
    resource_group = upgrade_int_setup["resourceGroup"]
    instance_name = upgrade_int_setup["instanceName"]

    # make tree get us the cluster
    instance_tree = run(f"az iot ops show -n {instance_name} -g {resource_group} --tree")
    cluster_name = instance_tree.split("\n", 1)[0].strip()

    cluster_id = run(
        f"az resource show -n {cluster_name} -g {resource_group} "
        "--resource-type Microsoft.Kubernetes/connectedClusters"
    )["id"]

    # get the original extensions and convert it to a map with relevant extensions
    original_ext_list = get_extensions(cluster_id=cluster_id)
    original_ext_map = {}
    for ext in original_ext_list:
        ext_type = ext["properties"]["extensionType"].lower()
        if ext_type in EXTENSION_TYPE_TO_ALIAS_MAP:
            original_ext_map[EXTENSION_TYPE_TO_ALIAS_MAP[ext_type]] = ext

    command = f"az iot ops upgrade -g {resource_group} -n {instance_name} --no-progress -y "

    # run first command with only additional args from input
    run(f"{command} {additional_args}")
    assert_extensions(cluster_id=cluster_id, original_ext_map=original_ext_map, additional_args=additional_args)
    # if additional args present, only run once
    if additional_args:
        return

    # run with 2 random config updates
    upgrade_extensions = random.sample(EXTENSIONS, k=2)
    for ext in upgrade_extensions:
        num_config_args = random.choice(range(1, 3))
        ext_patch = [f"{generate_random_string()}={generate_random_string()}" for _ in range(num_config_args)]
        ext_arg = f"--{ext}-config {' '.join(ext_patch)} "
        additional_args += ext_arg

    run(f"{command} {additional_args}")
    assert_extensions(cluster_id=cluster_id, original_ext_map=original_ext_map, additional_args=additional_args)


def assert_extensions(cluster_id: str, original_ext_map: Dict[str, Any], additional_args: str = ""):
    original_ext_map = deepcopy(original_ext_map)
    additional_args_dict = process_additional_args(additional_args)

    # update the original extensions to the correct value
    for arg, value in additional_args_dict.items():
        arg = arg.strip("-").lower()
        ext, _, operation = arg.partition("_")
        original_ext = original_ext_map[ext]
        if operation == "config":
            parsed_config = parse_kvp_nargs(value.split())
            original_ext["properties"]["configurationSettings"].update(parsed_config)
        elif operation == "version":
            original_ext["properties"]["version"] = value
        elif operation == "train":
            original_ext["properties"]["releaseTrain"] = value

    # post upgrade extensions
    extensions = get_extensions(cluster_id)
    for extension in extensions:
        ext_type = extension["properties"]["extensionType"].lower()
        if ext_type in EXTENSION_TYPE_TO_ALIAS_MAP:
            ext_type = EXTENSION_TYPE_TO_ALIAS_MAP[ext_type]
            ext_props = extension["properties"]
            original_ext_props = original_ext_map[ext_type]["properties"]
            assert ext_props["configurationSettings"] == original_ext_props["configurationSettings"]
            assert ext_props["version"] == original_ext_props["version"]
            assert ext_props["releaseTrain"] == original_ext_props["releaseTrain"]


def get_extensions(cluster_id: str) -> List[Dict[str, Any]]:
    extension_result = run(
        f"az rest --method GET --url {cluster_id}/providers/"
        "Microsoft.KubernetesConfiguration/extensions?api-version=2023-05-01"
    )
    extensions = extension_result["value"]
    while extension_result.get("nextLink"):
        extension_result = run(f"az rest --method GET --url {extension_result['nextLink']}")
        extensions.extend(extension_result["value"])

    return extensions
