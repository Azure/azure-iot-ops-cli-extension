# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy
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
from azext_edge.edge.providers.rpsaas.adr.specs import (
    NAMESPACE_DEVICE_OPCUA_ENDPOINT_SCHEMA,
    NAMESPACE_DEVICE_ONVIF_ENDPOINT_SCHEMA,
    NAMESPACE_ASSET_MEDIA_STREAM_CONFIGURATION_SCHEMA,
)
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


@pytest.mark.parametrize("datasets", [
    [{"name": "", "dataPoints": generate_random_string()}],
    [{"name": "default", "dataPoints": generate_random_string()}],
])
@pytest.mark.parametrize("dataset_name", ["default", generate_random_string()])
def test_get_default_dataset(datasets, dataset_name):
    from azext_edge.edge.providers.rpsaas.adr.helpers import get_default_dataset
    expected = deepcopy(datasets[0])
    if dataset_name != "default":
        expected = {"name": dataset_name, "dataPoints": generate_random_string()}
        datasets.append(expected)
    result = get_default_dataset(
        asset={"properties": {"datasets": datasets}},
        dataset_name=dataset_name
    )
    assert result["name"] == dataset_name
    assert result["dataPoints"] == expected["dataPoints"]


@pytest.mark.parametrize("dataset_name", ["default", generate_random_string()])
def test_get_default_dataset_error(dataset_name):
    from azext_edge.edge.providers.rpsaas.adr.helpers import get_default_dataset
    with pytest.raises(InvalidArgumentValueError):
        get_default_dataset(
            asset={"name": generate_random_string(), "properties": {}},
            dataset_name=dataset_name
        )
    with pytest.raises(InvalidArgumentValueError):
        get_default_dataset(
            asset={
                "name": generate_random_string(),
                "properties": {"datasets": [{"name": generate_random_string()}]}
            },
            dataset_name=dataset_name
        )


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
    mocked_logger, original_props, req
):
    from azext_edge.edge.providers.rpsaas.adr.helpers import process_authentication
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


@pytest.mark.parametrize("schema, data", [
    # Simple schema with basic data types
    (
        {
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer", "minimum": 0, "maximum": 150},
                "settings": {
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean"},
                        "value": {"type": "integer", "minimum": 1, "maximum": 100}
                    }
                }
            }
        },
        {
            "name": "Test User",
            "age": 30,
            "settings": {
                "enabled": True,
                "value": 50
            }
        }
    ),
    # Simple schema with minimum and maximum value exactly at boundary
    (
        {
            "properties": {
                "count": {"type": "integer", "minimum": 0},
                "percentage": {"type": "integer", "maximum": 100}
            }
        },
        {
            "count": 0,
            "percentage": 100
        }
    ),
    # Schema with nested objects
    (
        {
            "properties": {
                "name": {"type": "string"},
                "settings": {
                    "type": "object",
                    "properties": {
                        "security": {
                            "type": "object",
                            "properties": {
                                "mode": {"type": "string"}
                            }
                        },
                        "enabled": {"type": "boolean"},
                        "value": {"type": "integer", "minimum": 1, "maximum": 100},
                        "display": {
                            "type": "object",
                            "properties": {
                                "width": {"type": "integer", "minimum": 0},
                                "color": {
                                    "type": "object",
                                    "properties": {
                                        "red": {"type": "integer", "minimum": 0, "maximum": 255},
                                        "green": {"type": "integer", "minimum": 0, "maximum": 255},
                                        "blue": {"type": "integer", "minimum": 0, "maximum": 255}
                                    }
                                },
                                "height": {"type": "integer", "minimum": 0}
                            }
                        }
                    }
                }
            }
        },
        {
            "name": "Test User",
            "settings": {
                "security": {
                    "mode": "secure"
                },
                "enabled": True,
                "display": {
                    "color": {
                        "red": 255,
                        "green": 0,
                        "blue": 0
                    },
                    "width": 1920,
                    "height": 1080
                },
                "value": 50,
            }
        }
    ),
    # OPCUA endpoint schema with minimal data
    (
        NAMESPACE_DEVICE_OPCUA_ENDPOINT_SCHEMA,
        {
            "applicationName": "Test OPCUA App",
            "keepAliveMilliseconds": 10000,
            "defaults": {
                "publishingIntervalMilliseconds": 1000,
                "samplingIntervalMilliseconds": 1000,
                "queueSize": 1,
                "keyFrameCount": 0
            },
            "session": {
                "timeoutMilliseconds": 60000,
                "keepAliveIntervalMilliseconds": 10000,
                "reconnectPeriodMilliseconds": 2000,
                "reconnectExponentialBackOffMilliseconds": 10000,
                "enableTracingHeaders": False
            },
            "subscription": {
                "maxItems": 1000,
                "lifeTimeMilliseconds": 60000
            },
            "security": {
                "autoAcceptUntrustedServerCertificates": False,
                "securityPolicy": None,
                "securityMode": None
            },
            "runAssetDiscovery": False
        }
    ),
    # ONVIF endpoint schema
    (
        NAMESPACE_DEVICE_ONVIF_ENDPOINT_SCHEMA,
        {
            "acceptInvalidHostnames": True,
            "acceptInvalidCertificates": False
        }
    ),
    # Media stream configuration schema - has oneof
    (
        NAMESPACE_ASSET_MEDIA_STREAM_CONFIGURATION_SCHEMA,
        {
            "tasKType": "stream-to-rtsp",
            "mediaServerAddress": "rtsp://example.com/stream",
            "mediaServerPort": 554,
            "mediaServerPath": "/live",
        }
    ),
    # Test with null values in schema
    (
        {
            "properties": {
                "required_string": {"type": "string"},
                "optional_value": {"type": ["integer", "null"]}
            }
        },
        {
            "required_string": "test",
            "optional_value": None
        }
    ),
    # Test with null values in OPCUA security settings
    (
        NAMESPACE_DEVICE_OPCUA_ENDPOINT_SCHEMA,
        {
            "applicationName": "Test App",
            "keepAliveMilliseconds": 10000,
            "defaults": {
                "publishingIntervalMilliseconds": 1000,
                "samplingIntervalMilliseconds": 1000,
                "queueSize": 1,
                "keyFrameCount": 0
            },
            "session": {
                "timeoutMilliseconds": 60000,
                "keepAliveIntervalMilliseconds": None,
                "reconnectPeriodMilliseconds": 2000,
                "reconnectExponentialBackOffMilliseconds": 10000,
                "enableTracingHeaders": False
            },
            "subscription": {
                "maxItems": 1000,
                "lifeTimeMilliseconds": 60000
            },
            "security": {
                "autoAcceptUntrustedServerCertificates": False,
                "securityPolicy": None,
                "securityMode": None
            },
            "runAssetDiscovery": False
        }
    )
])
def test_ensure_schema_structure_valid(schema, data):
    """
    Test ensure_schema_structure with valid inputs that don't trigger validation errors.
    """
    from azext_edge.edge.providers.rpsaas.adr.helpers import ensure_schema_structure

    # This should not raise any exceptions for valid data
    ensure_schema_structure(schema, data)

    # Test passes if no exception is raised


@pytest.mark.parametrize("schema, data, expected_error", [
    # Test with value below minimum
    (
        {
            "properties": {
                "age": {"type": "integer", "minimum": 18}
            }
        },
        {
            "age": 15
        },
        "Invalid value for age: the value must be at least 18, instead got 15"
    ),
    # Test with two values above maximum
    (
        {
            "properties": {
                "percentage": {"type": "integer", "maximum": 100},
                "error": {"type": "integer", "maximum": 10}
            }
        },
        {
            "percentage": 120,
            "error": 12
        },
        "Invalid value for percentage: the value must be at most 100, instead got 120\n"
        "Invalid value for error: the value must be at most 10, instead got 12"
    ),
    # Test with value outside of both min and max
    (
        {
            "properties": {
                "score": {"type": "integer", "minimum": 0, "maximum": 10}
            }
        },
        {
            "score": 15
        },
        "Invalid value for score: the value must be between 0 and 10 inclusive, instead got 15"
    ),
    # Test with nested object having invalid value
    (
        {
            "properties": {
                "settings": {
                    "type": "object",
                    "properties": {
                        "threshold": {"type": "integer", "minimum": 5, "maximum": 50}
                    }
                }
            }
        },
        {
            "settings": {
                "threshold": 2
            }
        },
        "Invalid value for threshold: the value must be between 5 and 50 inclusive, instead got 2"
    ),
    # Test with oneOf schema with invalid data
    (
        {
            "oneOf": [
                {
                    "properties": {
                        "yellowCount": {"type": "integer", "minimum": 0, "maximum": 255},
                        "blueCount": {"type": "integer", "minimum": 0, "maximum": 255},
                    },
                },
                {
                    "properties": {
                        "redCount": {"type": "integer", "minimum": 0, "maximum": 255},
                        "greenCount": {"type": "integer", "minimum": 0, "maximum": 255},
                    },
                }
            ]
        },
        {
            "redCount": 300,
            "greenCount": 100
        },
        "Invalid value for redCount: the value must be between 0 and 255 inclusive, instead got 300"
    )
])
def test_ensure_schema_structure_invalid(schema, data, expected_error):
    """
    Test ensure_schema_structure with invalid inputs that should trigger validation errors.
    """
    from azext_edge.edge.providers.rpsaas.adr.helpers import ensure_schema_structure

    with pytest.raises(InvalidArgumentValueError) as exc:
        ensure_schema_structure(schema, data)

    for error in expected_error.split("\n"):
        assert error in str(exc.value)
