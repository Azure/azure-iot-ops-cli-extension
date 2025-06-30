# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from azure.cli.core.commands.parameters import (
    get_enum_type,
    get_three_state_flag,
    tags_type,
)
from ....common import (
    ADRAuthModes,
    FileType,
    TopicRetain,
)
from .specs import MediaFormat, MediaTaskType, SecurityPolicy, SecurityMode


def load_adr_arguments(self, _):
    """
    Load ADR (Asset + Asset Endpoint Profile) CLI Args for Knack parser
    """

    with self.argument_context("iot ops asset") as context:
        context.argument(
            "asset_name",
            options_list=["--name", "-n"],
            help="Asset name.",
        )
        context.argument(
            "endpoint_profile",
            options_list=["--endpoint-profile", "--ep"],
            help="Asset endpoint profile name.",
        )
        context.argument(
            "instance_name", options_list=["--instance"], help="Instance name to associate the created asset with."
        )
        context.argument(
            "instance_resource_group",
            options_list=["--instance-resource-group", "--ig"],
            help="Instance resource group. If not provided, asset resource group will be used.",
        )
        context.argument(
            "instance_subscription",
            options_list=["--instance-subscription", "--is"],
            help="Instance subscription id. If not provided, asset subscription id will be used.",
            deprecate_info=context.deprecate(hide=True),
        )
        context.argument(
            "custom_attributes",
            options_list=["--custom-attribute", "--attr"],
            help="Space-separated key=value pairs corresponding to additional custom attributes for the asset. "
            "This parameter can be used more than once.",
            nargs="+",
            arg_group="Additional Info",
            action="extend",
        )
        context.argument(
            "data_points",
            options_list=["--data"],
            nargs="+",
            action="append",
            help="Space-separated key=value pairs corresponding to properties of the data-point to create. "
            "The following key values are supported: `data_source` (required), `name` (required), "
            "`observability_mode` (None, Gauge, Counter, Histogram, or Log), `sampling_interval` (int), "
            "`queue_size` (int). "
            "--data can be used 1 or more times. Review help examples for full parameter usage",
            arg_group="Data-point",
        )
        context.argument(
            "data_points_file_path",
            options_list=["--data-file", "--df"],
            help="File path for the file containing the data-points. The following file types are supported: "
            f"{', '.join(FileType.list())}.",
            arg_group="Data-point",
        )
        context.argument(
            "description",
            options_list=["--description", "-d"],
            help="Description.",
        )
        context.argument(
            "display_name",
            options_list=["--display-name", "--dn"],
            help="Display name.",
        )
        context.argument(
            "disabled",
            options_list=["--disable"],
            help="Disable an asset.",
            arg_type=get_three_state_flag(),
        )
        context.argument(
            "documentation_uri",
            options_list=["--documentation-uri", "--du"],
            help="Documentation URI.",
            arg_group="Additional Info",
        )
        context.argument(
            "events",
            options_list=["--event"],
            nargs="+",
            action="append",
            help="Space-separated key=value pairs corresponding to properties of the event to create. "
            "The following key values are supported: `event_notifier` (required), "
            "`name` (required), `observability_mode` (none or log), `sampling_interval` "
            "(int), `queue_size` (int). "
            "--event can be used 1 or more times. Review help examples for full parameter usage",
            arg_group="Event",
        )
        context.argument(
            "events_file_path",
            options_list=["--event-file", "--ef"],
            help="File path for the file containing the events. The following file types are supported: "
            f"{', '.join(FileType.list())}.",
            arg_group="Event",
        )
        context.argument(
            "external_asset_id",
            options_list=["--external-asset-id", "--eai"],
            help="External asset Id.",
            arg_group="Additional Info",
        )
        context.argument(
            "hardware_revision",
            options_list=["--hardware-revision", "--hr"],
            help="Hardware revision.",
            arg_group="Additional Info",
        )
        context.argument(
            "manufacturer",
            options_list=["--manufacturer"],
            help="Manufacturer.",
            arg_group="Additional Info",
        )
        context.argument(
            "manufacturer_uri",
            options_list=["--manufacturer-uri", "--mu"],
            help="Manufacturer URI.",
            arg_group="Additional Info",
        )
        context.argument(
            "model",
            options_list=["--model"],
            help="Model.",
            arg_group="Additional Info",
        )
        context.argument(
            "product_code",
            options_list=["--product-code", "--pc"],
            help="Product code.",
            arg_group="Additional Info",
        )
        context.argument(
            "serial_number",
            options_list=["--serial-number", "--sn"],
            help="Serial number.",
            arg_group="Additional Info",
        )
        context.argument(
            "software_revision",
            options_list=["--software-revision", "--sr"],
            help="Software revision.",
            arg_group="Additional Info",
        )
        context.argument(
            "ds_publishing_interval",
            options_list=["--dataset-publish-int", "--dpi"],
            help="Default publishing interval for datasets.",
            arg_group="Dataset Default",
        )
        context.argument(
            "ds_sampling_interval",
            options_list=["--dataset-sample-int", "--dsi"],
            help="Default sampling interval (in milliseconds) for datasets.",
            arg_group="Dataset Default",
        )
        context.argument(
            "ds_queue_size",
            options_list=["--dataset-queue-size", "--dqs"],
            help="Default queue size for datasets.",
            arg_group="Dataset Default",
        )
        context.argument(
            "ev_publishing_interval",
            options_list=["--event-publish-int", "--epi"],
            help="Default publishing interval for events.",
            arg_group="Event Default",
        )
        context.argument(
            "ev_sampling_interval",
            options_list=["--event-sample-int", "--esi"],
            help="Default sampling interval (in milliseconds) for events.",
            arg_group="Event Default",
        )
        context.argument(
            "ev_queue_size",
            options_list=["--event-queue-size", "--eqs"],
            help="Default queue size for events.",
            arg_group="Event Default",
        )
        context.argument(
            "default_topic_path",
            options_list=["--topic-path", "--tp"],
            help="Default topic path.",
            arg_group="MQTT Topic Default",
        )
        context.argument(
            "default_topic_retain",
            options_list=["--topic-retain", "--tr"],
            help="Default topic retain policy.",
            arg_group="MQTT Topic Default",
            arg_type=get_enum_type(TopicRetain),
        )
        context.argument(
            "tags",
            options_list=["--tags"],
            help="Asset resource tags. Property bag in key-value pairs with the following format: a=b c=d",
            arg_type=tags_type,
        )
        context.argument(
            "queue_size",
            options_list=["--queue-size", "--qs"],
            help="Custom queue size.",
        )
        context.argument(
            "publishing_interval",
            options_list=["--publishing-interval", "--pi"],
            help="Custom publishing interval (in milliseconds).",
        )
        context.argument(
            "sampling_interval",
            options_list=["--sampling-interval", "--si"],
            help="Custom sampling interval (in milliseconds).",
        )
        context.argument(
            "extension",
            options_list=["--format", "-f"],
            help="File format.",
            choices=FileType.list(),
            arg_type=get_enum_type(FileType),
        )
        context.argument(
            "output_dir",
            options_list=["--output-dir", "--od"],
            help="Output directory for exported file.",
        )
        context.argument(
            "custom_query",
            options_list=["--custom-query", "--cq"],
            help="Custom query to use. All other query arguments will be ignored.",
        )

    with self.argument_context("iot ops asset query") as context:
        context.argument(
            "disabled",
            options_list=["--disabled"],
            help="State of asset.",
            arg_group="Additional Info",
            arg_type=get_three_state_flag(),
        )

    with self.argument_context("iot ops asset update") as context:
        context.argument(
            "custom_attributes",
            options_list=["--custom-attribute", "--attr"],
            help="Space-separated key=value pairs corresponding to additional custom attributes for the asset. "
            "This parameter can be used more than once."
            'To remove a custom attribute, please set the attribute\'s value to "".',
            nargs="+",
            arg_group="Additional Info",
            action="extend",
        )

    with self.argument_context("iot ops asset dataset") as context:
        context.argument(
            "asset_name",
            options_list=["--asset", "-a"],
            help="Asset name.",
        )
        context.argument(
            "dataset_name",
            options_list=["--name", "-n"],
            help="Dataset name.",
        )

    with self.argument_context("iot ops asset dataset point") as context:
        context.argument(
            "capability_id",
            options_list=["--capability-id", "--ci"],
            help="Capability Id. If not provided, data-point name will be used.",
        )
        context.argument(
            "dataset_name",
            options_list=["--dataset", "-d"],
            help="Dataset name.",
        )
        context.argument(
            "data_point_name",
            options_list=["--name", "-n"],
            help="Data point name.",
        )
        context.argument(
            "data_source",
            options_list=["--data-source", "--ds"],
            help="Data source.",
        )
        context.argument(
            "observability_mode",
            options_list=["--observability-mode", "--om"],
            help="Observability mode. Must be none, gauge, counter, histogram, or log.",
        )

    with self.argument_context("iot ops asset dataset point add") as context:
        context.argument(
            "replace",
            options_list=["--replace"],
            help="Replace the data-point if another data-point with the same name is present already.",
            arg_type=get_three_state_flag(),
        )

    with self.argument_context("iot ops asset dataset point export") as context:
        context.argument(
            "replace",
            options_list=["--replace"],
            help="Replace the local file if present.",
            arg_type=get_three_state_flag(),
        )

    with self.argument_context("iot ops asset dataset point import") as context:
        context.argument(
            "replace",
            options_list=["--replace"],
            help="Replace duplicate asset data-points with those from the file. If false, the file data-points "
            "will be ignored. Duplicate asset data-points will be determined by name.",
            arg_type=get_three_state_flag(),
        )
        context.argument(
            "file_path",
            options_list=["--input-file", "--if"],
            help="File path for the file containing the data-points. The following file types are supported: "
            f"{', '.join(FileType.list())}.",
        )

    with self.argument_context("iot ops asset event") as context:
        context.argument(
            "asset_name",
            options_list=["--asset", "-a"],
            help="Asset name.",
        )
        context.argument(
            "capability_id",
            options_list=["--capability-id", "--ci"],
            help="Capability Id. If not provided, event name will be used.",
        )
        context.argument(
            "event_name",
            options_list=["--name", "-n"],
            help="Event name.",
        )
        context.argument(
            "event_notifier",
            options_list=["--event-notifier", "--en"],
            help="Event notifier.",
        )
        context.argument(
            "observability_mode",
            options_list=["--observability-mode", "--om"],
            help="Observability mode. Must be none or log.",
        )

    with self.argument_context("iot ops asset event add") as context:
        context.argument(
            "replace",
            options_list=["--replace"],
            help="Replace the event if another event with the same name is already present.",
            arg_type=get_three_state_flag(),
        )

    with self.argument_context("iot ops asset event export") as context:
        context.argument(
            "replace",
            options_list=["--replace"],
            help="Replace the local file if present.",
            arg_type=get_three_state_flag(),
        )

    with self.argument_context("iot ops asset event import") as context:
        context.argument(
            "replace",
            options_list=["--replace"],
            help="Replace duplicate asset events with those from the file. If false, the file events "
            "will be ignored. Duplicate asset events will be determined by name.",
            arg_type=get_three_state_flag(),
        )
        context.argument(
            "file_path",
            options_list=["--input-file", "--if"],
            help="File path for the file containing the events. The following file types are supported: "
            f"{', '.join(FileType.list())}.",
        )

    with self.argument_context("iot ops asset endpoint") as context:
        context.argument(
            "asset_endpoint_profile_name",
            options_list=["--name", "-n"],
            help="Asset Endpoint Profile name.",
        )
        context.argument(
            "instance_resource_group",
            options_list=["--instance-resource-group", "--ig"],
            help="Instance resource group. If not provided, asset endpoint profile resource group will be used.",
        )
        context.argument(
            "instance_subscription",
            options_list=["--instance-subscription", "--is"],
            help="Instance subscription id. If not provided, asset endpoint profile subscription id will be used.",
            deprecate_info=context.deprecate(hide=True),
        )
        context.argument(
            "target_address",
            options_list=["--target-address", "--ta"],
            help="Target Address. Must be a valid local address that follows the opc.tcp protocol.",
        )
        context.argument(
            "endpoint_profile_type",
            options_list=["--endpoint-profile-type", "--ept"],
            help="Connector type for the endpoint profile.",
        )
        context.argument(
            "auth_mode",
            options_list=["--authentication-mode", "--am"],
            help="Authentication Mode.",
            arg_group="Authentication",
            arg_type=get_enum_type(ADRAuthModes),
        )
        context.argument(
            "certificate_reference",
            options_list=["--certificate-ref", "--cert-ref", context.deprecate(target="--cr", redirect="--cert-ref")],
            help="Reference for the certificate used in authentication. This method of user authentication is not "
            "supported yet.",
            arg_group="Authentication",
        )
        context.argument(
            "password_reference",
            options_list=["--password-ref", "--pass-ref", context.deprecate(target="--pr", redirect="--pass-ref")],
            help="Reference for the password used in authentication.",
            arg_group="Authentication",
        )
        context.argument(
            "username_reference",
            options_list=[
                context.deprecate(target="--username-reference", redirect="--user-ref"),
                "--username-ref",
                "--user-ref",
                context.deprecate(target="--ur", redirect="--user-ref")
            ],
            help="Reference for the username used in authentication.",
            arg_group="Authentication",
        )
        context.argument(
            "tags",
            options_list=["--tags"],
            help="Asset Endpoint Profile resource tags. Property bag in key-value pairs with the following "
            "format: a=b c=d",
            arg_type=tags_type,
        )

    with self.argument_context("iot ops asset endpoint create custom") as context:
        context.argument(
            "endpoint_profile_type",
            options_list=["--endpoint-type", "--et"],
            help="Endpoint Profile Type for the Connector.",
            arg_group="Connector",
        )
        context.argument(
            "additional_configuration",
            options_list=["--additional-config", "--ac"],
            help="File path containing or inline json for the additional configuration.",
            arg_group="Connector",
        )

    with self.argument_context("iot ops asset endpoint create opcua") as context:
        context.argument(
            "application_name",
            options_list=["--application", "--app"],
            help="Application name. Will be used as the subject for any certificates generated by the connector.",
            arg_group="Connector",
        )
        context.argument(
            "auto_accept_untrusted_server_certs",
            options_list=["--accept-untrusted-certs", "--auc"],
            help="Flag to enable auto accept untrusted server certificates.",
            arg_type=get_three_state_flag(),
            arg_group="Connector",
        )
        context.argument(
            "default_publishing_interval",
            options_list=["--default-publishing-int", "--dpi"],
            help="Default publishing interval in milliseconds. Minimum: -1. Recommended: 1000",
            type=int,
            arg_group="Connector",
        )
        context.argument(
            "default_sampling_interval",
            options_list=["--default-sampling-int", "--dsi"],
            help="Default sampling interval in milliseconds. Minimum: -1. Recommended: 1000.",
            type=int,
            arg_group="Connector",
        )
        context.argument(
            "default_queue_size",
            options_list=["--default-queue-size", "--dqs"],
            help="Default queue size. Minimum: 0. Recommended: 1.",
            type=int,
            arg_group="Connector",
        )
        context.argument(
            "keep_alive",
            options_list=["--keep-alive", "--ka"],
            help="Time in milliseconds after which a keep alive publish response is sent. Minimum: 0. "
            "Recommended: 10000.",
            type=int,
            arg_group="Connector",
        )
        context.argument(
            "run_asset_discovery",
            options_list=["--run-asset-discovery", "--rad"],
            help="Flag to determine if asset discovery should be run.",
            arg_type=get_three_state_flag(),
            arg_group="Connector",
        )
        context.argument(
            "session_timeout",
            options_list=["--session-timeout", "--st"],
            help="Session timeout in milliseconds. Minimum: 0. Recommended: 60000.",
            type=int,
            arg_group="Connector",
        )
        context.argument(
            "session_keep_alive",
            options_list=["--session-keep-alive", "--ska"],
            help="Time in milliseconds after which a session keep alive challenge is sent to detect "
            "connection issues. Minimum: 0. Recommended: 10000.",
            type=int,
            arg_group="Connector",
        )
        context.argument(
            "session_reconnect_period",
            options_list=["--session-reconnect-period", "--srp"],
            help="Session reconnect period in milliseconds. Minimum: 0. Recommended: 2000.",
            type=int,
            arg_group="Connector",
        )
        context.argument(
            "session_reconnect_exponential_back_off",
            options_list=["--session-reconnect-backoff", "--srb"],
            help="Session reconnect exponential back off in milliseconds. Minimum: -1. Recommended: 10000.",
            type=int,
            arg_group="Connector",
        )
        context.argument(
            "security_policy",
            options_list=["--security-policy", "--sp"],
            help="Security policy.",
            arg_group="Connector",
            arg_type=get_enum_type(SecurityPolicy),
        )
        context.argument(
            "security_mode",
            options_list=["--security-mode", "--sm"],
            help="Security mode.",
            arg_group="Connector",
            arg_type=get_enum_type(SecurityMode),
        )
        context.argument(
            "sub_max_items",
            options_list=["--subscription-max-items", "--smi"],
            help="Maximum number of items that the connector can create for the subscription. "
            "Minimum: 1. Recommended: 1000.",
            type=int,
            arg_group="Connector",
        )
        context.argument(
            "sub_life_time",
            options_list=["--subscription-life-time", "--slt"],
            help="Life time in milliseconds of the items created by the connector for the subscription. "
            "Minimum: 0. Recommended: 60000.",
            type=int,
            arg_group="Connector",
        )
        context.argument(
            "certificate_reference",
            options_list=["--certificate-ref", "--cert-ref", "--cr", "--cert-ref"],
            help="Reference for the certificate used in authentication. This method of user authentication is not "
            "supported yet.",
            arg_group="Authentication",
            deprecate_info=context.deprecate(hide=True)
        )

    # ADR REFRESH
    with self.argument_context("iot ops ns") as context:
        context.argument(
            "namespace_name",
            options_list=["--name", "-n"],
            help="Namespace name.",
        )
        context.argument(
            "mi_system_identity",
            options_list=["--mi-system-assigned"],
            help="Enable system-assigned managed identity for the namespace.",
            arg_type=get_three_state_flag(),
        )

    with self.argument_context("iot ops ns endpoint") as context:
        context.argument(
            "namespace_name",
            options_list=["--namespace", "--ns"],
            help="Namespace name.",
        )

    with self.argument_context("iot ops ns device") as context:
        context.argument(
            "namespace_name",
            options_list=["--namespace", "--ns"],
            help="Namespace name.",
        )
        context.argument(
            "device_name",
            options_list=["--name", "-n"],
            help="The name of the device to create.",
        )
        context.argument(
            "custom_attributes",
            options_list=["--custom-attribute", "--attr"],
            help="Space-separated key=value pairs corresponding to additional custom attributes for the device. "
                 "This parameter can be used more than once.",
            nargs="+",
            action="extend",
        )
        context.argument(
            "device_group_id",
            options_list=["--device-group-id", "--group-id"],
            help="The device group ID for the device.",
        )
        context.argument(
            "disabled",
            options_list=["--disabled"],
            help="Disable the device. By default, no change will be made to the device's enabled/disabled state.",
            arg_type=get_three_state_flag(),
        )
        context.argument(
            "operating_system_version",
            options_list=["--os-version"],
            help="The device operating system version.",
        )
        context.argument(
            "tags",
            options_list=["--tags"],
            help="Space-separated tags in 'key[=value]' format. Use '' to clear existing tags.",
            arg_type=tags_type,
        )

    with self.argument_context("iot ops ns device create") as context:
        context.argument(
            "instance_name",
            options_list=["--instance", "--inst"],
            help="The name of the Azure IoT Operations instance.",
        )
        context.argument(
            "device_template_id",
            options_list=["--template-id", "--tid"],
            help="The device template ID to use for the device.",
        )
        context.argument(
            "instance_resource_group",
            options_list=["--instance-resource-group", "--irg"],
            help="The resource group of the Azure IoT Operations instance. If not provided, the device "
            "resource group will be used.",
        )
        context.argument(
            "instance_subscription",
            options_list=["--instance-subscription", "--isub"],
            help="The subscription ID of the Azure IoT Operations instance. If not provided, the current "
            "subscription will be used.",
        )
        context.argument(
            "manufacturer",
            options_list=["--manufacturer"],
            help="The device manufacturer.",
        )
        context.argument(
            "model",
            options_list=["--model"],
            help="The device model.",
        )
        context.argument(
            "operating_system",
            options_list=["--os"],
            help="The device operating system.",
        )

    with self.argument_context("iot ops ns device endpoint") as context:
        context.argument(
            "device_name",
            options_list=["--device", "-d"],
            help="Device name.",
        )
        context.argument(
            "namespace_name",
            options_list=["--namespace", "--ns"],
            help="Namespace name.",
        )
        context.argument(
            "endpoint_name",
            options_list=["--name"],
            help="Endpoint name.",
        )
        context.argument(
            "endpoint_address",
            options_list=["--endpoint-address", "--address"],
            help="Endpoint address to connect to.",
        )
        context.argument(
            "certificate_reference",
            options_list=["--certificate-ref", "--cert-ref"],
            help="Reference for the certificate used in authentication.",
            arg_group="Authentication",
        )
        context.argument(
            "password_reference",
            options_list=["--password-ref", "--pass-ref"],
            help="Reference for the password used in authentication.",
            arg_group="Authentication",
        )
        context.argument(
            "username_reference",
            options_list=["--username-ref", "--user-ref"],
            help="Reference for the username used in authentication.",
            arg_group="Authentication",
        )
        context.argument(
            "trust_list",
            options_list=["--trust-list"],
            help="List of trusted certificates for the endpoint.",
        )

    with self.argument_context("iot ops ns device endpoint list") as context:
        context.argument(
            "inbound",
            options_list=["--inbound"],
            help="Flag to only list inbound endpoints.",
            arg_type=get_three_state_flag(),
        )

    with self.argument_context("iot ops ns device endpoint inbound remove") as context:
        context.argument(
            "endpoint_names",
            options_list=["--endpoint"],
            help="Space-separated list of endpoint names to remove from the device.",
            nargs="+",
            action="extend",
        )

    with self.argument_context("iot ops ns device endpoint inbound add custom") as context:
        context.argument(
            "endpoint_type",
            options_list=["--endpoint-type", "--type"],
            help="Type of the custom endpoint.",
        )
        context.argument(
            "additional_configuration",
            options_list=["--additional-config", "--config"],
            help="Additional configuration for the custom endpoint in JSON format.",
        )

    with self.argument_context("iot ops ns device endpoint inbound add onvif") as context:
        context.argument(
            "accept_invalid_hostnames",
            options_list=["--accept-invalid-hostnames", "--aih"],
            help="Accept invalid hostnames in certificates.",
            arg_type=get_three_state_flag(),
            arg_group="ONVIF Configuration",
        )
        context.argument(
            "accept_invalid_certificates",
            options_list=["--accept-invalid-certificates", "--aic"],
            help="Accept invalid certificates.",
            arg_type=get_three_state_flag(),
            arg_group="ONVIF Configuration",
        )

    with self.argument_context("iot ops ns device endpoint inbound add opcua") as context:
        context.argument(
            "application_name",
            options_list=["--application-name", "--app"],
            help="Application name for the OPC UA client.",
            arg_group="Configuration",
        )
        context.argument(
            "keep_alive",
            options_list=["--keep-alive"],
            help="Keep alive time in milliseconds.",
            type=int,
            arg_group="Configuration",
        )
        context.argument(
            "publishing_interval",
            options_list=["--publishing-interval", "--pi"],
            help="Publishing interval in milliseconds.",
            type=int,
            arg_group="Configuration",
        )
        context.argument(
            "sampling_interval",
            options_list=["--sampling-interval", "--si"],
            help="Sampling interval in milliseconds.",
            type=int,
            arg_group="Configuration",
        )
        context.argument(
            "queue_size",
            options_list=["--queue-size", "--qs"],
            help="Queue size.",
            type=int,
            arg_group="Configuration",
        )
        context.argument(
            "key_frame_count",
            options_list=["--key-frame-count", "--kfc"],
            help="Key frame count.",
            type=int,
            arg_group="Configuration",
        )
        context.argument(
            "session_timeout",
            options_list=["--session-timeout"],
            help="Session timeout in milliseconds.",
            type=int,
            arg_group="Session",
        )
        context.argument(
            "session_keep_alive_interval",
            options_list=["--session-keep-alive", "--ska"],
            help="Session keep alive interval in milliseconds.",
            type=int,
            arg_group="Session",
        )
        context.argument(
            "session_reconnect_period",
            options_list=["--session-reconnect", "--srp"],
            help="Session reconnect period in milliseconds.",
            type=int,
            arg_group="Session",
        )
        context.argument(
            "session_reconnect_exponential_backoff",
            options_list=["--session-backoff", "--sbo"],
            help="Session reconnect exponential backoff in milliseconds.",
            type=int,
            arg_group="Session",
        )
        context.argument(
            "session_enable_tracing_headers",
            options_list=["--session-tracing", "--str"],
            help="Enable tracing headers for the session.",
            arg_type=get_three_state_flag(),
            arg_group="Session",
        )
        context.argument(
            "subscription_max_items",
            options_list=["--subscription-max-items", "--smi"],
            help="Maximum number of items in subscription.",
            type=int,
            arg_group="Subscription",
        )
        context.argument(
            "subscription_life_time",
            options_list=["--subscription-lifetime", "--slt"],
            help="Subscription lifetime in milliseconds.",
            type=int,
            arg_group="Subscription",
        )
        context.argument(
            "security_auto_accept_certificates",
            options_list=["--accept-certs", "--ac"],
            help="Auto accept untrusted server certificates.",
            arg_type=get_three_state_flag(),
            arg_group="Security",
        )
        context.argument(
            "security_policy",
            options_list=["--security-policy", "--sp"],
            help="Security policy to use for the connection.",
            arg_type=get_enum_type(SecurityPolicy),  # should this be a caseinsensitivelist?
            arg_group="Security",
        )
        context.argument(
            "security_mode",
            options_list=["--security-mode", "--sm"],
            help="Security mode to use for the connection.",
            arg_type=get_enum_type(SecurityMode),  # should this be a caseinsensitivelist?
            arg_group="Security",
        )
        context.argument(
            "run_asset_discovery",
            options_list=["--run-asset-discovery", "--ad"],
            help="Enable asset discovery after connecting to the endpoint.",
            arg_type=get_three_state_flag(),
            arg_group="Configuration",
        )

    with self.argument_context("iot ops ns asset") as context:
        context.argument(
            "asset_name",
            options_list=["--name", "-n"],
            help="Name of the asset.",
        )
        context.argument(
            "device_name",
            options_list=["--device", "-d"],
            help="Device name.",
        )
        context.argument(
            "namespace_name",
            options_list=["--namespace", "--ns"],
            help="Namespace name.",
        )
        context.argument(
            "device_endpoint_name",
            options_list=["--endpoint-name", "--endpoint", "--ep"],
            help="Device endpoint name.",
        )
        context.argument(
            "asset_type_refs",
            options_list=["--asset-type-ref", "--type-ref"],
            help="Space-separated list of asset type references.",
            nargs="+",
            action="extend",
        )
        context.argument(
            "attributes",
            options_list=["--attribute", "--attr"],
            help="Space-separated key=value pairs for custom asset attributes.",
            nargs="+",
            action="extend",
            arg_group="Additional Info"
        )
        context.argument(
            "description",
            options_list=["--description"],
            help="Description of the asset.",
        )
        context.argument(
            "disabled",
            options_list=["--disable"],
            help="Disable the asset.",
            arg_type=get_three_state_flag(),
        )
        context.argument(
            "display_name",
            options_list=["--display-name", "--dn"],
            help="Display name for the asset.",
        )
        context.argument(
            "documentation_uri",
            options_list=["--documentation-uri", "--doc-uri"],
            help="Documentation URI for the asset.",
            arg_group="Additional Info"
        )
        context.argument(
            "external_asset_id",
            options_list=["--external-asset-id", "--eid"],
            help="External asset ID.",
            arg_group="Additional Info"
        )
        context.argument(
            "hardware_revision",
            options_list=["--hardware-revision", "--hw-rev"],
            help="Hardware revision information.",
            arg_group="Additional Info"
        )
        context.argument(
            "manufacturer",
            options_list=["--manufacturer"],
            help="Manufacturer name.",
            arg_group="Additional Info"
        )
        context.argument(
            "manufacturer_uri",
            options_list=["--manufacturer-uri", "--mfr-uri"],
            help="Manufacturer URI.",
            arg_group="Additional Info"
        )
        context.argument(
            "model",
            options_list=["--model"],
            help="Model name or number.",
            arg_group="Additional Info"
        )
        context.argument(
            "product_code",
            options_list=["--product-code", "--pc"],
            help="Product code.",
            arg_group="Additional Info"
        )
        context.argument(
            "serial_number",
            options_list=["--serial-number", "--sn"],
            help="Serial number.",
            arg_group="Additional Info"
        )
        context.argument(
            "software_revision",
            options_list=["--software-revision", "--sw-rev"],
            help="Software revision information.",
            arg_group="Additional Info"
        )
        context.argument(
            "tags",
            options_list=["--tags"],
            help="Space-separated tags in 'key[=value]' format.",
            arg_type=tags_type,
        )
        context.argument(
            "custom_query",
            options_list=["--custom-query", "--cq"],
            help="Custom query to use. All other query arguments will be ignored.",
        )

    for command in ("create", "update"):
        with self.argument_context(f"iot ops ns asset custom {command}") as context:
            context.argument(
                "datasets_custom_configuration",
                options_list=["--dataset-config", "--dsc"],
                help="File path containing or inline json containing custom configuration for datasets.",
                arg_group="Default Configuration",
            )
            context.argument(
                "datasets_destinations",
                options_list=["--dataset-dest", "--dsd"],
                help="Key=value pairs representing the destination for dataset. "
                "Allowed arguments include: `key` for BrokerStateStore; `path` for Storage; or "
                "`topic`, `retain`, `qos`, and `ttl` for MQTT.",
                nargs="+",
                arg_group="Default Destination",
            )
            context.argument(
                "events_custom_configuration",
                options_list=["--event-config", "--evc"],
                help="File path containing or inline json containing custom configuration for events.",
                arg_group="Default Configuration",
            )
            context.argument(
                "events_destinations",
                options_list=["--event-dest", "--evd"],
                help="Key=value pairs representing the destination for events. "
                "Allowed arguments include: `key` for BrokerStateStore; `path` for Storage; or "
                "`topic`, `retain`, `qos`, and `ttl` for MQTT.",
                nargs="+",
                arg_group="Default Destination",
            )
            context.argument(
                "mgmt_custom_configuration",
                options_list=["--mgmt-config", "--mgc"],
                help="File path containing or inline json containing custom configuration for management.",
                arg_group="Default Configuration",
            )
            context.argument(
                "streams_custom_configuration",
                options_list=["--stream-config", "--stc"],
                help="File path containing or inline json containing custom configuration for streams.",
                arg_group="Default Configuration",
            )
            context.argument(
                "streams_destinations",
                options_list=["--stream-dest", "--std"],
                help="Key=value pairs representing the destination for streams. "
                "Allowed arguments include: `key` for BrokerStateStore; `path` for Storage; or "
                "`topic`, `retain`, `qos`, and `ttl` for MQTT.",
                nargs="+",
                arg_group="Default Destination",
            )

        with self.argument_context(f"iot ops ns asset media {command}") as context:
            context.argument(
                "task_type",
                options_list=["--task-type"],
                help="Media task type.",
                arg_type=get_enum_type(MediaTaskType),
                arg_group="Default Stream Configuration",
            )
            context.argument(
                "task_format",
                options_list=["--task-format", "--format"],
                help="Media format. Only allowed for only " + (
                    ', '.join([
                        MediaTaskType.snapshot_to_mqtt.value,
                        MediaTaskType.snapshot_to_fs.value,
                        MediaTaskType.clip_to_fs.value
                    ])
                ) + ". For snapshots, only " + (
                    ', '.join([
                        mf.value for mf in MediaFormat if mf.allowed_for_snapshot
                    ])
                ) + " are allowed. For clips, only " + (
                    ', '.join([
                        mf.value for mf in MediaFormat if mf.allowed_for_clip
                    ])
                ) + " are allowed.",
                arg_type=get_enum_type(MediaFormat),  # should I remove this to clutter the param help less
                arg_group="Default Stream Configuration",
            )
            context.argument(
                "snapshots_per_second",
                options_list=["--snapshots-per-sec", "--sps"],
                help=f"Number of snapshots per second. Only allowed for only {MediaTaskType.snapshot_to_mqtt.value} "
                f"and {MediaTaskType.snapshot_to_fs.value}. Minimum: 0",
                type=float,
                arg_group="Default Stream Configuration",
            )
            context.argument(
                "path",
                options_list=["--path", "-p"],
                help="File system path for snapshots or clips. Only allowed for only "
                f"{MediaTaskType.snapshot_to_fs.value} and {MediaTaskType.clip_to_fs.value}.",
                arg_group="Default Stream Configuration",
            )
            context.argument(
                "duration",
                options_list=["--duration"],
                help=f"Duration of clip in seconds. Only allowed for only {MediaTaskType.clip_to_fs.value}. Minimum: 0",
                type=int,
                arg_group="Default Stream Configuration",
            )
            context.argument(
                "media_server_address",
                options_list=["--media-server-address", "--ms-addr"],
                help=f"Media server address for streaming. Only allowed for only {MediaTaskType.stream_to_rtsp.value} "
                f"and {MediaTaskType.stream_to_rtsps.value}.",
                arg_group="Default Stream Configuration",
            )
            context.argument(
                "media_server_path",
                options_list=["--media-server-path", "--ms-path"],
                help=f"Media server path for streaming. Only allowed for only {MediaTaskType.stream_to_rtsp.value} "
                f"and {MediaTaskType.stream_to_rtsps.value}.",
                arg_group="Default Stream Configuration",
            )
            context.argument(
                "media_server_port",
                options_list=["--media-server-port", "--ms-port"],
                help=f"Media server port for streaming. Only allowed for only {MediaTaskType.stream_to_rtsp.value} "
                f"and {MediaTaskType.stream_to_rtsps.value}. Minimum: 1",
                type=int,
                arg_group="Default Stream Configuration",
            )
            context.argument(
                "media_server_username",
                options_list=["--media-server-user", "--ms-user"],
                help=f"Media server username reference. Only allowed for only {MediaTaskType.stream_to_rtsp.value} "
                f"and {MediaTaskType.stream_to_rtsps.value}.",
                arg_group="Default Stream Configuration",
            )
            context.argument(
                "media_server_password",
                options_list=["--media-server-pass", "--ms-pass"],
                help=f"Media server password reference. Only allowed for only {MediaTaskType.stream_to_rtsp.value} "
                f"and {MediaTaskType.stream_to_rtsps.value}.",
                arg_group="Default Stream Configuration",
            )
            context.argument(
                "media_server_certificate",
                options_list=["--media-server-cert", "--ms-cert"],
                help="Media server certificate reference. Only allowed for only "
                f"{MediaTaskType.stream_to_rtsps.value}.",
                arg_group="Default Stream Configuration",
            )
            context.argument(
                "streams_destinations",
                options_list=["--stream-dest", "--std"],
                help="Key=value pairs representing the destination for streams. "
                "Allowed arguments include: `path` for Storage; or "
                "`topic`, `retain`, `qos`, and `ttl` for MQTT.",
                nargs="+",
                arg_group="Default Stream Destination",
            )

        with self.argument_context(f"iot ops ns asset opcua {command}") as context:
            context.argument(
                "dataset_publishing_interval",
                options_list=["--dataset-publish-int", "--dspi"],
                help="Publishing interval for datasets in milliseconds. Minimum: -1.",
                type=int,
                arg_group="Default Dataset",
            )
            context.argument(
                "dataset_sampling_interval",
                options_list=["--dataset-sampling-int", "--dssi"],
                help="Sampling interval for datasets in milliseconds. Minimum: -1.",
                type=int,
                arg_group="Default Dataset",
            )
            context.argument(
                "dataset_queue_size",
                options_list=["--dataset-queue-size", "--dsqs"],
                help="Queue size for datasets. Minimum: 0.",
                type=int,
                arg_group="Default Dataset",
            )
            context.argument(
                "dataset_key_frame_count",
                options_list=["--dataset-key-frame-count", "--dskfc"],
                help="Key frame count for datasets. Minimum: 0.",
                type=int,
                arg_group="Default Dataset",
            )
            context.argument(
                "dataset_start_instance",
                options_list=["--dataset-start-inst", "--dss"],
                help="Start instance for datasets.",
                arg_group="Default Dataset",
            )
            context.argument(
                "datasets_destinations",
                options_list=["--dataset-dest", "--dsd"],
                help="Key=value pairs representing the destination for datasets. "
                "Allowed and required arguments are `topic`, `retain`, `qos`, and `ttl` for MQTT destinations. ",
                nargs="+",
                arg_group="Default Dataset",
            )
            context.argument(
                "events_publishing_interval",
                options_list=["--event-publish-int", "--evpi"],
                help="Publishing interval for events in milliseconds. Minimum: -1.",
                type=int,
                arg_group="Default Event",
            )
            context.argument(
                "events_queue_size",
                options_list=["--event-queue-size", "--evqs"],
                help="Queue size for events. Minimum: 0.",
                type=int,
                arg_group="Default Event",
            )
            context.argument(
                "events_start_instance",
                options_list=["--event-start-inst", "--evs"],
                help="Start instance for events.",
                arg_group="Default Event",
            )
            context.argument(
                "events_filter_type",
                options_list=["--event-filter-type", "--evft"],
                help="Filter type for events.",
                arg_group="Default Event",
            )
            context.argument(
                "events_filter_clauses",
                options_list=["--event-filter-clause", "--evf"],
                help="Space-separated key=value pairs for event filter clauses. Allowed keys are `path` (required), "
                "`type`, and `field`.",
                nargs="+",
                action="append",
                arg_group="Default Event",
            )
            context.argument(
                "events_destinations",
                options_list=["--event-dest", "--evd"],
                help="Key=value pairs representing the destination for events. "
                "Allowed and required arguments are `topic`, `retain`, `qos`, and `ttl` for MQTT destinations.",
                nargs="+",
                arg_group="Default Event",
            )

    with self.argument_context("iot ops ns asset custom dataset") as context:
        context.argument(
            "asset_name",
            options_list=["--asset", "-a"],
            help="Asset name.",
        )
        context.argument(
            "dataset_name",
            options_list=["--name"],
            help="Dataset name.",
        )
        context.argument(
            "replace",
            options_list=["--replace"],
            help="Replace the dataset if another dataset with the same name is already present.",
            arg_type=get_three_state_flag(),
        )
        context.argument(
            "dataset_configuration",
            options_list=["--config"],
            help="Custom dataset configuration as a JSON string or file path.",
        )
        context.argument(
            "dataset_data_source",
            options_list=["--data-source", "--ds"],
            help="Data source for the dataset.",
        )
        context.argument(
            "dataset_destinations",
            options_list=["--destination", "--dest"],
            help="Key=value pairs representing the destination for dataset. "
            "Allowed arguments include: `key` for BrokerStateStore; `path` for Storage; or "
            "`topic`, `retain`, `qos`, and `ttl` for MQTT.",
            action="append",
            nargs="+",
        )

    with self.argument_context("iot ops ns asset custom dataset point") as context:
        context.argument(
            "dataset_name",
            options_list=["--dataset", "-d"],
            help="Dataset name.",
        )
        context.argument(
            "datapoint_name",
            options_list=["--name"],
            help="Data point name.",
        )
        context.argument(
            "data_source",
            options_list=["--data-source", "--ds"],
            help="Data source for the data point.",
        )
        context.argument(
            "custom_configuration",
            options_list=["--config"],
            help="Custom data point configuration as a JSON string or file path.",
        )
        context.argument(
            "replace",
            options_list=["--replace"],
            help="Replace the data point if another point with the same name is already present.",
            arg_type=get_three_state_flag(),
        )

    with self.argument_context("iot ops ns asset opcua dataset") as context:
        context.argument(
            "asset_name",
            options_list=["--asset", "-a"],
            help="Asset name.",
        )
        context.argument(
            "dataset_name",
            options_list=["--name"],
            help="Dataset name.",
        )
        context.argument(
            "dataset_data_source",
            options_list=["--data-source", "--ds"],
            help="Data source for the dataset.",
        )
        context.argument(
            "dataset_publishing_interval",
            options_list=["--dataset-publish-int", "--dspi"],
            help="Publishing interval for datasets in milliseconds. Minimum: -1.",
            type=int,
        )
        context.argument(
            "dataset_sampling_interval",
            options_list=["--dataset-sampling-int", "--dssi"],
            help="Sampling interval for datasets in milliseconds. Minimum: -1.",
            type=int,
        )
        context.argument(
            "dataset_queue_size",
            options_list=["--dataset-queue-size", "--dsqs"],
            help="Queue size for datasets. Minimum: 0.",
            type=int,
        )
        context.argument(
            "dataset_key_frame_count",
            options_list=["--dataset-key-frame-count", "--dskfc"],
            help="Key frame count for datasets. Minimum: 0.",
            type=int,
        )
        context.argument(
            "dataset_start_instance",
            options_list=["--dataset-start-inst", "--dss"],
            help="Start instance for datasets.",
        )
        context.argument(
            "datasets_destinations",
            options_list=["--dataset-dest", "--dsd"],
            help="Key=value pairs representing the destination for datasets. "
            "Allowed and required arguments are `topic`, `retain`, `qos`, and `ttl` for MQTT destinations. ",
            nargs="+",
        )
        context.argument(
            "replace",
            options_list=["--replace"],
            help="Replace the dataset if another dataset with the same name is already present.",
            arg_type=get_three_state_flag(),
        )

    with self.argument_context("iot ops ns asset opcua dataset point") as context:
        context.argument(
            "dataset_name",
            options_list=["--dataset", "-d"],
            help="Dataset name.",
        )
        context.argument(
            "datapoint_name",
            options_list=["--name"],
            help="Data point name.",
        )
        context.argument(
            "data_source",
            options_list=["--data-source", "--ds"],
            help="Data source for the OPC UA data point.",
        )
        context.argument(
            "sampling_interval",
            options_list=["--sampling-int", "--si"],
            help="Sampling interval in milliseconds. Minimum: -1.",
            type=int,
            arg_group="Default Dataset",
        )
        context.argument(
            "queue_size",
            options_list=["--queue-size", "--qs"],
            help="Queue size. Minimum: 0.",
            type=int,
            arg_group="Default Dataset",
        )
        context.argument(
            "replace",
            options_list=["--replace"],
            help="Replace the data point if another point with the same name is already present.",
            arg_type=get_three_state_flag(),
        )

    with self.argument_context("iot ops ns asset custom event") as context:
        context.argument(
            "asset_name",
            options_list=["--asset", "-a"],
            help="Asset name.",
        )
        context.argument(
            "event_name",
            options_list=["--name"],
            help="Event name.",
        )
        context.argument(
            "event_notifier",
            options_list=["--event-notifier", "--en"],
            help="Event notifier.",
        )
        context.argument(
            "replace",
            options_list=["--replace"],
            help="Replace the event if another event with the same name is already present.",
            arg_type=get_three_state_flag(),
        )
        context.argument(
            "event_configuration",
            options_list=["--config"],
            help="Custom event configuration as a JSON string or file path.",
        )
        context.argument(
            "events_destinations",
            options_list=["--destination", "--dest"],
            help="Key=value pairs representing the destination for events. "
            "Allowed and required arguments are `topic`, `retain`, `qos`, and `ttl` for MQTT destinations.",
            action="append",
            nargs="+",
        )

    with self.argument_context("iot ops ns asset custom event point") as context:
        context.argument(
            "event_name",
            options_list=["--event", "-e"],
            help="Event name.",
        )
        context.argument(
            "datapoint_name",
            options_list=["--name"],
            help="Data point name.",
        )
        context.argument(
            "data_source",
            options_list=["--data-source", "--ds"],
            help="Data source for the event data point.",
        )
        context.argument(
            "custom_configuration",
            options_list=["--config"],
            help="Custom event data point configuration as a JSON string or file path.",
        )
        context.argument(
            "replace",
            options_list=["--replace"],
            help="Replace the data point if another point with the same name is already present.",
            arg_type=get_three_state_flag(),
        )

    with self.argument_context("iot ops ns asset onvif event") as context:
        context.argument(
            "asset_name",
            options_list=["--asset", "-a"],
            help="Asset name.",
        )
        context.argument(
            "event_name",
            options_list=["--name"],
            help="Event name.",
        )
        context.argument(
            "event_notifier",
            options_list=["--event-notifier", "--en"],
            help="Event notifier.",
        )
        context.argument(
            "replace",
            options_list=["--replace"],
            help="Replace the event if another event with the same name is already present.",
            arg_type=get_three_state_flag(),
        )
        context.argument(
            "events_destinations",
            options_list=["--destination", "--dest"],
            help="Key=value pairs representing the destination for events. "
            "Allowed and required arguments are `topic`, `retain`, `qos`, and `ttl` for MQTT destinations.",
            action="append",
            nargs="+",
        )

    with self.argument_context("iot ops ns asset opcua event") as context:
        context.argument(
            "asset_name",
            options_list=["--asset", "-a"],
            help="Asset name.",
        )
        context.argument(
            "event_name",
            options_list=["--name"],
            help="Event name.",
        )
        context.argument(
            "event_notifier",
            options_list=["--event-notifier", "--en"],
            help="Event notifier.",
        )
        context.argument(
            "opcua_event_publishing_interval",
            options_list=["--event-publish-int", "--evpi"],
            help="Publishing interval for events in milliseconds. Minimum: -1.",
            type=int,
        )
        context.argument(
            "opcua_event_queue_size",
            options_list=["--event-queue-size", "--evqs"],
            help="Queue size for events. Minimum: 0.",
            type=int,
        )
        context.argument(
            "opcua_event_filter_type",
            options_list=["--event-filter-type", "--evft"],
            help="Filter type for events.",
        )
        context.argument(
            "opcua_event_filter_clauses",
            options_list=["--event-filter-clause", "--evf"],
            help="Space-separated key=value pairs for event filter clauses. Allowed keys are `path` (required), "
            "`type`, and `field`.",
            nargs="+",
            action="append",
        )
        context.argument(
            "events_destinations",
            options_list=["--event-dest", "--evd"],
            help="Key=value pairs representing the destination for events. "
            "Allowed and required arguments are `topic`, `retain`, `qos`, and `ttl` for MQTT destinations.",
            nargs="+",
        )
        context.argument(
            "replace",
            options_list=["--replace"],
            help="Replace the event if another event with the same name is already present.",
            arg_type=get_three_state_flag(),
        )

    with self.argument_context("iot ops ns asset opcua event point") as context:
        context.argument(
            "event_name",
            options_list=["--event", "-e"],
            help="Event name.",
        )
        context.argument(
            "datapoint_name",
            options_list=["--name"],
            help="Data point name.",
        )
        context.argument(
            "data_source",
            options_list=["--data-source", "--ds"],
            help="Data source for the OPC UA event data point.",
        )
        context.argument(
            "sampling_interval",
            options_list=["--sampling-int", "--si"],
            help="Sampling interval in milliseconds. Minimum: -1.",
            type=int,
        )
        context.argument(
            "queue_size",
            options_list=["--queue-size", "--qs"],
            help="Queue size. Minimum: 0.",
            type=int,
        )
        context.argument(
            "replace",
            options_list=["--replace"],
            help="Replace the data point if another point with the same name is already present.",
            arg_type=get_three_state_flag(),
        )

    with self.argument_context("iot ops ns asset custom event") as context:
        context.argument(
            "asset_name",
            options_list=["--asset", "-a"],
            help="Asset name.",
        )
        context.argument(
            "event_name",
            options_list=["--name"],
            help="Event name.",
        )
        context.argument(
            "event_notifier",
            options_list=["--event-notifier", "--en"],
            help="Event notifier.",
        )
        context.argument(
            "replace",
            options_list=["--replace"],
            help="Replace the event if another event with the same name is already present.",
            arg_type=get_three_state_flag(),
        )
        context.argument(
            "event_configuration",
            options_list=["--config"],
            help="Custom event configuration as a JSON string or file path.",
        )
        context.argument(
            "events_destinations",
            options_list=["--destination", "--dest"],
            help="Key=value pairs representing the destination for events. "
            "Allowed and required arguments are `topic`, `retain`, `qos`, and `ttl` for MQTT destinations.",
            action="append",
            nargs="+",
        )

    with self.argument_context("iot ops ns asset custom event point") as context:
        context.argument(
            "event_name",
            options_list=["--event", "-e"],
            help="Event name.",
        )
        context.argument(
            "datapoint_name",
            options_list=["--name"],
            help="Data point name.",
        )
        context.argument(
            "data_source",
            options_list=["--data-source", "--ds"],
            help="Data source for the event data point.",
        )
        context.argument(
            "custom_configuration",
            options_list=["--config"],
            help="Custom event data point configuration as a JSON string or file path.",
        )
        context.argument(
            "replace",
            options_list=["--replace"],
            help="Replace the data point if another point with the same name is already present.",
            arg_type=get_three_state_flag(),
        )

    with self.argument_context("iot ops ns asset onvif event") as context:
        context.argument(
            "asset_name",
            options_list=["--asset", "-a"],
            help="Asset name.",
        )
        context.argument(
            "event_name",
            options_list=["--name"],
            help="Event name.",
        )
        context.argument(
            "event_notifier",
            options_list=["--event-notifier", "--en"],
            help="Event notifier.",
        )
        context.argument(
            "replace",
            options_list=["--replace"],
            help="Replace the event if another event with the same name is already present.",
            arg_type=get_three_state_flag(),
        )
        context.argument(
            "events_destinations",
            options_list=["--destination", "--dest"],
            help="Key=value pairs representing the destination for events. "
            "Allowed and required arguments are `topic`, `retain`, `qos`, and `ttl` for MQTT destinations.",
            action="append",
            nargs="+",
        )

    with self.argument_context("iot ops ns asset opcua event") as context:
        context.argument(
            "asset_name",
            options_list=["--asset", "-a"],
            help="Asset name.",
        )
        context.argument(
            "event_name",
            options_list=["--name"],
            help="Event name.",
        )
        context.argument(
            "event_notifier",
            options_list=["--event-notifier", "--en"],
            help="Event notifier.",
        )
        context.argument(
            "opcua_event_publishing_interval",
            options_list=["--event-publish-int", "--evpi"],
            help="Publishing interval for events in milliseconds. Minimum: -1.",
            type=int,
        )
        context.argument(
            "opcua_event_queue_size",
            options_list=["--event-queue-size", "--evqs"],
            help="Queue size for events. Minimum: 0.",
            type=int,
        )
        context.argument(
            "opcua_event_filter_type",
            options_list=["--event-filter-type", "--evft"],
            help="Filter type for events.",
        )
        context.argument(
            "opcua_event_filter_clauses",
            options_list=["--event-filter-clause", "--evf"],
            help="Space-separated key=value pairs for event filter clauses. Allowed keys are `path` (required), "
            "`type`, and `field`.",
            nargs="+",
            action="append",
        )
        context.argument(
            "events_destinations",
            options_list=["--event-dest", "--evd"],
            help="Key=value pairs representing the destination for events. "
            "Allowed and required arguments are `topic`, `retain`, `qos`, and `ttl` for MQTT destinations.",
            nargs="+",
        )
        context.argument(
            "replace",
            options_list=["--replace"],
            help="Replace the event if another event with the same name is already present.",
            arg_type=get_three_state_flag(),
        )
    # TODO: to be added in follow-up release
    # with self.argument_context("iot ops ns asset opcua event point") as context:
    #     context.argument(
    #         "event_name",
    #         options_list=["--event", "-e"],
    #         help="Event name.",
    #     )
    #     context.argument(
    #         "datapoint_name",
    #         options_list=["--name"],
    #         help="Data point name.",
    #     )
    #     context.argument(
    #         "data_source",
    #         options_list=["--data-source", "--ds"],
    #         help="Data source for the OPC UA event data point.",
    #     )
    #     context.argument(
    #         "sampling_interval",
    #         options_list=["--sampling-int", "--si"],
    #         help="Sampling interval in milliseconds. Minimum: -1.",
    #         type=int,
    #     )
    #     context.argument(
    #         "queue_size",
    #         options_list=["--queue-size", "--qs"],
    #         help="Queue size. Minimum: 0.",
    #         type=int,
    #     )
    #     context.argument(
    #         "replace",
    #         options_list=["--replace"],
    #         help="Replace the data point if another point with the same name is already present.",
    #         arg_type=get_three_state_flag(),
    #     )
