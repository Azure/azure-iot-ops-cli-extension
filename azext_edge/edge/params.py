# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

"""
CLI parameter definitions.
"""

from knack.arguments import CaseInsensitiveList
from azure.cli.core.commands.parameters import get_three_state_flag, tags_type
from .common import SupportForEdgeServiceType


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

    with self.argument_context("edge asset") as context:
        context.argument(
            "asset_name",
            options_list=["--asset-name", "-n"],
            help="Asset name.",
        )
        context.argument(
            "endpoint_profile",
            options_list=["--endpoint-profile", "--ep"],
            help="Endpoint profile.",
        )
        context.argument(
            "custom_location",
            options_list=["--custom-location", "--cl"],
            help="Custom location used to associate asset with cluster.",
        )
        context.argument(
            "custom_location_resource_group",
            options_list=["--custom-location-resource-group", "--clrg"],
            help="Resource group for custom location. If not provided, asset resource group will be used.",
        )
        context.argument(
            "custom_location_subscription",
            options_list=["--custom-location-subscription", "--cls"],
            help="Subscription Id for custom location. If not provided, asset subscription Id will be used.",
        )
        context.argument(
            "asset_type",
            options_list=["--asset-type", "--at"],
            help="Asset type.",
            arg_group="Additional Info",
        )
        context.argument(
            "data_points",
            options_list=["--data-point", "--dp"],
            nargs="+",
            action="append",
            help="Space-separated key=value pairs corresponding to properties of the data point to create. "
            "The following key values are supported: `capability_id`, `data_point_configuration`, `data_source` (required), `name`, `observability_mode` (none, gauge, counter, histogram, or log), `sampling_interval` (int), `queue_size` (int) "
            "--data-point can be used 1 or more times. Review help examples for full parameter usage",
            arg_group="Additional Info",
        )
        context.argument(
            "description",
            options_list=["--description", "-d"],
            help="Description.",
            arg_group="Additional Info",
        )
        context.argument(
            "documentation_uri",
            options_list=["--documentation-uri", "--du"],
            help="Documentation URI.",
            arg_group="Additional Info",
        )
        context.argument(
            "events",
            options_list=["--event", "-e"],
            nargs="+",
            action="append",
            help="Space-separated key=value pairs corresponding to properties of the event to create. "
            "The following key values are supported: `capability_id`, `data_point_configuration`, `event_notifier` (required), `name`, `observability_mode` (none, gauge, counter, histogram, or log), `sampling_interval` (int), `queue_size` (int) "
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
            options_list=["--data-point-publishing-interval", "--dppi"],
            help="Default publishing interval for data points.",
            arg_group="Data Point Default",
        )
        context.argument(
            "dp_sampling_interval",
            options_list=["--data-point-sampling-interval", "--dpsi"],
            help="Default sampling interval for data points.",
            arg_group="Data Point Default",
        )
        context.argument(
            "dp_queue_size",
            options_list=["--data-point-queue-size", "--dpqs"],
            help="Default queue size for data points.",
            arg_group="Data Point Default",
        )
        context.argument(
            "ev_publishing_interval",
            options_list=["--event-publishing-interval", "--epi"],
            help="Default publishing interval for events.",
            arg_group="Event Default",
        )
        context.argument(
            "ev_sampling_interval",
            options_list=["--event-sampling-interval", "--esi"],
            help="Default sampling interval for events.",
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
            help="Asset tags.",
            arg_type=tags_type,
        )
