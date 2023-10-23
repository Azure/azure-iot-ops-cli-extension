# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.commands_asset_endpoint_profiles import create_asset_endpoint_profile
from azext_edge.edge.common import ResourceTypeMapping
from azext_edge.edge.providers.resource_management import API_VERSION

from ...generators import generate_generic_id


@pytest.mark.parametrize("mocked_resource_management_client", [{
    "resource_groups.get": {"location": generate_generic_id()},
    "resources.begin_create_or_update_by_id": {"result": generate_generic_id()}
}], ids=["create"], indirect=True)
@pytest.mark.parametrize("aep_helpers_fixture", [{
    "update_properties": generate_generic_id(),
}], ids=["create helpers"], indirect=True)
@pytest.mark.parametrize("req", [
    {},
    {
        "custom_location_name": generate_generic_id(),
        "custom_location_resource_group": generate_generic_id(),
        "custom_location_subscription": generate_generic_id(),
        "cluster_name": generate_generic_id(),
        "cluster_resource_group": generate_generic_id(),
        "cluster_subscription": generate_generic_id(),
        "additional_configuration": generate_generic_id(),
        "username": generate_generic_id(),
        "password": generate_generic_id(),
        "certificate_reference": generate_generic_id(),
        "tags": generate_generic_id(),
    },
    {
        "custom_location_resource_group": generate_generic_id(),
        "cluster_subscription": generate_generic_id(),
        "additional_configuration": generate_generic_id(),
        "username": generate_generic_id(),
        "password": generate_generic_id(),
    },
])
def test_create_asset_endpoint_profile(mocker, mocked_cmd, mocked_resource_management_client, aep_helpers_fixture, req):
    patched_cap = mocker.patch(
        "azext_edge.edge.providers.resource_management.ResourceManagementProvider."
        "_check_cluster_and_custom_location"
    )
    patched_cap.return_value = generate_generic_id()

    # Required params
    asset_endpoint_profile_name = generate_generic_id()
    resource_group_name = generate_generic_id()
    target_address = generate_generic_id()

    result = create_asset_endpoint_profile(
        cmd=mocked_cmd,
        asset_endpoint_profile_name=asset_endpoint_profile_name,
        resource_group_name=resource_group_name,
        target_address=target_address,
        **req
    ).result()

    # resource group call
    location = req.get(
        "location",
        mocked_resource_management_client.resource_groups.get.return_value.as_dict.return_value["location"]
    )
    if req.get("location"):
        mocked_resource_management_client.resource_groups.get.assert_not_called()
    else:
        mocked_resource_management_client.resource_groups.get.assert_called_once()

    # create call
    poller = mocked_resource_management_client.resources.begin_create_or_update_by_id.return_value
    assert result == poller.result()
    mocked_resource_management_client.resources.begin_create_or_update_by_id.assert_called_once()
    call_kwargs = mocked_resource_management_client.resources.begin_create_or_update_by_id.call_args.kwargs
    expected_resource_path = f"/resourceGroups/{resource_group_name}/providers/"\
        f"{ResourceTypeMapping.asset_endpoint_profile.value}/{asset_endpoint_profile_name}"
    assert expected_resource_path in call_kwargs["resource_id"]
    assert call_kwargs["api_version"] == API_VERSION

    # asset body
    request_body = call_kwargs["parameters"]
    assert request_body["location"] == location
    assert request_body["tags"] == req.get("tags")
    assert request_body["extendedLocation"] == patched_cap.return_value

    # Extended location helper call
    for arg in patched_cap.call_args.kwargs:
        expected_arg = mocked_cmd.cli_ctx.data['subscription_id'] if arg == "subscription" else req.get(arg)
        assert patched_cap.call_args.kwargs[arg] == expected_arg

    # Properties
    request_props = request_body["properties"]
    req["target_address"] = target_address
    if all(["username" not in req, "password" not in req, "certificate_reference" not in req]):
        req["auth_mode"] = "Anonymous"
    assert request_props["result"]

    for arg in aep_helpers_fixture.call_args.kwargs:
        assert aep_helpers_fixture.call_args.kwargs[arg] == req.get(arg)
        assert request_props.get(arg) is None
