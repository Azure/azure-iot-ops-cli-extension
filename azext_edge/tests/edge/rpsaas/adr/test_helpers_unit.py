# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import pytest
import responses
from azure.cli.core.azclierror import (
    CLIError,
    FileOperationError,
    InvalidArgumentValueError,
    MutuallyExclusiveArgumentError,
    RequiredArgumentMissingError,
)

from azext_edge.edge.common import ADRAuthModes
from ....generators import generate_random_string, BASE_URL, generate_resource_id

CONNECTED_CLUSTER_API = "2024-07-15-preview"


@pytest.fixture()
def mocked_logger(mocker):
    yield mocker.patch("azext_edge.edge.providers.rpsaas.adr.helpers.logger", autospec=True)


@pytest.mark.parametrize("connected", [True, False])
def test_check_cluster_connectivity(mocked_cmd, mocked_logger, mocked_responses: responses, connected: bool):
    from azext_edge.edge.providers.rpsaas.adr.helpers import check_cluster_connectivity
    # base resource - should be ok if it is not an instance object
    resource = {
        "extendedLocation": {
            "name": generate_resource_id(
                resource_group_name=generate_random_string(),
                resource_provider=generate_random_string(),
                resource_path=f"/{generate_random_string()}"
            )
        }
    }
    # the custom location
    cl_resource = {
        "properties": {
            "hostResourceId": generate_resource_id(
                resource_group_name=generate_random_string(),
                resource_provider="Microsoft.Kubernetes/connectedClusters",
                resource_path=f"/{generate_random_string()}"
            )
        }
    }
    # get custom location (from base resource)
    mocked_responses.add(
        method=responses.GET,
        url=f"{BASE_URL}{resource['extendedLocation']['name']}",
        json=cl_resource,
        status=200,
        content_type="application/json",
    )
    # get cluster (from custom location)
    mocked_responses.add(
        method=responses.GET,
        url=f"{BASE_URL}{cl_resource['properties']['hostResourceId']}".replace("resourceGroups", "resourcegroups"),
        json={"properties": {"connectivityStatus": "connected" if connected else "offline"}},
        status=200,
        content_type="application/json",
    )
    check_cluster_connectivity(cmd=mocked_cmd, resource=resource)

    assert mocked_logger.warning.called is not connected


@pytest.mark.parametrize("connected", [True, False])
@pytest.mark.parametrize("subscription", [None, generate_random_string()])
def test_get_extended_location(
    mocked_cmd, mocked_logger, mocked_responses: responses, connected: bool, subscription: str
):
    from azext_edge.edge.providers.rpsaas.adr.helpers import get_extended_location
    name = generate_random_string()
    resource_group = generate_random_string()
    location = generate_random_string()
    # base resource - should be ok if it is not an instance object
    resource = {
        "extendedLocation": {
            "name": generate_resource_id(
                resource_group_name=generate_random_string(),
                resource_provider=generate_random_string(),
                resource_path=f"/{generate_random_string()}"
            )
        },
        "id": generate_resource_id(
            resource_subscription=subscription,
            resource_group_name=resource_group,
            resource_provider="Microsoft.IoTOperations/instances",
            resource_path=f"/{name}"
        )
    }
    # the custom location
    cl_resource = {
        "properties": {
            "hostResourceId": generate_resource_id(
                resource_group_name=generate_random_string(),
                resource_provider="Microsoft.Kubernetes/connectedClusters",
                resource_path=f"/{generate_random_string()}"
            )
        }
    }
    # get instance
    mocked_responses.add(
        method=responses.GET,
        url=f"{BASE_URL}{resource['id']}",
        json=resource,
        status=200,
        content_type="application/json",
    )
    # get custom location (from base resource)
    mocked_responses.add(
        method=responses.GET,
        url=f"{BASE_URL}{resource['extendedLocation']['name']}",
        json=cl_resource,
        status=200,
        content_type="application/json",
    )
    # get cluster (from custom location)
    mocked_responses.add(
        method=responses.GET,
        url=f"{BASE_URL}{cl_resource['properties']['hostResourceId']}".replace("resourceGroups", "resourcegroups"),
        json={
            "location": location,
            "properties": {"connectivityStatus": "connected" if connected else "offline"}
        },
        status=200,
        content_type="application/json",
    )
    result = get_extended_location(
        cmd=mocked_cmd,
        instance_name=name,
        instance_resource_group=resource_group,
        instance_subscription=subscription
    )

    assert result["type"] == "CustomLocation"
    assert result["name"] == resource['extendedLocation']['name']
    assert result["cluster_location"] == location
    assert mocked_logger.warning.called is not connected


@pytest.mark.parametrize("configuration", [
    "",
    json.dumps({generate_random_string(): generate_random_string()}),
])
@pytest.mark.parametrize("is_file", [True, False])
def test_process_additional_configuration(
    mocker, configuration, is_file
):
    from azext_edge.edge.providers.rpsaas.adr.helpers import process_additional_configuration
    patched_read_file = mocker.patch("azext_edge.edge.util.read_file_content")
    file_name = None
    if is_file:
        patched_read_file.return_value = configuration
        file_name = generate_random_string()
    else:
        patched_read_file.side_effect = FileOperationError("Not a file.")

    if is_file and not configuration:
        with pytest.raises(InvalidArgumentValueError):
            process_additional_configuration(file_name)
        return

    result = process_additional_configuration(file_name if is_file else configuration)
    if configuration == "":
        assert result is None
    else:
        assert result == configuration


def test_process_additional_configuration_error(mocker):
    from azext_edge.edge.providers.rpsaas.adr.helpers import process_additional_configuration
    configuration = json.dumps({generate_random_string(): generate_random_string()})
    configuration = configuration[-2:-1]  # remove the } to make invalid
    file_name = generate_random_string

    # file
    patched_read_file = mocker.patch("azext_edge.edge.util.read_file_content")
    patched_read_file.return_value = configuration
    with pytest.raises(InvalidArgumentValueError):
        process_additional_configuration(file_name)

    # in-line
    patched_read_file.side_effect = FileOperationError("Not a file.")
    with pytest.raises(InvalidArgumentValueError):
        process_additional_configuration(configuration)


@pytest.mark.parametrize("original_props", [
    None,
    {
        "method": generate_random_string(),
        "x509Credentials": {"certificateSecretName": generate_random_string()},
        "usernamePasswordCredentials": {
            "usernameSecretName": generate_random_string(),
            "passwordSecretName": generate_random_string(),
        },
    }
])
@pytest.mark.parametrize("req", [
    {},
    {
        "auth_mode": ADRAuthModes.anonymous.value
    },
    {
        "auth_mode": ADRAuthModes.certificate.value,
        "certificate_reference": generate_random_string()
    },
    {
        "certificate_reference": generate_random_string()
    },
    {
        "auth_mode": ADRAuthModes.userpass.value,
        "password_reference": generate_random_string(),
        "username_reference": generate_random_string()
    },
    {
        "password_reference": generate_random_string(),
        "username_reference": generate_random_string()
    },
])
def test_process_authentication(
    mocker, original_props, req
):
    from azext_edge.edge.providers.rpsaas.adr.helpers import process_authentication
    # remove logger warnings
    mocker.patch("azext_edge.edge.providers.rpsaas.adr.asset_endpoint_profiles.logger")
    result = process_authentication(
        auth_props=original_props,
        **req
    )

    if original_props is None:
        original_props = {}
    expected_auth = req.get("auth_mode") or original_props.get("method")
    if expected_auth is None and req.get("certificate_reference"):
        expected_auth = ADRAuthModes.certificate.value
    elif expected_auth is None and req.get("password_reference"):
        expected_auth = ADRAuthModes.userpass.value
    elif not req and not original_props:
        expected_auth = ADRAuthModes.anonymous.value
    assert result.get("method") == expected_auth

    if result.get("method") == ADRAuthModes.anonymous.value:
        assert result.get("x509Credentials") is None
        assert result.get("usernamePasswordCredentials") is None
    elif result.get("method") == ADRAuthModes.certificate.value:
        assert result["x509Credentials"]["certificateSecretName"] == req["certificate_reference"]
        assert result.get("usernamePasswordCredentials") is None
    elif result.get("method") == ADRAuthModes.userpass.value:
        assert result.get("x509Credentials") is None
        assert result["usernamePasswordCredentials"]["passwordSecretName"] == req["password_reference"]
        assert result["usernamePasswordCredentials"]["usernameSecretName"] == req["username_reference"]
    else:
        assert result == original_props


@pytest.mark.parametrize("req", [
    # Anonymous auth mode with other params
    {
        "auth_mode": ADRAuthModes.anonymous.value,
        "certificate_reference": generate_random_string()
    },
    {
        "auth_mode": ADRAuthModes.anonymous.value,
        "password_reference": generate_random_string(),
    },
    {
        "auth_mode": ADRAuthModes.anonymous.value,
        "username_reference": generate_random_string()
    },
    # certificate authmode with no params
    {
        "auth_mode": ADRAuthModes.certificate.value,
    },
    # certificate authmode with userpass params
    {
        "auth_mode": ADRAuthModes.certificate.value,
        "password_reference": generate_random_string(),
    },
    {
        "auth_mode": ADRAuthModes.certificate.value,
        "username_reference": generate_random_string()
    },
    # userpass with no params
    {
        "auth_mode": ADRAuthModes.userpass.value,
    },
    # userpass with certificate params
    {
        "auth_mode": ADRAuthModes.userpass.value,
        "certificate_reference": generate_random_string()
    },
    # userpass with only one of the params
    {
        "auth_mode": ADRAuthModes.userpass.value,
        "password_reference": generate_random_string(),
    },
    {
        "auth_mode": ADRAuthModes.userpass.value,
        "username_reference": generate_random_string(),
    },
    {
        "password_reference": generate_random_string(),
    },
    {
        "username_reference": generate_random_string(),
    },
])
def test_process_authentication_error(
    req
):
    from azext_edge.edge.providers.rpsaas.adr.helpers import process_authentication
    with pytest.raises(CLIError) as e:
        process_authentication(
            auth_props=None,
            **req
        )

    if req.get("auth_mode") in [None, ADRAuthModes.userpass.value] and any(
        [req.get("username_reference"), req.get("password_reference")]
    ):
        assert isinstance(e.value, RequiredArgumentMissingError)
    else:
        assert isinstance(e.value, MutuallyExclusiveArgumentError)
