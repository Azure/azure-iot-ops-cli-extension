# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from typing import Optional
from unittest.mock import Mock

import pytest
import responses

from azure.core.exceptions import ResourceNotFoundError
from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_edge.edge.commands_dataflow import (
    apply_dataflow,
    delete_dataflow,
    show_dataflow,
    list_dataflows,
)
from azext_edge.edge.common import DEFAULT_DATAFLOW_PROFILE
from azext_edge.edge.providers.orchestration.common import DATAFLOW_ENDPOINT_TYPE_SETTINGS
from azext_edge.tests.edge.orchestration.resources.test_dataflow_endpoints_unit import (
    get_dataflow_endpoint_endpoint,
    get_mock_dataflow_endpoint_record,
)
from azext_edge.tests.edge.orchestration.resources.test_instances_unit import (
    get_instance_endpoint,
    get_mock_instance_record,
)

from ....generators import generate_random_string
from .conftest import get_base_endpoint, get_mock_resource


def get_dataflow_endpoint(
    profile_name: str, instance_name: str, resource_group_name: str, dataflow_name: Optional[str] = None
) -> str:
    resource_path = f"/instances/{instance_name}/dataflowProfiles/{profile_name}/dataflows"
    if dataflow_name:
        resource_path += f"/{dataflow_name}"
    return get_base_endpoint(resource_group_name=resource_group_name, resource_path=resource_path)


def get_mock_dataflow_record(
    dataflow_name: str,
    profile_name: str,
    instance_name: str,
    resource_group_name: str,
    trans_operation: Optional[dict] = None,
) -> dict:
    properties = {
        "operations": [
            {
                "operationType": "Source",
                "sourceSettings": {
                    "endpointRef": "myendpoint1",
                    "assetRef": "",
                    "serializationFormat": "Json",
                    "schemaRef": "",
                    "dataSources": [
                        "test"
                    ]
                }
            },
            {
                "operationType": "Destination",
                "destinationSettings": {
                    "endpointRef": "myendpoint2",
                    "dataDestination": "test"
                }
            }
        ],
        "profileRef": "mydataflowprofile",
        "mode": "Enabled",
        "provisioningState": "Succeeded",
    }

    if trans_operation:
        properties["operations"].append(trans_operation)

    return get_mock_resource(
        name=dataflow_name,
        resource_path=f"/instances/{instance_name}/dataflowProfiles/{profile_name}/dataflows/{dataflow_name}",
        properties=properties,
        resource_group_name=resource_group_name,
        qualified_type="microsoft.iotoperations/instances/dataflows",
        is_proxy_resource=True,
    )


def test_dataflow_show(mocked_cmd, mocked_responses: responses):
    dataflow_name = generate_random_string()
    profile_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_dataflow_record = get_mock_dataflow_record(
        dataflow_name=dataflow_name,
        profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )

    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_endpoint(
            dataflow_name=dataflow_name,
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            profile_name=profile_name,
        ),
        json=mock_dataflow_record,
        status=200,
        content_type="application/json",
    )

    result = show_dataflow(
        cmd=mocked_cmd,
        dataflow_name=dataflow_name,
        profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )

    assert result == mock_dataflow_record
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "records",
    [0, 2],
)
def test_dataflow_list(mocked_cmd, mocked_responses: responses, records: int):
    profile_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_dataflow_records = {
        "value": [
            get_mock_dataflow_record(
                dataflow_name=generate_random_string(),
                profile_name=profile_name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
            )
            for _ in range(records)
        ]
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_endpoint(
            profile_name=profile_name, instance_name=instance_name, resource_group_name=resource_group_name
        ),
        json=mock_dataflow_records,
        status=200,
        content_type="application/json",
    )

    result = list(
        list_dataflows(
            cmd=mocked_cmd,
            profile_name=profile_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )
    )

    assert result == mock_dataflow_records["value"]
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "scenario",
    [
        {
            "file_payload": get_mock_dataflow_record(
                dataflow_name=generate_random_string(),
                profile_name=generate_random_string(),
                instance_name=generate_random_string(),
                resource_group_name=generate_random_string(),
            ),
            "source_endpoint": get_mock_dataflow_endpoint_record(
                dataflow_endpoint_name="myendpoint1",
                instance_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                dataflow_endpoint_type="Mqtt",
                host="aio-broker",
            ),
            "destination_endpoint": get_mock_dataflow_endpoint_record(
                dataflow_endpoint_name="myendpoint2",
                instance_name=generate_random_string(),
                resource_group_name=generate_random_string(),
            ),
        },
        {
            "file_payload": get_mock_dataflow_record(
                dataflow_name=generate_random_string(),
                profile_name=generate_random_string(),
                instance_name=generate_random_string(),
                resource_group_name=generate_random_string(),
            ),
            "source_endpoint": get_mock_dataflow_endpoint_record(
                dataflow_endpoint_name="myendpoint1",
                instance_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                dataflow_endpoint_type="Kafka",
                group_id="mygroupid",
            ),
            "destination_endpoint": get_mock_dataflow_endpoint_record(
                dataflow_endpoint_name="myendpoint2",
                instance_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                dataflow_endpoint_type="Mqtt",
                host="aio-broker",
            ),
        },
        {
            "file_payload": get_mock_dataflow_record(
                dataflow_name=generate_random_string(),
                profile_name=generate_random_string(),
                instance_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                trans_operation={
                    "operationType": "BuiltInTransformation",
                    "builtInTransformationSettings": {
                        "serializationFormat": "Json",
                        "schemaRef": "",
                        "datasets": [],
                        "filter": [],
                        "map": [
                            {
                                "type": "PassThrough",
                                "inputs": [
                                    "*"
                                ],
                                "output": "*"
                            }
                        ]
                    }
                }
            ),
            "dataflow_profile_name": generate_random_string(),
            "source_endpoint": get_mock_dataflow_endpoint_record(
                dataflow_endpoint_name="myendpoint1",
                instance_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                dataflow_endpoint_type="Mqtt",
                host="aio-broker",
            ),
            "destination_endpoint": get_mock_dataflow_endpoint_record(
                dataflow_endpoint_name="myendpoint2",
                instance_name=generate_random_string(),
                resource_group_name=generate_random_string(),
                dataflow_endpoint_type="Mqtt",
            ),
        },
    ],
)
def test_dataflow_apply(mocked_cmd, mocked_responses: responses, mocked_get_file_config: Mock, scenario: dict):
    file_payload = scenario["file_payload"]
    dataflow_name = file_payload["name"]
    resource_id = file_payload["id"]
    instance_name = resource_id.split("/instances/")[1].split("/dataflowProfiles/")[0]
    resource_group_name = resource_id.split("/resourceGroups/")[1].split("/providers/")[0]
    dataflow_profile_name = resource_id.split("/dataflowProfiles/")[1].split("/dataflows/")[0]

    expected_payload = None
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

    source_endpoint_payload = scenario["source_endpoint"]
    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_endpoint_name=source_endpoint_payload["name"],
        ),
        json=source_endpoint_payload,
        status=200,
    )
    destination_endpoint_payload = scenario["destination_endpoint"]
    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_endpoint_name=destination_endpoint_payload["name"],
        ),
        json=destination_endpoint_payload,
        status=200,
    )
    put_response = mocked_responses.add(
        method=responses.PUT,
        url=get_dataflow_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            profile_name=dataflow_profile_name or DEFAULT_DATAFLOW_PROFILE,
            dataflow_name=dataflow_name,
        ),
        json=expected_payload,
        status=200,
    )
    create_result = apply_dataflow(
        cmd=mocked_cmd,
        profile_name=dataflow_profile_name or DEFAULT_DATAFLOW_PROFILE,
        dataflow_name=dataflow_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        config_file="config.json",
        wait_sec=0.1,
    )
    assert len(mocked_responses.calls) == 4
    assert create_result == expected_payload
    request_payload = json.loads(put_response.calls[0].request.body)
    assert request_payload["extendedLocation"] == mock_instance_record["extendedLocation"]


@pytest.mark.parametrize(
    "scenario, expected_error_type, expected_error_text",
    [
        # Invalid source endpoint type
        (
            {
                "file_payload": get_mock_dataflow_record(
                    dataflow_name=generate_random_string(),
                    profile_name=generate_random_string(),
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                ),
                "source_endpoint": get_mock_dataflow_endpoint_record(
                    dataflow_endpoint_name="myendpoint1",
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                    dataflow_endpoint_type="DataExplorer",
                ),
                "destination_endpoint": get_mock_dataflow_endpoint_record(
                    dataflow_endpoint_name="myendpoint2",
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                ),
            },
            InvalidArgumentValueError,
            "'DataExplorer' is not a valid type for source dataflow endpoint.",
        ),
        # No consumer group id for Kafka source endpoint
        (
            {
                "file_payload": get_mock_dataflow_record(
                    dataflow_name=generate_random_string(),
                    profile_name=generate_random_string(),
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                ),
                "source_endpoint": get_mock_dataflow_endpoint_record(
                    dataflow_endpoint_name="myendpoint1",
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                    dataflow_endpoint_type="Kafka",
                ),
                "destination_endpoint": get_mock_dataflow_endpoint_record(
                    dataflow_endpoint_name="myendpoint2",
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                ),
            },
            InvalidArgumentValueError,
            "'consumerGroupId' is required in kafka source dataflow endpoint configuration.",
        ),
        # No schema ref for certain destiantion endpoint type
        (
            {
                "file_payload": get_mock_dataflow_record(
                    dataflow_name=generate_random_string(),
                    profile_name=generate_random_string(),
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                ),
                "source_endpoint": get_mock_dataflow_endpoint_record(
                    dataflow_endpoint_name="myendpoint1",
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                    dataflow_endpoint_type="Mqtt",
                    group_id="mygroupid",
                ),
                "destination_endpoint": get_mock_dataflow_endpoint_record(
                    dataflow_endpoint_name="myendpoint2",
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                    dataflow_endpoint_type="LocalStorage",
                ),
            },
            InvalidArgumentValueError,
            "'schemaRef' is required for dataflow due to destination endpoint 'LocalStorage' type.",
        ),
        # At least one of source and destination endpoint must have host with "aio-broker" that is MQTT endpoint
        (
            {
                "file_payload": get_mock_dataflow_record(
                    dataflow_name=generate_random_string(),
                    profile_name=generate_random_string(),
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                ),
                "source_endpoint": get_mock_dataflow_endpoint_record(
                    dataflow_endpoint_name="myendpoint1",
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                    dataflow_endpoint_type="Mqtt",
                    group_id="mygroupid",
                ),
                "destination_endpoint": get_mock_dataflow_endpoint_record(
                    dataflow_endpoint_name="myendpoint2",
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                    dataflow_endpoint_type="Mqtt",
                ),
            },
            InvalidArgumentValueError,
            "Either source or destination endpoint must be Azure IoT Operations "
            "Local MQTT endpoint with host containing 'aio-broker'.",
        ),
        (
            {
                "file_payload": get_mock_dataflow_record(
                    dataflow_name=generate_random_string(),
                    profile_name=generate_random_string(),
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                ),
                "source_endpoint": get_mock_dataflow_endpoint_record(
                    dataflow_endpoint_name="myendpoint1",
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                    dataflow_endpoint_type="Kafka",
                    group_id="mygroupid",
                ),
                "destination_endpoint": get_mock_dataflow_endpoint_record(
                    dataflow_endpoint_name="myendpoint2",
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                    dataflow_endpoint_type="Mqtt",
                ),
            },
            InvalidArgumentValueError,
            "Either source or destination endpoint must be Azure IoT Operations "
            "Local MQTT endpoint with host containing 'aio-broker'.",
        ),
    ],
)
def test_dataflow_apply_error(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_file_config: Mock,
    scenario: dict,
    expected_error_type: Exception,
    expected_error_text: str,
):
    file_payload = scenario["file_payload"]
    dataflow_name = file_payload["name"]
    resource_id = file_payload["id"]
    instance_name = resource_id.split("/instances/")[1].split("/dataflowProfiles/")[0]
    resource_group_name = resource_id.split("/resourceGroups/")[1].split("/providers/")[0]
    dataflow_profile_name = resource_id.split("/dataflowProfiles/")[1].split("/dataflows/")[0]

    if file_payload:
        expected_file_content = json.dumps(file_payload)
    mocked_get_file_config.return_value = expected_file_content

    source_endpoint_payload = scenario.get("source_endpoint")
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
    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_endpoint_name=source_endpoint_payload["name"],
        ),
        json=source_endpoint_payload,
        status=200,
    )

    source_endpoint_type = source_endpoint_payload["properties"]["endpointType"]
    source_endpoint_group_id = source_endpoint_payload["properties"].get(
        DATAFLOW_ENDPOINT_TYPE_SETTINGS[source_endpoint_type]).get("consumerGroupId")
    if source_endpoint_type == "Mqtt" or (
        source_endpoint_type == "Kafka" and source_endpoint_group_id
    ):
        destination_operation_payload = scenario.get("destination_endpoint")
        mocked_responses.add(
            method=responses.GET,
            url=get_dataflow_endpoint_endpoint(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                dataflow_endpoint_name=destination_operation_payload["name"],
            ),
            json=destination_operation_payload,
            status=200,
        )

    with pytest.raises(expected_error_type) as e:
        apply_dataflow(
            cmd=mocked_cmd,
            profile_name=dataflow_profile_name or DEFAULT_DATAFLOW_PROFILE,
            dataflow_name=dataflow_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            config_file="config.json",
            wait_sec=0.1,
        )

    assert expected_error_text in e.value.args[0]


@pytest.mark.parametrize(
    "scenario, expected_error_type, expected_error_text",
    [
        # Invalid source endpoint type
        (
            {
                "file_payload": get_mock_dataflow_record(
                    dataflow_name=generate_random_string(),
                    profile_name=generate_random_string(),
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                ),
                "source_endpoint": get_mock_dataflow_endpoint_record(
                    dataflow_endpoint_name="myendpoint1",
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                    dataflow_endpoint_type="DataExplorer",
                ),
                "destination_endpoint": get_mock_dataflow_endpoint_record(
                    dataflow_endpoint_name="myendpoint2",
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                ),
            },
            ResourceNotFoundError,
            "Source dataflow endpoint 'myendpoint1' not found in instance 'myinstance'. "
            "Please provide a valid 'endpointRef' using --config-file.",
        ),
    ]
)
def test_dataflow_apply_resource_error(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_file_config: Mock,
    scenario: dict,
    expected_error_type: Exception,
    expected_error_text: str,
):
    file_payload = scenario["file_payload"]
    dataflow_name = file_payload["name"]
    resource_id = file_payload["id"]
    instance_name = resource_id.split("/instances/")[1].split("/dataflowProfiles/")[0]
    resource_group_name = resource_id.split("/resourceGroups/")[1].split("/providers/")[0]
    dataflow_profile_name = resource_id.split("/dataflowProfiles/")[1].split("/dataflows/")[0]

    if file_payload:
        expected_file_content = json.dumps(file_payload)
    mocked_get_file_config.return_value = expected_file_content

    source_endpoint_payload = scenario.get("source_endpoint")
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
    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_endpoint_name=source_endpoint_payload["name"],
        ),
        json={},
        status=200,
    )

    with pytest.raises(expected_error_type) as e:
        apply_dataflow(
            cmd=mocked_cmd,
            profile_name=dataflow_profile_name or DEFAULT_DATAFLOW_PROFILE,
            dataflow_name=dataflow_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            config_file="config.json",
            wait_sec=0.1,
        )
    assert expected_error_text in e.value.args[0]


def test_dataflow_delete(mocked_cmd, mocked_responses: responses):
    profile_name = generate_random_string()
    dataflow_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mocked_responses.add(
        method=responses.DELETE,
        url=get_dataflow_endpoint(
            profile_name=profile_name,
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_name=dataflow_name
        ),
        status=204,
    )
    delete_dataflow(
        cmd=mocked_cmd,
        dataflow_name=dataflow_name,
        profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=True,
        wait_sec=0.25,
    )
    assert len(mocked_responses.calls) == 1
