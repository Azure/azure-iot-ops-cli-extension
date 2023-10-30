# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from os.path import exists
from pathlib import PurePath
from typing import Any, Dict, List, Optional, Union

from azure.cli.core.azclierror import InvalidArgumentValueError
from knack.log import get_logger

from .providers.base import DEFAULT_NAMESPACE, load_config_context
from .providers.check.common import ResourceOutputDetailLevel
from .providers.orchestration.common import MqMemoryProfile, MqMode, MqServiceType
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
    show_template: Optional[bool] = None,
    simulate_plc: Optional[bool] = None,
    opcua_discovery_endpoint: Optional[str] = None,
    no_block: Optional[bool] = None,
    no_progress: Optional[bool] = None,
    dp_instance_name: Optional[str] = None,
    dp_reader_workers: int = 1,
    dp_runner_workers: int = 1,
    dp_message_stores: int = 1,
    mq_mode: str = MqMode.distributed.value,
    mq_memory_profile: str = MqMemoryProfile.medium.value,
    mq_service_type: str = MqServiceType.cluster_ip.value,
    mq_backend_partitions: int = 2,
    mq_backend_workers: int = 2,
    mq_backend_redundancy_factor: int = 2,
    mq_frontend_workers: int = 2,
    mq_frontend_replicas: int = 2,
    mq_instance_name: Optional[str] = None,
    mq_listener_name: Optional[str] = None,
    mq_broker_name: Optional[str] = None,
    mq_authn_name: Optional[str] = None,
    target_name: Optional[str] = None,
    disable_secret_rotation: Optional[bool] = None,
    rotation_poll_interval: str = "1h",
    service_principal_app_id: Optional[str] = None,
    service_principal_object_id: Optional[str] = None,
    service_principal_secret: Optional[str] = None,
    keyvault_resource_id: Optional[str] = None,
    tls_ca_path: Optional[str] = None,
    tls_ca_key_path: Optional[str] = None,
    tls_ca_dir: Optional[str] = None,
    no_deploy: Optional[bool] = None,
    no_tls: Optional[bool] = None,
    context_name: Optional[str] = None,
) -> Union[Dict[str, Any], None]:
    from .providers.orchestration import deploy
    from .util import url_safe_hash_phrase
    from .util.sp import LoggedInPrincipal

    if all([no_tls, not keyvault_resource_id, no_deploy]):
        logger.warning("Nothing to do :)")
        return

    load_config_context(context_name=context_name)

    if keyvault_resource_id and not any([show_aio_version, show_template]):
        logged_in_principal = LoggedInPrincipal(cmd=cmd)
        if logged_in_principal.is_app():
            app_principal = logged_in_principal.fetch_self_if_app()
            if not app_principal and not all(
                [service_principal_app_id, service_principal_object_id, service_principal_secret]
            ):
                logger.warning(
                    "When logged in with a service principal, either ensure it's permissions "
                    "to MS graph or provide values for --sp-app-id, --sp-object-id and --sp-secret."
                )

    # cluster namespace must be lowercase
    cluster_namespace = str(cluster_namespace).lower()
    cluster_name_lowered = cluster_name.lower()

    hashed_cluster_slug = url_safe_hash_phrase(cluster_name)[:5]
    if not mq_instance_name:
        mq_instance_name = f"init-{hashed_cluster_slug}-mq-instance"
    if not mq_listener_name:
        mq_listener_name = "listener"
    if not mq_broker_name:
        mq_broker_name = "broker"
    if not mq_authn_name:
        mq_authn_name = "authn"

    if not custom_location_name:
        custom_location_name = f"{cluster_name_lowered}-aio-init-cl"

    if not custom_location_namespace:
        custom_location_namespace = cluster_namespace

    if not dp_instance_name:
        dp_instance_name = f"{cluster_name_lowered}-aio-init-processor"
        dp_instance_name = dp_instance_name.replace("_", "-")

    if not target_name:
        target_name = f"{cluster_name_lowered}-aio-init-target"
        target_name = target_name.replace("_", "-")

    if simulate_plc and not opcua_discovery_endpoint:
        opcua_discovery_endpoint = f"opc.tcp://opcplc-000000.{cluster_namespace}:50000"

    if tls_ca_path:
        if not tls_ca_key_path:
            raise InvalidArgumentValueError("When using --ca-file, --ca-key-file is required.")

        if not exists(tls_ca_path):
            raise InvalidArgumentValueError("Provided CA file does not exist.")

        if not exists(tls_ca_key_path):
            raise InvalidArgumentValueError("Provided CA private key file does not exist.")

    return deploy(
        cmd=cmd,
        cluster_name=cluster_name,
        cluster_namespace=cluster_namespace,
        custom_location_name=custom_location_name,
        custom_location_namespace=custom_location_namespace,
        resource_group_name=resource_group_name,
        location=location,
        show_aio_version=show_aio_version,
        show_template=show_template,
        opcua_discovery_endpoint=opcua_discovery_endpoint,
        simulate_plc=simulate_plc,
        no_block=no_block,
        no_progress=no_progress,
        no_tls=no_tls,
        no_deploy=no_deploy,
        dp_instance_name=dp_instance_name,
        dp_reader_workers=int(dp_reader_workers),
        dp_runner_workers=int(dp_runner_workers),
        dp_message_stores=int(dp_message_stores),
        mq_mode=str(mq_mode),
        mq_memory_profile=str(mq_memory_profile),
        mq_service_type=str(mq_service_type),
        mq_backend_partitions=int(mq_backend_partitions),
        mq_backend_workers=int(mq_backend_workers),
        mq_backend_redundancy_factor=int(mq_backend_redundancy_factor),
        mq_frontend_replicas=int(mq_frontend_replicas),
        mq_frontend_workers=int(mq_frontend_workers),
        mq_instance_name=mq_instance_name,
        mq_listener_name=mq_listener_name,
        mq_broker_name=mq_broker_name,
        mq_authn_name=mq_authn_name,
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
        tls_ca_dir=tls_ca_dir,
    )
