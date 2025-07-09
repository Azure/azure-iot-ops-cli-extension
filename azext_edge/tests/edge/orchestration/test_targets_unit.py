# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------
from random import randint
from typing import Dict, List, Optional

import pytest
from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_edge.edge.providers.orchestration.common import (
    EXTENSION_TYPE_ACS,
    EXTENSION_TYPE_OPS,
    EXTENSION_TYPE_PLATFORM,
    EXTENSION_TYPE_SSC,
    EXTENSION_TYPE_TO_MONIKER_MAP,
)
from azext_edge.edge.providers.orchestration.targets import (
    TRUST_ISSUER_KIND_KEY,
    TRUST_SETTING_KEYS,
    InitTargets,
    get_default_acs_config,
    get_insecure_listener,
    get_merged_acs_config,
    parse_feature_kvp_nargs,
    parse_kvp_nargs,
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


def get_schema_registry_id():
    return get_resource_id(
        resource_path="/schemaRegistries/myregistry",
        resource_group_name=generate_random_string(),
        resource_provider="Microsoft.DeviceRegistry",
    )


K8S_NAME_KEYS = frozenset(["cluster_namespace", "custom_location_name", "instance_name"])
KEY_CONVERSION_MAP = {"enable_rsync_rules": "deploy_resource_sync_rules"}
KVP_KEYS = frozenset(["ops_config", "ssc_config", "acs_config", "trust_settings"])
ENABLEMENT_PARAM_CONVERSION_MAP = {
    "clusterName": "cluster_name",
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
INSTANCE_FEATURE_MAP = {"connectors.settings.preview=Enabled": {"connectors": {"settings": {"preview": "Enabled"}}}}
INSTANCE_FEATURE_ATTR = "instance_features"


@pytest.mark.parametrize(
    "target_scenario",
    [
        build_target_scenario(cluster_name=generate_random_string(), resource_group_name=generate_random_string()),
        build_target_scenario(
            cluster_name=generate_random_string(),
            resource_group_name=generate_random_string(),
            schema_registry_resource_id=get_schema_registry_id(),
            location=generate_random_string(),
            instance_name=generate_random_string(),
            custom_broker_config={generate_random_string(): generate_random_string()},
        ),
        build_target_scenario(
            cluster_name=generate_random_string(),
            resource_group_name=generate_random_string(),
            schema_registry_resource_id=get_schema_registry_id(),
            user_trust=True,
        ),
        build_target_scenario(
            cluster_name=generate_random_string(),
            resource_group_name=generate_random_string(),
            schema_registry_resource_id=get_schema_registry_id(),
            cluster_namespace=generate_random_string(),
            location=generate_random_string(),
            custom_location_name=generate_random_string(),
            enable_rsync_rules=True,
            instance_name=generate_random_string(),
            instance_description=generate_random_string(),
            tags={generate_random_string(): generate_random_string()},
            enable_fault_tolerance=True,
            ops_config=[f"{generate_random_string()}={generate_random_string()}"],
            ops_version=generate_random_string(),
            ops_train=generate_random_string(),
            dataflow_profile_instances=randint(1, 10),
            broker_memory_profile=generate_random_string(),
            broker_backend_partitions=randint(1, 10),
            broker_backend_workers=randint(1, 10),
            broker_backend_redundancy_factor=randint(2, 5),
            broker_frontend_workers=randint(1, 10),
            broker_frontend_replicas=randint(1, 10),
            add_insecure_listener=True,
            trust_settings=get_trust_settings(),
            instance_features=["connectors.settings.preview=Enabled"],
        ),
        build_target_scenario(
            cluster_name=generate_random_string(),
            resource_group_name=generate_random_string(),
            ssc_config=[f"{generate_random_string()}={generate_random_string()}"],
            ssc_version=generate_random_string(),
            ssc_train=generate_random_string(),
            acs_config=[f"{generate_random_string()}={generate_random_string()}"],
            acs_version=generate_random_string(),
            acs_train=generate_random_string(),
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
            target_scenario[scenario_key] = parse_kvp_nargs(target_scenario[scenario_key])
        if scenario_key == INSTANCE_FEATURE_ATTR:
            target_scenario[scenario_key] = parse_feature_kvp_nargs(target_scenario[scenario_key])

        targets_value = getattr(targets, targets_key)

        assert (
            target_scenario[scenario_key] == targets_value
        ), f"{scenario_key} input mismatch with equivalent targets {targets_key} value."

    expected_acs_config = {"edgeStorageConfiguration.create": "true", "feature.diskStorageClass": "default,local-path"}
    if target_scenario.get("enable_fault_tolerance"):
        assert targets.advanced_config == {"edgeStorageAccelerator": {"faultToleranceEnabled": True}}
        expected_acs_config["feature.diskStorageClass"] = "acstor-arccontainerstorage-storage-pool"
        expected_acs_config["acstorConfiguration.create"] = "true"
        expected_acs_config["acstorConfiguration.properties.diskMountPoint"] = "/mnt"

    enablement_template, enablement_parameters = targets.get_ops_enablement_template()
    verify_trust_config(
        target_scenario=target_scenario,
        parameters=enablement_parameters,
        template=enablement_template,
    )

    for parameter in enablement_parameters:
        targets_key = parameter
        if parameter in ENABLEMENT_PARAM_CONVERSION_MAP:
            targets_key = ENABLEMENT_PARAM_CONVERSION_MAP[parameter]
        assert enablement_parameters[parameter]["value"] == getattr(
            targets, targets_key
        ), f"{parameter} value mismatch with targets {targets_key} value."

    assert_version_attr(
        variables=enablement_template["variables"],
        key="secretStore",
        train=targets.ssc_train,
        version=targets.ssc_version,
    )

    expected_ssc_config = {
        "rotationPollIntervalInSeconds": "120",
        "validatingAdmissionPolicies.applyPolicies": "false",
    }
    ssc_config_settings = enablement_template["resources"]["secret_store_extension"]["properties"][
        "configurationSettings"
    ]
    assert_extension_config(
        settings=ssc_config_settings, expected_base_config=expected_ssc_config, custom_config=targets.ssc_config
    )

    assert_version_attr(
        variables=enablement_template["variables"],
        key="containerStorage",
        train=targets.acs_train,
        version=targets.acs_version,
    )

    acs_config_settings = enablement_template["resources"]["container_storage_extension"]["properties"][
        "configurationSettings"
    ]
    assert_extension_config(
        settings=acs_config_settings, expected_base_config=expected_acs_config, custom_config=targets.acs_config
    )

    extension_ids = [generate_random_string(), generate_random_string()]

    instance_template, instance_parameters = targets.get_ops_instance_template(extension_ids)
    verify_trust_config(
        target_scenario=target_scenario,
        parameters=instance_parameters,
    )
    verify_broker_config(
        target_scenario=target_scenario,
        parameters=instance_parameters,
    )

    assert_version_attr(
        variables=instance_template["variables"],
        key="iotOperations",
        train=targets.ops_train,
        version=targets.ops_version,
    )

    if targets.ops_config:
        aio_config_settings = instance_template["variables"]["defaultAioConfigurationSettings"]
        for c in targets.ops_config:
            assert aio_config_settings[c] == targets.ops_config[c]

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

    assert instance_template["resources"]["aioInstance"]["properties"]["schemaRegistryRef"] == {
        "resourceId": "[parameters('schemaRegistryId')]"
    }

    assert instance_template["resources"]["aioInstance"]["properties"]["features"] == targets.instance_features

    if targets.tags:
        assert instance_template["resources"]["aioInstance"]["tags"] == targets.tags

    if targets.instance_name:
        assert instance_template["resources"]["aioInstance"]["name"] == targets.instance_name
        assert instance_template["resources"]["broker"]["name"] == f"{targets.instance_name}/default"
        assert instance_template["resources"]["broker_authn"]["name"] == f"{targets.instance_name}/default/default"
        assert instance_template["resources"]["broker_listener"]["name"] == f"{targets.instance_name}/default/default"
        assert instance_template["resources"]["dataflow_profile"]["name"] == f"{targets.instance_name}/default"
        assert instance_template["resources"]["dataflow_endpoint"]["name"] == f"{targets.instance_name}/default"
        assert instance_template["outputs"]["aio"]["value"]["name"] == targets.instance_name

    if targets.custom_broker_config:
        assert instance_template["resources"]["broker"]["properties"] == targets.custom_broker_config

    if targets.add_insecure_listener:
        assert instance_template["resources"]["broker_listener_insecure"] == get_insecure_listener(
            targets.instance_name, "default"
        )


def verify_broker_config(target_scenario: dict, parameters):
    assert "serviceType" not in parameters["brokerConfig"]["value"]
    for target_pair in [
        ("broker_frontend_replicas", "frontendReplicas"),
        ("broker_frontend_workers", "frontendWorkers"),
        ("broker_backend_redundancy_factor", "backendRedundancyFactor"),
        ("broker_backend_workers", "backendWorkers"),
        ("broker_backend_partitions", "backendPartitions"),
        ("broker_memory_profile", "memoryProfile"),
    ]:
        if target_pair[0] in target_scenario:
            assert parameters["brokerConfig"]["value"][target_pair[1]] == target_scenario[target_pair[0]]


def verify_trust_config(target_scenario: dict, parameters: dict, template: Optional[dict] = None):
    user_trust = target_scenario.get("user_trust")
    trust_settings = target_scenario.get("trust_settings")

    expected_payload = {"source": "SelfSigned"}
    if user_trust:
        expected_payload["source"] = "CustomerManaged"
        if template:
            # TODO @c-ryan-k - Enablement template should not require "settings" for customer managed trust config
            assert template["definitions"]["_1.CustomerManaged"]["properties"]["settings"]["nullable"]

    if trust_settings:
        expected_payload["source"] = "CustomerManaged"
        expected_payload["settings"] = {
            "issuerKind": trust_settings["issuerKind"],
            "configMapKey": trust_settings["configMapKey"],
            "issuerName": trust_settings["issuerName"],
            "configMapName": trust_settings["configMapName"],
        }

    if parameters:
        assert parameters["trustConfig"]["value"] == expected_payload


def test_get_extension_versions():
    def _assert_version_map(extension_types: List[str], version_map: dict):
        for ext_type in extension_types:
            moniker = EXTENSION_TYPE_TO_MONIKER_MAP[ext_type]
            assert version_map[moniker]["version"]
            assert version_map[moniker]["train"]
        assert len(extension_types) == len(version_map)

    targets = InitTargets(generate_random_string(), generate_random_string())
    enablement_version_map = targets.get_extension_versions()
    enablement_types = [EXTENSION_TYPE_PLATFORM, EXTENSION_TYPE_ACS, EXTENSION_TYPE_SSC]
    _assert_version_map(enablement_types, enablement_version_map)

    create_version_map = targets.get_extension_versions(False)
    create_types = [EXTENSION_TYPE_OPS]
    _assert_version_map(create_types, create_version_map)

    combined_version_map = {**enablement_version_map, **create_version_map}
    _assert_version_map(enablement_types + create_types, combined_version_map)


def assert_extension_config(
    settings: Dict[str, str], expected_base_config: Dict[str, str], custom_config: Optional[Dict[str, str]] = None
):
    for c in expected_base_config:
        assert settings[c] == expected_base_config[c]
    custom_config_len = 0
    if custom_config:
        custom_config_len = len(custom_config)
        for c in custom_config:
            assert settings[c] == custom_config[c]
    assert len(settings) == (len(expected_base_config) + custom_config_len)


def assert_version_attr(
    variables: Dict[
        str,
        str,
    ],
    key: str,
    version: Optional[str] = None,
    train: Optional[str] = None,
):
    if version:
        assert variables["VERSIONS"][key] == version
    if train:
        assert variables["TRAINS"][key] == train


@pytest.mark.parametrize(
    "enable_fault_tolerance",
    [True, False],
)
@pytest.mark.parametrize(
    "acs_config",
    [
        None,
        {"test": generate_random_string()},
        {"feature.diskStorageClass": "default,local-path"},
        {"feature.diskStorageClass": ""},
    ],
)
def test_get_merged_acs_config(enable_fault_tolerance: bool, acs_config: Optional[List[str]]):
    targets = InitTargets(generate_random_string(), generate_random_string())
    targets.enable_fault_tolerance = enable_fault_tolerance
    targets.acs_config = acs_config

    if (
        acs_config
        and acs_config.get("feature.diskStorageClass") is not None
        and not acs_config.get("feature.diskStorageClass")
    ):
        with pytest.raises(
            InvalidArgumentValueError,
            match=r"^Provided ACS config does not contain a 'feature.diskStorageClass' value:",
        ):
            get_merged_acs_config(acs_config=acs_config, enable_fault_tolerance=enable_fault_tolerance)
    else:
        result = get_merged_acs_config(
            acs_config=acs_config,
            enable_fault_tolerance=enable_fault_tolerance,
        )

        default_config = get_default_acs_config(enable_fault_tolerance=enable_fault_tolerance)
        for key in [
            "edgeStorageConfiguration.create",
            "feature.diskStorageClass",
            "acstorConfiguration.create",
            "acstorConfiguration.properties.diskMountPoint",
            "test",
        ]:
            assert result.get(key) == (
                acs_config.get(key, default_config.get(key)) if acs_config else default_config.get(key)
            )


@pytest.mark.parametrize(
    "target_scenario, expected_error",
    [
        (
            build_target_scenario(
                cluster_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                broker_backend_redundancy_factor=1,
            ),
            "backendRedundancyFactor value range min:2 max:5",
        ),
        (
            build_target_scenario(
                cluster_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                broker_backend_redundancy_factor=1,
                broker_frontend_replicas=20,
                broker_backend_workers=20,
            ),
            "frontendReplicas value range min:1 max:16\n"
            "backendRedundancyFactor value range min:2 max:5\n"
            "backendWorkers value range min:1 max:16",
        ),
    ],
)
def test_broker_config_limits(target_scenario: dict, expected_error: str):
    with pytest.raises(
        InvalidArgumentValueError,
    ) as e:
        InitTargets(**target_scenario)
    assert str(e.value) == expected_error
