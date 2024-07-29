# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""
Load CLI commands
"""
from azure.cli.core.commands import CliCommandType

mq_resource_ops = CliCommandType(operations_tmpl="azext_edge.edge.commands_mq#{}")
dataflow_resource_ops = CliCommandType(operations_tmpl="azext_edge.edge.commands_dataflow#{}")
edge_resource_ops = CliCommandType(operations_tmpl="azext_edge.edge.commands_edge#{}")
asset_resource_ops = CliCommandType(operations_tmpl="azext_edge.edge.commands_assets#{}")
aep_resource_ops = CliCommandType(operations_tmpl="azext_edge.edge.commands_asset_endpoint_profiles#{}")


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
        cmd_group.command("delete", "delete")
        cmd_group.command("verify-host", "verify_host")
        cmd_group.show_command("show", "show_instance")
        cmd_group.command("list", "list_instances")
        cmd_group.command("update", "update_instance")

    with self.command_group(
        "iot ops support",
        command_type=edge_resource_ops,
    ) as cmd_group:
        cmd_group.command("create-bundle", "support_bundle")

    with self.command_group(
        "iot ops broker",
        command_type=mq_resource_ops,
    ) as cmd_group:
        cmd_group.command("stats", "stats")
        cmd_group.show_command("show", "show_broker")
        cmd_group.command("list", "list_brokers")

    with self.command_group(
        "iot ops broker listener",
        command_type=mq_resource_ops,
    ) as cmd_group:
        cmd_group.show_command("show", "show_broker_listener")
        cmd_group.command("list", "list_broker_listeners")

    with self.command_group(
        "iot ops broker authn",
        command_type=mq_resource_ops,
    ) as cmd_group:
        cmd_group.show_command("show", "show_broker_authn")
        cmd_group.command("list", "list_broker_authns")

    with self.command_group(
        "iot ops broker authz",
        command_type=mq_resource_ops,
    ) as cmd_group:
        cmd_group.show_command("show", "show_broker_authz")
        cmd_group.command("list", "list_broker_authzs")

    with self.command_group(
        "iot ops dataflow",
        command_type=dataflow_resource_ops,
    ) as cmd_group:
        cmd_group.show_command("show", "show_dataflow")
        cmd_group.command("list", "list_dataflows")

    with self.command_group(
        "iot ops dataflow profile",
        command_type=dataflow_resource_ops,
    ) as cmd_group:
        cmd_group.show_command("show", "show_dataflow_profile")
        cmd_group.command("list", "list_dataflow_profiles")

    with self.command_group(
        "iot ops dataflow endpoint",
        command_type=dataflow_resource_ops,
    ) as cmd_group:
        cmd_group.show_command("show", "show_dataflow_endpoint")
        cmd_group.command("list", "list_dataflow_endpoints")

    with self.command_group(
        "iot ops asset",
        command_type=asset_resource_ops,
    ) as cmd_group:
        cmd_group.command("create", "create_asset")
        cmd_group.command("delete", "delete_asset")
        cmd_group.command("query", "query_assets")
        cmd_group.show_command("show", "show_asset")
        cmd_group.command("update", "update_asset")

    with self.command_group(
        "iot ops asset data-point",
        command_type=asset_resource_ops,
    ) as cmd_group:
        cmd_group.command("add", "add_asset_data_point")
        cmd_group.command("export", "export_asset_data_points")
        cmd_group.command("import", "import_asset_data_points")
        cmd_group.command("list", "list_asset_data_points")
        cmd_group.command("remove", "remove_asset_data_point")

    with self.command_group(
        "iot ops asset event",
        command_type=asset_resource_ops,
    ) as cmd_group:
        cmd_group.command("add", "add_asset_event")
        cmd_group.command("export", "export_asset_events")
        cmd_group.command("import", "import_asset_events")
        cmd_group.command("list", "list_asset_events")
        cmd_group.command("remove", "remove_asset_event")

    with self.command_group(
        "iot ops asset endpoint",
        command_type=aep_resource_ops,
    ) as cmd_group:
        cmd_group.command("create", "create_asset_endpoint_profile")
        cmd_group.command("delete", "delete_asset_endpoint_profile")
        cmd_group.command("query", "query_asset_endpoint_profiles")
        cmd_group.show_command("show", "show_asset_endpoint_profile")
        cmd_group.command("update", "update_asset_endpoint_profile")

    with self.command_group(
        "iot ops asset endpoint certificate",
        command_type=aep_resource_ops,
    ) as cmd_group:
        cmd_group.command("add", "add_asset_endpoint_profile_transport_auth")
        cmd_group.command("list", "list_asset_endpoint_profile_transport_auth")
        cmd_group.command("remove", "remove_asset_endpoint_profile_transport_auth")
