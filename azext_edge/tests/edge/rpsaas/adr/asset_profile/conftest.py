# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from .....generators import generate_random_string


@pytest.fixture()
def aep_helpers_fixture(mocker, request):
    def mock_update_properties(properties, **kwargs):
        """Minimize how much to check by setting everything update properties should touch to None."""
        for k in kwargs:
            properties.pop(k, None)
        properties["result"] = request.param["update_properties"]

    patched_up = mocker.patch(f"{AEP_PATH}._update_properties")
    patched_up.side_effect = mock_update_properties
    yield patched_up


# Paths for mocking
AEP_PATH = "azext_edge.edge.providers.rpsaas.adr.asset_endpoint_profiles"

# Generic objects
MINIMUM_AEP = {
    "extendedLocation": {
        "name": generate_random_string(),
        "type": generate_random_string(),
    },
    "id": generate_random_string(),
    "location": "westus3",
    "name": "aep-min",
    "properties": {
        "targetAddress": generate_random_string(),
        "userAuthentication": {
            "mode": "Anonymous"
        },
    },
    "resourceGroup": generate_random_string(),
    "type": "microsoft.deviceregistry/assetendpointprofiles"
}
FULL_AEP = {
    "extendedLocation": {
        "name": generate_random_string(),
        "type": generate_random_string(),
    },
    "id": generate_random_string(),
    "location": "westus3",
    "name": "aep-full",
    "properties": {
        "additionalConfiguration": generate_random_string(),
        "targetAddress": generate_random_string(),
        "transportAuthentication": {
            "ownCertificates": [
                {
                    "certThumbprint": generate_random_string(),
                    "certSecretReference": generate_random_string(),
                    "certPasswordReference": generate_random_string(),
                },
                {
                    "certThumbprint": generate_random_string(),
                    "certSecretReference": generate_random_string(),
                    "certPasswordReference": generate_random_string(),
                }
            ]
        },
        "userAuthentication": {
            "mode": "UsernamePassword",
            "usernamePasswordCredentials": {
                "passwordReference": generate_random_string(),
                "usernameReference": generate_random_string()
            }
        },
    },
    "resourceGroup": generate_random_string(),
    "type": "microsoft.deviceregistry/assetendpointprofiles"
}
