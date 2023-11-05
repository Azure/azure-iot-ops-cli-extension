# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

"""
Load CLI commands
"""
from azure.cli.core.commands import CliCommandType

mq_resource_ops = CliCommandType(operations_tmpl="azext_edge.edge.commands_mq#{}")
edge_resource_ops = CliCommandType(operations_tmpl="azext_edge.edge.commands_edge#{}")
asset_resource_ops = CliCommandType(operations_tmpl="azext_edge.edge.commands_assets#{}")


def load_iotops_commands(self, _):
    """
    Load CLI commands
    """
    with self.command_group(
        "iot ops",
        command_type=edge_resource_ops,
        is_preview=True,
    ) as cmd_group:
        cmd_group.command("check", "check")
        cmd_group.command("init", "init")

    with self.command_group(
        "iot ops support",
        command_type=edge_resource_ops,
    ) as cmd_group:
        cmd_group.command("create-bundle", "support_bundle")

    with self.command_group(
        "iot ops mq",
        command_type=mq_resource_ops,
    ) as cmd_group:
        cmd_group.command("stats", "stats")
        cmd_group.command("get-password-hash", "get_password_hash")

    with self.command_group(
        "iot ops asset",
        command_type=asset_resource_ops,
    ) as cmd_group:
        cmd_group.command("create", "create_asset")
        cmd_group.command("delete", "delete_asset")
        cmd_group.command("list", "list_assets")
        cmd_group.command("query", "query_assets")
        cmd_group.show_command("show", "show_asset")
        cmd_group.command("update", "update_asset")

    with self.command_group(
        "iot ops asset data-point",
        command_type=asset_resource_ops,
    ) as cmd_group:
        cmd_group.command("add", "add_asset_data_point")
        cmd_group.command("list", "list_asset_data_points")
        cmd_group.command("remove", "remove_asset_data_point")

    with self.command_group(
        "iot ops asset event",
        command_type=asset_resource_ops,
    ) as cmd_group:
        cmd_group.command("add", "add_asset_event")
        cmd_group.command("list", "list_asset_events")
        cmd_group.command("remove", "remove_asset_event")
