# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from azure.cli.core.azclierror import ValidationError

from azext_edge.edge.commands_edge import create_instance, upgrade_instance
from azext_edge.edge.providers.orchestration.common import (
    EXTENSION_TYPE_CM, EXTENSION_TYPE_OPS, EXTENSION_TYPE_PLATFORM, EXTENSION_TYPE_SSC,
)
from azext_edge.edge.providers.orchestration.runtime_dependencies import DependencyIdentity, DependencyRequirement
from azext_edge.edge.providers.orchestration.runtime_profiles import RuntimeChannel, RuntimeProfileCatalog
from azext_edge.edge.providers.orchestration.targets import InitTargets
from azext_edge.edge.providers.orchestration.upgrade2 import ExtensionOperation, ExtensionUpgradeState, UpgradeManager
from azext_edge.edge.providers.orchestration.work import WorkManager
from .test_runtime_profiles_unit import make_profile
from .test_upgrade2_unit import UpgradeScenario
from .test_work_unit import CallKey, ServiceGenerator, build_target_scenario


def requirement(extension_type=EXTENSION_TYPE_SSC, version="1.5.3", train="stable", config=()):
    # Test-only compatibility inputs, not a production qualification claim.
    return DependencyRequirement(extension_type, (DependencyIdentity(version, train),), config)


def installed(extension_type=EXTENSION_TYPE_SSC, **overrides):
    return {"properties": {"extensionType": extension_type, "version": "1.5.3", "currentVersion": "1.5.3",
                           "releaseTrain": "Stable", "provisioningState": "Succeeded",
                           "configurationSettings": {"retained": "yes"}, **overrides}}


def test_compatible_dependency_is_read_only():
    record = installed()
    original = deepcopy(record)
    requirement(config=(("retained", "yes"),)).validate_installed(record)
    assert record == original
    del record["properties"]["version"]
    requirement().validate_installed(record)


@pytest.mark.parametrize("overrides,match", [
    ({"currentVersion": None}, "currentVersion missing"),
    ({"currentVersion": "bad"}, "extension version"),
    ({"currentVersion": "1.5.2", "version": "1.5.2"}, "compatibility policy"),
    ({"currentVersion": "1.5.4", "version": "1.5.4"}, "compatibility policy"),
    ({"version": "1.5.4"}, "requested and installed"),
    ({"releaseTrain": "preview"}, "compatibility policy"),
    ({"releaseTrain": None}, "explicit release train"),
    ({"provisioningState": "Updating"}, "not ready"),
    ({"provisioningState": "Failed"}, "not ready"),
    ({"errorInfo": {"code": "Failure"}}, "failed status"),
    ({"statuses": [{"level": "Error"}]}, "failed status"),
    ({"statuses": ["invalid"]}, "failed status"),
    ({"statuses": {"state": "unknown"}}, "failed status"),
    ({"configurationSettings": {}}, "requires configuration"),
    ({"configurationSettings": ["invalid"]}, "invalid configuration"),
    ({"extensionType": EXTENSION_TYPE_OPS}, "does not match"),
])
def test_incompatible_or_unknown_installed_dependency_is_rejected(overrides, match):
    with pytest.raises(ValidationError, match=match):
        requirement(config=(("retained", "yes"),)).validate_installed(installed(**overrides))


@pytest.mark.parametrize("state", ["Failed", "Canceled"])
def test_known_failed_dependency_can_be_repaired(state):
    record = installed(provisioningState=state, version="1.5.4", errorInfo={"code": "Failure"})
    requirement().validate_observed(record, allow_repair=True)
    with pytest.raises(ValidationError, match="not ready"):
        requirement().validate_observed(record)
    record["properties"]["provisioningState"] = "Updating"
    with pytest.raises(ValidationError, match="not ready"):
        requirement().validate_observed(record, allow_repair=True)


def test_shared_policy_is_immutable_and_duplicate_rules_fail():
    identities = [DependencyIdentity("1.5.3", "stable")]
    configuration = [["retained", "yes"]]
    policy = DependencyRequirement(EXTENSION_TYPE_SSC, identities, configuration)
    identities.clear()
    configuration[0][1] = "changed"
    policy.validate_installed(installed())
    with pytest.raises(ValidationError, match="Duplicate shared"):
        RuntimeProfileCatalog([], dependency_requirements=(policy, policy))
    with pytest.raises(ValidationError, match="at least one reviewed"):
        DependencyRequirement(EXTENSION_TYPE_SSC, ())


@pytest.mark.parametrize("channel", list(RuntimeChannel))
@pytest.mark.parametrize("no_preflight", [False, True])
def test_dependency_gate_blocks_create_before_registration(
    mocker, mocked_cmd, mocked_responses, mocked_sleep, channel, no_preflight,
):
    version = "1.5.7" if channel == RuntimeChannel.STABLE else "1.6.0-preview.4"
    profile = make_profile(channel, version)
    mocker.patch("azext_edge.edge.providers.orchestration.work.get_runtime_catalog", return_value=(
        RuntimeProfileCatalog([profile], dependency_requirements=(requirement(),))
    ))
    mocker.patch("azext_edge.edge.providers.orchestration.work.confirm_preview_creation", return_value=True)
    scenario = build_target_scenario(extension_config_settings={EXTENSION_TYPE_SSC: installed(currentVersion=None)})
    service = ServiceGenerator(scenario=scenario, mocked_responses=mocked_responses, action="create")
    mocked_responses.assert_all_requests_are_fired = False
    with pytest.raises(ValidationError, match="currentVersion missing"):
        create_instance(
            cmd=mocked_cmd, cluster_name=scenario["cluster"]["name"],
            resource_group_name=scenario["resourceGroup"], instance_name=scenario["instance"]["name"],
            schema_registry_resource_id=scenario["schemaRegistry"]["id"],
            adr_namespace_resource_id=scenario["adrNamespace"]["id"],
            use_preview=channel == RuntimeChannel.PREVIEW, no_progress=True, no_preflight=no_preflight,
        )
    assert not service.call_map[CallKey.GET_RESOURCE_PROVIDERS]
    assert all(call.request.method in {"GET", "HEAD"} for call in mocked_responses.calls)


def test_customer_managed_trust_does_not_require_cert_manager(mocker):
    manager = WorkManager.__new__(WorkManager)
    manager._targets = SimpleNamespace(trust_settings={"issuerName": "custom"})
    manager._dependency_requirements = (requirement(EXTENSION_TYPE_CM), requirement())
    mocker.patch.object(WorkManager, "ops_extension_dependencies", new=property(
        lambda _: {EXTENSION_TYPE_CM: None, EXTENSION_TYPE_SSC: installed()}
    ))
    manager._process_extension_dependencies()


@pytest.mark.parametrize("force", [False, True])
def test_incompatible_dependency_target_blocks_all_upgrade_writes(mocker, mocked_cmd, mocked_responses, force):
    scenario = UpgradeScenario().set_extension(EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
    scenario.set_extension(EXTENSION_TYPE_OPS, ext_vers="1.4.0")
    scenario.set_instance_mock(mocked_responses, "instance", "rg")
    profile = make_profile(RuntimeChannel.STABLE, "1.4.105", opcua_connector_version="test-tag")
    # The override is valid semver but not a reviewed dependency identity.
    mocker.patch("azext_edge.edge.providers.orchestration.upgrade2.get_runtime_catalog", return_value=(
        RuntimeProfileCatalog([profile], dependency_requirements=(requirement(),))
    ))
    with pytest.raises(ValidationError, match="compatibility policy"):
        upgrade_instance(mocked_cmd, "rg", "instance", ssc_version="1.5.4", force=force, confirm_yes=True)
    assert not [call for call in mocked_responses.calls if call.request.method in {"PUT", "PATCH", "DELETE"}]


@pytest.mark.parametrize("operation", ["noop", "config", "version", "create", "repair", "user_trust"])
def test_foundation_plan_validates_effective_target(operation):
    manager = UpgradeManager.__new__(UpgradeManager)
    manager.targets = InitTargets("cluster", "rg")
    ext_type = EXTENSION_TYPE_CM if operation in {"create", "user_trust"} else EXTENSION_TYPE_SSC
    manager.runtime_catalog = RuntimeProfileCatalog([], dependency_requirements=(
        requirement(ext_type, config=(("retained", "yes"),)),
    ))
    record = installed(ext_type)
    kwargs = {"extension": record, "desired_version_map": {"version": "1.5.3", "train": "stable"}}
    if operation == "config":
        record["properties"]["configurationSettings"] = {}
        kwargs["desired_config"] = {"retained": "yes"}
    if operation == "version":
        record["properties"].update(version="1.5.2", currentVersion="1.5.2")
    if operation == "create":
        kwargs.update(extension=None, extension_type=ext_type, operation_type=ExtensionOperation.CREATE,
                      desired_config={"retained": "yes"})
    if operation == "repair":
        record["properties"].update(provisioningState="Failed", version="1.5.4")
        # Explicitly repair to a reviewed target, even if the requested pin differs.
        kwargs["desired_version_map"]["version"] = "1.5.4"
        manager.runtime_catalog = RuntimeProfileCatalog([], dependency_requirements=(
            requirement(ext_type, version="1.5.4", config=(("retained", "yes"),)),
        ))
    extensions = [] if operation == "user_trust" else [ExtensionUpgradeState(**kwargs)]
    manager._validate_foundation_plan(SimpleNamespace(extension_upgrades=extensions))


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("required_key", ["AgentOperationTimeoutInMinutes", "reviewedSetting"])
def test_cert_manager_creation_policy_validates_real_plan_not_invented_config(
    mocker, mocked_cmd, mocked_responses, force, required_key,
):
    scenario = UpgradeScenario().set_extension(EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
    scenario.set_extension(EXTENSION_TYPE_CM, remove=True)
    scenario.set_extension(EXTENSION_TYPE_OPS, ext_vers="1.4.0")
    scenario.set_instance_mock(mocked_responses, "instance", "rg")
    cm = scenario.targets.get_extension_versions()["certManager"]
    policy = requirement(EXTENSION_TYPE_CM, cm["version"], cm["train"], config=((required_key, "20"),))
    profile = make_profile(RuntimeChannel.STABLE, "1.4.105", opcua_connector_version="test-tag")
    mocker.patch("azext_edge.edge.providers.orchestration.upgrade2.get_runtime_catalog", return_value=(
        RuntimeProfileCatalog([profile], dependency_requirements=(policy,))
    ))
    if required_key == "reviewedSetting":
        # Eligibility requirements must not silently turn into configuration migrations.
        with pytest.raises(ValidationError, match="requires configuration reviewedSetting"):
            upgrade_instance(mocked_cmd, "rg", "instance", force=force, confirm_yes=True)
    else:
        manager = UpgradeManager(mocked_cmd, "rg", "instance", force=force, no_progress=True)
        state = manager.analyze_cluster()
        creates = [extension for extension in state.extension_upgrades
                   if extension.operation_type == ExtensionOperation.CREATE]
        assert len(creates) == 1
        payload = manager._build_creation_payload(creates[0])["properties"]
        policy.validate_identity(payload["version"], payload["releaseTrain"], payload["configurationSettings"])
        assert payload["configurationSettings"] == {"AgentOperationTimeoutInMinutes": "20"}
    assert not [call for call in mocked_responses.calls if call.request.method in {"PUT", "PATCH", "DELETE"}]


def test_apply_rechecks_dependency_policy_before_any_write(mocker):
    manager = UpgradeManager.__new__(UpgradeManager)
    manager.runtime_catalog = RuntimeProfileCatalog([], dependency_requirements=(requirement(),))
    extension = ExtensionUpgradeState(installed(), {"version": "1.5.4", "train": "stable"})
    state = SimpleNamespace(validate_plan=Mock(), extension_upgrades=[extension])
    writer = mocker.patch.object(manager, "_apply_single_operation")
    with pytest.raises(ValidationError, match="compatibility policy"):
        manager.apply_upgrades(state)
    writer.assert_not_called()


@pytest.mark.parametrize("operation", [ExtensionOperation.CREATE, ExtensionOperation.UPDATE, ExtensionOperation.DELETE])
def test_extension_mutations_target_cluster_resource_group(operation):
    manager = UpgradeManager.__new__(UpgradeManager)
    manager.resource_group_name = "instance-rg"
    manager.targets = InitTargets("cluster", "host-rg")
    clients = Mock()
    manager.resource_map = SimpleNamespace(connected_cluster=SimpleNamespace(
        cluster_name="host-cluster", resource_group_name="host-rg", clusters=SimpleNamespace(extensions=clients),
    ))
    record = installed(EXTENSION_TYPE_CM)
    record["name"] = "cert-manager"
    extension = ExtensionUpgradeState(record, {"version": "1.5.3", "train": "stable"}, operation_type=operation)
    manager._apply_single_operation(extension, operation, {})
    assert len(clients.mock_calls) == 1
    assert clients.mock_calls[0].kwargs["resource_group_name"] == "host-rg"
    assert clients.mock_calls[0].kwargs["cluster_name"] == "host-cluster"
