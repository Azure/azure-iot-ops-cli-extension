# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------
from contextlib import nullcontext
from random import randint
from typing import Dict, List, Optional, Union
from unittest.mock import Mock

import pytest
from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_edge.edge.providers.orchestration.common import (
    EXTENSION_TYPE_CM,
    EXTENSION_TYPE_OPS,
    EXTENSION_TYPE_SSC,
    EXTENSION_TYPE_TO_MONIKER_MAP,
)
from azext_edge.edge.providers.orchestration.targets import (
    TRUST_ISSUER_KIND_KEY,
    TRUST_SETTING_KEYS,
    InitTargets,
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


K8S_NAME_KEYS = frozenset(["cluster_namespace", "custom_location_name", "instance_name"])
KEY_CONVERSION_MAP = {}
KVP_KEYS = frozenset(["ops_config", "ssc_config", "trust_settings", "persist_mode"])
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
    "schemaRegistryId": "schema_registry_resource_id",
    "adrNamespaceId": "adr_namespace_resource_id",
    "defaultDataflowInstanceCount": "dataflow_profile_instances",
    "brokerConfig": "broker_config",
    "trustConfig": "trust_config",
}
INSTANCE_FEATURE_MAP = {"connectors.settings.preview=Enabled": {"connectors": {"settings": {"preview": "Enabled"}}}}
INSTANCE_FEATURE_ATTR = "instance_features"


def assert_parameter_matches_targets(parameters: dict, targets: InitTargets, conversion_map: dict):
    """Helper to assert that parameters match targets attributes using a conversion map."""
    for parameter, parameter_value in parameters.items():
        if parameter == "clExtentionIds":  # Special case
            continue

        targets_key = conversion_map.get(parameter, parameter)
        expected_value = getattr(targets, targets_key)

        if "value" in parameter_value:
            actual_value = parameter_value["value"]
        else:
            actual_value = parameter_value

        assert actual_value == expected_value, (
            f"{parameter} value mismatch with targets {targets_key} value. "
            f"Expected: {expected_value}, Got: {actual_value}"
        )


def assert_instance_names(template: dict, instance_name: str):
    """Helper to assert all instance-related names in the template."""
    expected_names = {
        "aioInstance": instance_name,
        "broker": f"{instance_name}/default",
        "brokerAuthn": f"{instance_name}/default/default",
        "brokerListener": f"{instance_name}/default/default",
        "dataflowProfile": f"{instance_name}/default",
        "dataflowEndpoint": f"{instance_name}/default",
    }

    for resource_key, expected_name in expected_names.items():
        assert template["resources"][resource_key]["name"] == expected_name

    assert template["outputs"]["aio"]["value"]["name"] == instance_name


@pytest.mark.parametrize(
    "target_scenario",
    [
        # Basic scenario
        build_target_scenario(
            cluster_name=generate_random_string(),
            resource_group_name=generate_random_string(),
        ),
        # Scenario with schema registry and custom broker config
        build_target_scenario(
            cluster_name=generate_random_string(),
            resource_group_name=generate_random_string(),
            schema_registry_resource_id=get_schema_registry_id(),
            location=generate_random_string(),
            instance_name=generate_random_string(),
            custom_broker_config={generate_random_string(): generate_random_string()},
        ),
        # Scenario with user trust
        build_target_scenario(
            cluster_name=generate_random_string(),
            resource_group_name=DEFAULT_RESOURCE_GROUP,
            schema_registry_resource_id=get_schema_registry_id(),
            adr_namespace_resource_id=get_ns_resource_id(DEFAULT_RESOURCE_GROUP),
            user_trust=True,
        ),
        # Scenario with persistence configuration
        build_target_scenario(
            instance_name=generate_random_string(),
            cluster_name=generate_random_string(),
            resource_group_name=DEFAULT_RESOURCE_GROUP,
            schema_registry_resource_id=get_schema_registry_id(),
            adr_namespace_resource_id=get_ns_resource_id(DEFAULT_RESOURCE_GROUP),
            persist_max_size="10Gi",
            persist_pvc_sc=generate_random_string(),
        ),
        # Scenario with persistence modes
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
        # Full configuration scenario
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
        # SSC configuration scenario
        build_target_scenario(
            cluster_name=generate_random_string(),
            resource_group_name=generate_random_string(),
            ssc_config=[f"{generate_random_string()}={generate_random_string()}"],
            ssc_version=generate_random_string(),
            ssc_train=generate_random_string(),
        ),
    ],
)
def test_init_targets(target_scenario: dict, mocked_feature_keys: Mock):
    """Test InitTargets initialization and template generation with various scenarios."""
    targets = InitTargets(**target_scenario)

    # Verify target initialization
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

    # Test enablement template
    enablement_template, enablement_parameters = targets.get_ops_enablement_template()
    verify_trust_config(
        target_scenario=target_scenario,
        parameters=enablement_parameters,
        template=enablement_template,
    )

    assert_parameter_matches_targets(enablement_parameters, targets, ENABLEMENT_PARAM_CONVERSION_MAP)

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
    ssc_config_settings = enablement_template["resources"]["secretStoreExtension"]["properties"][
        "configurationSettings"
    ]
    assert_extension_config(
        settings=ssc_config_settings, expected_base_config=expected_ssc_config, custom_config=targets.ssc_config
    )

    # Test instance template
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

    # Verify extension IDs parameter
    assert instance_parameters["clExtensionIds"]["value"] == extension_ids

    # Verify other parameters
    for parameter in instance_parameters:
        if parameter == "clExtensionIds":
            continue
        targets_key = INSTANCE_PARAM_CONVERSION_MAP.get(parameter, parameter)
        assert instance_parameters[parameter]["value"] == getattr(
            targets, targets_key
        ), f"{parameter} value mismatch with targets {targets_key} value."

    # Verify instance properties
    aio_instance = instance_template["resources"]["aioInstance"]
    assert aio_instance["properties"]["description"] == targets.instance_description
    assert aio_instance["properties"]["schemaRegistryRef"] == {"resourceId": "[parameters('schemaRegistryId')]"}
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


def verify_broker_config(target_scenario: dict, parameters: dict):
    """Verify broker configuration parameters match the target scenario."""
    broker_config = parameters["brokerConfig"]["value"]
    assert "serviceType" not in broker_config

    # Map of target scenario keys to broker config keys
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

    # Check persistence configuration
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

    # Check persistence modes
    explicit_mode_keys = {key: False for key in PERSIST_MODE_KEYS}

    if "persist_mode" in target_scenario:
        for k, v in target_scenario["persist_mode"].items():
            expected_payload = {"mode": v}
            if v == PERSIST_MODE_CUSTOM:
                expected_payload[k + "Settings"] = {"dynamic": {"mode": "Enabled"}}

            assert persistence[k] == expected_payload
            explicit_mode_keys[k] = True

    # Set default for unspecified modes
    for k, was_set in explicit_mode_keys.items():
        if not was_set:
            assert persistence[k] == {
                "mode": PERSIST_MODE_CUSTOM,
                k + "Settings": {"dynamic": {"mode": "Enabled"}},
            }


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
            assert version_map[moniker]["version"], f"Missing version for {moniker}"
            assert version_map[moniker]["train"], f"Missing train for {moniker}"
        assert len(extension_types) == len(version_map)

    targets = InitTargets(generate_random_string(), generate_random_string())
    enablement_version_map = targets.get_extension_versions()
    enablement_types = [EXTENSION_TYPE_CM, EXTENSION_TYPE_SSC]
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
    "target_scenario, expected_error",
    [
        # Broker redundancy factor below minimum
        (
            build_target_scenario(
                cluster_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                broker_backend_redundancy_factor=1,
            ),
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
            f"Invalid persistence mode key: a. Valid keys are {PERSIST_MODE_KEYS}.",
        ),
        # Invalid persistence mode value
        (
            build_target_scenario(
                cluster_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                persist_max_size="10Gi",
                persist_mode=["stateStore=All", "retain=d"],
            ),
            "Invalid persistence mode value: d. "
            f"Valid values are ['{PERSIST_MODE_NONE}', '{PERSIST_MODE_ALL}', '{PERSIST_MODE_CUSTOM}'].",
        ),
        # Malformed schema registry resource ID
        (
            build_target_scenario(
                cluster_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                schema_registry_resource_id=generate_random_string(),
            ),
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
                adr_namespace_resource_id=get_ns_resource_id(
                    resource_group_name=DEFAULT_RESOURCE_GROUP,
                ),
            ),
            f"--sr-resource-id value must be of type {ADR_RP}/schemaRegistries.",
        ),
        # Namespace resource group mismatch
        (
            build_target_scenario(
                cluster_name=generate_random_string(),
                resource_group_name="instancegroup",
                schema_registry_resource_id=get_schema_registry_id(),
                adr_namespace_resource_id=get_ns_resource_id(),
            ),
            "--ns-resource-id value must match the resource group 'instancegroup'.",
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
            f"--ns-resource-id value must be of type {ADR_RP}/namespaces.",
        ),
    ],
)
def test_broker_config_limits(target_scenario: dict, expected_error: str):
    """Test validation of broker configuration limits and resource ID formats."""
    with pytest.raises(InvalidArgumentValueError) as e:
        InitTargets(**target_scenario)
    assert str(e.value) == expected_error


@pytest.mark.parametrize(
    "target_scenario, expected_error",
    [
        (
            build_target_scenario(
                cluster_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                custom_location_name=generate_random_string(size=1),
            ),
            None,
        ),
        (
            build_target_scenario(
                cluster_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                custom_location_name=generate_random_string(size=63),
            ),
            None,
        ),
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
    ctx = (
        pytest.raises(expected_error, match="Custom location name must be 63 characters or less.")
        if expected_error
        else nullcontext()
    )
    with ctx:
        InitTargets(**target_scenario)
