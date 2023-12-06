# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""
CLI parameter definitions.
"""

from knack.arguments import CaseInsensitiveList
from azure.cli.core.commands.parameters import get_three_state_flag, get_enum_type, tags_type

from .common import OpsServiceType
from .providers.edge_api import (
    DataProcessorResourceKinds,
    LnmResourceKinds,
    MqResourceKinds,
    OpcuaResourceKinds
)
from .providers.check.common import ResourceOutputDetailLevel
from .providers.orchestration.common import MqMemoryProfile, MqMode, MqServiceType

from ._validators import validate_namespace


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
            options_list=["--mq-traces"],
            arg_type=get_three_state_flag(),
            help="Include mq traces in the support bundle.",
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
            choices=CaseInsensitiveList(["mq", "dataprocessor", "lnm", "opcua"]),
            help="The IoT Operations service deployment that will be evaluated.",
        )
        context.argument(
            "resource_kinds",
            nargs="*",
            options_list=["--resources"],
            choices=CaseInsensitiveList(
                [
                    DataProcessorResourceKinds.DATASET.value,
                    DataProcessorResourceKinds.PIPELINE.value,
                    DataProcessorResourceKinds.INSTANCE.value,
                    LnmResourceKinds.LNM.value,
                    MqResourceKinds.BROKER.value,
                    MqResourceKinds.BROKER_LISTENER.value,
                    MqResourceKinds.DIAGNOSTIC_SERVICE.value,
                    MqResourceKinds.MQTT_BRIDGE_CONNECTOR.value,
                    MqResourceKinds.DATALAKE_CONNECTOR.value,
                    MqResourceKinds.KAFKA_CONNECTOR.value,
                    OpcuaResourceKinds.ASSET_TYPE.value,
                ]
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
            "Choose 0 for a summary view, (minimal output), "
            "1 for a detailed view, (more comprehensive information) "
            "or 2 for a verbose view, (all available information).",
        )

    with self.argument_context("iot ops mq get-password-hash") as context:
        context.argument(
            "iterations",
            options_list=["--iterations", "-i"],
            help="Using a higher iteration count will increase the cost of an exhaustive search but "
            "will also make derivation proportionally slower.",
            type=int,
        )
        context.argument(
            "passphrase",
            options_list=["--phrase", "-p"],
            help="Passphrase to apply hashing algorithm to.",
        )

    with self.argument_context("iot ops mq stats") as context:
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

    with self.argument_context("iot ops init") as context:
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
            "The default is in the form '{cluster_name}-ops-init-cl'.",
        )
        context.argument(
            "custom_location_namespace",
            options_list=["--custom-location-namespace", "--cln"],
            help="The namespace associated with the custom location mapped to the cluster. Must be lowercase. "
            "If not provided cluster namespace will be used.",
            deprecate_info=context.deprecate(hide=True),
        )
        context.argument(
            "location",
            options_list=["--location"],
            help="The ARM location that will be used for provisioned ARM collateral. "
            "If not provided the resource group location will be used.",
        )
        context.argument(
            "cluster_location",
            options_list=["--cluster-location"],
            help="The cluster ARM location.",
        )
        context.argument(
            "show_template",
            options_list=["--show-template"],
            arg_type=get_three_state_flag(),
            help="Flag when set, will output the template intended for deployment.",
            arg_group="Template",
        )
        context.argument(
            "no_progress",
            options_list=["--no-progress"],
            arg_type=get_three_state_flag(),
            help="Disable init progress bar.",
        )
        context.argument(
            "no_block",
            options_list=["--no-block"],
            arg_type=get_three_state_flag(),
            help="Return immediately after the IoT Operations deployment has started.",
        )
        context.argument(
            "no_deploy",
            options_list=["--no-deploy"],
            arg_type=get_three_state_flag(),
            help="The deployment of IoT Operations will be skipped.",
        )
        context.argument(
            "no_tls",
            options_list=["--no-tls"],
            arg_type=get_three_state_flag(),
            help="The configuration of TLS in the init workflow will be skipped.",
        )
        # Akri
        context.argument(
            "opcua_discovery_endpoint",
            options_list=["--opcua-discovery-url"],
            help="Configures an OPC-UA server endpoint for Akri discovery handlers. If not provided "
            "and --simulate-plc is set, this value becomes "
            "'opc.tcp://opcplc-000000.{cluster_namespace}:50000'.",
            arg_group="Akri",
        )
        # OPC-UA Broker
        context.argument(
            "simulate_plc",
            options_list=["--simulate-plc"],
            arg_type=get_three_state_flag(),
            help="Flag when set, will configure the OPC-UA broker installer to spin-up a PLC server.",
            arg_group="OPC-UA Broker",
        )
        # Data Processor
        context.argument(
            "dp_instance_name",
            options_list=["--dp-instance"],
            help="Instance name for data processor. The default is in the form '{cluster_name}-ops-init-processor'.",
            arg_group="Data Processor",
        )
        context.argument(
            "dp_reader_workers",
            type=int,
            options_list=["--dp-reader-workers"],
            help="Number of reader worker replicas",
            arg_group="Data Processor",
        )
        context.argument(
            "dp_runner_workers",
            type=int,
            options_list=["--dp-runner-workers"],
            help="Number of runner worker replicas",
            arg_group="Data Processor",
        )
        context.argument(
            "dp_message_stores",
            type=int,
            options_list=["--dp-message-stores"],
            help="Number of message store replicas",
            arg_group="Data Processor",
        )
        # MQ
        context.argument(
            "mq_instance_name",
            options_list=["--mq-instance"],
            help="The mq instance name. The default is in the form 'init-{hash}-mq-instance'.",
            arg_group="MQ",
        )
        context.argument(
            "mq_frontend_server_name",
            options_list=["--mq-frontend-server"],
            help="The mq frontend server name. The default is 'mq-dmqtt-frontend'.",
            arg_group="MQ",
        )
        context.argument(
            "mq_listener_name",
            options_list=["--mq-listener"],
            help="The mq listener name. The default is 'listener'.",
            arg_group="MQ",
        )
        context.argument(
            "mq_broker_name",
            options_list=["--mq-broker"],
            help="The mq broker name. The default is 'broker'.",
            arg_group="MQ",
        )
        context.argument(
            "mq_authn_name",
            options_list=["--mq-authn"],
            help="The mq authN name. The default is 'authn'.",
            arg_group="MQ",
        )
        context.argument(
            "mq_insecure",
            options_list=["--mq-insecure"],
            arg_type=get_three_state_flag(),
            help="When enabled the mq deployment will include a listener bound to port 1883 with no authN "
            "or authZ. The broker encryptInternalTraffic setting will be set to false. "
            "For non-production workloads only.",
            arg_group="MQ",
        )
        # MQ cardinality
        context.argument(
            "mq_frontend_replicas",
            type=int,
            options_list=["--mq-frontend-replicas"],
            help="MQ frontend replicas.",
            arg_group="MQ Cardinality",
        )
        context.argument(
            "mq_frontend_workers",
            type=int,
            options_list=["--mq-frontend-workers"],
            help="MQ frontend workers.",
            arg_group="MQ Cardinality",
        )
        context.argument(
            "mq_backend_redundancy_factor",
            type=int,
            options_list=["--mq-backend-rf"],
            help="MQ backend redundancy factor.",
            arg_group="MQ Cardinality",
        )
        context.argument(
            "mq_backend_workers",
            type=int,
            options_list=["--mq-backend-workers"],
            help="MQ backend workers.",
            arg_group="MQ Cardinality",
        )
        context.argument(
            "mq_backend_partitions",
            type=int,
            options_list=["--mq-backend-part"],
            help="MQ backend partitions.",
            arg_group="MQ Cardinality",
        )
        context.argument(
            "mq_mode",
            arg_type=get_enum_type(MqMode),
            options_list=["--mq-mode"],
            help="MQ mode of operation.",
            arg_group="MQ",
        )
        context.argument(
            "mq_memory_profile",
            arg_type=get_enum_type(MqMemoryProfile),
            options_list=["--mq-mem-profile"],
            help="MQ memory profile.",
            arg_group="MQ",
        )
        context.argument(
            "mq_service_type",
            arg_type=get_enum_type(MqServiceType),
            options_list=["--mq-service-type"],
            help="MQ service type.",
            arg_group="MQ",
        )
        # Symphony
        context.argument(
            "target_name",
            options_list=["--target"],
            help="Target name for ops orchestrator. The default is in the form '{cluster_name}-ops-init-target'.",
            arg_group="Orchestration",
        )
        # AKV CSI Driver
        context.argument(
            "keyvault_resource_id",
            options_list=["--kv-id"],
            help="Key Vault ARM resource Id. Providing this resource Id will enable the client "
            "to setup all necessary resources and cluster side configuration to enable "
            "the Key Vault CSI driver for IoT Operations.",
            arg_group="Key Vault CSI Driver",
        )
        context.argument(
            "keyvault_sat_secret_name",
            options_list=["--kv-sat-secret-name"],
            help="The Key Vault secret *name* to use for the IoT Operations service account (SAT). "
            "If the secret does not exist, it will be created with a cryptographically secure placeholder value.",
            arg_group="Key Vault CSI Driver",
        )
        context.argument(
            "disable_secret_rotation",
            options_list=["--disable-rotation"],
            arg_type=get_three_state_flag(),
            help="Flag to disable secret rotation.",
            arg_group="Key Vault CSI Driver",
        )
        context.argument(
            "rotation_poll_interval",
            options_list=["--rotation-int"],
            help="Rotation poll interval.",
            arg_group="Key Vault CSI Driver",
        )
        context.argument(
            "service_principal_app_id",
            options_list=["--sp-app-id"],
            help="Service principal app Id. If provided it will be used for CSI driver setup. "
            "Otherwise an app registration will be created. "
            "!Required! if the logged in principal does not have permissions to query graph.",
            arg_group="Key Vault CSI Driver",
        )
        context.argument(
            "service_principal_object_id",
            options_list=["--sp-object-id"],
            help="Service principal object Id. If provided it will be used for CSI driver setup. "
            "Otherwise a service principal will be queried and in necessary will be created. "
            "!Required! if the logged in principal does not have permissions to query graph.",
            arg_group="Key Vault CSI Driver",
        )
        context.argument(
            "service_principal_secret",
            options_list=["--sp-secret"],
            help="The secret corresponding to the provided service principal app Id. "
            "If provided it will be used for CSI driver setup. Otherwise a new secret "
            "will be requested from MS graph. "
            "!Required! if the logged in principal does not have permissions to query graph.",
            arg_group="Key Vault CSI Driver",
        )
        # TLS
        context.argument(
            "tls_ca_path",
            options_list=["--ca-file"],
            help="The path to the desired CA file in PEM format.",
            arg_group="TLS",
        )
        context.argument(
            "tls_ca_key_path",
            options_list=["--ca-key-file"],
            help="The path to the CA private key file in PEM format. !Required! when --ca-file is provided.",
            arg_group="TLS",
        )
        context.argument(
            "tls_ca_dir",
            options_list=["--ca-dir"],
            help="The local directory the generated test CA and private key will be placed in. "
            "If no directory is provided the current directory is used. Applicable when no "
            "--ca-file and --ca-key-file are provided.",
            arg_group="TLS",
        )

    with self.argument_context("iot ops asset") as context:
        context.argument(
            "asset_name",
            options_list=["--name", "-n"],
            help="Asset name.",
        )
        context.argument(
            "endpoint",
            options_list=["--endpoint"],
            help="Endpoint Uri.",
        )
        context.argument(
            "custom_location_name",
            options_list=["--custom-location", "--cl"],
            help="Custom location used to associate asset with cluster.",
        )
        context.argument(
            "custom_location_resource_group",
            options_list=["--custom-location-resource-group", "--clrg"],
            help="Resource group for custom location.",
        )
        context.argument(
            "custom_location_subscription",
            options_list=["--custom-location-subscription", "--cls"],
            help="Subscription Id for custom location. If not provided, asset subscription Id will be used.",
        )
        context.argument(
            "cluster_name",
            options_list=["--cluster", "-c"],
            help="Cluster to associate the asset with.",
        )
        context.argument(
            "cluster_resource_group",
            options_list=["--cluster-resource-group", "--crg"],
            help="Resource group for cluster.",
        )
        context.argument(
            "cluster_subscription",
            options_list=["--cluster-subscription", "--cs"],
            help="Subscription Id for cluster. If not provided, asset subscription Id will be used.",
        )
        context.argument(
            "asset_type",
            options_list=["--asset-type", "--at"],
            help="Asset type.",
            arg_group="Additional Info",
        )
        context.argument(
            "data_points",
            options_list=["--data"],
            nargs="+",
            action="append",
            help="Space-separated key=value pairs corresponding to properties of the data point to create. "
            "The following key values are supported: `capability_id`, `data_source` (required), `name`, "
            "`observability_mode` (none, gauge, counter, histogram, or log), `sampling_interval` (int), "
            "`queue_size` (int). "
            "--data can be used 1 or more times. Review help examples for full parameter usage",
            arg_group="Additional Info",
        )
        context.argument(
            "description",
            options_list=["--description", "-d"],
            help="Description.",
            arg_group="Additional Info",
        )
        context.argument(
            "display_name",
            options_list=["--display-name", "--dn"],
            help="Display name.",
            arg_group="Additional Info",
        )
        context.argument(
            "disabled",
            options_list=["--disable"],
            help="Disable an asset.",
            arg_group="Additional Info",
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
            "The following key values are supported: `capability_id`, `event_notifier` (required), "
            "`name`, `observability_mode` (none, gauge, counter, histogram, or log), `sampling_interval` "
            "(int), `queue_size` (int). "
            "--event can be used 1 or more times. Review help examples for full parameter usage",
            arg_group="Additional Info",
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
            "dp_publishing_interval",
            options_list=["--data-publish-int", "--dpi"],
            help="Default publishing interval for data points.",
            arg_group="Data Point Default",
        )
        context.argument(
            "dp_sampling_interval",
            options_list=["--data-sample-int", "--dsi"],
            help="Default sampling interval (in milliseconds) for data points.",
            arg_group="Data Point Default",
        )
        context.argument(
            "dp_queue_size",
            options_list=["--data-queue-size", "--dqs"],
            help="Default queue size for data points.",
            arg_group="Data Point Default",
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
            "tags",
            options_list=["--tags"],
            help="Asset tags. Property bag in key-value pairs with the following format: a=b c=d",
            arg_type=tags_type,
        )
        context.argument(
            "observability_mode",
            options_list=["--observability-mode", "--om"],
            help="Observability mode.",
        )
        context.argument(
            "queue_size",
            options_list=["--queue-size", "--qs"],
            help="Custom queue size.",
        )
        context.argument(
            "sampling_interval",
            options_list=["--sampling-interval", "--si"],
            help="Custom sampling interval (in milliseconds).",
        )

    with self.argument_context("iot ops asset query") as context:
        context.argument(
            "disabled",
            options_list=["--disabled"],
            help="State of asset.",
            arg_group="Additional Info",
            arg_type=get_three_state_flag(),
        )

    with self.argument_context("iot ops asset data-point") as context:
        context.argument(
            "asset_name",
            options_list=["--asset", "-a"],
            help="Asset name.",
        )
        context.argument(
            "capability_id",
            options_list=["--capability-id", "--ci"],
            help="Capability Id. If not provided, data point name will be used.",
        )
        context.argument(
            "name",
            options_list=["--name", "-n"],
            help="Data point name.",
        )
        context.argument(
            "data_source",
            options_list=["--data-source", "--ds"],
            help="Data source.",
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
            "name",
            options_list=["--name", "-n"],
            help="Event name.",
        )
        context.argument(
            "event_notifier",
            options_list=["--event-notifier", "--en"],
            help="Event notifier.",
        )
