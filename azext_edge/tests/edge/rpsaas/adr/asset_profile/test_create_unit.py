# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_edge.edge.commands_asset_endpoint_profiles import create_asset_endpoint_profile
from azext_edge.edge.common import ResourceProviderMapping, ResourceTypeMapping
from azext_edge.edge.providers.rpsaas.adr.base import ADR_API_VERSION

from .....generators import generate_random_string


@pytest.mark.parametrize("mocked_resource_management_client", [{
    "resource_groups.get": {"location": generate_random_string()},
    "resources.begin_create_or_update": {"result": generate_random_string()}
}], ids=["create"], indirect=True)
@pytest.mark.parametrize("aep_helpers_fixture", [{
    "update_properties": generate_random_string(),
}], ids=["create helpers"], indirect=True)
@pytest.mark.parametrize("req", [
    {},
    {
        "custom_location_name": generate_random_string(),
        "custom_location_resource_group": generate_random_string(),
        "custom_location_subscription": generate_random_string(),
        "cluster_name": generate_random_string(),
        "cluster_resource_group": generate_random_string(),
        "cluster_subscription": generate_random_string(),
        "additional_configuration": generate_random_string(),
        "username_reference": generate_random_string(),
        "password_reference": generate_random_string(),
        # "certificate_reference": generate_random_string(),
        "tags": generate_random_string(),
    },
    {
        "custom_location_resource_group": generate_random_string(),
        "cluster_subscription": generate_random_string(),
        "additional_configuration": generate_random_string(),
        "username_reference": generate_random_string(),
        "password_reference": generate_random_string(),
    },
])
def test_create_asset_endpoint_profile(mocker, mocked_cmd, mocked_resource_management_client, aep_helpers_fixture, req):
    patched_cap = mocker.patch(
        "azext_edge.edge.providers.rpsaas.adr.base.ADRBaseProvider.check_cluster_and_custom_location"
    )
    patched_cap.return_value = generate_random_string()

    # Required params
    asset_endpoint_profile_name = generate_random_string()
    resource_group_name = generate_random_string()
    target_address = generate_random_string()

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
    poller = mocked_resource_management_client.resources.begin_create_or_update.return_value
    assert result == poller.result()
    mocked_resource_management_client.resources.begin_create_or_update.assert_called_once()
    call_kwargs = mocked_resource_management_client.resources.begin_create_or_update.call_args.kwargs
    assert call_kwargs["resource_group_name"] == resource_group_name
    assert call_kwargs["resource_provider_namespace"] == ResourceProviderMapping.deviceregistry.value
    assert call_kwargs["parent_resource_path"] == ""
    assert call_kwargs["resource_type"] == ResourceTypeMapping.asset_endpoint_profile.value
    assert call_kwargs["resource_name"] == asset_endpoint_profile_name
    assert call_kwargs["api_version"] == ADR_API_VERSION

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
    if all(["username_reference" not in req, "password_reference" not in req, "certificate_reference" not in req]):
        req["auth_mode"] = "Anonymous"
    assert request_props["result"]

    for arg in aep_helpers_fixture.call_args.kwargs:
        assert aep_helpers_fixture.call_args.kwargs[arg] == req.get(arg)
        assert request_props.get(arg) is None


def test_create_asset_endpoint_profile_error(mocker, mocked_cmd):
    with pytest.raises(InvalidArgumentValueError):
        create_asset_endpoint_profile(
            cmd=mocked_cmd,
            asset_endpoint_profile_name=generate_random_string(),
            resource_group_name=generate_random_string(),
            target_address=generate_random_string(),
            certificate_reference=generate_random_string()
        )
