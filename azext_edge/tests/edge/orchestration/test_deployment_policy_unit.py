# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from azure.cli.core.azclierror import InvalidArgumentValueError, ValidationError

from azext_edge.edge.providers.orchestration import deployment_policy
from azext_edge.edge.providers.orchestration.common import (
    EXTENSION_MONIKER_OPS,
    EXTENSION_TYPE_CM,
    EXTENSION_TYPE_OPS,
    EXTENSION_TYPE_SSC,
)
from azext_edge.edge.providers.orchestration.deployment_policy import DeploymentPolicy, get_deployment_policy
from azext_edge.edge.providers.orchestration.runtime_catalog import get_runtime_catalog
from azext_edge.edge.providers.orchestration.runtime_profiles import (
    RuntimeChannel, RuntimeProfileCatalog, resolve_runtime_identity,
)
from azext_edge.edge.providers.orchestration.targets import InitTargets
from azext_edge.edge.providers.orchestration.template import TEMPLATE_BLUEPRINT_ENABLEMENT, TEMPLATE_BLUEPRINT_INSTANCE
from azext_edge.edge.providers.orchestration.template_preview import TEMPLATE_BLUEPRINT_INSTANCE_PREVIEW
from azext_edge.edge.providers.orchestration.template_fairfax import (
    TEMPLATE_BLUEPRINT_ENABLEMENT_FAIRFAX,
    TEMPLATE_BLUEPRINT_INSTANCE_FAIRFAX,
)
from azext_edge.edge.providers.orchestration.upgrade2 import UpgradeManager
from azext_edge.edge.providers.orchestration.work import WorkManager
from azext_edge.tests.helpers import build_mock_cmd_for_cloud

from .test_runtime_commands_unit import isolated_work  # noqa: F401
from .test_runtime_profiles_unit import make_profile
from .test_runtime_registration_unit import PREVIEW_ONLY, invocation  # noqa: F401


FF_CONFIGURATION = {
    "schemaRegistry.values.armSchemaRegistry.baseUrl": "https://management.usgovcloudapi.net",
    "schemaRegistry.values.armSchemaRegistry.audience": "https://management.core.usgovcloudapi.net/",
    "Azure.Cluster.Cloud": "AZUREUSGOVERNMENTCLOUD",
}
FF_FOUNDATION = {
    "certManager": {"version": "1.2.1", "train": "preview"},
    "secretStore": {"version": "1.6.0", "train": "preview"},
}


@pytest.mark.parametrize("cloud_name", ["AzureCloud", "AzureUSGovernment", "AzureChinaCloud"])
def test_policy_uses_active_cloud_without_discovery(cloud_name):
    cmd = build_mock_cmd_for_cloud(cloud_name)
    policy = get_deployment_policy(cmd)
    assert policy.cloud_name == cloud_name
    assert policy.aio_configuration == (FF_CONFIGURATION if cloud_name == "AzureUSGovernment" else {})
    assert policy.foundation_targets == (FF_FOUNDATION if cloud_name == "AzureUSGovernment" else {})
    cmd.assert_not_called()


def test_ff_targets_are_isolated_from_public_and_preview_blueprints():
    originals = [
        deepcopy(blueprint.content) for blueprint in (
            TEMPLATE_BLUEPRINT_ENABLEMENT, TEMPLATE_BLUEPRINT_INSTANCE, TEMPLATE_BLUEPRINT_INSTANCE_PREVIEW,
        )
    ]
    for cloud_name in ("AzureCloud", "AzureUSGovernment", "AzureCloud", "AzureUSGovernment"):
        targets = InitTargets(
            "cluster", "rg", cloud_name=cloud_name, ops_config=["custom.setting=keep"],
        )
        enablement, _ = targets.get_ops_enablement_template()
        instance, _ = targets.get_ops_instance_template()
        configuration = instance["variables"]["defaultAioConfigurationSettings"]
        assert configuration["custom.setting"] == "keep"
        if cloud_name == "AzureUSGovernment":
            assert targets.get_extension_versions() == FF_FOUNDATION
            assert FF_CONFIGURATION.items() <= configuration.items()
            assert instance["parameters"]["clusterLocation"]["allowedValues"] == ["usgovvirginia"]
        else:
            assert enablement["variables"]["VERSIONS"] == {"certManager": "1.2.0", "secretStore": "1.5.5"}
            assert enablement["variables"]["TRAINS"] == {"certManager": "stable", "secretStore": "stable"}
            assert not (FF_CONFIGURATION.keys() & configuration.keys())
            assert "allowedValues" not in instance["parameters"]["clusterLocation"]
    assert originals == [
        blueprint.content for blueprint in (
            TEMPLATE_BLUEPRINT_ENABLEMENT, TEMPLATE_BLUEPRINT_INSTANCE, TEMPLATE_BLUEPRINT_INSTANCE_PREVIEW,
        )
    ]


@pytest.mark.parametrize("key", list(FF_CONFIGURATION))
def test_ff_rejects_conflicting_cloud_settings_but_public_keeps_user_overrides(key):
    with pytest.raises(InvalidArgumentValueError, match="must be"):
        InitTargets("cluster", "rg", cloud_name="AzureUSGovernment", ops_config=[f"{key}=wrong"])
    template, _ = InitTargets("cluster", "rg", ops_config=[f"{key}=custom"]).get_ops_instance_template()
    assert template["variables"]["defaultAioConfigurationSettings"][key] == "custom"


def test_ff_accepts_matching_settings_and_preserves_dependency_override_options():
    targets = InitTargets(
        "cluster", "rg", cloud_name="AzureUSGovernment",
        ops_config=[f"{key}={value}" for key, value in FF_CONFIGURATION.items()],
        cm_version="1.2.2", cm_train="stable", ssc_version="1.6.1", ssc_train="stable",
    )
    assert targets.get_extension_versions() == {
        "certManager": {"version": "1.2.2", "train": "stable"},
        "secretStore": {"version": "1.6.1", "train": "stable"},
    }


@pytest.mark.parametrize("location", ["usgovvirginia", "USGovVirginia", "US Gov Virginia", None])
def test_ff_location_allows_supported_region_or_deferred_resolution(location):
    DeploymentPolicy("AzureUSGovernment").validate_location(location)


@pytest.mark.parametrize("location", ["usgovvirginia", "USGovVirginia", "US Gov Virginia"])
@pytest.mark.parametrize("implicit", [False, True])
def test_ff_location_is_canonical_at_custom_location_and_template_receivers(location, implicit):
    manager = WorkManager.__new__(WorkManager)
    manager._apply_foundation = False
    manager._headers = {}
    manager._targets = InitTargets(
        "cluster", "rg", cloud_name="AzureUSGovernment", location=None if implicit else location,
    )
    manager._resource_map = Mock()
    manager._resource_map.connected_cluster.resource = {
        "location": location,
        "properties": {"provisioningState": "Succeeded", "connectivityStatus": "Connected"},
    }
    manager.custom_locations = Mock()
    manager._process_connected_cluster()
    manager._create_or_update_custom_location(extension_ids=[])
    _, parameters = manager._targets.get_ops_instance_template()
    assert manager.custom_locations.create.call_args.kwargs["location"] == "usgovvirginia"
    assert parameters["clusterLocation"]["value"] == "usgovvirginia"


def test_public_display_location_is_not_changed():
    targets = InitTargets("cluster", "rg", location="East US")
    _, parameters = targets.get_ops_instance_template()
    assert targets.location == "East US"
    assert parameters["clusterLocation"]["value"] == "East US"


@pytest.mark.parametrize("location", ["usgovarizona", "eastus", ""])
def test_ff_rejects_other_instance_locations_without_restricting_public(location):
    with pytest.raises(InvalidArgumentValueError, match="usgovvirginia"):
        InitTargets("cluster", "rg", cloud_name="AzureUSGovernment", location=location).get_ops_instance_template()
    InitTargets("cluster", "rg", location=location).get_ops_instance_template()


@pytest.mark.parametrize("no_preflight", [True, False])
def test_ff_create_preview_fails_before_work(mocker, isolated_work, no_preflight):  # noqa: F811
    manager, writer = isolated_work
    manager.cmd = build_mock_cmd_for_cloud("AzureUSGovernment")
    catalog = RuntimeProfileCatalog([make_profile(RuntimeChannel.PREVIEW, "1.6.0-preview.1")])
    mocker.patch("azext_edge.edge.providers.orchestration.work.get_runtime_catalog", return_value=catalog)
    with pytest.raises(ValidationError, match="preview runtime is not supported"):
        manager.execute_ops_init(
            apply_foundation=False, use_preview=True, pre_flight=not no_preflight,
            cluster_name="cluster", resource_group_name="rg",
        )
    writer.assert_not_called()
    manager._bootstrap_ux.assert_not_called()


@pytest.mark.parametrize("apply_foundation", [True, False])
def test_work_manager_passes_active_cloud_to_targets(mocker, isolated_work, apply_foundation):  # noqa: F811
    manager, writer = isolated_work
    manager.cmd = build_mock_cmd_for_cloud("AzureUSGovernment")
    catalog = get_runtime_catalog("AzureUSGovernment")
    mocker.patch("azext_edge.edge.providers.orchestration.work.get_runtime_catalog", return_value=catalog)
    manager.execute_ops_init(
        apply_foundation=apply_foundation, cluster_name="cluster", resource_group_name="rg", location="usgovvirginia",
    )
    assert manager._targets.get_extension_versions() == FF_FOUNDATION
    if not apply_foundation:
        instance, _ = manager._targets.get_ops_instance_template()
        assert FF_CONFIGURATION.items() <= instance["variables"]["defaultAioConfigurationSettings"].items()
    writer.assert_called_once()


def test_cluster_location_is_checked_after_implicit_resolution():
    manager = WorkManager.__new__(WorkManager)
    manager._apply_foundation = False
    manager._targets = InitTargets("cluster", "rg", cloud_name="AzureUSGovernment")
    manager._resource_map = Mock()
    manager._resource_map.connected_cluster.resource = {
        "location": "usgovarizona",
        "properties": {"provisioningState": "Succeeded", "connectivityStatus": "Connected"},
    }
    with pytest.raises(InvalidArgumentValueError, match="usgovvirginia"):
        manager._process_connected_cluster()


def test_ff_preview_command_guard_precedes_runtime_discovery(invocation):  # noqa: F811
    call = invocation(runtime_requirement=PREVIEW_ONLY)
    call.cli.cloud.name = "AzureUSGovernment"
    with pytest.raises(ValidationError, match="preview runtime is not supported"):
        call.execute()
    call.instances.assert_not_called()
    call.writer.assert_not_called()


@pytest.fixture
def ff_upgrade_manager(mocker):
    profile = get_runtime_catalog("AzureUSGovernment").for_create()
    manager = UpgradeManager.__new__(UpgradeManager)
    manager.cmd = build_mock_cmd_for_cloud("AzureUSGovernment")
    manager.targets = InitTargets("cluster", "rg", runtime_profile=profile, cloud_name="AzureUSGovernment")
    manager.runtime_context = SimpleNamespace(identity=profile.identity)
    manager.runtime_profile = profile
    manager.runtime_catalog = RuntimeProfileCatalog([profile])
    manager.resource_map = SimpleNamespace(connected_cluster=SimpleNamespace(connected=True))
    manager.no_progress = True
    manager.force = False
    manager.no_cm_install = True
    manager.instance_record = None
    manager.secretsync_migration = None
    extensions = {}
    for extension_type, version, train in (
        (EXTENSION_TYPE_OPS, profile.identity.version, profile.identity.train),
        (EXTENSION_TYPE_CM, "1.2.1", "preview"),
        (EXTENSION_TYPE_SSC, "1.6.0", "preview"),
    ):
        extensions[extension_type] = {"properties": {
            "extensionType": extension_type, "version": version, "currentVersion": version,
            "releaseTrain": train, "provisioningState": "Succeeded", "autoUpgradeMinorVersion": False,
            "configurationSettings": {"unrelated.setting": "keep"},
        }}
    mocker.patch.object(manager, "_get_extensions_for_plan", return_value=extensions)
    mocker.patch.object(manager, "_validate_foundation_plan")
    mocker.patch.object(manager, "_check_default_registry_needed", return_value=False)
    mocker.patch.object(manager, "_check_opcua_connector_template_needed", return_value=(False, None))
    return manager, extensions


@pytest.mark.parametrize("sync_mode", [None, "full", "add", "none"])
def test_ff_upgrade_repairs_cloud_settings_without_deleting_unrelated_config(ff_upgrade_manager, sync_mode):
    manager, extensions = ff_upgrade_manager
    extensions[EXTENSION_TYPE_OPS]["properties"]["configurationSettings"]["Azure.Cluster.Cloud"] = "AZUREPUBLICCLOUD"
    original = deepcopy(extensions)
    state = manager.analyze_cluster(ops_config=["user.setting=value"], ops_config_sync_mode=sync_mode)
    ops = next(ext for ext in state.extension_upgrades if ext.moniker == EXTENSION_MONIKER_OPS)
    configuration = ops.get_patch()["properties"]["configurationSettings"]
    assert FF_CONFIGURATION.items() <= configuration.items()
    assert configuration["user.setting"] == "value"
    assert "unrelated.setting" not in configuration
    assert all(value is not None for value in configuration.values())
    assert extensions == original


def test_ff_upgrade_does_not_reapply_correct_cloud_settings(ff_upgrade_manager):
    manager, extensions = ff_upgrade_manager
    extensions[EXTENSION_TYPE_OPS]["properties"]["configurationSettings"].update(FF_CONFIGURATION)
    state = manager.analyze_cluster()
    assert not state.override_map[EXTENSION_MONIKER_OPS].config
    assert manager.targets.get_extension_versions() == FF_FOUNDATION


@pytest.mark.parametrize("missing_value", [None, {}])
def test_ff_upgrade_preserves_missing_ops_extension_validation(ff_upgrade_manager, missing_value):
    manager, extensions = ff_upgrade_manager
    if missing_value is None:
        del extensions[EXTENSION_TYPE_OPS]
    else:
        extensions[EXTENSION_TYPE_OPS] = missing_value
    with pytest.raises(ValidationError, match="IoT Operations extension not detected"):
        manager.analyze_cluster()


@pytest.mark.parametrize("force", [False, True])
def test_unmapped_ff_stable_baseline_preserves_internal_compatibility_bypass(ff_upgrade_manager, force):
    manager, extensions = ff_upgrade_manager
    manager.force = force
    properties = extensions[EXTENSION_TYPE_OPS]["properties"]
    properties.update({"version": "1.5.41", "currentVersion": "1.5.41"})
    manager.runtime_context.identity = resolve_runtime_identity(
        "1.5.41", "stable", manager.runtime_catalog.qualification_identities,
    )
    if not force:
        with pytest.raises(ValidationError, match="not mapped to AzureUSGovernment") as error:
            manager.analyze_cluster()
        assert "--force" not in str(error.value)
        return
    state = manager.analyze_cluster()
    ops = next(ext for ext in state.extension_upgrades if ext.moniker == EXTENSION_MONIKER_OPS)
    patch = ops.get_patch()["properties"]
    assert patch["version"] == "1.5.42"
    assert FF_CONFIGURATION.items() <= patch["configurationSettings"].items()
    assert "unrelated.setting" not in patch["configurationSettings"]
    assert properties["configurationSettings"] == {"unrelated.setting": "keep"}


@pytest.mark.parametrize("key", list(FF_CONFIGURATION))
def test_ff_upgrade_rejects_conflicting_settings(ff_upgrade_manager, key):
    manager, _ = ff_upgrade_manager
    with pytest.raises(InvalidArgumentValueError, match="must be"):
        manager.analyze_cluster(ops_config=[f"{key}=wrong"], force=True)


def test_ff_upgrade_constructor_selects_cloud_catalog_and_complete_template(mocker):
    from azext_edge.edge.providers.orchestration import upgrade2

    cmd = build_mock_cmd_for_cloud("AzureUSGovernment")
    profile = get_runtime_catalog("AzureUSGovernment").for_create()
    instances = mocker.patch.object(upgrade2, "Instances").return_value
    record = {"location": "usgovvirginia", "extendedLocation": {"name": "custom-location"}}
    instances.show.return_value = record
    instances.use_runtime_profile.return_value = record
    instances.get_runtime_context.return_value.identity = profile.identity
    instances.get_resource_map.return_value.connected_cluster.cluster_name = "cluster"
    for name in ("RegistryEndpoints", "ConnectorTemplates", "SecretSyncMigrationManager"):
        mocker.patch.object(upgrade2, name)
    manager = UpgradeManager(cmd, "rg", "instance", no_progress=True)
    assert manager.runtime_profile.identity == profile.identity
    assert profile.identity in instances.get_runtime_context.call_args.args[1]
    instances.use_runtime_profile.assert_called_once_with(manager.runtime_profile, record)
    assert manager.targets.get_extension_versions(False)["iotOperations"] == {
        "version": profile.identity.version, "train": profile.identity.train,
    }
    template, _ = manager.targets.get_ops_instance_template()
    assert template["variables"]["resolvedVersion"] == (
        TEMPLATE_BLUEPRINT_INSTANCE_FAIRFAX.content["variables"]["resolvedVersion"]
    )


def test_ff_force_does_not_allow_unreviewed_upgrade_version(ff_upgrade_manager):
    manager, _ = ff_upgrade_manager
    manager.force = True
    with pytest.raises(ValidationError, match="reviewed cloud profile"):
        manager.analyze_cluster(ops_version="1.5.43")


def test_policy_consumes_generated_inputs_and_returns_private_copies(mocker):
    foundation = {
        "certManager": {"version": "9.8.7", "train": "test"},
        "secretStore": {"version": "8.7.6", "train": "test"},
    }
    configuration = {**FF_CONFIGURATION, "Azure.Cluster.Cloud": "TESTCLOUD"}
    enablement = TEMPLATE_BLUEPRINT_ENABLEMENT_FAIRFAX.copy()
    instance = TEMPLATE_BLUEPRINT_INSTANCE_FAIRFAX.copy()
    enablement.content["variables"]["VERSIONS"].update({
        moniker: target["version"] for moniker, target in foundation.items()
    })
    enablement.content["variables"]["TRAINS"].update({
        moniker: target["train"] for moniker, target in foundation.items()
    })
    instance.content["variables"]["defaultAioConfigurationSettings"].update(configuration)
    instance.parameters["clusterLocation"]["allowedValues"] = ["test-region"]
    mocker.patch.object(deployment_policy, "TEMPLATE_BLUEPRINT_ENABLEMENT_FAIRFAX", enablement)
    mocker.patch.object(deployment_policy, "TEMPLATE_BLUEPRINT_INSTANCE_FAIRFAX", instance)
    mocker.patch(
        "azext_edge.edge.providers.orchestration.runtime_catalog.TEMPLATE_BLUEPRINT_INSTANCE_FAIRFAX", instance,
    )
    policy = DeploymentPolicy("AzureUSGovernment")
    assert policy.foundation_targets == foundation
    assert policy.aio_configuration == configuration
    policy.validate_location("test-region")
    policy.foundation_targets["certManager"]["version"] = "mutated"
    policy.aio_configuration["Azure.Cluster.Cloud"] = "mutated"
    assert policy.foundation_targets == foundation
    assert policy.aio_configuration == configuration
    targets = InitTargets("cluster", "rg", cloud_name="AzureUSGovernment", location="test-region")
    assert targets.get_extension_versions()["certManager"] == {"version": "9.8.7", "train": "test"}
    template, _ = targets.get_ops_instance_template()
    assert template["parameters"]["clusterLocation"]["allowedValues"] == ["test-region"]
    assert template["variables"]["defaultAioConfigurationSettings"]["Azure.Cluster.Cloud"] == "TESTCLOUD"
    public = DeploymentPolicy("AzureCloud")
    assert public.foundation_targets == {}
    assert public.aio_configuration == {}
    assert not public.allowed_locations


def test_bundled_ff_source_is_pinned_separately_from_public_runtime():
    assert TEMPLATE_BLUEPRINT_ENABLEMENT_FAIRFAX.commit_id == "dbe60868edbd354658365cf374667446181f97b1"
    assert TEMPLATE_BLUEPRINT_INSTANCE_FAIRFAX.commit_id == "089d884ecbcfd770f845d7e570b9eed5e7581701"
    variables = TEMPLATE_BLUEPRINT_INSTANCE_FAIRFAX.content["variables"]
    assert variables["VERSIONS"] == {"iotOperations": "1.5.42", "connectors": "1.5.19"}
    assert variables["TRAINS"] == {"iotOperations": "stable"}
