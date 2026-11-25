# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import random
import os
import shlex
from copy import deepcopy
from typing import Any, Dict, List

import pytest
from azure.cli.core import get_default_cli

from azext_edge.edge.providers.orchestration.common import (
    EXTENSION_ALIAS_TO_TYPE_MAP,
    EXTENSION_TYPE_ACS,
    EXTENSION_TYPE_OPS,
    EXTENSION_TYPE_PLATFORM,
)
from azext_edge.edge.providers.orchestration.runtime_catalog import get_runtime_catalog
from azext_edge.edge.util import parse_kvp_nargs
from azext_edge.edge.providers.orchestration.runtime_profiles import (
    RuntimeChannel, parse_runtime_version, resolve_runtime_identity,
)

from ...generators import generate_random_string
from ...helpers import process_additional_args, run, strip_quotes
from ...runtime_checks import assert_runtime, configured_baseline, read_runtime

EXTENSION_TYPE_TO_ALIAS_MAP = {
    val: key
    for key, val in EXTENSION_ALIAS_TO_TYPE_MAP.items()
    if val not in [EXTENSION_TYPE_ACS, EXTENSION_TYPE_PLATFORM]
}
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


@pytest.mark.upgrade
def test_upgrade(upgrade_int_setup):
    if os.environ.get("azext_edge_internal_upgrade_versions"):
        pytest.skip("Dedicated internal-upgrade validation is configured.")
    additional_args = upgrade_int_setup["additionalUpgradeArgs"] or ""
    resource_group = upgrade_int_setup["resourceGroup"]
    instance_name = upgrade_int_setup["instanceName"]
    channel = os.environ.get("azext_edge_runtime_channel")
    baseline = configured_baseline()
    if channel:
        source = assert_runtime(instance_name, resource_group, channel, baseline)
        # Qualification always targets the bundled profile, not arbitrary overrides.
        assert not additional_args, "Do not override the target in a channel qualification job."

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
    if channel:
        target = assert_runtime(instance_name, resource_group, channel)
        assert source.instance_id == target.instance_id
        assert source.identity.channel == target.identity.channel
        assert source.identity.train == target.identity.train
        if baseline:
            from azext_edge.edge.providers.orchestration.runtime_profiles import parse_runtime_version

            assert parse_runtime_version(source.identity.version) < parse_runtime_version(target.identity.version)
            # This is an actual version upgrade, not the random configuration/repair
            # scenario below. Migration-specific assertions belong to the supplied path.
            return
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

    runtime, _, extensions = read_runtime(instance_name, resource_group)
    profile = get_runtime_catalog(get_default_cli().cloud.name).for_upgrade(runtime.identity)
    assert runtime.identity == profile.identity, "Pin-clear coverage requires the bundled runtime to be installed."
    ops_extension = next(
        ext for ext in extensions if ext["properties"]["extensionType"].lower() == EXTENSION_TYPE_OPS
    )
    original_config = deepcopy(ops_extension["properties"].get("configurationSettings") or {})
    original_tag = original_config.get("connectors.image.tag")
    try:
        run(f"{command} --ops-config connectors.image.tag={profile.require_opcua_connector_version()}")
        pinned_ext_map = {
            EXTENSION_TYPE_TO_ALIAS_MAP[ext["properties"]["extensionType"].lower()]: ext
            for ext in get_extensions(cluster_id)
            if ext["properties"]["extensionType"].lower() in EXTENSION_TYPE_TO_ALIAS_MAP
        }
        assert pinned_ext_map["ops"]["properties"]["configurationSettings"]["connectors.image.tag"] == (
            profile.require_opcua_connector_version()
        )
        run(f"{command} --cct")
        assert_extensions(cluster_id, pinned_ext_map, "--cct")
    finally:
        restore_config = f"connectors.image.tag={original_tag}" if original_tag is not None else "connectors.image.tag"
        run(f"{command} --ops-config {restore_config}")
        restored_ops = next(
            ext for ext in get_extensions(cluster_id)
            if ext["properties"]["extensionType"].lower() == EXTENSION_TYPE_OPS
        )
        assert (restored_ops["properties"].get("configurationSettings") or {}) == original_config
    if channel:
        assert_runtime(instance_name, resource_group, channel)


@pytest.mark.upgrade
@pytest.mark.serial
def test_internal_dev_upgrades(upgrade_int_setup):
    versions = os.environ.get("azext_edge_internal_upgrade_versions")
    if not versions:
        pytest.skip("Set azext_edge_internal_upgrade_versions to two ascending dev build versions.")
    assert not os.environ.get("azext_edge_runtime_channel"), (
        "Internal upgrades require a dedicated instance outside bundled runtime qualification."
    )
    assert get_default_cli().cloud.name == "AzureCloud", "Dev upgrade validation requires Public Azure."
    assert not upgrade_int_setup["additionalUpgradeArgs"], "Do not override dedicated internal-upgrade arguments."
    versions = [version.strip() for version in versions.split(",")]
    assert len(versions) == 2, "Supply exactly two ascending dev build versions."
    targets = [
        resolve_runtime_identity(version, "dev", allow_unbundled_dev=True) for version in versions
    ]
    name, group = upgrade_int_setup["instanceName"], upgrade_int_setup["resourceGroup"]
    source, _, _ = read_runtime(name, group, allow_unbundled_integration=True, allow_unbundled_dev=True)
    source.require_ready()
    assert source.identity.channel == RuntimeChannel.STABLE and source.identity.train in {"stable", "integration"}, (
        "Start internal-upgrade validation from a GA stable/integration baseline."
    )
    assert source.auto_upgrade_minor_version is False, "Disable automatic upgrades on the dedicated instance."
    assert parse_runtime_version(source.identity.version) < parse_runtime_version(targets[0].version)
    assert parse_runtime_version(targets[0].version) < parse_runtime_version(targets[1].version)
    for target in targets:
        run(shlex.join([
            "az", "iot", "ops", "upgrade", "-n", name, "-g", group,
            "--ops-version", target.version, "--ops-train", target.train,
            "--force", "--yes", "--no-progress",
        ]))
        observed, _, _ = read_runtime(name, group, allow_unbundled_integration=True, allow_unbundled_dev=True)
        observed.require_ready()
        assert observed.instance_id == source.instance_id
        assert observed.identity == target, f"Expected {target}, observed {observed.identity}."
        assert observed.auto_upgrade_minor_version is False


def assert_extensions(cluster_id: str, original_ext_map: Dict[str, Any], additional_args: str = ""):
    original_ext_map = deepcopy(original_ext_map)
    additional_args_dict = process_additional_args(additional_args)

    # update the original extensions to the correct value
    for arg, value in additional_args_dict.items():
        arg = arg.strip("-").lower()
        if arg in {"clear_connector_tag", "cct"}:
            if value:
                original_ext_map["ops"]["properties"]["configurationSettings"].pop("connectors.image.tag", None)
            continue
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
