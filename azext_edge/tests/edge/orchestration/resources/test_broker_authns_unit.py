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

from azext_edge.edge.commands_mq import (
    add_broker_authn_method,
    apply_broker_authn,
    delete_broker_authn,
    list_broker_authns,
    show_broker_authn,
)
from azext_edge.edge.common import DEFAULT_BROKER

from ....generators import generate_random_string
from .conftest import get_base_endpoint, get_mock_resource
from .test_instances_unit import get_instance_endpoint, get_mock_instance_record
from azure.cli.core.azclierror import InvalidArgumentValueError


def get_broker_authn_endpoint(
    instance_name: str, broker_name: str, resource_group_name: str, authn_name: Optional[str] = None
) -> str:
    resource_path = f"/instances/{instance_name}/brokers/{broker_name}/authentications"
    if authn_name:
        resource_path += f"/{authn_name}"
    return get_base_endpoint(resource_group_name=resource_group_name, resource_path=resource_path)


def get_mock_broker_authn_record(
    authn_name: str, broker_name: str, instance_name: str, resource_group_name: str, properties: Optional[dict] = None
) -> dict:
    default_properties = {
        "authenticationMethods": [
            {"method": "ServiceAccountToken", "serviceAccountToken": {"audiences": ["aio-broker"]}}
        ],
        "provisioningState": "Succeeded",
    }
    return get_mock_resource(
        name=authn_name,
        resource_path=f"/instances/{instance_name}/brokers/{broker_name}/authentications/{authn_name}",
        properties=properties or default_properties,
        resource_group_name=resource_group_name,
        qualified_type="microsoft.iotoperations/instances/brokers/authentications",
    )


def test_broker_authn_show(mocked_cmd, mocked_responses: responses):
    authn_name = generate_random_string()
    broker_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_broker_authn_record = get_mock_broker_authn_record(
        authn_name=authn_name,
        broker_name=broker_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )

    mocked_responses.add(
        method=responses.GET,
        url=get_broker_authn_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            broker_name=broker_name,
            authn_name=authn_name,
        ),
        json=mock_broker_authn_record,
        status=200,
        content_type="application/json",
    )

    result = show_broker_authn(
        cmd=mocked_cmd,
        authn_name=authn_name,
        broker_name=broker_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )

    assert result == mock_broker_authn_record
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "records",
    [0, 2],
)
def test_broker_authn_list(mocked_cmd, mocked_responses: responses, records: int):
    broker_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_broker_authn_records = {
        "value": [
            get_mock_broker_authn_record(
                authn_name=generate_random_string(),
                broker_name=broker_name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
            )
            for _ in range(records)
        ]
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_broker_authn_endpoint(
            broker_name=broker_name, instance_name=instance_name, resource_group_name=resource_group_name
        ),
        json=mock_broker_authn_records,
        status=200,
        content_type="application/json",
    )

    result = list(
        list_broker_authns(
            cmd=mocked_cmd,
            broker_name=broker_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )
    )

    assert result == mock_broker_authn_records["value"]
    assert len(mocked_responses.calls) == 1


def test_broker_authn_delete(mocked_cmd, mocked_responses: responses):
    authn_name = generate_random_string()
    broker_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mocked_responses.add(
        method=responses.DELETE,
        url=get_broker_authn_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            broker_name=broker_name,
            authn_name=authn_name,
        ),
        status=204,
    )
    delete_broker_authn(
        cmd=mocked_cmd,
        authn_name=authn_name,
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
def test_broker_authn_apply(mocked_cmd, mocked_responses: responses, mocked_get_file_config: Mock, scenario: dict):
    authn_name = generate_random_string()
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
        url=get_broker_authn_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            broker_name=broker_name or DEFAULT_BROKER,
            authn_name=authn_name,
        ),
        json=expected_payload,
        status=200,
    )
    kwargs = {}
    if broker_name:
        kwargs["broker_name"] = broker_name
    create_result = apply_broker_authn(
        cmd=mocked_cmd,
        authn_name=authn_name,
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
    "existing_authn_config",
    [
        {},
        {
            "authenticationMethods": [
                {"method": "ServiceAccountToken", "serviceAccountTokenSettings": {"audiences": ["aio-internal"]}},
            ],
            "provisioningState": "Succeeded",
        },
    ],
)
@pytest.mark.parametrize(
    "scenario",
    [
        {
            "input": {"sat_audiences": ["my-audience1", "my-audience2"]},
            "expected_payload": {
                "authenticationMethods": [
                    {
                        "method": "ServiceAccountToken",
                        "serviceAccountTokenSettings": {"audiences": ["my-audience1", "my-audience2"]},
                    }
                ],
            },
        },
        {
            "input": {
                "x509_client_ca_cm": "client-ca",
                "x509_attrs": [
                    "root.subject=CN = Contoso Root CA Cert, OU = Engineering, C = US",
                    "root.attributes.organization=contoso",
                    "intermediate.subject=CN = Contoso Intermediate CA",
                    "intermediate.attributes.city=seattle",
                    "intermediate.attributes.foo=bar",
                    "smartfan.subject=CN = smart-fan",
                    "smartfan.attributes.building=17",
                ],
            },
            "expected_payload": {
                "authenticationMethods": [
                    {
                        "method": "X509",
                        "x509Settings": {
                            "authorizationAttributes": {
                                "intermediate": {
                                    "attributes": {"city": "seattle", "foo": "bar"},
                                    "subject": "CN = Contoso Intermediate CA",
                                },
                                "root": {
                                    "attributes": {"organization": "contoso"},
                                    "subject": "CN = Contoso Root CA Cert, OU = Engineering, C = US",
                                },
                                "smartfan": {"attributes": {"building": "17"}, "subject": "CN = smart-fan"},
                            },
                            "trustedClientCaCert": "client-ca",
                        },
                    }
                ],
            },
        },
        {
            "input": {
                "custom_endpoint": "https://localhost",
                "custom_ca_cm": "myca-ref",
                "custom_x509_secret_ref": "mysecret-ref",
                "custom_http_headers": ["a=b", "c=d"],
                "broker_name": "mybroker",
            },
            "expected_payload": {
                "authenticationMethods": [
                    {
                        "method": "Custom",
                        "customSettings": {
                            "auth": {"x509": {"secretRef": "mysecret-ref"}},
                            "caCertConfigMap": "myca-ref",
                            "endpoint": "https://localhost",
                            "headers": {"a": "b", "c": "d"},
                        },
                    }
                ],
            },
        },
        {
            "input": {
                "custom_endpoint": "https://localhost",
                "custom_ca_cm": "myca-ref",
                "custom_x509_secret_ref": "mysecret-ref",
                "show_config": True,
                "sat_audiences": ["my-audience1", "my-audience2"],
            },
            "expected_payload": {
                "authenticationMethods": [
                    {
                        "method": "ServiceAccountToken",
                        "serviceAccountTokenSettings": {"audiences": ["my-audience1", "my-audience2"]},
                    },
                    {
                        "method": "Custom",
                        "customSettings": {
                            "auth": {"x509": {"secretRef": "mysecret-ref"}},
                            "caCertConfigMap": "myca-ref",
                            "endpoint": "https://localhost",
                        },
                    },
                ],
            },
        },
        {
            "input": {},
            "expected_payload": {},
            "error": (InvalidArgumentValueError, "At least one authn config is required."),
        },
    ],
)
def test_broker_authn_method_add(
    mocked_cmd, mocked_responses: responses, scenario: dict, existing_authn_config: Optional[dict]
):
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    authn_name = generate_random_string()

    scenario_inputs: dict = scenario.get("input", {})
    broker_name = scenario_inputs.get("broker_name")
    expected_payload = scenario.get("expected_payload")
    error_type, error_msg = scenario.get("error", (None, None))

    if error_type:
        with pytest.raises(error_type) as exc:
            add_broker_authn_method(
                cmd=mocked_cmd,
                authn_name=authn_name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
                **scenario_inputs,
            )
        exc_msg = str(exc.value)
        assert exc_msg == error_msg
        return

    expected_authn_request = {}
    get_authn_kwargs = {}
    if not existing_authn_config:
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
        expected_authn_request = {
            "extendedLocation": mock_instance_record["extendedLocation"],
            "name": authn_name,
            "properties": expected_payload,
        }
        get_authn_kwargs["status"] = 404
    else:
        mock_authn_record = get_mock_broker_authn_record(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            broker_name=broker_name or DEFAULT_BROKER,
            authn_name=authn_name,
            properties=existing_authn_config,
        )
        expected_authn_request = deepcopy(mock_authn_record)
        expected_authn_request["properties"]["authenticationMethods"].extend(expected_payload["authenticationMethods"])
        get_authn_kwargs["status"] = 200
        get_authn_kwargs["json"] = mock_authn_record

    mocked_responses.add(
        method=responses.GET,
        url=get_broker_authn_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            broker_name=broker_name or DEFAULT_BROKER,
            authn_name=authn_name,
        ),
        **get_authn_kwargs,
    )

    show_config = scenario_inputs.get("show_config")
    if not show_config:
        put_response = mocked_responses.add(
            method=responses.PUT,
            url=get_broker_authn_endpoint(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                broker_name=broker_name or DEFAULT_BROKER,
                authn_name=authn_name,
            ),
            json=expected_authn_request,
            status=200,
        )

    add_result = add_broker_authn_method(
        cmd=mocked_cmd,
        authn_name=authn_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        wait_sec=0.1,
        **scenario_inputs,
    )
    if show_config:
        assert add_result == expected_authn_request["properties"]
        return

    assert add_result == expected_authn_request
    request_payload = json.loads(put_response.calls[0].request.body)
    assert request_payload == expected_authn_request
