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

from azext_edge.edge.providers.adr.common import ADRAuthModes
from azext_edge.edge.providers.adr.specs import (
    NAMESPACE_DEVICE_OPCUA_ENDPOINT_SCHEMA,
    NAMESPACE_DEVICE_ONVIF_ENDPOINT_SCHEMA,
    NAMESPACE_ASSET_MEDIA_STREAM_CONFIGURATION_SCHEMA,
)
from ...generators import generate_random_string, BASE_URL, generate_resource_id

CONNECTED_CLUSTER_API = "2024-07-15-preview"


@pytest.fixture()
def mocked_logger(mocker):
    yield mocker.patch("azext_edge.edge.providers.adr.helpers.logger", autospec=True)


@pytest.mark.parametrize("connected", [True, False])
def test_check_cluster_connectivity(mocked_cmd, mocked_logger, mocked_responses: responses, connected: bool):
    from azext_edge.edge.providers.adr.helpers import check_cluster_connectivity
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
@pytest.mark.parametrize("namespace_name", [None, generate_random_string()])
def test_get_extended_location(
    mocked_cmd,
    mocked_logger,
    mocked_responses: responses,
    connected: bool,
    subscription: str,
    namespace_name: str
):
    from azext_edge.edge.providers.adr.helpers import get_extended_location
    name = generate_random_string()
    resource_group = generate_random_string()
    location = generate_random_string()
    namespace_resource_group = generate_random_string() if namespace_name else None
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
        ),
        "properties": {}
    }
    if namespace_name:
        resource["properties"]["adrNamespaceRef"] = {
            "resourceId": generate_resource_id(
                resource_subscription=subscription,
                resource_group_name=namespace_resource_group,
                resource_provider="Microsoft.DeviceRegistry/namespaces",
                resource_path=f"/{namespace_name}"
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

    if namespace_name:
        assert result["namespace"]["name"] == namespace_name
        assert result["namespace"]["resource_group"] == namespace_resource_group
    else:
        assert result["namespace"] is None


@pytest.mark.parametrize("subscription", [None, generate_random_string()])
@pytest.mark.parametrize("namespace_name", [generate_random_string()])
def test_get_namespace_for_instance(
    mocked_cmd,
    mocked_responses: responses,
    subscription: str,
    namespace_name: str
):
    from azext_edge.edge.providers.adr.helpers import get_namespace_for_instance

    instance_name = generate_random_string()
    instance_resource_group = generate_random_string()
    namespace_resource_group = generate_random_string()

    # Create mock instance resource
    instance_resource = {
        "id": generate_resource_id(
            resource_subscription=subscription,
            resource_group_name=instance_resource_group,
            resource_provider="Microsoft.IoTOperations/instances",
            resource_path=f"/{instance_name}"
        ),
        "properties": {
            "adrNamespaceRef": {
                "resourceId": generate_resource_id(
                    resource_subscription=subscription,
                    resource_group_name=namespace_resource_group,
                    resource_provider="Microsoft.DeviceRegistry/namespaces",
                    resource_path=f"/{namespace_name}"
                )
            }
        }
    }

    # Mock the instance API call
    mocked_responses.add(
        method=responses.GET,
        url=f"{BASE_URL}{instance_resource['id']}",
        json=instance_resource,
        status=200,
        content_type="application/json",
    )

    # Call the function
    result = get_namespace_for_instance(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        instance_subscription=subscription
    )

    # Verify the result
    assert result["name"] == namespace_name
    assert result["resource_group"] == namespace_resource_group


@pytest.mark.parametrize("subscription", [None, generate_random_string()])
@pytest.mark.parametrize("scenario", [
    "missing_adr_namespace_ref",
    "empty_adr_namespace_ref",
    "missing_resource_id",
    "empty_resource_id",
    "null_resource_id"
])
def test_get_namespace_for_instance_error(
    mocked_cmd,
    mocked_responses: responses,
    subscription: str,
    scenario: str
):
    from azext_edge.edge.providers.adr.helpers import get_namespace_for_instance

    instance_name = generate_random_string()
    instance_resource_group = generate_random_string()

    # Create mock instance resource based on scenario
    instance_resource = {
        "id": generate_resource_id(
            resource_subscription=subscription,
            resource_group_name=instance_resource_group,
            resource_provider="Microsoft.IoTOperations/instances",
            resource_path=f"/{instance_name}"
        )
    }

    if scenario == "missing_adr_namespace_ref":
        instance_resource["properties"] = {}
    elif scenario == "empty_adr_namespace_ref":
        instance_resource["properties"] = {
            "adrNamespaceRef": {}
        }
    elif scenario == "missing_resource_id":
        instance_resource["properties"] = {
            "adrNamespaceRef": {
                "someOtherProperty": "value"
            }
        }
    elif scenario == "empty_resource_id":
        instance_resource["properties"] = {
            "adrNamespaceRef": {
                "resourceId": ""
            }
        }
    elif scenario == "null_resource_id":
        instance_resource["properties"] = {
            "adrNamespaceRef": {
                "resourceId": None
            }
        }

    # Mock the instance API call
    mocked_responses.add(
        method=responses.GET,
        url=f"{BASE_URL}{instance_resource['id']}",
        json=instance_resource,
        status=200,
        content_type="application/json",
    )

    # Call the function and expect InvalidArgumentValueError
    with pytest.raises(InvalidArgumentValueError) as exc_info:
        get_namespace_for_instance(
            cmd=mocked_cmd,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
            instance_subscription=subscription
        )

    # Verify the error message
    expected_error = (
        f"Instance {instance_name} does not have an Device Registry namespace associated with it. "
        "Please update your instance to use new Device Registry features."
    )
    assert str(exc_info.value) == expected_error


@pytest.mark.parametrize("input_query", [
    # base
    "Resources | where type =~ 'Microsoft.DeviceRegistry/namespaces/assets'",
    # with some props
    "Resources | where type =~ 'Microsoft.DeviceRegistry/namespaces/assets' | where properties.enabled == true",
    # with custom location
    "Resources | where type =~ 'Microsoft.DeviceRegistry/namespaces/assets' "
    "| extend customLocation = tostring(extendedLocation.name)",
])
@pytest.mark.parametrize("instance_name", [None, generate_random_string()])
@pytest.mark.parametrize("instance_resource_group", [None, generate_random_string()])
@pytest.mark.parametrize("project_away_custom_location", [True, False])
def test_get_instance_query(
    input_query: str, instance_name: str, instance_resource_group: str, project_away_custom_location: bool
):
    from azext_edge.edge.providers.adr.helpers import get_instance_query
    result = get_instance_query(
        instance_name=instance_name,
        instance_resource_group=instance_resource_group,
        query=input_query,
        project_away_custom_location=project_away_custom_location
    )

    # nothing changes
    if not instance_name and not instance_resource_group:
        assert result == input_query
        return

    # make sure the query starts with the expected base
    assert result.startswith("Resources | where type =~ 'microsoft.iotoperations/instances'")

    # ensure there is customLocation defined (needed for query to join correctly)
    if "extend customLocation = tostring(extendedLocation.name)" not in input_query:
        input_query += " | extend customLocation = tostring(extendedLocation.name)"
    assert f"join kind=innerunique ({input_query}) on customLocation" in result

    # split the query and check for instance name and resource group
    split_query = [q.strip() for q in result.split("|")]
    if instance_name:
        assert f"where name =~ \"{instance_name}\"" in split_query
    if instance_resource_group:
        assert f"where resourceGroup =~ \"{instance_resource_group}\"" in split_query

    # make sure we got only the correct project-away
    assert ("project-away customLocation1, customLocation" in split_query) is project_away_custom_location
    assert ("project-away customLocation1" in split_query) is not project_away_custom_location


@pytest.mark.parametrize("param_mapping", [
    {},
    {  # lifted from assets
        "asset_name": "name",
        "device_name": "properties.deviceRef.deviceName",
        "device_endpoint_name": "properties.deviceRef.endpointName",
        "display_name": "properties.displayName",
        "documentation_uri": "properties.documentationUri",
        "external_asset_id": "properties.externalAssetId",
        "hardware_revision": "properties.hardwareRevision",
        "manufacturer": "properties.manufacturer",
        "manufacturer_uri": "properties.manufacturerUri",
        "model": "properties.model",
        "product_code": "properties.productCode",
        "serial_number": "properties.serialNumber",
        "software_revision": "properties.softwareRevision",
    }
])
@pytest.mark.parametrize("params", [
    {},
    {
        "asset_name": generate_random_string(),
        "device_name": generate_random_string(),
        "device_endpoint_name": generate_random_string(),
        "display_name": generate_random_string(),
        "documentation_uri": generate_random_string(),
        "external_asset_id": generate_random_string(),
        "hardware_revision": generate_random_string(),
        "manufacturer": generate_random_string(),
        "manufacturer_uri": generate_random_string(),
        "model": generate_random_string(),
        "product_code": generate_random_string(),
        "serial_number": generate_random_string(),
        "software_revision": generate_random_string(),
        "disabled": False
    },
    {  # mix ok and not ok params
        "asset_name": generate_random_string(),
        "operating_system": generate_random_string(),
        "disabled": True
    },
    {
        "disabled": None
    }
])
def test_get_query(param_mapping, params):
    from azext_edge.edge.providers.adr.helpers import get_query
    query = get_query(
        param_mapping=param_mapping,
        params=params
    )
    split_query = [q.strip() for q in query.split("|")]
    if "disabled" in params and params["disabled"] is not None:
        disabled = params.pop("disabled")
        assert f"where properties.enabled == {not disabled}" in split_query

    for param, value in params.items():
        if param in param_mapping:
            assert f"where {param_mapping[param]} =~ \"{value}\"" in split_query


@pytest.mark.parametrize("datasets", [
    [{"name": "", "dataPoints": generate_random_string()}],
    [{"name": "default", "dataPoints": generate_random_string()}],
])
@pytest.mark.parametrize("dataset_name", ["default", generate_random_string()])
def test_get_default_dataset(datasets, dataset_name):
    from azext_edge.edge.providers.adr.helpers import get_default_dataset
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
    from azext_edge.edge.providers.adr.helpers import get_default_dataset
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
    from azext_edge.edge.providers.adr.helpers import process_additional_configuration
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
    from azext_edge.edge.providers.adr.helpers import process_additional_configuration
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
        "certificate_reference": generate_random_string(),
        "key_reference": generate_random_string()
    },
    {
        "certificate_reference": generate_random_string(),
        "intermediate_certificate_reference": generate_random_string()
    },
    {
        "certificate_reference": generate_random_string(),
        "key_reference": generate_random_string(),
        "intermediate_certificate_reference": generate_random_string()
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
    from azext_edge.edge.providers.adr.helpers import process_authentication
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
        if req.get("key_reference"):
            assert result["x509Credentials"]["keySecretName"] == req["key_reference"]
        else:
            assert "keySecretName" not in result["x509Credentials"]
        if req.get("intermediate_certificate_reference"):
            assert result["x509Credentials"]["intermediateCertificatesSecretName"] == (
                req["intermediate_certificate_reference"]
            )
        else:
            assert "intermediateCertificatesSecretName" not in result["x509Credentials"]
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
    # Key reference without certificate reference
    {
        "key_reference": generate_random_string(),
    },
    # Intermediate certificate reference without certificate reference
    {
        "intermediate_certificate_reference": generate_random_string(),
    },
    # Both optional certificate fields without required certificate reference
    {
        "key_reference": generate_random_string(),
        "intermediate_certificate_reference": generate_random_string(),
    },
])
def test_process_authentication_error(
    req
):
    from azext_edge.edge.providers.adr.helpers import process_authentication
    with pytest.raises(CLIError) as e:
        process_authentication(
            auth_props=None,
            **req
        )

    if req.get("auth_mode") in [None, ADRAuthModes.userpass.value] and any(
        [req.get("username_reference"), req.get("password_reference")]
    ):
        assert isinstance(e.value, RequiredArgumentMissingError)
    elif any([req.get("key_reference"), req.get("intermediate_certificate_reference")]) and not req.get(
        "certificate_reference"
    ):
        assert isinstance(e.value, RequiredArgumentMissingError)
        assert "Certificate reference (--cert-ref) is required" in str(e.value)
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
    from azext_edge.edge.providers.adr.helpers import ensure_schema_structure

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
    from azext_edge.edge.providers.adr.helpers import ensure_schema_structure

    with pytest.raises(InvalidArgumentValueError) as exc:
        ensure_schema_structure(schema, data)

    for error in expected_error.split("\n"):
        assert error in str(exc.value)
