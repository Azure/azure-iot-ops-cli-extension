# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, Optional
import json
import pytest
import responses

from azext_edge.edge.commands_asset_endpoint_profiles import (
    create_opcua_asset_endpoint_profile,
    delete_asset_endpoint_profile,
    list_asset_endpoint_profiles,
    show_asset_endpoint_profile,
    update_asset_endpoint_profile
)

from .conftest import get_profile_id, get_profile_record, get_mgmt_uri
from ....generators import generate_random_string


# TODO: add in OPCUA additional config args
@pytest.mark.parametrize("req", [
    {},
    {
        "certificate_reference": generate_random_string(),
        "instance_resource_group": generate_random_string(),
        "instance_subscription": generate_random_string(),
        "location": generate_random_string(),
        "tags": generate_random_string(),
    },
    {
        "instance_resource_group": generate_random_string(),
        "password_reference": generate_random_string(),
        "username_reference": generate_random_string(),
    }
])
def test_create(
    mocked_cmd,
    mocked_get_extended_location,
    mocked_responses: responses,
    req: Dict[str, str]
):
    profile_name = generate_random_string()
    target_address = generate_random_string()
    resource_group_name = generate_random_string()
    instance_name = generate_random_string()

    mock_profile_record = get_profile_record(
        profile_name, resource_group_name,
    )
    mocked_responses.add(
        method=responses.PUT,
        url=get_mgmt_uri(get_profile_id(profile_name, resource_group_name)),
        json=mock_profile_record,
        status=200,
        content_type="application/json",
    )

    result = create_opcua_asset_endpoint_profile(
        cmd=mocked_cmd,
        asset_endpoint_profile_name=profile_name,
        target_address=target_address,
        resource_group_name=resource_group_name,
        instance_name=instance_name,
        **req
    ).result()
    assert result == mock_profile_record
    call_body = json.loads(mocked_responses.calls[0].request.body)
    extended_location = mocked_get_extended_location.original_return_value
    assert call_body["extendedLocation"]["name"] == extended_location["name"]
    assert call_body["location"] == req.get("location", extended_location["cluster_location"])
    assert call_body["tags"] == req.get("tags")

    call_body_props = call_body["properties"]
    assert call_body_props["endpointProfileType"] == "OPCUA"
    assert call_body_props["targetAddress"] == target_address

    auth_props = call_body_props["authentication"]
    if req.get("certificate_reference"):
        assert auth_props["x509Credentials"]["certificateSecretName"] == req.get("certificate_reference")
        assert auth_props["method"] == "Certificate"
    elif req.get("username_reference"):
        user_pass = auth_props["usernamePasswordCredentials"]
        assert user_pass["passwordSecretName"] == req.get("password_reference")
        assert user_pass["usernameSecretName"] == req.get("username_reference")
        assert auth_props["method"] == "UsernamePassword"
    else:
        assert auth_props["method"] == "Anonymous"


@pytest.mark.parametrize("discovered", [False])  # TODO: discovered
def test_delete(mocked_cmd, mocked_check_cluster_connectivity, mocked_responses: responses, discovered: bool):
    profile_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_profile_record = get_profile_record(
        profile_name, resource_group_name, discovered=discovered
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_mgmt_uri(get_profile_id(profile_name, resource_group_name)),
        json="" if discovered else mock_profile_record,
        status=404 if discovered else 200,
        content_type="application/json",
    )
    if discovered:
        mocked_responses.add(
            method=responses.GET,
            url=get_mgmt_uri(get_profile_id(profile_name, resource_group_name, discovered=True)),
            json=mock_profile_record,
            status=200,
            content_type="application/json",
        )
    mocked_responses.add(
        method=responses.DELETE,
        url=get_mgmt_uri(get_profile_id(profile_name, resource_group_name, discovered=discovered)),
        status=202,
        content_type="application/json",
    )

    delete_asset_endpoint_profile(
        cmd=mocked_cmd,
        asset_endpoint_profile_name=profile_name,
        resource_group_name=resource_group_name,
    )
    assert len(mocked_responses.calls) == (3 if discovered else 2)


@pytest.mark.parametrize("records", [0, 2])
@pytest.mark.parametrize("resource_group_name", [None, generate_random_string()])
def test_list(
    mocked_cmd, mocked_responses: responses, records: int, resource_group_name: Optional[str]
):
    mock_profile_records = {
        "value": [
            get_profile_record(
                generate_random_string(),
                resource_group_name,
                discovered=False  # TODO: discovered
            )
            for _ in range(records)
        ]
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_mgmt_uri(get_profile_id(
            "", resource_group_name, discovered=False
        )),
        json=mock_profile_records,
        status=200,
        content_type="application/json",
    )

    result = list(list_asset_endpoint_profiles(cmd=mocked_cmd, resource_group_name=resource_group_name))
    assert result == mock_profile_records["value"]
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize("discovered", [False])  # TODO: discovered
def test_show(mocked_cmd, mocked_responses: responses, discovered: bool):
    profile_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_profile_record = get_profile_record(
        profile_name, resource_group_name, discovered=discovered
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_mgmt_uri(get_profile_id(profile_name, resource_group_name)),
        json="" if discovered else mock_profile_record,
        status=404 if discovered else 200,
        content_type="application/json",
    )
    if discovered:
        mocked_responses.add(
            method=responses.GET,
            url=get_mgmt_uri(get_profile_id(profile_name, resource_group_name, discovered=True)),
            json=mock_profile_record,
            status=200,
            content_type="application/json",
        )

    result = show_asset_endpoint_profile(
        cmd=mocked_cmd,
        asset_endpoint_profile_name=profile_name,
        resource_group_name=resource_group_name,
    )
    assert result == mock_profile_record
    assert len(mocked_responses.calls) == (2 if discovered else 1)


@pytest.mark.parametrize("req", [
    {},
    {
        "auth_mode": "Anonymous",
    },
    {
        "target_address": generate_random_string(),
        "certificate_reference": generate_random_string(),
        "tags": generate_random_string(),
    },
    {
        "password_reference": generate_random_string(),
        "username_reference": generate_random_string(),
    }
])
def test_asset_update(
    mocked_cmd,
    mocked_check_cluster_connectivity,
    mocked_responses: responses,
    req: dict
):
    # use non discovered since delete shows the update_ops is selected correctly
    profile_name = generate_random_string()
    resource_group_name = generate_random_string()

    # make sure that the get vs patch have different results
    mock_original_profile = get_profile_record(profile_name, resource_group_name,)
    mock_profile_record = get_profile_record(
        profile_name, resource_group_name, full=True
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_mgmt_uri(get_profile_id(profile_name, resource_group_name)),
        json=mock_original_profile,
        status=200,
        content_type="application/json",
    )
    mocked_responses.add(
        method=responses.PUT,
        url=get_mgmt_uri(get_profile_id(profile_name, resource_group_name)),
        json=mock_profile_record,
        status=200,
        content_type="application/json",
    )

    result = update_asset_endpoint_profile(
        cmd=mocked_cmd,
        asset_endpoint_profile_name=profile_name,
        resource_group_name=resource_group_name,
        **req
    ).result()
    assert result == mock_profile_record
    assert len(mocked_responses.calls) == 2
    call_body = json.loads(mocked_responses.calls[-1].request.body)
    assert call_body.get("tags") == req.get("tags", mock_original_profile.get("tags"))

    call_body_props = call_body["properties"]
    assert call_body_props["targetAddress"] == req.get(
        "target_address", mock_original_profile["properties"].get("targetAddress")
    )

    auth_props = call_body_props["authentication"]
    if req.get("certificate_reference"):
        assert auth_props["x509Credentials"]["certificateSecretName"] == req.get("certificate_reference")
        assert auth_props["method"] == "Certificate"
    elif req.get("username_reference"):
        user_pass = auth_props["usernamePasswordCredentials"]
        assert user_pass["passwordSecretName"] == req.get("password_reference")
        assert user_pass["usernameSecretName"] == req.get("username_reference")
        assert auth_props["method"] == "UsernamePassword"
    elif req.get("auth_mode"):
        assert auth_props["method"] == req.get("auth_mode")
    else:
        assert auth_props == mock_original_profile["properties"]["authentication"]
