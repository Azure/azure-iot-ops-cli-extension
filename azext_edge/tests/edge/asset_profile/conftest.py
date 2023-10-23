# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import pytest
from ...generators import generate_generic_id


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
AEP_PATH = "azext_edge.edge.providers.asset_endpoint_profiles"

# Generic objects
MINIMUM_AEP = {
    "extendedLocation": {
        "name": generate_generic_id(),
        "type": generate_generic_id(),
    },
    "id": generate_generic_id(),
    "location": "westus3",
    "name": "aep-min",
    "properties": {
        "targetAddress": generate_generic_id(),
        "userAuthentication": {
            "mode": "Anonymous"
        },
    },
    "resourceGroup": generate_generic_id(),
    "type": "microsoft.deviceregistry/assetendpointprofiles"
}
FULL_AEP = {
    "extendedLocation": {
        "name": generate_generic_id(),
        "type": generate_generic_id(),
    },
    "id": generate_generic_id(),
    "location": "westus3",
    "name": "aep-full",
    "properties": {
        "additionalConfiguration": generate_generic_id(),
        "targetAddress": generate_generic_id(),
        "transportAuthentication": {
            "ownCertificates": [
                {
                    "certThumbprint": generate_generic_id(),
                    "certSecretReference": generate_generic_id(),
                    "certPasswordReference": generate_generic_id(),
                },
                {
                    "certThumbprint": generate_generic_id(),
                    "certSecretReference": generate_generic_id(),
                    "certPasswordReference": generate_generic_id(),
                }
            ]
        },
        "userAuthentication": {
            "mode": "UsernamePassword",
            "usernamePasswordCredentials": {
                "passwordReference": generate_generic_id(),
                "usernameReference": generate_generic_id()
            }
        },
    },
    "resourceGroup": generate_generic_id(),
    "type": "microsoft.deviceregistry/assetendpointprofiles"
}
