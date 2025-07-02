# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial
from typing import Optional, Callable

"""Helpers for ADR v2 tests."""


def check_configuration(config_key: str, added: dict, expected: dict):
    """Helper function to check dataset/event configuration."""
    if expected and config_key in expected:
        assert added[config_key] == expected[config_key]


check_dataset_configuration: Callable = partial(check_configuration, "datasetConfiguration")
check_event_configuration: Callable = partial(check_configuration, "eventConfiguration")


def check_destinations(added: dict, expected: Optional[dict] = None):
    """Helper function to check destinations."""
    if not expected or "destinations" not in expected:
        return

    added_destinations = added.get("destinations", [])
    assert len(added_destinations) == len(expected["destinations"])
    destination = added_destinations[0]
    expected_destination = expected["destinations"][0]
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
