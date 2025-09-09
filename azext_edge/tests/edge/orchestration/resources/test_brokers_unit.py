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


def get_broker_endpoint(
    instance_name: str, resource_group_name: str, broker_name: Optional[str] = None, **kwargs: dict
) -> str:
    resource_path = f"/instances/{instance_name}/brokers"
    if broker_name:
        resource_path += f"/{broker_name}"
    return get_base_endpoint(resource_group_name=resource_group_name, resource_path=resource_path, **kwargs)


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


def create_persistence_config(
    retain_mode: str = "Custom",
    state_store_mode: str = "Custom",
    subscriber_queue_mode: str = "Custom",
    max_size: str = "10Gi",
) -> dict:
    """Create a persistence configuration with specified modes."""
    config = {"maxSize": max_size}

    # Add retain configuration
    config["retain"] = {"mode": retain_mode}
    if retain_mode == "Custom":
        config["retain"]["retainSettings"] = {"dynamic": {"mode": "Enabled"}}

    # Add stateStore configuration
    config["stateStore"] = {"mode": state_store_mode}
    if state_store_mode == "Custom":
        config["stateStore"]["stateStoreSettings"] = {"dynamic": {"mode": "Enabled"}}

    # Add subscriberQueue configuration
    config["subscriberQueue"] = {"mode": subscriber_queue_mode}
    if subscriber_queue_mode == "Custom":
        config["subscriberQueue"]["subscriberQueueSettings"] = {"dynamic": {"mode": "Enabled"}}

    return config


@pytest.mark.parametrize(
    "existing_persistence_config",
    [
        None,  # No persistence configuration
        create_persistence_config(),  # All Custom modes
        create_persistence_config("All", "All", "All"),  # All modes set to "All"
        create_persistence_config("None", "None", "None"),  # All modes set to "None"
        create_persistence_config("Custom", "All", "None"),  # Mixed modes
    ],
)
@pytest.mark.parametrize(
    "scenario",
    [
        # === ERROR CASE: No persistence enabled ===
        {
            "description": "Error when no persistence is configured",
            "input": {"persist_mode": ["retain=Custom"]},
            "error": (
                ValidationError,
                "The broker is not enabled for disk persistence which must be configured at create time.\n"
                "Use 'az iot ops create' with '--persist-max-size' to enable.",
            ),
        },
        # === ERROR CASES: Invalid mode configurations ===
        {
            "description": "Invalid persistence mode key",
            "input": {"persist_mode": ["invalid=Custom"]},
            "error": (
                InvalidArgumentValueError,
                "Invalid persistence mode key: invalid. Valid keys are ['stateStore', 'retain', 'subscriberQueue'].",
            ),
        },
        {
            "description": "Invalid persistence mode value",
            "input": {"persist_mode": ["retain=Invalid"]},
            "error": (
                InvalidArgumentValueError,
                "Invalid persistence mode value: Invalid. Valid values are ['None', 'All', 'Custom'].",
            ),
        },
        # === ERROR CASES: Invalid disable_dynamic key ===
        {
            "description": "Invalid disable_dynamic key",
            "input": {"persist_mode": ["retain=Custom"], "disable_dynamic": ["invalidKey"]},
            "error": (
                InvalidArgumentValueError,
                "Invalid disable dynamic key: invalidKey. Valid keys are ['stateStore', 'retain', 'subscriberQueue'].",
            ),
        },
        {
            "description": "Mixed valid and invalid disable_dynamic keys",
            "input": {
                "persist_mode": ["retain=Custom", "stateStore=Custom"],
                "disable_dynamic": ["retain", "wrongKey"],
            },
            "error": (
                InvalidArgumentValueError,
                "Invalid disable dynamic key: wrongKey. Valid keys are ['stateStore', 'retain', 'subscriberQueue'].",
            ),
        },
        # === ERROR CASES: Configuration without proper mode ===
        {
            "description": "Retain topics requires Custom mode",
            "input": {"retain_topics": ["topic1"]},
            "check_mode": {"retain": "Custom"},
            "error": (
                InvalidArgumentValueError,
                "To set retain topics for persistence, retain mode must be set to 'Custom'.",
            ),
        },
        {
            "description": "Subscriber queue client IDs requires Custom mode",
            "input": {"subscriber_queue_client_ids": ["client1"]},
            "check_mode": {"subscriberQueue": "Custom"},
            "error": (
                InvalidArgumentValueError,
                "To set subscriber queue client Ids for persistence, subscriberQueue mode must be set to 'Custom'.",
            ),
        },
        {
            "description": "State store keys requires Custom mode",
            "input": {"state_store_str_keys": [["key1"]]},
            "check_mode": {"stateStore": "Custom"},
            "error": (
                InvalidArgumentValueError,
                "To set state store keys for persistence, stateStore mode must be set to 'Custom'.",
            ),
        },
        {
            "description": "Disable dynamic requires Custom mode",
            "input": {"persist_mode": ["retain=All"], "disable_dynamic": ["retain"]},
            "error": (
                InvalidArgumentValueError,
                "To disable dynamic persistence for retain, retain mode must be set to 'Custom'.",
            ),
        },
        # === SUCCESS CASES: Basic mode updates ===
        {
            "description": "Update multiple modes",
            "input": {"persist_mode": ["retain=All", "stateStore=None"]},
            "expected_updates": {
                "retain": {"mode": "All"},
                "stateStore": {"mode": "None"},
            },
        },
        {
            "description": "Set subscriberQueue to Custom",
            "input": {"persist_mode": ["subscriberQueue=Custom"]},
            "expected_updates": {
                "subscriberQueue": {"mode": "Custom", "subscriberQueueSettings": {"dynamic": {"mode": "Enabled"}}},
            },
        },
        {
            "description": "Mode transitions - mix of All, None, Custom",
            "input": {"persist_mode": ["retain=All", "stateStore=None", "subscriberQueue=Custom"]},
            "expected_updates": {
                "retain": {"mode": "All"},
                "stateStore": {"mode": "None"},
                "subscriberQueue": {"mode": "Custom", "subscriberQueueSettings": {"dynamic": {"mode": "Enabled"}}},
            },
        },
        # === SUCCESS CASES: Retain configurations ===
        {
            "description": "Set retain topics",
            "input": {"persist_mode": ["retain=Custom"], "retain_topics": ["topic1", "topic2", "topic3"]},
            "expected_updates": {
                "retain": {"mode": "Custom", "retainSettings": {"topics": ["topic1", "topic2", "topic3"]}},
            },
        },
        {
            "description": "Retain topics when retain is already Custom",
            "input": {"retain_topics": ["topic1", "topic2"]},
            "check_mode": {"retain": "Custom"},  # Only succeeds if retain is Custom
            "expected_updates": {
                "retain": {
                    "mode": "Custom",
                    "retainSettings": {"topics": ["topic1", "topic2"]},
                },
            },
        },
        # === SUCCESS CASES: Subscriber queue configurations ===
        {
            "description": "Set subscriber queue client IDs",
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
        {
            "description": "Subscriber client IDs when subscriberQueue is already Custom",
            "input": {"subscriber_queue_client_ids": ["client1", "client2", "client3"]},
            "check_mode": {"subscriberQueue": "Custom"},  # Only succeeds if subscriberQueue is Custom
            "expected_updates": {
                "subscriberQueue": {
                    "mode": "Custom",
                    "subscriberQueueSettings": {"subscriberClientIds": ["client1", "client2", "client3"]},
                },
            },
        },
        # === SUCCESS CASES: State store configurations ===
        {
            "description": "State store with simple keys",
            "input": {
                "persist_mode": ["stateStore=Custom"],
                "state_store_str_keys": [["key1"], ["key2"]],
                "state_store_glob_keys": [["pattern*"]],
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
                            {"keys": ["binkey1"], "keyType": "Binary"},
                        ]
                    },
                },
            },
        },
        {
            "description": "State store keys when stateStore is already Custom",
            "input": {
                "state_store_str_keys": [["cache:key1", "cache:key2"]],
                "state_store_glob_keys": [["logs/*"]],
            },
            "check_mode": {"stateStore": "Custom"},  # Only succeeds if stateStore is Custom
            "expected_updates": {
                "stateStore": {
                    "mode": "Custom",
                    "stateStoreSettings": {
                        "stateStoreResources": [
                            {"keys": ["cache:key1", "cache:key2"], "keyType": "String"},
                            {"keys": ["logs/*"], "keyType": "Pattern"},
                        ]
                    },
                },
            },
        },
        # === SUCCESS CASES: Disable dynamic ===
        {
            "description": "Disable dynamic for multiple modes",
            "input": {
                "persist_mode": ["retain=Custom", "stateStore=Custom"],
                "disable_dynamic": ["retain", "stateStore"],
            },
            "expected_updates": {
                "retain": {"mode": "Custom", "retainSettings": {"dynamic": {"mode": "Disabled"}}},
                "stateStore": {"mode": "Custom", "stateStoreSettings": {"dynamic": {"mode": "Disabled"}}},
            },
        },
        # === SUCCESS CASES: Complex scenarios ===
        {
            "description": "Complex - retain topics with dynamic disabled",
            "input": {
                "persist_mode": ["retain=Custom"],
                "retain_topics": ["test/*"],
                "disable_dynamic": ["retain"],
            },
            "expected_updates": {
                "retain": {
                    "mode": "Custom",
                    "retainSettings": {"topics": ["test/*"], "dynamic": {"mode": "Disabled"}},
                },
            },
        },
        {
            "description": "Update with custom broker name",
            "input": {"persist_mode": ["retain=None"], "broker_name": "custom-broker"},
            "expected_updates": {
                "retain": {"mode": "None"},
            },
        },
    ],
)
def test_update_broker_persist(
    mocked_cmd,
    mocked_responses: responses,
    scenario: dict,
    existing_persistence_config: Optional[dict],
):
    """Test update_broker_persist with various persistence configurations and scenarios."""
    error_info = scenario.get("error")

    # Check if this is the "no persistence" error - it should only run when config is None
    is_no_persistence_error = (
        error_info and error_info[0] == ValidationError and "not enabled for disk persistence" in str(error_info[1])
    )

    # Skip incompatible combinations
    if existing_persistence_config is None:
        if not is_no_persistence_error:
            return  # No config: only run "no persistence" error test
    elif is_no_persistence_error:
        return  # Has config: skip "no persistence" error test

    # Setup test data
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    scenario_inputs = scenario.get("input", {}).copy()
    broker_name = scenario_inputs.pop("broker_name", DEFAULT_BROKER)

    # Adjust expectations based on check_mode
    check_mode = scenario.get("check_mode")
    expected_updates = scenario.get("expected_updates")

    if check_mode and existing_persistence_config:
        mode_matches = all(
            existing_persistence_config.get(key, {}).get("mode") == required_mode
            for key, required_mode in check_mode.items()
        )
        if mode_matches:
            error_info = None  # Should succeed
        else:
            expected_updates = None  # Should fail

    # Skip if no clear expectation
    if not error_info and not expected_updates:
        return

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
    mocked_responses.add(method=responses.GET, url=endpoint, json=mock_broker_record, status=200)

    # Execute and verify
    if error_info:
        # Test error case
        error_type, error_msg = error_info
        with pytest.raises(error_type) as exc:
            update_broker_persist(
                cmd=mocked_cmd,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
                broker_name=broker_name,
                **scenario_inputs,
            )
        assert str(exc.value) == error_msg
        assert len(mocked_responses.calls) == 1  # Only GET was called
    else:
        # Test success case
        expected_broker_record = deepcopy(mock_broker_record)
        expected_broker_record["properties"]["persistence"].update(expected_updates)

        mocked_responses.add(method=responses.PUT, url=endpoint, json=expected_broker_record, status=200)

        result = update_broker_persist(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            broker_name=broker_name,
            wait_sec=0.1,
            **scenario_inputs,
        )

        assert result == expected_broker_record
        assert len(mocked_responses.calls) == 2

        # Verify PUT request payload
        request_payload = json.loads(mocked_responses.calls[1].request.body)
        assert request_payload == expected_broker_record
