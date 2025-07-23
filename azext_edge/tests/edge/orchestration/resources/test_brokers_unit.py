# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from copy import deepcopy
from typing import Optional

import pytest
import responses
from azure.cli.core.azclierror import InvalidArgumentValueError, ValidationError

from azext_edge.edge.commands_mq import (
    delete_broker,
    list_brokers,
    show_broker,
    update_broker_persist,
)
from azext_edge.edge.common import DEFAULT_BROKER

from ....generators import generate_random_string
from .conftest import get_base_endpoint, get_mock_resource


def get_broker_endpoint(instance_name: str, resource_group_name: str, broker_name: Optional[str] = None) -> str:
    resource_path = f"/instances/{instance_name}/brokers"
    if broker_name:
        resource_path += f"/{broker_name}"
    return get_base_endpoint(resource_group_name=resource_group_name, resource_path=resource_path)


def get_mock_broker_record(
    broker_name: str, instance_name: str, resource_group_name: str, properties: Optional[dict] = None
) -> dict:
    default_properties = {
        "advanced": {"encryptInternalTraffic": "Enabled"},
        "cardinality": {
            "backendChain": {"partitions": 2, "redundancyFactor": 2, "workers": 2},
            "frontend": {"replicas": 2, "workers": 2},
        },
        "diagnostics": {
            "logs": {"level": "info"},
            "metrics": {"prometheusPort": 9600},
            "selfCheck": {"intervalSeconds": 30, "mode": "Enabled", "timeoutSeconds": 15},
            "traces": {
                "cacheSizeMegabytes": 16,
                "mode": "Enabled",
                "selfTracing": {"intervalSeconds": 30, "mode": "Enabled"},
                "spanChannelCapacity": 1000,
            },
        },
        "generateResourceLimits": {"cpu": "Disabled"},
        "memoryProfile": "Medium",
        "provisioningState": "Succeeded",
    }

    if properties:
        default_properties.update(properties)

    return get_mock_resource(
        name=broker_name,
        resource_path=f"/instances/{instance_name}/brokers/{broker_name}",
        properties=default_properties,
        resource_group_name=resource_group_name,
        qualified_type="microsoft.iotoperations/instances/brokers",
        is_proxy_resource=True,
    )


def test_broker_show(mocked_cmd, mocked_responses: responses):
    broker_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_broker_record = get_mock_broker_record(
        broker_name=broker_name, instance_name=instance_name, resource_group_name=resource_group_name
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_broker_endpoint(
            resource_group_name=resource_group_name, instance_name=instance_name, broker_name=broker_name
        ),
        json=mock_broker_record,
        status=200,
        content_type="application/json",
    )

    result = show_broker(
        cmd=mocked_cmd,
        broker_name=broker_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )
    assert result == mock_broker_record
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "records",
    [0, 2],
)
def test_broker_list(mocked_cmd, mocked_responses: responses, records: int):
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_broker_records = {
        "value": [
            get_mock_broker_record(
                broker_name=generate_random_string(),
                instance_name=instance_name,
                resource_group_name=resource_group_name,
            )
            for _ in range(records)
        ]
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_broker_endpoint(instance_name=instance_name, resource_group_name=resource_group_name),
        json=mock_broker_records,
        status=200,
        content_type="application/json",
    )

    result = list(list_brokers(cmd=mocked_cmd, instance_name=instance_name, resource_group_name=resource_group_name))
    assert result == mock_broker_records["value"]
    assert len(mocked_responses.calls) == 1


def test_broker_delete(mocked_cmd, mocked_responses: responses):
    broker_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mocked_responses.add(
        method=responses.DELETE,
        url=get_broker_endpoint(
            resource_group_name=resource_group_name, instance_name=instance_name, broker_name=broker_name
        ),
        status=204,
    )
    delete_broker(
        cmd=mocked_cmd,
        broker_name=broker_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=True,
        wait_sec=0.25,
    )
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "existing_persistence_config",
    [
        # No persistence configuration - should raise ValidationError
        None,
        # Basic persistence configuration with maxSize
        {
            "maxSize": "10Gi",
            "retain": {"mode": "Custom", "retainSettings": {"dynamic": {"mode": "Enabled"}}},
            "stateStore": {"mode": "Custom", "stateStoreSettings": {"dynamic": {"mode": "Enabled"}}},
            "subscriberQueue": {"mode": "Custom", "subscriberQueueSettings": {"dynamic": {"mode": "Enabled"}}},
        },
        # Persistence with All modes
        {
            "maxSize": "5Gi",
            "retain": {"mode": "All"},
            "stateStore": {"mode": "All"},
            "subscriberQueue": {"mode": "All"},
        },
        # Persistence with None modes
        {
            "maxSize": "20Gi",
            "retain": {"mode": "None"},
            "stateStore": {"mode": "None"},
            "subscriberQueue": {"mode": "None"},
        },
    ],
)
@pytest.mark.parametrize(
    "scenario",
    [
        # Test error case - no persistence enabled
        {
            "input": {"persist_mode": ["retain=Custom"]},
            "persistence_required": True,
            "error": (
                ValidationError,
                "The broker is not enabled for disk persistence which must be configured at create time.\n"
                "Use 'az iot ops create' with '--persist-max-size' to enable.",
            ),
        },
        # Test basic mode updates
        {
            "input": {"persist_mode": ["retain=All", "stateStore=None"]},
            "expected_updates": {
                "retain": {"mode": "All"},
                "stateStore": {"mode": "None"},
            },
        },
        {
            "input": {"persist_mode": ["subscriberQueue=Custom"]},
            "expected_updates": {
                "subscriberQueue": {"mode": "Custom", "subscriberQueueSettings": {"dynamic": {"mode": "Enabled"}}},
            },
        },
        # Test retain topics configuration
        {
            "input": {"persist_mode": ["retain=Custom"], "retain_topics": ["topic1", "topic2", "topic3"]},
            "expected_updates": {
                "retain": {"mode": "Custom", "retainSettings": {"topics": ["topic1", "topic2", "topic3"]}},
            },
        },
        # Test subscriber queue client IDs
        {
            "input": {
                "persist_mode": ["subscriberQueue=Custom"],
                "subscriber_queue_client_ids": ["client1", "client2"],
            },
            "expected_updates": {
                "subscriberQueue": {
                    "mode": "Custom",
                    "subscriberQueueSettings": {"subscriberClientIds": ["client1", "client2"]},
                },
            },
        },
        # Test state store keys - simple case
        {
            "input": {
                "persist_mode": ["stateStore=Custom"],
                "state_store_str_keys": [["key1"], ["key2"]],
                "state_store_glob_keys": [["pattern*"], ["*.json"]],
                "state_store_bin_keys": [["binkey1"]],
            },
            "expected_updates": {
                "stateStore": {
                    "mode": "Custom",
                    "stateStoreSettings": {
                        "stateStoreResources": [
                            {"keys": ["key1"], "keyType": "String"},
                            {"keys": ["key2"], "keyType": "String"},
                            {"keys": ["pattern*"], "keyType": "Pattern"},
                            {"keys": ["*.json"], "keyType": "Pattern"},
                            {"keys": ["binkey1"], "keyType": "Binary"},
                        ]
                    },
                },
            },
        },
        # Test state store keys - complex multiple keys per group
        {
            "input": {
                "persist_mode": ["stateStore=Custom"],
                "state_store_str_keys": [["key1", "key2", "key3"], ["key4"], ["key5", "key6"]],
                "state_store_glob_keys": [["sensor/*", "device/*"], ["*.json", "*.xml", "*.csv"]],
                "state_store_bin_keys": [["binkey1", "binkey2"], ["binkey3"]],
            },
            "expected_updates": {
                "stateStore": {
                    "mode": "Custom",
                    "stateStoreSettings": {
                        "stateStoreResources": [
                            {"keys": ["key1", "key2", "key3"], "keyType": "String"},
                            {"keys": ["key4"], "keyType": "String"},
                            {"keys": ["key5", "key6"], "keyType": "String"},
                            {"keys": ["sensor/*", "device/*"], "keyType": "Pattern"},
                            {"keys": ["*.json", "*.xml", "*.csv"], "keyType": "Pattern"},
                            {"keys": ["binkey1", "binkey2"], "keyType": "Binary"},
                            {"keys": ["binkey3"], "keyType": "Binary"},
                        ]
                    },
                },
            },
        },
        # Test state store keys - only string keys with multiple groups
        {
            "input": {
                "persist_mode": ["stateStore=Custom"],
                "state_store_str_keys": [
                    ["user:1001", "user:1002", "user:1003"],
                    ["session:active"],
                    ["config:database", "config:cache", "config:logging", "config:security"],
                    ["temp:cleanup"],
                ],
            },
            "expected_updates": {
                "stateStore": {
                    "mode": "Custom",
                    "stateStoreSettings": {
                        "stateStoreResources": [
                            {"keys": ["user:1001", "user:1002", "user:1003"], "keyType": "String"},
                            {"keys": ["session:active"], "keyType": "String"},
                            {
                                "keys": ["config:database", "config:cache", "config:logging", "config:security"],
                                "keyType": "String",
                            },
                            {"keys": ["temp:cleanup"], "keyType": "String"},
                        ]
                    },
                },
            },
        },
        # Test user property configuration
        {
            "input": {"user_property_key": "myKey", "user_property_value": "myValue"},
            "expected_updates": {
                "dynamicSettings": {
                    "userPropertyKey": "myKey",
                    "userPropertyValue": "myValue",
                },
            },
        },
        # Test disable dynamic configuration
        {
            "input": {
                "persist_mode": ["retain=Custom", "stateStore=Custom"],
                "disable_dynamic": ["retain", "stateStore"],
            },
            "expected_updates": {
                "retain": {"mode": "Custom", "retainSettings": {"dynamic": {"mode": "Disabled"}}},
                "stateStore": {"mode": "Custom", "stateStoreSettings": {"dynamic": {"mode": "Disabled"}}},
            },
        },
        # Test complex scenario with multiple configurations
        {
            "input": {
                "persist_mode": ["retain=Custom", "subscriberQueue=All"],
                "retain_topics": ["sensor/*", "telemetry/+"],
                "user_property_key": "persistence",
                "user_property_value": "enabled",
            },
            "expected_updates": {
                "retain": {"mode": "Custom", "retainSettings": {"topics": ["sensor/*", "telemetry/+"]}},
                "subscriberQueue": {"mode": "All"},
                "dynamicSettings": {
                    "userPropertyKey": "persistence",
                    "userPropertyValue": "enabled",
                },
            },
        },
        # Test custom broker name
        {
            "input": {"persist_mode": ["retain=None"], "broker_name": "custom-broker"},
            "expected_updates": {
                "retain": {"mode": "None"},
            },
        },
        # Test error cases for invalid configurations
        {
            "input": {"retain_topics": ["topic1"]},
            "error": (
                InvalidArgumentValueError,
                "To set retain topics for persistence, retain mode must be set to 'Custom'.",
            ),
        },
        {
            "input": {"subscriber_queue_client_ids": ["client1"]},
            "error": (
                InvalidArgumentValueError,
                "To set subscriber queue client Ids for persistence, subscriberQueue mode must be set to 'Custom'.",
            ),
        },
        {
            "input": {"state_store_str_keys": [["key1"]]},
            "error": (
                InvalidArgumentValueError,
                "To set state store keys for persistence, stateStore mode must be set to 'Custom'.",
            ),
        },
        {
            "input": {"user_property_key": "key"},
            "error": (InvalidArgumentValueError, "Both --user-key and --user-value must be set or both must be unset."),
        },
        {
            "input": {"user_property_value": "value"},
            "error": (InvalidArgumentValueError, "Both --user-key and --user-value must be set or both must be unset."),
        },
        {
            "input": {"persist_mode": ["retain=All"], "disable_dynamic": ["retain"]},
            "error": (
                InvalidArgumentValueError,
                "To disable dynamic persistence for retain, retain mode must be set to 'Custom'.",
            ),
        },
        {
            "input": {"persist_mode": ["invalid=Custom"]},
            "error": (
                InvalidArgumentValueError,
                "Invalid persistence mode key: invalid. Valid keys are ['stateStore', 'retain', 'subscriberQueue'].",
            ),
        },
        {
            "input": {"persist_mode": ["retain=Invalid"]},
            "error": (
                InvalidArgumentValueError,
                "Invalid persistence mode value: Invalid. Valid values are ['None', 'All', 'Custom'].",
            ),
        },
    ],
)
def test_update_broker_persist(
    mocked_cmd,
    mocked_responses: responses,
    scenario: dict,
    existing_persistence_config: Optional[dict],
):
    # Skip incompatible test combinations
    persistence_required = scenario.get("persistence_required", False)
    if (existing_persistence_config is None and not persistence_required) or (
        persistence_required and existing_persistence_config is not None
    ):
        return

    # Setup test data
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    scenario_inputs: dict = scenario.get("input", {})
    broker_name = scenario_inputs.get("broker_name", DEFAULT_BROKER)
    test_inputs = {k: v for k, v in scenario_inputs.items() if k != "broker_name"}

    # Create mock broker
    broker_properties = {"persistence": deepcopy(existing_persistence_config)} if existing_persistence_config else {}
    mock_broker_record = get_mock_broker_record(
        broker_name=broker_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        properties=broker_properties,
    )

    endpoint = get_broker_endpoint(
        resource_group_name=resource_group_name, instance_name=instance_name, broker_name=broker_name
    )

    # Add GET mock
    mocked_responses.add(method=responses.GET, url=endpoint, json=mock_broker_record, status=200)

    # Determine expected outcome
    error_info = scenario.get("error")
    expected_updates = scenario.get("expected_updates", {})

    # Handle dynamic error-to-success conversion for configuration-dependent scenarios
    if error_info and existing_persistence_config:
        # Check if error scenario should actually succeed based on existing persistence modes
        should_succeed = False

        if "retain_topics" in scenario_inputs:
            should_succeed = existing_persistence_config.get("retain", {}).get("mode") == "Custom"
            if should_succeed:
                expected_updates = {
                    "retain": {"mode": "Custom", "retainSettings": {"topics": scenario_inputs["retain_topics"]}}
                }
        elif "subscriber_queue_client_ids" in scenario_inputs:
            should_succeed = existing_persistence_config.get("subscriberQueue", {}).get("mode") == "Custom"
            if should_succeed:
                expected_updates = {
                    "subscriberQueue": {
                        "mode": "Custom",
                        "subscriberQueueSettings": {
                            "subscriberClientIds": scenario_inputs["subscriber_queue_client_ids"]
                        },
                    }
                }
        elif any(
            k in scenario_inputs for k in ["state_store_str_keys", "state_store_glob_keys", "state_store_bin_keys"]
        ):
            should_succeed = existing_persistence_config.get("stateStore", {}).get("mode") == "Custom"
            if should_succeed:
                resources = []
                for collection, key_type in zip(
                    [
                        scenario_inputs.get("state_store_str_keys", []),
                        scenario_inputs.get("state_store_glob_keys", []),
                        scenario_inputs.get("state_store_bin_keys", []),
                    ],
                    ["String", "Pattern", "Binary"],
                ):
                    for item in collection:
                        resources.append({"keys": item, "keyType": key_type})
                expected_updates = {
                    "stateStore": {"mode": "Custom", "stateStoreSettings": {"stateStoreResources": resources}}
                }

        if should_succeed:
            error_info = None

    # Execute test
    if error_info:
        # Test error case
        error_type, error_msg = error_info
        with pytest.raises(error_type) as exc:
            update_broker_persist(
                cmd=mocked_cmd,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
                broker_name=broker_name,
                **test_inputs,
            )
        assert str(exc.value) == error_msg
    else:
        # Test success case
        expected_broker_record = deepcopy(mock_broker_record)
        if expected_updates:
            expected_broker_record["properties"]["persistence"].update(expected_updates)

        mocked_responses.add(method=responses.PUT, url=endpoint, json=expected_broker_record, status=200)

        result = update_broker_persist(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            broker_name=broker_name,
            wait_sec=0.1,
            **test_inputs,
        )

        assert result == expected_broker_record
        assert len(mocked_responses.calls) == 2

        # Verify PUT request payload
        request_payload = mocked_responses.calls[1].request.body
        request_payload = json.loads(request_payload)
        assert request_payload == expected_broker_record
