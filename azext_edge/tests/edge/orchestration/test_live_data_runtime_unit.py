# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Real Live Data registration and runtime hook; no authentication or live resource access."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from azure.cli.core import AzCli
from azure.cli.core.azclierror import ValidationError
from azure.cli.core.commands import AzCliCommandInvoker
from azure.cli.core.parser import AzCliCommandParser
from knack.arguments import CLIArgumentType, ignore_type
from knack.cli import CLI
from knack.events import EVENT_INVOKER_POST_PARSE_ARGS

from azext_edge import OpsExtensionCommandsLoader
from azext_edge.edge.providers.orchestration.runtime import RuntimeContext
from azext_edge.edge.providers.orchestration.runtime_catalog import get_runtime_catalog
from azext_edge.edge.providers.orchestration.runtime_profiles import RuntimeChannel

from . import test_live_data_int as integration


@pytest.fixture
def live_data_invocation(mocker, tmp_path):
    cli = AzCli.__new__(AzCli)
    CLI.__init__(cli, cli_name="az", config_dir=str(tmp_path))
    cli.cloud = Mock(profile="latest")
    cli.local_context = SimpleNamespace(is_on=False)
    cli.data.update(subscription_id="default-subscription", completer_active=False)
    invoker = AzCliCommandInvoker.__new__(AzCliCommandInvoker)
    invoker.cli_ctx = cli
    invoker.data = {}
    cli.invocation = invoker
    loader = OpsExtensionCommandsLoader(cli)
    invoker.commands_loader = loader
    mocker.patch("azext_edge.edge.util.version_check.check_latest")
    mocker.patch("azure.cli.core._profile.Profile.get_raw_token", side_effect=AssertionError("authentication"))
    instances = mocker.patch("azext_edge.edge.providers.orchestration.resources.instances.Instances")
    provider = mocker.patch("azext_edge.edge.commands_live_data.LiveData")
    loader.load_command_table([])

    def prepare(verb, channel):
        name = f"iot ops live-data {verb}"
        invoker.data["command_string"] = name
        loader.command_name = name
        loader.load_arguments(name)
        command = loader.command_table[name]
        command.load_arguments()
        command.update_argument("cmd", ignore_type)
        # MainCommandsLoader normally supplies these common argument aliases.
        command.update_argument("instance_name", CLIArgumentType(options_list=["--instance", "-i", "-n"]))
        command.update_argument("resource_group_name", CLIArgumentType(options_list=["--resource-group", "-g"]))
        if verb == "disable":
            command.update_argument("confirm_yes", CLIArgumentType(options_list=["--yes", "-y"], action="store_true"))
        identity = get_runtime_catalog().get(channel).identity
        instances.return_value.get_runtime_context.return_value = RuntimeContext(
            "instance", "custom-location", "cluster", "extension", identity, identity.version, "Succeeded",
        )
        loader.command_table = {name: command}
        help_handler = Mock()

        def execute(help_only=False):
            parent = AzCliCommandParser.create_global_parser(cli_ctx=cli)
            invoker.parser = AzCliCommandParser(cli_ctx=cli, cli_help=help_handler, prog="az", parents=[parent])
            invoker.parser.load_command_table(loader)
            arguments = ["--help"] if help_only else ["-i", "instance", "-g", "rg"]
            if not help_only and verb == "enable":
                arguments += ["--eg-resource-id", "/subscriptions/sub/resourceGroups/rg/providers/"
                              "Microsoft.EventGrid/namespaces/test"]
            if not help_only and verb == "disable":
                arguments += ["--yes"]
            namespace = invoker.parser.parse_args(name.split() + arguments)
            cli.raise_event(EVENT_INVOKER_POST_PARSE_ARGS, command=name, args=namespace)
            namespace.cmd = namespace._cmd = command
            invoker._validation(namespace)  # pylint: disable=protected-access
            command(invoker._filter_params(namespace))  # pylint: disable=protected-access

        return SimpleNamespace(command=command, execute=execute, instances=instances, provider=provider,
                               help_handler=help_handler)

    return prepare


@pytest.mark.parametrize("verb", ["enable", "disable", "show"])
@pytest.mark.parametrize("channel", list(RuntimeChannel))
def test_live_data_registered_requirement_precedes_provider(live_data_invocation, verb, channel):
    call = live_data_invocation(verb, channel)
    assert call.command.runtime_requirement.channels == frozenset({RuntimeChannel.PREVIEW})
    if channel == RuntimeChannel.STABLE:
        with pytest.raises(ValidationError, match="Live Data requires a preview runtime; the target uses stable"):
            call.execute()
        call.provider.assert_not_called()
    else:
        call.execute()
        call.provider.assert_called_once()
        getattr(call.provider.return_value, verb).assert_called_once()
    call.instances.return_value.show.assert_called_once_with(name="instance", resource_group_name="rg")


@pytest.mark.parametrize("verb", ["enable", "disable", "show"])
def test_live_data_help_stays_offline(live_data_invocation, verb):
    call = live_data_invocation(verb, RuntimeChannel.STABLE)
    with pytest.raises(SystemExit) as result:
        call.execute(help_only=True)
    assert result.value.code == 0
    call.instances.assert_not_called()
    call.provider.assert_not_called()


def test_ga_skips_preview_setup_before_feature_discovery_or_writes(mocker):
    run = mocker.patch.object(integration, "run", side_effect=AssertionError("unexpected feature setup"))
    runtime = SimpleNamespace(identity=SimpleNamespace(channel=RuntimeChannel.STABLE))
    fixture = integration.live_data_setup.__wrapped__(Mock(), Mock(), runtime)
    with pytest.raises(pytest.skip.Exception, match="Preview lifecycle only"):
        next(fixture)
    run.assert_not_called()


@pytest.mark.parametrize("verb", ["enable", "disable", "show"])
def test_ga_integration_rejection_uses_separate_read_only_snapshots(mocker, verb):
    settings = SimpleNamespace(env=SimpleNamespace(azext_edge_instance="instance", azext_edge_rg="rg"))
    runtime = SimpleNamespace(identity=SimpleNamespace(channel=RuntimeChannel.STABLE),
                              instance_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.IoTOperations/"
                                          "instances/instance")
    snapshot = mocker.patch.object(integration, "_ga_configuration_snapshot", return_value={"config": "unchanged"})
    execute = mocker.patch.object(integration.subprocess, "run", return_value=SimpleNamespace(
        returncode=1, stderr="Live Data requires a preview runtime; the target uses stable.",
    ))
    integration.test_live_data_rejected_on_ga_without_mutation(settings, runtime, verb)
    assert snapshot.call_count == 2
    args = execute.call_args.args[0]
    assert args[:5] == ["az", "iot", "ops", "live-data", verb]
    assert ("--eg-resource-id" in args) == (verb == "enable")
    assert ("--yes" in args) == (verb == "disable")
