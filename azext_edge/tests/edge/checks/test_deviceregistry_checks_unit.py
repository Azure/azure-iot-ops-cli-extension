# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from azext_edge.edge.providers.check.common import ResourceOutputDetailLevel
from azext_edge.edge.providers.check.deviceregistry import evaluate_assets, evaluate_asset_endpoint_profiles
from azext_edge.edge.providers.edge_api.deviceregistry import DeviceRegistryResourceKinds

from .conftest import (
    assert_check_by_resource_types,
    assert_conditions,
    assert_evaluations,
)
from ...generators import generate_generic_id


@pytest.mark.parametrize(
    "resource_kinds",
    [
        None,
        [],
        [DeviceRegistryResourceKinds.ASSET.value],
        [DeviceRegistryResourceKinds.ASSETENDPOINTPROFILE.value],
        [
            DeviceRegistryResourceKinds.ASSET.value,
            DeviceRegistryResourceKinds.ASSETENDPOINTPROFILE.value,
        ]
    ],
)
@pytest.mark.parametrize('ops_service', ['deviceregistry'])
def test_check_deviceregistry_by_resource_types(ops_service, mocker, mock_resource_types, resource_kinds):
    eval_lookup = {
        DeviceRegistryResourceKinds.ASSET.value:
            "azext_edge.edge.providers.check.deviceregistry.evaluate_assets",
        DeviceRegistryResourceKinds.ASSETENDPOINTPROFILE.value:
            "azext_edge.edge.providers.check.deviceregistry.evaluate_asset_endpoint_profiles",
    }

    assert_check_by_resource_types(ops_service, mocker, mock_resource_types, resource_kinds, eval_lookup)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize(
    "assets, namespace_conditions, namespace_evaluations",
    [
        (
            # assets
            [
                {
                    "metadata": {
                        "name": "asset-1",
                    },
                    "spec": {
                        "assetEndpointProfileUri": "endpoint",
                    }
                },
            ],
            # namespace conditions str
            ["spec.assetEndpointProfileUri"],
            # namespace evaluations str
            [
                [
                    ("status", "success"),
                    ("value/spec.assetEndpointProfileUri", "endpoint"),
                ],
            ]
        ),
        # assetEndpointProfileUri not defined
        (
            # assets
            [
                {
                    "metadata": {
                        "name": "asset-1",
                    },
                    "spec": {
                    }
                },
            ],
            # namespace conditions str
            ["spec.assetEndpointProfileUri"],
            # namespace evaluations str
            [
                [
                    ("status", "error"),
                    ("value/spec.assetEndpointProfileUri", ''),
                ],
            ]
        ),
        # datasource not defined
        (
            # assets
            [
                {
                    "metadata": {
                        "name": "asset-1",
                    },
                    "spec": {
                        "assetEndpointProfileUri": "endpoint",
                        "dataPoints": [
                            {
                                "name": "datapoint-1",
                                "type": "double",
                            },
                        ],
                    }
                },
            ],
            # namespace conditions str
            ["spec.assetEndpointProfileUri", 'len(spec.dataPoints)', "spec.dataPoints.[0].dataSource"],
            # namespace evaluations str
            [
                [
                    ("status", "success"),
                    ("value/spec.assetEndpointProfileUri", 'endpoint'),
                ],
                [
                    ("status", "success"),
                    ("value/len(spec.dataPoints)", 1),
                ],
                [
                    ("status", "error"),
                    ("value/spec.dataPoints.[0].dataSource", ""),
                ],
            ]
        ),
        # no assets
        (
            # assets
            [],
            # namespace conditions str
            [],
            # namespace evaluations str
            [
                [
                    ("status", "skipped"),
                    ("value", "Unable to fetch assets in any namespaces."),
                ],
            ]
        ),
        # status failed
        (
            # assets
            [
                {
                    "metadata": {
                        "name": "asset-1",
                    },
                    "spec": {
                        "assetEndpointProfileUri": "endpoint",
                        "status": {
                            "errors": [
                                {
                                    "code": "404",
                                    "message": "error",
                                }
                            ]
                        }
                    }
                },
            ],
            # namespace conditions str
            ["spec.assetEndpointProfileUri", "spec.status"],
            # namespace evaluations str
            [
                [
                    ("status", "success"),
                    ("value/spec.assetEndpointProfileUri", 'endpoint'),
                ],
                [
                    ("status", "error"),
                    ("value/spec.status", "{'errors': [{'code': '404', 'message': 'error'}]}"),
                ],
            ]
        ),
        # event Notifier not defined
        (
            # assets
            [
                {
                    "metadata": {
                        "name": "asset-1",
                    },
                    "spec": {
                        "assetEndpointProfileUri": "endpoint",
                        "events": [
                            {
                                "name": "event-1",
                            },
                        ]
                    }
                },
            ],
            # namespace conditions str
            ["spec.assetEndpointProfileUri", "len(spec.events)", "spec.events.[0].eventNotifier"],
            # namespace evaluations str
            [
                [
                    ("status", "success"),
                    ("value/spec.assetEndpointProfileUri", 'endpoint'),
                ],
                [
                    ("status", "success"),
                    ("value/len(spec.events)", 1),
                ],
                [
                    ("status", "error"),
                    ("value/spec.events.[0].eventNotifier", ""),
                ],
            ]
        ),
    ]
)
def test_assets_checks(
    mocker,
    assets,
    namespace_conditions,
    namespace_evaluations,
    mock_generate_deviceregistry_asset_target_resources,
    detail_level,
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        side_effect=[{"items": assets}],
    )

    namespace = generate_generic_id()
    for asset in assets:
        asset['metadata']['namespace'] = namespace
    result = evaluate_assets(detail_level=detail_level)

    assert result["name"] == "evalAssets"
    assert result["targets"]["deviceregistry.microsoft.com"]
    target = result["targets"]["deviceregistry.microsoft.com"]

    for namespace in target:
        assert namespace in result["targets"]["deviceregistry.microsoft.com"]

        target[namespace]["conditions"] = [] if not target[namespace]["conditions"] else target[namespace]["conditions"]
        assert_conditions(target[namespace], namespace_conditions)
        assert_evaluations(target[namespace], namespace_evaluations)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize(
    "asset_endpoint_profiles, namespace_conditions, namespace_evaluations",
    [
        (
            # asset_endpoint_profiles
            [
                {
                    "metadata": {
                        "name": "assetendpointprofile-1",
                    },
                    "spec": {
                        "uuid": "1234",
                    }
                },
            ],
            # namespace conditions str
            ["spec.uuid"],
            # namespace evaluations str
            [
                [
                    ("status", "success"),
                    ("value/spec.uuid", "1234"),
                ],
            ]
        ),
        # ownCertificates not defined
        (
            # asset_endpoint_profiles
            [
                {
                    "metadata": {
                        "name": "assetendpointprofile-1",
                    },
                    "spec": {
                        "uuid": "1234",
                        "transportAuthentication": {
                            "ownCertificates": None
                        },
                    }
                },
            ],
            # namespace conditions str
            ["spec.uuid", "spec.transportAuthentication.ownCertificates"],
            # namespace evaluations str
            [
                [
                    ("status", "success"),
                    ("value/spec.uuid", "1234"),
                ],
                [
                    ("status", "error"),
                    ("value/spec.transportAuthentication.ownCertificates", None),
                ],
            ]
        ),
        # passwordReference not defined
        (
            # asset_endpoint_profiles
            [
                {
                    "metadata": {
                        "name": "assetendpointprofile-1",
                    },
                    "spec": {
                        "uuid": "1234",
                        "userAuthentication": {
                            "mode": "UsernamePassword",
                            "usernamePasswordCredentials": {
                                "usernameReference": "username-1",
                            }
                        }
                    }
                },
            ],
            # namespace conditions str
            [
                "spec.uuid",
                "spec.userAuthentication.mode",
                "spec.userAuthentication.usernamePasswordCredentials.usernameReference",
                "spec.userAuthentication.usernamePasswordCredentials.passwordReference"
            ],
            # namespace evaluations str
            [
                [
                    ("status", "success"),
                    ("value/spec.uuid", "1234"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.userAuthentication.mode", "UsernamePassword"),
                ],
                [
                    ("status", "error"),
                    ("value/spec.userAuthentication.usernamePasswordCredentials.passwordReference", ''),
                ],
            ]
        ),
        # certificateReference not defined
        (
            # asset_endpoint_profiles
            [
                {
                    "metadata": {
                        "name": "assetendpointprofile-1",
                    },
                    "spec": {
                        "uuid": "1234",
                        "userAuthentication": {
                            "mode": "Certificate",
                            "x509Credentials": {
                                "certificateReference": None,
                            }
                        }
                    }
                },
            ],
            # namespace conditions str
            [
                "spec.uuid",
                "spec.userAuthentication.mode",
                "spec.userAuthentication.x509Credentials.certificateReference",
            ],
            # namespace evaluations str
            [
                [
                    ("status", "success"),
                    ("value/spec.uuid", "1234"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.userAuthentication.mode", "Certificate"),
                ],
                [
                    ("status", "error"),
                    ("value/spec.userAuthentication.x509Credentials.certificateReference", None),
                ],
            ]
        ),
        # no assetEndpointProfiles
        (
            # assetEndpointProfiles
            [],
            # namespace conditions str
            [],
            # namespace evaluations str
            [
                [
                    ("status", "skipped"),
                    ("value", "Unable to fetch asset endpoint profiles in any namespaces."),
                ],
            ]
        ),
    ]
)
def test_asset_endpoint_profiles_checks(
    mocker,
    asset_endpoint_profiles,
    namespace_conditions,
    namespace_evaluations,
    mock_generate_deviceregistry_asset_target_resources,
    detail_level,
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        side_effect=[{"items": asset_endpoint_profiles}],
    )

    namespace = generate_generic_id()
    for asset_endpoint_profile in asset_endpoint_profiles:
        asset_endpoint_profile['metadata']['namespace'] = namespace
    result = evaluate_asset_endpoint_profiles(detail_level=detail_level)

    assert result["name"] == "evalAssetEndpointProfiles"
    assert result["targets"]["deviceregistry.microsoft.com"]
    target = result["targets"]["deviceregistry.microsoft.com"]

    for namespace in target:
        assert namespace in result["targets"]["deviceregistry.microsoft.com"]

        target[namespace]["conditions"] = [] if not target[namespace]["conditions"] else target[namespace]["conditions"]
        assert_conditions(target[namespace], namespace_conditions)
        assert_evaluations(target[namespace], namespace_evaluations)
