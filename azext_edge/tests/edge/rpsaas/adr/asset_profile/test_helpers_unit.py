# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import pytest

from azure.cli.core.azclierror import (
    CLIError,
    MutuallyExclusiveArgumentError,
    RequiredArgumentMissingError,
    UnrecognizedArgumentError
)
from azext_edge.edge.util.common import assemble_nargs_to_dict
from azext_edge.edge.common import AEPAuthModes

from azext_edge.edge.providers.rpsaas.adr.asset_endpoint_profiles import (
    _process_authentication,
    _process_certificates,
    _update_properties
)

from .....generators import generate_random_string


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


@pytest.mark.parametrize("cert_list", [
    None,
    [
        [
            f"thumbprint={generate_random_string()}",
            f"secret={generate_random_string()}",
        ],
    ],
    [
        [
            f"password={generate_random_string()}",
            f"thumbprint={generate_random_string()}",
            f"secret={generate_random_string()}",
        ],
    ],
    [
        [
            f"password={generate_random_string()}",
            f"thumbprint={generate_random_string()}",
            f"secret={generate_random_string()}",
        ],
        [
            f"thumbprint={generate_random_string()}",
            f"secret={generate_random_string()}",
        ],
    ],
])
def test_process_certificates(cert_list):
    result = _process_certificates(cert_list)
    if cert_list is None:
        cert_list = []
    assert len(result) == len(cert_list)
    for i in range(len(result)):
        expected_item = assemble_nargs_to_dict(cert_list[i])
        assert result[i]["certThumbprint"] == expected_item["thumbprint"]
        assert result[i]["certSecretReference"] == expected_item["secret"]
        assert result[i]["certPasswordReference"] == expected_item.get("password")


@pytest.mark.parametrize("missing_arg", ["thumbprint", "secert"])
def test_process_certificates_missing_error(missing_arg):
    cert = [
        f"{arg}={generate_random_string()}" for arg in ["password", "thumbprint", "secert"] if arg != missing_arg
    ]
    with pytest.raises(RequiredArgumentMissingError) as e:
        _process_certificates(
            [cert]
        )
    assert e.value.error_msg.startswith("Transport authentication")

    with pytest.raises(RequiredArgumentMissingError) as e:
        _process_certificates(
            [[f"{missing_arg}={generate_random_string()}"]]
        )
    assert e.value.error_msg.startswith("Transport authentication")


@pytest.mark.parametrize("password", [None, generate_random_string()])
def test_process_certificates_unrecognized_error(password):
    cert = [
        f"thumbprint={generate_random_string()}",
        f"secret={generate_random_string()}",
        f"{generate_random_string()}={generate_random_string()}",
    ]
    if password:
        cert.append(f"password={password}")
    with pytest.raises(UnrecognizedArgumentError) as e:
        _process_certificates(
            [cert]
        )
    assert e.value.error_msg.startswith("Transport authentication")


@pytest.mark.parametrize("properties", [
    {},
    {
        "additionalConfiguration": generate_random_string(),
        "targetAddress": generate_random_string(),
        "transportAuthentication": {
            "ownCertificates": [generate_random_string()]
        },
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
        "transport_authentication": [
            [
                f"password={generate_random_string()}",
                f"thumbprint={generate_random_string()}",
                f"secret={generate_random_string()}",
            ],
        ],
    },
    {
        "target_address": generate_random_string(),
        "auth_mode": AEPAuthModes.userpass.value,
        "username_reference": generate_random_string(),
        "password_reference": generate_random_string(),
        "transport_authentication": [
            [
                f"password={generate_random_string()}",
                f"thumbprint={generate_random_string()}",
                f"secret={generate_random_string()}",
            ],
            [
                f"password={generate_random_string()}",
                f"thumbprint={generate_random_string()}",
                f"secret={generate_random_string()}"
            ]
        ],
    },
    {
        "additional_configuration": generate_random_string(),
        "auth_mode": AEPAuthModes.certificate.value,
        "certificate_reference": generate_random_string(),
    }
])
def test_update_properties(properties, req):
    # lazy way of copying to avoid having to make sure we copy possible the lists
    original_properties = json.loads(json.dumps(properties))
    _update_properties(
        properties=properties,
        **req
    )

    assert properties.get("additionalConfiguration") == req.get(
        "additional_configuration", original_properties.get("additionalConfiguration")
    )
    assert properties.get("targetAddress") == req.get("target_address", original_properties.get("targetAddress"))

    expected_certs = original_properties.get("transportAuthentication", {}).get("ownCertificates")
    if req.get("transport_authentication"):
        expected_certs = _process_certificates(req["transport_authentication"])
    assert properties.get("transportAuthentication", {}).get("ownCertificates") == expected_certs

    expected_auth = _process_authentication(
        auth_props=properties.get("userAuthentication", {}),
        auth_mode=req.get("auth_mode"),
        certificate_reference=req.get("certificate_reference"),
        username_reference=req.get("username_reference"),
        password_reference=req.get("password_reference")
    )
    assert properties.get("userAuthentication", {}) == expected_auth
