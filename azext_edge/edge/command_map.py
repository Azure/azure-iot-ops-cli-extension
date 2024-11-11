# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""
Load CLI commands
"""
from azure.cli.core.commands import CliCommandType

schema_resource_ops = CliCommandType(operations_tmpl="azext_edge.edge.commands_schema#{}")
mq_resource_ops = CliCommandType(operations_tmpl="azext_edge.edge.commands_mq#{}")
dataflow_resource_ops = CliCommandType(operations_tmpl="azext_edge.edge.commands_dataflow#{}")
edge_resource_ops = CliCommandType(operations_tmpl="azext_edge.edge.commands_edge#{}")
secretsync_resource_ops = CliCommandType(operations_tmpl="azext_edge.edge.commands_secretsync#{}")
asset_resource_ops = CliCommandType(operations_tmpl="azext_edge.edge.commands_assets#{}")
aep_resource_ops = CliCommandType(operations_tmpl="azext_edge.edge.commands_asset_endpoint_profiles#{}")
connector_resource_ops = CliCommandType(operations_tmpl="azext_edge.edge.commands_connector#{}")


def load_iotops_commands(self, _):
    """
    Load CLI commands
    """
    with self.command_group(
        "iot ops",
        command_type=edge_resource_ops,
    ) as cmd_group:
        cmd_group.command("check", "check", is_preview=True)
        cmd_group.command("init", "init")
        cmd_group.command("upgrade", "upgrade", deprecate_info=cmd_group.deprecate(hide=True))
        cmd_group.command("create", "create_instance")
        cmd_group.command("update", "update_instance")
        cmd_group.show_command("show", "show_instance")
        cmd_group.command("list", "list_instances")
        cmd_group.command("delete", "delete")

    with self.command_group(
        "iot ops identity",
        command_type=edge_resource_ops,
    ) as cmd_group:
        cmd_group.command("assign", "instance_identity_assign")
        cmd_group.command("remove", "instance_identity_remove")
        cmd_group.show_command("show", "instance_identity_show")

    with self.command_group(
        "iot ops secretsync",
        command_type=secretsync_resource_ops,
        is_preview=True,
    ) as cmd_group:
        cmd_group.command("enable", "secretsync_enable")
        cmd_group.command("disable", "secretsync_disable")
        cmd_group.show_command("list", "secretsync_list")

    with self.command_group(
        "iot ops support",
        command_type=edge_resource_ops,
        is_preview=True,
    ) as cmd_group:
        cmd_group.command("create-bundle", "support_bundle")

    with self.command_group(
        "iot ops broker",
        command_type=mq_resource_ops,
    ) as cmd_group:
        cmd_group.show_command("show", "show_broker")
        cmd_group.command("list", "list_brokers")
        cmd_group.command("delete", "delete_broker")

    with self.command_group(
        "iot ops broker listener",
        command_type=mq_resource_ops,
    ) as cmd_group:
        cmd_group.show_command("show", "show_broker_listener")
        cmd_group.command("list", "list_broker_listeners")
        cmd_group.command("delete", "delete_broker_listener")

    with self.command_group(
        "iot ops broker authn",
        command_type=mq_resource_ops,
    ) as cmd_group:
        cmd_group.show_command("show", "show_broker_authn")
        cmd_group.command("list", "list_broker_authns")
        cmd_group.command("delete", "delete_broker_authn")

    with self.command_group(
        "iot ops broker authz",
        command_type=mq_resource_ops,
    ) as cmd_group:
        cmd_group.show_command("show", "show_broker_authz")
        cmd_group.command("list", "list_broker_authzs")
        cmd_group.command("delete", "delete_broker_authz")

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
        "iot ops asset dataset",
        command_type=asset_resource_ops,
    ) as cmd_group:
        cmd_group.command("list", "list_asset_datasets")
        cmd_group.show_command("show", "show_asset_dataset")

    with self.command_group(
        "iot ops asset dataset point",
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
        cmd_group.command("delete", "delete_asset_endpoint_profile")
        cmd_group.command("query", "query_asset_endpoint_profiles")
        cmd_group.show_command("show", "show_asset_endpoint_profile")
        cmd_group.command("update", "update_asset_endpoint_profile")

    with self.command_group(
        "iot ops asset endpoint create",
        command_type=aep_resource_ops,
    ) as cmd_group:
        cmd_group.command("opcua", "create_opcua_asset_endpoint_profile")

    with self.command_group(
        "iot ops schema",
        command_type=schema_resource_ops,
        is_preview=True,
    ) as cmd_group:
        cmd_group.command("create", "create_schema")
        cmd_group.show_command("show", "show_schema")
        cmd_group.command("list", "list_schemas")
        cmd_group.command("show-dataflow-refs", "list_schema_versions_dataflow_format", is_experimental=True)
        cmd_group.command("delete", "delete_schema")

    with self.command_group(
        "iot ops schema registry",
        command_type=schema_resource_ops,
    ) as cmd_group:
        cmd_group.command("create", "create_registry")
        cmd_group.show_command("show", "show_registry")
        cmd_group.command("list", "list_registries")
        cmd_group.command("delete", "delete_registry")

    with self.command_group(
        "iot ops schema version",
        command_type=schema_resource_ops,
    ) as cmd_group:
        cmd_group.command("add", "add_version")
        cmd_group.show_command("show", "show_version")
        cmd_group.command("list", "list_versions")
        cmd_group.command("remove", "remove_version")

    with self.command_group(
        "iot ops connector",
        command_type=connector_resource_ops,
        is_preview=True,
    ) as cmd_group:
        pass

    with self.command_group(
        "iot ops connector opcua trust",
        command_type=connector_resource_ops,
        is_preview=True,
    ) as cmd_group:
        cmd_group.command("add", "add_connector_opcua_trust")
        cmd_group.command("remove", "remove_connector_opcua_trust")
        cmd_group.show_command("show", "show_connector_opcua_trust")

    with self.command_group(
        "iot ops connector opcua issuer",
        command_type=connector_resource_ops,
        is_preview=True,
    ) as cmd_group:
        cmd_group.command("add", "add_connector_opcua_issuer")
        cmd_group.command("remove", "remove_connector_opcua_issuer")
        cmd_group.show_command("show", "show_connector_opcua_issuer")

    with self.command_group(
        "iot ops connector opcua client",
        command_type=connector_resource_ops,
        is_preview=True,
    ) as cmd_group:
        cmd_group.command("add", "add_connector_opcua_client")
        cmd_group.command("remove", "remove_connector_opcua_client")
        cmd_group.show_command("show", "show_connector_opcua_client")
