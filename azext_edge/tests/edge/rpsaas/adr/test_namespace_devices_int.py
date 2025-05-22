# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List
from azext_edge.edge.util.common import parse_kvp_nargs

from ....generators import generate_random_string
from ....helpers import run


def test_namespace_device_lifecycle_operations(require_init, tracked_resources: List[str]):
    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    custom_location = require_init["customLocationId"]
    namespace_name = f"ns-{generate_random_string(8)}"
    device_name_1 = f"dev-{generate_random_string(8)}"
    device_name_2 = f"dev-{generate_random_string(8)}"
    device_template_id = "dtmi:sample:device;1"
    endpoint_name_onvif = f"onvif-{generate_random_string(8)}"
    endpoint_name_opcua = f"opcua-{generate_random_string(8)}"
    endpoint_name_media = f"media-{generate_random_string(8)}"
    endpoint_name_custom = f"custom-{generate_random_string(8)}"

    # Create namespace
    result = run(f"az iot ops namespace create -n {namespace_name} -g {resource_group} --mi-system-assigned")
    tracked_resources.append(result["id"])  # only track namespace - deletion of it should delete devices too

    # Create 1st device with minimal inputs
    result = run(
        f"az iot ops namespace device create --name {device_name_1} --namespace {namespace_name} "
        f"-g {resource_group} --instance {instance_name} --template-id {device_template_id}"
    )
    assert_namespace_device_properties(
        result,
        name=device_name_1,
        template_id=device_template_id,
        enabled=True,
        custom_location=custom_location,
    )

    # Show device
    result = run(
        f"az iot ops namespace device show --name {device_name_1} --namespace {namespace_name} "
        f"-g {resource_group}"
    )
    assert_namespace_device_properties(
        result,
        name=device_name_1,
        template_id=device_template_id,
        enabled=True,
        custom_location=custom_location,
    )

    # List devices
    result = run(
        f"az iot ops namespace device list --namespace {namespace_name} -g {resource_group}"
    )
    assert len(result) == 1
    assert device_name_1 in [d["name"] for d in result]

    # Update device
    custom_attrs = ["location=building1", "department=manufacturing"]
    tags = ["env=test", "criticality=high"]
    result = run(
        f"az iot ops namespace device update --name {device_name_1} --namespace {namespace_name} "
        f"-g {resource_group} --attr {' '.join(custom_attrs)} --device-group-id critical-devices "
        f"--os-version 2.0 --tags {' '.join(tags)} --disabled"
    )
    assert_namespace_device_properties(
        result,
        name=device_name_1,
        template_id=device_template_id,
        enabled=True,
        custom_location=custom_location,
        device_group_id="critical-devices",
        operating_system_version="2.0",
        custom_attributes=custom_attrs,
        tags=tags,
    )

    # Create 2nd device with all inputs
    custom_attrs = ["floor=3", "building=HQ"]
    tags = ["environment=prod", "priority=p1"]
    result = run(
        f"az iot ops namespace device create --name {device_name_2} --namespace {namespace_name} "
        f"-g {resource_group} --instance {instance_name} --template-id {device_template_id} "
        f"--device-group-id production-devices --attr {' '.join(custom_attrs)} --manufacturer Contoso "
        f"--model Gateway-X5 --os Linux --os-version 4.15 --tags {' '.join(tags)} --disabled"
    )
    assert_namespace_device_properties(
        result,
        name=device_name_2,
        template_id=device_template_id,
        enabled=False,
        custom_location=custom_location,
        device_group_id="production-devices",
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
        f"az iot ops namespace device endpoint inbound add onvif --device {device_name_2} "
        f"--namespace {namespace_name} -g {resource_group} --endpoint-name {endpoint_name_onvif} "
        f"--endpoint-address {endpoint_address} "
        f"--accept-invalid-hostnames true --accept-invalid-certificates true "
        f"--username-reference {username_reference} --password-reference {password_reference} "
    )
    assert_namespace_device_endpoint_props(
        result,
        endpoint_name=endpoint_name_onvif,
        endpoint_type="Onvif",
        endpoint_address=endpoint_address,
        accept_invalid_hostnames=True,
        accept_invalid_certificates=True,
        authentication_method="UsernamePassword",
        username_reference=username_reference,
        password_reference=password_reference,
    )

    # Add Media endpoint
    endpoint_address = "rtsp://192.168.1.100:554/stream"
    result = run(
        f"az iot ops namespace device endpoint inbound add media --device {device_name_2} "
        f"--namespace {namespace_name} -g {resource_group} --endpoint-name {endpoint_name_media} "
        f"--endpoint-address rtsp://192.168.1.100:554/stream "
        f"--username-reference {username_reference} --password-reference {password_reference} "
    )
    assert_namespace_device_endpoint_props(
        result,
        endpoint_name=endpoint_name_media,
        endpoint_type="Media",
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
    security_mode = "SignAndEncrypt"

    result = run(
        f"az iot ops namespace device endpoint inbound add opcua --device {device_name_2} "
        f"--namespace {namespace_name} -g {resource_group} --endpoint-name {endpoint_name_opcua} "
        f"--endpoint-address {endpoint_address} --application-name {application_name} "
        f"--keep-alive {keep_alive} --publishing-interval {publishing_interval} "
        f"--sampling-interval {sampling_interval} --queue-size {queue_size} "
        f"--key-frame-count {key_frame_count} --security-policy {security_policy} "
        f"--security-mode {security_mode} --run-asset-discovery "
        f"--session-timeout {session_timeout} --reconnect-period {reconnect_period} "
        f"--reconnect-exponential-backoff {reconnect_exponential_backoff} "
        f"--enable-tracing --sub-lifetime {sub_lifetime} "
        f"--sub-max-items {sub_max_items} --accept-certs "

    )
    assert_namespace_device_endpoint_props(
        result,
        endpoint_name=endpoint_name_opcua,
        endpoint_type="OpcUa",
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
    trust_list = "cert1"
    result = run(
        f"az iot ops namespace device endpoint inbound add custom --device {device_name_2} "
        f"--namespace {namespace_name} -g {resource_group} --endpoint-name {endpoint_name_custom} "
        f"--endpoint-type {endpoint_type} --endpoint-address {endpoint_address} "
        f"--additional-configuration \"{{\\\"customSetting\\\": \\\"value\\\"}}\""
        f" --certificate-reference {certificate_reference} --trust-list {trust_list} "
    )
    assert_namespace_device_endpoint_props(
        result,
        endpoint_name=endpoint_name_custom,
        endpoint_type="Custom.Type",
        endpoint_address=endpoint_address,
        custom_configuration=custom_configuration,
        authentication_method="Certificate",
        certificate_reference=certificate_reference,
        trust_list=trust_list,
    )

    # List (all) endpoints
    result = run(
        f"az iot ops namespace device endpoint list --device {device_name_2} "
        f"--namespace {namespace_name} -g {resource_group} --all"
    )
    assert len(result["inbound"]) == 4
    assert endpoint_name_onvif in result["inbound"]
    assert endpoint_name_media in result["inbound"]
    assert endpoint_name_opcua in result["inbound"]
    assert endpoint_name_custom in result["inbound"]

    # List inbound endpoints option a
    result_1 = run(
        f"az iot ops namespace device endpoint list --device {device_name_2} "
        f"--namespace {namespace_name} -g {resource_group} --inbound"
    )

    # List inbound endpoints option b
    result_2 = run(
        f"az iot ops namespace device endpoint inbound list --device {device_name_2} "
        f"--namespace {namespace_name} -g {resource_group}"
    )
    assert len(result_1) == len(result_2) == 4
    assert result_1 == result_2
    assert endpoint_name_onvif in result
    assert endpoint_name_media in result
    assert endpoint_name_opcua in result
    assert endpoint_name_custom in result

    # Remove endpoints
    result = run(
        f"az iot ops namespace device endpoint inbound remove --device {device_name_2} "
        f"--namespace {namespace_name} -g {resource_group} "
        f"--endpoint-names {endpoint_name_onvif} {endpoint_name_media}"
    )
    assert len(result["endpoints"]) == 2
    assert endpoint_name_onvif not in result["endpoints"]
    assert endpoint_name_media not in result["endpoints"]
    assert endpoint_name_opcua in result["endpoints"]
    assert endpoint_name_custom in result["endpoints"]

    # Delete devices
    run(
        f"az iot ops namespace device delete --name {device_name_1} --namespace {namespace_name} "
        f"-g {resource_group} -y"
    )
    run(
        f"az iot ops namespace device delete --name {device_name_2} --namespace {namespace_name} "
        f"-g {resource_group} -y"
    )
    result = run(
        f"az iot ops namespace device list --namespace {namespace_name} -g {resource_group}"
    )
    assert len(result) == 0

    # Cleanup: Delete namespace
    run(f"az iot ops namespace delete -n {namespace_name} -g {resource_group} -y")
    tracked_resources.remove(result["id"])


def assert_namespace_device_properties(
    result: dict,
    **expected
):
    """Assert that the device properties match the expected values."""
    # Check basic properties
    assert result["name"] == expected.get("name")

    # Check custom location
    if "custom_location" in expected:
        assert result["properties"]["extendedLocation"]["name"] == expected["custom_location"]

    # Check device properties
    device_properties = result["properties"]
    assert device_properties["templateId"] == expected.get("template_id")

    # Check optional properties if specified
    assert device_properties.get("deviceGroupId") == expected.get("device_group_id")
    assert device_properties.get("manufacturer") == expected.get("manufacturer")
    assert device_properties.get("model") == expected.get("model")
    assert device_properties.get("operatingSystem") == expected.get("operating_system")
    assert device_properties.get("operatingSystemVersion") == expected.get("operating_system_version")
    assert device_properties.get("tags") == expected.get("tags")
    assert device_properties.get("enabled") == expected.get("enabled")

    if "custom_attributes" in expected:
        # Accept either a string or a list of strings with key=value pairs
        if isinstance(expected["custom_attributes"], str):
            expected["custom_attributes"] = (expected["custom_attributes"]).split(" ")
        custom_attributes = parse_kvp_nargs(expected["custom_attributes"])
        assert device_properties["customAttributes"] == custom_attributes

    # Check tags if specified
    if "tags" in expected:
        # Accept either a string or a list of strings with key=value pairs
        if isinstance(expected["tags"], str):
            expected["tags"] = (expected["tags"]).split(" ")
        tags = parse_kvp_nargs(expected["tags"])
        assert result["tags"] == tags


def assert_namespace_device_endpoint_props(
    result_endpoint: dict,
    **expected: dict
):
    """Asserts that the endpoint properties match the expected values."""
    # Check basic properties
    assert result_endpoint["name"] == expected["endpoint_name"]
    if expected["endpoint_type"] in ["Onvif", "Media", "OpcUa"]:
        expected["endpoint_type"] = f"Microsoft.{expected['endpoint_type']}"
    assert result_endpoint["endpointType"] == expected["endpoint_type"]
    assert result_endpoint["endpointType"] == f"Microsoft.{expected['endpoint_type']}"
    assert result_endpoint["address"] == expected.get("endpoint_address")

    # Check authentication
    result_auth = result_endpoint["authentication"]
    assert result_auth["method"] == expected.get("authentication_method", "Anonymous")

    if "username_reference" in expected:
        assert result_auth["usernamePasswordCredentials"]["usernameReference"] == expected["username_reference"]
        assert result_auth["usernamePasswordCredentials"]["passwordReference"] == expected["password_reference"]
    elif "certificate_reference" in expected:
        assert result_auth["x509Credentials"]["certificateSecretName"] == expected["certificate_reference"]

    if "trust_list" in expected:
        assert result_auth["trustSettings"]["trustList"] == expected["trust_list"]

    """Asserts that the endpoint additional configuration properties match the expected values."""
    # Check additional configuration
    # Custom Configuration
    if "custom_configuration" in expected:
        assert result_endpoint["additionalConfiguration"] == expected["custom_configuration"]

    # ONVIF Configuration
    if result_endpoint["endpointType"] == "Microsoft.Onvif":
        additional_config = result_endpoint["additionalConfiguration"]
        assert additional_config["acceptInvalidHostnames"] == expected.get("accept_invalid_hostnames", False)
        assert additional_config["acceptInvalidCertificates"] == expected.get("accept_invalid_certificates", False)

    # pylint said too many if statements
    if result_endpoint["endpointType"] == "Microsoft.OpcUa":
        assert_namespace_device_opcua_props(
            result_endpoint["additionalConfiguration"],
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
        assert result_config["default"]["publishingIntervalMilliseconds"] == expected["publishing_interval"]
    if "sampling_interval" in expected:
        assert result_config["default"]["samplingIntervalMilliseconds"] == expected["sampling_interval"]
    if "queue_size" in expected:
        assert result_config["default"]["queueSize"] == expected["queue_size"]
    if "key_frame_count" in expected:
        assert result_config["default"]["keyFrameCount"] == expected["key_frame_count"]
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
        assert result_config["session"]["enableTracing"] is expected["enableTracingHeaders"]
    # Subscription
    if "sub_lifetime" in expected:
        assert result_config["subscription"]["lifetimeMilliseconds"] == expected["sub_lifetime"]
    if "sub_max_items" in expected:
        assert result_config["subscription"]["maxItems"] == expected["sub_max_items"]
    # Security
    if "accept_certs" in expected:
        assert result_config["security"]["autoAcceptUntrustedServerCertificates"] == expected["accept_certs"]
    if "security_policy" in expected:
        expected_policy = f"http://opcfoundation.org/UA/SecurityPolicy#{expected['security_policy']}"
        assert result_config["securityPolicy"] == expected_policy
    if "security_mode" in expected:
        assert result_config["securityMode"] == expected["security_mode"]
