# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.commands_asset_endpoint_profiles import update_asset_endpoint_profile
from azext_edge.edge.providers.adr.base import API_VERSION

from .conftest import MINIMUM_AEP, FULL_AEP
from ....generators import generate_generic_id


@pytest.mark.parametrize("mocked_resource_management_client", [
    {
        "resources.get": MINIMUM_AEP,
        "resources.begin_create_or_update_by_id": {"result": generate_generic_id()}
    },
    {
        "resources.get": FULL_AEP,
        "resources.begin_create_or_update_by_id": {"result": generate_generic_id()}
    },
], ids=["minimal", "full"], indirect=True)
@pytest.mark.parametrize("aep_helpers_fixture", [{
    "update_properties": generate_generic_id(),
}], ids=["update helpers"], indirect=True)
@pytest.mark.parametrize("req", [
    {},
    {
        "target_address": generate_generic_id(),
        "additional_configuration": generate_generic_id(),
        "auth_mode": generate_generic_id(),
        "username": generate_generic_id(),
        "password": generate_generic_id(),
        "certificate_reference": generate_generic_id(),
        "tags": generate_generic_id(),
    },
    {
        "additional_configuration": generate_generic_id(),
        "auth_mode": generate_generic_id(),
    },
])
def test_update_asset_endpoint_profile(
    mocked_cmd,
    mock_check_cluster_connectivity,
    mocked_resource_management_client,
    aep_helpers_fixture,
    req
):
    # Required params
    asset_endpoint_profile_name = generate_generic_id()
    resource_group_name = generate_generic_id()
    result = update_asset_endpoint_profile(
        cmd=mocked_cmd,
        asset_endpoint_profile_name=asset_endpoint_profile_name,
        resource_group_name=resource_group_name,
        **req
    ).result()

    mocked_resource_management_client.resources.get.assert_called_once()
    mocked_resource_management_client.resources.begin_create_or_update_by_id.assert_called_once()
    original_aep = mocked_resource_management_client.resources.get.return_value.original
    poller = mocked_resource_management_client.resources.begin_create_or_update_by_id.return_value
    assert result == poller.result()

    # Update call
    call_kwargs = mocked_resource_management_client.resources.begin_create_or_update_by_id.call_args.kwargs
    assert call_kwargs["resource_id"] == original_aep["id"]
    assert call_kwargs["api_version"] == API_VERSION

    # Check update request
    request_body = call_kwargs["parameters"]
    assert request_body["location"] == original_aep["location"]
    assert request_body["extendedLocation"] == original_aep["extendedLocation"]
    assert request_body.get("tags") == req.get("tags", original_aep.get("tags"))

    # Properties
    request_props = request_body["properties"]

    # Check that update props mock got called correctly
    assert request_props["result"]
    for arg in aep_helpers_fixture.call_args.kwargs:
        assert aep_helpers_fixture.call_args.kwargs[arg] == req.get(arg)
        assert request_props.get(arg) is None
