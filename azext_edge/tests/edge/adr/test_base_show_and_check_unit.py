# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from ...generators import generate_generic_id


@pytest.mark.parametrize("mocked_resource_management_client", [
    {"resources.get": {"extendedLocation": {"name": generate_generic_id()}}},
], ids=["extendedLocation"], indirect=True)
def test_show_and_check(mocked_cmd, mocked_resource_management_client, mock_check_cluster_connectivity):
    from azext_edge.edge.providers.adr.base import ADRBaseProvider
    provider = ADRBaseProvider(mocked_cmd, generate_generic_id())
    result = provider.show_and_check(generate_generic_id(), generate_generic_id())

    mocked_resource_management_client.resources.get.assert_called_once()
    # note that pop will modify the return value
    as_dict = mocked_resource_management_client.resources.get.return_value.as_dict.return_value
    assert result == as_dict

    mock_check_cluster_connectivity.assert_called_once_with(as_dict["extendedLocation"]["name"])
