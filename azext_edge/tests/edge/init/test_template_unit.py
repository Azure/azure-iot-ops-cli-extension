# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from unittest import TestCase

def test_current_template():
    from azext_edge.edge.providers.orchestration.template import CURRENT_TEMPLATE, get_current_template_copy

    assert CURRENT_TEMPLATE.commit_id
    assert CURRENT_TEMPLATE.content_vers
    assert CURRENT_TEMPLATE.content
    assert CURRENT_TEMPLATE.parameters

    deep_copy_template = get_current_template_copy()

    assert deep_copy_template.commit_id == CURRENT_TEMPLATE.commit_id
    assert deep_copy_template.content_vers == CURRENT_TEMPLATE.content_vers
    assert deep_copy_template.parameters == CURRENT_TEMPLATE.parameters
    assert deep_copy_template.content == CURRENT_TEMPLATE.content
    TestCase().assertDictEqual(CURRENT_TEMPLATE.content, deep_copy_template.content)
