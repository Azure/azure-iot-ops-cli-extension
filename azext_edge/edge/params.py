# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""
CLI parameter definitions.
"""

from azure.cli.core.commands.parameters import (
    get_enum_type,
    get_three_state_flag,
    tags_type,
)
from knack.arguments import CaseInsensitiveList

from azext_edge.edge.providers.edge_api.dataflow import DataflowResourceKinds

from ._validators import validate_namespace, validate_resource_name
from .common import FileType, OpsServiceType, SecurityModes, SecurityPolicies, TopicRetain, AEPAuthModes
from .providers.check.common import ResourceOutputDetailLevel
from .providers.edge_api import (
    DeviceRegistryResourceKinds,
    MqResourceKinds,
    OpcuaResourceKinds,
)
from .providers.orchestration.common import (
    IdentityUsageType,
    KubernetesDistroType,
    MqMemoryProfile,
    MqServiceType,
    TRUST_SETTING_KEYS,
)


def load_iotops_arguments(self, _):
    """
    Load CLI Args for Knack parser
    """

    with self.argument_context("iot ops") as context:
        context.argument(
            "context_name",
            options_list=["--context"],
            help="Kubeconfig context name to use for k8s cluster communication. "
            "If no context is provided current_context is used.",
            arg_group="K8s Cluster",
        )
        context.argument(
            "namespace",
            options_list=["--namespace", "-n"],
            help="K8s cluster namespace the command should operate against. "
            "If no namespace is provided the kubeconfig current_context namespace will be used. "
            "If not defined, the fallback value `azure-iot-operations` will be used. ",
            validator=validate_namespace,
        )
        context.argument(
            "confirm_yes",
            options_list=["--yes", "-y"],
            arg_type=get_three_state_flag(),
            help="Confirm [y]es without a prompt. Useful for CI and automation scenarios.",
        )
        context.argument(
            "no_progress",
            options_list=["--no-progress"],
            arg_type=get_three_state_flag(),
            help="Disable visual representation of work.",
        )
        context.argument(
            "force",
            options_list=["--force"],
            arg_type=get_three_state_flag(),
            help="Force the operation to execute.",
        )
        context.argument(
            "tags",
            options_list=["--tags"],
            arg_type=tags_type,
            help="Instance tags. Property bag in key-value pairs with the following format: a=b c=d. "
            'Use --tags "" to remove all tags.',
        )
        context.argument(
            "instance_name",
            options_list=["--name", "-n"],
            help="IoT Operations instance name.",
        )
        context.argument(
            "instance_description",
            options_list=["--description"],
            help="Description of the IoT Operations instance.",
        )
        context.argument(
            "broker_name",
            options_list=["--broker", "-b"],
            help="Mqtt broker name.",
        )
        context.argument(
            "mi_user_assigned",
            options_list=["--mi-user-assigned"],
            help="The resource Id for the desired user-assigned managed identity to use with the instance.",
        )
        context.argument(
            "federated_credential_name",
            options_list=["--fc"],
            help="The federated credential name.",
        )
        context.argument(
            "use_self_hosted_issuer",
            options_list=["--self-hosted-issuer"],
            arg_type=get_three_state_flag(),
            help="Use the self-hosted oidc issuer for federation.",
        )

    with self.argument_context("iot ops identity") as context:
        context.argument(
            "usage_type",
            options_list=["--usage"],
            arg_type=get_enum_type(IdentityUsageType),
            help="Indicates the usage type of the associated identity.",
        )

    with self.argument_context("iot ops show") as context:
        context.argument(
            "show_tree",
            options_list=["--tree"],
            arg_type=get_three_state_flag(),
            help="Use to visualize the IoT Operations deployment against the backing cluster.",
        )

    with self.argument_context("iot ops support") as context:
        context.argument(
            "ops_service",
            options_list=["--ops-service", "--svc"],
            choices=CaseInsensitiveList(OpsServiceType.list()),
            help="The IoT Operations service the support bundle creation should apply to. "
            "If auto is selected, the operation will detect which services are available.",
        )
        context.argument(
            "log_age_seconds",
            options_list=["--log-age"],
            help="Container log age in seconds.",
            type=int,
        )
        context.argument(
            "bundle_dir",
            options_list=["--bundle-dir"],
            help="The local directory the produced bundle will be saved to. "
            "If no directory is provided the current directory is used.",
        )
        context.argument(
            "include_mq_traces",
            options_list=["--broker-traces"],
            arg_type=get_three_state_flag(),
            help="Include mqtt broker traces in the support bundle. "
            "Usage may add considerable size to the produced bundle.",
        )

    with self.argument_context("iot ops check") as context:
        context.argument(
            "pre_deployment_checks",
            options_list=["--pre"],
            help="Run pre-requisite checks to determine if the minimum "
            "requirements of a service deployment are fulfilled.",
            arg_type=get_three_state_flag(),
        )
        context.argument(
            "post_deployment_checks",
            options_list=["--post"],
            help="Run post-deployment checks.",
            arg_type=get_three_state_flag(),
        )
        context.argument(
            "as_object",
            options_list=["--as-object"],
            help="Output check content and validations in a CI friendly data structure.",
            arg_type=get_three_state_flag(),
            arg_group="Format",
        )
        context.argument(
            "ops_service",
            options_list=["--ops-service", "--svc"],
            choices=CaseInsensitiveList(OpsServiceType.list_check_services()),
            help="The IoT Operations service deployment that will be evaluated.",
        )
        context.argument(
            "resource_kinds",
            nargs="*",
            options_list=["--resources"],
            choices=CaseInsensitiveList(
                set(
                    [
                        DeviceRegistryResourceKinds.ASSET.value,
                        DeviceRegistryResourceKinds.ASSETENDPOINTPROFILE.value,
                        MqResourceKinds.BROKER.value,
                        MqResourceKinds.BROKER_LISTENER.value,
                        OpcuaResourceKinds.ASSET_TYPE.value,
                        DataflowResourceKinds.DATAFLOW.value,
                        DataflowResourceKinds.DATAFLOWENDPOINT.value,
                        DataflowResourceKinds.DATAFLOWPROFILE.value,
                    ]
                )
            ),
            help="Only run checks on specific resource kinds. Use space-separated values.",
        ),
        context.argument(
            "detail_level",
            options_list=["--detail-level"],
            default=ResourceOutputDetailLevel.summary.value,
            choices=ResourceOutputDetailLevel.list(),
            arg_type=get_enum_type(ResourceOutputDetailLevel),
            help="Controls the level of detail displayed in the check output. "
            "Choose 0 for a summary view (minimal output), "
            "1 for a detailed view (more comprehensive information), "
            "or 2 for a verbose view (all available information).",
        ),
        context.argument(
            "resource_name",
            options_list=["--resource-name", "--rn"],
            help="Only run checks for the specific resource name. "
            "The name is case insensitive. "
            "Glob patterns '*' and '?' are supported. "
            "Note: Only alphanumeric characters, hyphens, '?' and '*' are allowed.",
            validator=validate_resource_name,
        ),

    with self.argument_context("iot ops dataflow") as context:
        context.argument(
            "instance_name",
            options_list=["--instance", "-i"],
            help="IoT Operations instance name.",
        )
        context.argument(
            "dataflow_name",
            options_list=["--name", "-n"],
            help="Dataflow name.",
        )
        context.argument(
            "profile_name",
            options_list=["--profile", "-p"],
            help="Dataflow profile name.",
        )

    with self.argument_context("iot ops dataflow profile") as context:
        context.argument(
            "profile_name",
            options_list=["--name", "-n"],
            help="Dataflow profile name.",
        )

    with self.argument_context("iot ops dataflow endpoint") as context:
        context.argument(
            "endpoint_name",
            options_list=["--name", "-n"],
            help="Dataflow endpoint name.",
        )

    with self.argument_context("iot ops broker") as context:
        context.argument(
            "instance_name",
            options_list=["--instance", "-i"],
            help="IoT Operations instance name.",
        )
        context.argument(
            "broker_name",
            options_list=["--name", "-n"],
            help="Mqtt broker name.",
        )

    with self.argument_context("iot ops broker listener") as context:
        context.argument(
            "listener_name",
            options_list=["--name", "-n"],
            help="Mqtt broker listener name.",
        )
        context.argument(
            "broker_name",
            options_list=["--broker", "-b"],
            help="Mqtt broker name.",
        )

    with self.argument_context("iot ops broker authn") as context:
        context.argument(
            "authn_name",
            options_list=["--name", "-n"],
            help="Mqtt broker authentication resource name.",
        )
        context.argument(
            "broker_name",
            options_list=["--broker", "-b"],
            help="Mqtt broker name.",
        )

    with self.argument_context("iot ops broker authz") as context:
        context.argument(
            "authz_name",
            options_list=["--name", "-n"],
            help="Mqtt broker authorization resource name.",
        )
        context.argument(
            "broker_name",
            options_list=["--broker", "-b"],
            help="Mqtt broker name.",
        )

    with self.argument_context("iot ops broker stats") as context:
        context.argument(
            "refresh_in_seconds",
            options_list=["--refresh"],
            help="Number of seconds between a stats refresh. Applicable with --watch.",
            type=int,
        )
        context.argument(
            "watch",
            options_list=["--watch"],
            help="The operation blocks and dynamically updates a stats table.",
            arg_type=get_three_state_flag(),
        )
        context.argument(
            "diag_service_pod_prefix",
            options_list=["--diag-svc-pod"],
            help="The diagnostic service pod prefix. The first pod fulfilling the condition will be connected to.",
            arg_group="Diagnostics Pod",
        )
        context.argument(
            "pod_metrics_port",
            type=int,
            options_list=["--metrics-port"],
            help="Diagnostic service metrics API port.",
            arg_group="Diagnostics Pod",
        )
        context.argument(
            "pod_protobuf_port",
            type=int,
            options_list=["--protobuf-port"],
            help="Diagnostic service protobuf API port.",
            arg_group="Diagnostics Pod",
        )
        context.argument(
            "raw_response_print",
            options_list=["--raw"],
            arg_type=get_three_state_flag(),
            help="Return raw output from the metrics API.",
        )
        context.argument(
            "trace_ids",
            nargs="*",
            options_list=["--trace-ids"],
            help="Space-separated trace ids in hex format.",
            arg_group="Trace",
        )
        context.argument(
            "trace_dir",
            options_list=["--trace-dir"],
            help="Local directory where traces will be bundled and stored at.",
            arg_group="Trace",
        )

    for cmd_space in ["iot ops init", "iot ops create"]:
        with self.argument_context(cmd_space) as context:
            context.argument(
                "instance_name",
                options_list=["--name", "-n"],
                help="IoT Operations instance name. An instance name must be provided to "
                "deploy an instance during init orchestration.",
            )
            context.argument(
                "cluster_name",
                options_list=["--cluster"],
                help="Target cluster name for IoT Operations deployment.",
            )
            context.argument(
                "cluster_namespace",
                options_list=["--cluster-namespace"],
                help="The cluster namespace IoT Operations infra will be deployed to. Must be lowercase.",
            )
            context.argument(
                "custom_location_name",
                options_list=["--custom-location"],
                help="The custom location name corresponding to the IoT Operations deployment. "
                "The default is in the form 'location-{hash(5)}'.",
            )
            context.argument(
                "location",
                options_list=["--location"],
                help="The region that will be used for provisioned resource collateral. "
                "If not provided the connected cluster location will be used.",
            )
            context.argument(
                "enable_rsync_rules",
                options_list=["--enable-rsync"],
                arg_type=get_three_state_flag(),
                help="Resource sync rules will be included in the IoT Operations deployment.",
            )
            context.argument(
                "ensure_latest",
                options_list=["--ensure-latest"],
                arg_type=get_three_state_flag(),
                help="Ensure the latest IoT Ops CLI is being used, raising an error if an upgrade is available.",
            )
            # Schema Registry
            context.argument(
                "schema_registry_resource_id",
                options_list=["--sr-resource-id"],
                help="The schema registry resource Id to use with IoT Operations.",
            )
            # Akri
            context.argument(
                "container_runtime_socket",
                options_list=["--runtime-socket"],
                help="The default node path of the container runtime socket. If not provided (default), the "
                "socket path is determined by --kubernetes-distro.",
                arg_group="Akri",
            )
            context.argument(
                "kubernetes_distro",
                arg_type=get_enum_type(KubernetesDistroType),
                options_list=["--kubernetes-distro"],
                help="The Kubernetes distro to use for Akri configuration. The selected distro implies the "
                "default container runtime socket path when no --runtime-socket value is provided.",
                arg_group="Akri",
            )
            # Broker
            context.argument(
                "custom_broker_config_file",
                options_list=["--broker-config-file"],
                help="Path to a json file with custom broker config properties. "
                "File config content is used over individual broker config parameters. "
                "Useful for advanced scenarios. "
                "The expected format is described at https://aka.ms/aziotops-broker-config.",
                arg_group="Broker",
            )
            context.argument(
                "add_insecure_listener",
                options_list=[
                    "--add-insecure-listener",
                    context.deprecate(
                        target="--mq-insecure",
                        redirect="--add-insecure-listener",
                        hide=True,
                    ),
                ],
                arg_type=get_three_state_flag(),
                help="When enabled the mqtt broker deployment will include a listener "
                f"of service type {MqServiceType.load_balancer.value}, bound to port 1883 with no authN or authZ. "
                "For non-production workloads only.",
                arg_group="Broker",
            )
            # Broker Config
            context.argument(
                "broker_frontend_replicas",
                type=int,
                options_list=["--broker-frontend-replicas", "--fr"],
                help="Mqtt broker frontend replicas. Min value: 1, max value: 16.",
                arg_group="Broker",
            )
            context.argument(
                "broker_frontend_workers",
                type=int,
                options_list=["--broker-frontend-workers", "--fw"],
                help="Mqtt broker frontend workers. Min value: 1, max value: 16.",
                arg_group="Broker",
            )
            context.argument(
                "broker_backend_redundancy_factor",
                type=int,
                options_list=["--broker-backend-rf", "--br"],
                help="Mqtt broker backend redundancy factor. Min value: 1, max value: 5.",
                arg_group="Broker",
            )
            context.argument(
                "broker_backend_workers",
                type=int,
                options_list=["--broker-backend-workers", "--bw"],
                help="Mqtt broker backend workers. Min value: 1, max value: 16.",
                arg_group="Broker",
            )
            context.argument(
                "broker_backend_partitions",
                type=int,
                options_list=["--broker-backend-part", "--bp"],
                help="Mqtt broker backend partitions. Min value: 1, max value: 16.",
                arg_group="Broker",
            )
            context.argument(
                "broker_memory_profile",
                arg_type=get_enum_type(MqMemoryProfile),
                options_list=["--broker-mem-profile", "--mp"],
                help="Mqtt broker memory profile.",
                arg_group="Broker",
            )
            context.argument(
                "broker_service_type",
                arg_type=get_enum_type(MqServiceType),
                options_list=["--broker-listener-type", "--lt"],
                help="Service type associated with the default mqtt broker listener.",
                arg_group="Broker",
            )
            context.argument(
                "ops_config",
                options_list=["--ops-config"],
                nargs="+",
                action="extend",
                help="IoT Operations arc extension custom configuration. Format is space-separated key=value pairs. "
                "--ops-config can be used one or more times. For advanced use cases.",
            )
            context.argument(
                "ops_version",
                options_list=["--ops-version"],
                help="Use to override the built-in IoT Operations arc extension version. ",
                deprecate_info=context.deprecate(hide=True),
            )
            context.argument(
                "enable_fault_tolerance",
                arg_type=get_three_state_flag(),
                options_list=["--enable-fault-tolerance"],
                help="Enable fault tolerance for Azure Arc Container Storage. At least 3 cluster nodes are required.",
                arg_group="Container Storage",
            )
            context.argument(
                "dataflow_profile_instances",
                type=int,
                options_list=["--df-profile-instances"],
                help="The instance count associated with the default dataflow profile.",
                arg_group="Dataflow",
            )
            context.argument(
                "trust_settings",
                options_list=["--trust-settings"],
                nargs="+",
                action="store",
                help="Settings for user provided trust bundle. Used for component TLS. Format is space-separated "
                f"key=value pairs. The following keys are required: `{'`, `'.join(TRUST_SETTING_KEYS)}`. If not "
                "used, a system provided self-signed trust bundle is configured.",
                arg_group="Trust",
            )

    with self.argument_context("iot ops delete") as context:
        context.argument(
            "include_dependencies",
            options_list=["--include-deps"],
            arg_type=get_three_state_flag(),
            help="Indicates the command should remove IoT Operations dependencies. "
            "This option is intended to reverse the application of init.",
        )
        context.argument(
            "cluster_name",
            options_list=["--cluster"],
            help="Target cluster name for IoT Operations deletion.",
        )

    with self.argument_context("iot ops secretsync") as context:
        context.argument(
            "keyvault_resource_id",
            options_list=["--kv-resource-id"],
            help="Key Vault ARM resource Id.",
        )
        context.argument(
            "spc_name",
            options_list=["--spc"],
            help="The secret provider class name for secret sync enablement. "
            "The default pattern is '{instance_name}-spc'.",
        )
        context.argument(
            "skip_role_assignments",
            options_list=["--skip-ra"],
            arg_type=get_three_state_flag(),
            help="When used the role assignment step of the operation will be skipped.",
        )

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
            "instance_name",
            options_list=["--instance"],
            help="Instance name to associate the created asset with."
        )
        context.argument(
            "instance_resource_group",
            options_list=["--instance-resource-group", "--ig"],
            help="Instance resource group. If not provided, asset resource group will be used."
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
            help="Space-separated key=value pairs corresponding to properties of the data point to create. "
            "The following key values are supported: `data_source` (required), `name` (required), "
            "`observability_mode` (None, Gauge, Counter, Histogram, or Log), `sampling_interval` (int), "
            "`queue_size` (int). "
            "--data can be used 1 or more times. Review help examples for full parameter usage",
            arg_group="Data-point",
        )
        context.argument(
            "data_points_file_path",
            options_list=["--data-file", "--df"],
            help="File path for the file containing the data points. The following file types are supported: "
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
            "discovered",
            options_list=["--discovered"],
            help="Flag to determine if an asset was discovered on the cluster.",
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
            arg_group="Topic Default",
        )
        context.argument(
            "default_topic_retain",
            options_list=["--topic-retain", "--tr"],
            help="Default topic retain policy.",
            arg_group="Topic Default",
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
        context.argument(  # TODO: figure out better wording
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
            help="Capability Id. If not provided, data point name will be used.",
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
            help="Replace all asset data points with those from the file. If false, the file data points "
            "will be appended.",
            arg_type=get_three_state_flag(),
        )
        context.argument(
            "file_path",
            options_list=["--input-file", "--if"],
            help="File path for the file containing the data points. The following file types are supported: "
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
            help="Replace all asset events with those from the file. If false, the file events will be appended.",
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
            help="Instance resource group. If not provided, asset endpoint profile resource group will be used."
        )
        context.argument(
            "instance_subscription",
            options_list=["--instance-subscription", "--is"],
            help="Instance subscription id. If not provided, asset endpoint profile subscription id will be used.",
            deprecate_info=context.deprecate(hide=True),
        )
        context.argument(
            "discovered",
            options_list=["--discovered"],
            help="Flag to determine if an asset endpoint profile was discovered on the cluster.",
            arg_group="Additional Info",
            arg_type=get_three_state_flag(),
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
            arg_type=get_enum_type(AEPAuthModes)
        )
        context.argument(
            "certificate_reference",
            options_list=["--certificate-ref", "--cert-ref", "--cr"],
            help="Reference for the certificate used in authentication. This method of user authentication is not "
            "supported yet.",
            arg_group="Authentication",
        )
        context.argument(
            "password_reference",
            options_list=["--password-ref", "--pr"],
            help="Reference for the password used in authentication.",
            arg_group="Authentication",
        )
        context.argument(
            "username_reference",
            options_list=["--username-reference", "--ur"],
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
            arg_type=get_enum_type(SecurityPolicies),
        )
        context.argument(
            "security_mode",
            options_list=["--security-mode", "--sm"],
            help="Security mode.",
            arg_group="Connector",
            arg_type=get_enum_type(SecurityModes),
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

    with self.argument_context("iot ops schema registry") as context:
        context.argument(
            "schema_registry_name",
            options_list=["--name", "-n"],
            help="Schema registry name.",
        )
        context.argument(
            "registry_namespace",
            options_list=["--registry-namespace", "--rn"],
            help="Schema registry namespace. Uniquely identifies a schema registry within a tenant.",
        )
        context.argument(
            "tags",
            options_list=["--tags"],
            arg_type=tags_type,
            help="Schema registry tags. Property bag in key-value pairs with the following format: a=b c=d. "
            'Use --tags "" to remove all tags.',
        )
        context.argument(
            "description",
            options_list=["--desc"],
            help="Description for the schema registry.",
        )
        context.argument(
            "display_name",
            options_list=["--display-name"],
            help="Display name for the schema registry.",
        )
        context.argument(
            "location",
            options_list=["--location", "-l"],
            help="Region to create the schema registry. "
            "If no location is provided the resource group location will be used.",
        )
        context.argument(
            "storage_account_resource_id",
            options_list=["--sa-resource-id"],
            help="Storage account resource Id to be used with the schema registry.",
        )
        context.argument(
            "storage_container_name",
            options_list=["--sa-container"],
            help="Storage account container name where schemas will be stored.",
        )
        context.argument(
            "custom_role_id",
            options_list=["--custom-role-id"],
            help="Fully qualified role definition Id in the following format: "
            "/subscriptions/{subscriptionId}/providers/Microsoft.Authorization/roleDefinitions/{roleId}",
        )
