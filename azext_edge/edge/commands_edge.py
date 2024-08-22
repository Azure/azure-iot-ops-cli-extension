# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from pathlib import PurePath
from typing import Any, Dict, Iterable, List, Optional, Union

from knack.log import get_logger

from .common import OpsServiceType
from .providers.base import DEFAULT_NAMESPACE, load_config_context
from .providers.check.common import ResourceOutputDetailLevel
from .providers.edge_api.orc import ORC_API_V1
from .providers.orchestration.common import (
    KubernetesDistroType,
    MqMemoryProfile,
    MqServiceType,
)
from .providers.orchestration.resources import Instances
from .providers.support.base import get_bundle_path

logger = get_logger(__name__)


def support_bundle(
    cmd,
    log_age_seconds: int = 60 * 60 * 24,
    ops_service: str = OpsServiceType.auto.value,
    bundle_dir: Optional[str] = None,
    include_mq_traces: Optional[bool] = None,
    context_name: Optional[str] = None,
) -> Union[Dict[str, Any], None]:
    load_config_context(context_name=context_name)
    from .providers.support_bundle import build_bundle

    bundle_path: PurePath = get_bundle_path(bundle_dir=bundle_dir)
    return build_bundle(
        ops_service=ops_service,
        bundle_path=str(bundle_path),
        log_age_seconds=log_age_seconds,
        include_mq_traces=include_mq_traces,
    )


def check(
    cmd,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    pre_deployment_checks: Optional[bool] = None,
    post_deployment_checks: Optional[bool] = None,
    as_object=None,
    context_name=None,
    ops_service: str = OpsServiceType.mq.value,
    resource_kinds: List[str] = None,
    resource_name: str = None,
) -> Union[Dict[str, Any], None]:
    load_config_context(context_name=context_name)
    from .providers.checks import run_checks

    # by default - run prechecks if AIO is not deployed
    run_pre = not ORC_API_V1.is_deployed() if pre_deployment_checks is None else pre_deployment_checks
    run_post = True if post_deployment_checks is None else post_deployment_checks

    # only one of pre or post is explicity set to True
    if pre_deployment_checks and not post_deployment_checks:
        run_post = False
    if post_deployment_checks and not pre_deployment_checks:
        run_pre = False

    return run_checks(
        ops_service=ops_service,
        detail_level=detail_level,
        as_list=not as_object,
        resource_name=resource_name,
        pre_deployment=run_pre,
        post_deployment=run_post,
        resource_kinds=resource_kinds,
    )


def verify_host(
    cmd,
    no_progress: Optional[bool] = None,
):
    from .providers.orchestration import run_host_verify

    run_host_verify(render_progress=not no_progress)
    return


def init(
    cmd,
    cluster_name: str,
    resource_group_name: str,
    instance_name: Optional[str] = None,
    instance_description: Optional[str] = None,
    cluster_namespace: str = DEFAULT_NAMESPACE,
    custom_location_name: Optional[str] = None,
    location: Optional[str] = None,
    container_runtime_socket: Optional[str] = None,
    kubernetes_distro: str = KubernetesDistroType.k8s.value,
    no_block: Optional[bool] = None,
    no_progress: Optional[bool] = None,
    mq_memory_profile: str = MqMemoryProfile.medium.value,
    mq_service_type: str = MqServiceType.cluster_ip.value,
    mq_backend_partitions: int = 2,
    mq_backend_workers: int = 2,
    mq_backend_redundancy_factor: int = 2,
    mq_frontend_workers: int = 2,
    mq_frontend_replicas: int = 2,
    mq_frontend_server_name: str = "mq-dmqtt-frontend",
    mq_listener_name: str = "listener",
    mq_broker_name: str = "broker",
    mq_authn_name: str = "authn",
    mq_broker_config_file: Optional[str] = None,
    add_insecure_listener: Optional[bool] = None,
    dataflow_profile_instances: int = 1,
    # TODO - @digimaun csi_driver_config: Optional[List[str]] = None,
    keyvault_resource_id: Optional[str] = None,  # TODO - @digimaun
    template_path: Optional[str] = None,
    no_deploy: Optional[bool] = None,
    disable_rsync_rules: Optional[bool] = None,
    context_name: Optional[str] = None,
    ensure_latest: Optional[bool] = None,
    **kwargs,
) -> Union[Dict[str, Any], None]:
    from .common import INIT_NO_PREFLIGHT_ENV_KEY
    from .providers.orchestration import WorkManager
    from .util import (
        # assemble_nargs_to_dict,
        is_env_flag_enabled,
        read_file_content,
        url_safe_random_chars,
    )
    # TODO - @digimaun
    load_config_context(context_name=context_name)
    no_pre_flight = is_env_flag_enabled(INIT_NO_PREFLIGHT_ENV_KEY)

    # cluster namespace must be lowercase
    cluster_namespace = str(cluster_namespace).lower()
    cluster_name_lowered = cluster_name.lower()
    # TODO - @digimaun
    safe_cluster_name = cluster_name_lowered.replace("_", "-")

    if not instance_name:
        instance_name = f"{safe_cluster_name}-ops-instance"

    if not custom_location_name:
        custom_location_name = f"{cluster_name_lowered}-{url_safe_random_chars(3).lower()}-ops-cl"

    # TODO - @digimaun
    mq_broker_config = None
    if mq_broker_config_file:
        mq_broker_config = json.loads(read_file_content(file_path=mq_broker_config_file))

    work_manager = WorkManager(cmd)
    return work_manager.execute_ops_init(
        show_progress=not no_progress,
        block=not no_block,
        pre_flight= not no_pre_flight,
        cluster_name=cluster_name,
        resource_group_name=resource_group_name,
        location=location,
        cluster_namespace=cluster_namespace,
        instance_name=instance_name,
        instance_description=instance_description,
        custom_location_name=custom_location_name,
        disable_rsync_rules=disable_rsync_rules,
        container_runtime_socket=container_runtime_socket,
        kubernetes_distro=str(kubernetes_distro),
        dataflow_profile_instances=int(dataflow_profile_instances),
        add_insecure_listener=add_insecure_listener,
        mq_broker_name=str(mq_broker_name),
        mq_broker_config=mq_broker_config,
    )

    # TODO - @digimaun
    # work_manager = WorkManager(
    #     mq_memory_profile=str(mq_memory_profile),
    #     mq_service_type=str(mq_service_type),
    #     mq_backend_partitions=int(mq_backend_partitions),
    #     mq_backend_workers=int(mq_backend_workers),
    #     mq_backend_redundancy_factor=int(mq_backend_redundancy_factor),
    #     mq_frontend_replicas=int(mq_frontend_replicas),
    #     mq_frontend_workers=int(mq_frontend_workers),
    #     mq_frontend_server_name=str(mq_frontend_server_name),
    #     mq_listener_name=str(mq_listener_name),
    #     mq_authn_name=str(mq_authn_name),
    #     keyvault_resource_id=keyvault_resource_id,
    #     template_path=template_path,
    #     **kwargs,
    # )


def delete(
    cmd,
    cluster_name: str,
    resource_group_name: str,
    confirm_yes: Optional[bool] = None,
    no_progress: Optional[bool] = None,
    force: Optional[bool] = None,
):
    from .providers.orchestration import delete_ops_resources

    return delete_ops_resources(
        cmd=cmd,
        cluster_name=cluster_name,
        resource_group_name=resource_group_name,
        confirm_yes=confirm_yes,
        no_progress=no_progress,
        force=force,
    )


def show_instance(cmd, instance_name: str, resource_group_name: str, show_tree: Optional[bool] = None) -> dict:
    return Instances(cmd).show(name=instance_name, resource_group_name=resource_group_name, show_tree=show_tree)


def list_instances(cmd, resource_group_name: Optional[str] = None) -> Iterable[dict]:
    return Instances(cmd).list(resource_group_name)


def update_instance(
    cmd,
    instance_name: str,
    resource_group_name: str,
    tags: Optional[str] = None,
    instance_description: Optional[str] = None,
    **kwargs,
) -> dict:
    return Instances(cmd).update(
        name=instance_name,
        resource_group_name=resource_group_name,
        tags=tags,
        description=instance_description,
        **kwargs,
    )
