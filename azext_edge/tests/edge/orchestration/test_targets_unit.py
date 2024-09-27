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
ENABLEMENT_PARAM_CONVERSION_MAP = {"clusterName": "cluster_name", "kubernetesDistro": "kubernetes_distro", "trustConfig": "trust_config", "advancedConfig": "advanced_config"}


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
            # TODO - missing broker config
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


    enablement_template, enablement_parameters = targets.get_ops_enablement_template()
    # for parameter in enablement_parameters:
    #     if parameter in ENABLEMENT_PARAM_CONVERSION_MAP:
    #         assert target_scenario[ENABLEMENT_PARAM_CONVERSION_MAP[parameter]["value"]] == 


    #instance_template, instance_parameters = targets.get_ops_instance_template()
    import pdb; pdb.set_trace()
    if target_scenario.get("enable_fault_tolerance"):
        assert targets.advanced_config == {"edgeStorageAccelerator": {"faultToleranceEnabled": True}}

    if target_scenario.get("trust_settings"):
        assert targets.trust_config == {
            "source": "CustomerManaged",
            "settings": {
                "issuerKind": target_scenario["trust_settings"]["issuerKind"],
                "configMapKey": target_scenario["trust_settings"]["configMapKey"],
                "issuerName": target_scenario["trust_settings"]["issuerName"],
                "configMapName": target_scenario["trust_settings"]["configMapName"],
            },
        }
