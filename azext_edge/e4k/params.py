# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
CLI parameter definitions.
"""

from knack.arguments import CLIArgumentType
from azure.cli.core.commands.parameters import (
    resource_group_name_type,
    get_three_state_flag,
    get_enum_type,
    tags_type,
)


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
            "bundle_dir",
            options_list=["--bundle-dir"],
            help="The local directory the produced bundle will be saved to. "
            "If no directory is provided the current directory is used.",
        )

    with self.argument_context("edge e4k check") as context:
        context.argument(
            "pre_deployment_checks",
            options_list=["--pre-deployment"],
            help="Run only pre-requisite checks such as Kubernetes, Helm version, "
            "memory requirements etc, are satisfied before attempting to install E4K.",
            arg_type=get_three_state_flag(),
        )
        context.argument(
            "post_deployment_checks",
            options_list=["--post-deployment"],
            help="Run only post deployment checks to measure E4K system key health attributes.",
            arg_type=get_three_state_flag(),
        )
        context.argument(
            "as_list",
            options_list=["--list"],
            help="Output check content and validations in a human optimized list format.",
            arg_type=get_three_state_flag(),
        )

    with self.argument_context("edge e4k config") as context:
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
            help="Number of seconds between a stats refresh.",
            type=int,
        )
        context.argument(
            "watch",
            options_list=["--watch"],
            help="The operation blocks and dynamically updates a stats table.",
            arg_type=get_three_state_flag(),
        )

    with self.argument_context("edge e4k support") as context:
        context.argument(
            "namespaces",
            nargs="+",
            options_list=["--namespaces"],
            help="Space-separated namespaces in addition to `kube-system` from which to fetch key performance indicators. "
            "If no namespaces are provided the namespace `default` will be used.",
        )

    with self.argument_context("edge opcua") as context:
        context.argument(
            "log_age_seconds",
            options_list=["--log-age"],
            help="Container log age in seconds.",
            type=int,
        )
