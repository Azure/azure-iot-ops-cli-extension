# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from copy import deepcopy
from typing import Optional
from unittest.mock import Mock

import pytest
import responses
from azure.core.exceptions import ResourceNotFoundError

from azext_edge.edge.commands_mq import (
    add_broker_listener_port,
    create_broker_listener,
    delete_broker_listener,
    list_broker_listeners,
    remove_broker_listener_port,
    show_broker_listener,
)
from azext_edge.edge.common import DEFAULT_BROKER

from ....generators import generate_random_string
from .conftest import get_base_endpoint, get_mock_resource
from .test_instances_unit import get_instance_endpoint, get_mock_instance_record
from azure.cli.core.azclierror import InvalidArgumentValueError


@pytest.fixture
def mocked_logger(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.brokers.logger",
    )
    yield patched


def get_broker_listener_endpoint(
    instance_name: str, broker_name: str, resource_group_name: str, listener_name: Optional[str] = None
) -> str:
    resource_path = f"/instances/{instance_name}/brokers/{broker_name}/listeners"
    if listener_name:
        resource_path += f"/{listener_name}"
    return get_base_endpoint(resource_group_name=resource_group_name, resource_path=resource_path)


def get_mock_broker_listener_record(
    listener_name: str,
    broker_name: str,
    instance_name: str,
    resource_group_name: str,
    properties: Optional[dict] = None,
) -> dict:
    default_properties = {
        "ports": [
            {
                "authenticationRef": "authn",
                "port": 8883,
                "protocol": "Mqtt",
                "tls": {
                    "automatic": {
                        "issuerRef": {"apiGroup": "cert-manager.io", "kind": "Issuer", "name": "mq-dmqtt-frontend"}
                    },
                    "mode": "Automatic",
                },
            }
        ],
        "provisioningState": "Succeeded",
        "serviceName": "aio-broker-dmqtt-frontend",
        "serviceType": "ClusterIp",
    }
    return get_mock_resource(
        name=listener_name,
        resource_path=f"/instances/{instance_name}/brokers/{broker_name}/listeners/{listener_name}",
        properties=properties or default_properties,
        resource_group_name=resource_group_name,
    )


def test_broker_listener_show(mocked_cmd, mocked_responses: responses):
    listener_name = generate_random_string()
    broker_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_broker_listener_record = get_mock_broker_listener_record(
        listener_name=listener_name,
        broker_name=broker_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )

    mocked_responses.add(
        method=responses.GET,
        url=get_broker_listener_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            broker_name=broker_name,
            listener_name=listener_name,
        ),
        json=mock_broker_listener_record,
        status=200,
        content_type="application/json",
    )

    result = show_broker_listener(
        cmd=mocked_cmd,
        listener_name=listener_name,
        broker_name=broker_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )

    assert result == mock_broker_listener_record
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "records",
    [0, 2],
)
def test_broker_list(mocked_cmd, mocked_responses: responses, records: int):
    broker_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_broker_listener_records = {
        "value": [
            get_mock_broker_listener_record(
                listener_name=generate_random_string(),
                broker_name=broker_name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
            )
            for _ in range(records)
        ]
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_broker_listener_endpoint(
            broker_name=broker_name, instance_name=instance_name, resource_group_name=resource_group_name
        ),
        json=mock_broker_listener_records,
        status=200,
        content_type="application/json",
    )

    result = list(
        list_broker_listeners(
            cmd=mocked_cmd,
            broker_name=broker_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )
    )

    assert result == mock_broker_listener_records["value"]
    assert len(mocked_responses.calls) == 1


def test_broker_listener_delete(mocked_cmd, mocked_responses: responses):
    listener_name = generate_random_string()
    broker_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mocked_responses.add(
        method=responses.DELETE,
        url=get_broker_listener_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            broker_name=broker_name,
            listener_name=listener_name,
        ),
        status=204,
    )
    delete_broker_listener(
        cmd=mocked_cmd,
        listener_name=listener_name,
        broker_name=broker_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=True,
        wait_sec=0.25,
    )
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "scenario",
    [
        {"file_payload": {generate_random_string(): generate_random_string()}},
        {
            "file_payload": {generate_random_string(): generate_random_string()},
            "broker_name": generate_random_string(),
        },
    ],
)
def test_broker_listener_create(mocked_cmd, mocked_responses: responses, mocked_get_file_config: Mock, scenario: dict):
    listener_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    broker_name = scenario.get("broker_name")

    expected_payload = None
    file_payload = scenario.get("file_payload")
    if file_payload:
        expected_payload = file_payload
        expected_file_content = json.dumps(file_payload)
    mocked_get_file_config.return_value = expected_file_content

    mock_instance_record = get_mock_instance_record(name=instance_name, resource_group_name=resource_group_name)
    mocked_responses.add(
        method=responses.GET,
        url=get_instance_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
        ),
        json=mock_instance_record,
        status=200,
    )
    put_response = mocked_responses.add(
        method=responses.PUT,
        url=get_broker_listener_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            broker_name=broker_name or DEFAULT_BROKER,
            listener_name=listener_name,
        ),
        json=expected_payload,
        status=200,
    )
    kwargs = {}
    if broker_name:
        kwargs["broker_name"] = broker_name
    create_result = create_broker_listener(
        cmd=mocked_cmd,
        listener_name=listener_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        config_file="config.json",
        wait_sec=0.1,
        **kwargs,
    )
    assert len(mocked_responses.calls) == 2
    assert create_result == expected_payload
    request_payload = json.loads(put_response.calls[0].request.body)
    assert request_payload["extendedLocation"] == mock_instance_record["extendedLocation"]


@pytest.mark.parametrize(
    "existing_listener_config",
    [
        {},
        {
            "ports": [
                {
                    "port": 18883,
                    "protocol": "Mqtt",
                    "tls": {
                        "certManagerCertificateSpec": {
                            "issuerRef": {
                                "group": "cert-manager.io",
                                "kind": "ClusterIssuer",
                                "name": "azure-iot-operations-aio-certificate-issuer",
                            },
                            "privateKey": {"algorithm": "Ec256", "rotationPolicy": "Always"},
                        },
                        "mode": "Automatic",
                    },
                }
            ],
            "provisioningState": "Succeeded",
            "serviceName": "aio-broker",
            "serviceType": "ClusterIp",
        },
        {
            "ports": [
                {
                    "port": 1883,
                    "protocol": "Mqtt",
                    "tls": {
                        "certManagerCertificateSpec": {
                            "issuerRef": {
                                "group": "cert-manager.io",
                                "kind": "ClusterIssuer",
                                "name": "azure-iot-operations-aio-certificate-issuer",
                            },
                            "privateKey": {"algorithm": "Ec256", "rotationPolicy": "Always"},
                        },
                        "mode": "Automatic",
                    },
                }
            ],
            "provisioningState": "Succeeded",
            "serviceName": "aio-broker",
            "serviceType": "LoadBalancer",
        },
    ],
)
@pytest.mark.parametrize(
    "scenario",
    [
        {
            "input": {"port": 1883, "service_type": "ClusterIp"},
            "expected_payload": {
                "ports": [{"port": 1883}],
                "serviceType": "ClusterIp",
            },
        },
        {
            "input": {"port": 1883, "service_type": "ClusterIp", "show_config": True},
            "expected_payload": {
                "ports": [{"port": 1883}],
                "serviceType": "ClusterIp",
            },
        },
        {
            "input": {
                "port": 1883,
                "service_type": "NodePort",
                "authn_ref": "myauthn",
                "nodeport": 1000,
                "tls_auto_issuer_ref": ["name=myissuer", "kind=ClusterIssuer"],
            },
            "expected_payload": {
                "ports": [
                    {
                        "port": 1883,
                        "authenticationRef": "myauthn",
                        "nodePort": 1000,
                        "tls": {
                            "mode": "Automatic",
                            "certManagerCertificateSpec": {
                                "issuerRef": {"group": "cert-manager.io", "kind": "ClusterIssuer", "name": "myissuer"}
                            },
                        },
                    }
                ],
                "serviceType": "NodePort",
            },
        },
        {
            "input": {
                "port": 8883,
                "protocol": "WebSockets",
                "authn_ref": "myauthn",
                "authz_ref": "myauthz",
                "tls_auto_issuer_ref": ["name=myissuer", "kind=Issuer", "group=mygroup.com"],
                "tls_auto_duration": "24h",
                "tls_auto_key_algo": "Ec256",
                "tls_auto_key_rotation_policy": "Always",
                "tls_auto_renew_before": "5h",
                "tls_auto_san_dns": ["a.com", "b.com", "c.com"],
                "tls_auto_san_ip": ["192.168.1.1", "192.168.1.2"],
                "tls_auto_secret_name": "mySecretKey",
            },
            "expected_payload": {
                "ports": [
                    {
                        "port": 8883,
                        "authenticationRef": "myauthn",
                        "authorizationRef": "myauthz",
                        "protocol": "WebSockets",
                        "tls": {
                            "mode": "Automatic",
                            "certManagerCertificateSpec": {
                                "issuerRef": {"group": "mygroup.com", "kind": "Issuer", "name": "myissuer"},
                                "duration": "24h",
                                "privateKey": {"algorithm": "Ec256", "rotationPolicy": "Always"},
                                "renewBefore": "5h",
                                "san": {"dns": ["a.com", "b.com", "c.com"], "ip": ["192.168.1.1", "192.168.1.2"]},
                                "secretName": "mySecretKey",
                            },
                        },
                    }
                ],
                "serviceType": "LoadBalancer",
            },
        },
        {
            "input": {
                "port": 8883,
                "protocol": "Mqtt",
                "tls_manual_secret_ref": "mySecretRef",
                "service_name": "myservice",
                "broker_name": "mybroker",
            },
            "expected_payload": {
                "ports": [
                    {
                        "port": 8883,
                        "protocol": "Mqtt",
                        "tls": {
                            "mode": "Manual",
                            "manual": {"secretRef": "mySecretRef"},
                        },
                    }
                ],
                "serviceType": "LoadBalancer",
                "serviceName": "myservice",
            },
        },
        {
            "input": {
                "port": 8883,
                "protocol": "Mqtt",
                "tls_manual_secret_ref": "mySecretRef",
                "tls_auto_issuer_ref": ["name=myissuer", "kind=Issuer", "group=mygroup.com"],
            },
            "expected_payload": {},
            "error": (InvalidArgumentValueError, "TLS may be setup with an automatic or manual config, not both."),
        },
    ],
)
def test_broker_listener_port_add(
    mocked_cmd,
    mocked_responses: responses,
    scenario: dict,
    existing_listener_config: Optional[dict],
):
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    listener_name = generate_random_string()

    scenario_inputs: dict = scenario.get("input", {})
    broker_name = scenario_inputs.get("broker_name")
    expected_payload = scenario.get("expected_payload")
    error_type, error_msg = scenario.get("error", (None, None))

    if error_type:
        with pytest.raises(error_type) as exc:
            add_broker_listener_port(
                cmd=mocked_cmd,
                listener_name=listener_name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
                **scenario_inputs,
            )
        exc_msg = str(exc.value)
        assert exc_msg == error_msg
        return

    expected_listener_request = {}
    get_listener_kwargs = {}
    if not existing_listener_config:
        mock_instance_record = get_mock_instance_record(name=instance_name, resource_group_name=resource_group_name)
        mocked_responses.add(
            method=responses.GET,
            url=get_instance_endpoint(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
            ),
            json=mock_instance_record,
            status=200,
        )
        p = {"ports": expected_payload["ports"]}
        p["serviceType"] = scenario_inputs.get("service_type", "LoadBalancer")
        if "service_name" in scenario_inputs:
            p["serviceName"] = scenario_inputs["service_name"]

        expected_listener_request = {
            "extendedLocation": mock_instance_record["extendedLocation"],
            "name": listener_name,
            "properties": p,
        }
        get_listener_kwargs["status"] = 404
    else:
        mock_listener_record = get_mock_broker_listener_record(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            broker_name=broker_name or DEFAULT_BROKER,
            listener_name=listener_name,
            properties=existing_listener_config,
        )
        expected_listener_request = deepcopy(mock_listener_record)
        for i in range(len(expected_listener_request["properties"]["ports"])):
            if expected_listener_request["properties"]["ports"][i]["port"] == expected_payload["ports"][0]["port"]:
                expected_listener_request["properties"]["ports"].pop(i)
        expected_listener_request["properties"]["ports"].append(expected_payload["ports"][0])
        get_listener_kwargs["status"] = 200
        get_listener_kwargs["json"] = mock_listener_record

    mocked_responses.add(
        method=responses.GET,
        url=get_broker_listener_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            broker_name=broker_name or DEFAULT_BROKER,
            listener_name=listener_name,
        ),
        **get_listener_kwargs,
    )

    show_config = scenario_inputs.get("show_config")
    if not show_config:
        put_response = mocked_responses.add(
            method=responses.PUT,
            url=get_broker_listener_endpoint(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                broker_name=broker_name or DEFAULT_BROKER,
                listener_name=listener_name,
            ),
            json=expected_listener_request,
            status=200,
        )

    add_result = add_broker_listener_port(
        cmd=mocked_cmd,
        listener_name=listener_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        wait_sec=0.1,
        **scenario_inputs,
    )
    if show_config:
        assert add_result == expected_listener_request["properties"]
        return

    assert add_result == expected_listener_request
    request_payload = json.loads(put_response.calls[0].request.body)
    assert request_payload == expected_listener_request


@pytest.mark.parametrize(
    "existing_listener_config",
    [
        {},
        {
            "ports": [
                {
                    "port": 8883,
                    "protocol": "Mqtt",
                    "tls": {
                        "certManagerCertificateSpec": {
                            "issuerRef": {
                                "group": "cert-manager.io",
                                "kind": "ClusterIssuer",
                                "name": "azure-iot-operations-aio-certificate-issuer",
                            },
                            "privateKey": {"algorithm": "Ec256", "rotationPolicy": "Always"},
                        },
                        "mode": "Automatic",
                    },
                }
            ],
            "provisioningState": "Succeeded",
            "serviceName": "aio-broker",
            "serviceType": "ClusterIp",
        },
        {
            "ports": [
                {
                    "port": 1883,
                    "protocol": "Mqtt",
                    "tls": {
                        "certManagerCertificateSpec": {
                            "issuerRef": {
                                "group": "cert-manager.io",
                                "kind": "ClusterIssuer",
                                "name": "azure-iot-operations-aio-certificate-issuer",
                            },
                            "privateKey": {"algorithm": "Ec256", "rotationPolicy": "Always"},
                        },
                        "mode": "Automatic",
                    },
                },
                {
                    "port": 8883,
                    "protocol": "Mqtt",
                    "tls": {
                        "certManagerCertificateSpec": {
                            "issuerRef": {
                                "group": "cert-manager.io",
                                "kind": "ClusterIssuer",
                                "name": "azure-iot-operations-aio-certificate-issuer",
                            },
                            "privateKey": {"algorithm": "Ec256", "rotationPolicy": "Always"},
                        },
                        "mode": "Automatic",
                    },
                },
            ],
            "provisioningState": "Succeeded",
            "serviceName": "aio-broker",
            "serviceType": "LoadBalancer",
        },
    ],
)
@pytest.mark.parametrize(
    "scenario",
    [
        {
            "input": {"port": 1883},
        },
        {
            "input": {"port": 8883, "broker_name": "mybroker"},
        },
    ],
)
def test_broker_listener_port_remove(
    mocked_cmd,
    mocked_responses: responses,
    scenario: dict,
    existing_listener_config: Optional[dict],
    mocked_logger: Mock,
):
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    listener_name = generate_random_string()

    scenario_inputs: dict = scenario.get("input", {})
    broker_name = scenario_inputs.get("broker_name")

    if not existing_listener_config:
        mocked_responses.add(
            method=responses.GET,
            url=get_broker_listener_endpoint(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                broker_name=broker_name or DEFAULT_BROKER,
                listener_name=listener_name,
            ),
            status=404,
        )
        with pytest.raises(ResourceNotFoundError):
            remove_broker_listener_port(
                cmd=mocked_cmd,
                listener_name=listener_name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
                **scenario_inputs,
            )
        return

    mock_listener_record = get_mock_broker_listener_record(
        resource_group_name=resource_group_name,
        instance_name=instance_name,
        broker_name=broker_name or DEFAULT_BROKER,
        listener_name=listener_name,
        properties=existing_listener_config,
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_broker_listener_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            broker_name=broker_name or DEFAULT_BROKER,
            listener_name=listener_name,
        ),
        status=200,
        json=mock_listener_record,
    )

    existing_ports = [p["port"] for p in mock_listener_record["properties"]["ports"]]
    should_delete = False
    no_op = False
    if scenario_inputs["port"] in existing_ports:
        if len(existing_ports) - 1 == 0:
            should_delete = True
            mocked_responses.add(
                method=responses.DELETE,
                url=get_broker_listener_endpoint(
                    resource_group_name=resource_group_name,
                    instance_name=instance_name,
                    broker_name=broker_name or DEFAULT_BROKER,
                    listener_name=listener_name,
                ),
                status=204,
            )
    else:
        no_op = True

    cheap_response = {generate_random_string(): generate_random_string()}
    if all([not should_delete, not no_op]):
        put_response = mocked_responses.add(
            method=responses.PUT,
            url=get_broker_listener_endpoint(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                broker_name=broker_name or DEFAULT_BROKER,
                listener_name=listener_name,
            ),
            json=cheap_response,
            status=200,
        )

    remove_result = remove_broker_listener_port(
        cmd=mocked_cmd,
        listener_name=listener_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=True,
        wait_sec=0.1,
        **scenario_inputs,
    )
    if should_delete or no_op:
        if no_op:
            mocked_logger.warning.assert_called_once_with("No port modification detected.")
        if should_delete:
            mocked_logger.warning.assert_called_once_with(
                "Listener resource will be deleted as it will no longer have any ports configured."
            )
        assert not remove_result
        return

    assert remove_result == cheap_response
    request_payload = json.loads(put_response.calls[0].request.body)
    request_ports = [p["port"] for p in request_payload["properties"]["ports"]]
    assert scenario_inputs["port"] not in request_ports
