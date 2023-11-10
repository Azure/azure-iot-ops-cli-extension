# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest


RM_PATH = "azext_edge.edge.providers.adr.base"


@pytest.fixture()
def mock_check_cluster_connectivity(mocker):
    patched = mocker.patch(f"{RM_PATH}.ResourceManagementProvider._check_cluster_connectivity")
    patched.return_value = None

    yield patched
