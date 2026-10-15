# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from azure.cli.core.azclierror import ArgumentUsageError

from azext_edge.edge.commands_edge import check
from azext_edge.edge.providers.checks import run_checks
from azext_edge.edge.providers.check.summary import check_summary
from azext_edge.edge.providers.edge_api import (
    DATAFLOW_ACTIVE_API,
    DEVICEREGISTRY_API_V1,
    MQ_ACTIVE_API,
)


@pytest.mark.parametrize("as_list", [False, True])
@pytest.mark.parametrize("pod_state, expected_status", [("Running", "success"), ("Failed", "error")])
def test_summary_without_broker_diagnostics_service(
    mocker, mock_broker_without_diagnostics_service, as_list, pod_state, expected_status
):
    fixture = mock_broker_without_diagnostics_service
    fixture["pods"]["aio-broker-backend"][0].status.phase = pod_state
    mocker.patch(
        "azext_edge.edge.providers.check.base.deployment.enumerate_ops_service_resources",
        return_value=(
            {"name": "enumerateBrokerApi", "description": "Enumerate MQTT Broker API resources", "status": "success"},
            {"Broker": []},
        ),
    )
    for service in ["akri", "deviceregistry", "opcua", "dataflows"]:
        mocker.patch(f"azext_edge.edge.providers.check.summary.check_{service}_deployment", return_value=[])

    result = check_summary(resource_name=None, resource_kinds=None, as_list=as_list)

    assert result["status"] == expected_status
    broker_target = result["targets"][MQ_ACTIVE_API.as_str()]["_all_"]
    assert broker_target["status"] == expected_status
    assert {"status": expected_status, "value": {"evalBrokers": expected_status}} in broker_target["evaluations"]
    fixture["get_service"].assert_not_called()


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
    assert result["postDeployment"][0]["description"] == "Service summary checks"
    expected_status = "skipped"
    for status in ["success", "warning", "error"]:
        if status in [akri_status, broker_status, deviceregistry_status, opcua_status, dataflow_status]:
            expected_status = status
    assert result["postDeployment"][0]["status"] == expected_status
    for service, status in [
        ("Akri", akri_status),
        (MQ_ACTIVE_API.as_str(), broker_status),
        (DEVICEREGISTRY_API_V1.as_str(), deviceregistry_status),
        ("OPCUA", opcua_status),
        (DATAFLOW_ACTIVE_API.as_str(), dataflow_status),
    ]:
        assert service in result["postDeployment"][0]["targets"]
        assert result["postDeployment"][0]["targets"][service]["_all_"]["status"] == status


@pytest.mark.parametrize(
    "resource_kinds",
    [
        ["broker", "dataflowprofile"],
        ["brokerlistener", "dataflowendpoint", "dataflow"],
    ],
)
@pytest.mark.parametrize("resource_name", ["broker", "dataflowprofile"])
@pytest.mark.parametrize("detail_level", [0, 1, 2])
@pytest.mark.parametrize("ops_service", [None])
@pytest.mark.parametrize("as_object", [True, False])
def test_summary_input_errors(
    mocked_cmd, mocked_client, mocked_config, as_object, ops_service, detail_level, resource_kinds, resource_name
):
    with pytest.raises(ArgumentUsageError):
        check(
            cmd=mocked_cmd,
            detail_level=detail_level,
            as_object=as_object,
            ops_service=ops_service,
            resource_kinds=resource_kinds,
            resource_name=resource_name,
        )
