# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


import json
import string
from os import environ
from pathlib import Path
from random import randint
from typing import Dict, FrozenSet, List
from unittest.mock import Mock

import pytest

from azext_edge.edge.commands_edge import init
from azext_edge.edge.common import INIT_NO_PREFLIGHT_ENV_KEY
from azext_edge.edge.providers.base import DEFAULT_NAMESPACE
from azext_edge.edge.providers.orchestration.base import KEYVAULT_ARC_EXTENSION_VERSION
from azext_edge.edge.providers.orchestration.common import (
    KubernetesDistroType,
    MqMemoryProfile,
    MqServiceType,
)
from azext_edge.edge.providers.orchestration.work import (
    CLUSTER_SECRET_CLASS_NAME,
    CLUSTER_SECRET_REF,
    CURRENT_TEMPLATE,
    WorkCategoryKey,
    WorkManager,
    WorkStepKey,
)
from azext_edge.edge.util import assemble_nargs_to_dict

from ...generators import generate_random_string

MOCK_BROKER_CONFIG_PATH = Path(__file__).parent.joinpath("./broker_config.json")


@pytest.fixture(scope="module")
def mock_broker_config():
    custom_config = {generate_random_string(): generate_random_string()}
    MOCK_BROKER_CONFIG_PATH.write_text(json.dumps(custom_config), encoding="utf-8")
    yield custom_config
    MOCK_BROKER_CONFIG_PATH.unlink()


@pytest.mark.parametrize(
    """
    instance_name,
    instance_description,
    cluster_name,
    cluster_namespace,
    resource_group_name,
    keyvault_spc_secret_name,
    keyvault_resource_id,
    custom_location_name,
    custom_location_namespace,
    location,
    simulate_plc,
    container_runtime_socket,
    kubernetes_distro,
    mq_frontend_server_name,
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
    disable_rsync_rules,
    mq_broker_config_file,
    """,
    [
        pytest.param(
            None,  # instance_name
            None,  # instance_description
            generate_random_string(),  # cluster_name
            None,  # cluster_namespace
            generate_random_string(),  # resource_group_name
            None,  # keyvault_spc_secret_name
            None,  # keyvault_resource_id
            None,  # custom_location_name
            None,  # custom_location_namespace
            None,  # location
            None,  # simulate_plc
            None,  # container_runtime_socket
            None,  # kubernetes_distro,
            None,  # mq_frontend_server_name
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
            None,  # disable_rsync_rules
            None,  # mq_broker_config_file
        ),
        pytest.param(
            None,  # instance_name
            None,  # instance_description
            generate_random_string(),  # cluster_name
            generate_random_string(),  # cluster_namespace
            generate_random_string(),  # resource_group_name
            generate_random_string(),  # keyvault_spc_secret_name
            generate_random_string(),  # keyvault_resource_id
            generate_random_string(),  # custom_location_name
            None,  # custom_location_namespace
            generate_random_string(),  # location
            True,  # simulate_plc
            None,  # container_runtime_socket
            KubernetesDistroType.k3s.value,  # kubernetes_distro,
            generate_random_string(),  # mq_frontend_server_name
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
            None,  # disable_rsync_rules
            None,  # mq_broker_config_file
        ),
        pytest.param(
            generate_random_string(),  # instance_name
            generate_random_string(),  # instance_description
            generate_random_string(),  # cluster_name
            generate_random_string(),  # cluster_namespace
            generate_random_string(),  # resource_group_name
            generate_random_string(),  # keyvault_spc_secret_name
            generate_random_string(),  # keyvault_resource_id
            generate_random_string(),  # custom_location_name
            None,  # custom_location_namespace
            generate_random_string(),  # location
            True,  # simulate_plc
            generate_random_string(),  # container_runtime_socket
            KubernetesDistroType.microk8s.value,  # kubernetes_distro,
            generate_random_string(),  # mq_frontend_server_name
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
            True,  # disable_rsync_rules
            str(MOCK_BROKER_CONFIG_PATH),  # mq_broker_config_file
        ),
    ],
)
def test_init_to_template_params(
    mocked_cmd: Mock,
    mocked_deploy: Mock,
    mocked_config: Mock,
    mock_broker_config: dict,
    instance_name,
    instance_description,
    cluster_name,
    cluster_namespace,
    resource_group_name,
    keyvault_spc_secret_name,
    keyvault_resource_id,
    custom_location_name,
    custom_location_namespace,
    location,
    simulate_plc,
    container_runtime_socket,
    kubernetes_distro,
    mq_frontend_server_name,
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
    disable_rsync_rules,
    mq_broker_config_file,
):
    kwargs = {}

    param_tuples = [
        (instance_name, "instance_name"),
        (instance_description, "instance_description"),
        (cluster_namespace, "cluster_namespace"),
        (keyvault_spc_secret_name, "keyvault_spc_secret_name"),
        (keyvault_resource_id, "keyvault_resource_id"),
        (custom_location_name, "custom_location_name"),
        (custom_location_namespace, "custom_location_namespace"),
        (location, "location"),
        (simulate_plc, "simulate_plc"),
        (container_runtime_socket, "container_runtime_socket"),
        (kubernetes_distro, "kubernetes_distro"),
        (mq_frontend_server_name, "mq_frontend_server_name"),
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
        (disable_rsync_rules, "disable_rsync_rules"),
        (mq_broker_config_file, "mq_broker_config_file"),
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

    assert "instanceName" in parameters
    if instance_name:
        assert parameters["instanceName"]["value"] == instance_name
    else:
        assert parameters["instanceName"]["value"] == f"{lowered_cluster_name}-ops-instance"

    assert parameters["clusterLocation"]["value"] == connected_cluster_location
    if location:
        assert parameters["location"]["value"] == location
    else:
        assert parameters["location"]["value"] == connected_cluster_location

    assert "customLocationName" in parameters
    if custom_location_name:
        assert parameters["customLocationName"]["value"] == custom_location_name
    else:
        split_custom_location_name = parameters["customLocationName"]["value"].split("-")
        assert split_custom_location_name[0] == lowered_cluster_name

        expected_char_set = string.ascii_lowercase + string.ascii_uppercase + string.digits
        for c in split_custom_location_name[1]:
            assert c in expected_char_set
        assert parameters["customLocationName"]["value"].endswith("-ops-init-cl")

    if simulate_plc:
        assert "simulatePLC" in parameters and parameters["simulatePLC"]["value"] is True

    assert "deployResourceSyncRules" in parameters
    assert parameters["deployResourceSyncRules"] is not disable_rsync_rules

    passthrough_value_tuples = [
        (instance_description, "instanceDescription", None),
        (container_runtime_socket, "containerRuntimeSocket", None),
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
        (mq_memory_profile, "mqMemoryProfile", MqMemoryProfile.medium.value),
        (mq_service_type, "mqServiceType", MqServiceType.cluster_ip.value),
    ]

    for passthrough_value_tuple in passthrough_value_tuples:
        if passthrough_value_tuple[0]:
            assert parameters[passthrough_value_tuple[1]]["value"] == passthrough_value_tuple[0]
        elif passthrough_value_tuple[2]:
            assert parameters[passthrough_value_tuple[1]]["value"] == passthrough_value_tuple[2]
        else:
            assert passthrough_value_tuple[1] not in parameters

    set_value_tuples = [
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

    listener = template_ver.get_resource_defs(resource_type="Microsoft.IoTOperations/instances/brokers/listeners")
    assert listener
    ports: List[dict] = listener["properties"]["ports"]
    assert ports
    assert ports[0]["port"] == 8883

    if mq_insecure:
        assert len(ports) == 2
        assert ports[1]["port"] == 1883

    broker = template_ver.get_resource_defs(resource_type="Microsoft.IoTOperations/instances/brokers")
    assert broker
    if mq_broker_config_file:
        assert broker["properties"] == mock_broker_config


@pytest.mark.parametrize(
    """
    cluster_name,
    cluster_namespace,
    resource_group_name,
    keyvault_resource_id,
    keyvault_spc_secret_name,
    disable_secret_rotation,
    rotation_poll_interval,
    csi_driver_version,
    csi_driver_config,
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
            None,  # csi_driver_version
            None,  # csi_driver_config
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
            None,  # csi_driver_version
            None,  # csi_driver_config
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
            None,  # csi_driver_version
            None,  # csi_driver_config
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
            None,  # csi_driver_version
            None,  # csi_driver_config
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
            "2.0.0",  # csi_driver_version
            ["telegraf.resources.limits.memory=500Mi", "telegraf.resources.limits.cpu=100m"],  # csi_driver_config
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
            None,  # csi_driver_version
            None,  # csi_driver_config
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
            None,  # csi_driver_version
            None,  # csi_driver_config
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
    mocked_eval_secret_via_sp: Mock,
    mocked_verify_custom_location_namespace: Mock,
    spy_get_current_template_copy: Mock,
    cluster_name,
    cluster_namespace,
    resource_group_name,
    keyvault_resource_id,
    keyvault_spc_secret_name,
    disable_secret_rotation,
    rotation_poll_interval,
    csi_driver_version,
    csi_driver_config,
    tls_ca_path,
    tls_ca_key_path,
    tls_ca_dir,
    no_deploy,
    no_tls,
    no_preflight,
    disable_rsync_rules,
    spy_work_displays,
):
    # TODO: Refactor for simplification

    call_kwargs = {
        "cmd": mocked_cmd,
        "cluster_name": cluster_name,
        "resource_group_name": resource_group_name,
        "keyvault_resource_id": keyvault_resource_id,
        "disable_secret_rotation": disable_secret_rotation,
        "no_deploy": no_deploy,
        "no_tls": no_tls,
        "no_progress": True,
        "disable_rsync_rules": disable_rsync_rules,
    }

    if no_preflight:
        environ[INIT_NO_PREFLIGHT_ENV_KEY] = "true"

    for param_with_default in [
        (rotation_poll_interval, "rotation_poll_interval"),
        (csi_driver_version, "csi_driver_version"),
        (csi_driver_config, "csi_driver_config"),
        (cluster_namespace, "cluster_namespace"),
        (keyvault_spc_secret_name, "keyvault_spc_secret_name"),
        (tls_ca_path, "tls_ca_path"),
        (tls_ca_key_path, "tls_ca_key_path"),
        (tls_ca_dir, "tls_ca_dir"),
    ]:
        if param_with_default[0]:
            call_kwargs[param_with_default[1]] = param_with_default[0]

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

    displays_to_eval = []
    for category_tuple in [
        (not no_preflight, WorkCategoryKey.PRE_FLIGHT),
        (keyvault_resource_id, WorkCategoryKey.CSI_DRIVER),
        (not no_tls, WorkCategoryKey.TLS_CA),
        (not no_deploy, WorkCategoryKey.DEPLOY_AIO),
    ]:
        if category_tuple[0]:
            displays_to_eval.append(category_tuple[1])
    _assert_displays_for(set(displays_to_eval), spy_work_displays)

    if not no_preflight:
        expected_template_copies += 1
        mocked_register_providers.assert_called_once()
        mocked_verify_custom_locations_enabled.assert_called_once()
        mocked_connected_cluster_extensions.assert_called_once()
        mocked_verify_arc_cluster_config.assert_called_once()
        mocked_verify_custom_location_namespace.assert_called_once()

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
        mocked_verify_custom_location_namespace.assert_not_called()

    if keyvault_resource_id:
        assert result["csiDriver"]
        assert result["csiDriver"]["spAppId"]
        assert result["csiDriver"]["spObjectId"]
        assert result["csiDriver"]["keyVaultId"] == keyvault_resource_id

        expected_csi_driver_version = csi_driver_version if csi_driver_version else KEYVAULT_ARC_EXTENSION_VERSION
        assert result["csiDriver"]["version"] == expected_csi_driver_version

        expected_csi_driver_custom_config = assemble_nargs_to_dict(csi_driver_config) if csi_driver_config else {}
        if expected_csi_driver_custom_config:
            for key in expected_csi_driver_custom_config:
                assert expected_csi_driver_custom_config[key] == result["csiDriver"]["configurationSettings"][key]

        expected_keyvault_spc_secret_name = keyvault_spc_secret_name if keyvault_spc_secret_name else DEFAULT_NAMESPACE
        assert result["csiDriver"]["kvSpcSecretName"] == expected_keyvault_spc_secret_name

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

        mocked_eval_secret_via_sp.assert_called_once()
        assert mocked_eval_secret_via_sp.call_args.kwargs["vault_uri"] == expected_vault_uri
        assert (
            mocked_eval_secret_via_sp.call_args.kwargs["keyvault_spc_secret_name"] == expected_keyvault_spc_secret_name
        )
        assert mocked_eval_secret_via_sp.call_args.kwargs["sp_record"]
    else:
        if not nothing_to_do and result:
            assert "csiDriver" not in result
        mocked_prepare_sp.assert_not_called()
        mocked_prepare_keyvault_access_policy.assert_not_called()
        mocked_prepare_keyvault_secret.assert_not_called()
        mocked_provision_akv_csi_driver.assert_not_called()
        mocked_configure_cluster_secrets.assert_not_called()
        mocked_eval_secret_via_sp.assert_not_called()

        mocked_edge_api_keyvault_api_v1.is_deployed.assert_called_once()

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
        if not nothing_to_do and result:
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
        assert result["deploymentState"]["opsVersion"] == CURRENT_TEMPLATE.get_component_vers()
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
        if not nothing_to_do and result:
            assert "deploymentName" not in result
            assert "resourceGroup" not in result
            assert "clusterName" not in result
            assert "clusterNamespace" not in result
            assert "deploymentLink" not in result
            assert "deploymentState" not in result
        # TODO
        # mocked_deploy_template.assert_not_called()

    assert spy_get_current_template_copy.call_count == expected_template_copies


def _assert_displays_for(work_category_set: FrozenSet[WorkCategoryKey], display_spys: Dict[str, Mock]):
    render_display = display_spys["render_display"]
    render_display_call_kwargs = [m.kwargs for m in render_display.mock_calls]

    index = 0
    if WorkCategoryKey.PRE_FLIGHT in work_category_set:
        assert render_display_call_kwargs[index] == {
            "category": WorkCategoryKey.PRE_FLIGHT,
            "active_step": WorkStepKey.REG_RP,
        }
        index += 1
        assert render_display_call_kwargs[index] == {"active_step": WorkStepKey.ENUMERATE_PRE_FLIGHT}
        index += 1
        assert render_display_call_kwargs[index] == {"active_step": WorkStepKey.WHAT_IF}
        index += 1
        assert render_display_call_kwargs[index] == {"active_step": -1}
        index += 1

    if WorkCategoryKey.CSI_DRIVER in work_category_set:
        assert render_display_call_kwargs[index] == {
            "category": WorkCategoryKey.CSI_DRIVER,
            "active_step": WorkStepKey.KV_CLOUD_PERM_MODEL,
        }
        index += 1
        assert render_display_call_kwargs[index] == {"active_step": WorkStepKey.SP}
        index += 1
        assert render_display_call_kwargs[index] == {"category": WorkCategoryKey.CSI_DRIVER}
        index += 1
        assert render_display_call_kwargs[index] == {"active_step": WorkStepKey.KV_CLOUD_AP}
        index += 1
        assert render_display_call_kwargs[index] == {"active_step": WorkStepKey.KV_CLOUD_SEC}
        index += 1
        assert render_display_call_kwargs[index] == {"active_step": WorkStepKey.KV_CLOUD_TEST}
        index += 1
        assert render_display_call_kwargs[index] == {"active_step": WorkStepKey.KV_CSI_DEPLOY}
        index += 1
        assert render_display_call_kwargs[index] == {"active_step": WorkStepKey.KV_CSI_CLUSTER}
        index += 1
        assert render_display_call_kwargs[index] == {"active_step": -1}
        index += 1

    if WorkCategoryKey.TLS_CA in work_category_set:
        assert render_display_call_kwargs[index] == {
            "category": WorkCategoryKey.TLS_CA,
            "active_step": WorkStepKey.TLS_CERT,
        }
        index += 1
        assert render_display_call_kwargs[index] == {"active_step": WorkStepKey.TLS_CLUSTER}
        index += 1
        assert render_display_call_kwargs[index] == {"active_step": -1}
        index += 1

    if WorkCategoryKey.DEPLOY_AIO in work_category_set:
        assert render_display_call_kwargs[index] == {"category": WorkCategoryKey.DEPLOY_AIO}
        index += 1
        # DEPLOY_AIO gets rendered twice to dynamically expose deployment link
        assert render_display_call_kwargs[index] == {"category": WorkCategoryKey.DEPLOY_AIO}
