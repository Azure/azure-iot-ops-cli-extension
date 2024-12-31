# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import pytest
from time import sleep
from knack.log import get_logger
from ....generators import generate_random_string
from ....helpers import create_file, run

logger = get_logger(__name__)

# pytest mark for rpsaas (cloud-side) tests
pytestmark = pytest.mark.rpsaas


def test_asset_endpoint_lifecycle(require_init, tracked_resources, tracked_files):
    rg = require_init["resourceGroup"]
    instance = require_init["instanceName"]
    custom_location = require_init["customLocationId"]

    # Create an endpoint profile
    anon_name = "test-endpoint-" + generate_random_string(force_lower=True)[:4]
    address = f"opc.tcp://{generate_random_string()}:5000"
    endpoint_type = generate_random_string()
    anon_endpoint = run(
        f"az iot ops asset endpoint create custom -n {anon_name} -g {rg} --instance {instance} "
        f"--ta {address} --et {endpoint_type}"
    )
    tracked_resources.append(anon_endpoint["id"])
    assert_endpoint_props(
        result=anon_endpoint,
        name=anon_name,
        custom_location=custom_location,
        target_address=address,
        endpoint_type=endpoint_type,
    )

    show_endpoint = run(
        f"az iot ops asset endpoint show -n {anon_name} -g {rg}"
    )
    assert_endpoint_props(
        result=show_endpoint,
        name=anon_name,
        custom_location=custom_location,
        target_address=address,
        endpoint_type=endpoint_type,
    )

    update_endpoint = run(
        f"az iot ops asset endpoint update -n {anon_name} -g {rg}"
    )
    assert_endpoint_props(
        result=update_endpoint,
        name=anon_name,
        custom_location=custom_location,
        target_address=address,
        endpoint_type=endpoint_type,
    )

    json_content = json.dumps({
        generate_random_string(): generate_random_string(),
        generate_random_string(): {
            generate_random_string(): generate_random_string()
        },
        generate_random_string(): generate_random_string()
    })
    file_path = create_file(
        file_name=f"test_additional_config_{generate_random_string(size=4)}.json",
        module_file=__file__,
        tracked_files=tracked_files,
        content=json_content
    )

    anon_name2 = "test-endpoint-" + generate_random_string(force_lower=True)[:4]
    address = f"opc.tcp://{generate_random_string()}:5000"
    endpoint_type = generate_random_string()
    anon_endpoint2 = run(
        f"az iot ops asset endpoint create custom -n {anon_name2} -g {rg} --instance {instance} "
        f"--ta {address} --et {endpoint_type} --ac {file_path}"
    )
    tracked_resources.append(anon_endpoint2["id"])
    assert_endpoint_props(
        result=anon_endpoint2,
        name=anon_name2,
        custom_location=custom_location,
        target_address=address,
        endpoint_type=endpoint_type,
    )
    assert anon_endpoint2["properties"]["additionalConfiguration"] == json_content

    userpass_name = "test-endpoint-" + generate_random_string(force_lower=True)[:4]
    username = generate_random_string()
    password = generate_random_string()
    address = f"opc.tcp://{generate_random_string()}:5000"
    userpass_endpoint = run(
        f"az iot ops asset endpoint create onvif -n {userpass_name} -g {rg} --instance {instance} "
        f"--ta {address} --username-ref {username} --password-ref {password}"
    )
    tracked_resources.append(userpass_endpoint["id"])
    assert_endpoint_props(
        result=userpass_endpoint,
        name=userpass_name,
        custom_location=custom_location,
        target_address=address,
        username_reference=username,
        password_reference=password,
        endpoint_type="Microsoft.Onvif",
    )

    cert_name = "test-endpoint-" + generate_random_string(force_lower=True)[:4]
    cert = generate_random_string()
    address = f"opc.tcp://{generate_random_string()}:5000"
    opcua_args = {
        "application": generate_random_string(),
        "default_publishing_int": 10,
        "default_queue_size": 10,
        "default_sampling_int": 10,
        "keep_alive": 10,
        "security_mode": "sign",
        "security_policy": "Basic256",
        "session_keep_alive": 10,
        "session_reconnect_backoff": 10,
        "session_reconnect_period": 10,
        "session_timeout": 10,
        "subscription_life_time": 10,
        "subscription_max_items": 10
    }
    command = f"az iot ops asset endpoint create opcua -n {cert_name} -g {rg} --instance {instance} "\
        f"--ta {address} --certificate-ref {cert} --accept-untrusted-certs --run-asset-discovery "
    for arg, val in opcua_args.items():
        command += f"--{arg.replace('_', '-')} {val} "
    cert_endpoint = run(command)
    tracked_resources.append(cert_endpoint["id"])
    assert_endpoint_props(
        result=cert_endpoint,
        name=cert_name,
        custom_location=custom_location,
        target_address=address,
        certificate_reference=cert,
        endpoint_type="Microsoft.OpcUa",
    )
    assert_opcua_props(
        result=cert_endpoint,
        accept_untrusted_certs=True,
        run_asset_discovery=True,
        **opcua_args
    )

    run(f"az iot ops asset endpoint delete -n {userpass_name} -g {rg}")
    sleep(30)
    asset_list = run(f"az iot ops asset query --instance {instance}")
    asset_names = [asset["name"] for asset in asset_list]
    assert userpass_name not in asset_names
    tracked_resources.remove(userpass_endpoint["id"])


def assert_endpoint_props(result, **expected):
    assert result["name"] == expected["name"]
    assert result["extendedLocation"]["name"].endswith(expected["custom_location"])

    result_props = result["properties"]
    assert result_props["endpointProfileType"] == expected["endpoint_type"]
    assert result_props["targetAddress"] == expected["target_address"]

    user_auth = result_props["authentication"]
    if expected.get("certificate_reference"):
        assert user_auth["method"] == "Certificate"
        assert user_auth["x509Credentials"]["certificateSecretName"] == expected["certificate_reference"]
    elif expected.get("username_reference"):
        assert user_auth["method"] == "UsernamePassword"
        creds = user_auth["usernamePasswordCredentials"]
        assert creds["passwordSecretName"] == expected["password_reference"]
        assert creds["usernameSecretName"] == expected["username_reference"]
    else:
        assert user_auth["method"] == "Anonymous"


def assert_opcua_props(result, **expected):
    result_config = json.loads(result["properties"]["additionalConfiguration"])

    if expected.get("application"):
        result_config["applicationName"] = expected["application"]
    if expected.get("keep_alive"):
        result_config["keepAliveMilliseconds"] = expected["keep_alive"]
    if expected.get("run_asset_discovery") is not None:
        result_config["runAssetDiscovery"] = expected["run_asset_discovery"]

    # defaults
    if expected.get("default_publishing_int"):
        result_config["defaults"]["publishingIntervalMilliseconds"] = expected["default_publishing_int"]
    if expected.get("default_sampling_int"):
        result_config["defaults"]["samplingIntervalMilliseconds"] = expected["default_sampling_int"]
    if expected.get("default_queue_size"):
        result_config["defaults"]["queueSize"] = expected["default_queue_size"]

    # session
    if expected.get("session_timeout"):
        result_config["session"]["timeoutMilliseconds"] = expected["session_timeout"]
    if expected.get("session_keep_alive"):
        result_config["session"]["keepAliveIntervalMilliseconds"] = expected["session_keep_alive"]
    if expected.get("session_reconnect_period"):
        result_config["session"]["reconnectPeriodMilliseconds"] = expected["session_reconnect_period"]
    if expected.get("session_reconnect_backoff"):
        result_config["session"]["reconnectExponentialBackOffMilliseconds"] = expected["session_reconnect_backoff"]

    # subscription
    if expected.get("sub_life_time"):
        result_config["subscription"]["lifeTimeMilliseconds"] = expected["sub_life_time"]
    if expected.get("sub_max_items"):
        result_config["subscription"]["maxItems"] = expected["sub_max_items"]

    # security
    if expected.get("accept_untrusted_certs") is not None:
        result_config["security"]["autoAcceptUntrustedServerCertificates"] = expected["accept_untrusted_certs"]
    if expected.get("security_mode"):
        result_config["security"]["securityMode"] = expected["security_mode"]
    if expected.get("security_policy"):
        result_config["security"]["securityPolicy"] = (
            "http://opcfoundation.org/UA/SecurityPolicy#" + expected["security_policy"]
        )
