# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from azure.cli.core import AzCommandsLoader
from azext_edge.constants import VERSION
from knack.events import EVENT_INVOKER_POST_PARSE_ARGS


def version_check_handler(cli_ctx, **kwargs):
    from .edge.util.version_check import check_latest

    command: str = kwargs.get("command")
    if command:
        if command.startswith("iot ops"):
            if command == "iot ops init":
                ensure_latest = kwargs["args"].ensure_latest
                check_latest(cli_ctx=cli_ctx, force_refresh=ensure_latest, throw_if_upgrade=ensure_latest)
            else:
                check_latest(cli_ctx)


class OpsExtensionCommandsLoader(AzCommandsLoader):
    def __init__(self, cli_ctx=None):
        super(OpsExtensionCommandsLoader, self).__init__(cli_ctx=cli_ctx)
        if cli_ctx:
            cli_ctx.register_event(EVENT_INVOKER_POST_PARSE_ARGS, version_check_handler)

    def load_command_table(self, args):
        from azext_edge.edge.command_map import load_iotops_commands

        load_iotops_commands(self, args)

        return self.command_table

    def load_arguments(self, command):
        from azext_edge.edge.params import load_iotops_arguments

        load_iotops_arguments(self, command)


COMMAND_LOADER_CLS = OpsExtensionCommandsLoader

__version__ = VERSION
