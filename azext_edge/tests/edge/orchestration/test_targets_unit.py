# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------
from random import randint

import pytest

from azext_edge.edge.providers.orchestration.targets import (
    TRUST_ISSUER_KIND_KEY,
    TRUST_SETTING_KEYS,
    InitTargets,
    assemble_nargs_to_dict,
    get_insecure_listener,
    REGISTRY_API_VERSION,
)

from ...generators import generate_random_string
from .resources.conftest import get_resource_id


def build_target_scenario(cluster_name: str, resource_group_name: str, **kwargs):
    return {
        "cluster_name": cluster_name,
        "resource_group_name": resource_group_name,
        **kwargs,
    }


def get_trust_settings():
    return [
        f"{key}={generate_random_string()}" if key != TRUST_ISSUER_KIND_KEY else f"{key}=ClusterIssuer"
        for key in TRUST_SETTING_KEYS
    ]


K8S_NAME_KEYS = frozenset(["cluster_namespace", "custom_location_name", "instance_name"])
KEY_CONVERSION_MAP = {"enable_rsync_rules": "deploy_resource_sync_rules"}
KVP_KEYS = frozenset(["ops_config", "trust_settings"])
ENABLEMENT_PARAM_CONVERSION_MAP = {
    "clusterName": "cluster_name",
    "kubernetesDistro": "kubernetes_distro",
    "containerRuntimeSocket": "container_runtime_socket",
    "trustConfig": "trust_config",
    "schemaRegistryId": "schema_registry_resource_id",
    "advancedConfig": "advanced_config",
}
INSTANCE_PARAM_CONVERSION_MAP = {
    "clusterName": "cluster_name",
    "clusterNamespace": "cluster_namespace",
    "clusterLocation": "location",
    "customLocationName": "custom_location_name",
    "deployResourceSyncRules": "deploy_resource_sync_rules",
    "schemaRegistryId": "schema_registry_resource_id",
    "defaultDataflowinstanceCount": "dataflow_profile_instances",
    "brokerConfig": "broker_config",
    "trustConfig": "trust_config",
}


@pytest.mark.parametrize(
    "target_scenario",
    [
        build_target_scenario(cluster_name=generate_random_string(), resource_group_name=generate_random_string()),
        build_target_scenario(
            cluster_name=generate_random_string(),
            resource_group_name=generate_random_string(),
            schema_registry_resource_id=get_resource_id(
                resource_path="/schemaRegistries/myregistry",
                resource_group_name=generate_random_string(),
                resource_provider="Microsoft.DeviceRegistry",
            ),
            location=generate_random_string(),
            instance_name=generate_random_string(),
        ),
        build_target_scenario(
            cluster_name=generate_random_string(),
            resource_group_name=generate_random_string(),
            schema_registry_resource_id=get_resource_id(
                resource_path="/schemaRegistries/myregistry",
                resource_group_name=generate_random_string(),
                resource_provider="Microsoft.DeviceRegistry",
            ),
            location=generate_random_string(),
            custom_location_name=generate_random_string(),
            enable_rsync_rules=True,
            instance_name=generate_random_string(),
            instance_description=generate_random_string(),
            tags={generate_random_string(): generate_random_string()},
            enable_fault_tolerance=True,
            ops_config=[f"{generate_random_string()}={generate_random_string()}"],
            ops_version=generate_random_string(),
            trust_settings=get_trust_settings(),
            dataflow_profile_instances=randint(1, 10),
            broker_memory_profile=generate_random_string(),
            broker_service_type=generate_random_string(),
            broker_backend_partitions=randint(1, 10),
            broker_backend_workers=randint(1, 10),
            broker_backend_redundancy_factor=randint(1, 5),
            broker_frontend_workers=randint(1, 10),
            broker_frontend_replicas=randint(1, 10),
            add_insecure_listener=True,
            kubernetes_distro=generate_random_string(),
            container_runtime_socket=generate_random_string(),
            custom_broker_config={generate_random_string(): generate_random_string()},
        ),
    ],
)
def test_init_targets(target_scenario: dict):
    targets = InitTargets(**target_scenario)

    for scenario_key in target_scenario:
        targets_key = scenario_key
        if scenario_key in K8S_NAME_KEYS:
            target_scenario[scenario_key] = targets._sanitize_k8s_name(target_scenario[scenario_key])
        if scenario_key in KEY_CONVERSION_MAP:
            targets_key = KEY_CONVERSION_MAP[scenario_key]
        if scenario_key in KVP_KEYS:
            target_scenario[scenario_key] = assemble_nargs_to_dict(target_scenario[scenario_key])

        targets_value = getattr(targets, targets_key)

        assert (
            target_scenario[scenario_key] == targets_value
        ), f"{scenario_key} input mismatch with equivalent targets {targets_key} value."

    if target_scenario.get("enable_fault_tolerance"):
        assert targets.advanced_config == {"edgeStorageAccelerator": {"faultToleranceEnabled": True}}

    verify_user_trust_settings(targets, target_scenario)

    enablement_template, enablement_parameters = targets.get_ops_enablement_template()
    for parameter in enablement_parameters:
        targets_key = parameter
        if parameter in ENABLEMENT_PARAM_CONVERSION_MAP:
            targets_key = ENABLEMENT_PARAM_CONVERSION_MAP[parameter]
        assert enablement_parameters[parameter]["value"] == getattr(
            targets, targets_key
        ), f"{parameter} value mismatch with targets {targets_key} value."

    if targets.ops_config:
        aio_config_settings = enablement_template["variables"]["defaultAioConfigurationSettings"]
        for c in targets.ops_config:
            assert c in aio_config_settings
            assert aio_config_settings[c] == targets.ops_config[c]

    if targets.ops_version:
        assert enablement_template["variables"]["VERSIONS"]["aio"] == targets.ops_version

    extension_ids = [generate_random_string(), generate_random_string()]
    extension_config = {"schemaRegistry.values.resourceId": target_scenario.get("schema_registry_resource_id")}
    target_scenario_has_user_trust = target_scenario.get("trust_settings")
    if target_scenario_has_user_trust:
        extension_config["trustSource"] = "CustomerManaged"
        extension_config["trustBundleSettings.issuer.name"] = target_scenario["trust_settings"]["issuerName"]
        extension_config["trustBundleSettings.issuer.kind"] = target_scenario["trust_settings"]["issuerKind"]
        extension_config["trustBundleSettings.configMap.name"] = target_scenario["trust_settings"]["configMapName"]
        extension_config["trustBundleSettings.configMap.key"] = target_scenario["trust_settings"]["configMapKey"]
        targets.trust_config = None

    instance_template, instance_parameters = targets.get_ops_instance_template(extension_ids, extension_config)
    for parameter in instance_parameters:
        if parameter == "clExtentionIds":
            assert instance_parameters[parameter]["value"] == extension_ids
            continue
        targets_key = parameter
        if parameter in INSTANCE_PARAM_CONVERSION_MAP:
            targets_key = INSTANCE_PARAM_CONVERSION_MAP[parameter]
        assert instance_parameters[parameter]["value"] == getattr(
            targets, targets_key
        ), f"{parameter} value mismatch with targets {targets_key} value."

    assert instance_template["resources"]["aioInstance"]["properties"]["description"] == targets.instance_description

    assert (
        instance_template["resources"]["aioInstance"]["properties"]["schemaRegistryNamespace"]
        == f"[reference(parameters('schemaRegistryId'), '{REGISTRY_API_VERSION}').namespace]"
    )

    if targets.tags:
        assert instance_template["resources"]["aioInstance"]["tags"] == targets.tags

    if targets.instance_name:
        assert instance_template["resources"]["aioInstance"]["name"] == targets.instance_name
        assert instance_template["resources"]["broker"]["name"] == f"{targets.instance_name}/default"
        assert instance_template["resources"]["broker_authn"]["name"] == f"{targets.instance_name}/default/default"
        assert instance_template["resources"]["broker_listener"]["name"] == f"{targets.instance_name}/default/default"
        assert instance_template["resources"]["dataflow_profile"]["name"] == f"{targets.instance_name}/default"
        assert instance_template["resources"]["dataflow_endpoint"]["name"] == f"{targets.instance_name}/default"

    if targets.custom_broker_config:
        assert instance_template["resources"]["broker"]["properties"] == targets.custom_broker_config

    if targets.add_insecure_listener:
        assert instance_template["resources"]["broker_listener_insecure"] == get_insecure_listener(
            targets.instance_name, "default"
        )

    verify_user_trust_settings(targets, target_scenario)


def verify_user_trust_settings(targets: InitTargets, target_scenario: dict):
    target_scenario_has_user_trust = target_scenario.get("trust_settings")
    if not target_scenario_has_user_trust:
        assert targets.trust_config == {"source": "SelfSigned"}
        return

    assert targets.trust_config == {
        "source": "CustomerManaged",
        "settings": {
            "issuerKind": target_scenario["trust_settings"]["issuerKind"],
            "configMapKey": target_scenario["trust_settings"]["configMapKey"],
            "issuerName": target_scenario["trust_settings"]["issuerName"],
            "configMapName": target_scenario["trust_settings"]["configMapName"],
        },
    }
