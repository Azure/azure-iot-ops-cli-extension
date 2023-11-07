# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from azure.cli.core import AzCommandsLoader
from azext_edge.constants import VERSION


class OpsExtensionCommandsLoader(AzCommandsLoader):
    def __init__(self, cli_ctx=None):
        super(OpsExtensionCommandsLoader, self).__init__(cli_ctx=cli_ctx)

    def load_command_table(self, args):
        from azext_edge.edge.command_map import load_iotops_commands
        load_iotops_commands(self, args)

        return self.command_table

    def load_arguments(self, command):
        from azext_edge.edge.params import load_iotops_arguments
        load_iotops_arguments(self, command)


COMMAND_LOADER_CLS = OpsExtensionCommandsLoader

__version__ = VERSION
