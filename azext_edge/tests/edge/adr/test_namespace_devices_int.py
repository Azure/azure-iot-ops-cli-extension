# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
import json
from typing import List
from knack.log import get_logger
from azure.cli.core.azclierror import CLIInternalError
from azext_edge.edge.providers.adr.namespace_devices import DeviceEndpointType
from azext_edge.edge.util.common import parse_kvp_nargs

from ...generators import generate_random_string
from ...helpers import run

logger = get_logger(__name__)
pytestmark = pytest.mark.rpsaas


def test_namespace_device_lifecycle_operations(require_init, tracked_resources: List[str]):
    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    custom_location = require_init["customLocationId"]
    device_name_1 = f"dev-{generate_random_string(8, force_lower=True)}"
    device_name_2 = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name_onvif = f"onvif-{generate_random_string(8)}"
    endpoint_name_opcua = f"opcua-{generate_random_string(8)}"
    endpoint_name_media = f"media-{generate_random_string(8)}"
    endpoint_name_custom = f"custom-{generate_random_string(8)}"
    endpoint_name_rest = f"rest-{generate_random_string(8)}"
    endpoint_name_sse = f"sse-{generate_random_string(8)}"
    endpoint_name_mqtt = f"mqtt-{generate_random_string(8)}"

    # Create 1st device with minimal inputs
    result = run(
        f"az iot ops ns device create --name {device_name_1} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])
    assert_namespace_device_properties(
        result,
        name=device_name_1,
        enabled=True,
        custom_location=custom_location,
    )

    # Show device
    result = run(
        f"az iot ops ns device show --name {device_name_1} --instance {instance_name} "
        f"-g {resource_group}"
    )
    assert_namespace_device_properties(
        result,
        name=device_name_1,
        enabled=True,
        custom_location=custom_location,
    )

    # Query devices
    result = run(
        "az iot ops ns device query"
    )
    assert device_name_1 in [d["name"] for d in result]

    # Update device
    custom_attrs = ["location=building1", "department=manufacturing"]
    tags = ["env=test", "criticality=high"]
    result = run(
        f"az iot ops ns device update --name {device_name_1} --instance {instance_name} "
        f"-g {resource_group} --attr {' '.join(custom_attrs)} "
        f"--os-version 2.0 --tags {' '.join(tags)} --disabled"
    )
    assert_namespace_device_properties(
        result,
        name=device_name_1,
        enabled=False,
        custom_location=custom_location,
        operating_system_version="2.0",
        custom_attributes=custom_attrs,
        tags=tags,
    )

    # Create 2nd device with all inputs
    custom_attrs = ["floor=3", "building=HQ"]
    tags = ["environment=prod", "priority=p1"]
    result = run(
        f"az iot ops ns device create --name {device_name_2} --instance {instance_name} "
        f"-g {resource_group} "
        f"--attr {' '.join(custom_attrs)} --manufacturer Contoso "
        f"--model Gateway-X5 --os Linux --os-version 4.15 --tags {' '.join(tags)} --disabled"
    )
    tracked_resources.append(result["id"])
    assert_namespace_device_properties(
        result,
        name=device_name_2,
        enabled=False,
        custom_location=custom_location,
        custom_attributes=custom_attrs,
        manufacturer="Contoso",
        model="Gateway-X5",
        operating_system="Linux",
        operating_system_version="4.15",
        tags=tags,
    )

    # Add endpoints of all types to device_name_2
    # Add ONVIF endpoint
    endpoint_address = "https://192.168.1.100:8000/onvif/device_service"
    username_reference = "secretRef:username"
    password_reference = "secretRef:password"
    result = run(
        f"az iot ops ns device endpoint inbound add onvif --device {device_name_2} "
        f"--instance {instance_name} -g {resource_group} --name {endpoint_name_onvif} "
        f"--endpoint-address {endpoint_address} "
        f"--accept-invalid-hostnames true --accept-invalid-certificates true "
        f"--user-ref {username_reference} --pass-ref {password_reference} "
        f"--version 1"
    )
    assert_namespace_device_endpoint_props(
        result,
        endpoint_name=endpoint_name_onvif,
        endpoint_type=DeviceEndpointType.ONVIF.value,
        endpoint_address=endpoint_address,
        accept_invalid_hostnames=True,
        accept_invalid_certificates=True,
        authentication_method="UsernamePassword",
        username_reference=username_reference,
        password_reference=password_reference,
        version="1",
    )

    # Add Media endpoint
    endpoint_address = "rtsp://192.168.1.100:554/stream"
    result = run(
        f"az iot ops ns device endpoint inbound add media --device {device_name_2} "
        f"--instance {instance_name} -g {resource_group} --name {endpoint_name_media} "
        f"--endpoint-address rtsp://192.168.1.100:554/stream "
        f"--user-ref {username_reference} --pass-ref {password_reference} "
    )
    assert_namespace_device_endpoint_props(
        result,
        endpoint_name=endpoint_name_media,
        endpoint_type=DeviceEndpointType.MEDIA.value,
        endpoint_address=endpoint_address,
        authentication_method="UsernamePassword",
        username_reference=username_reference,
        password_reference=password_reference,
    )

    # Add OPC UA endpoint
    endpoint_address = "opc.tcp://192.168.1.100:4840"
    application_name = "TestApp"
    keep_alive = 15000
    publishing_interval = 2000
    sampling_interval = 1500
    queue_size = 2
    key_frame_count = 5
    session_timeout = 30000
    reconnect_period = 10000
    reconnect_exponential_backoff = 5000
    sub_lifetime = 60000
    sub_max_items = 10
    security_policy = "Basic256Sha256"
    security_mode = "signAndEncrypt"

    result = run(
        f"az iot ops ns device endpoint inbound add opcua --device {device_name_2} "
        f"--instance {instance_name} -g {resource_group} --name {endpoint_name_opcua} "
        f"--endpoint-address {endpoint_address} --application-name {application_name} "
        f"--keep-alive {keep_alive} --publishing-interval {publishing_interval} "
        f"--sampling-interval {sampling_interval} --queue-size {queue_size} "
        f"--key-frame-count {key_frame_count} --security-policy {security_policy} "
        f"--security-mode {security_mode} --run-asset-discovery "
        f"--session-timeout {session_timeout} --session-reconnect {reconnect_period} "
        f"--session-backoff {reconnect_exponential_backoff} "
        f"--session-tracing --subscription-lifetime {sub_lifetime} "
        f"--subscription-max-items {sub_max_items} --accept-certs "

    )
    assert_namespace_device_endpoint_props(
        result,
        endpoint_name=endpoint_name_opcua,
        endpoint_type=DeviceEndpointType.OPCUA.value,
        endpoint_address=endpoint_address,
        application_name=application_name,
        keep_alive=keep_alive,
        publishing_interval=publishing_interval,
        sampling_interval=sampling_interval,
        queue_size=queue_size,
        key_frame_count=key_frame_count,
        session_timeout=session_timeout,
        reconnect_period=reconnect_period,
        reconnect_exponential_backoff=reconnect_exponential_backoff,
        sub_lifetime=sub_lifetime,
        sub_max_items=sub_max_items,
        security_policy=security_policy,
        security_mode=security_mode,
        accept_certs=True,
        enable_tracing=True,
        run_asset_discovery=True,
        authentication_method="Anonymous",
    )

    # Add Custom endpoint
    endpoint_type = "Custom.Type"
    endpoint_address = "http://192.168.1.100:8080"
    custom_configuration = {"customSetting": "value"}
    certificate_reference = "secretRef:certificate"
    key_reference = "secretRef:privateKey"
    intermediate_cert_reference = "secretRef:intermediateCerts"
    trust_list = "cert1"
    result = run(
        f"az iot ops ns device endpoint inbound add custom --device {device_name_2} "
        f"--instance {instance_name} -g {resource_group} --name {endpoint_name_custom} "
        f"--endpoint-type {endpoint_type} --endpoint-address {endpoint_address} "
        f"--additional-config \"{{\\\"customSetting\\\": \\\"value\\\"}}\" "
        f"--cert-ref {certificate_reference} --key-ref {key_reference} "
        f"--intermediate-cert-ref {intermediate_cert_reference} --trust-list {trust_list} "
        f"--version 1.0.0"
    )
    assert_namespace_device_endpoint_props(
        result,
        endpoint_name=endpoint_name_custom,
        endpoint_type="Custom.Type",
        endpoint_address=endpoint_address,
        custom_configuration=custom_configuration,
        authentication_method="Certificate",
        certificate_reference=certificate_reference,
        key_reference=key_reference,
        intermediate_certificate_reference=intermediate_cert_reference,
        trust_list=trust_list,
        version="1.0.0",
    )

    # Add replace ONVIF with REST endpoint
    endpoint_address = "https://192.168.1.100:8000/rest/device_service"
    username_reference = "secretRef:username"
    password_reference = "secretRef:password"
    result = run(
        f"az iot ops ns device endpoint inbound add rest --device {device_name_2} "
        f"--instance {instance_name} -g {resource_group} --name {endpoint_name_onvif} "
        f"--endpoint-address {endpoint_address} "
        f"--user-ref {username_reference} --pass-ref {password_reference} "
        f"--version 1  --replace"
    )
    assert_namespace_device_endpoint_props(
        result,
        endpoint_name=endpoint_name_onvif,
        endpoint_type=DeviceEndpointType.REST.value,
        endpoint_address=endpoint_address,
        accept_invalid_hostnames=True,
        accept_invalid_certificates=True,
        authentication_method="UsernamePassword",
        username_reference=username_reference,
        password_reference=password_reference,
        version="1",
    )

    # Add REST endpoint with certificate authentication
    endpoint_address = "https://192.168.1.100:8443/rest/secure_service"
    certificate_reference = "secretRef:certificate"
    key_reference = "secretRef:privateKey"
    intermediate_cert_reference = "secretRef:intermediateCerts"
    result = run(
        f"az iot ops ns device endpoint inbound add rest --device {device_name_2} "
        f"--instance {instance_name} -g {resource_group} --name {endpoint_name_rest} "
        f"--endpoint-address {endpoint_address} "
        f"--cert-ref {certificate_reference} --key-ref {key_reference} "
        f"--intermediate-cert-ref {intermediate_cert_reference} "
        f"--version 2.0"
    )
    assert_namespace_device_endpoint_props(
        result,
        endpoint_name=endpoint_name_rest,
        endpoint_type=DeviceEndpointType.REST.value,
        endpoint_address=endpoint_address,
        accept_invalid_hostnames=True,
        accept_invalid_certificates=True,
        authentication_method="Certificate",
        certificate_reference=certificate_reference,
        key_reference=key_reference,
        intermediate_certificate_reference=intermediate_cert_reference,
        version="2.0",
    )

    # Add SSE endpoint with username/password authentication
    sse_endpoint_address = "https://192.168.1.100:8080/events"
    username_reference = "secretRef:username"
    password_reference = "secretRef:password"
    result = run(
        f"az iot ops ns device endpoint inbound add sse --device {device_name_2} "
        f"--instance {instance_name} -g {resource_group} --name {endpoint_name_sse} "
        f"--endpoint-address {sse_endpoint_address} "
        f"--username-ref {username_reference} --password-ref {password_reference} "
        f"--version 1.1"
    )
    assert_namespace_device_endpoint_props(
        result,
        endpoint_name=endpoint_name_sse,
        endpoint_type=DeviceEndpointType.SSE.value,
        endpoint_address=sse_endpoint_address,
        accept_invalid_hostnames=True,
        accept_invalid_certificates=True,
        authentication_method="UsernamePassword",
        username_reference=username_reference,
        password_reference=password_reference,
        version="1.1",
    )

    # Add MQTT endpoint (no authentication, in-cluster broker only)
    mqtt_endpoint_address = "aio-broker:18883"
    result = run(
        f"az iot ops ns device endpoint inbound add mqtt --device {device_name_2} "
        f"--instance {instance_name} -g {resource_group} --name {endpoint_name_mqtt} "
        f"--endpoint-address {mqtt_endpoint_address} "
        f"--version 0.3.4"
    )
    assert_namespace_device_endpoint_props(
        result,
        endpoint_name=endpoint_name_mqtt,
        endpoint_type=DeviceEndpointType.MQTT.value,
        endpoint_address=mqtt_endpoint_address,
        accept_invalid_hostnames=True,
        accept_invalid_certificates=True,
        authentication_method="Anonymous",
        version="0.3.4",
    )

    # List (all) endpoints
    result = run(
        f"az iot ops ns device endpoint list --device {device_name_2} "
        f"--instance {instance_name} -g {resource_group}"
    )
    assert len(result["inbound"]) == 7
    assert endpoint_name_onvif in result["inbound"]
    assert endpoint_name_media in result["inbound"]
    assert endpoint_name_opcua in result["inbound"]
    assert endpoint_name_custom in result["inbound"]
    assert endpoint_name_rest in result["inbound"]
    assert endpoint_name_sse in result["inbound"]
    assert endpoint_name_mqtt in result["inbound"]

    # List inbound endpoints option a
    result_1 = run(
        f"az iot ops ns device endpoint list --device {device_name_2} "
        f"--instance {instance_name} -g {resource_group} --inbound"
    )

    # List inbound endpoints option b
    result_2 = run(
        f"az iot ops ns device endpoint inbound list --device {device_name_2} "
        f"--instance {instance_name} -g {resource_group}"
    )
    assert len(result_1) == len(result_2) == 7
    assert result_1 == result_2
    assert endpoint_name_onvif in result_1
    assert endpoint_name_media in result_1
    assert endpoint_name_opcua in result_1
    assert endpoint_name_custom in result_1
    assert endpoint_name_rest in result_1
    assert endpoint_name_sse in result_1
    assert endpoint_name_mqtt in result_1

    # List inbound endpoints with specific type
    result = run(
        f"az iot ops ns device endpoint inbound list --device {device_name_2} "
        f"--instance {instance_name} -g {resource_group} --endpoint-type media"
    )
    assert len(result) == 1
    assert endpoint_name_media in result
    assert endpoint_name_custom not in result

    # Remove endpoints (REST cert-auth, SSE username-auth, MQTT anonymous)
    try:
        result = run(
            f"az iot ops ns device endpoint inbound remove --device {device_name_2} "
            f"--instance {instance_name} -g {resource_group} "
            f"--endpoint {endpoint_name_onvif} {endpoint_name_media} {endpoint_name_rest} "
            f"{endpoint_name_sse} {endpoint_name_mqtt} -y"
        )
    except CLIInternalError as e:
        # TODO - disable once bug is fixed / test is passing
        if "400216" in str(e) and "Invalid Address is specified" in str(e):
            pytest.xfail(f"Service-side validation bug: 400216 Invalid Address during endpoint remove: {e}")
        raise
    # Verify only the expected endpoints remain
    assert len(result) == 2
    # Removed endpoints should not be present in the result
    assert endpoint_name_onvif not in result
    assert endpoint_name_media not in result
    assert endpoint_name_rest not in result
    assert endpoint_name_sse not in result
    assert endpoint_name_mqtt not in result
    # Remaining endpoints should be present with their configurations
    assert endpoint_name_opcua in result
    assert endpoint_name_custom in result

    # Test device query functionality
    # Query for specific device by name
    result = run(
        f"az iot ops ns device query --name {device_name_1}"
    )
    assert len(result) == 1
    assert result[0]["name"] == device_name_1

    # Query for devices by instance
    result = run(
        f"az iot ops ns device query -i {instance_name} -g {resource_group}"
    )
    device_names = [d["name"] for d in result]
    assert device_name_2 in device_names
    assert device_name_1 in device_names

    # Query for devices by manufacturer
    result = run(
        "az iot ops ns device query --manufacturer Contoso"
    )
    device_names = [d["name"] for d in result]
    assert device_name_2 in device_names
    assert device_name_1 not in device_names

    # Delete devices
    try:
        run(
            f"az iot ops ns device delete --name {device_name_1} --instance {instance_name} "
            f"-g {resource_group} -y"
        )
    except CLIInternalError as e:
        if "Operation returned an invalid status" in str(e):
            logger.warning("Device api returns the wrong error code.")
        else:
            raise e
    try:
        run(
            f"az iot ops ns device delete --name {device_name_2} --instance {instance_name} "
            f"-g {resource_group} -y"
        )
    except CLIInternalError as e:
        if "Operation returned an invalid status" in str(e):
            logger.warning("Device api returns the wrong error code.")
        else:
            raise e


def assert_namespace_device_properties(
    result: dict,
    **expected
):
    """Assert that the device properties match the expected values."""
    # Check basic properties
    assert result["name"] == expected.get("name")

    # Check custom location
    if "custom_location" in expected:
        assert result["extendedLocation"]["name"] == expected["custom_location"]

    # Check device properties
    device_properties = result["properties"]

    # Check optional properties if specified
    assert device_properties.get("manufacturer") == expected.get("manufacturer")
    assert device_properties.get("model") == expected.get("model")
    assert device_properties.get("operatingSystem") == expected.get("operating_system")
    assert device_properties.get("operatingSystemVersion") == expected.get("operating_system_version")
    assert device_properties.get("enabled") == expected.get("enabled")

    if "custom_attributes" in expected:
        # Accept either a string or a list of strings with key=value pairs
        if isinstance(expected["custom_attributes"], str):
            expected["custom_attributes"] = (expected["custom_attributes"]).split(" ")
        custom_attributes = parse_kvp_nargs(expected["custom_attributes"])
        assert device_properties["attributes"] == custom_attributes

    # Check tags if specified
    if "tags" in expected:
        # Accept either a string or a list of strings with key=value pairs
        if isinstance(expected["tags"], str):
            expected["tags"] = (expected["tags"]).split(" ")
        tags = parse_kvp_nargs(expected["tags"])
        assert result["tags"] == tags


def assert_namespace_device_endpoint_props(
    result_endpoints: dict,
    **expected: dict
):
    """Asserts that the endpoint properties match the expected values."""
    # Check basic properties
    assert expected["endpoint_name"] in result_endpoints
    result_endpoint = result_endpoints[expected["endpoint_name"]]

    assert result_endpoint["endpointType"] == expected["endpoint_type"]
    assert result_endpoint["address"] == expected.get("endpoint_address")
    assert result_endpoint.get("version") == expected.get("version")

    # Check authentication
    result_auth = result_endpoint["authentication"]
    assert result_auth["method"] == expected.get("authentication_method", "Anonymous")

    if "username_reference" in expected:
        assert result_auth["usernamePasswordCredentials"]["usernameSecretName"] == expected["username_reference"]
        assert result_auth["usernamePasswordCredentials"]["passwordSecretName"] == expected["password_reference"]
    elif "certificate_reference" in expected:
        x509_creds = result_auth["x509Credentials"]
        assert x509_creds["certificateSecretName"] == expected["certificate_reference"]

        # Check optional key reference
        if "key_reference" in expected:
            assert x509_creds["keySecretName"] == expected["key_reference"]
        else:
            assert "keySecretName" not in x509_creds

        # Check optional intermediate certificate reference
        if "intermediate_certificate_reference" in expected:
            assert x509_creds["intermediateCertificatesSecretName"] == expected["intermediate_certificate_reference"]
        else:
            assert "intermediateCertificatesSecretName" not in x509_creds

    if "trust_list" in expected:
        assert result_endpoint["trustSettings"]["trustList"] == expected["trust_list"]

    # Check additional configuration
    # Custom Configuration
    if "custom_configuration" in expected:
        assert json.loads(result_endpoint["additionalConfiguration"]) == expected["custom_configuration"]

    # ONVIF Configuration
    if result_endpoint["endpointType"] == "Microsoft.Onvif":
        additional_config = json.loads(result_endpoint["additionalConfiguration"])
        assert additional_config["acceptInvalidHostnames"] == expected.get("accept_invalid_hostnames", False)
        assert additional_config["acceptInvalidCertificates"] == expected.get("accept_invalid_certificates", False)

    # pylint said too many if statements
    if result_endpoint["endpointType"] == "Microsoft.OpcUa":
        assert_namespace_device_opcua_props(
            json.loads(result_endpoint["additionalConfiguration"]),
            **expected,
        )


def assert_namespace_device_opcua_props(
    result_config: dict,
    **expected: dict
):
    """Asserts that the endpoint properties match the expected values."""

    # General
    if "application_name" in expected:
        assert result_config["applicationName"] == expected["application_name"]
    if "keep_alive" in expected:
        assert result_config["keepAliveMilliseconds"] == expected["keep_alive"]
    if "run_asset_discovery" in expected:
        assert result_config["runAssetDiscovery"] == expected["run_asset_discovery"]
    # Default
    if "publishing_interval" in expected:
        assert result_config["defaults"]["publishingIntervalMilliseconds"] == expected["publishing_interval"]
    if "sampling_interval" in expected:
        assert result_config["defaults"]["samplingIntervalMilliseconds"] == expected["sampling_interval"]
    if "queue_size" in expected:
        assert result_config["defaults"]["queueSize"] == expected["queue_size"]
    if "key_frame_count" in expected:
        assert result_config["defaults"]["keyFrameCount"] == expected["key_frame_count"]
    # Session
    if "timeout" in expected:
        assert result_config["session"]["timeoutMilliseconds"] == expected["timeout"]
    if "keep_alive_interval" in expected:
        assert result_config["session"]["keepAliveIntervalMilliseconds"] == expected["keep_alive_interval"]
    if "reconnect_period" in expected:
        assert result_config["session"]["reconnectPeriodMilliseconds"] == expected["reconnect_period"]
    if "reconnect_exponential_backoff" in expected:
        result_backoff = result_config["session"]["reconnectExponentialBackOffMilliseconds"]
        assert result_backoff == expected["reconnect_exponential_backoff"]
    if "enable_tracing" in expected:
        assert result_config["session"]["enableTracingHeaders"] is expected["enable_tracing"]
    # Subscription
    if "sub_lifetime" in expected:
        assert result_config["subscription"]["lifeTimeMilliseconds"] == expected["sub_lifetime"]
    if "sub_max_items" in expected:
        assert result_config["subscription"]["maxItems"] == expected["sub_max_items"]
    # Security
    if "accept_certs" in expected:
        assert result_config["security"]["autoAcceptUntrustedServerCertificates"] == expected["accept_certs"]
    if "security_policy" in expected:
        expected_policy = f"http://opcfoundation.org/UA/SecurityPolicy#{expected['security_policy']}"
        assert result_config["security"]["securityPolicy"] == expected_policy
    if "security_mode" in expected:
        assert result_config["security"]["securityMode"] == expected["security_mode"]
