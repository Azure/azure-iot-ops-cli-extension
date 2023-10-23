# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.commands_asset_endpoint_profiles import (
    add_asset_endpoint_profile_transport_auth,
    list_asset_endpoint_profile_transport_auth,
    remove_asset_endpoint_profile_transport_auth
)
from azext_edge.edge.providers.asset_endpoint_profiles import API_VERSION

from .conftest import MINIMUM_AEP, FULL_AEP
from ..conftest import RM_PATH
from ...generators import generate_generic_id


FULL_CERT = FULL_AEP["properties"]["transportAuthentication"]["ownCertificates"][0]


@pytest.mark.parametrize("mocked_build_query", [{
    "path": RM_PATH,
    "result": [{"properties": {"connectivityStatus": "Online"}}]
}], ids=["query"], indirect=True)
@pytest.mark.parametrize("mocked_resource_management_client", [
    {
        "resources.get": MINIMUM_AEP,
        "resources.begin_create_or_update_by_id": {
            "properties": {"transportAuthentication": {"result": generate_generic_id()}}
        }
    },
    {
        "resources.get": FULL_AEP,
        "resources.begin_create_or_update_by_id": {
            "properties": {"transportAuthentication": {"result": generate_generic_id()}}
        }
    },
], ids=["minimal", "full"], indirect=True)
def test_add_asset_endpoint_profile_transport_auth(
    mocked_cmd,
    mocked_resource_management_client,
    mocked_build_query
):
    asset_endpoint_profile_name = generate_generic_id()
    resource_group_name = generate_generic_id()
    secret = generate_generic_id()
    thumbprint = generate_generic_id()
    password = generate_generic_id()
    result = add_asset_endpoint_profile_transport_auth(
        cmd=mocked_cmd,
        asset_endpoint_profile_name=asset_endpoint_profile_name,
        resource_group_name=resource_group_name,
        secret=secret,
        thumbprint=thumbprint,
        password=password
    )
    mocked_resource_management_client.resources.get.assert_called_once()
    mocked_resource_management_client.resources.begin_create_or_update_by_id.assert_called_once()
    original_aep = mocked_resource_management_client.resources.get.return_value.original
    poller = mocked_resource_management_client.resources.begin_create_or_update_by_id.return_value
    expected_asset = poller.result()
    assert result == expected_asset["properties"]["transportAuthentication"]

    # AEP changes
    call_kwargs = mocked_resource_management_client.resources.begin_create_or_update_by_id.call_args.kwargs
    assert call_kwargs["resource_id"] == original_aep["id"]
    assert call_kwargs["api_version"] == API_VERSION

    # Check update request
    request_aep_certs = call_kwargs["parameters"]["properties"]["transportAuthentication"]["ownCertificates"]
    original_certs = original_aep["properties"].get("transportAuthentication", {}).get("ownCertificates", [])

    assert request_aep_certs[:-1] == original_certs
    added_cert = request_aep_certs[-1]
    assert added_cert["certSecretReference"] == secret
    assert added_cert["certThumbprint"] == thumbprint
    assert added_cert["certPasswordReference"] == password


@pytest.mark.parametrize("mocked_resource_management_client", [
    {"resources.get": MINIMUM_AEP},
    {"resources.get": FULL_AEP},
], ids=["minimal", "full"], indirect=True)
def test_list_asset_endpoint_profile_transport_auths(mocked_cmd, mocked_resource_management_client):
    asset_endpoint_profile_name = generate_generic_id()
    resource_group_name = generate_generic_id()
    result = list_asset_endpoint_profile_transport_auth(
        cmd=mocked_cmd,
        asset_endpoint_profile_name=asset_endpoint_profile_name,
        resource_group_name=resource_group_name
    )
    mocked_resource_management_client.resources.get.assert_called_once()
    original_aep = mocked_resource_management_client.resources.get.return_value.as_dict.return_value
    expected = original_aep["properties"].get("transportAuthentication", {"ownCertificates": []})
    assert result == expected


@pytest.mark.parametrize("mocked_build_query", [{
    "path": RM_PATH,
    "result": [{"properties": {"connectivityStatus": "Online"}}]
}], ids=["query"], indirect=True)
@pytest.mark.parametrize("mocked_resource_management_client", [
    {
        "resources.get": FULL_AEP,
        "resources.begin_create_or_update_by_id": {
            "properties": {"transportAuthentication": {"result": generate_generic_id()}}
        }
    },
], ids=["full"], indirect=True)
@pytest.mark.parametrize("thumbprint", [generate_generic_id(), FULL_CERT["certThumbprint"]])
def test_remove_asset_endpoint_profile_transport_auth(
    mocked_cmd, mocked_resource_management_client, mocked_build_query, thumbprint
):
    asset_endpoint_profile_name = generate_generic_id()
    resource_group_name = generate_generic_id()
    result = remove_asset_endpoint_profile_transport_auth(
        cmd=mocked_cmd,
        asset_endpoint_profile_name=asset_endpoint_profile_name,
        resource_group_name=resource_group_name,
        thumbprint=thumbprint
    )
    mocked_resource_management_client.resources.get.assert_called_once()
    mocked_resource_management_client.resources.begin_create_or_update_by_id.assert_called_once()
    original_aep = mocked_resource_management_client.resources.get.return_value.original
    poller = mocked_resource_management_client.resources.begin_create_or_update_by_id.return_value
    expected_asset = poller.result()
    assert result == expected_asset["properties"].get("transportAuthentication", {})

    # Asset changes
    call_kwargs = mocked_resource_management_client.resources.begin_create_or_update_by_id.call_args.kwargs
    assert call_kwargs["resource_id"] == original_aep["id"]
    assert call_kwargs["api_version"] == API_VERSION

    # Check update request
    request_certs = call_kwargs["parameters"]["properties"]["transportAuthentication"]["ownCertificates"]
    original_certs = original_aep["properties"]["transportAuthentication"]["ownCertificates"]

    if thumbprint == FULL_CERT["certThumbprint"]:
        assert len(request_certs) + 1 == len(original_certs)
        assert request_certs == original_certs[1:]
    else:
        assert request_certs == original_certs
