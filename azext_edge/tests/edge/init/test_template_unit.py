# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from pathlib import Path
from unittest import TestCase

from azext_edge.edge.providers.orchestration.template import (
    CURRENT_TEMPLATE,
    get_current_template_copy,
)


def test_current_template():
    assert CURRENT_TEMPLATE.commit_id
    assert CURRENT_TEMPLATE.moniker
    assert CURRENT_TEMPLATE.content_vers
    assert CURRENT_TEMPLATE.content
    assert CURRENT_TEMPLATE.parameters

    deep_copy_template = get_current_template_copy()

    assert deep_copy_template.commit_id == CURRENT_TEMPLATE.commit_id
    assert deep_copy_template.moniker == CURRENT_TEMPLATE.moniker
    assert deep_copy_template.content_vers == CURRENT_TEMPLATE.content_vers
    assert deep_copy_template.parameters == CURRENT_TEMPLATE.parameters
    assert deep_copy_template.content == CURRENT_TEMPLATE.content
    TestCase().assertDictEqual(CURRENT_TEMPLATE.content, deep_copy_template.content)

    assert id(CURRENT_TEMPLATE) != id(deep_copy_template)


def test_custom_template():
    custom_template_path = Path(__file__).parent.joinpath("custom_template.json")
    expected_custom_template_content = json.loads(custom_template_path.read_text(encoding="utf-8"))

    custom_template = get_current_template_copy(str(custom_template_path))
    custom_template.commit_id == "custom"
    custom_template.moniker == "custom"
    custom_template.content == expected_custom_template_content
    custom_template.parameters == expected_custom_template_content["parameters"]
    custom_template.content_vers == expected_custom_template_content["variables"]["VERSIONS"]
