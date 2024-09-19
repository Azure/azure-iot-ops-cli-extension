# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from time import sleep
from knack.log import get_logger
from ....generators import generate_random_string
from ....helpers import run

logger = get_logger(__name__)


# TODO: update with OPCUA connector args
def test_asset_endpoint_lifecycle(require_init, tracked_resources):
    rg = require_init["resourceGroup"]
    instance = require_init["instanceName"]
    custom_location = require_init["customLocationId"]

    # Create an endpoint profile
    anon_name = "test-endpoint-" + generate_random_string(force_lower=True)[:4]
    address = f"opc.tcp://{generate_random_string()}:5000"
    anon_endpoint = run(
        f"az iot ops asset endpoint create opcua -n {anon_name} -g {rg} --instance {instance} "
        f"--ta {address}"
    )
    tracked_resources.append(anon_endpoint["id"])
    assert_endpoint_props(
        result=anon_endpoint,
        name=anon_name,
        custom_location=custom_location,
        target_address=address
    )

    show_endpoint = run(
        f"az iot ops asset endpoint show -n {anon_name} -g {rg}"
    )
    assert_endpoint_props(
        result=show_endpoint,
        name=anon_name,
        custom_location=custom_location,
        target_address=address
    )

    update_endpoint = run(
        f"az iot ops asset endpoint update -n {anon_name} -g {rg}"
    )
    assert_endpoint_props(
        result=update_endpoint,
        name=anon_name,
        custom_location=custom_location,
        target_address=address,
    )

    userpass_name = "test-endpoint-" + generate_random_string(force_lower=True)[:4]
    username = generate_random_string()
    password = generate_random_string()
    address = f"opc.tcp://{generate_random_string()}:5000"
    userpass_endpoint = run(
        f"az iot ops asset endpoint create opcua -n {userpass_name} -g {rg} --instance {instance} "
        f"--ta {address} --username-ref {username} --password-ref {password}"
    )
    tracked_resources.append(userpass_endpoint["id"])
    assert_endpoint_props(
        result=userpass_endpoint,
        name=userpass_name,
        custom_location=custom_location,
        target_address=address,
        username_reference=username,
        password_reference=password
    )

    # Certificate reference not supported yet
    cert_name = "test-endpoint-" + generate_random_string(force_lower=True)[:4]
    cert = generate_random_string()
    address = f"opc.tcp://{generate_random_string()}:5000"
    cert_endpoint = run(
        f"az iot ops asset endpoint create opcua -n {cert_name} -g {rg} --instance {instance} "
        f"--ta {address} --certificate-ref {cert}"
    )
    tracked_resources.append(cert_endpoint["id"])
    assert_endpoint_props(
        result=cert_endpoint,
        name=cert_name,
        custom_location=custom_location,
        target_address=address,
        certificate_reference=cert,
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
