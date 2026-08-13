# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------
from contextlib import nullcontext
from random import randint
from typing import Dict, Optional, Union
from unittest.mock import Mock

import pytest
from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_edge.edge.providers.orchestration.common import (
    EXTENSION_MONIKER_CM,
    EXTENSION_MONIKER_OPS,
    EXTENSION_MONIKER_SSC,
)
from azext_edge.edge.providers.orchestration.targets import (
    CM_AUTHORIZED_SECRETS_ALL_CONFIG,
    CM_SECRET_TARGETS_ENABLED_CONFIG,
    TRUST_ISSUER_KIND_KEY,
    TRUST_SETTING_KEYS,
    ExtensionConfig,
    ExtensionConfigManager,
    InitTargets,
    InstancePhase,
    get_default_cl_name,
    get_default_cm_config,
    get_default_ssc_config,
    get_insecure_listener,
    parse_feature_kvp_nargs,
    parse_kvp_nargs,
)

from ...generators import generate_random_string
from .resources.conftest import ADR_RP, STORAGE_RP, get_resource_id

ExpectedExc = Optional[Union[type[Exception], tuple[type[Exception], ...]]]

# Test constants
DEFAULT_RESOURCE_GROUP = "myresourcegroup"
DEFAULT_NAMESPACE_PATH = "/namespaces/mynamespace"
DEFAULT_SCHEMA_REGISTRY_PATH = "/schemaRegistries/myregistry"

# Persistence mode constants
PERSIST_MODE_ALL = "All"
PERSIST_MODE_CUSTOM = "Custom"
PERSIST_MODE_NONE = "None"
PERSIST_MODE_KEYS = ["stateStore", "retain", "subscriberQueue"]

# Broker config limits
BROKER_BACKEND_REDUNDANCY_MIN = 2
BROKER_BACKEND_REDUNDANCY_MAX = 5
BROKER_WORKERS_MAX = 16
BROKER_REPLICAS_MAX = 16

# Keys for different attribute categories
K8S_NAME_KEYS = frozenset(["cluster_namespace", "custom_location_name", "instance_name"])
PARSEABLE_KVP_KEYS = frozenset(["trust_settings", "persist_mode"])
EXTENSION_ATTR_KEYS = frozenset(
    [
        "ops_config",
        "ops_version",
        "ops_train",
        "ssc_config",
        "ssc_version",
        "ssc_train",
        "cm_config",
        "cm_version",
        "cm_train",
    ]
)

# Parameter mapping
ENABLEMENT_PARAM_CONVERSION_MAP = {
    "clusterName": "cluster_name",
    "trustConfig": "trust_config",
}
INSTANCE_PARAM_CONVERSION_MAP = {
    "clusterName": "cluster_name",
    "clusterNamespace": "cluster_namespace",
    "clusterLocation": "location",
    "customLocationName": "custom_location_name",
    "schemaRegistryId": "schema_registry_resource_id",
    "adrNamespaceId": "adr_namespace_resource_id",
    "defaultDataflowInstanceCount": "dataflow_profile_instances",
    "brokerConfig": "broker_config",
    "trustConfig": "trust_config",
}
INSTANCE_FEATURE_ATTR = "instance_features"


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
        resource_path=DEFAULT_SCHEMA_REGISTRY_PATH,
        resource_group_name=generate_random_string(),
        resource_provider=ADR_RP,
    )


def get_ns_resource_id(resource_group_name: Optional[str] = None):
    return get_resource_id(
        resource_path=DEFAULT_NAMESPACE_PATH,
        resource_group_name=resource_group_name or generate_random_string(),
        resource_provider=ADR_RP,
    )


def assert_parameter_matches_targets(parameters: dict, targets: InitTargets, conversion_map: dict):
    for parameter, parameter_value in parameters.items():
        if parameter == "clExtensionIds":
            continue

        targets_key = conversion_map.get(parameter, parameter)
        expected_value = getattr(targets, targets_key)
        actual_value = parameter_value["value"] if "value" in parameter_value else parameter_value

        assert actual_value == expected_value, (
            f"{parameter} value mismatch with targets {targets_key} value. "
            f"Expected: {expected_value}, Got: {actual_value}"
        )


def assert_instance_names(template: dict, instance_name: str):
    expected_names = {
        "aioInstance": instance_name,
        "broker": f"{instance_name}/default",
        "brokerAuthn": f"{instance_name}/default/default",
        "brokerListener": f"{instance_name}/default/default",
        "dataflowProfile": f"{instance_name}/default",
        "dataflowEndpoint": f"{instance_name}/default",
    }

    for resource_key, expected_name in expected_names.items():
        if resource_key in template["resources"]:
            assert template["resources"][resource_key]["name"] == expected_name

    if "outputs" in template and "aio" in template["outputs"]:
        assert template["outputs"]["aio"]["value"]["name"] == instance_name


def assert_extension_config(
    settings: Dict[str, str], expected_base_config: Dict[str, str], custom_config: Optional[Dict[str, str]] = None
):
    merged_config = {**expected_base_config, **(custom_config or {})}
    assert settings == merged_config


def assert_version_attr(variables: dict, key: str, version: Optional[str] = None, train: Optional[str] = None):
    if version:
        assert variables["VERSIONS"][key] == version
    if train:
        assert variables["TRAINS"][key] == train


def verify_broker_config(target_scenario: dict, parameters: dict):
    broker_config = parameters["brokerConfig"]["value"]
    assert "serviceType" not in broker_config

    broker_config_mapping = [
        ("broker_frontend_replicas", "frontendReplicas"),
        ("broker_frontend_workers", "frontendWorkers"),
        ("broker_backend_redundancy_factor", "backendRedundancyFactor"),
        ("broker_backend_workers", "backendWorkers"),
        ("broker_backend_partitions", "backendPartitions"),
        ("broker_memory_profile", "memoryProfile"),
    ]

    for target_key, broker_key in broker_config_mapping:
        if target_key in target_scenario:
            assert broker_config[broker_key] == target_scenario[target_key]

    if "persist_max_size" not in target_scenario:
        assert "persistence" not in broker_config
        return

    persistence = broker_config["persistence"]
    assert persistence["maxSize"] == target_scenario["persist_max_size"]

    if "persist_pvc_sc" in target_scenario:
        assert persistence["persistentVolumeClaimSpec"] == {
            "storageClassName": target_scenario["persist_pvc_sc"],
            "accessModes": ["ReadWriteOncePod"],
        }

    explicit_mode_keys = {key: False for key in PERSIST_MODE_KEYS}

    if "persist_mode" in target_scenario:
        persist_mode = target_scenario["persist_mode"]
        if isinstance(persist_mode, list):
            persist_mode = parse_kvp_nargs(persist_mode)

        for k, v in persist_mode.items():
            expected_payload = {"mode": v}
            if v == PERSIST_MODE_CUSTOM:
                expected_payload[k + "Settings"] = {"dynamic": {"mode": "Enabled"}}

            assert persistence[k] == expected_payload
            explicit_mode_keys[k] = True

    for k, was_set in explicit_mode_keys.items():
        if not was_set:
            assert persistence[k] == {
                "mode": PERSIST_MODE_CUSTOM,
                k + "Settings": {"dynamic": {"mode": "Enabled"}},
            }


def verify_trust_config(target_scenario: dict, parameters: dict, template: Optional[dict] = None):
    user_trust = target_scenario.get("user_trust")
    trust_settings = target_scenario.get("trust_settings")

    if trust_settings and isinstance(trust_settings, list):
        trust_settings = parse_kvp_nargs(trust_settings)

    expected_payload = {"source": "SelfSigned"}
    if user_trust:
        expected_payload["source"] = "CustomerManaged"
        if template:
            assert template["definitions"]["_1.CustomerManaged"]["properties"]["settings"]["nullable"]

    if trust_settings:
        expected_payload["source"] = "CustomerManaged"
        expected_payload["settings"] = trust_settings

    if parameters:
        assert parameters["trustConfig"]["value"] == expected_payload


def verify_extension_configs_in_manager(targets: InitTargets, target_scenario: dict) -> dict:
    """Verify all extension configurations are properly stored in extension_manager."""
    parsed_configs = {}

    extension_scenarios = [
        (EXTENSION_MONIKER_OPS, "ops_config", "ops_version", "ops_train"),
        (EXTENSION_MONIKER_SSC, "ssc_config", "ssc_version", "ssc_train"),
        (EXTENSION_MONIKER_CM, "cm_config", "cm_version", "cm_train"),
    ]

    for moniker, config_key, version_key, train_key in extension_scenarios:
        parsed_config = parse_kvp_nargs(target_scenario.get(config_key))
        parsed_configs[moniker] = parsed_config

        ext = targets.extension_manager.extensions.get(moniker)
        if any(target_scenario.get(k) for k in [config_key, version_key, train_key]):
            assert ext is not None
            assert ext.version == target_scenario.get(version_key)
            assert ext.train == target_scenario.get(train_key)
            assert ext.config == parsed_config

    return parsed_configs


def verify_extension_in_template(
    template: dict, moniker: str, expected_config: dict, custom_config: dict = None, ext: ExtensionConfig = None
):
    if not ext:
        return

    resource_map = {
        "certManager": "certManagerExtension",
        "secretStore": "secretStoreExtension",
    }

    if ext.version or ext.train:
        assert_version_attr(template["variables"], moniker, ext.version, ext.train)

    if moniker in resource_map and resource_map[moniker] in template.get("resources", {}):
        settings = template["resources"][resource_map[moniker]]["properties"]["configurationSettings"]
        assert_extension_config(settings, expected_config, custom_config)


@pytest.mark.parametrize(
    "target_scenario",
    [
        # Basic scenario
        build_target_scenario(
            cluster_name=generate_random_string(),
            resource_group_name=generate_random_string(),
        ),
        # Schema registry and custom broker config
        build_target_scenario(
            cluster_name=generate_random_string(),
            resource_group_name=generate_random_string(),
            schema_registry_resource_id=get_schema_registry_id(),
            location=generate_random_string(),
            instance_name=generate_random_string(),
            custom_broker_config={generate_random_string(): generate_random_string()},
        ),
        # User trust - with namespace in same RG as instance
        build_target_scenario(
            cluster_name=generate_random_string(),
            resource_group_name=DEFAULT_RESOURCE_GROUP,
            schema_registry_resource_id=get_schema_registry_id(),
            adr_namespace_resource_id=get_ns_resource_id(DEFAULT_RESOURCE_GROUP),
            user_trust=True,
        ),
        # Cross-RG namespace support - namespace in different RG than instance
        build_target_scenario(
            cluster_name=generate_random_string(),
            resource_group_name=DEFAULT_RESOURCE_GROUP,  # Instance in DEFAULT_RESOURCE_GROUP
            schema_registry_resource_id=get_schema_registry_id(),
            adr_namespace_resource_id=get_ns_resource_id("different-namespace-rg"),  # Namespace in different RG
        ),
        # Persistence configuration
        build_target_scenario(
            instance_name=generate_random_string(),
            cluster_name=generate_random_string(),
            resource_group_name=DEFAULT_RESOURCE_GROUP,
            schema_registry_resource_id=get_schema_registry_id(),
            adr_namespace_resource_id=get_ns_resource_id(DEFAULT_RESOURCE_GROUP),
            persist_max_size="10Gi",
            persist_pvc_sc=generate_random_string(),
        ),
        # Persistence modes
        build_target_scenario(
            instance_name=generate_random_string(),
            cluster_name=generate_random_string(),
            resource_group_name=DEFAULT_RESOURCE_GROUP,
            schema_registry_resource_id=get_schema_registry_id(),
            adr_namespace_resource_id=get_ns_resource_id(DEFAULT_RESOURCE_GROUP),
            persist_max_size="10Gi",
            persist_mode=[
                f"stateStore={PERSIST_MODE_ALL}",
                f"retain={PERSIST_MODE_CUSTOM}",
                f"subscriberQueue={PERSIST_MODE_NONE}",
            ],
        ),
        # Full configuration with all extensions
        build_target_scenario(
            cluster_name=generate_random_string(),
            resource_group_name=generate_random_string(),
            schema_registry_resource_id=get_schema_registry_id(),
            cluster_namespace=generate_random_string(),
            location=generate_random_string(),
            custom_location_name=generate_random_string(),
            instance_name=generate_random_string(),
            instance_description=generate_random_string(),
            tags={generate_random_string(): generate_random_string()},
            ops_config=[f"{generate_random_string()}={generate_random_string()}"],
            ops_version=generate_random_string(),
            ops_train=generate_random_string(),
            cm_config=[f"{generate_random_string()}={generate_random_string()}"],
            cm_version=generate_random_string(),
            cm_train=generate_random_string(),
            ssc_config=[f"{generate_random_string()}={generate_random_string()}"],
            ssc_version=generate_random_string(),
            ssc_train=generate_random_string(),
            dataflow_profile_instances=randint(1, 10),
            broker_memory_profile=generate_random_string(),
            broker_backend_partitions=randint(1, 10),
            broker_backend_workers=randint(1, BROKER_WORKERS_MAX),
            broker_backend_redundancy_factor=randint(BROKER_BACKEND_REDUNDANCY_MIN, BROKER_BACKEND_REDUNDANCY_MAX),
            broker_frontend_workers=randint(1, BROKER_WORKERS_MAX),
            broker_frontend_replicas=randint(1, BROKER_REPLICAS_MAX),
            add_insecure_listener=True,
            trust_settings=get_trust_settings(),
            instance_features=["connectors.settings.preview=Enabled"],
        ),
    ],
)
def test_init_targets(target_scenario: dict, mocked_feature_keys: Mock):
    """Test InitTargets initialization and template generation with various scenarios."""
    targets = InitTargets(**target_scenario)

    # Verify extension configs are properly stored
    parsed_configs = verify_extension_configs_in_manager(targets, target_scenario)

    # Verify non-extension target attributes
    for scenario_key, expected_value in target_scenario.items():
        if scenario_key in EXTENSION_ATTR_KEYS:
            continue

        if scenario_key in K8S_NAME_KEYS:
            expected_value = targets._sanitize_k8s_name(expected_value)
        elif scenario_key in PARSEABLE_KVP_KEYS:
            expected_value = parse_kvp_nargs(expected_value)
        elif scenario_key == INSTANCE_FEATURE_ATTR:
            expected_value = parse_feature_kvp_nargs(expected_value)

        targets_value = getattr(targets, scenario_key)
        assert (
            targets_value == expected_value
        ), f"{scenario_key} input mismatch with targets value. Expected: {expected_value}, Got: {targets_value}"

    # Test enablement template
    enablement_template, enablement_parameters = targets.get_ops_enablement_template()
    verify_trust_config(target_scenario, enablement_parameters, enablement_template)
    assert_parameter_matches_targets(enablement_parameters, targets, ENABLEMENT_PARAM_CONVERSION_MAP)

    # Verify extension configs in enablement template
    for moniker, base_config_getter in [
        (EXTENSION_MONIKER_SSC, get_default_ssc_config),
        (EXTENSION_MONIKER_CM, get_default_cm_config),
    ]:
        ext = targets.extension_manager.extensions.get(moniker)
        if ext:
            moniker_key = "secretStore" if moniker == EXTENSION_MONIKER_SSC else "certManager"
            verify_extension_in_template(
                enablement_template, moniker_key, base_config_getter(), parsed_configs[moniker], ext
            )

    # Test instance template
    extension_ids = [generate_random_string(), generate_random_string()]
    instance_template, instance_parameters = targets.get_ops_instance_template(extension_ids)

    verify_trust_config(target_scenario, instance_parameters)
    verify_broker_config(target_scenario, instance_parameters)

    # Verify IoT Operations extension config
    ops_ext = targets.extension_manager.extensions.get(EXTENSION_MONIKER_OPS)
    if ops_ext:
        if ops_ext.version or ops_ext.train:
            assert_version_attr(instance_template["variables"], "iotOperations", ops_ext.version, ops_ext.train)

        if parsed_configs[EXTENSION_MONIKER_OPS]:
            aio_config = instance_template["variables"]["defaultAioConfigurationSettings"]
            for key, value in parsed_configs[EXTENSION_MONIKER_OPS].items():
                assert aio_config[key] == value

    assert instance_parameters["clExtensionIds"]["value"] == extension_ids
    assert_parameter_matches_targets(instance_parameters, targets, INSTANCE_PARAM_CONVERSION_MAP)

    # Verify instance properties
    aio_instance = instance_template["resources"]["aioInstance"]
    assert aio_instance["properties"]["description"] == targets.instance_description
    assert aio_instance["properties"]["features"] == targets.instance_features

    if targets.tags:
        assert aio_instance["tags"] == targets.tags

    if targets.instance_name:
        assert_instance_names(instance_template, targets.instance_name)

    if targets.custom_broker_config:
        assert instance_template["resources"]["broker"]["properties"] == targets.custom_broker_config

    if targets.add_insecure_listener:
        assert instance_template["resources"]["brokerListenerInsecure"] == get_insecure_listener(
            targets.instance_name, "default"
        )

    # Test extension versions are properly exposed
    enablement_versions = targets.get_extension_versions()
    instance_versions = targets.get_extension_versions(for_enablement=False)

    if ops_ext:
        assert instance_versions.get("iotOperations")
    if targets.extension_manager.extensions.get(EXTENSION_MONIKER_CM):
        assert enablement_versions.get("certManager")
    if targets.extension_manager.extensions.get(EXTENSION_MONIKER_SSC):
        assert enablement_versions.get("secretStore")


@pytest.mark.parametrize(
    "target_scenario",
    [
        build_target_scenario(
            cluster_name=generate_random_string(),
            resource_group_name=generate_random_string(),
            schema_registry_resource_id=get_schema_registry_id(),
            instance_features=["opcua.mode=Stable"],
        ),
    ],
)
def test_init_targets_opcua_mode(target_scenario: dict):
    """Verify opcua.mode feature flows through InitTargets into the
    ARM template against the real COMPAT_FEAT_KEY_SET."""
    targets = InitTargets(**target_scenario)

    expected_features = parse_feature_kvp_nargs(target_scenario["instance_features"])
    assert targets.instance_features == expected_features

    extension_ids = [generate_random_string(), generate_random_string()]
    instance_template, _instance_parameters = targets.get_ops_instance_template(extension_ids)

    aio_instance = instance_template["resources"]["aioInstance"]
    assert aio_instance["properties"]["features"] == expected_features


@pytest.mark.parametrize(
    "cm_config, expected_config",
    [
        (None, get_default_cm_config()),
        (
            [f"{CM_SECRET_TARGETS_ENABLED_CONFIG}=true"],
            {**get_default_cm_config(), CM_SECRET_TARGETS_ENABLED_CONFIG: "true"},
        ),
        (
            [f"{CM_AUTHORIZED_SECRETS_ALL_CONFIG}=true"],
            {**get_default_cm_config(), CM_AUTHORIZED_SECRETS_ALL_CONFIG: "true"},
        ),
        (
            [
                f"{CM_SECRET_TARGETS_ENABLED_CONFIG}=true",
                f"{CM_AUTHORIZED_SECRETS_ALL_CONFIG}=true",
            ],
            {
                **get_default_cm_config(),
                CM_SECRET_TARGETS_ENABLED_CONFIG: "true",
                CM_AUTHORIZED_SECRETS_ALL_CONFIG: "true",
            },
        ),
    ],
)
def test_cert_manager_secret_target_config(cm_config, expected_config):
    targets = InitTargets(
        cluster_name=generate_random_string(),
        resource_group_name=generate_random_string(),
        cm_config=cm_config,
    )

    enablement_template, _ = targets.get_ops_enablement_template()
    settings = enablement_template["resources"]["certManagerExtension"]["properties"]["configurationSettings"]

    assert settings == expected_config


def test_extension_config_manager():
    """Test ExtensionConfigManager functionality comprehensively."""
    manager = ExtensionConfigManager()

    # Test registration and basic functionality
    custom_config = {"key1": "value1", "key2": "value2"}
    manager.register_extension(
        moniker=EXTENSION_MONIKER_CM,
        version="1.0.0",
        train="stable",
        user_config=custom_config,
        default_config_getter=get_default_cm_config,
    )

    assert EXTENSION_MONIKER_CM in manager.extensions
    ext = manager.extensions[EXTENSION_MONIKER_CM]
    assert ext == ExtensionConfig(
        moniker=EXTENSION_MONIKER_CM,
        version="1.0.0",
        train="stable",
        config=custom_config,
        default_config_getter=get_default_cm_config,
    )

    # Test merged config
    merged = manager.get_merged_config(EXTENSION_MONIKER_CM)
    assert merged == {**get_default_cm_config(), **custom_config}

    # Test merged config with template defaults
    template_defaults = {"template_key": "template_value", "key1": "original"}
    merged = manager.get_merged_config(EXTENSION_MONIKER_CM, template_defaults)
    assert merged == {**template_defaults, **custom_config}

    # Test non-existent extension
    assert manager.get_merged_config("non_existent") == {}

    # Test template application for all extension types
    manager.register_extension(
        moniker=EXTENSION_MONIKER_OPS, version="2.0.0", train="dev", user_config={"ops_custom": "ops_value"}
    )

    manager.register_extension(
        moniker=EXTENSION_MONIKER_SSC,
        version="1.5.0",
        train="preview",
        user_config={"ssc_custom": "ssc_value"},
        default_config_getter=get_default_ssc_config,
    )

    # Test enablement template
    enablement_template = {
        "variables": {},
        "resources": {"certManagerExtension": {"properties": {}}, "secretStoreExtension": {"properties": {}}},
    }
    manager.apply_to_template(enablement_template, "enablement")

    assert enablement_template["variables"]["VERSIONS"]["certManager"] == "1.0.0"
    assert enablement_template["variables"]["TRAINS"]["certManager"] == "stable"
    assert enablement_template["resources"]["certManagerExtension"]["properties"]["configurationSettings"] == {
        **get_default_cm_config(),
        **custom_config,
    }

    assert enablement_template["variables"]["VERSIONS"]["secretStore"] == "1.5.0"
    assert enablement_template["variables"]["TRAINS"]["secretStore"] == "preview"
    assert enablement_template["resources"]["secretStoreExtension"]["properties"]["configurationSettings"] == {
        **get_default_ssc_config(),
        "ssc_custom": "ssc_value",
    }

    # Test instance template
    instance_template = {
        "variables": {"defaultAioConfigurationSettings": {"existing": "config"}},
        "resources": {"aioExtension": {"properties": {}}},
    }
    manager.apply_to_template(instance_template, "instance")

    assert instance_template["variables"]["VERSIONS"]["iotOperations"] == "2.0.0"
    assert instance_template["variables"]["TRAINS"]["iotOperations"] == "dev"
    assert instance_template["variables"]["defaultAioConfigurationSettings"] == {
        "existing": "config",
        "ops_custom": "ops_value",
    }

    # Test resource key mapping
    assert manager.resource_key_map[EXTENSION_MONIKER_CM] == "certManagerExtension"
    assert manager.resource_key_map[EXTENSION_MONIKER_SSC] == "secretStoreExtension"
    assert manager.resource_key_map[EXTENSION_MONIKER_OPS] == "aioExtension"


@pytest.mark.parametrize(
    "target_scenario, expected_error, error_match",
    [
        # Broker validation errors - single value out of range
        (
            build_target_scenario(
                cluster_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                broker_backend_redundancy_factor=1,
            ),
            InvalidArgumentValueError,
            f"backendRedundancyFactor value range min:{BROKER_BACKEND_REDUNDANCY_MIN} "
            f"max:{BROKER_BACKEND_REDUNDANCY_MAX}",
        ),
        # Multiple broker config values out of range
        (
            build_target_scenario(
                cluster_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                broker_backend_redundancy_factor=1,
                broker_frontend_replicas=20,
                broker_backend_workers=20,
            ),
            InvalidArgumentValueError,
            f"frontendReplicas value range min:1 max:{BROKER_REPLICAS_MAX}\n"
            f"backendRedundancyFactor value range min:{BROKER_BACKEND_REDUNDANCY_MIN} "
            f"max:{BROKER_BACKEND_REDUNDANCY_MAX}\n"
            f"backendWorkers value range min:1 max:{BROKER_WORKERS_MAX}",
        ),
        # Persistence mode without max size
        (
            build_target_scenario(
                cluster_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                persist_mode=["a=b", "c=d"],
            ),
            InvalidArgumentValueError,
            "Provide a persist max size value to enable and customize broker disk persistence.",
        ),
        # Invalid persistence mode key
        (
            build_target_scenario(
                cluster_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                persist_max_size="10Gi",
                persist_mode=["a=b", "c=d"],
            ),
            InvalidArgumentValueError,
            f"Invalid persistence mode key: a. Valid keys are {PERSIST_MODE_KEYS}.",
        ),
        # Invalid persistence mode value
        (
            build_target_scenario(
                cluster_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                persist_max_size="10Gi",
                persist_mode=["stateStore=All", "retain=invalid"],
            ),
            InvalidArgumentValueError,
            "Invalid persistence mode value: invalid. "
            f"Valid values are ['{PERSIST_MODE_NONE}', '{PERSIST_MODE_ALL}', '{PERSIST_MODE_CUSTOM}'].",
        ),
        # Malformed schema registry resource ID
        (
            build_target_scenario(
                cluster_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                schema_registry_resource_id=generate_random_string(),
            ),
            InvalidArgumentValueError,
            "--sr-resource-id is malformed. An Azure resource Id has the form:\n"
            "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroup}/providers"
            "/Microsoft.Provider/{resourceType}/{resourceName}",
        ),
        # Malformed namespace resource ID
        (
            build_target_scenario(
                cluster_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                schema_registry_resource_id=get_schema_registry_id(),
                adr_namespace_resource_id=generate_random_string(),
            ),
            InvalidArgumentValueError,
            "--ns-resource-id is malformed. An Azure resource Id has the form:\n"
            "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroup}/providers"
            "/Microsoft.Provider/{resourceType}/{resourceName}",
        ),
        # Wrong resource type for schema registry
        (
            build_target_scenario(
                cluster_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                schema_registry_resource_id=get_resource_id(
                    resource_provider=STORAGE_RP,
                    resource_group_name=generate_random_string(),
                    resource_path="/storageAccounts/mystorageaccount",
                ),
                adr_namespace_resource_id=get_ns_resource_id(DEFAULT_RESOURCE_GROUP),
            ),
            InvalidArgumentValueError,
            f"--sr-resource-id value must be of type {ADR_RP}/schemaRegistries.",
        ),
        # Wrong resource type for namespace
        (
            build_target_scenario(
                cluster_name=generate_random_string(),
                resource_group_name=DEFAULT_RESOURCE_GROUP,
                schema_registry_resource_id=get_schema_registry_id(),
                adr_namespace_resource_id=get_resource_id(
                    resource_provider=STORAGE_RP,
                    resource_group_name=DEFAULT_RESOURCE_GROUP,
                    resource_path="/storageAccounts/mystorageaccount",
                ),
            ),
            InvalidArgumentValueError,
            f"--ns-resource-id value must be of type {ADR_RP}/namespaces.",
        ),
        # Trust settings validation - missing required keys
        (
            build_target_scenario(
                cluster_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                trust_settings=["configMapName=mymap", "configMapKey=mykey"],
            ),
            InvalidArgumentValueError,
            "issuerName is a required trust setting/key.",
        ),
        # Trust settings validation - invalid issuer kind
        (
            build_target_scenario(
                cluster_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                trust_settings=[
                    "issuerKind=InvalidKind",
                    "issuerName=myissuer",
                    "configMapName=mymap",
                    "configMapKey=mykey",
                ],
            ),
            InvalidArgumentValueError,
            "issuerKind allowed values are ['ClusterIssuer', 'Issuer'].",
        ),
    ],
)
def test_validation_errors(target_scenario: dict, expected_error: type[Exception], error_match: str):
    """Test all validation errors in InitTargets."""
    with pytest.raises(expected_error) as e:
        InitTargets(**target_scenario)
    assert str(e.value) == error_match


@pytest.mark.parametrize(
    "target_scenario, expected_error",
    [
        # Valid small custom location name
        (
            build_target_scenario(
                cluster_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                custom_location_name=generate_random_string(size=1),
            ),
            None,
        ),
        # Valid max-length custom location name
        (
            build_target_scenario(
                cluster_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                custom_location_name=generate_random_string(size=63),
            ),
            None,
        ),
        # Invalid - too long custom location name
        (
            build_target_scenario(
                cluster_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                custom_location_name=generate_random_string(size=64),
            ),
            InvalidArgumentValueError,
        ),
    ],
)
def test_custom_location_name_limits(target_scenario: dict, expected_error: ExpectedExc):
    """Test custom location name length limits."""
    ctx = (
        pytest.raises(expected_error, match="Custom location name must be 63 characters or less.")
        if expected_error
        else nullcontext()
    )
    with ctx:
        targets = InitTargets(**target_scenario)
        if not expected_error:
            assert len(targets.custom_location_name) == len(target_scenario["custom_location_name"])


def test_valid_trust_settings():
    """Test valid trust settings configurations."""
    targets = InitTargets(
        cluster_name=generate_random_string(),
        resource_group_name=generate_random_string(),
        trust_settings=[
            "issuerKind=ClusterIssuer",
            "issuerName=myissuer",
            "configMapName=mymap",
            "configMapKey=mykey",
        ],
    )
    assert targets.trust_settings == {
        "issuerKind": "ClusterIssuer",
        "issuerName": "myissuer",
        "configMapName": "mymap",
        "configMapKey": "mykey",
    }


def test_sanitize_methods():
    """Test sanitization methods."""
    targets = InitTargets("cluster", "rg")

    # Test _sanitize_k8s_name
    assert targets._sanitize_k8s_name(None) is None
    assert targets._sanitize_k8s_name("test-name") == "test-name"
    assert targets._sanitize_k8s_name("Test_Name") == "test-name"
    assert targets._sanitize_k8s_name("TEST_NAME_123") == "test-name-123"

    # Test _sanitize_int
    assert targets._sanitize_int(None) is None
    assert targets._sanitize_int(5) == 5
    assert targets._sanitize_int("10") == 10


@pytest.mark.parametrize(
    "phase, expected_resources, expected_existing",
    [
        # EXT phase: Deploy extension and cluster, cluster is pre-existing
        (
            InstancePhase.EXT,
            {"aioExtension", "cluster"},  # Resources that should be present
            {"cluster"},  # Only cluster is marked as existing (it's a prerequisite)
        ),
        # INSTANCE phase: Deploy instance and customLocation
        (
            InstancePhase.INSTANCE,
            {"aioExtension", "cluster", "aioInstance", "customLocation"},
            {"aioExtension", "cluster", "customLocation"},  # All except aioInstance marked as existing
        ),
        # RESOURCES phase: Deploy broker and related resources
        (
            InstancePhase.RESOURCES,
            {
                "aioExtension",
                "cluster",
                "customLocation",
                "aioInstance",
                "broker",
                "brokerAuthn",
                "brokerListener",
                "dataflowProfile",
                "dataflowEndpoint",
                "artifactRegistryEndpoint",
                "opcUaConnectorTemplate",
            },
            {"aioExtension", "cluster", "customLocation", "aioInstance"},  # All base resources marked as existing
        ),
        # No phase: Complete deployment, cluster is still marked as existing (it's always a prerequisite)
        (
            None,
            {
                "aioExtension",
                "aioInstance",
                "broker",
                "brokerAuthn",
                "brokerListener",
                "dataflowProfile",
                "dataflowEndpoint",
                "artifactRegistryEndpoint",
                "opcUaConnectorTemplate",
                "cluster",
                "customLocation",
            },
            {"cluster"},  # Cluster is always marked as existing since it's a prerequisite
        ),
    ],
)
def test_instance_phases(phase, expected_resources, expected_existing):
    """Test instance template phases generate correct resources and existing markers."""

    cluster_name = generate_random_string()
    resource_group_name = generate_random_string()
    instance_name = generate_random_string()
    location = generate_random_string()

    targets = InitTargets(
        cluster_name=cluster_name,
        resource_group_name=resource_group_name,
        schema_registry_resource_id=get_schema_registry_id(),
        adr_namespace_resource_id=get_ns_resource_id(resource_group_name),
        instance_name=instance_name,
        location=location,
    )

    extension_ids = [generate_random_string(), generate_random_string()]
    template, _ = targets.get_ops_instance_template(extension_ids, phase=phase)
    resources = template["resources"]

    # Check that expected resources are present
    assert (
        set(resources.keys()) == expected_resources
    ), f"Phase {phase}: Expected resources {expected_resources}, got {set(resources.keys())}"

    # Check that resources are marked as existing correctly
    for resource_name in expected_resources:
        resource_def = resources[resource_name]
        should_be_existing = resource_name in expected_existing
        is_existing = resource_def.get("existing", False)

        assert is_existing == should_be_existing, f"Phase {phase}: Resource '{resource_name}' existing flag should"
        f"be {should_be_existing}, but is {is_existing}"

        # If marked as existing, verify it only has the core properties
        if is_existing:
            allowed_keys = {"type", "apiVersion", "name", "scope", "condition", "existing"}
            actual_keys = set(resource_def.keys())
            assert actual_keys.issubset(
                allowed_keys
            ), f"Phase {phase}: Existing resource '{resource_name}' has unexpected keys: {actual_keys - allowed_keys}"


def test_get_default_cl_name():
    """Test default custom location name generation."""
    resource_group = "test-rg"
    cluster = "test-cluster"
    namespace = "test-namespace"

    name = get_default_cl_name(resource_group, cluster, namespace)
    assert name.startswith("location-")
    assert len(name) == len("location-") + 5  # prefix + 5 char hash

    # Test consistency
    name2 = get_default_cl_name(resource_group, cluster, namespace)
    assert name == name2

    # Test different inputs produce different names
    name3 = get_default_cl_name("different-rg", cluster, namespace)
    assert name != name3
