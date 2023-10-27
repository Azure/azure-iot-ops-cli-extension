# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from pathlib import PurePath
from typing import Any, Dict, List, Optional, Union

from knack.log import get_logger

from .providers.base import DEFAULT_NAMESPACE, load_config_context
from .providers.check.common import ResourceOutputDetailLevel
from .providers.support.base import get_bundle_path

logger = get_logger(__name__)


def support_bundle(
    cmd,
    log_age_seconds: int = 60 * 60 * 24,
    edge_service: str = "auto",
    bundle_dir: Optional[str] = None,
    context_name: Optional[str] = None,
) -> Union[Dict[str, Any], None]:
    load_config_context(context_name=context_name)
    from .providers.support_bundle import build_bundle

    bundle_path: PurePath = get_bundle_path(bundle_dir=bundle_dir)
    return build_bundle(edge_service=edge_service, bundle_path=str(bundle_path), log_age_seconds=log_age_seconds)


def check(
    cmd,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    pre_deployment_checks: Optional[bool] = None,
    post_deployment_checks: Optional[bool] = None,
    as_object=None,
    context_name=None,
    edge_service: str = "e4k",
    resource_kinds: List[str] = None,
) -> Union[Dict[str, Any], None]:
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
        as_list=not as_object,
        pre_deployment=run_pre,
        post_deployment=run_post,
        resource_kinds=resource_kinds,
    )


def init(
    cmd,
    cluster_name: str,
    resource_group_name: str,
    cluster_namespace: str = DEFAULT_NAMESPACE,
    keyvault_secret_name: str = DEFAULT_NAMESPACE,
    custom_location_namespace: Optional[str] = None,
    custom_location_name: Optional[str] = None,
    show_aio_version: Optional[bool] = None,
    location: Optional[str] = None,
    what_if: Optional[bool] = None,
    show_template: Optional[bool] = None,
    simulate_plc: Optional[bool] = None,
    opcua_discovery_endpoint: Optional[str] = None,
    no_block: Optional[bool] = None,
    no_progress: Optional[bool] = None,
    processor_instance_name: Optional[str] = None,
    target_name: Optional[str] = None,
    disable_secret_rotation: Optional[bool] = None,
    rotation_poll_interval: str = "1h",
    service_principal_app_id: Optional[str] = None,
    service_principal_object_id: Optional[str] = None,
    service_principal_secret: Optional[str] = None,
    keyvault_resource_id: Optional[str] = None,
    tls_ca_path: Optional[str] = None,
    tls_ca_key_path: Optional[str] = None,
    no_deploy: Optional[bool] = None,
    context_name: Optional[str] = None,
) -> Union[Dict[str, Any], None]:
    from azure.cli.core.commands.client_factory import get_subscription_id

    from .providers.orchestration import deploy
    from .util.sp import principal_is_app, sp_can_fetch_self

    load_config_context(context_name=context_name)

    if keyvault_resource_id:
        is_app, app_id = principal_is_app(cmd.cli_ctx)
        if (
            is_app
            and not sp_can_fetch_self(cmd.cli_ctx, app_id)
            and not all([service_principal_app_id, service_principal_object_id, service_principal_secret])
        ):
            logger.warning(
                "When logged in with a service principal, either ensure it's permissions "
                "to MS graph or provide values for --sp-app-id, --sp-object-id and --sp-secret."
            )

    # cluster namespace must be lowercase
    cluster_namespace = str(cluster_namespace).lower()

    cluster_name_lowered = cluster_name.lower()

    if not custom_location_name:
        custom_location_name = f"{cluster_name_lowered}-aziotops-init-cl"

    if not custom_location_namespace:
        custom_location_namespace = cluster_namespace

    if not processor_instance_name:
        processor_instance_name = f"{cluster_name_lowered}-aziotops-init-proc"
        processor_instance_name = processor_instance_name.replace("_", "-")

    if not target_name:
        target_name = f"{cluster_name_lowered}-aziotops-init-target"
        target_name = target_name.replace("_", "-")

    if simulate_plc and not opcua_discovery_endpoint:
        opcua_discovery_endpoint = f"opc.tcp://opcplc-000000.{cluster_namespace}:50000"

    # TODO: @digimaun
    # implement "has permission to graph check"
    # if keyvault_resource_id:
    #    ensure_access_to_graph()

    return deploy(
        cmd=cmd,
        subscription_id=get_subscription_id(cmd.cli_ctx),
        cluster_name=cluster_name,
        cluster_namespace=cluster_namespace,
        custom_location_name=custom_location_name,
        custom_location_namespace=custom_location_namespace,
        resource_group_name=resource_group_name,
        location=location,
        show_aio_version=show_aio_version,
        what_if=what_if,
        show_template=show_template,
        opcua_discovery_endpoint=opcua_discovery_endpoint,
        simulate_plc=simulate_plc,
        no_block=no_block,
        no_progress=no_progress,
        no_deploy=no_deploy,
        processor_instance_name=processor_instance_name,
        target_name=target_name,
        keyvault_resource_id=keyvault_resource_id,
        keyvault_secret_name=str(keyvault_secret_name),
        disable_secret_rotation=disable_secret_rotation,
        rotation_poll_interval=str(rotation_poll_interval),
        service_principal_app_id=service_principal_app_id,
        service_principal_object_id=service_principal_object_id,
        service_principal_secret=service_principal_secret,
        tls_ca_path=tls_ca_path,
        tls_ca_key_path=tls_ca_key_path,
    )
