# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import pytest

from ...generators import generate_generic_id


@pytest.mark.parametrize("mocked_resource_management_client", [
    {"resources.get": {"extended_location": generate_generic_id()}},
    {"resources.get": {"extendedLocation": generate_generic_id()}},
    {"resources.get": {"result": generate_generic_id()}},
], ids=["extended_location", "extendedLocation", "result"], indirect=True)
def test_show(mocked_cmd, mocked_resource_management_client):
    from azext_edge.edge.providers.adr.base import ResourceManagementProvider
    provider = ResourceManagementProvider(mocked_cmd)
    result = provider.show(generate_generic_id(), generate_generic_id())

    mocked_resource_management_client.resources.get.assert_called_once()
    # note that pop will modify the return value
    as_dict = mocked_resource_management_client.resources.get.return_value.as_dict.return_value
    assert "extended_location" not in result
    assert result == as_dict


@pytest.mark.parametrize("mocked_resource_management_client", [
    {"resources.get": {"extendedLocation": {"name": generate_generic_id()}}},
], ids=["extendedLocation"], indirect=True)
def test_show_and_check(mocked_cmd, mocked_resource_management_client, mock_check_cluster_connectivity):
    from azext_edge.edge.providers.adr.base import ResourceManagementProvider
    provider = ResourceManagementProvider(mocked_cmd)
    result = provider.show_and_check(generate_generic_id(), generate_generic_id())

    mocked_resource_management_client.resources.get.assert_called_once()
    # note that pop will modify the return value
    as_dict = mocked_resource_management_client.resources.get.return_value.as_dict.return_value
    assert result == as_dict

    mock_check_cluster_connectivity.assert_called_once_with(as_dict["extendedLocation"]["name"])
