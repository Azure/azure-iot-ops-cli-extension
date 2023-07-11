# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# PRIVATE DISTRIBUTION FOR NDA CUSTOMERS ONLY
# --------------------------------------------------------------------------------------------

"""
Load CLI commands
"""
from azure.cli.core.commands import CliCommandType

e4k_resource_ops = CliCommandType(operations_tmpl="azext_edge.edge.commands_e4k#{}")
edge_resource_ops = CliCommandType(operations_tmpl="azext_edge.edge.commands_edge#{}")


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
        cmd_group.command("get-password-hash", "get_password_hash")
