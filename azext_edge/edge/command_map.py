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
namespace_resource_ops = CliCommandType(operations_tmpl="azext_edge.edge.commands_namespaces#{}")
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
        cmd_group.command("create", "create_instance")
        cmd_group.command("upgrade", "upgrade_instance")
        cmd_group.command("update", "update_instance")
        cmd_group.show_command("show", "show_instance")
        cmd_group.command("list", "list_instances")
        cmd_group.command("delete", "delete")
        cmd_group.command("clone", "clone_instance", is_preview=True)

    with self.command_group(
        "iot ops rsync",
        command_type=edge_resource_ops,
        is_preview=True,
    ) as cmd_group:
        cmd_group.command("enable", "enable_rsync")
        cmd_group.command("disable", "disable_rsync")
        cmd_group.command("list", "list_rsync")

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
        cmd_group.command("delete", "delete_broker", deprecate_info=cmd_group.deprecate(hide=True))

    with self.command_group(
        "iot ops broker listener",
        command_type=mq_resource_ops,
    ) as cmd_group:
        cmd_group.command("apply", "apply_broker_listener")
        cmd_group.show_command("show", "show_broker_listener")
        cmd_group.command("list", "list_broker_listeners")
        cmd_group.command("delete", "delete_broker_listener")

    with self.command_group(
        "iot ops broker listener port",
        command_type=mq_resource_ops,
    ) as cmd_group:
        cmd_group.command("add", "add_broker_listener_port")
        cmd_group.command("remove", "remove_broker_listener_port")

    with self.command_group(
        "iot ops broker authn",
        command_type=mq_resource_ops,
    ) as cmd_group:
        cmd_group.command("apply", "apply_broker_authn")
        cmd_group.show_command("show", "show_broker_authn")
        cmd_group.command("list", "list_broker_authns")
        cmd_group.command("delete", "delete_broker_authn")

    with self.command_group(
        "iot ops broker authn method",
        command_type=mq_resource_ops,
    ) as cmd_group:
        cmd_group.command("add", "add_broker_authn_method")

    with self.command_group(
        "iot ops broker authz",
        command_type=mq_resource_ops,
    ) as cmd_group:
        cmd_group.command("apply", "apply_broker_authz")
        cmd_group.show_command("show", "show_broker_authz")
        cmd_group.command("list", "list_broker_authzs")
        cmd_group.command("delete", "delete_broker_authz")

    with self.command_group(
        "iot ops dataflow",
        command_type=dataflow_resource_ops,
    ) as cmd_group:
        cmd_group.show_command("show", "show_dataflow")
        cmd_group.command("list", "list_dataflows")
        cmd_group.command("apply", "apply_dataflow")
        cmd_group.command("delete", "delete_dataflow")

    with self.command_group(
        "iot ops dataflow profile",
        command_type=dataflow_resource_ops,
    ) as cmd_group:
        cmd_group.show_command("show", "show_dataflow_profile")
        cmd_group.command("list", "list_dataflow_profiles")
        cmd_group.command("create", "create_dataflow_profile")
        cmd_group.command("update", "update_dataflow_profile")
        cmd_group.command("delete", "delete_dataflow_profile")

    with self.command_group(
        "iot ops dataflow endpoint",
        command_type=dataflow_resource_ops,
    ) as cmd_group:
        cmd_group.command("delete", "delete_dataflow_endpoint")
        cmd_group.command("apply", "apply_dataflow_endpoint")
        cmd_group.show_command("show", "show_dataflow_endpoint")
        cmd_group.command("list", "list_dataflow_endpoints")

    with self.command_group(
        "iot ops dataflow endpoint create",
        command_type=dataflow_resource_ops,
    ) as cmd_group:
        cmd_group.command("adx", "create_dataflow_endpoint_adx")
        cmd_group.command("adls", "create_dataflow_endpoint_adls")
        cmd_group.command("fabric-onelake", "create_dataflow_endpoint_fabric_onelake")
        cmd_group.command("eventhub", "create_dataflow_endpoint_eventhub")
        cmd_group.command("fabric-realtime", "create_dataflow_endpoint_fabric_realtime")
        cmd_group.command("custom-kafka", "create_dataflow_endpoint_custom_kafka")
        cmd_group.command("local-storage", "create_dataflow_endpoint_localstorage")
        cmd_group.command("local-mqtt", "create_dataflow_endpoint_aio")
        cmd_group.command("eventgrid", "create_dataflow_endpoint_eventgrid")
        cmd_group.command("custom-mqtt", "create_dataflow_endpoint_custom_mqtt")

    with self.command_group(
        "iot ops dataflow endpoint update",
        command_type=dataflow_resource_ops,
    ) as cmd_group:
        cmd_group.command("adx", "update_dataflow_endpoint_adx")
        cmd_group.command("adls", "update_dataflow_endpoint_adls")
        cmd_group.command("fabric-onelake", "update_dataflow_endpoint_fabric_onelake")
        cmd_group.command("eventhub", "update_dataflow_endpoint_eventhub")
        cmd_group.command("fabric-realtime", "update_dataflow_endpoint_fabric_realtime")
        cmd_group.command("custom-kafka", "update_dataflow_endpoint_custom_kafka")
        cmd_group.command("local-storage", "update_dataflow_endpoint_localstorage")
        cmd_group.command("local-mqtt", "update_dataflow_endpoint_aio")
        cmd_group.command("eventgrid", "update_dataflow_endpoint_eventgrid")
        cmd_group.command("custom-mqtt", "update_dataflow_endpoint_custom_mqtt")

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
        cmd_group.command(
            "custom", "create_custom_asset_endpoint_profile", deprecate_info=cmd_group.deprecate(hide=True)
        )
        cmd_group.command(
            "onvif", "create_onvif_asset_endpoint_profile", deprecate_info=cmd_group.deprecate(hide=True)
        )
        cmd_group.command("opcua", "create_opcua_asset_endpoint_profile")

    with self.command_group(
        "iot ops ns",
        command_type=namespace_resource_ops,
        is_preview=True,
    ) as cmd_group:
        cmd_group.command("create", "create_namespace")
        cmd_group.command("delete", "delete_namespace")
        cmd_group.command("list", "list_namespaces")
        cmd_group.show_command("show", "show_namespace")
        cmd_group.command("update", "update_namespace")

    with self.command_group(
        "iot ops ns device",
        command_type=namespace_resource_ops,
    ) as cmd_group:
        cmd_group.command("create", "create_namespace_device")
        cmd_group.command("delete", "delete_namespace_device")
        cmd_group.command("list", "list_namespace_devices")
        cmd_group.show_command("show", "show_namespace_device")
        cmd_group.command("update", "update_namespace_device")

    with self.command_group(
        "iot ops ns device endpoint",
        command_type=namespace_resource_ops,
    ) as cmd_group:
        cmd_group.command("list", "list_namespace_device_endpoints")

    with self.command_group(
        "iot ops ns device endpoint inbound",
        command_type=namespace_resource_ops,
    ) as cmd_group:
        cmd_group.command("list", "list_inbound_device_endpoints")
        cmd_group.command("remove", "remove_inbound_device_endpoints")

    with self.command_group(
        "iot ops ns device endpoint inbound add",
        command_type=namespace_resource_ops,
    ) as cmd_group:
        cmd_group.command("custom", "add_inbound_custom_device_endpoint")
        cmd_group.command("media", "add_inbound_media_device_endpoint")
        cmd_group.command("onvif", "add_inbound_onvif_device_endpoint")
        cmd_group.command("opcua", "add_inbound_opcua_device_endpoint")

    with self.command_group(
        "iot ops ns asset",
        command_type=namespace_resource_ops,
    ) as cmd_group:
        cmd_group.command("delete", "delete_namespace_asset")
        cmd_group.command("query", "query_namespace_assets")
        cmd_group.show_command("show", "show_namespace_asset")

    with self.command_group(
        "iot ops ns asset custom",
        command_type=namespace_resource_ops,
    ) as cmd_group:
        cmd_group.command("create", "create_namespace_custom_asset")
        cmd_group.command("update", "update_namespace_custom_asset")

    with self.command_group(
        "iot ops ns asset custom dataset",
        command_type=namespace_resource_ops,
    ) as cmd_group:
        cmd_group.command("add", "add_namespace_custom_asset_dataset")
        cmd_group.command("list", "list_namespace_asset_datasets")
        cmd_group.command("remove", "remove_namespace_asset_dataset")
        cmd_group.command("show", "show_namespace_asset_dataset")
        cmd_group.command("update", "update_namespace_custom_asset_dataset")

    with self.command_group(
        "iot ops ns asset custom dataset point",
        command_type=namespace_resource_ops,
    ) as cmd_group:
        cmd_group.command("add", "add_namespace_custom_asset_dataset_point")
        cmd_group.command("list", "list_namespace_asset_dataset_points")
        cmd_group.command("remove", "remove_namespace_asset_dataset_point")

    with self.command_group(
        "iot ops ns asset custom event",
        command_type=namespace_resource_ops,
    ) as cmd_group:
        cmd_group.command("add", "add_namespace_custom_asset_event")
        cmd_group.command("list", "list_namespace_asset_events")
        cmd_group.command("remove", "remove_namespace_asset_event")
        cmd_group.command("show", "show_namespace_asset_event")
        cmd_group.command("update", "update_namespace_custom_asset_event")

    with self.command_group(
        "iot ops ns asset custom event point",
        command_type=namespace_resource_ops,
    ) as cmd_group:
        cmd_group.command("add", "add_namespace_custom_asset_event_point")
        cmd_group.command("list", "list_namespace_asset_event_points")
        cmd_group.command("remove", "remove_namespace_asset_event_point")

    with self.command_group(
        "iot ops ns asset media",
        command_type=namespace_resource_ops,
    ) as cmd_group:
        cmd_group.command("create", "create_namespace_media_asset")
        cmd_group.command("update", "update_namespace_media_asset")

    with self.command_group(
        "iot ops ns asset onvif",
        command_type=namespace_resource_ops,
    ) as cmd_group:
        cmd_group.command("create", "create_namespace_onvif_asset")
        cmd_group.command("update", "update_namespace_onvif_asset")

    with self.command_group(
        "iot ops ns asset onvif event",
        command_type=namespace_resource_ops,
    ) as cmd_group:
        cmd_group.command("add", "add_namespace_onvif_asset_event")
        cmd_group.command("list", "list_namespace_asset_events")
        cmd_group.command("remove", "remove_namespace_asset_event")
        cmd_group.command("show", "show_namespace_asset_event")
        cmd_group.command("update", "update_namespace_onvif_asset_event")

    with self.command_group(
        "iot ops ns asset opcua",
        command_type=namespace_resource_ops,
    ) as cmd_group:
        cmd_group.command("create", "create_namespace_opcua_asset")
        cmd_group.command("update", "update_namespace_opcua_asset")

    with self.command_group(
        "iot ops ns asset opcua dataset",
        command_type=namespace_resource_ops,
    ) as cmd_group:
        cmd_group.command("add", "add_namespace_opcua_asset_dataset")
        cmd_group.command("list", "list_namespace_asset_datasets")
        cmd_group.command("remove", "remove_namespace_asset_dataset")
        cmd_group.command("show", "show_namespace_asset_dataset")
        cmd_group.command("update", "update_namespace_opcua_asset_dataset")

    with self.command_group(
        "iot ops ns asset opcua dataset point",
        command_type=namespace_resource_ops,
    ) as cmd_group:
        cmd_group.command("add", "add_namespace_opcua_asset_dataset_point")
        cmd_group.command("list", "list_namespace_asset_dataset_points")
        cmd_group.command("remove", "remove_namespace_asset_dataset_point")

    with self.command_group(
        "iot ops ns asset opcua event",
        command_type=namespace_resource_ops,
    ) as cmd_group:
        cmd_group.command("add", "add_namespace_opcua_asset_event")
        cmd_group.command("list", "list_namespace_asset_events")
        cmd_group.command("remove", "remove_namespace_asset_event")
        cmd_group.command("show", "show_namespace_asset_event")
        cmd_group.command("update", "update_namespace_opcua_asset_event")

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
    ) as cmd_group:
        cmd_group.command("add", "add_connector_opcua_trust")
        cmd_group.command("remove", "remove_connector_opcua_trust")
        cmd_group.show_command("show", "show_connector_opcua_trust")

    with self.command_group(
        "iot ops connector opcua issuer",
        command_type=connector_resource_ops,
    ) as cmd_group:
        cmd_group.command("add", "add_connector_opcua_issuer")
        cmd_group.command("remove", "remove_connector_opcua_issuer")
        cmd_group.show_command("show", "show_connector_opcua_issuer")

    with self.command_group(
        "iot ops connector opcua client",
        command_type=connector_resource_ops,
    ) as cmd_group:
        cmd_group.command("add", "add_connector_opcua_client")
        cmd_group.command("remove", "remove_connector_opcua_client")
        cmd_group.show_command("show", "show_connector_opcua_client")
