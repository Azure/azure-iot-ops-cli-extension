# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------


from random import randint
from unittest.mock import Mock

import pytest

from azext_edge.edge.commands_edge import init
from azext_edge.edge.providers.base import DEFAULT_NAMESPACE
from azext_edge.edge.providers.orchestration.common import (
    MqMemoryProfile,
    MqMode,
    MqServiceType,
)
from azext_edge.edge.providers.orchestration.work import WorkManager, CLUSTER_SECRET_CLASS_NAME, CLUSTER_SECRET_REF
from azext_edge.edge.util import url_safe_hash_phrase

from ...generators import generate_generic_id


@pytest.mark.parametrize(
    """
    cluster_name,
    cluster_namespace,
    resource_group_name,
    keyvault_sat_secret_name,
    keyvault_resource_id,
    custom_location_name,
    custom_location_namespace,
    location,
    simulate_plc,
    opcua_discovery_endpoint,
    dp_instance_name,
    dp_reader_workers,
    dp_runner_workers,
    dp_message_stores,
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
    target_name,
    """,
    [
        pytest.param(
            generate_generic_id(),  # cluster_name
            None,  # cluster_namespace
            generate_generic_id(),  # resource_group_name
            None,  # keyvault_sat_secret_name
            None,  # keyvault_resource_id
            None,  # custom_location_name
            None,  # custom_location_namespace
            None,  # location
            None,  # simulate_plc
            None,  # opcua_discovery_endpoint
            None,  # dp_instance_name
            None,  # dp_reader_workers
            None,  # dp_runner_workers
            None,  # dp_message_stores
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
            None,  # target_name
        ),
        pytest.param(
            generate_generic_id(),  # cluster_name
            generate_generic_id(),  # cluster_namespace
            generate_generic_id(),  # resource_group_name
            generate_generic_id(),  # keyvault_sat_secret_name
            generate_generic_id(),  # keyvault_resource_id
            generate_generic_id(),  # custom_location_name
            None,  # custom_location_namespace
            generate_generic_id(),  # location
            True,  # simulate_plc
            None,  # opcua_discovery_endpoint
            generate_generic_id(),  # dp_instance_name
            randint(1, 5),  # dp_reader_workers
            randint(1, 5),  # dp_runner_workers
            randint(1, 5),  # dp_message_stores
            generate_generic_id(),  # mq_instance_name
            generate_generic_id(),  # mq_frontend_server_name
            MqMode.auto.value,  # mq_mode
            MqMemoryProfile.high.value,  # mq_memory_profile
            MqServiceType.load_balancer.value,  # mq_service_type
            randint(1, 5),  # mq_backend_partitions
            randint(1, 5),  # mq_backend_workers
            randint(1, 5),  # mq_backend_redundancy_factor
            randint(1, 5),  # mq_frontend_workers
            randint(1, 5),  # mq_frontend_replicas
            generate_generic_id(),  # mq_listener_name
            generate_generic_id(),  # mq_broker_name
            generate_generic_id(),  # mq_authn_name
            generate_generic_id(),  # target_name
        ),
        pytest.param(
            generate_generic_id(),  # cluster_name
            generate_generic_id(),  # cluster_namespace
            generate_generic_id(),  # resource_group_name
            generate_generic_id(),  # keyvault_sat_secret_name
            generate_generic_id(),  # keyvault_resource_id
            generate_generic_id(),  # custom_location_name
            None,  # custom_location_namespace
            generate_generic_id(),  # location
            True,  # simulate_plc
            generate_generic_id(),  # opcua_discovery_endpoint
            generate_generic_id(),  # dp_instance_name
            randint(1, 5),  # dp_reader_workers
            randint(1, 5),  # dp_runner_workers
            randint(1, 5),  # dp_message_stores
            generate_generic_id(),  # mq_instance_name
            generate_generic_id(),  # mq_frontend_server_name
            MqMode.auto.value,  # mq_mode
            MqMemoryProfile.high.value,  # mq_memory_profile
            MqServiceType.load_balancer.value,  # mq_service_type
            randint(1, 5),  # mq_backend_partitions
            randint(1, 5),  # mq_backend_workers
            randint(1, 5),  # mq_backend_redundancy_factor
            randint(1, 5),  # mq_frontend_workers
            randint(1, 5),  # mq_frontend_replicas
            generate_generic_id(),  # mq_listener_name
            generate_generic_id(),  # mq_broker_name
            generate_generic_id(),  # mq_authn_name
            generate_generic_id(),  # target_name
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
    keyvault_sat_secret_name,
    keyvault_resource_id,
    custom_location_name,
    custom_location_namespace,
    location,
    simulate_plc,
    opcua_discovery_endpoint,
    dp_instance_name,
    dp_reader_workers,
    dp_runner_workers,
    dp_message_stores,
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
    target_name,
):
    kwargs = {}

    param_tuples = [
        (cluster_namespace, "cluster_namespace"),
        (keyvault_sat_secret_name, "keyvault_sat_secret_name"),
        (keyvault_resource_id, "keyvault_resource_id"),
        (custom_location_name, "custom_location_name"),
        (custom_location_namespace, "custom_location_namespace"),
        (location, "location"),
        (simulate_plc, "simulate_plc"),
        (opcua_discovery_endpoint, "opcua_discovery_endpoint"),
        (dp_instance_name, "dp_instance_name"),
        (dp_reader_workers, "dp_reader_workers"),
        (dp_runner_workers, "dp_runner_workers"),
        (dp_message_stores, "dp_message_stores"),
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
        (target_name, "target_name"),
    ]

    for param_tuple in param_tuples:
        if param_tuple[0]:
            kwargs[param_tuple[1]] = param_tuple[0]

    init(cmd=mocked_cmd, cluster_name=cluster_name, resource_group_name=resource_group_name, **kwargs)
    mocked_deploy.assert_called_once()
    work = WorkManager(**mocked_deploy.call_args.kwargs)
    template_ver, parameters = work.build_template({})

    assert "clusterName" in parameters
    assert parameters["clusterName"]["value"] == cluster_name

    assert "customLocationName" in parameters
    if custom_location_name:
        assert parameters["customLocationName"]["value"] == custom_location_name
    else:
        assert parameters["customLocationName"]["value"] == f"{cluster_name}-aio-init-cl"

    assert "targetName" in parameters
    if target_name:
        assert parameters["targetName"]["value"] == target_name
    else:
        assert parameters["targetName"]["value"] == f"{cluster_name}-aio-init-target"

    assert "dataProcessorInstanceName" in parameters
    if dp_instance_name:
        assert parameters["dataProcessorInstanceName"]["value"] == dp_instance_name
    else:
        assert parameters["dataProcessorInstanceName"]["value"] == f"{cluster_name}-aio-init-processor"

    assert "mqInstanceName" in parameters
    if mq_instance_name:
        assert parameters["mqInstanceName"]["value"] == mq_instance_name
    else:
        assert parameters["mqInstanceName"]["value"] == f"init-{url_safe_hash_phrase(cluster_name)[:5]}-mq-instance"

    if simulate_plc:
        assert "simulatePLC" in parameters and parameters["simulatePLC"]["value"] is True
        if not opcua_discovery_endpoint:
            assert parameters["opcuaDiscoveryEndpoint"]["value"] == f"opc.tcp://opcplc-000000.{cluster_namespace}:50000"

    if opcua_discovery_endpoint:
        assert "opcuaDiscoveryEndpoint" in parameters
        assert parameters["opcuaDiscoveryEndpoint"]["value"] == opcua_discovery_endpoint

    passthrough_value_tuples = [
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

    dp_cardinality = {
        "readerWorker": dp_reader_workers or 1,
        "runnerWorker": dp_runner_workers or 1,
        "messageStore": dp_message_stores or 1,
    }
    passthrough_value_tuples.append((False, "dataProcessorCardinality", dp_cardinality))

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

    assert template_ver.content["variables"]["AIO_CLUSTER_RELEASE_NAMESPACE"] == cluster_namespace or DEFAULT_NAMESPACE

    # TODO
    assert template_ver.content["variables"]["AIO_TRUST_CONFIG_MAP"]
    assert template_ver.content["variables"]["AIO_TRUST_SECRET_NAME"]


@pytest.mark.parametrize(
    """
    cluster_name,
    cluster_namespace,
    resource_group_name,
    keyvault_resource_id,
    keyvault_sat_secret_name,
    disable_secret_rotation,
    rotation_poll_interval,
    tls_ca_path,
    tls_ca_key_path,
    tls_ca_dir,
    no_deploy,
    no_tls,
    """,
    [
        pytest.param(
            generate_generic_id(),  # cluster_name
            None,  # cluster_namespace
            generate_generic_id(),  # resource_group_name
            None,  # keyvault_resource_id
            None,  # keyvault_sat_secret_name
            None,  # disable_secret_rotation
            None,  # rotation_poll_interval
            None,  # tls_ca_path
            None,  # tls_ca_key_path
            None,  # tls_ca_dir
            None,  # no_deploy
            None,  # no_tls
        ),
        pytest.param(
            generate_generic_id(),  # cluster_name
            None,  # cluster_namespace
            generate_generic_id(),  # resource_group_name
            generate_generic_id(),  # keyvault_resource_id
            None,  # keyvault_sat_secret_name
            None,  # disable_secret_rotation
            None,  # rotation_poll_interval
            None,  # tls_ca_path
            None,  # tls_ca_key_path
            None,  # tls_ca_dir
            None,  # no_deploy
            None,  # no_tls
        ),
        pytest.param(
            generate_generic_id(),  # cluster_name
            generate_generic_id(),  # cluster_namespace
            generate_generic_id(),  # resource_group_name
            generate_generic_id(),  # keyvault_resource_id
            generate_generic_id(),  # keyvault_sat_secret_name
            None,  # disable_secret_rotation
            None,  # rotation_poll_interval
            None,  # tls_ca_path
            None,  # tls_ca_key_path
            None,  # tls_ca_dir
            None,  # no_deploy
            None,  # no_tls
        ),
        pytest.param(
            generate_generic_id(),  # cluster_name
            None,  # cluster_namespace
            generate_generic_id(),  # resource_group_name
            generate_generic_id(),  # keyvault_resource_id
            generate_generic_id(),  # keyvault_sat_secret_name
            True,  # disable_secret_rotation
            "3h",  # rotation_poll_interval
            None,  # tls_ca_path
            None,  # tls_ca_key_path
            "/certs/",  # tls_ca_dir
            None,  # no_deploy
            None,  # no_tls
        ),
        pytest.param(
            generate_generic_id(),  # cluster_name
            None,  # cluster_namespace
            generate_generic_id(),  # resource_group_name
            generate_generic_id(),  # keyvault_resource_id
            generate_generic_id(),  # keyvault_sat_secret_name
            True,  # disable_secret_rotation
            "3h",  # rotation_poll_interval
            "/my/ca.crt",  # tls_ca_path
            "/my/key.pem",  # tls_ca_key_path
            None,  # tls_ca_dir
            True,  # no_deploy
            None,  # no_tls
        ),
        pytest.param(
            generate_generic_id(),  # cluster_name
            None,  # cluster_namespace
            generate_generic_id(),  # resource_group_name
            None,  # keyvault_resource_id
            None,  # keyvault_sat_secret_name
            None,  # disable_secret_rotation
            None,  # rotation_poll_interval
            None,  # tls_ca_path
            None,  # tls_ca_key_path
            None,  # tls_ca_dir
            True,  # no_deploy
            True,  # no_tls
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
    mocked_wait_for_terminal_state: Mock,
    mocked_file_exists,
    cluster_name,
    cluster_namespace,
    resource_group_name,
    keyvault_resource_id,
    keyvault_sat_secret_name,
    disable_secret_rotation,
    rotation_poll_interval,
    tls_ca_path,
    tls_ca_key_path,
    tls_ca_dir,
    no_deploy,
    no_tls,
):
    call_kwargs = {
        "cmd": mocked_cmd,
        "cluster_name": cluster_name,
        "resource_group_name": resource_group_name,
        "keyvault_resource_id": keyvault_resource_id,
        "disable_secret_rotation": disable_secret_rotation,
        "no_deploy": no_deploy,
        "no_tls": no_tls,
        "no_progress": True,
    }
    if rotation_poll_interval:
        call_kwargs["rotation_poll_interval"] = rotation_poll_interval
    if cluster_namespace:
        call_kwargs["cluster_namespace"] = cluster_namespace
    if keyvault_sat_secret_name:
        call_kwargs["keyvault_sat_secret_name"] = keyvault_sat_secret_name
    if tls_ca_path:
        call_kwargs["tls_ca_path"] = tls_ca_path
    if tls_ca_key_path:
        call_kwargs["tls_ca_key_path"] = tls_ca_key_path
    if tls_ca_dir:
        call_kwargs["tls_ca_dir"] = tls_ca_dir

    result = init(**call_kwargs)
    nothing_to_do = all([not keyvault_resource_id, no_tls, no_deploy])
    if nothing_to_do:
        assert not result

    if keyvault_resource_id:
        assert result["csiDriver"]
        assert result["csiDriver"]["spAppId"]
        assert result["csiDriver"]["spObjectId"]
        assert result["csiDriver"]["keyVaultId"] == keyvault_resource_id
        assert (
            result["csiDriver"]["kvSatSecretName"] == keyvault_sat_secret_name
            if keyvault_sat_secret_name
            else DEFAULT_NAMESPACE
        )
        assert result["csiDriver"]["rotationPollInterval"] == rotation_poll_interval if rotation_poll_interval else "1h"
        assert result["csiDriver"]["enableSecretRotation"] == "false" if disable_secret_rotation else "true"

        mocked_prepare_sp.assert_called_once()
        assert mocked_prepare_sp.call_args.kwargs["deployment_name"]
        assert mocked_prepare_sp.call_args.kwargs["cmd"]

        mocked_prepare_keyvault_access_policy.assert_called_once()
        assert mocked_prepare_keyvault_access_policy.call_args.kwargs["subscription_id"]
        assert mocked_prepare_keyvault_access_policy.call_args.kwargs["keyvault_resource_id"] == keyvault_resource_id
        assert mocked_prepare_keyvault_access_policy.call_args.kwargs["sp_record"]

        mocked_prepare_keyvault_secret.assert_called_once()
        assert mocked_prepare_keyvault_secret.call_args.kwargs["cmd"]
        assert mocked_prepare_keyvault_secret.call_args.kwargs["deployment_name"]
        assert (
            mocked_prepare_keyvault_secret.call_args.kwargs["vault_uri"]
            == f"https://localhost/{keyvault_resource_id}/vault"
        )
        assert (
            mocked_prepare_keyvault_secret.call_args.kwargs["keyvault_sat_secret_name"] == keyvault_sat_secret_name
            if keyvault_sat_secret_name
            else DEFAULT_NAMESPACE
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
        assert (
            mocked_configure_cluster_secrets.call_args.kwargs["cluster_namespace"] == cluster_namespace
            if cluster_namespace
            else DEFAULT_NAMESPACE
        )
        assert mocked_configure_cluster_secrets.call_args.kwargs["cluster_secret_ref"] == CLUSTER_SECRET_REF
        assert (
            mocked_configure_cluster_secrets.call_args.kwargs["cluster_akv_secret_class_name"]
            == CLUSTER_SECRET_CLASS_NAME
        )
        assert (
            mocked_configure_cluster_secrets.call_args.kwargs["keyvault_sat_secret_name"] == keyvault_sat_secret_name
            if keyvault_sat_secret_name
            else DEFAULT_NAMESPACE
        )
        assert mocked_configure_cluster_secrets.call_args.kwargs["keyvault_resource_id"] == keyvault_resource_id
        assert mocked_configure_cluster_secrets.call_args.kwargs["sp_record"]
    else:
        if not nothing_to_do:
            assert "csiDriver" not in result
        mocked_prepare_sp.assert_not_called()
        mocked_prepare_keyvault_access_policy.assert_not_called()
        mocked_prepare_keyvault_secret.assert_not_called()
        mocked_provision_akv_csi_driver.assert_not_called()
        mocked_configure_cluster_secrets.assert_not_called()

    if not no_tls:
        assert result["tls"]["aioTrustConfigMap"]
        assert result["tls"]["aioTrustSecretName"]
        mocked_prepare_ca.assert_called_once()
        assert mocked_prepare_ca.call_args.kwargs["tls_ca_path"] == tls_ca_path
        assert mocked_prepare_ca.call_args.kwargs["tls_ca_key_path"] == tls_ca_key_path
        assert mocked_prepare_ca.call_args.kwargs["tls_ca_dir"] == tls_ca_dir

        mocked_cluster_tls.assert_called_once()
        assert (
            mocked_cluster_tls.call_args.kwargs["cluster_namespace"] == cluster_namespace
            if cluster_namespace
            else DEFAULT_NAMESPACE
        )
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
        assert result["deploymentName"]
        assert result["resourceGroup"] == resource_group_name
        assert result["clusterName"] == cluster_name
        assert result["clusterNamespace"]
        assert result["deploymentLink"]
        assert result["deploymentState"]

        mocked_deploy_template.assert_called_once()
        assert mocked_deploy_template.call_args.kwargs["template"]
        assert mocked_deploy_template.call_args.kwargs["parameters"]
        assert mocked_deploy_template.call_args.kwargs["subscription_id"]
        assert mocked_deploy_template.call_args.kwargs["resource_group_name"] == resource_group_name
        assert mocked_deploy_template.call_args.kwargs["deployment_name"]
        assert mocked_deploy_template.call_args.kwargs["cluster_name"] == cluster_name
        assert (
            mocked_deploy_template.call_args.kwargs["cluster_namespace"] == cluster_namespace
            if cluster_namespace
            else DEFAULT_NAMESPACE
        )
    else:
        if not nothing_to_do:
            assert "deploymentName" not in result
            assert "resourceGroup" not in result
            assert "clusterName" not in result
            assert "clusterNamespace" not in result
            assert "deploymentLink" not in result
            assert "deploymentState" not in result
        mocked_deploy_template.assert_not_called()
