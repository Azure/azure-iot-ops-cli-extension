# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

"""
CLI parameter definitions.
"""

from knack.arguments import CaseInsensitiveList
from azure.cli.core.commands.parameters import get_three_state_flag
from .common import SupportForEdgeServiceType, AkriK8sDistroType, DeployableAioVersions
from .providers.orchestration.aio_versions import EdgeServiceMoniker


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
            "If no namespace is provided `default` will be used.",
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
            help="Run only pre-requisite checks to determine if the minimum "
            "requirements of an edge service deployment are fulfilled.",
            arg_type=get_three_state_flag(),
        )
        context.argument(
            "post_deployment_checks",
            options_list=["--post"],
            help="Run only post-deployment checks.",
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
            choices=CaseInsensitiveList(["e4k"]),
            help="The edge service deployment that will be evaluated.",
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
            help="The diagnostic service pod prefix. The first pod fulfilling the condition " "will be connected to.",
            arg_group="Pod",
        )
        context.argument(
            "pod_port", type=int, options_list=["--port"], help="The pod port to connect through.", arg_group="Pod"
        )
        context.argument(
            "raw_response_print",
            options_list=["--raw"],
            arg_type=get_three_state_flag(),
            help="Return raw output from the metrics API.",
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
            help="The custom location name corresponding to the PAS deployment.",
        )
        context.argument(
            "cluster_namespace",
            options_list=["--cluster-namespace"],
            help="The cluster namespace PAS resources will be deployed to.",
        )
        context.argument(
            "location",
            options_list=["--location"],
            help="The location that will be used for provisioned collateral. "
            "If not provided the resource group location will be used.",
        )
        context.argument(
            "what_if",
            options_list=["--what-if"],
            arg_type=get_three_state_flag(),
            help="Flag when set, will show changes that will be made by the deployment "
            "if executed at the scope of the resource group.",
            arg_group="Template"
        )
        context.argument(
            "show_template",
            options_list=["--show-template"],
            arg_type=get_three_state_flag(),
            help="Flag when set, will output the generated template intended for deployment.",
            arg_group="Template"
        )
        context.argument(
            "aio_version",
            options_list=["--aio-version"],
            help="The AIO bundle version to deploy.",
            choices=CaseInsensitiveList(DeployableAioVersions.list()),
            arg_group="AIO Version",
        )
        context.argument(
            "detail_aio_version",
            options_list=["--detail-version"],
            help="Summarize and show the versions of deployable components.",
            arg_type=get_three_state_flag(),
            arg_group="AIO Version",
        )
        context.argument(
            "custom_version",
            nargs="+",
            options_list=["--custom-version"],
            help="Customize AIO deployment by specifying edge service versions. Usage takes precedence over --aio-version. "
            "Use space-separated {key}={value} pairs where {key} is the edge service moniker and {value} "
            f"is the desired version. The following monikers may be used: {', '.join(EdgeServiceMoniker.list())}. "
            "Example: e4k=0.5.0 bluefin=0.3.0",
            arg_group="AIO Version",
        )
        context.argument(
            "only_deploy_custom",
            options_list=["--only-custom"],
            arg_type=get_three_state_flag(),
            help="Only deploy the edge services specified in --custom-version.",
            arg_group="AIO Version",
        )
        context.argument(
            "create_sync_rules",
            options_list=["--create-sync-rules"],
            arg_type=get_three_state_flag(),
            help="Create sync rules for arc-enabled extensions.",
        )
        context.argument(
            "no_progress",
            options_list=["--no-progress"],
            arg_type=get_three_state_flag(),
            help="Disable deployment progress bar.",
        )
        context.argument(
            "no_wait",
            options_list=["--no-wait"],
            help="Do not block.",
        )
        # Akri
        context.argument(
            "opcua_discovery_endpoint",
            options_list=["--opcua-discovery-url"],
            help="Configures an OPC-UA server endpoint for Akri discovery handlers.",
            arg_group="Akri",
        )
        context.argument(
            "kubernetes_distro",
            options_list=["--kubernetes-distro"],
            help="Optimizes the Akri deployment for a particular Kubernetes distribution.",
            choices=CaseInsensitiveList(AkriK8sDistroType.list()),
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
            "instance_name",
            options_list=["--processor-instance"],
            arg_type=get_three_state_flag(),
            help="Disable deployment progress bar.",
            arg_group="Data Processor",
        )