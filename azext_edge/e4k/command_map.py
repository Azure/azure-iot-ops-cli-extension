# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
Load CLI commands
"""
from azure.cli.core.commands import CliCommandType
from azure.cli.core.commands import LongRunningOperation

e4k_resource_ops = CliCommandType(
    operations_tmpl="azext_edge.e4k.commands_e4k#{}"
)
e4i_resource_ops = CliCommandType(
    operations_tmpl="azext_edge.e4k.commands_e4i#{}"
)
edge_resource_ops = CliCommandType(
    operations_tmpl="azext_edge.e4k.commands_edge#{}"
)


class IdentityResultTransform(LongRunningOperation):
    def __call__(self, poller):
        result = super(IdentityResultTransform, self).__call__(poller)
        return result.identity


def load_iotedge_commands(self, _):
    """
    Load CLI commands
    """
    with self.command_group(
        "edge",
        command_type=edge_resource_ops,
        is_preview=True,
    ) as cmd_group:
        cmd_group.command("check", "check")

    with self.command_group(
        "edge support",
        command_type=edge_resource_ops,
    ) as cmd_group:
        cmd_group.command("create-bundle", "support_bundle")

    with self.command_group(
        "edge e4k",
        command_type=e4k_resource_ops,
    ) as cmd_group:
        cmd_group.command("stats", "stats")

    with self.command_group(
        "edge e4k config",
        command_type=e4k_resource_ops,
    ) as cmd_group:
        cmd_group.command("hash", "config")
