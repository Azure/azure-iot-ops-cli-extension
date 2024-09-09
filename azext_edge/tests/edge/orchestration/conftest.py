# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest


@pytest.fixture
def mocked_resource_graph(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.connected_cluster.ResourceGraph", autospec=True)
    yield patched
