# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


from random import randint
from unittest.mock import Mock

import pytest

from azext_edge.edge.commands_edge import init
from azext_edge.edge.providers.base import DEFAULT_NAMESPACE
from azext_edge.edge.providers.orchestration.base import KEYVAULT_ARC_EXTENSION_VERSION
from azext_edge.edge.providers.orchestration.common import (
    MqMemoryProfile,
    MqMode,
    MqServiceType,
    KubernetesDistroType,
)
from azext_edge.edge.providers.orchestration.work import (
    CLUSTER_SECRET_CLASS_NAME,
    CLUSTER_SECRET_REF,
    CURRENT_TEMPLATE,
    TemplateVer,
    WorkManager,
)
from azext_edge.edge.util import url_safe_hash_phrase

from ...generators import generate_random_string


@pytest.mark.parametrize(
    """
    cluster_name,
    cluster_namespace,
    resource_group_name,
    keyvault_spc_secret_name,
    keyvault_resource_id,
    custom_location_name,
    custom_location_namespace,
    location,
    simulate_plc,
    opcua_discovery_endpoint,
    container_runtime_socket,
    kubernetes_distro,
    dp_instance_name,
    mq_instance_name,
    mq_frontend_server_name,
    mq_mode,
    mq_memory_profile,
    mq_service_type,
    mq_backend_partitions,
    mq_backend_workers,
    mq_backend_redundancy_factor,
    mq_frontend_workers,
    mq_frontend_replicas,
    mq_listener_name,
    mq_broker_name,
    mq_authn_name,
    mq_insecure,
    target_name,
    disable_rsync_rules,
    """,
    [
        pytest.param(
            generate_random_string(),  # cluster_name
            None,  # cluster_namespace
            generate_random_string(),  # resource_group_name
            None,  # keyvault_spc_secret_name
            None,  # keyvault_resource_id
            None,  # custom_location_name
            None,  # custom_location_namespace
            None,  # location
            None,  # simulate_plc
            None,  # opcua_discovery_endpoint
            None,  # container_runtime_socket
            None,  # kubernetes_distro,
            None,  # dp_instance_name
            None,  # mq_instance_name
            None,  # mq_frontend_server_name
            None,  # mq_mode
            None,  # mq_memory_profile
            None,  # mq_service_type
            None,  # mq_backend_partitions
            None,  # mq_backend_workers
            None,  # mq_backend_redundancy_factor
            None,  # mq_frontend_workers
            None,  # mq_frontend_replicas
            None,  # mq_listener_name
            None,  # mq_broker_name
            None,  # mq_authn_name
            None,  # mq_insecure
            None,  # target_name
            None,  # disable_rsync_rules
        ),
        pytest.param(
            generate_random_string(),  # cluster_name
            generate_random_string(),  # cluster_namespace
            generate_random_string(),  # resource_group_name
            generate_random_string(),  # keyvault_spc_secret_name
            generate_random_string(),  # keyvault_resource_id
            generate_random_string(),  # custom_location_name
            None,  # custom_location_namespace
            generate_random_string(),  # location
            True,  # simulate_plc
            None,  # opcua_discovery_endpoint
            None,  # container_runtime_socket
            KubernetesDistroType.k3s.value,  # kubernetes_distro,
            generate_random_string(),  # dp_instance_name
            generate_random_string(),  # mq_instance_name
            generate_random_string(),  # mq_frontend_server_name
            MqMode.auto.value,  # mq_mode
            MqMemoryProfile.high.value,  # mq_memory_profile
            MqServiceType.load_balancer.value,  # mq_service_type
            randint(1, 5),  # mq_backend_partitions
            randint(1, 5),  # mq_backend_workers
            randint(1, 5),  # mq_backend_redundancy_factor
            randint(1, 5),  # mq_frontend_workers
            randint(1, 5),  # mq_frontend_replicas
            generate_random_string(),  # mq_listener_name
            generate_random_string(),  # mq_broker_name
            generate_random_string(),  # mq_authn_name
            None,  # mq_insecure
            generate_random_string(),  # target_name
            None,  # disable_rsync_rules
        ),
        pytest.param(
            generate_random_string(),  # cluster_name
            generate_random_string(),  # cluster_namespace
            generate_random_string(),  # resource_group_name
            generate_random_string(),  # keyvault_spc_secret_name
            generate_random_string(),  # keyvault_resource_id
            generate_random_string(),  # custom_location_name
            None,  # custom_location_namespace
            generate_random_string(),  # location
            True,  # simulate_plc
            generate_random_string(),  # opcua_discovery_endpoint
            generate_random_string(),  # container_runtime_socket
            KubernetesDistroType.microk8s.value,  # kubernetes_distro,
            generate_random_string(),  # dp_instance_name
            generate_random_string(),  # mq_instance_name
            generate_random_string(),  # mq_frontend_server_name
            MqMode.auto.value,  # mq_mode
            MqMemoryProfile.high.value,  # mq_memory_profile
            MqServiceType.load_balancer.value,  # mq_service_type
            randint(1, 5),  # mq_backend_partitions
            randint(1, 5),  # mq_backend_workers
            randint(1, 5),  # mq_backend_redundancy_factor
            randint(1, 5),  # mq_frontend_workers
            randint(1, 5),  # mq_frontend_replicas
            generate_random_string(),  # mq_listener_name
            generate_random_string(),  # mq_broker_name
            generate_random_string(),  # mq_authn_name
            True,  # mq_insecure
            generate_random_string(),  # target_name
            True,  # disable_rsync_rules
        ),
    ],
)
def test_init_to_template_params(
    mocked_cmd: Mock,
    mocked_deploy: Mock,
    mocked_config: Mock,
    cluster_name,
    cluster_namespace,
    resource_group_name,
    keyvault_spc_secret_name,
    keyvault_resource_id,
    custom_location_name,
    custom_location_namespace,
    location,
    simulate_plc,
    opcua_discovery_endpoint,
    container_runtime_socket,
    kubernetes_distro,
    dp_instance_name,
    mq_instance_name,
    mq_frontend_server_name,
    mq_mode,
    mq_memory_profile,
    mq_service_type,
    mq_backend_partitions,
    mq_backend_workers,
    mq_backend_redundancy_factor,
    mq_frontend_workers,
    mq_frontend_replicas,
    mq_listener_name,
    mq_broker_name,
    mq_authn_name,
    mq_insecure,
    target_name,
    disable_rsync_rules,
):
    kwargs = {}

    param_tuples = [
        (cluster_namespace, "cluster_namespace"),
        (keyvault_spc_secret_name, "keyvault_spc_secret_name"),
        (keyvault_resource_id, "keyvault_resource_id"),
        (custom_location_name, "custom_location_name"),
        (custom_location_namespace, "custom_location_namespace"),
        (location, "location"),
        (simulate_plc, "simulate_plc"),
        (opcua_discovery_endpoint, "opcua_discovery_endpoint"),
        (container_runtime_socket, "container_runtime_socket"),
        (kubernetes_distro, "kubernetes_distro"),
        (dp_instance_name, "dp_instance_name"),
        (mq_instance_name, "mq_instance_name"),
        (mq_frontend_server_name, "mq_frontend_server_name"),
        (mq_mode, "mq_mode"),
        (mq_memory_profile, "mq_memory_profile"),
        (mq_service_type, "mq_service_type"),
        (mq_backend_partitions, "mq_backend_partitions"),
        (mq_backend_workers, "mq_backend_workers"),
        (mq_backend_redundancy_factor, "mq_backend_redundancy_factor"),
        (mq_frontend_workers, "mq_frontend_workers"),
        (mq_frontend_replicas, "mq_frontend_replicas"),
        (mq_listener_name, "mq_listener_name"),
        (mq_broker_name, "mq_broker_name"),
        (mq_authn_name, "mq_authn_name"),
        (mq_insecure, "mq_insecure"),
        (target_name, "target_name"),
        (disable_rsync_rules, "disable_rsync_rules"),
    ]

    for param_tuple in param_tuples:
        if param_tuple[0] is not None:
            kwargs[param_tuple[1]] = param_tuple[0]

    init(cmd=mocked_cmd, cluster_name=cluster_name, resource_group_name=resource_group_name, **kwargs)
    mocked_deploy.assert_called_once()
    # There is no longer user input for cluster_location
    assert mocked_deploy.call_args.kwargs["cluster_location"] is None

    work = WorkManager(**mocked_deploy.call_args.kwargs)
    # emulate dynamic query of location
    connected_cluster_location = generate_random_string()
    work._kwargs["cluster_location"] = connected_cluster_location
    if not location:
        assert mocked_deploy.call_args.kwargs["location"] is None
        work._kwargs["location"] = connected_cluster_location

    template_ver, parameters = work.build_template({})

    expected_cluster_namespace = cluster_namespace.lower() if cluster_namespace else DEFAULT_NAMESPACE

    lowered_cluster_name = cluster_name.lower()
    assert "clusterName" in parameters
    assert parameters["clusterName"]["value"] == cluster_name

    assert parameters["clusterLocation"]["value"] == connected_cluster_location
    if location:
        assert parameters["location"]["value"] == location
    else:
        assert parameters["location"]["value"] == connected_cluster_location

    assert "customLocationName" in parameters
    if custom_location_name:
        assert parameters["customLocationName"]["value"] == custom_location_name
    else:
        assert parameters["customLocationName"]["value"] == f"{lowered_cluster_name}-ops-init-cl"

    assert "targetName" in parameters
    if target_name:
        assert parameters["targetName"]["value"] == target_name
    else:
        assert parameters["targetName"]["value"] == f"{lowered_cluster_name}-ops-init-target"

    assert "dataProcessorInstanceName" in parameters
    if dp_instance_name:
        assert parameters["dataProcessorInstanceName"]["value"] == dp_instance_name
    else:
        assert parameters["dataProcessorInstanceName"]["value"] == f"{lowered_cluster_name}-ops-init-processor"

    assert "mqInstanceName" in parameters
    if mq_instance_name:
        assert parameters["mqInstanceName"]["value"] == mq_instance_name
    else:
        assert parameters["mqInstanceName"]["value"] == f"init-{url_safe_hash_phrase(cluster_name)[:5]}-mq-instance"

    if simulate_plc:
        assert "simulatePLC" in parameters and parameters["simulatePLC"]["value"] is True
        if not opcua_discovery_endpoint:
            assert (
                parameters["opcuaDiscoveryEndpoint"]["value"]
                == f"opc.tcp://opcplc-000000.{expected_cluster_namespace}:50000"
            )

    if opcua_discovery_endpoint:
        assert "opcuaDiscoveryEndpoint" in parameters
        assert parameters["opcuaDiscoveryEndpoint"]["value"] == opcua_discovery_endpoint

    assert "deployResourceSyncRules" in parameters
    assert parameters["deployResourceSyncRules"] is not disable_rsync_rules

    passthrough_value_tuples = [
        (container_runtime_socket, "containerRuntimeSocket", ""),
        (kubernetes_distro, "kubernetesDistro", KubernetesDistroType.k8s.value),
        (mq_listener_name, "mqListenerName", "listener"),
        (mq_frontend_server_name, "mqFrontendServer", "mq-dmqtt-frontend"),
        (mq_broker_name, "mqBrokerName", "broker"),
        (mq_authn_name, "mqAuthnName", "authn"),
        (mq_frontend_replicas, "mqFrontendReplicas", 2),
        (mq_frontend_workers, "mqFrontendWorkers", 2),
        (mq_backend_redundancy_factor, "mqBackendRedundancyFactor", 2),
        (mq_backend_workers, "mqBackendWorkers", 2),
        (mq_backend_partitions, "mqBackendPartitions", 2),
        (mq_mode, "mqMode", MqMode.distributed.value),
        (mq_memory_profile, "mqMemoryProfile", MqMemoryProfile.medium.value),
        (mq_service_type, "mqServiceType", MqServiceType.cluster_ip.value),
    ]

    for passthrough_value_tuple in passthrough_value_tuples:
        if passthrough_value_tuple[0]:
            assert parameters[passthrough_value_tuple[1]]["value"] == passthrough_value_tuple[0]
        else:
            assert parameters[passthrough_value_tuple[1]]["value"] == passthrough_value_tuple[2]

    set_value_tuples = [
        (
            "dataProcessorSecrets",
            {"enabled": True, "secretProviderClassName": "aio-default-spc", "servicePrincipalSecretRef": "aio-akv-sp"},
        ),
        (
            "mqSecrets",
            {"enabled": True, "secretProviderClassName": "aio-default-spc", "servicePrincipalSecretRef": "aio-akv-sp"},
        ),
        (
            "opcUaBrokerSecrets",
            {"kind": "csi", "csiServicePrincipalSecretRef": "aio-akv-sp"},
        ),
    ]
    for set_value_tuple in set_value_tuples:
        assert parameters[set_value_tuple[0]]["value"] == set_value_tuple[1]

    assert template_ver.content["variables"]["AIO_CLUSTER_RELEASE_NAMESPACE"] == expected_cluster_namespace

    # TODO
    assert template_ver.content["variables"]["AIO_TRUST_CONFIG_MAP"]
    assert template_ver.content["variables"]["AIO_TRUST_SECRET_NAME"]

    # test mq_insecure
    listeners = _get_resources_of_type(
        resource_type="Microsoft.IoTOperationsMQ/mq/broker/listener", template=template_ver
    )
    brokers = _get_resources_of_type(resource_type="Microsoft.IoTOperationsMQ/mq/broker", template=template_ver)
    insecure_listener_added = False
    for listener in listeners:
        if "'non-tls-listener'" in listener["name"]:
            insecure_listener_added = True

    if mq_insecure:
        assert insecure_listener_added
        assert brokers[0]["properties"]["encryptInternalTraffic"] is False
        return

    assert not insecure_listener_added
    assert "encryptInternalTraffic" not in brokers[0]["properties"]


def _get_resources_of_type(resource_type: str, template: TemplateVer):
    return [resource for resource in template.content["resources"] if resource["type"] == resource_type]


@pytest.mark.parametrize(
    """
    cluster_name,
    cluster_namespace,
    resource_group_name,
    keyvault_resource_id,
    keyvault_spc_secret_name,
    disable_secret_rotation,
    rotation_poll_interval,
    tls_ca_path,
    tls_ca_key_path,
    tls_ca_dir,
    no_deploy,
    no_tls,
    no_preflight,
    disable_rsync_rules,
    """,
    [
        pytest.param(
            generate_random_string(),  # cluster_name
            None,  # cluster_namespace
            generate_random_string(),  # resource_group_name
            None,  # keyvault_resource_id
            None,  # keyvault_spc_secret_name
            None,  # disable_secret_rotation
            None,  # rotation_poll_interval
            None,  # tls_ca_path
            None,  # tls_ca_key_path
            None,  # tls_ca_dir
            None,  # no_deploy
            None,  # no_tls
            None,  # no_preflight
            None,  # disable_rsync_rules
        ),
        pytest.param(
            generate_random_string(),  # cluster_name
            None,  # cluster_namespace
            generate_random_string(),  # resource_group_name
            generate_random_string(),  # keyvault_resource_id
            None,  # keyvault_spc_secret_name
            None,  # disable_secret_rotation
            None,  # rotation_poll_interval
            None,  # tls_ca_path
            None,  # tls_ca_key_path
            None,  # tls_ca_dir
            None,  # no_deploy
            None,  # no_tls
            None,  # no_preflight
            None,  # disable_rsync_rules
        ),
        pytest.param(
            generate_random_string(),  # cluster_name
            generate_random_string(),  # cluster_namespace
            generate_random_string(),  # resource_group_name
            generate_random_string(),  # keyvault_resource_id
            generate_random_string(),  # keyvault_spc_secret_name
            None,  # disable_secret_rotation
            None,  # rotation_poll_interval
            None,  # tls_ca_path
            None,  # tls_ca_key_path
            None,  # tls_ca_dir
            None,  # no_deploy
            None,  # no_tls
            None,  # no_preflight
            None,  # disable_rsync_rules
        ),
        pytest.param(
            generate_random_string(),  # cluster_name
            None,  # cluster_namespace
            generate_random_string(),  # resource_group_name
            generate_random_string(),  # keyvault_resource_id
            generate_random_string(),  # keyvault_spc_secret_name
            True,  # disable_secret_rotation
            "3h",  # rotation_poll_interval
            None,  # tls_ca_path
            None,  # tls_ca_key_path
            "/certs/",  # tls_ca_dir
            None,  # no_deploy
            None,  # no_tls
            None,  # no_preflight
            None,  # disable_rsync_rules
        ),
        pytest.param(
            generate_random_string(),  # cluster_name
            None,  # cluster_namespace
            generate_random_string(),  # resource_group_name
            generate_random_string(),  # keyvault_resource_id
            generate_random_string(),  # keyvault_spc_secret_name
            True,  # disable_secret_rotation
            "3h",  # rotation_poll_interval
            "/my/ca.crt",  # tls_ca_path
            "/my/key.pem",  # tls_ca_key_path
            None,  # tls_ca_dir
            True,  # no_deploy
            None,  # no_tls
            None,  # no_preflight
            None,  # disable_rsync_rules
        ),
        pytest.param(
            generate_random_string(),  # cluster_name
            None,  # cluster_namespace
            generate_random_string(),  # resource_group_name
            None,  # keyvault_resource_id
            None,  # keyvault_spc_secret_name
            None,  # disable_secret_rotation
            None,  # rotation_poll_interval
            None,  # tls_ca_path
            None,  # tls_ca_key_path
            None,  # tls_ca_dir
            True,  # no_deploy
            True,  # no_tls
            None,  # no_preflight
            None,  # disable_rsync_rules
        ),
        pytest.param(
            generate_random_string(),  # cluster_name
            None,  # cluster_namespace
            generate_random_string(),  # resource_group_name
            None,  # keyvault_resource_id
            None,  # keyvault_spc_secret_name
            None,  # disable_secret_rotation
            None,  # rotation_poll_interval
            None,  # tls_ca_path
            None,  # tls_ca_key_path
            None,  # tls_ca_dir
            True,  # no_deploy
            True,  # no_tls
            True,  # no_preflight
            True,  # disable_rsync_rules
        ),
    ],
)
def test_work_order(
    mocked_cmd: Mock,
    mocked_config: Mock,
    mocked_provision_akv_csi_driver: Mock,
    mocked_configure_cluster_secrets: Mock,
    mocked_cluster_tls: Mock,
    mocked_deploy_template: Mock,
    mocked_prepare_ca: Mock,
    mocked_prepare_keyvault_access_policy: Mock,
    mocked_prepare_keyvault_secret: Mock,
    mocked_prepare_sp: Mock,
    mocked_register_providers: Mock,
    mocked_verify_cli_client_connections: Mock,
    mocked_edge_api_keyvault_api_v1: Mock,
    mocked_validate_keyvault_permission_model: Mock,
    mocked_verify_write_permission_against_rg: Mock,
    mocked_wait_for_terminal_state: Mock,
    mocked_file_exists: Mock,
    mocked_connected_cluster_location: Mock,
    mocked_connected_cluster_extensions: Mock,
    mocked_verify_custom_locations_enabled: Mock,
    mocked_verify_arc_cluster_config: Mock,
    mocked_test_secret_via_sp: Mock,
    spy_get_current_template_copy: Mock,
    cluster_name,
    cluster_namespace,
    resource_group_name,
    keyvault_resource_id,
    keyvault_spc_secret_name,
    disable_secret_rotation,
    rotation_poll_interval,
    tls_ca_path,
    tls_ca_key_path,
    tls_ca_dir,
    no_deploy,
    no_tls,
    no_preflight,
    disable_rsync_rules,
):
    call_kwargs = {
        "cmd": mocked_cmd,
        "cluster_name": cluster_name,
        "resource_group_name": resource_group_name,
        "keyvault_resource_id": keyvault_resource_id,
        "disable_secret_rotation": disable_secret_rotation,
        "no_deploy": no_deploy,
        "no_tls": no_tls,
        "no_preflight": no_preflight,
        "no_progress": True,
        "disable_rsync_rules": disable_rsync_rules,
    }
    if rotation_poll_interval:
        call_kwargs["rotation_poll_interval"] = rotation_poll_interval
    if cluster_namespace:
        call_kwargs["cluster_namespace"] = cluster_namespace
    if keyvault_spc_secret_name:
        call_kwargs["keyvault_spc_secret_name"] = keyvault_spc_secret_name
    if tls_ca_path:
        call_kwargs["tls_ca_path"] = tls_ca_path
    if tls_ca_key_path:
        call_kwargs["tls_ca_key_path"] = tls_ca_key_path
    if tls_ca_dir:
        call_kwargs["tls_ca_dir"] = tls_ca_dir

    result = init(**call_kwargs)
    expected_template_copies = 0
    nothing_to_do = all([not keyvault_resource_id, no_tls, no_deploy, no_preflight])
    if nothing_to_do:
        assert not result
        mocked_verify_cli_client_connections.assert_not_called()
        mocked_edge_api_keyvault_api_v1.is_deployed.assert_not_called()
        return

    if any([not no_preflight, not no_deploy, keyvault_resource_id]):
        mocked_verify_cli_client_connections.assert_called_once()
        mocked_connected_cluster_location.assert_called_once()

    expected_cluster_namespace = cluster_namespace.lower() if cluster_namespace else DEFAULT_NAMESPACE

    if not no_preflight:
        expected_template_copies += 1
        mocked_register_providers.assert_called_once()
        mocked_verify_custom_locations_enabled.assert_called_once()
        mocked_connected_cluster_extensions.assert_called_once()
        mocked_verify_arc_cluster_config.assert_called_once()

        if not disable_rsync_rules:
            mocked_verify_write_permission_against_rg.assert_called_once()
            mocked_verify_write_permission_against_rg.call_args.kwargs["subscription_id"]
            mocked_verify_write_permission_against_rg.call_args.kwargs["resource_group_name"] == resource_group_name
        else:
            mocked_verify_write_permission_against_rg.assert_not_called()
    else:
        mocked_register_providers.assert_not_called()
        mocked_verify_custom_locations_enabled.assert_not_called()
        mocked_connected_cluster_extensions.assert_not_called()
        mocked_verify_arc_cluster_config.assert_not_called()

    if not keyvault_resource_id:
        mocked_edge_api_keyvault_api_v1.is_deployed.assert_called_once()

    if keyvault_resource_id:
        assert result["csiDriver"]
        assert result["csiDriver"]["spAppId"]
        assert result["csiDriver"]["version"] == KEYVAULT_ARC_EXTENSION_VERSION
        assert result["csiDriver"]["spObjectId"]
        assert result["csiDriver"]["keyVaultId"] == keyvault_resource_id

        expected_keyvault_spc_secret_name = keyvault_spc_secret_name if keyvault_spc_secret_name else DEFAULT_NAMESPACE
        assert result["csiDriver"]["kvSatSecretName"] == expected_keyvault_spc_secret_name
        assert (
            result["csiDriver"]["rotationPollInterval"] == rotation_poll_interval if rotation_poll_interval else "1h"
        )
        assert result["csiDriver"]["enableSecretRotation"] == "false" if disable_secret_rotation else "true"

        mocked_validate_keyvault_permission_model.assert_called_once()
        assert mocked_validate_keyvault_permission_model.call_args.kwargs["subscription_id"]
        assert (
            mocked_validate_keyvault_permission_model.call_args.kwargs["keyvault_resource_id"] == keyvault_resource_id
        )

        mocked_prepare_sp.assert_called_once()
        assert mocked_prepare_sp.call_args.kwargs["deployment_name"]
        assert mocked_prepare_sp.call_args.kwargs["cmd"]

        mocked_prepare_keyvault_access_policy.assert_called_once()
        assert mocked_prepare_keyvault_access_policy.call_args.kwargs["subscription_id"]
        assert mocked_prepare_keyvault_access_policy.call_args.kwargs["keyvault_resource_id"] == keyvault_resource_id
        assert mocked_prepare_keyvault_access_policy.call_args.kwargs["sp_record"]

        mocked_prepare_keyvault_secret.assert_called_once()
        expected_vault_uri = f"https://localhost/{keyvault_resource_id}/vault"

        assert mocked_prepare_keyvault_secret.call_args.kwargs["cmd"]
        assert mocked_prepare_keyvault_secret.call_args.kwargs["deployment_name"]
        assert mocked_prepare_keyvault_secret.call_args.kwargs["vault_uri"] == expected_vault_uri
        assert (
            mocked_prepare_keyvault_secret.call_args.kwargs["keyvault_spc_secret_name"]
            == expected_keyvault_spc_secret_name
        )

        mocked_provision_akv_csi_driver.assert_called_once()
        assert mocked_provision_akv_csi_driver.call_args.kwargs["subscription_id"]
        assert mocked_provision_akv_csi_driver.call_args.kwargs["cluster_name"] == cluster_name
        assert mocked_provision_akv_csi_driver.call_args.kwargs["resource_group_name"] == resource_group_name
        assert (
            mocked_provision_akv_csi_driver.call_args.kwargs["enable_secret_rotation"] == "false"
            if disable_secret_rotation
            else "true"
        )
        assert (
            mocked_provision_akv_csi_driver.call_args.kwargs["rotation_poll_interval"] == rotation_poll_interval
            if rotation_poll_interval
            else "1h"
        )

        assert "extension_name" not in mocked_provision_akv_csi_driver.call_args.kwargs

        mocked_configure_cluster_secrets.assert_called_once()
        assert mocked_configure_cluster_secrets.call_args.kwargs["cluster_namespace"] == expected_cluster_namespace
        assert mocked_configure_cluster_secrets.call_args.kwargs["cluster_secret_ref"] == CLUSTER_SECRET_REF
        assert (
            mocked_configure_cluster_secrets.call_args.kwargs["cluster_akv_secret_class_name"]
            == CLUSTER_SECRET_CLASS_NAME
        )
        assert (
            mocked_configure_cluster_secrets.call_args.kwargs["keyvault_spc_secret_name"]
            == expected_keyvault_spc_secret_name
        )
        assert mocked_configure_cluster_secrets.call_args.kwargs["keyvault_resource_id"] == keyvault_resource_id
        assert mocked_configure_cluster_secrets.call_args.kwargs["sp_record"]

        mocked_test_secret_via_sp.assert_called_once()
        assert mocked_test_secret_via_sp.call_args.kwargs["vault_uri"] == expected_vault_uri
        assert (
            mocked_test_secret_via_sp.call_args.kwargs["keyvault_spc_secret_name"] == expected_keyvault_spc_secret_name
        )
        assert mocked_test_secret_via_sp.call_args.kwargs["sp_record"]
    else:
        if not nothing_to_do:
            assert "csiDriver" not in result
        mocked_prepare_sp.assert_not_called()
        mocked_prepare_keyvault_access_policy.assert_not_called()
        mocked_prepare_keyvault_secret.assert_not_called()
        mocked_provision_akv_csi_driver.assert_not_called()
        mocked_configure_cluster_secrets.assert_not_called()
        mocked_test_secret_via_sp.assert_not_called()

    if not no_tls:
        assert result["tls"]["aioTrustConfigMap"]  # TODO
        assert result["tls"]["aioTrustSecretName"]  # TODO
        mocked_prepare_ca.assert_called_once()
        assert mocked_prepare_ca.call_args.kwargs["tls_ca_path"] == tls_ca_path
        assert mocked_prepare_ca.call_args.kwargs["tls_ca_key_path"] == tls_ca_key_path
        assert mocked_prepare_ca.call_args.kwargs["tls_ca_dir"] == tls_ca_dir

        mocked_cluster_tls.assert_called_once()
        assert mocked_cluster_tls.call_args.kwargs["cluster_namespace"] == expected_cluster_namespace

        assert mocked_cluster_tls.call_args.kwargs["public_ca"]
        assert mocked_cluster_tls.call_args.kwargs["private_key"]
        assert mocked_cluster_tls.call_args.kwargs["secret_name"]
        assert mocked_cluster_tls.call_args.kwargs["cm_name"]
    else:
        if not nothing_to_do:
            assert "tls" not in result
        mocked_prepare_ca.assert_not_called()
        mocked_cluster_tls.assert_not_called()

    if not no_deploy:
        expected_template_copies += 1
        assert result["deploymentName"]
        assert result["resourceGroup"] == resource_group_name
        assert result["clusterName"] == cluster_name
        assert result["clusterNamespace"]
        assert result["deploymentLink"]
        assert result["deploymentState"]
        assert result["deploymentState"]["status"]
        assert result["deploymentState"]["correlationId"]
        assert result["deploymentState"]["opsVersion"] == CURRENT_TEMPLATE.component_vers
        assert result["deploymentState"]["timestampUtc"]
        assert result["deploymentState"]["timestampUtc"]["started"]
        assert result["deploymentState"]["timestampUtc"]["ended"]
        assert "resources" in result["deploymentState"]

        assert mocked_deploy_template.call_count == 2
        assert mocked_deploy_template.call_args.kwargs["template"]
        assert mocked_deploy_template.call_args.kwargs["parameters"]
        assert mocked_deploy_template.call_args.kwargs["subscription_id"]
        assert mocked_deploy_template.call_args.kwargs["resource_group_name"] == resource_group_name
        assert mocked_deploy_template.call_args.kwargs["deployment_name"]
        assert mocked_deploy_template.call_args.kwargs["cluster_name"] == cluster_name
        assert mocked_deploy_template.call_args.kwargs["cluster_namespace"] == expected_cluster_namespace
    else:
        if not nothing_to_do:
            assert "deploymentName" not in result
            assert "resourceGroup" not in result
            assert "clusterName" not in result
            assert "clusterNamespace" not in result
            assert "deploymentLink" not in result
            assert "deploymentState" not in result
        # TODO
        # mocked_deploy_template.assert_not_called()

    assert spy_get_current_template_copy.call_count == expected_template_copies
