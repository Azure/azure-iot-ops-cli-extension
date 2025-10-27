# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
import json
from typing import Optional, Callable, Tuple
from ...generators import generate_random_string
from ...helpers import create_file

"""Helpers for ADR v2 tests."""


def assert_dataset_properties(result, **expected):
    """Verify dataset properties match expected values.

    Minimal checks since unit tests already validate the command structure."""
    assert result["name"] == expected["name"]

    if "data_source" in expected:
        assert result["dataSource"] == expected["data_source"]
    if "custom_configuration" in expected:
        assert result["datasetConfiguration"] == expected["custom_configuration"]


def assert_event_properties(result, **expected):
    """Verify event properties match expected values.

    Minimal checks since unit tests already validate the command structure."""
    assert result["name"] == expected["name"]

    if "data_source" in expected:
        assert result["dataSource"] == expected["data_source"]
    if "custom_configuration" in expected:
        # Handle both event-group (eventGroupConfiguration) and event (eventConfiguration)
        if "eventGroupConfiguration" in result:
            assert result["eventGroupConfiguration"] == expected["custom_configuration"]
        elif "eventConfiguration" in result:
            assert result["eventConfiguration"] == expected["custom_configuration"]


def assert_management_group_properties(result, **expected):
    """Verify management group properties match expected values."""
    assert result["name"] == expected["name"]

    if "default_topic" in expected:
        assert result["defaultTopic"] == expected["default_topic"]
    if "default_timeout" in expected:
        assert result["defaultTimeoutInSeconds"] == expected["default_timeout"]
    if "data_source" in expected:
        assert result["dataSource"] == expected["data_source"]
    if "custom_configuration" in expected:
        assert result["managementGroupConfiguration"] == expected["custom_configuration"]


def assert_management_group_action_properties(result, **expected):
    """Verify management group action properties match expected values."""
    result = next((ac for ac in result if ac["name"] == expected["name"]), None)
    assert result, f"Action '{expected['name']}' not found in result"

    if "target_uri" in expected:
        assert result["targetUri"] == expected["target_uri"]
    if "action_type" in expected:
        assert result["actionType"] == expected["action_type"]
    if "timeout" in expected:
        assert result["timeoutInSeconds"] == expected["timeout"]
    if "topic" in expected:
        assert result["topic"] == expected["topic"]
    if "custom_configuration" in expected:
        assert result["actionConfiguration"] == expected["custom_configuration"]


def assert_point_properties(result, **expected):
    """Verify datapoint properties match expected values.

    Minimal checks since unit tests already validate the command structure."""
    result_map = {point["name"]: point for point in result}
    result_point = result_map.get(expected["name"])
    assert result_point["name"] == expected["name"]

    if "data_source" in expected:
        assert result_point["dataSource"] == expected["data_source"]
    if "custom_configuration" in expected:
        # Handle both event datapoints (eventConfiguration) and dataset datapoints (dataPointConfiguration)
        if "eventConfiguration" in result_point:
            assert result_point["eventConfiguration"] == expected["custom_configuration"]
        elif "dataPointConfiguration" in result_point:
            assert result_point["dataPointConfiguration"] == expected["custom_configuration"]


def assert_stream_properties(result, **expected):
    """Verify custom stream properties match expected values."""
    assert result["name"] == expected["name"]

    if "custom_configuration" in expected:
        check_stream_configuration(result, expected)


def check_configuration(config_key: str, added: dict, expected: dict):
    """Helper function to check dataset/event configuration."""
    if expected and config_key in expected:
        added_config = json.loads(added.get(config_key) or "{}")
        expected_config = json.loads(expected[config_key] or "{}")
        assert len(added_config) == len(expected_config)
        for key in expected_config:
            assert key in added_config
            assert added_config[key] == expected_config[key]


check_dataset_configuration: Callable = partial(check_configuration, "datasetConfiguration")
check_event_configuration: Callable = partial(check_configuration, "eventConfiguration")
check_stream_configuration: Callable = partial(check_configuration, "streamConfiguration")


def check_destinations(added: dict, expected: Optional[dict] = None, default: bool = False):
    """Helper function to check destinations."""
    key = "defaultDestinations" if default else "destinations"
    if not expected or not expected.get(key):
        return

    added_destinations = added.get(key, [])
    assert len(added_destinations) == len(expected[key])
    destination = added_destinations[0]
    expected_destination = expected[key][0]
    assert destination.get("target") == expected_destination.get("target")

    if destination.get("target") == "Mqtt":
        result_config = destination.get("configuration", {})
        expected_config = expected_destination.get("configuration", {})
        assert result_config.get("topic") == expected_config.get("topic")
        assert result_config.get("retain") == expected_config.get("retain")
        assert result_config.get("qos") == expected_config.get("qos")
        assert result_config.get("ttl") == expected_config.get("ttl")
    elif destination.get("target") == "Storage":
        result_config = destination.get("configuration", {})
        expected_config = expected_destination.get("configuration", {})
        assert result_config.get("path") == expected_config.get("path")
    else:
        result_config = destination.get("configuration", {})
        expected_config = expected_destination.get("configuration", {})
        assert result_config.get("key") == expected_config.get("key")


def create_config_file(tracked_files: list) -> Tuple[str, str]:
    """Create a JSON configuration file with random content."""
    json_content = json.dumps({
        generate_random_string(): generate_random_string(),
        generate_random_string(): {
            generate_random_string(): generate_random_string()
        },
        generate_random_string(): generate_random_string()
    })
    file_path = create_file(
        file_name=f"test_add_config_{generate_random_string(size=4)}.json",
        module_file=__file__,
        tracked_files=tracked_files,
        content=json_content
    )
    return file_path, json_content
