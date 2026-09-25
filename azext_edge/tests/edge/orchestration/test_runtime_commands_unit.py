# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy
from unittest.mock import Mock, call

import pytest
import responses
from azure.cli.core.azclierror import ValidationError

from azext_edge.edge.commands_edge import create_instance, update_instance
from azext_edge.edge.providers.orchestration import preview, runtime_requirements
from azext_edge.edge.providers.orchestration.common import EXTENSION_TYPE_OPS
from azext_edge.edge.providers.orchestration.resources.instances import Instances
from azext_edge.edge.providers.orchestration.runtime import OperationRequirements, ParameterRequirement
from azext_edge.edge.providers.orchestration.runtime_profiles import RuntimeChannel, RuntimeProfileCatalog
from azext_edge.edge.providers.orchestration.work import WorkManager
from .resources.test_instances_unit import get_instance_endpoint, get_mock_instance_record, mock_runtime_discovery
from .test_runtime_profiles_unit import make_profile
from .test_upgrade2_unit import mocked_upgrade_manager  # noqa: F401
from .test_work_unit import CallKey, ServiceGenerator, build_target_scenario


@pytest.fixture
def preview_profile():
    return make_profile(
        RuntimeChannel.PREVIEW, "1.6.0-preview.10", preview_notice="Test-only preview terms",
        preview_agreement_url="https://example.invalid/test-agreement", opcua_connector_version="test-preview-tag",
    )


@pytest.mark.parametrize("answer", [True, False])
def test_preview_explicit_consent(mocker, preview_profile, answer):
    output = mocker.patch.object(preview.console, "print")
    mocker.patch.object(preview.sys.stdin, "isatty", return_value=True)
    ask = mocker.patch.object(preview.Confirm, "ask", return_value=answer)
    assert preview.confirm_preview_creation(preview_profile) is answer
    assert ask.call_args.kwargs["default"] is True
    assert output.call_args_list == [
        call(preview_profile.preview_notice, markup=False),
        call(preview_profile.preview_agreement_url, markup=False),
    ]


@pytest.mark.parametrize("error", [EOFError, KeyboardInterrupt])
def test_preview_cancel_stops(mocker, preview_profile, error):
    mocker.patch.object(preview.sys.stdin, "isatty", return_value=True)
    mocker.patch.object(preview.Confirm, "ask", side_effect=error)
    assert preview.confirm_preview_creation(preview_profile) is False


@pytest.mark.parametrize("answer, accepted", [("", True), ("y", True), ("Y", True), ("n", False), ("N", False)])
def test_preview_prompt_responses(mocker, preview_profile, answer, accepted):
    mocker.patch.object(preview.sys.stdin, "isatty", return_value=True)
    mocker.patch.object(preview.console, "input", side_effect=[answer])
    assert preview.confirm_preview_creation(preview_profile) is accepted


def test_preview_automation_still_displays_notice(mocker, preview_profile):
    output = mocker.patch.object(preview.console, "print")
    mocker.patch.object(preview.sys.stdin, "isatty", return_value=False)
    ask = mocker.patch.object(preview.Confirm, "ask")
    with pytest.raises(ValidationError, match="--yes"):
        preview.confirm_preview_creation(preview_profile)
    assert preview.confirm_preview_creation(preview_profile, confirm_yes=True)
    assert output.call_count == 4
    ask.assert_not_called()


def test_preview_cannot_skip_missing_approved_terms():
    profile = make_profile(RuntimeChannel.PREVIEW, "1.6.0-preview.1")
    with pytest.raises(ValidationError, match="approved notice"):
        preview.confirm_preview_creation(profile, confirm_yes=True)


@pytest.fixture
def isolated_work(mocker):
    manager = WorkManager.__new__(WorkManager)
    manager.cmd = Mock()
    manager.subscription_id = "subscription"
    mocker.patch.object(manager, "_bootstrap_ux")
    mocker.patch.object(manager, "_build_display")
    writer = mocker.patch.object(manager, "_do_work")
    mocker.patch("azext_edge.edge.providers.orchestration.work.IoTOperationsResourceMap")
    mocker.patch("azext_edge.edge.providers.orchestration.work.WorkManager", return_value=manager)
    return manager, writer


def create_args():
    root = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.DeviceRegistry"
    return dict(
        cmd=Mock(), cluster_name="cluster", resource_group_name="rg", instance_name="instance",
        schema_registry_resource_id=f"{root}/schemaRegistries/sr",
        adr_namespace_resource_id=f"{root}/namespaces/ns", no_progress=True,
    )


@pytest.mark.parametrize("no_preflight", [True, False])
@pytest.mark.parametrize("invalid", ["unbundled", "train", "version", "decline"])
def test_create_runtime_gates_precede_all_work(mocker, isolated_work, preview_profile, no_preflight, invalid):
    manager, writer = isolated_work
    stable = make_profile(RuntimeChannel.STABLE, "1.5.7")
    profiles = [stable] if invalid == "unbundled" else [stable, preview_profile]
    mocker.patch(
        "azext_edge.edge.providers.orchestration.work.get_runtime_catalog", return_value=RuntimeProfileCatalog(profiles)
    )
    mocker.patch("azext_edge.edge.providers.orchestration.work.confirm_preview_creation", return_value=False)
    args = {**create_args(), "use_preview": True, "no_preflight": no_preflight}
    if invalid == "train":
        args["ops_train"] = "stable"
    if invalid == "version":
        args["ops_version"] = "1.6.0"
    if invalid == "decline":
        create_instance(**args)
    else:
        with pytest.raises(ValidationError):
            create_instance(**args)
    writer.assert_not_called()
    manager._bootstrap_ux.assert_not_called()


@pytest.mark.parametrize("use_preview", [False, True])
def test_create_selects_isolated_profile(mocker, isolated_work, preview_profile, use_preview):
    manager, writer = isolated_work
    stable = make_profile(RuntimeChannel.STABLE, "1.5.7")
    mocker.patch(
        "azext_edge.edge.providers.orchestration.work.get_runtime_catalog",
        return_value=RuntimeProfileCatalog([stable, preview_profile]),
    )
    consent = mocker.patch("azext_edge.edge.providers.orchestration.work.confirm_preview_creation", return_value=True)
    create_instance(**create_args(), use_preview=use_preview, confirm_yes=True)
    assert manager._targets.runtime_profile is (preview_profile if use_preview else stable)
    assert consent.call_count == int(use_preview)
    writer.assert_called_once()


def test_init_does_not_select_runtime_or_request_consent(mocker, isolated_work):
    manager, writer = isolated_work
    catalog = mocker.patch("azext_edge.edge.providers.orchestration.work.get_runtime_catalog")
    consent = mocker.patch("azext_edge.edge.providers.orchestration.work.confirm_preview_creation")
    manager.execute_ops_init(apply_foundation=True, cluster_name="cluster", resource_group_name="rg")
    assert manager._targets.runtime_profile is None
    catalog.assert_not_called()
    consent.assert_not_called()
    writer.assert_called_once()


def test_create_requirements_use_effective_override(mocker, isolated_work):
    _, writer = isolated_work
    mocker.patch(
        "azext_edge.edge.providers.orchestration.work.get_runtime_catalog",
        return_value=RuntimeProfileCatalog([make_profile(RuntimeChannel.STABLE, "1.5.7")]),
    )
    mocker.patch.dict(runtime_requirements.COMMAND_REQUIREMENTS, {
        "iot ops create": OperationRequirements("create", minimum_version="1.5.0"),
    })
    with pytest.raises(ValidationError, match="requires AIO version"):
        create_instance(**create_args(), ops_version="1.4.0")
    writer.assert_not_called()


@pytest.mark.parametrize("no_preflight", [False, True])
def test_existing_partial_deployment_blocks_create_before_registration(
    mocked_cmd, mocked_responses, mocked_sleep, no_preflight,
):
    scenario = build_target_scenario(existing_ops_extension=True)
    servgen = ServiceGenerator(scenario=scenario, mocked_responses=mocked_responses, action="create")
    mocked_responses.assert_all_requests_are_fired = False
    with pytest.raises(ValidationError, match="IoT Operations is detected"):
        create_instance(
            cmd=mocked_cmd, cluster_name=scenario["cluster"]["name"],
            resource_group_name=scenario["resourceGroup"], instance_name=scenario["instance"]["name"],
            schema_registry_resource_id=scenario["schemaRegistry"]["id"],
            adr_namespace_resource_id=scenario["adrNamespace"]["id"], no_progress=True, no_preflight=no_preflight,
        )
    assert not servgen.call_map[CallKey.GET_RESOURCE_PROVIDERS]
    assert all(c.request.method in {"GET", "HEAD"} for c in mocked_responses.calls)


@pytest.mark.parametrize("channel", list(RuntimeChannel))
def test_shared_update_with_restricted_parameter_value(mocker, mocked_cmd, mocked_responses, channel):
    instance = get_mock_instance_record("instance", "rg")
    endpoint = get_instance_endpoint(resource_group_name="rg", instance_name="instance")
    mocked_responses.add(responses.GET, endpoint, json=instance)
    version = "1.6.0-preview.4" if channel == RuntimeChannel.PREVIEW else "1.5.7"
    mock_runtime_discovery(mocked_responses, instance, version, channel.value)
    rule = ParameterRequirement(
        "opcua.mode", OperationRequirements("Selected OPC UA mode", frozenset({RuntimeChannel.PREVIEW})),
        frozenset({"Preview"}),
    )
    mocker.patch.dict(runtime_requirements.PARAMETER_REQUIREMENTS, {"iot ops update": (rule,)})
    profile = make_profile(channel, version, opcua_connector_version="test-profile-tag")
    mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.instances.get_runtime_catalog",
        return_value=RuntimeProfileCatalog([profile]),
    )
    # Isolate connector backfill writes while exercising real update ARM discovery and PUT.
    mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector_templates.ConnectorTemplates"
        ".check_default_opcua_template_needed", return_value=(False, None),
    )
    if channel == RuntimeChannel.STABLE:
        with pytest.raises(ValidationError, match="requires a preview runtime"):
            update_instance(mocked_cmd, "instance", "rg", instance_features=["opcua.mode=Preview"])
        assert all(c.request.method == "GET" for c in mocked_responses.calls)
    else:
        mocked_responses.add(responses.PUT, endpoint, json=instance)
        update_instance(mocked_cmd, "instance", "rg", instance_features=["opcua.mode=Preview"], wait_sec=0)
        assert sum(c.request.method == "PUT" for c in mocked_responses.calls) == 1


def test_update_does_not_mutate_supplied_record(mocker, mocked_cmd, mocked_responses):
    instance = get_mock_instance_record("instance", "rg", features={"opcua": {"mode": "Stable"}})
    original = deepcopy(instance)
    mock_runtime_discovery(mocked_responses, instance)
    endpoint = get_instance_endpoint(resource_group_name="rg", instance_name="instance")
    mocked_responses.add(responses.PUT, endpoint, json=instance)
    Instances(mocked_cmd).update("instance", "rg", instance=instance, features=["opcua.mode=Disabled"], wait_sec=0)
    assert instance == original


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.usefixtures("mocked_upgrade_manager")
def test_upgrade_prevalidates_dependencies_before_delete(mocked_cmd, mocked_responses, force):
    from azext_edge.edge.commands_edge import upgrade_instance
    from azext_edge.edge.providers.orchestration.common import EXTENSION_TYPE_CM, EXTENSION_TYPE_PLATFORM
    from .test_upgrade2_unit import UpgradeScenario

    scenario = UpgradeScenario().set_extension(EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
    scenario.set_extension(EXTENSION_TYPE_CM, remove=True)
    scenario.set_extension(EXTENSION_TYPE_OPS, ext_vers="1.4.0")
    scenario.set_instance_mock(mocked_responses, "instance", "rg")
    with pytest.raises(ValidationError, match="downgrade"):
        upgrade_instance(mocked_cmd, "rg", "instance", ops_version="1.3.0", force=force, confirm_yes=True)
    assert not [c for c in mocked_responses.calls if c.request.method in {"PUT", "PATCH", "DELETE"}]


@pytest.mark.usefixtures("mocked_upgrade_manager")
def test_invalid_dependency_plan_blocks_platform_deletion(mocked_cmd, mocked_responses):
    from azext_edge.edge.commands_edge import upgrade_instance
    from azext_edge.edge.providers.orchestration.common import EXTENSION_TYPE_CM, EXTENSION_TYPE_PLATFORM
    from .test_upgrade2_unit import UpgradeScenario

    scenario = UpgradeScenario().set_extension(EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
    scenario.set_extension(EXTENSION_TYPE_OPS, ext_vers="1.4.0")
    scenario.set_extension(EXTENSION_TYPE_CM, ext_vers="2.0.0")
    scenario.set_instance_mock(mocked_responses, "instance", "rg")
    with pytest.raises(ValidationError, match="downgrade"):
        upgrade_instance(mocked_cmd, "rg", "instance", cm_version="1.0.0", confirm_yes=True)
    assert not [c for c in mocked_responses.calls if c.request.method in {"PUT", "PATCH", "DELETE"}]


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("change", ["pin", "missing_installed", "duplicate", "in_progress"])
@pytest.mark.usefixtures("mocked_upgrade_manager")
def test_upgrade_unknown_or_inconsistent_runtime_never_writes(mocked_cmd, mocked_responses, force, change):
    from azext_edge.edge.commands_edge import upgrade_instance
    from .test_upgrade2_unit import UpgradeScenario

    scenario = UpgradeScenario().set_extension(EXTENSION_TYPE_OPS, ext_vers="1.4.0")
    ext = scenario.extensions[EXTENSION_TYPE_OPS]
    if change == "pin":
        ext["properties"]["version"] = "1.5.0"
    elif change == "missing_installed":
        del ext["properties"]["currentVersion"]
    elif change == "duplicate":
        duplicate = deepcopy(ext)
        duplicate["name"] = "other-aio"
        scenario.extensions["duplicate"] = duplicate
    else:
        ext["properties"]["provisioningState"] = "Updating"
    scenario.set_instance_mock(mocked_responses, "instance", "rg")
    with pytest.raises(ValidationError):
        upgrade_instance(mocked_cmd, "rg", "instance", confirm_yes=True, force=force)
    assert not [c for c in mocked_responses.calls if c.request.method in {"PUT", "PATCH", "DELETE"}]


@pytest.mark.parametrize("source,target,train,match", [
    ("1.6.0-preview.10", "1.6.0-preview.4", "preview", "downgrade"),
    ("1.5.7", "1.5.6", "stable", "downgrade"),
    ("1.6.0-preview.10", "1.7.0-preview.11", "preview", "across runtime version cycles"),
])
@pytest.mark.parametrize("force", [False, True])
def test_runtime_boundaries_apply_even_with_force(source, target, train, match, force):
    from .test_upgrade2_unit import build_ext_upgrade_state

    state = build_ext_upgrade_state(
        ext_type=EXTENSION_TYPE_OPS, current_version=source, current_train=train,
        built_in_version=target, built_in_train=train, version_override=target, force=force,
    )
    with pytest.raises(ValidationError, match=match):
        state.validate_upgrade()
    with pytest.raises(ValidationError, match=match):
        state.get_patch()


def test_integration_mapping_cannot_convert_ga_to_preview():
    from azext_edge.edge.providers.orchestration.runtime_profiles import RuntimeIdentity
    from .test_upgrade2_unit import build_ext_upgrade_state

    state = build_ext_upgrade_state(
        ext_type=EXTENSION_TYPE_OPS, current_version="1.5.7", current_train="integration",
        built_in_version="1.6.0-preview.4", built_in_train="integration", force=True,
    )
    state.qualification_identities = (
        RuntimeIdentity(RuntimeChannel.STABLE, "1.5.7", "integration"),
        RuntimeIdentity(RuntimeChannel.PREVIEW, "1.6.0-preview.4", "integration"),
    )
    with pytest.raises(ValidationError, match="GA clusters must remain GA"):
        state.get_patch()


def test_extension_writes_use_cluster_subscription(mocker, mocked_cmd):
    from azext_edge.edge.providers.orchestration.resources.clusters import ConnectedClusters

    cluster = mocker.patch("azext_edge.edge.providers.orchestration.resources.clusters.get_connectedk8s_mgmt_client")
    extension = mocker.patch("azext_edge.edge.providers.orchestration.resources.clusters.get_clusterconfig_mgmt_client")
    ConnectedClusters(mocked_cmd, subscription_id="host-subscription")
    assert cluster.call_args.kwargs["subscription_id"] == "host-subscription"
    assert extension.call_args.kwargs["subscription_id"] == "host-subscription"


def test_runtime_selector_is_normal_create_only_option_and_requires_no_authentication(mocker):
    from azure.cli.core import AzCli
    from azext_edge import OpsExtensionCommandsLoader

    mocker.patch("azure.cli.core.commands.client_factory.get_subscription_id", side_effect=AssertionError("auth"))
    mocker.patch("azure.cli.core._profile.Profile.get_raw_token", side_effect=AssertionError("auth"))
    mocker.patch(
        "azext_edge.edge.providers.orchestration.work.get_runtime_catalog", side_effect=AssertionError("runtime")
    )
    cli = Mock(spec=AzCli)
    cli.cloud = Mock(profile="latest")
    cli.data = {"completer_active": False}
    cli.enable_color = False
    cli.config = Mock()
    cli.invocation = Mock(data={})
    loader = OpsExtensionCommandsLoader(cli)
    cli.invocation.commands_loader = loader
    loader.load_command_table([])
    for name in ("iot ops create", "iot ops init", "iot ops update", "iot ops upgrade", "iot ops get-versions"):
        cli.invocation.data["command_string"] = name
        loader.command_name = name
        loader.load_arguments(name)
        option = loader.argument_registry.get_cli_argument(name, "use_preview").settings
        if name == "iot ops create":
            assert option["options_list"] == ["--use-preview"]
            assert not option.get("is_preview")
        else:
            assert not option
        assert getattr(loader.command_table[name], "preview_info", None) is None


def test_backfill_missing_version_is_rejected_before_instance_write(mocker, mocked_cmd):
    from azext_edge.edge.providers.orchestration.resources.connector_templates import ConnectorTemplates

    record = get_mock_instance_record("instance", "rg", features={"opcua": {"mode": "Disabled"}})
    original = deepcopy(record)
    instances = Instances(mocked_cmd)
    writer = mocker.patch.object(instances.iotops_mgmt_client.instance, "begin_create_or_update")
    mocker.patch.object(ConnectorTemplates, "check_default_opcua_template_needed", return_value=(True, None))
    connector_writer = mocker.patch.object(ConnectorTemplates, "create_default_opcua_template")
    with pytest.raises(ValidationError, match="reviewed connector version"):
        instances._update("instance", "rg", instance=record, features=["opcua.mode=Stable"])
    writer.assert_not_called()
    connector_writer.assert_not_called()
    assert record == original
