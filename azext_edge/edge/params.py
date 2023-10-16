# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

"""
CLI parameter definitions.
"""

from azure.cli.core.commands.parameters import get_three_state_flag, get_enum_type
from knack.arguments import CaseInsensitiveList

from .common import SupportForEdgeServiceType
from .providers.edge_api import E4kResourceKinds
from .providers.orchestration.pas_versions import EdgeServiceMoniker
from .providers.check.common import ResourceOutputDetailLevel
from .providers.edge_api.bluefin import BluefinResourceKinds
from ._validators import validate_namespace


def load_iotedge_arguments(self, _):
    """
    Load CLI Args for Knack parser
    """

    with self.argument_context("edge") as context:
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
            "If not defined, the fallback value `default` will be used. ",
            validator=validate_namespace,
        )

    with self.argument_context("edge support") as context:
        context.argument(
            "edge_service",
            options_list=["--edge-service", "-e"],
            choices=CaseInsensitiveList(SupportForEdgeServiceType.list()),
            help="The edge service the support bundle creation should apply to. "
            "If auto is selected, the operation will detect which edge services are available.",
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

    with self.argument_context("edge check") as context:
        context.argument(
            "pre_deployment_checks",
            options_list=["--pre"],
            help="Run pre-requisite checks to determine if the minimum "
            "requirements of an edge service deployment are fulfilled.",
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
            "edge_service",
            options_list=["--edge-service", "-e"],
            choices=CaseInsensitiveList(["e4k", "lnm"]),
            help="The edge service deployment that will be evaluated.",
        )
        context.argument(
            "resource_kinds",
            nargs="*",
            options_list=["--resources"],
            choices=CaseInsensitiveList(
                [
                    E4kResourceKinds.BROKER.value,
                    E4kResourceKinds.BROKER_LISTENER.value,
                    E4kResourceKinds.DIAGNOSTIC_SERVICE.value,
                    E4kResourceKinds.MQTT_BRIDGE_CONNECTOR.value,
                    E4kResourceKinds.DATALAKE_CONNECTOR.value,
                    E4kResourceKinds.KAFKA_CONNECTOR.value,
                    BluefinResourceKinds.DATASET.value,
                    BluefinResourceKinds.PIPELINE.value,
                    BluefinResourceKinds.INSTANCE.value,
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

    with self.argument_context("edge e4k get-password-hash") as context:
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

    with self.argument_context("edge e4k stats") as context:
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

    with self.argument_context("edge init") as context:
        context.argument(
            "cluster_name",
            options_list=["--cluster"],
            help="Target cluster name for PAS deployment.",
        )
        context.argument(
            "custom_location_name",
            options_list=["--custom-location"],
            help="The custom location name corresponding to PAS solution deployment. "
            "If no custom location name is provided one will be generated in the form '{cluster_name}-azedge-init'.",
        )
        context.argument(
            "custom_location_namespace",
            options_list=["--custom-location-namespace", "--cln"],
            help="The namespace associated with the custom location mapped to the cluster. Must be lowercase. "
            "If not provided cluster namespace will be used.",
        )
        context.argument(
            "cluster_namespace",
            options_list=["--cluster-namespace"],
            help="The cluster namespace PAS infrastructure will be deployed to. Must be lowercase.",
        )
        context.argument(
            "location",
            options_list=["--location"],
            help="The ARM location that will be used for provisioned ARM collateral. "
            "If not provided the resource group location will be used.",
        )
        context.argument(
            "what_if",
            options_list=["--what-if"],
            arg_type=get_three_state_flag(),
            help="Flag when set, will show changes that will be made by the deployment "
            "if executed at the scope of the resource group.",
            arg_group="Template",
        )
        context.argument(
            "show_template",
            options_list=["--show-template"],
            arg_type=get_three_state_flag(),
            help="Flag when set, will output the generated template intended for deployment.",
            arg_group="Template",
        )
        context.argument(
            "show_pas_version",
            options_list=["--pas-version"],
            help="Summarize and show the versions of deployable components.",
            arg_type=get_three_state_flag(),
            arg_group="PAS Version",
        )
        context.argument(
            "custom_version",
            nargs="+",
            options_list=[context.deprecate(hide=True, target="--custom-version")],
            help="Customize PAS deployment by specifying edge service versions. Usage takes "
            "precedence over --aio-version. Use space-separated {key}={value} pairs where {key} "
            "is the edge service moniker and {value} is the desired version. The following monikers "
            f"may be used: {', '.join(EdgeServiceMoniker.list())}. Example: e4k=0.5.0 bluefin=0.3.0",
            arg_group="PAS Version",
            deprecate_info=context.deprecate(hide=True),
        )
        context.argument(
            "only_deploy_custom",
            options_list=[context.deprecate(hide=True, target="--only-custom")],
            arg_type=get_three_state_flag(),
            help="Only deploy the edge services specified in --custom-version.",
            arg_group="PAS Version",
            deprecate_info=context.deprecate(hide=True),
        )
        context.argument(
            "create_sync_rules",
            options_list=["--create-sync-rules"],
            arg_type=get_three_state_flag(),
            help="Create sync rules for arc-enabled extensions that support it.",
        )
        context.argument(
            "no_progress",
            options_list=["--no-progress"],
            arg_type=get_three_state_flag(),
            help="Disable deployment progress bar.",
        )
        context.argument(
            "no_block",
            options_list=["--no-block"],
            arg_type=get_three_state_flag(),
            help="Disable blocking until completion.",
        )
        # Akri
        context.argument(
            "opcua_discovery_endpoint",
            options_list=["--opcua-discovery-url"],
            help="Configures an OPC-UA server endpoint for Akri discovery handlers. If not provided "
            "and --simulate-plc is set, this value becomes "
            "'opc.tcp://opcplc-000000.{cluster_namespace}.svc.cluster.local:50000'.",
            arg_group="Akri",
        )
        # OPC-UA Broker
        context.argument(
            "simulate_plc",
            options_list=["--simulate-plc"],
            arg_type=get_three_state_flag(),
            help="Flag when set, will configure the OPC-UA broker installer to spin-up a PLC server.",
            arg_group="Opc-Ua Broker",
        )
        # Bluefin
        context.argument(
            "processor_instance_name",
            options_list=["--processor-instance"],
            help="Instance name for data processor. Used if data processor is part of the deployment. "
            "If no processor instance name is provided one will be generated in the form "
            "'{cluster_name}-azedge-init-proc'.",
            arg_group="Data Processor",
        )
        # Symphony
        context.argument(
            "target_name",
            options_list=["--target"],
            help="Target name for edge orchestrator. Used if symphony is part of the deployment. "
            "If no target name is provided one will be generated in the form "
            "'{cluster_name}-azedge-init-target'.",
            arg_group="Orchestration",
        )
