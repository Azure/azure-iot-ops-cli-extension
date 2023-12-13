# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest


BP_PATH = "azext_edge.edge.providers.rpsaas.base_provider"


@pytest.fixture()
def mock_check_cluster_connectivity(mocker):
    patched = mocker.patch(f"{BP_PATH}.RPSaaSBaseProvider.check_cluster_connectivity")
    patched.return_value = None

    yield patched
