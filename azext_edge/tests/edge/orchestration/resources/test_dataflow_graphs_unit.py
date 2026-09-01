# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import copy
import json
from typing import Optional
from unittest.mock import Mock

import pytest
import responses

from azure.cli.core.azclierror import InvalidArgumentValueError, ValidationError
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

from azext_edge.edge.commands_dataflowgraph import (
    apply_dataflow_graph,
    delete_dataflow_graph,
    list_dataflow_graphs,
    show_dataflow_graph,
)
from .dataflow_endpoint.conftest import (
    get_dataflow_endpoint_endpoint,
    get_mock_dataflow_endpoint_record,
)
from .test_instances_unit import (
    get_instance_endpoint,
    get_mock_instance_record,
)
from .registry_endpoint.test_registry_endpoints_unit import (
    get_registry_endpoint_endpoint,
    get_mock_registry_endpoint_record,
)
from ....generators import generate_random_string
from .conftest import get_base_endpoint, get_mock_resource


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_dataflow_graph_endpoint(
    profile_name: str,
    instance_name: str,
    resource_group_name: str,
    graph_name: Optional[str] = None,
    **kwargs,
) -> str:
    resource_path = f"/instances/{instance_name}/dataflowProfiles/{profile_name}/dataflowGraphs"
    if graph_name:
        resource_path += f"/{graph_name}"
    return get_base_endpoint(resource_group_name=resource_group_name, resource_path=resource_path, **kwargs)


def get_mock_dataflow_graph_record(
    graph_name: str,
    profile_name: str,
    instance_name: str,
    resource_group_name: str,
    extra_nodes: Optional[list] = None,
) -> dict:
    nodes = [
        {
            "name": "source-node",
            "nodeType": "Source",
            "sourceSettings": {
                "endpointRef": "myendpoint1",
                "dataSources": ["test/topic"],
            },
        },
        {
            "name": "dest-node",
            "nodeType": "Destination",
            "destinationSettings": {
                "endpointRef": "myendpoint2",
                "dataDestination": "output/topic",
            },
        },
    ]
    if extra_nodes:
        nodes.extend(extra_nodes)

    properties = {
        "nodes": nodes,
        "nodeConnections": [
            {"from": {"name": "source-node"}, "to": {"name": "dest-node"}}
        ],
        "provisioningState": "Succeeded",
    }
    return get_mock_resource(
        name=graph_name,
        resource_path=(
            f"/instances/{instance_name}/dataflowProfiles/{profile_name}/dataflowGraphs/{graph_name}"
        ),
        properties=properties,
        resource_group_name=resource_group_name,
        qualified_type="microsoft.iotoperations/instances/dataflowgraphs",
        is_proxy_resource=True,
    )


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


def test_dataflow_graph_show(mocked_cmd, mocked_responses: responses):
    graph_name = generate_random_string()
    profile_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_record = get_mock_dataflow_graph_record(
        graph_name=graph_name,
        profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_graph_endpoint(
            graph_name=graph_name,
            profile_name=profile_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        ),
        json=mock_record,
        status=200,
        content_type="application/json",
    )

    result = show_dataflow_graph(
        cmd=mocked_cmd,
        dataflow_graph_name=graph_name,
        profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )

    assert result == mock_record
    assert len(mocked_responses.calls) == 1


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("records", [0, 2])
def test_dataflow_graph_list(mocked_cmd, mocked_responses: responses, records: int):
    profile_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_records = {
        "value": [
            get_mock_dataflow_graph_record(
                graph_name=generate_random_string(),
                profile_name=profile_name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
            )
            for _ in range(records)
        ]
    }
    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_graph_endpoint(
            profile_name=profile_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        ),
        json=mock_records,
        status=200,
        content_type="application/json",
    )

    result = list(
        list_dataflow_graphs(
            cmd=mocked_cmd,
            profile_name=profile_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )
    )

    assert result == mock_records["value"]
    assert len(mocked_responses.calls) == 1


# ---------------------------------------------------------------------------
# apply - success
# ---------------------------------------------------------------------------


def test_dataflow_graph_apply_invalid_json_config(
    mocked_cmd,
    mocked_get_file_config: Mock,
):
    mocked_get_file_config.return_value = "bad json {"

    with pytest.raises(InvalidArgumentValueError) as exc:
        apply_dataflow_graph(
            cmd=mocked_cmd,
            dataflow_graph_name=generate_random_string(),
            profile_name=generate_random_string(),
            instance_name=generate_random_string(),
            resource_group_name=generate_random_string(),
            config_file="config.json",
        )

    assert "--config-file" in exc.value.error_msg
    assert "config.json" in exc.value.error_msg


@pytest.mark.parametrize(
    "scenario",
    [
        # MQTT source (AIOLocalMqtt) → MQTT destination (CustomMqtt)
        {
            "source_endpoint": get_mock_dataflow_endpoint_record(
                dataflow_endpoint_name="myendpoint1",
                instance_name="myinstance",
                resource_group_name="myresourcegroup",
                dataflow_endpoint_type="AIOLocalMqtt",
                host="aio-broker",
            ),
            "destination_endpoint": get_mock_dataflow_endpoint_record(
                dataflow_endpoint_name="myendpoint2",
                instance_name="myinstance",
                resource_group_name="myresourcegroup",
                dataflow_endpoint_type="CustomMqtt",
            ),
        },
        # Kafka source (EventHub, with consumerGroupId) → MQTT destination (AIOLocalMqtt)
        {
            "source_endpoint": get_mock_dataflow_endpoint_record(
                dataflow_endpoint_name="myendpoint1",
                instance_name="myinstance",
                resource_group_name="myresourcegroup",
                dataflow_endpoint_type="EventHub",
                group_id="my-consumer-group",
            ),
            "destination_endpoint": get_mock_dataflow_endpoint_record(
                dataflow_endpoint_name="myendpoint2",
                instance_name="myinstance",
                resource_group_name="myresourcegroup",
                dataflow_endpoint_type="AIOLocalMqtt",
                host="aio-broker",
            ),
        },
        # MQTT source (EventGrid) → OpenTelemetry destination
        {
            "source_endpoint": get_mock_dataflow_endpoint_record(
                dataflow_endpoint_name="myendpoint1",
                instance_name="myinstance",
                resource_group_name="myresourcegroup",
                dataflow_endpoint_type="EventGrid",
                host="aio-broker",
            ),
            "destination_endpoint": get_mock_dataflow_endpoint_record(
                dataflow_endpoint_name="myendpoint2",
                instance_name="myinstance",
                resource_group_name="myresourcegroup",
                dataflow_endpoint_type="OpenTelemetry",
            ),
        },
        # MQTT source (AIOLocalMqtt) → Kafka destination (CustomKafka)
        {
            "source_endpoint": get_mock_dataflow_endpoint_record(
                dataflow_endpoint_name="myendpoint1",
                instance_name="myinstance",
                resource_group_name="myresourcegroup",
                dataflow_endpoint_type="AIOLocalMqtt",
                host="aio-broker",
            ),
            "destination_endpoint": get_mock_dataflow_endpoint_record(
                dataflow_endpoint_name="myendpoint2",
                instance_name="myinstance",
                resource_group_name="myresourcegroup",
                dataflow_endpoint_type="CustomKafka",
            ),
        },
        # Legacy generic Mqtt source → legacy generic Mqtt destination
        {
            "source_endpoint": get_mock_dataflow_endpoint_record(
                dataflow_endpoint_name="myendpoint1",
                instance_name="myinstance",
                resource_group_name="myresourcegroup",
                dataflow_endpoint_type="Mqtt",
                host="aio-broker",
            ),
            "destination_endpoint": get_mock_dataflow_endpoint_record(
                dataflow_endpoint_name="myendpoint2",
                instance_name="myinstance",
                resource_group_name="myresourcegroup",
                dataflow_endpoint_type="Mqtt",
            ),
        },
    ],
)
def test_dataflow_graph_apply(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_file_config: Mock,
    scenario: dict,
):

    graph_name = generate_random_string()
    profile_name = generate_random_string()
    instance_name = "myinstance"
    resource_group_name = "myresourcegroup"

    file_payload = get_mock_dataflow_graph_record(
        graph_name=graph_name,
        profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )
    mocked_get_file_config.return_value = json.dumps(file_payload)

    mock_instance_record = get_mock_instance_record(
        name=instance_name, resource_group_name=resource_group_name
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_instance_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
        ),
        json=mock_instance_record,
        status=200,
    )

    source_endpoint = scenario["source_endpoint"]
    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_endpoint_name=source_endpoint["name"],
        ),
        json=source_endpoint,
        status=200,
    )

    dest_endpoint = scenario["destination_endpoint"]
    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_endpoint_name=dest_endpoint["name"],
        ),
        json=dest_endpoint,
        status=200,
    )

    put_response = mocked_responses.add(
        method=responses.PUT,
        url=get_dataflow_graph_endpoint(
            profile_name=profile_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            graph_name=graph_name,
        ),
        json=file_payload,
        status=200,
    )

    result = apply_dataflow_graph(
        cmd=mocked_cmd,
        dataflow_graph_name=graph_name,
        profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        config_file="config.json",
        wait_sec=0.1,
    )

    assert len(mocked_responses.calls) == 4
    assert result == file_payload
    request_payload = json.loads(put_response.calls[0].request.body)
    assert request_payload["extendedLocation"] == mock_instance_record["extendedLocation"]


# ---------------------------------------------------------------------------
# apply - structural validation errors (no endpoint mocks needed)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "graph_properties, expected_error_text",
    [
        # Empty nodes list
        (
            {"nodes": [], "nodeConnections": []},
            "'nodes' is required and must contain at least one node",
        ),
        # Missing nodes key
        (
            {"nodeConnections": []},
            "'nodes' is required and must contain at least one node",
        ),
        # Node missing name
        (
            {
                "nodes": [{"nodeType": "Source", "sourceSettings": {"endpointRef": "ep1", "dataSources": ["t"]}}],
                "nodeConnections": [],
            },
            "is missing a 'name'",
        ),
        # Node missing nodeType
        (
            {
                "nodes": [{"name": "my-node"}],
                "nodeConnections": [],
            },
            "is missing a 'nodeType'",
        ),
        # Node with invalid nodeType
        (
            {
                "nodes": [{"name": "my-node", "nodeType": "Relay"}],
                "nodeConnections": [],
            },
            "has invalid nodeType 'Relay'",
        ),
        # Duplicate node name
        (
            {
                "nodes": [
                    {"name": "dup-node", "nodeType": "Source",
                     "sourceSettings": {"endpointRef": "ep1", "dataSources": ["t"]}},
                    {"name": "dup-node", "nodeType": "Destination",
                     "destinationSettings": {"endpointRef": "ep2", "dataDestination": "t"}},
                ],
                "nodeConnections": [],
            },
            "Duplicate node name 'dup-node'",
        ),
        # No Source node
        (
            {
                "nodes": [
                    {
                        "name": "dest-node",
                        "nodeType": "Destination",
                        "destinationSettings": {"endpointRef": "ep2", "dataDestination": "t"},
                    }
                ],
                "nodeConnections": [],
            },
            "must contain at least one node with nodeType 'Source'",
        ),
        # No Destination node
        (
            {
                "nodes": [
                    {
                        "name": "src-node",
                        "nodeType": "Source",
                        "sourceSettings": {"endpointRef": "ep1", "dataSources": ["t"]},
                    }
                ],
                "nodeConnections": [],
            },
            "must contain at least one node with nodeType 'Destination'",
        ),
        # nodeConnection is a self-loop (from == to)
        (
            {
                "nodes": [
                    {"name": "src", "nodeType": "Source",
                     "sourceSettings": {"endpointRef": "ep1", "dataSources": ["t"]}},
                    {"name": "dst", "nodeType": "Destination",
                     "destinationSettings": {"endpointRef": "ep2", "dataDestination": "t"}},
                ],
                "nodeConnections": [{"from": {"name": "src"}, "to": {"name": "src"}}],
            },
            "is a self-loop",
        ),
        # nodeConnection references unknown 'from' node
        (
            {
                "nodes": [
                    {"name": "src", "nodeType": "Source",
                     "sourceSettings": {"endpointRef": "ep1", "dataSources": ["t"]}},
                    {"name": "dst", "nodeType": "Destination",
                     "destinationSettings": {"endpointRef": "ep2", "dataDestination": "t"}},
                ],
                "nodeConnections": [{"from": {"name": "ghost"}, "to": {"name": "dst"}}],
            },
            "references unknown 'from' node 'ghost'",
        ),
        # nodeConnection references unknown 'to' node
        (
            {
                "nodes": [
                    {"name": "src", "nodeType": "Source",
                     "sourceSettings": {"endpointRef": "ep1", "dataSources": ["t"]}},
                    {"name": "dst", "nodeType": "Destination",
                     "destinationSettings": {"endpointRef": "ep2", "dataDestination": "t"}},
                ],
                "nodeConnections": [{"from": {"name": "src"}, "to": {"name": "ghost"}}],
            },
            "references unknown 'to' node 'ghost'",
        ),
        # nodeConnections is not a list (null)
        (
            {
                "nodes": [
                    {"name": "src", "nodeType": "Source",
                     "sourceSettings": {"endpointRef": "ep1", "dataSources": ["t"]}},
                    {"name": "dst", "nodeType": "Destination",
                     "destinationSettings": {"endpointRef": "ep2", "dataDestination": "t"}},
                ],
                "nodeConnections": None,
            },
            "'nodeConnections' is required and must contain at least one connection",
        ),
        # nodeConnection entry is not a dict
        (
            {
                "nodes": [
                    {"name": "src", "nodeType": "Source",
                     "sourceSettings": {"endpointRef": "ep1", "dataSources": ["t"]}},
                    {"name": "dst", "nodeType": "Destination",
                     "destinationSettings": {"endpointRef": "ep2", "dataDestination": "t"}},
                ],
                "nodeConnections": ["not-a-dict"],
            },
            "nodeConnection at index 0 must be an object",
        ),
        # Destination node used as 'from' (source of a connection)
        (
            {
                "nodes": [
                    {"name": "src", "nodeType": "Source",
                     "sourceSettings": {"endpointRef": "ep1", "dataSources": ["t"]}},
                    {"name": "dst", "nodeType": "Destination",
                     "destinationSettings": {"endpointRef": "ep2", "dataDestination": "t"}},
                ],
                "nodeConnections": [{"from": {"name": "dst"}, "to": {"name": "src"}}],
            },
            "Destination nodes are sinks and cannot be the source of a connection",
        ),
        # Source node used as 'to' (destination of a connection)
        (
            {
                "nodes": [
                    {"name": "src", "nodeType": "Source",
                     "sourceSettings": {"endpointRef": "ep1", "dataSources": ["t"]}},
                    {"name": "mid", "nodeType": "Graph",
                     "graphSettings": {"registryEndpointRef": "reg", "artifact": "myartifact:1.0"}},
                    {"name": "dst", "nodeType": "Destination",
                     "destinationSettings": {"endpointRef": "ep2", "dataDestination": "t"}},
                ],
                "nodeConnections": [{"from": {"name": "mid"}, "to": {"name": "src"}}],
            },
            "Source nodes are producers and cannot be the destination of a connection",
        ),
    ],
)
def test_dataflow_graph_apply_structural_error(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_file_config: Mock,
    graph_properties: dict,
    expected_error_text: str,
):
    graph_name = generate_random_string()
    profile_name = generate_random_string()
    instance_name = "myinstance"
    resource_group_name = "myresourcegroup"

    # Wrap in ARM resource so get_file_config extracts properties
    file_payload = {"properties": graph_properties}
    mocked_get_file_config.return_value = json.dumps(file_payload)

    with pytest.raises(InvalidArgumentValueError) as exc:
        apply_dataflow_graph(
            cmd=mocked_cmd,
            dataflow_graph_name=graph_name,
            profile_name=profile_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            config_file="config.json",
            wait_sec=0.1,
        )

    assert expected_error_text in exc.value.args[0]


# ---------------------------------------------------------------------------
# apply - endpoint validation errors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scenario, expected_error_text",
    [
        # Source missing endpointRef
        (
            {
                "graph_properties": {
                    "nodes": [
                        {
                            "name": "src",
                            "nodeType": "Source",
                            "sourceSettings": {"dataSources": ["t"]},  # no endpointRef
                        },
                        {
                            "name": "dst",
                            "nodeType": "Destination",
                            "destinationSettings": {"endpointRef": "myendpoint2", "dataDestination": "t"},
                        },
                    ],
                    "nodeConnections": [{"from": {"name": "src"}, "to": {"name": "dst"}}],
                },
                "source_endpoint": None,
                "destination_endpoint": None,
            },
            "is missing 'sourceSettings.endpointRef'",
        ),
        # Source endpoint not found
        (
            {
                "source_endpoint": get_mock_dataflow_endpoint_record(
                    dataflow_endpoint_name="myendpoint1",
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                    dataflow_endpoint_type="AIOLocalMqtt",
                    host="aio-broker",
                ),
                "destination_endpoint": None,
                "source_endpoint_status": 404,
                "expected_error_type": ResourceNotFoundError,
            },
            "not found in instance 'myinstance'",
        ),
        # Source endpoint is unsupported type (DataExplorer)
        (
            {
                "source_endpoint": get_mock_dataflow_endpoint_record(
                    dataflow_endpoint_name="myendpoint1",
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                    dataflow_endpoint_type="DataExplorer",
                ),
                "destination_endpoint": None,
            },
            "not supported in data flow graphs",
        ),
        # Source endpoint is unsupported type (DataLakeStorage)
        (
            {
                "source_endpoint": get_mock_dataflow_endpoint_record(
                    dataflow_endpoint_name="myendpoint1",
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                    dataflow_endpoint_type="DataLakeStorage",
                ),
                "destination_endpoint": None,
            },
            "not supported in data flow graphs",
        ),
        # Source endpoint is OpenTelemetry (destination-only)
        (
            {
                "source_endpoint": get_mock_dataflow_endpoint_record(
                    dataflow_endpoint_name="myendpoint1",
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                    dataflow_endpoint_type="OpenTelemetry",
                ),
                "destination_endpoint": None,
            },
            "destination-only and cannot be used as a source",
        ),
        # Source endpoint is FabricRealTime (destination-only)
        (
            {
                "source_endpoint": get_mock_dataflow_endpoint_record(
                    dataflow_endpoint_name="myendpoint1",
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                    dataflow_endpoint_type="FabricRealTime",
                ),
                "destination_endpoint": None,
            },
            "destination-only and cannot be used as a source",
        ),
        # Kafka source missing consumerGroupId (EventHub)
        (
            {
                "source_endpoint": get_mock_dataflow_endpoint_record(
                    dataflow_endpoint_name="myendpoint1",
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                    dataflow_endpoint_type="EventHub",
                    # no group_id → consumerGroupId=""
                ),
                "destination_endpoint": None,
            },
            "A consumer group ID is required for Kafka source endpoints",
        ),
        # Kafka source missing consumerGroupId (CustomKafka)
        (
            {
                "source_endpoint": get_mock_dataflow_endpoint_record(
                    dataflow_endpoint_name="myendpoint1",
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                    dataflow_endpoint_type="CustomKafka",
                    # no group_id → consumerGroupId=""
                ),
                "destination_endpoint": None,
            },
            "A consumer group ID is required for Kafka source endpoints",
        ),
        # Destination missing endpointRef
        (
            {
                "graph_properties": {
                    "nodes": [
                        {
                            "name": "src",
                            "nodeType": "Source",
                            "sourceSettings": {"endpointRef": "myendpoint1", "dataSources": ["t"]},
                        },
                        {
                            "name": "dst",
                            "nodeType": "Destination",
                            "destinationSettings": {"dataDestination": "t"},  # no endpointRef
                        },
                    ],
                    "nodeConnections": [{"from": {"name": "src"}, "to": {"name": "dst"}}],
                },
                "source_endpoint": get_mock_dataflow_endpoint_record(
                    dataflow_endpoint_name="myendpoint1",
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                    dataflow_endpoint_type="AIOLocalMqtt",
                    host="aio-broker",
                ),
                "destination_endpoint": None,
            },
            "is missing 'destinationSettings.endpointRef'",
        ),
        # Destination endpoint is unsupported type (FabricOneLake)
        (
            {
                "source_endpoint": get_mock_dataflow_endpoint_record(
                    dataflow_endpoint_name="myendpoint1",
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                    dataflow_endpoint_type="AIOLocalMqtt",
                    host="aio-broker",
                ),
                "destination_endpoint": get_mock_dataflow_endpoint_record(
                    dataflow_endpoint_name="myendpoint2",
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                    dataflow_endpoint_type="FabricOneLake",
                ),
            },
            "not supported in data flow graphs",
        ),
        # Destination endpoint is unsupported type (LocalStorage)
        (
            {
                "source_endpoint": get_mock_dataflow_endpoint_record(
                    dataflow_endpoint_name="myendpoint1",
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                    dataflow_endpoint_type="AIOLocalMqtt",
                    host="aio-broker",
                ),
                "destination_endpoint": get_mock_dataflow_endpoint_record(
                    dataflow_endpoint_name="myendpoint2",
                    instance_name="myinstance",
                    resource_group_name="myresourcegroup",
                    dataflow_endpoint_type="LocalStorage",
                ),
            },
            "not supported in data flow graphs",
        ),
    ],
)
def test_dataflow_graph_apply_endpoint_error(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_file_config: Mock,
    scenario: dict,
    expected_error_text: str,
):
    graph_name = generate_random_string()
    profile_name = generate_random_string()
    instance_name = "myinstance"
    resource_group_name = "myresourcegroup"

    # Build graph properties — use scenario override or default two-node config
    graph_properties = scenario.get("graph_properties") or {
        "nodes": [
            {
                "name": "source-node",
                "nodeType": "Source",
                "sourceSettings": {"endpointRef": "myendpoint1", "dataSources": ["test/topic"]},
            },
            {
                "name": "dest-node",
                "nodeType": "Destination",
                "destinationSettings": {"endpointRef": "myendpoint2", "dataDestination": "output/topic"},
            },
        ],
        "nodeConnections": [{"from": {"name": "source-node"}, "to": {"name": "dest-node"}}],
    }
    file_payload = {"properties": graph_properties}
    mocked_get_file_config.return_value = json.dumps(file_payload)

    source_endpoint = scenario.get("source_endpoint")
    if source_endpoint:
        source_status = scenario.get("source_endpoint_status", 200)
        mocked_responses.add(
            method=responses.GET,
            url=get_dataflow_endpoint_endpoint(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                dataflow_endpoint_name=source_endpoint["name"],
            ),
            json=source_endpoint if source_status == 200 else {"error": {"code": "NotFound"}},
            status=source_status,
        )

    dest_endpoint = scenario.get("destination_endpoint")
    if dest_endpoint:
        mocked_responses.add(
            method=responses.GET,
            url=get_dataflow_endpoint_endpoint(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                dataflow_endpoint_name=dest_endpoint["name"],
            ),
            json=dest_endpoint,
            status=200,
        )

    expected_error_type = scenario.get("expected_error_type", InvalidArgumentValueError)
    with pytest.raises(expected_error_type) as exc:
        apply_dataflow_graph(
            cmd=mocked_cmd,
            dataflow_graph_name=graph_name,
            profile_name=profile_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            config_file="config.json",
            wait_sec=0.1,
        )

    assert expected_error_text in exc.value.args[0]


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("confirm_yes", [True, False, None])
def test_dataflow_graph_delete(mocked_cmd, mocked_responses: responses, confirm_yes, mocker):
    graph_name = generate_random_string()
    profile_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    if not confirm_yes:
        mocker.patch(
            "azext_edge.edge.providers.orchestration.resources.dataflow_graphs.should_continue_prompt",
            return_value=False,
        )
    else:
        mocked_responses.add(
            method=responses.DELETE,
            url=get_dataflow_graph_endpoint(
                graph_name=graph_name,
                profile_name=profile_name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
            ),
            status=204,
        )

    delete_dataflow_graph(
        cmd=mocked_cmd,
        dataflow_graph_name=graph_name,
        profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=confirm_yes,
        wait_sec=0.1,
    )

    expected_calls = 0 if not confirm_yes else 1
    assert len(mocked_responses.calls) == expected_calls


# ---------------------------------------------------------------------------
# apply - graph node validation errors (artifact format + registryEndpointRef)
# ---------------------------------------------------------------------------

_GRAPH_NODE_BASE_PROPERTIES = {
    "nodes": [
        {
            "name": "src",
            "nodeType": "Source",
            "sourceSettings": {"endpointRef": "myendpoint1", "dataSources": ["t"]},
        },
        {
            "name": "dst",
            "nodeType": "Destination",
            "destinationSettings": {"endpointRef": "myendpoint2", "dataDestination": "t"},
        },
        {
            "name": "graph-node",
            "nodeType": "Graph",
            "graphSettings": {
                "registryEndpointRef": "myregistry",
                "artifact": "myartifact:1.0",
            },
        },
    ],
    "nodeConnections": [
        {"from": {"name": "src"}, "to": {"name": "graph-node"}},
        {"from": {"name": "graph-node"}, "to": {"name": "dst"}},
    ],
}


@pytest.mark.parametrize(
    "graph_settings_override, expected_error_text",
    [
        # Missing registryEndpointRef
        (
            {"artifact": "myartifact:1.0"},
            "is missing 'graphSettings.registryEndpointRef'",
        ),
        # Missing artifact
        (
            {"registryEndpointRef": "myregistry"},
            "is missing 'graphSettings.artifact'",
        ),
        # artifact with no colon
        (
            {"registryEndpointRef": "myregistry", "artifact": "myartifact"},
            "Expected format: '<artifact-name>:<version>'",
        ),
        # artifact colon at start
        (
            {"registryEndpointRef": "myregistry", "artifact": ":1.0"},
            "Expected format: '<artifact-name>:<version>'",
        ),
        # artifact colon at end
        (
            {"registryEndpointRef": "myregistry", "artifact": "myartifact:"},
            "Expected format: '<artifact-name>:<version>'",
        ),
    ],
)
def test_dataflow_graph_apply_graph_node_error(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_file_config,
    graph_settings_override: dict,
    expected_error_text: str,
):

    graph_name = generate_random_string()
    profile_name = generate_random_string()
    instance_name = "myinstance"
    resource_group_name = "myresourcegroup"

    graph_properties = copy.deepcopy(_GRAPH_NODE_BASE_PROPERTIES)
    for node in graph_properties["nodes"]:
        if node["nodeType"] == "Graph":
            node["graphSettings"] = graph_settings_override

    file_payload = {"properties": graph_properties}
    mocked_get_file_config.return_value = json.dumps(file_payload)

    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_endpoint_name="myendpoint1",
        ),
        json=get_mock_dataflow_endpoint_record(
            dataflow_endpoint_name="myendpoint1",
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            dataflow_endpoint_type="AIOLocalMqtt",
            host="aio-broker",
        ),
        status=200,
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_endpoint_name="myendpoint2",
        ),
        json=get_mock_dataflow_endpoint_record(
            dataflow_endpoint_name="myendpoint2",
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            dataflow_endpoint_type="CustomMqtt",
        ),
        status=200,
    )

    # If registryEndpointRef is present, the code fetches it before validating artifact format
    if "registryEndpointRef" in graph_settings_override:
        mocked_responses.add(
            method=responses.GET,
            url=get_registry_endpoint_endpoint(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                registry_endpoint_name=graph_settings_override["registryEndpointRef"],
            ),
            json=get_mock_registry_endpoint_record(
                registry_endpoint_name=graph_settings_override["registryEndpointRef"],
                instance_name=instance_name,
                resource_group_name=resource_group_name,
            ),
            status=200,
        )

    with pytest.raises(InvalidArgumentValueError) as exc:
        apply_dataflow_graph(
            cmd=mocked_cmd,
            dataflow_graph_name=graph_name,
            profile_name=profile_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            config_file="config.json",
            wait_sec=0.1,
        )

    assert expected_error_text in exc.value.args[0]


def test_dataflow_graph_apply_registry_endpoint_not_found(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_file_config,
):

    graph_name = generate_random_string()
    profile_name = generate_random_string()
    instance_name = "myinstance"
    resource_group_name = "myresourcegroup"

    graph_properties = copy.deepcopy(_GRAPH_NODE_BASE_PROPERTIES)
    file_payload = {"properties": graph_properties}
    mocked_get_file_config.return_value = json.dumps(file_payload)

    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_endpoint_name="myendpoint1",
        ),
        json=get_mock_dataflow_endpoint_record(
            dataflow_endpoint_name="myendpoint1",
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            dataflow_endpoint_type="AIOLocalMqtt",
            host="aio-broker",
        ),
        status=200,
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_endpoint_name="myendpoint2",
        ),
        json=get_mock_dataflow_endpoint_record(
            dataflow_endpoint_name="myendpoint2",
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            dataflow_endpoint_type="CustomMqtt",
        ),
        status=200,
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_registry_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            registry_endpoint_name="myregistry",
        ),
        json={"error": {"code": "ResourceNotFound", "message": "not found"}},
        status=404,
    )

    with pytest.raises(ResourceNotFoundError) as exc:
        apply_dataflow_graph(
            cmd=mocked_cmd,
            dataflow_graph_name=graph_name,
            profile_name=profile_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            config_file="config.json",
            wait_sec=0.1,
        )

    assert "myregistry" in exc.value.args[0]
    assert "not found in instance 'myinstance'" in exc.value.args[0]


# ---------------------------------------------------------------------------
# apply - artifact required configuration parameter validation
# ---------------------------------------------------------------------------

_MOCK_ARTIFACT_YAML_WITH_REQUIRED_PARAMS = (
    "moduleConfigurations:\n"
    "  - name: mymodule\n"
    "    parameters:\n"
    "      rules:\n"
    "        name: rules\n"
    "        required: true\n"
    "        description: Required rules config\n"
    "      optionalParam:\n"
    "        name: optionalParam\n"
    "        required: false\n"
    "        description: Optional param\n"
)

_MOCK_ARTIFACT_YAML_NO_REQUIRED_PARAMS = (
    "moduleConfigurations:\n"
    "  - name: mymodule\n"
    "    parameters:\n"
    "      optionalParam:\n"
    "        name: optionalParam\n"
    "        required: false\n"
    "        description: Optional param\n"
)


def _mock_oci_client(mocker, yaml_content: str):
    """Patch get_oci_client to return a mock that serves the given YAML content."""
    mock_artifact_info = Mock()
    mock_artifact_info.content = yaml_content.encode("utf-8")
    mock_oci = Mock()
    mock_oci.fetch_first_layer.return_value = mock_artifact_info
    mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.dataflow_graphs.get_oci_client",
        return_value=mock_oci,
    )
    return mock_oci


def _setup_graph_node_apply_mocks(mocked_responses, instance_name, resource_group_name, registry_endpoint_name):
    """Add HTTP mocks for the two dataflow endpoints and the registry endpoint used in Graph node tests."""
    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_endpoint_name="myendpoint1",
        ),
        json=get_mock_dataflow_endpoint_record(
            dataflow_endpoint_name="myendpoint1",
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            dataflow_endpoint_type="AIOLocalMqtt",
            host="aio-broker",
        ),
        status=200,
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_endpoint_name="myendpoint2",
        ),
        json=get_mock_dataflow_endpoint_record(
            dataflow_endpoint_name="myendpoint2",
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            dataflow_endpoint_type="CustomMqtt",
        ),
        status=200,
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_registry_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            registry_endpoint_name=registry_endpoint_name,
        ),
        json=get_mock_registry_endpoint_record(
            registry_endpoint_name=registry_endpoint_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            host="myregistry.azurecr.io",
        ),
        status=200,
    )


@pytest.mark.parametrize(
    "configuration, expected_error_text",
    [
        # No configuration field at all — required param 'rules' is missing
        (
            None,
            "requires configuration parameter(s) 'rules'",
        ),
        # Empty configuration list — required param 'rules' is missing
        (
            [],
            "requires configuration parameter(s) 'rules'",
        ),
        # Wrong key provided — required param 'rules' is still missing
        (
            [{"key": "optionalParam", "value": "something"}],
            "requires configuration parameter(s) 'rules'",
        ),
        # Key present but value is None — should not count as provided
        (
            [{"key": "rules", "value": None}],
            "requires configuration parameter(s) 'rules'",
        ),
        # Key present but value is empty string — should not count as provided
        (
            [{"key": "rules", "value": ""}],
            "requires configuration parameter(s) 'rules'",
        ),
        # Key present but value is whitespace only — should not count as provided
        (
            [{"key": "rules", "value": "   "}],
            "requires configuration parameter(s) 'rules'",
        ),
        # Entry has no value field at all — should not count as provided
        (
            [{"key": "rules"}],
            "requires configuration parameter(s) 'rules'",
        ),
    ],
)
def test_dataflow_graph_apply_missing_required_config(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_file_config,
    mocker,
    configuration,
    expected_error_text: str,
):

    graph_name = generate_random_string()
    profile_name = generate_random_string()
    instance_name = "myinstance"
    resource_group_name = "myresourcegroup"

    graph_properties = copy.deepcopy(_GRAPH_NODE_BASE_PROPERTIES)
    for node in graph_properties["nodes"]:
        if node["nodeType"] == "Graph":
            if configuration is not None:
                node["graphSettings"]["configuration"] = configuration
            else:
                node["graphSettings"].pop("configuration", None)

    file_payload = {"properties": graph_properties}
    mocked_get_file_config.return_value = json.dumps(file_payload)

    _setup_graph_node_apply_mocks(mocked_responses, instance_name, resource_group_name, "myregistry")
    _mock_oci_client(mocker, _MOCK_ARTIFACT_YAML_WITH_REQUIRED_PARAMS)

    with pytest.raises(InvalidArgumentValueError) as exc:
        apply_dataflow_graph(
            cmd=mocked_cmd,
            dataflow_graph_name=graph_name,
            profile_name=profile_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            config_file="config.json",
            wait_sec=0.1,
        )

    assert expected_error_text in exc.value.args[0]
    assert "myartifact:1.0" in exc.value.args[0]
    assert "Graph node" in exc.value.args[0]


def test_dataflow_graph_apply_with_graph_node_all_required_config_provided(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_file_config,
    mocker,
):
    """Graph node apply succeeds when all required configuration parameters are provided."""

    graph_name = generate_random_string()
    profile_name = generate_random_string()
    instance_name = "myinstance"
    resource_group_name = "myresourcegroup"

    graph_properties = copy.deepcopy(_GRAPH_NODE_BASE_PROPERTIES)
    for node in graph_properties["nodes"]:
        if node["nodeType"] == "Graph":
            node["graphSettings"]["configuration"] = [{"key": "rules", "value": "some-rules"}]

    file_payload = {"properties": graph_properties}
    mocked_get_file_config.return_value = json.dumps(file_payload)

    mock_instance_record = get_mock_instance_record(
        name=instance_name, resource_group_name=resource_group_name
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_instance_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
        ),
        json=mock_instance_record,
        status=200,
    )
    _setup_graph_node_apply_mocks(mocked_responses, instance_name, resource_group_name, "myregistry")
    _mock_oci_client(mocker, _MOCK_ARTIFACT_YAML_WITH_REQUIRED_PARAMS)

    mocked_responses.add(
        method=responses.PUT,
        url=get_dataflow_graph_endpoint(
            profile_name=profile_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            graph_name=graph_name,
        ),
        json=file_payload,
        status=200,
    )

    result = apply_dataflow_graph(
        cmd=mocked_cmd,
        dataflow_graph_name=graph_name,
        profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        config_file="config.json",
        wait_sec=0.1,
    )

    assert result == file_payload


@pytest.mark.parametrize(
    "fetch_side_effect",
    [
        ValidationError("registry unreachable"),
        HttpResponseError(message="connection error"),
        ConnectionError("network timeout"),
        Exception("unexpected error"),
    ],
    ids=["ValidationError", "HttpResponseError", "ConnectionError", "Exception"],
)
def test_dataflow_graph_apply_with_graph_node_oci_fetch_failure(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_file_config,
    mocker,
    fetch_side_effect,
):
    """Apply succeeds (skips config validation) when OCI artifact fetch raises any exception."""

    graph_name = generate_random_string()
    profile_name = generate_random_string()
    instance_name = "myinstance"
    resource_group_name = "myresourcegroup"

    graph_properties = copy.deepcopy(_GRAPH_NODE_BASE_PROPERTIES)
    # No configuration — but fetch will fail so validation is skipped entirely
    file_payload = {"properties": graph_properties}
    mocked_get_file_config.return_value = json.dumps(file_payload)

    mock_instance_record = get_mock_instance_record(
        name=instance_name, resource_group_name=resource_group_name
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_instance_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
        ),
        json=mock_instance_record,
        status=200,
    )
    _setup_graph_node_apply_mocks(mocked_responses, instance_name, resource_group_name, "myregistry")

    # Simulate OCI fetch failure — apply should proceed without error
    mock_oci = mocker.MagicMock()
    mock_oci.fetch_first_layer.side_effect = fetch_side_effect
    mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.dataflow_graphs.get_oci_client",
        return_value=mock_oci,
    )

    mocked_responses.add(
        method=responses.PUT,
        url=get_dataflow_graph_endpoint(
            profile_name=profile_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            graph_name=graph_name,
        ),
        json=file_payload,
        status=200,
    )

    result = apply_dataflow_graph(
        cmd=mocked_cmd,
        dataflow_graph_name=graph_name,
        profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        config_file="config.json",
        wait_sec=0.1,
    )

    assert result == file_payload


def test_dataflow_graph_apply_with_graph_node_no_required_params(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_file_config,
    mocker,
):
    """Graph node apply succeeds when the artifact has no required parameters (empty config is fine)."""

    graph_name = generate_random_string()
    profile_name = generate_random_string()
    instance_name = "myinstance"
    resource_group_name = "myresourcegroup"

    graph_properties = copy.deepcopy(_GRAPH_NODE_BASE_PROPERTIES)
    # No configuration provided in graph node — but artifact has no required params

    file_payload = {"properties": graph_properties}
    mocked_get_file_config.return_value = json.dumps(file_payload)

    mock_instance_record = get_mock_instance_record(
        name=instance_name, resource_group_name=resource_group_name
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_instance_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
        ),
        json=mock_instance_record,
        status=200,
    )
    _setup_graph_node_apply_mocks(mocked_responses, instance_name, resource_group_name, "myregistry")
    _mock_oci_client(mocker, _MOCK_ARTIFACT_YAML_NO_REQUIRED_PARAMS)

    mocked_responses.add(
        method=responses.PUT,
        url=get_dataflow_graph_endpoint(
            profile_name=profile_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            graph_name=graph_name,
        ),
        json=file_payload,
        status=200,
    )

    result = apply_dataflow_graph(
        cmd=mocked_cmd,
        dataflow_graph_name=graph_name,
        profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        config_file="config.json",
        wait_sec=0.1,
    )

    assert result == file_payload


@pytest.mark.parametrize(
    "registry_endpoint_ref_value",
    [
        "   ",
        "\t",
        " \n ",
    ],
    ids=["spaces", "tab", "newlines"],
)
def test_dataflow_graph_apply_graph_node_whitespace_registry_endpoint_ref(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_file_config,
    registry_endpoint_ref_value: str,
):
    """Graph node apply raises an error when registryEndpointRef is whitespace-only."""

    graph_name = generate_random_string()
    profile_name = generate_random_string()
    instance_name = "myinstance"
    resource_group_name = "myresourcegroup"

    graph_properties = copy.deepcopy(_GRAPH_NODE_BASE_PROPERTIES)
    for node in graph_properties["nodes"]:
        if node["nodeType"] == "Graph":
            node["graphSettings"]["registryEndpointRef"] = registry_endpoint_ref_value

    file_payload = {"properties": graph_properties}
    mocked_get_file_config.return_value = json.dumps(file_payload)

    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_endpoint_name="myendpoint1",
        ),
        json=get_mock_dataflow_endpoint_record(
            dataflow_endpoint_name="myendpoint1",
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            dataflow_endpoint_type="AIOLocalMqtt",
            host="aio-broker",
        ),
        status=200,
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_endpoint_name="myendpoint2",
        ),
        json=get_mock_dataflow_endpoint_record(
            dataflow_endpoint_name="myendpoint2",
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            dataflow_endpoint_type="CustomMqtt",
        ),
        status=200,
    )

    with pytest.raises(InvalidArgumentValueError) as exc:
        apply_dataflow_graph(
            cmd=mocked_cmd,
            dataflow_graph_name=graph_name,
            profile_name=profile_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            config_file="config.json",
            wait_sec=0.1,
        )

    assert "is missing 'graphSettings.registryEndpointRef'" in exc.value.args[0]


def test_dataflow_graph_apply_graph_node_registry_host_trailing_slash(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_file_config,
    mocker,
):
    """Graph node image_ref is built correctly when registry host has a trailing slash."""

    graph_name = generate_random_string()
    profile_name = generate_random_string()
    instance_name = "myinstance"
    resource_group_name = "myresourcegroup"

    graph_properties = copy.deepcopy(_GRAPH_NODE_BASE_PROPERTIES)
    file_payload = {"properties": graph_properties}
    mocked_get_file_config.return_value = json.dumps(file_payload)

    mock_instance_record = get_mock_instance_record(
        name=instance_name, resource_group_name=resource_group_name
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_instance_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
        ),
        json=mock_instance_record,
        status=200,
    )

    # Registry host has a trailing slash — image_ref must not contain double slash
    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_endpoint_name="myendpoint1",
        ),
        json=get_mock_dataflow_endpoint_record(
            dataflow_endpoint_name="myendpoint1",
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            dataflow_endpoint_type="AIOLocalMqtt",
            host="aio-broker",
        ),
        status=200,
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_dataflow_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_endpoint_name="myendpoint2",
        ),
        json=get_mock_dataflow_endpoint_record(
            dataflow_endpoint_name="myendpoint2",
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            dataflow_endpoint_type="CustomMqtt",
        ),
        status=200,
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_registry_endpoint_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            registry_endpoint_name="myregistry",
        ),
        json=get_mock_registry_endpoint_record(
            registry_endpoint_name="myregistry",
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            host="myregistry.azurecr.io/",  # trailing slash
        ),
        status=200,
    )
    _mock_oci_client(mocker, _MOCK_ARTIFACT_YAML_NO_REQUIRED_PARAMS)

    mocked_responses.add(
        method=responses.PUT,
        url=get_dataflow_graph_endpoint(
            profile_name=profile_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            graph_name=graph_name,
        ),
        json=file_payload,
        status=200,
    )

    result = apply_dataflow_graph(
        cmd=mocked_cmd,
        dataflow_graph_name=graph_name,
        profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        config_file="config.json",
        wait_sec=0.1,
    )

    assert result == file_payload
    # The apply succeeded — the trailing slash was stripped correctly (no double slash in result)
    assert "//" not in str(result)


def test_dataflow_graph_apply_graph_node_non_utf8_artifact(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_file_config,
    mocker,
):
    """Graph node apply skips config validation when artifact content is not valid UTF-8."""

    graph_name = generate_random_string()
    profile_name = generate_random_string()
    instance_name = "myinstance"
    resource_group_name = "myresourcegroup"

    graph_properties = copy.deepcopy(_GRAPH_NODE_BASE_PROPERTIES)
    file_payload = {"properties": graph_properties}
    mocked_get_file_config.return_value = json.dumps(file_payload)

    mock_instance_record = get_mock_instance_record(
        name=instance_name, resource_group_name=resource_group_name
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_instance_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
        ),
        json=mock_instance_record,
        status=200,
    )
    _setup_graph_node_apply_mocks(mocked_responses, instance_name, resource_group_name, "myregistry")

    # Artifact content is binary / non-UTF-8 — decode("utf-8") would raise UnicodeDecodeError
    mock_artifact_info = Mock()
    mock_artifact_info.content = b"\xff\xfe invalid utf-8 \x80\x81"
    mock_oci = Mock()
    mock_oci.fetch_first_layer.return_value = mock_artifact_info
    mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.dataflow_graphs.get_oci_client",
        return_value=mock_oci,
    )

    mocked_responses.add(
        method=responses.PUT,
        url=get_dataflow_graph_endpoint(
            profile_name=profile_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            graph_name=graph_name,
        ),
        json=file_payload,
        status=200,
    )

    # Should not raise — UnicodeDecodeError is caught and validation is skipped
    result = apply_dataflow_graph(
        cmd=mocked_cmd,
        dataflow_graph_name=graph_name,
        profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        config_file="config.json",
        wait_sec=0.1,
    )

    assert result == file_payload


@pytest.mark.parametrize(
    "content_value",
    [None, 12345, ["not", "bytes"]],
    ids=["none", "int", "list"],
)
def test_dataflow_graph_apply_graph_node_invalid_artifact_content_type(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_file_config,
    mocker,
    content_value,
):
    """Apply skips config validation when artifact content is None or a non-bytes type (AttributeError/TypeError)."""

    graph_name = generate_random_string()
    profile_name = generate_random_string()
    instance_name = "myinstance"
    resource_group_name = "myresourcegroup"

    graph_properties = copy.deepcopy(_GRAPH_NODE_BASE_PROPERTIES)
    file_payload = {"properties": graph_properties}
    mocked_get_file_config.return_value = json.dumps(file_payload)

    mock_instance_record = get_mock_instance_record(
        name=instance_name, resource_group_name=resource_group_name
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_instance_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
        ),
        json=mock_instance_record,
        status=200,
    )
    _setup_graph_node_apply_mocks(mocked_responses, instance_name, resource_group_name, "myregistry")

    mock_artifact_info = Mock()
    mock_artifact_info.content = content_value
    mock_oci = Mock()
    mock_oci.fetch_first_layer.return_value = mock_artifact_info
    mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.dataflow_graphs.get_oci_client",
        return_value=mock_oci,
    )

    mocked_responses.add(
        method=responses.PUT,
        url=get_dataflow_graph_endpoint(
            profile_name=profile_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            graph_name=graph_name,
        ),
        json=file_payload,
        status=200,
    )

    # Should not raise — AttributeError/TypeError is caught and validation is skipped
    result = apply_dataflow_graph(
        cmd=mocked_cmd,
        dataflow_graph_name=graph_name,
        profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        config_file="config.json",
        wait_sec=0.1,
    )

    assert result == file_payload


@pytest.mark.parametrize(
    "configuration, expected_provided",
    [
        # Whitespace-only key — should not count as provided
        ([{"key": "   ", "value": "something"}], False),
        # Valid key with valid value — should count as provided
        ([{"key": "rules", "value": "something"}], True),
    ],
    ids=["whitespace_key", "valid_entry"],
)
def test_dataflow_graph_apply_config_entry_whitespace_key(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_file_config,
    mocker,
    configuration: list,
    expected_provided: bool,
):
    """_is_config_entry_provided treats whitespace-only keys as not provided."""

    graph_name = generate_random_string()
    profile_name = generate_random_string()
    instance_name = "myinstance"
    resource_group_name = "myresourcegroup"

    graph_properties = copy.deepcopy(_GRAPH_NODE_BASE_PROPERTIES)
    for node in graph_properties["nodes"]:
        if node["nodeType"] == "Graph":
            node["graphSettings"]["configuration"] = configuration

    file_payload = {"properties": graph_properties}
    mocked_get_file_config.return_value = json.dumps(file_payload)

    _setup_graph_node_apply_mocks(mocked_responses, instance_name, resource_group_name, "myregistry")
    _mock_oci_client(mocker, _MOCK_ARTIFACT_YAML_WITH_REQUIRED_PARAMS)

    if expected_provided:
        mock_instance_record = get_mock_instance_record(
            name=instance_name, resource_group_name=resource_group_name
        )
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
            method=responses.PUT,
            url=get_dataflow_graph_endpoint(
                profile_name=profile_name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
                graph_name=graph_name,
            ),
            json=file_payload,
            status=200,
        )
        result = apply_dataflow_graph(
            cmd=mocked_cmd,
            dataflow_graph_name=graph_name,
            profile_name=profile_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            config_file="config.json",
            wait_sec=0.1,
        )
        assert result == file_payload
    else:
        with pytest.raises(InvalidArgumentValueError) as exc:
            apply_dataflow_graph(
                cmd=mocked_cmd,
                dataflow_graph_name=graph_name,
                profile_name=profile_name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
                config_file="config.json",
                wait_sec=0.1,
            )
        assert "requires configuration parameter(s)" in exc.value.args[0]


# ---------------------------------------------------------------------------
# apply - transform / runtime version compatibility
# ---------------------------------------------------------------------------

def _artifact_yaml_with_runtime(runtime_version: Optional[str], required_param: bool = False) -> str:
    """Build a transform manifest YAML with an optional moduleRequirements.runtimeVersion."""
    lines = []
    if runtime_version is not None:
        lines.append("moduleRequirements:")
        lines.append(f"  runtimeVersion: '{runtime_version}'")
    lines.append("moduleConfigurations:")
    lines.append("  - name: mymodule")
    lines.append("    parameters:")
    lines.append("      rules:")
    lines.append("        name: rules")
    lines.append(f"        required: {'true' if required_param else 'false'}")
    return "\n".join(lines) + "\n"


def _add_instance_mock(mocked_responses, instance_name, resource_group_name, version, drop_version=False):
    record = get_mock_instance_record(
        name=instance_name, resource_group_name=resource_group_name, version=version
    )
    if drop_version:
        record["properties"].pop("version", None)
    mocked_responses.add(
        method=responses.GET,
        url=get_instance_endpoint(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
        ),
        json=record,
        status=200,
    )


def test_dataflow_graph_apply_transform_runtime_incompatible(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_file_config,
    mocker,
):
    """Apply is blocked when the transform requires a newer runtime than the instance."""

    graph_name = generate_random_string()
    profile_name = generate_random_string()
    instance_name = "myinstance"
    resource_group_name = "myresourcegroup"

    graph_properties = copy.deepcopy(_GRAPH_NODE_BASE_PROPERTIES)
    file_payload = {"properties": graph_properties}
    mocked_get_file_config.return_value = json.dumps(file_payload)

    _add_instance_mock(mocked_responses, instance_name, resource_group_name, version="1.3.137")
    _setup_graph_node_apply_mocks(mocked_responses, instance_name, resource_group_name, "myregistry")
    _mock_oci_client(mocker, _artifact_yaml_with_runtime("1.99.0"))

    with pytest.raises(InvalidArgumentValueError) as exc:
        apply_dataflow_graph(
            cmd=mocked_cmd,
            dataflow_graph_name=graph_name,
            profile_name=profile_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            config_file="config.json",
            wait_sec=0.1,
        )

    msg = exc.value.args[0]
    # Failure identifies the transform, selected version, required runtime, and instance version.
    assert "myartifact" in msg
    assert "1.0" in msg  # selected version (artifact 'myartifact:1.0')
    assert "1.99.0" in msg  # required runtime
    assert "1.3.137" in msg  # current instance version


@pytest.mark.parametrize("required_runtime", ["1.0.0", "1.3.0", "1.3.137"])
def test_dataflow_graph_apply_transform_runtime_compatible(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_file_config,
    mocker,
    required_runtime: str,
):
    """Apply succeeds when the instance runtime is >= the transform's required runtime."""

    graph_name = generate_random_string()
    profile_name = generate_random_string()
    instance_name = "myinstance"
    resource_group_name = "myresourcegroup"

    graph_properties = copy.deepcopy(_GRAPH_NODE_BASE_PROPERTIES)
    file_payload = {"properties": graph_properties}
    mocked_get_file_config.return_value = json.dumps(file_payload)

    _add_instance_mock(mocked_responses, instance_name, resource_group_name, version="1.3.137")
    _setup_graph_node_apply_mocks(mocked_responses, instance_name, resource_group_name, "myregistry")
    _mock_oci_client(mocker, _artifact_yaml_with_runtime(required_runtime))
    mocked_responses.add(
        method=responses.PUT,
        url=get_dataflow_graph_endpoint(
            profile_name=profile_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            graph_name=graph_name,
        ),
        json=file_payload,
        status=200,
    )

    result = apply_dataflow_graph(
        cmd=mocked_cmd,
        dataflow_graph_name=graph_name,
        profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        config_file="config.json",
        wait_sec=0.1,
    )
    assert result == file_payload


@pytest.mark.parametrize(
    "runtime_version, drop_instance_version",
    [
        (None, False),          # manifest declares no moduleRequirements.runtimeVersion
        ("not-a-version", False),  # malformed required runtime
        ("1.99.0", True),       # instance version cannot be determined
    ],
    ids=["missing_required", "malformed_required", "unknown_instance_version"],
)
def test_dataflow_graph_apply_transform_runtime_fail_open(
    mocked_cmd,
    mocked_responses: responses,
    mocked_get_file_config,
    mocker,
    runtime_version: Optional[str],
    drop_instance_version: bool,
):
    """Missing or malformed versions fail open — apply proceeds and defers to runtime enforcement."""

    graph_name = generate_random_string()
    profile_name = generate_random_string()
    instance_name = "myinstance"
    resource_group_name = "myresourcegroup"

    graph_properties = copy.deepcopy(_GRAPH_NODE_BASE_PROPERTIES)
    file_payload = {"properties": graph_properties}
    mocked_get_file_config.return_value = json.dumps(file_payload)

    _add_instance_mock(
        mocked_responses,
        instance_name,
        resource_group_name,
        version="1.3.137",
        drop_version=drop_instance_version,
    )
    _setup_graph_node_apply_mocks(mocked_responses, instance_name, resource_group_name, "myregistry")
    _mock_oci_client(mocker, _artifact_yaml_with_runtime(runtime_version))
    mocked_responses.add(
        method=responses.PUT,
        url=get_dataflow_graph_endpoint(
            profile_name=profile_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            graph_name=graph_name,
        ),
        json=file_payload,
        status=200,
    )

    result = apply_dataflow_graph(
        cmd=mocked_cmd,
        dataflow_graph_name=graph_name,
        profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        config_file="config.json",
        wait_sec=0.1,
    )
    assert result == file_payload
