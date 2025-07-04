# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from pathlib import PurePath
from typing import Any, Dict, Iterable, List, Optional, Union

from azure.cli.core.azclierror import ArgumentUsageError
from knack.log import get_logger

from .providers.base import DEFAULT_NAMESPACE, load_config_context
from .providers.check.common import ResourceOutputDetailLevel
from .providers.edge_api import META_API_V1
from .providers.orchestration.common import (
    IdentityUsageType,
    KubernetesDistroType,
    MqMemoryProfile,
)
from .providers.orchestration.resources import Instances
from .providers.support.base import get_bundle_path


logger = get_logger(__name__)


def support_bundle(
    cmd,
    log_age_seconds: int = 60 * 60 * 24,
    bundle_dir: Optional[str] = None,
    include_mq_traces: Optional[bool] = None,
    context_name: Optional[str] = None,
    ops_services: Optional[List[str]] = None,
    bundle_name: Optional[str] = None,
) -> Union[Dict[str, Any], None]:
    load_config_context(context_name=context_name)
    from .providers.support_bundle import build_bundle

    bundle_path: PurePath = get_bundle_path(bundle_dir=bundle_dir, bundle_name=bundle_name)
    return build_bundle(
        ops_services=ops_services,
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
    ops_service: Optional[str] = None,
    resource_kinds: List[str] = None,
    resource_name: str = None,
) -> Union[Dict[str, Any], None]:
    load_config_context(context_name=context_name)
    from .providers.checks import run_checks

    aio_deployed = META_API_V1.is_deployed()
    # by default - run prechecks if AIO is not deployed, otherwise use argument
    run_pre = not aio_deployed if pre_deployment_checks is None else pre_deployment_checks
    # by default - run postchecks if AIO is deployed, otherwise use argument
    run_post = aio_deployed if post_deployment_checks is None else post_deployment_checks

    # only one of pre or post is explicity set to True
    if pre_deployment_checks and not post_deployment_checks:
        run_post = False
    if post_deployment_checks and not pre_deployment_checks:
        run_pre = False

    # error if resource_name provided without ops_service
    if resource_name and not ops_service:
        raise ArgumentUsageError(
            "Resource name filtering (--resource-name) can only be used with service name (--svc)."
        )

    if resource_kinds and not ops_service:
        raise ArgumentUsageError("Service name (--svc) is required to specify individual resource kind checks.")

    if detail_level != ResourceOutputDetailLevel.summary.value and not ops_service:
        logger.warning("Detail level (--detail-level) will only affect individual service checks with '--svc'")

    return run_checks(
        ops_service=ops_service,
        detail_level=detail_level,
        as_list=not as_object,
        resource_name=resource_name,
        pre_deployment=run_pre,
        post_deployment=run_post,
        resource_kinds=resource_kinds,
    )


def init(
    cmd,
    cluster_name: str,
    resource_group_name: str,
    context_name: Optional[str] = None,
    enable_fault_tolerance: Optional[bool] = None,
    check_cluster: Optional[bool] = None,
    no_progress: Optional[bool] = None,
    ensure_latest: Optional[bool] = None,
    user_trust: Optional[bool] = None,
    acs_config: Optional[List[str]] = None,
    acs_version: Optional[str] = None,
    acs_train: Optional[str] = None,
    ssc_config: Optional[List[str]] = None,
    ssc_version: Optional[str] = None,
    ssc_train: Optional[str] = None,
    **kwargs,
) -> Union[Dict[str, Any], None]:
    from .common import INIT_NO_PREFLIGHT_ENV_KEY
    from .providers.orchestration.work import WorkManager
    from .util import (
        is_env_flag_enabled,
    )

    no_pre_flight = is_env_flag_enabled(INIT_NO_PREFLIGHT_ENV_KEY)

    work_manager = WorkManager(cmd)
    result_payload = work_manager.execute_ops_init(
        show_progress=not no_progress,
        pre_flight=not no_pre_flight,
        cluster_name=cluster_name,
        context_name=context_name,
        resource_group_name=resource_group_name,
        enable_fault_tolerance=enable_fault_tolerance,
        check_cluster=check_cluster,
        user_trust=user_trust,
        acs_config=acs_config,
        acs_version=acs_version,
        acs_train=acs_train,
        ssc_config=ssc_config,
        ssc_version=ssc_version,
        ssc_train=ssc_train,
        **kwargs,
    )
    if no_progress and result_payload:
        # @digimaun - TODO
        pass


def create_instance(
    cmd,
    cluster_name: str,
    resource_group_name: str,
    instance_name: str,
    schema_registry_resource_id: str,
    adr_namespace_resource_id: str,
    cluster_namespace: str = DEFAULT_NAMESPACE,
    location: Optional[str] = None,
    custom_location_name: Optional[str] = None,
    enable_rsync_rules: Optional[bool] = None,
    instance_description: Optional[str] = None,
    instance_features: Optional[List[str]] = None,
    dataflow_profile_instances: int = 1,
    trust_settings: Optional[List[str]] = None,
    # Akri [Deprecated]
    container_runtime_socket: Optional[str] = None,
    kubernetes_distro: str = KubernetesDistroType.k8s.value,
    # Ops Extension
    ops_config: Optional[List[str]] = None,
    ops_version: Optional[str] = None,
    ops_train: Optional[str] = None,
    # Broker
    custom_broker_config_file: Optional[str] = None,
    broker_memory_profile: str = MqMemoryProfile.medium.value,
    broker_backend_partitions: int = 2,
    broker_backend_workers: int = 2,
    broker_backend_redundancy_factor: int = 2,
    broker_frontend_workers: int = 2,
    broker_frontend_replicas: int = 2,
    add_insecure_listener: Optional[bool] = None,
    tags: Optional[dict] = None,
    no_progress: Optional[bool] = None,
    **kwargs,
) -> Union[Dict[str, Any], None]:
    from .common import INIT_NO_PREFLIGHT_ENV_KEY
    from .providers.orchestration.work import WorkManager
    from .util import (
        is_env_flag_enabled,
        read_file_content,
    )

    no_pre_flight = is_env_flag_enabled(INIT_NO_PREFLIGHT_ENV_KEY)

    _ = container_runtime_socket
    _ = kubernetes_distro

    # TODO - @digimaun
    custom_broker_config = None
    if custom_broker_config_file:
        custom_broker_config = json.loads(read_file_content(file_path=custom_broker_config_file))

    work_manager = WorkManager(cmd)
    result_payload = work_manager.execute_ops_init(
        show_progress=not no_progress,
        pre_flight=not no_pre_flight,
        apply_foundation=False,
        cluster_name=cluster_name,
        resource_group_name=resource_group_name,
        cluster_namespace=cluster_namespace,
        schema_registry_resource_id=schema_registry_resource_id,
        adr_namespace_resource_id=adr_namespace_resource_id,
        location=location,
        custom_location_name=custom_location_name,
        enable_rsync_rules=enable_rsync_rules,
        instance_name=instance_name,
        instance_description=instance_description,
        instance_features=instance_features,
        add_insecure_listener=add_insecure_listener,
        dataflow_profile_instances=dataflow_profile_instances,
        trust_settings=trust_settings,
        # Ops extension
        ops_config=ops_config,
        ops_version=ops_version,
        ops_train=ops_train,
        # Broker
        custom_broker_config=custom_broker_config,
        broker_memory_profile=broker_memory_profile,
        broker_backend_partitions=broker_backend_partitions,
        broker_backend_workers=broker_backend_workers,
        broker_backend_redundancy_factor=broker_backend_redundancy_factor,
        broker_frontend_workers=broker_frontend_workers,
        broker_frontend_replicas=broker_frontend_replicas,
        tags=tags,
        **kwargs,
    )
    if no_progress and result_payload:
        # @digimaun - TODO
        pass


# The extra-ordinary number of explicit params are due to how Azure CLI handles params/args.
# Potentially this can be simplified by some Knack hacking.
def upgrade_instance(
    cmd,
    resource_group_name: str,
    instance_name: str,
    no_progress: Optional[bool] = None,
    confirm_yes: Optional[bool] = None,
    ops_config: Optional[List[str]] = None,
    ops_config_sync_mode: Optional[str] = None,
    ops_version: Optional[str] = None,
    ops_train: Optional[str] = None,
    acs_config: Optional[List[str]] = None,
    acs_config_sync_mode: Optional[str] = None,
    acs_version: Optional[str] = None,
    acs_train: Optional[str] = None,
    ssc_config: Optional[List[str]] = None,
    ssc_version: Optional[str] = None,
    ssc_train: Optional[str] = None,
    ssc_config_sync_mode: Optional[str] = None,
    plat_config: Optional[List[str]] = None,
    plat_version: Optional[str] = None,
    plat_train: Optional[str] = None,
    plat_config_sync_mode: Optional[str] = None,
    force: Optional[bool] = None,
    **kwargs,
) -> Optional[List[dict]]:
    from .providers.orchestration.upgrade2 import upgrade_ops_instance

    return upgrade_ops_instance(
        cmd=cmd,
        resource_group_name=resource_group_name,
        instance_name=instance_name,
        no_progress=no_progress,
        confirm_yes=confirm_yes,
        ops_config=ops_config,
        ops_version=ops_version,
        ops_train=ops_train,
        ops_config_sync_mode=ops_config_sync_mode,
        acs_config=acs_config,
        acs_version=acs_version,
        acs_train=acs_train,
        acs_config_sync_mode=acs_config_sync_mode,
        ssc_config=ssc_config,
        ssc_version=ssc_version,
        ssc_train=ssc_train,
        ssc_config_sync_mode=ssc_config_sync_mode,
        plat_config=plat_config,
        plat_version=plat_version,
        plat_train=plat_train,
        plat_config_sync_mode=plat_config_sync_mode,
        force=force,
        **kwargs,
    )


def delete(
    cmd,
    resource_group_name: str,
    instance_name: Optional[str] = None,
    cluster_name: Optional[str] = None,
    confirm_yes: Optional[bool] = None,
    no_progress: Optional[bool] = None,
    force: Optional[bool] = None,
    include_dependencies: Optional[bool] = None,
):
    from .providers.orchestration.deletion import delete_ops_resources

    return delete_ops_resources(
        cmd=cmd,
        instance_name=instance_name,
        cluster_name=cluster_name,
        resource_group_name=resource_group_name,
        confirm_yes=confirm_yes,
        no_progress=no_progress,
        force=force,
        include_dependencies=include_dependencies,
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
    instance_features: Optional[List[str]] = None,
    **kwargs,
) -> dict:
    return Instances(cmd).update(
        name=instance_name,
        resource_group_name=resource_group_name,
        tags=tags,
        description=instance_description,
        features=instance_features,
        **kwargs,
    )


def instance_identity_assign(
    cmd,
    instance_name: str,
    resource_group_name: str,
    mi_user_assigned: str,
    federated_credential_name: Optional[str] = None,
    usage_type: str = IdentityUsageType.DATAFLOW.value,
    use_self_hosted_issuer: Optional[bool] = None,
    **kwargs,
) -> dict:
    return Instances(cmd).add_mi_user_assigned(
        name=instance_name,
        resource_group_name=resource_group_name,
        mi_user_assigned=mi_user_assigned,
        federated_credential_name=federated_credential_name,
        use_self_hosted_issuer=use_self_hosted_issuer,
        usage_type=usage_type,
        **kwargs,
    )


def instance_identity_show(cmd, instance_name: str, resource_group_name: str) -> dict:
    instance = Instances(cmd).show(
        name=instance_name,
        resource_group_name=resource_group_name,
    )
    return instance.get("identity", {})


def instance_identity_remove(
    cmd,
    instance_name: str,
    resource_group_name: str,
    mi_user_assigned: str,
    federated_credential_name: Optional[str] = None,
    **kwargs,
) -> dict:
    return Instances(cmd).remove_mi_user_assigned(
        name=instance_name,
        resource_group_name=resource_group_name,
        mi_user_assigned=mi_user_assigned,
        federated_credential_name=federated_credential_name,
        **kwargs,
    )


def clone_instance(
    cmd,
    instance_name: str,
    resource_group_name: str,
    summary_mode: Optional[str] = None,
    to_dir: Optional[str] = None,
    template_mode: Optional[str] = None,
    to_cluster_params: Optional[List[str]] = None,
    to_cluster_id: Optional[str] = None,
    use_self_hosted_issuer: Optional[bool] = None,
    linked_base_uri: Optional[str] = None,
    no_progress: Optional[bool] = None,
    confirm_yes: Optional[bool] = None,
    force: Optional[bool] = None,
):
    from .providers.orchestration.clone import clone_instance

    return clone_instance(
        cmd=cmd,
        resource_group_name=resource_group_name,
        instance_name=instance_name,
        summary_mode=summary_mode,
        to_dir=to_dir,
        template_mode=template_mode,
        to_cluster_params=to_cluster_params,
        to_cluster_id=to_cluster_id,
        use_self_hosted_issuer=use_self_hosted_issuer,
        linked_base_uri=linked_base_uri,
        no_progress=no_progress,
        confirm_yes=confirm_yes,
        force=force,
    )


def enable_rsync(
    cmd,
    instance_name: str,
    resource_group_name: str,
    skip_role_assignments: Optional[bool] = None,
    custom_role_id: Optional[str] = None,
    k8_bridge_sp_oid: Optional[str] = None,
    rule_ops_name: Optional[str] = None,
    rule_adr_name: Optional[str] = None,
    rule_ops_pri: Optional[int] = None,
    rule_adr_pri: Optional[int] = None,
    tags: Optional[dict] = None,
    **kwargs,
):
    from .providers.orchestration.resources import SyncRules

    return SyncRules(cmd=cmd, resource_group_name=resource_group_name, instance_name=instance_name).enable(
        skip_role_assignments=skip_role_assignments,
        custom_role_id=custom_role_id,
        k8_bridge_sp_oid=k8_bridge_sp_oid,
        rule_ops_name=rule_ops_name,
        rule_adr_name=rule_adr_name,
        rule_ops_pri=rule_ops_pri,
        rule_adr_pri=rule_adr_pri,
        tags=tags,
        **kwargs,
    )


def disable_rsync(cmd, instance_name: str, resource_group_name: str, confirm_yes: Optional[bool] = None):
    from .providers.orchestration.resources import SyncRules

    return SyncRules(cmd=cmd, resource_group_name=resource_group_name, instance_name=instance_name).disable(
        confirm_yes=confirm_yes
    )


def list_rsync(
    cmd,
    instance_name: str,
    resource_group_name: str,
) -> List[dict]:
    from .providers.orchestration.resources import SyncRules

    return SyncRules(cmd=cmd, resource_group_name=resource_group_name, instance_name=instance_name).list()
