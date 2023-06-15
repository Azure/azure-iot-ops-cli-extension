# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from azure.cli.core import AzCommandsLoader
from azext_edge.constants import VERSION


class EdgeExtensionCommandsLoader(AzCommandsLoader):
    def __init__(self, cli_ctx=None):
        super(EdgeExtensionCommandsLoader, self).__init__(cli_ctx=cli_ctx)

    def load_command_table(self, args):
        from azext_edge.e4k.command_map import load_iotedge_commands
        load_iotedge_commands(self, args)

        return self.command_table

    def load_arguments(self, command):
        from azext_edge.e4k.params import load_iotedge_arguments
        load_iotedge_arguments(self, command)


COMMAND_LOADER_CLS = EdgeExtensionCommandsLoader

__version__ = VERSION
