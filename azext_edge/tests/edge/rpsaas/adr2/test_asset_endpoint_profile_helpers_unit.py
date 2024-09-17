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
        assert param in e.error_msg
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


@pytest.mark.parametrize("original_props", [
    None,
    {
        "mode": generate_random_string(),
        "x509Credentials": {"certificateReference": generate_random_string()},
        "usernamePasswordCredentials": {
            "usernameReference": generate_random_string(),
            "passwordReference": generate_random_string(),
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
    expected_auth = req.get("auth_mode") or original_props.get("mode")
    if expected_auth is None and req.get("certificate_reference"):
        expected_auth = AEPAuthModes.certificate.value
    if expected_auth is None and req.get("password_reference"):
        expected_auth = AEPAuthModes.userpass.value
    assert result.get("mode") == expected_auth

    if result.get("mode") == AEPAuthModes.anonymous.value:
        assert result.get("x509Credentials") is None
        assert result.get("usernamePasswordCredentials") is None
    elif result.get("mode") == AEPAuthModes.certificate.value:
        assert result["x509Credentials"]["certificateReference"] == req["certificate_reference"]
        assert result.get("usernamePasswordCredentials") is None
    elif result.get("mode") == AEPAuthModes.userpass.value:
        assert result.get("x509Credentials") is None
        assert result["usernamePasswordCredentials"]["passwordReference"] == req["password_reference"]
        assert result["usernamePasswordCredentials"]["usernameReference"] == req["username_reference"]
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
        "userAuthentication": {
            "mode": generate_random_string(),
            "x509Credentials": {"certificateReference": generate_random_string()},
            "usernamePasswordCredentials": {
                "usernameReference": generate_random_string(),
                "passwordReference": generate_random_string(),
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
        auth_props=properties.get("userAuthentication", {}),
        auth_mode=req.get("auth_mode"),
        certificate_reference=req.get("certificate_reference"),
        username_reference=req.get("username_reference"),
        password_reference=req.get("password_reference")
    )
    assert properties.get("userAuthentication", {}) == expected_auth