# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from pathlib import PurePath
from typing import Optional, Union, List

from knack.log import get_logger

from .providers.base import load_config_context
from .providers.support.base import get_bundle_path
from .common import DeployablePasVersions
from .providers.check.common import ResourceOutputDetailLevel

logger = get_logger(__name__)


def support_bundle(
    cmd,
    log_age_seconds: int = 60 * 60 * 24,
    edge_service: str = "auto",
    bundle_dir: Optional[str] = None,
    context_name: Optional[str] = None,
) -> dict:
    load_config_context(context_name=context_name)
    from .providers.support_bundle import build_bundle

    bundle_path: PurePath = get_bundle_path(bundle_dir=bundle_dir)
    return build_bundle(edge_service=edge_service, bundle_path=str(bundle_path), log_age_seconds=log_age_seconds)


def check(
    cmd,
    detail_level: Optional[int] = ResourceOutputDetailLevel.summary.value,
    pre_deployment_checks: Optional[bool] = None,
    post_deployment_checks: Optional[bool] = None,
    namespace: Optional[str] = None,
    as_object=None,
    context_name=None,
    edge_service: str = "e4k",
    resource_kinds: List[str] = None,
) -> Union[dict, None]:
    load_config_context(context_name=context_name)
    from .providers.checks import run_checks

    run_pre = True
    run_post = True
    if pre_deployment_checks and not post_deployment_checks:
        run_post = False
    if post_deployment_checks and not pre_deployment_checks:
        run_pre = False

    return run_checks(
        edge_service=edge_service,
        detail_level=detail_level,
        namespace=namespace,
        as_list=not as_object,
        pre_deployment=run_pre,
        post_deployment=run_post,
        resource_kinds=resource_kinds,
    )


def init(
    cmd,
    cluster_name: str,
    resource_group_name: str,
    cluster_namespace: str = "default",
    custom_location_namespace: Optional[str] = None,
    pas_version: str = DeployablePasVersions.v012.value,
    custom_location_name: Optional[str] = None,
    show_pas_version: Optional[bool] = None,
    custom_version: Optional[List[str]] = None,
    only_deploy_custom: Optional[bool] = None,
    location: Optional[str] = None,
    what_if: Optional[bool] = None,
    show_template: Optional[bool] = None,
    simulate_plc: Optional[bool] = None,
    opcua_discovery_endpoint: Optional[str] = None,
    create_sync_rules: Optional[bool] = None,
    block: Union[bool, str] = "true",
    no_progress: Optional[bool] = None,
    processor_instance_name: Optional[str] = None,
    target_name: Optional[str] = None,
) -> Union[dict, None]:
    from azure.cli.core.commands.client_factory import get_subscription_id
    from .providers.orchestration import deploy

    # cluster namespace must be lowercase
    cluster_namespace = cluster_namespace.lower()

    cluster_name_lowered = cluster_name.lower()

    if not custom_location_name:
        custom_location_name = f"{cluster_name_lowered}-azedge-init"

    if not custom_location_namespace:
        custom_location_namespace = cluster_namespace

    if not processor_instance_name:
        processor_instance_name = f"{cluster_name_lowered}-azedge-init-proc"
        processor_instance_name = processor_instance_name.replace("_", "-")

    if not target_name:
        target_name = f"{cluster_name_lowered}-azedge-init-target"

    if simulate_plc and not opcua_discovery_endpoint:
        opcua_discovery_endpoint = f"opc.tcp://opcplc-000000.{cluster_namespace}.svc.cluster.local:50000"

    return deploy(
        subscription_id=get_subscription_id(cmd.cli_ctx),
        cluster_name=cluster_name,
        cluster_namespace=cluster_namespace,
        custom_location_name=custom_location_name,
        custom_location_namespace=custom_location_namespace,
        resource_group_name=resource_group_name,
        pas_version=pas_version,
        location=location,
        show_pas_version=show_pas_version,
        custom_version=custom_version,
        only_deploy_custom=only_deploy_custom,
        what_if=what_if,
        show_template=show_template,
        opcua_discovery_endpoint=opcua_discovery_endpoint,
        simulate_plc=simulate_plc,
        create_sync_rules=create_sync_rules,
        block=block,
        no_progress=no_progress,
        processor_instance_name=processor_instance_name,
        target_name=target_name,
    )
