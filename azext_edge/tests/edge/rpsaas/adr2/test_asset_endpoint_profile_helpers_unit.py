# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy
import json
import pytest

from azure.cli.core.azclierror import (
    CLIError,
    InvalidArgumentValueError,
    MutuallyExclusiveArgumentError,
    RequiredArgumentMissingError,
)
from azext_edge.edge.util.common import assemble_nargs_to_dict

from azext_edge.edge.providers.rpsaas.adr2.asset_endpoint_profiles import (
    _assert_above_min,
    _build_opcua_config,
    _build_query_body,
    _process_authentication,
    _update_properties,
    AEP_RESOURCE_TYPE,
    AEPAuthModes
)
from ....generators import generate_random_string


@pytest.mark.parametrize("value", [-1, 100])
@pytest.mark.parametrize("minimum", [-1, 0])
def test_assert_above_min(value, minimum):
    param = generate_random_string()
    if value < minimum:
        with pytest.raises(InvalidArgumentValueError) as e:
            _assert_above_min(
                param=param, value=value, minimum=minimum
            )
        assert param in e.value.error_msg
    else:
        _assert_above_min(
            param=param, value=value, minimum=minimum
        )


@pytest.mark.parametrize("original_config", [
    None,
    {
        "applicationName": generate_random_string(),
        "keepAliveMilliseconds": 999,
        "runAssetDiscovery": False,
        "defaults": {
            "publishingIntervalMilliseconds": 888,
            "samplingIntervalMilliseconds": 777,
            "queueSize": 666
        },
        "session": {
            "timeoutMilliseconds": 555,
            "keepAliveIntervalMilliseconds": 444,
            "reconnectPeriodMilliseconds": 333,
            "reconnectExponentialBackOffMilliseconds": 222
        },
        "subscription": {
            "maxItems": 111,
            "lifeTimeMilliseconds": 9999
        },
        "security": {
            "autoAcceptUntrustedServerCertificates": False,
            "securityMode": generate_random_string(),
            "securityPolicy": generate_random_string()
        }
    }
])
@pytest.mark.parametrize("req", [
    {},
    {
        "application_name": generate_random_string(),
        "auto_accept_untrusted_server_certs": False,
        "default_publishing_interval": 111,
        "default_sampling_interval": 222,
        "default_queue_size": 333,
        "keep_alive": 444,
        "run_asset_discovery": True,
        "session_timeout": 555,
        "session_keep_alive": 666,
        "session_reconnect_period": 777,
        "session_reconnect_exponential_back_off": 888,
        "security_policy": generate_random_string(),
        "security_mode": generate_random_string(),
        "sub_max_items": 999,
        "sub_life_time": 1000,
    },
    {
        "auto_accept_untrusted_server_certs": True,
        "run_asset_discovery": False,
    }
])
def test_build_opcua_config(original_config, req):
    result = _build_opcua_config(
        original_config=json.dumps(original_config) if original_config else original_config,
        **req
    )
    result = json.loads(result)
    original_config = original_config or {}
    assert result.get("applicationName") == req.get("application_name", original_config.get("applicationName"))
    assert result.get("keepAliveMilliseconds") == req.get("keep_alive", original_config.get("keepAliveMilliseconds"))
    assert result.get("runAssetDiscovery") == req.get("run_asset_discovery", original_config.get("runAssetDiscovery"))

    og_defaults = original_config.get("defaults", {})
    res_defaults = result.get("defaults", {})
    assert res_defaults.get("publishingIntervalMilliseconds") == req.get(
        "default_publishing_interval", og_defaults.get("publishingIntervalMilliseconds")
    )
    assert res_defaults.get("samplingIntervalMilliseconds") == req.get(
        "default_sampling_interval", og_defaults.get("samplingIntervalMilliseconds")
    )
    assert res_defaults.get("queueSize") == req.get("default_queue_size", og_defaults.get("queueSize"))

    og_session = original_config.get("session", {})
    res_session = result.get("session", {})
    assert res_session.get("timeoutMilliseconds") == req.get(
        "session_timeout", og_session.get("timeoutMilliseconds")
    )
    assert res_session.get("keepAliveIntervalMilliseconds") == req.get(
        "session_keep_alive", og_session.get("keepAliveIntervalMilliseconds")
    )
    assert res_session.get("reconnectPeriodMilliseconds") == req.get(
        "session_reconnect_period", og_session.get("reconnectPeriodMilliseconds")
    )
    assert res_session.get("reconnectExponentialBackOffMilliseconds") == req.get(
        "session_reconnect_exponential_back_off", og_session.get("reconnectExponentialBackOffMilliseconds")
    )

    og_sub = original_config.get("subscription", {})
    res_sub = result.get("subscription", {})
    assert res_sub.get("maxItems") == req.get("sub_life_time", og_sub.get("maxItems"))
    assert res_sub.get("lifeTimeMilliseconds") == req.get("sub_max_items", og_sub.get("lifeTimeMilliseconds"))

    og_security = original_config.get("security", {})
    res_security = result.get("security", {})
    assert res_security.get("autoAcceptUntrustedServerCertificates") == req.get(
        "auto_accept_untrusted_server_certs", og_security.get("autoAcceptUntrustedServerCertificates")
    )
    assert res_security.get("securityMode") == req.get("security_mode", og_security.get("securityMode"))
    assert res_security.get("securityPolicy") == req.get("security_policy", og_security.get("securityPolicy"))


@pytest.mark.parametrize("asset_endpoint_profile_name", [None, generate_random_string()])
@pytest.mark.parametrize("auth_mode", [None, generate_random_string()])
@pytest.mark.parametrize("endpoint_profile_type", [None, generate_random_string()])
@pytest.mark.parametrize("location", [None, generate_random_string()])
@pytest.mark.parametrize("resource_group_name", [None, generate_random_string()])
@pytest.mark.parametrize("target_address", [None, generate_random_string()])
def test_build_query_body(
    asset_endpoint_profile_name,
    auth_mode,
    endpoint_profile_type,
    location,
    resource_group_name,
    target_address
):
    result = _build_query_body(
        asset_endpoint_profile_name=asset_endpoint_profile_name,
        auth_mode=auth_mode,
        endpoint_profile_type=endpoint_profile_type,
        location=location,
        resource_group_name=resource_group_name,
        target_address=target_address
    )
    result = [line.strip() for line in result.split("|")]
    assert result[-1] == "project id, customLocation, location, name, resourceGroup, provisioningState, tags, "\
        "type, subscriptionId"
    assert result[-2] == "extend provisioningState = properties.provisioningState"
    assert result[-3] == "extend customLocation = tostring(extendedLocation.name)"

    if resource_group_name:
        assert f"where resourceGroup =~ \"{resource_group_name}\"" in result
    if location:
        assert f"where location =~ \"{location}\"" in result
    if asset_endpoint_profile_name:
        assert f"where name =~ \"{asset_endpoint_profile_name}\"" in result
    if auth_mode:
        assert f"where properties.authentication.method =~ \"{auth_mode}\"" in result
    if endpoint_profile_type:
        assert f"where properties.endpointProfileType =~ \"{endpoint_profile_type}\"" in result
    if target_address:
        assert f"where properties.targetAddress =~ \"{target_address}\"" in result


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
        "auth_mode": AEPAuthModes.anonymous.value
    },
    {
        "auth_mode": AEPAuthModes.certificate.value,
        "certificate_reference": generate_random_string()
    },
    {
        "certificate_reference": generate_random_string()
    },
    {
        "auth_mode": AEPAuthModes.userpass.value,
        "password_reference": generate_random_string(),
        "username_reference": generate_random_string()
    },
    {
        "password_reference": generate_random_string(),
        "username_reference": generate_random_string()
    },
])
def test_process_authentication(
    original_props, req
):
    result = _process_authentication(
        auth_props=original_props,
        **req
    )

    if original_props is None:
        original_props = {}
    expected_auth = req.get("auth_mode") or original_props.get("method")
    if expected_auth is None and req.get("certificate_reference"):
        expected_auth = AEPAuthModes.certificate.value
    if expected_auth is None and req.get("password_reference"):
        expected_auth = AEPAuthModes.userpass.value
    assert result.get("method") == expected_auth

    if result.get("method") == AEPAuthModes.anonymous.value:
        assert result.get("x509Credentials") is None
        assert result.get("usernamePasswordCredentials") is None
    elif result.get("method") == AEPAuthModes.certificate.value:
        assert result["x509Credentials"]["certificateSecretName"] == req["certificate_reference"]
        assert result.get("usernamePasswordCredentials") is None
    elif result.get("method") == AEPAuthModes.userpass.value:
        assert result.get("x509Credentials") is None
        assert result["usernamePasswordCredentials"]["passwordSecretName"] == req["password_reference"]
        assert result["usernamePasswordCredentials"]["usernameSecretName"] == req["username_reference"]
    else:
        assert result == original_props


@pytest.mark.parametrize("req", [
    {
        "auth_mode": AEPAuthModes.anonymous.value,
        "certificate_reference": generate_random_string()
    },
    {
        "auth_mode": AEPAuthModes.anonymous.value,
        "password_reference": generate_random_string(),
    },
    {
        "auth_mode": AEPAuthModes.anonymous.value,
        "username_reference": generate_random_string()
    },
    {
        "auth_mode": AEPAuthModes.certificate.value,
    },
    {
        "auth_mode": AEPAuthModes.certificate.value,
        "password_reference": generate_random_string(),
    },
    {
        "auth_mode": AEPAuthModes.certificate.value,
        "username_reference": generate_random_string()
    },
    {
        "auth_mode": AEPAuthModes.userpass.value,
    },
    {
        "auth_mode": AEPAuthModes.userpass.value,
        "certificate_reference": generate_random_string()
    },
    {
        "auth_mode": AEPAuthModes.userpass.value,
        "password_reference": generate_random_string(),
    },
    {
        "auth_mode": AEPAuthModes.userpass.value,
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
    with pytest.raises(CLIError) as e:
        _process_authentication(
            auth_props=None,
            **req
        )

    if req.get("auth_mode") in [None, AEPAuthModes.userpass.value] and any(
        [req.get("username_reference"), req.get("password_reference")]
    ):
        assert isinstance(e.value, RequiredArgumentMissingError)
    else:
        assert isinstance(e.value, MutuallyExclusiveArgumentError)
    # bad scenarios: all mutual unless noted
    # authmode anon + any pass, user, cert
    # authmode cert + pass/user
    # authmode cert + no cert in param or props
    # authmode pass + cert
    # authmode pass + one of pass/user in result -> req
    # one of pass/user in result
    # pass, user, cert


@pytest.mark.parametrize("properties", [
    {},
    {
        "additionalConfiguration": generate_random_string(),
        "targetAddress": generate_random_string(),
        "authentication": {
            "method": generate_random_string(),
            "x509Credentials": {"certificateSecretName": generate_random_string()},
            "usernamePasswordCredentials": {
                "usernameSecretName": generate_random_string(),
                "passwordSecretName": generate_random_string(),
            },
        }
    }
])
@pytest.mark.parametrize("req", [
    {},
    {
        "target_address": generate_random_string(),
        "additional_configuration": generate_random_string(),
    },
    {
        "target_address": generate_random_string(),
        "additional_configuration": generate_random_string(),
        "auth_mode": AEPAuthModes.anonymous.value,
    },
    {
        "target_address": generate_random_string(),
        "auth_mode": AEPAuthModes.userpass.value,
        "username_reference": generate_random_string(),
        "password_reference": generate_random_string(),
    },
    {
        "additional_configuration": generate_random_string(),
        "auth_mode": AEPAuthModes.certificate.value,
        "certificate_reference": generate_random_string(),
    }
])
def test_update_properties(properties, req):
    # lazy way of copying to avoid having to make sure we copy possible the lists
    original_properties = deepcopy(properties)
    _update_properties(
        properties=properties,
        **req
    )

    assert properties.get("additionalConfiguration") == req.get(
        "additional_configuration", original_properties.get("additionalConfiguration")
    )
    assert properties.get("targetAddress") == req.get("target_address", original_properties.get("targetAddress"))

    expected_certs = original_properties.get("transportAuthentication", {}).get("ownCertificates")
    assert properties.get("transportAuthentication", {}).get("ownCertificates") == expected_certs

    expected_auth = _process_authentication(
        auth_props=properties.get("authentication", {}),
        auth_mode=req.get("auth_mode"),
        certificate_reference=req.get("certificate_reference"),
        username_reference=req.get("username_reference"),
        password_reference=req.get("password_reference")
    )
    assert properties.get("authentication", {}) == expected_auth