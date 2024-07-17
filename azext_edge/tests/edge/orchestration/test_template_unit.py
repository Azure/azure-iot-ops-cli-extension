# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from pathlib import Path
from unittest import TestCase
from ...generators import generate_random_string

from azext_edge.edge.providers.orchestration.template import (
    CURRENT_TEMPLATE,
    get_current_template_copy,
)


def test_current_template():
    assert CURRENT_TEMPLATE.commit_id
    assert CURRENT_TEMPLATE.moniker
    assert CURRENT_TEMPLATE.content
    assert CURRENT_TEMPLATE.parameters

    default_components = CURRENT_TEMPLATE.get_component_vers()
    assert "processor" not in default_components
    assert CURRENT_TEMPLATE.get_component_vers() == CURRENT_TEMPLATE.content["variables"]["VERSIONS"]

    deep_copy_template = get_current_template_copy()

    assert deep_copy_template.commit_id == CURRENT_TEMPLATE.commit_id
    assert deep_copy_template.moniker == CURRENT_TEMPLATE.moniker
    assert deep_copy_template.parameters == CURRENT_TEMPLATE.parameters
    assert deep_copy_template.content == CURRENT_TEMPLATE.content
    assert deep_copy_template.get_component_vers() == CURRENT_TEMPLATE.get_component_vers()

    TestCase().assertDictEqual(CURRENT_TEMPLATE.content, deep_copy_template.content)

    assert id(CURRENT_TEMPLATE) != id(deep_copy_template)


def test_custom_template():
    # Use built-in template as baseline
    expected_custom_template_content = get_current_template_copy().content

    expected_custom_template_content["metadata"] = {
        "description": f"Custom deployment {generate_random_string()} of Azure IoT Operations."
    }
    expected_custom_template_content["parameters"][generate_random_string()] = {
        "type": "string",
        "defaultValue": generate_random_string(),
        "metadata": {"description": "IoT Ops CLI test"},
    }

    to_consume_custom_template_path = Path(__file__).parent.joinpath("custom_template.json")
    to_consume_custom_template_path.write_text(json.dumps(expected_custom_template_content), encoding="utf-8")

    custom_template = get_current_template_copy(str(to_consume_custom_template_path))

    assert custom_template.commit_id == "custom"
    assert custom_template.moniker == "custom"
    assert custom_template.content == expected_custom_template_content
    assert custom_template.parameters == expected_custom_template_content["parameters"]

    assert custom_template.get_component_vers() == expected_custom_template_content["variables"]["VERSIONS"]

    to_consume_custom_template_path.unlink()
