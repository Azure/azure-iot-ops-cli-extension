# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Real command registration, parser, expansion and validation; no account or ARM access."""

from copy import copy, deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from azure.cli.core import AzCli
from azure.cli.core.azclierror import ValidationError
from azure.cli.core.commands import AzCliCommandInvoker, CliCommandType, _explode_list_args
from azure.cli.core.commands.parameters import get_three_state_flag
from azure.cli.core.commands.validators import IterateValue
from azure.cli.core.parser import AzCliCommandParser
from knack.arguments import CLIArgumentType, ignore_type
from knack.cli import CLI
from knack.events import EVENT_INVOKER_POST_PARSE_ARGS, EVENT_INVOKER_PRE_PARSE_ARGS
from knack.help_files import helps

from azext_edge import OpsExtensionCommandsLoader
from azext_edge.edge.providers.orchestration import runtime_requirements
from azext_edge.edge.providers.orchestration.runtime import OperationRequirements, ParameterRequirement, RuntimeContext
from azext_edge.edge.providers.orchestration.runtime_commands import (
    PREVIEW_RUNTIME_NOTICE, RuntimeTarget, get_runtime_notice_targets,
)
from azext_edge.edge.providers.orchestration.runtime_profiles import RuntimeChannel, RuntimeIdentity


PREVIEW_ONLY = OperationRequirements("Synthetic capability", channels={RuntimeChannel.PREVIEW})


def synthetic_handler(
    cmd, instance_name="instance", resource_group_name="rg", mode="Preview", enabled=False, count=0,
    modes=None, instance_features=None, other_name=None, other_rg=None, target_subscription=None,
    force=False, confirm_yes=False, no_preflight=False, use_preview=False, ensure_latest=False,
):
    """Signature used by Azure CLI argument reflection, without validation boilerplate."""


def runtime(channel=RuntimeChannel.STABLE, version=None, issues=()):
    version = version or ("1.6.0-preview.4" if channel == RuntimeChannel.PREVIEW else "1.5.7")
    return RuntimeContext(
        instance_id="instance", custom_location_id="location", cluster_id="cluster", extension_id="extension",
        identity=RuntimeIdentity(channel, version, channel.value), requested_version=version,
        provisioning_state="Succeeded", readiness_issues=issues,
    )


@pytest.fixture
def invocation(mocker, tmp_path):
    # Initialize Knack's real event/config plumbing but not AzCli's account caches.
    cli = AzCli.__new__(AzCli)
    CLI.__init__(cli, cli_name="az", config_dir=str(tmp_path))
    cli.cloud = Mock(profile="latest")
    cli.local_context = SimpleNamespace(is_on=False)
    cli.data["subscription_id"] = "default-subscription"
    cli.data["completer_active"] = False
    invoker = AzCliCommandInvoker.__new__(AzCliCommandInvoker)
    invoker.cli_ctx = cli
    invoker.data = {}
    cli.invocation = invoker
    loader = OpsExtensionCommandsLoader(cli)
    invoker.commands_loader = loader
    mocker.patch("azext_edge.edge.util.version_check.check_latest")
    mocker.patch("azure.cli.core._profile.Profile.get_raw_token", side_effect=AssertionError("authentication"))
    instances = mocker.patch("azext_edge.edge.providers.orchestration.resources.instances.Instances")
    instances.return_value.get_runtime_context.return_value = runtime()

    def register(command_name="iot ops synthetic", validator=None, argument_validator=None,
                 registration_method="command", **metadata):
        group_name, verb = command_name.rsplit(" ", 1)
        command_type = CliCommandType(operations_tmpl=__name__ + "#{}")
        with loader.command_group(
            group_name, command_type=command_type, custom_command_type=command_type,
        ) as group:
            getattr(group, registration_method)(verb, "synthetic_handler", validator=validator, **metadata)
        command = loader.command_table[command_name]
        command.load_arguments()
        # MainCommandsLoader normally supplies the global ignored cmd argument.
        command.update_argument("cmd", ignore_type)
        command.update_argument("mode", CLIArgumentType(options_list=["--mode", "-m"], validator=argument_validator))
        command.update_argument("enabled", get_three_state_flag())
        command.update_argument("count", CLIArgumentType(type=int))
        for dest in ("modes", "instance_features"):
            command.update_argument(dest, CLIArgumentType(nargs="+"))
        writer = Mock(return_value={})
        command.handler = writer
        help_handler = Mock()

        def execute(arguments=(), expanded_targets=None, help_command=None):
            selected_command = help_command or command_name
            invoker.data["command_string"] = selected_command
            cli.data["runtime_notice_targets"] = get_runtime_notice_targets(loader.command_table)
            global_parser = AzCliCommandParser.create_global_parser(cli_ctx=cli)
            invoker.parser = AzCliCommandParser(
                cli_ctx=cli, cli_help=help_handler, prog="az", parents=[global_parser],
            )
            invoker.parser.load_command_table(loader)
            args = selected_command.split() + list(arguments)
            cli.raise_event(EVENT_INVOKER_PRE_PARSE_ARGS, args=args)
            namespace = invoker.parser.parse_args(args)
            cli.raise_event(EVENT_INVOKER_POST_PARSE_ARGS, command=command_name, args=namespace)
            if expanded_targets:
                # Same values the ARM --ids parser supplies; use the actual CLI
                # expansion and validator methods, including per-job subscriptions.
                namespace.instance_name = IterateValue([item[0] for item in expanded_targets])
                namespace.resource_group_name = IterateValue([item[1] for item in expanded_targets])
                namespace._subscription = IterateValue([item[2] for item in expanded_targets])
            jobs = []
            for expanded in _explode_list_args(namespace):
                job = copy(command)
                job.cli_ctx = copy(cli)
                job.cli_ctx.data = deepcopy(cli.data)
                expanded.cmd = expanded._cmd = job
                if hasattr(expanded, "_subscription"):
                    job.cli_ctx.data["subscription_id"] = expanded._subscription
                invoker._validation(expanded)
                jobs.append((job, expanded))
            for job, expanded in jobs:
                job(invoker._filter_params(expanded))
            return jobs

        return SimpleNamespace(
            execute=execute, command=command, writer=writer, instances=instances, cli=cli,
            help_handler=help_handler,
        )

    return register


@pytest.mark.parametrize("registration", ["metadata", "registry"])
@pytest.mark.parametrize("label", [False, True])
@pytest.mark.parametrize("help_command", ["iot ops synthetic show", "iot ops synthetic"])
def test_fixed_runtime_notice_for_offline_help(invocation, mocker, caplog, registration, label, help_command):
    name = "iot ops synthetic show"
    metadata = {"runtime_requirement": PREVIEW_ONLY} if registration == "metadata" else {}
    if registration == "registry":
        mocker.patch.dict(runtime_requirements.COMMAND_REQUIREMENTS, {name: PREVIEW_ONLY})
    call = invocation(command_name=name, is_preview=label, **metadata)
    original_help = dict(helps)
    preview_info = call.command.preview_info
    with pytest.raises(SystemExit) as result:
        call.execute(["--help"], help_command=help_command)
    assert result.value.code == 0
    assert caplog.messages.count(PREVIEW_RUNTIME_NOTICE) == 1
    assert helps == original_help
    assert call.command.preview_info is preview_info
    call.instances.assert_not_called()
    call.writer.assert_not_called()
    call.help_handler.show_help.assert_called_once()


def test_runtime_notice_once_per_invocation_not_per_target(invocation, caplog):
    call = invocation(runtime_requirement=PREVIEW_ONLY)
    call.instances.return_value.get_runtime_context.return_value = runtime(RuntimeChannel.PREVIEW)
    OpsExtensionCommandsLoader(call.cli)
    for _ in range(2):
        call.execute(expanded_targets=[("first", "rg", "sub"), ("second", "rg", "sub")])
    assert call.writer.call_count == 4
    assert caplog.messages.count(PREVIEW_RUNTIME_NOTICE) == 2


@pytest.mark.parametrize("metadata", [
    {"is_preview": True},
    {"runtime_requirement": OperationRequirements("Stable", channels={RuntimeChannel.STABLE})},
    {"runtime_requirement": OperationRequirements("Shared", channels=set(RuntimeChannel))},
    {"runtime_parameters": (ParameterRequirement("enabled", PREVIEW_ONLY),)},
])
def test_shared_command_help_has_no_preview_runtime_notice(invocation, caplog, metadata):
    call = invocation(**metadata)
    with pytest.raises(SystemExit) as result:
        call.execute(["--help"])
    assert result.value.code == 0
    assert PREVIEW_RUNTIME_NOTICE not in caplog.messages
    call.instances.assert_not_called()


def test_mixed_group_help_has_no_preview_runtime_notice(invocation, caplog):
    invocation(command_name="iot ops synthetic shared")
    call = invocation(command_name="iot ops synthetic restricted", runtime_requirement=PREVIEW_ONLY)
    with pytest.raises(SystemExit) as result:
        call.execute(["--help"], help_command="iot ops synthetic")
    assert result.value.code == 0
    assert PREVIEW_RUNTIME_NOTICE not in caplog.messages
    call.instances.assert_not_called()


@pytest.mark.parametrize("channel", list(RuntimeChannel))
@pytest.mark.parametrize("registration", ["metadata", "registry"])
def test_command_requirement_precedes_handler(invocation, mocker, channel, registration, caplog):
    metadata = {"runtime_requirement": PREVIEW_ONLY} if registration == "metadata" else {}
    if registration == "registry":
        mocker.patch.dict(runtime_requirements.COMMAND_REQUIREMENTS, {"iot ops synthetic": PREVIEW_ONLY})
    call = invocation(**metadata)
    call.instances.return_value.get_runtime_context.return_value = runtime(channel)
    if channel == RuntimeChannel.STABLE:
        with pytest.raises(ValidationError, match="requires a preview runtime"):
            call.execute()
        call.writer.assert_not_called()
    else:
        call.execute()
        call.writer.assert_called_once()
    assert call.command.preview_info is None
    assert caplog.messages.count(PREVIEW_RUNTIME_NOTICE) == 1


@pytest.mark.parametrize("registration_method", ["show_command", "custom_show_command"])
@pytest.mark.parametrize("channel", list(RuntimeChannel))
def test_show_registration_consumes_and_enforces_runtime_metadata(invocation, registration_method, channel):
    call = invocation(registration_method=registration_method, runtime_requirement=PREVIEW_ONLY)
    call.instances.return_value.get_runtime_context.return_value = runtime(channel)
    if channel == RuntimeChannel.STABLE:
        with pytest.raises(ValidationError, match="requires a preview runtime"):
            call.execute()
        call.writer.assert_not_called()
    else:
        call.execute()
        call.writer.assert_called_once()


@pytest.mark.parametrize("registration_method", ["show_command", "custom_show_command"])
def test_show_parameter_metadata_and_custom_target(invocation, registration_method):
    resolver = Mock(return_value=runtime())
    call = invocation(registration_method=registration_method, runtime_target=resolver,
                      runtime_parameters=(ParameterRequirement("enabled", PREVIEW_ONLY),))
    call.execute()
    resolver.assert_not_called()
    call.writer.reset_mock()
    with pytest.raises(ValidationError, match="requires a preview runtime"):
        call.execute(["--enabled"])
    resolver.assert_called_once()
    call.writer.assert_not_called()


@pytest.mark.parametrize("label", [False, True])
def test_unmarked_command_and_cli_preview_label_do_not_discover(invocation, label, caplog):
    call = invocation(is_preview=label)
    call.execute()
    call.instances.assert_not_called()
    call.writer.assert_called_once()
    assert PREVIEW_RUNTIME_NOTICE not in caplog.messages


@pytest.mark.parametrize("parameter", ["mode", "enabled", "count"])
def test_omitted_option_default_does_not_restrict_shared_command(invocation, parameter):
    call = invocation(runtime_parameters=(ParameterRequirement(parameter, PREVIEW_ONLY),))
    call.execute()
    call.instances.assert_not_called()
    call.writer.assert_called_once()


@pytest.mark.parametrize("parameter,arguments", [
    ("mode", ["-m", "Preview"]), ("mode", ["--mode=Preview"]), ("mode", ["--mode", ""]),
    ("enabled", ["--enabled", "false"]), ("count", ["--count", "0"]),
])
def test_explicit_default_false_zero_and_empty_are_requests(invocation, parameter, arguments):
    call = invocation(runtime_parameters=(ParameterRequirement(parameter, PREVIEW_ONLY),))
    with pytest.raises(ValidationError, match="requires a preview runtime"):
        call.execute(arguments)
    call.writer.assert_not_called()


@pytest.mark.parametrize("channel", list(RuntimeChannel))
@pytest.mark.parametrize("arguments,restricted", [
    ([], False), (["--mode", "Stable"], False), (["--mode", "Preview"], True),
    (["--modes", "Stable", "Preview"], True),
    (["--instance-features", "component.mode=Stable"], False),
    (["--instance-features", "component.mode=Preview"], True),
])
def test_only_selected_restricted_values_require_runtime(invocation, channel, arguments, restricted):
    rules = tuple(ParameterRequirement(name, PREVIEW_ONLY, {"Preview"}) for name in (
        "mode", "modes", "component.mode",
    ))
    call = invocation(runtime_parameters=rules)
    call.instances.return_value.get_runtime_context.return_value = runtime(channel)
    if restricted and channel == RuntimeChannel.STABLE:
        with pytest.raises(ValidationError, match="requires a preview runtime"):
            call.execute(arguments)
        call.writer.assert_not_called()
    else:
        call.execute(arguments)
        call.writer.assert_called_once()
    assert call.instances.call_count == int(restricted)


@pytest.mark.parametrize("version,allowed", [("1.5.0", False), ("1.5.7", True), ("1.6.0", False)])
def test_shared_version_bounds(invocation, version, allowed):
    requirement = OperationRequirements(
        "Versioned operation", minimum_version="1.5.5", maximum_version_exclusive="1.6.0",
    )
    call = invocation(runtime_requirement=requirement)
    call.instances.return_value.get_runtime_context.return_value = runtime(version=version)
    if allowed:
        call.execute()
    else:
        with pytest.raises(ValidationError, match="requires AIO version"):
            call.execute()
        call.writer.assert_not_called()


@pytest.mark.parametrize("command_level", [False, True])
def test_existing_validators_are_preserved_without_reclassifying_defaults(invocation, command_level):
    visited = []

    def existing(cmd, namespace):
        visited.append(cmd.cli_ctx.data["subscription_id"])
        namespace.mode = "Preview"

    call = invocation(
        validator=existing if command_level else None,
        argument_validator=None if command_level else existing,
        runtime_parameters=(ParameterRequirement("mode", PREVIEW_ONLY),),
    )
    call.execute()
    assert visited == ["default-subscription"]
    call.instances.assert_not_called()
    call.writer.assert_called_once()


def test_existing_validator_failure_stops_runtime_discovery(invocation):
    def existing(namespace):
        raise ValidationError("existing validation failed")

    call = invocation(validator=existing, runtime_requirement=PREVIEW_ONLY)
    with pytest.raises(ValidationError, match="existing validation failed"):
        call.execute()
    call.instances.assert_not_called()
    call.writer.assert_not_called()


def test_expanded_targets_use_job_subscription_and_all_validate_before_handlers(invocation):
    call = invocation(runtime_requirement=PREVIEW_ONLY)
    call.instances.return_value.get_runtime_context.side_effect = [runtime(RuntimeChannel.PREVIEW), runtime()]
    with pytest.raises(ValidationError, match="requires a preview runtime"):
        call.execute(expanded_targets=[("one", "rg1", "sub1"), ("two", "rg2", "sub2")])
    assert [c.args[0].cli_ctx.data["subscription_id"] for c in call.instances.call_args_list] == ["sub1", "sub2"]
    assert [c.kwargs for c in call.instances.return_value.show.call_args_list] == [
        {"name": "one", "resource_group_name": "rg1"}, {"name": "two", "resource_group_name": "rg2"},
    ]
    assert call.cli.data["subscription_id"] == "default-subscription"
    call.writer.assert_not_called()


def test_nonstandard_target_mapping(invocation):
    call = invocation(
        runtime_requirement=OperationRequirements("Shared"),
        runtime_target=RuntimeTarget("other_name", "other_rg", "target_subscription"),
    )
    call.execute(["--other-name", "mapped", "--other-rg", "mapped-rg", "--target-subscription", "mapped-sub"])
    assert call.instances.call_args.kwargs == {"subscription_id": "mapped-sub"}
    call.instances.return_value.show.assert_called_once_with(name="mapped", resource_group_name="mapped-rg")


def test_missing_mapped_target_fails_closed(invocation):
    call = invocation(runtime_requirement=PREVIEW_ONLY, runtime_target=RuntimeTarget("other_name", "other_rg"))
    with pytest.raises(ValidationError, match="Cannot resolve the AIO runtime"):
        call.execute()
    call.instances.assert_not_called()
    call.writer.assert_not_called()


def test_explicit_target_resolver(invocation):
    resolver = Mock(return_value=runtime(RuntimeChannel.PREVIEW))
    call = invocation(runtime_requirement=PREVIEW_ONLY, runtime_target=resolver)
    jobs = call.execute()
    assert resolver.call_args.args[0] is jobs[0][0]
    call.instances.assert_not_called()
    call.writer.assert_called_once()


def test_not_ready_target_cannot_execute(invocation):
    call = invocation(runtime_requirement=PREVIEW_ONLY)
    call.instances.return_value.get_runtime_context.return_value = runtime(RuntimeChannel.PREVIEW, issues=("pending",))
    with pytest.raises(ValidationError, match="not ready"):
        call.execute()
    call.writer.assert_not_called()


def test_restricted_help_is_offline(invocation):
    call = invocation(runtime_requirement=PREVIEW_ONLY)
    with pytest.raises(SystemExit) as error:
        call.execute(["--help"])
    assert error.value.code == 0
    call.help_handler.show_help.assert_called_once()
    call.instances.assert_not_called()
    call.writer.assert_not_called()


@pytest.mark.parametrize("command_name", ["iot ops create", "iot ops update", "iot ops upgrade"])
@pytest.mark.parametrize("explicit", [False, True])
def test_lifecycle_reuses_explicit_selections_and_existing_discovery(invocation, command_name, explicit):
    call = invocation(command_name, runtime_parameters=(ParameterRequirement("mode", PREVIEW_ONLY),))
    jobs = call.execute(["--mode", "Preview"] if explicit else [])
    job = jobs[0][0]
    call.instances.assert_not_called()
    # Simulate the existing lifecycle's prewrite check after its own profile/runtime
    # selection. Parser defaults cannot reappear as user selections on the second check.
    defaults = {"mode": "Preview"}
    if explicit:
        with pytest.raises(ValidationError, match="requires a preview runtime"):
            runtime_requirements.validate_runtime_requirements(command_name, runtime().identity, defaults, job)
    else:
        runtime_requirements.validate_runtime_requirements(command_name, runtime().identity, defaults, job)
    assert "runtime_requested_arguments" not in vars(call.command)


def test_parameter_registry_is_enforced(invocation, mocker):
    mocker.patch.dict(runtime_requirements.PARAMETER_REQUIREMENTS, {
        "iot ops synthetic": (ParameterRequirement("enabled", PREVIEW_ONLY),),
    })
    call = invocation()
    with pytest.raises(ValidationError, match="requires a preview runtime"):
        call.execute(["--enabled", "false"])
    call.writer.assert_not_called()


@pytest.mark.parametrize("arguments", [["--force"], ["--confirm-yes"], ["--no-preflight"]])
def test_flags_cannot_bypass_command_requirement(invocation, arguments):
    call = invocation(runtime_requirement=PREVIEW_ONLY)
    with pytest.raises(ValidationError, match="requires a preview runtime"):
        call.execute(arguments)
    call.writer.assert_not_called()


def test_explicit_selection_does_not_leak_to_next_invocation(invocation):
    call = invocation(runtime_parameters=(ParameterRequirement("enabled", PREVIEW_ONLY),))
    with pytest.raises(ValidationError, match="requires a preview runtime"):
        call.execute(["--enabled"])
    call.instances.reset_mock()
    call.execute()
    call.instances.assert_not_called()
    call.writer.assert_called_once()


def test_validators_cannot_mutate_away_an_explicit_restricted_value(invocation):
    def existing(namespace):
        namespace.modes.clear()

    call = invocation(
        validator=existing, runtime_parameters=(ParameterRequirement("modes", PREVIEW_ONLY, {"Preview"}),),
    )
    with pytest.raises(ValidationError, match="requires a preview runtime"):
        call.execute(["--modes", "Preview"])
    call.writer.assert_not_called()


def test_init_and_independent_adr_command_remain_unmarked(invocation):
    for name in ("iot ops init", "iot ops ns asset show"):
        call = invocation(name)
        jobs = call.execute()
        call.instances.assert_not_called()
        assert "runtime_requested_arguments" not in vars(jobs[0][0])
        call.writer.assert_called_once()
