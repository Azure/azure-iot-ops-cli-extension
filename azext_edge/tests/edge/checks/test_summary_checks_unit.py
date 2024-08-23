# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.providers.checks import run_checks


@pytest.mark.parametrize(
    "broker_deployment, broker_status",
    [
        # success
        (
            [
                {
                    "name": "broker",
                    "description": "Evaluate Broker",
                    "status": "success",
                    "targets": {
                        "broker.iotoperations.azure.com": {
                            "status": "success",
                            "namespace": {
                                "status": "success",
                            },
                        }
                    },
                },
            ],
            "success",
        ),
        # warning
        (
            [
                {
                    "name": "broker",
                    "description": "Evaluate Broker",
                    "status": "warning",
                    "targets": {
                        "broker.iotoperations.azure.com": {
                            "status": "warning",
                            "namespace": {
                                "status": "warning",
                            },
                        }
                    },
                },
            ],
            "warning",
        ),
    ],
)
@pytest.mark.parametrize(
    "akri_deployment, akri_status",
    [
        # success
        (
            [
                {
                    "name": "akri",
                    "description": "Evaluate Akri",
                    "status": "success",
                    "targets": {
                        "akri.sh/v0": {
                            "status": "success",
                            "namespace": {
                                "status": "success",
                            },
                        }
                    },
                },
            ],
            "success",
        ),
        # warning
        (
            [
                {
                    "name": "akri",
                    "description": "Evaluate Akri",
                    "status": "warning",
                    "targets": {
                        "akri.sh/v0": {
                            "status": "warning",
                            "namespace": {
                                "status": "warning",
                            },
                        }
                    },
                },
            ],
            "warning",
        ),
    ],
)
@pytest.mark.parametrize(
    "deviceregistry_deployment, deviceregistry_status",
    [
        # success
        (
            [
                {
                    "name": "deviceregistry",
                    "description": "Evaluate DeviceRegistry",
                    "status": "success",
                    "targets": {
                        "deviceregistry.microsoft.com": {
                            "status": "success",
                            "namespace": {
                                "status": "success",
                            },
                        }
                    },
                },
            ],
            "success",
        ),
        # warning
        (
            [
                {
                    "name": "deviceregistry",
                    "description": "Evaluate DeviceRegistry",
                    "status": "warning",
                    "targets": {
                        "deviceregistry.microsoft.com": {
                            "status": "warning",
                            "namespace": {
                                "status": "warning",
                            },
                        }
                    },
                },
            ],
            "warning",
        ),
    ],
)
@pytest.mark.parametrize(
    "opcua_deployment, opcua_status",
    [
        # success
        (
            [
                {
                    "name": "opcua",
                    "description": "Evaluate OPCUA",
                    "status": "success",
                    "targets": {
                        "opcua.iotoperations.azure.com": {
                            "status": "success",
                            "namespace": {
                                "status": "success",
                            },
                        }
                    },
                },
            ],
            "success",
        ),
        # warning
        (
            [
                {
                    "name": "opcua",
                    "description": "Evaluate OPCUA",
                    "status": "warning",
                    "targets": {
                        "opcua.iotoperations.azure.com": {
                            "status": "warning",
                            "namespace": {
                                "status": "warning",
                            },
                        }
                    },
                },
            ],
            "warning",
        ),
    ],
)
@pytest.mark.parametrize(
    "dataflow_deployment, dataflow_status",
    [
        # success
        (
            [
                {
                    "name": "dataflow",
                    "description": "Evaluate Dataflow",
                    "status": "success",
                    "targets": {
                        "dataflow.microsoft.com": {
                            "status": "success",
                            "namespace": {
                                "status": "success",
                            },
                        }
                    },
                },
            ],
            "success",
        ),
        # error
        (
            [
                {
                    "name": "dataflow",
                    "description": "Evaluate Dataflow",
                    "status": "error",
                    "targets": {
                        "dataflow.microsoft.com": {
                            "status": "warning",
                            "namespace": {
                                "status": "warning",
                            },
                        }
                    },
                },
            ],
            "error",
        ),
    ],
)
@pytest.mark.parametrize("ops_service", [None])
def test_summary_checks(
    mocker,
    mock_resource_types,
    ops_service,
    akri_deployment,
    akri_status,
    broker_deployment,
    broker_status,
    deviceregistry_deployment,
    deviceregistry_status,
    opcua_deployment,
    opcua_status,
    dataflow_deployment,
    dataflow_status,
):

    mocker.patch("azext_edge.edge.providers.check.akri.check_post_deployment", return_value=akri_deployment)
    mocker.patch("azext_edge.edge.providers.check.mq.check_post_deployment", return_value=broker_deployment)
    mocker.patch(
        "azext_edge.edge.providers.check.deviceregistry.check_post_deployment", return_value=deviceregistry_deployment
    )
    mocker.patch("azext_edge.edge.providers.check.opcua.check_post_deployment", return_value=opcua_deployment)
    mocker.patch("azext_edge.edge.providers.check.dataflow.check_post_deployment", return_value=dataflow_deployment)

    result = run_checks(
        pre_deployment=False,
        post_deployment=True,
        as_list=False,
        ops_service=ops_service,
    )

    assert result["title"] == "IoT Operations Summary"
    assert result["postDeployment"][0]["name"] == "evalAIOSummary"
    assert result["postDeployment"][0]["description"] == "AIO components"
    expected_status = "skipped"
    for status in ["success", "warning", "error"]:
        if status in [akri_status, broker_status, deviceregistry_status, opcua_status, dataflow_status]:
            expected_status = status
    assert result["postDeployment"][0]["status"] == expected_status
    for service, status in [
        ("Akri", akri_status),
        ("Broker", broker_status),
        ("DeviceRegistry", deviceregistry_status),
        ("OPCUA", opcua_status),
        ("Dataflow", dataflow_status),
    ]:
        assert service in result["postDeployment"][0]["targets"]
        assert result["postDeployment"][0]["targets"][service]["_all_"]["status"] == status
