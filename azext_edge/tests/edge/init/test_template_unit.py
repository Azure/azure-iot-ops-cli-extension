# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


def test_current_template():
    from azext_edge.edge.providers.orchestration.template import CURRENT_TEMPLATE

    assert CURRENT_TEMPLATE.commit_id
    assert CURRENT_TEMPLATE.content_vers
    assert CURRENT_TEMPLATE.content
    assert CURRENT_TEMPLATE.parameters
