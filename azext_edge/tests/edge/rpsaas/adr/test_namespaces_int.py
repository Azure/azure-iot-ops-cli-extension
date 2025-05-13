# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, List, Optional
import pytest
from knack.log import get_logger
from ....generators import generate_random_string
from ....helpers import run

logger = get_logger(__name__)

# pytest mark for rpsaas (cloud-side) tests
pytestmark = pytest.mark.rpsaas


def test_namespace_lifecycle(tracked_resources: List[str], settings_with_rg):
    rg = settings_with_rg.env.azext_edge_rg

    # Create two eventgrid topics
    eventgrid1 = run(
        f"az eventgrid topic create -n testns{generate_random_string(force_lower=True)} -g {rg}"
    )
    eventgrid2 = run(
        f"az eventgrid topic create -n testns{generate_random_string(force_lower=True)} -g {rg}"
    )
    tracked_resources.append(eventgrid1["id"])
    tracked_resources.append(eventgrid2["id"])

    # Create a minimal namespace
    namespace_name1 = "testns" + generate_random_string()[:4]
    min_namespace = run(
        f"az iot ops namespace create -n {namespace_name1} -g {rg} --initial-endpoint-ids {eventgrid1['id']}"
    )
    tracked_resources.append(min_namespace["id"])
    assert_namespace_properties(result=min_namespace, name=namespace_name1, identity_type="None")

    # Show namespace
    namespace = run(
        f"az iot ops namespace show -n {namespace_name1} -g {rg}"
    )
    assert_namespace_properties(result=namespace, name=namespace_name1, identity_type="None")

    # Update namespace with system identity
    namespace = run(
        f"az iot ops namespace update -n {namespace_name1} -g {rg} --mi-system-identity "
    )
    assert_namespace_properties(result=namespace, name=namespace_name1, identity_type="SystemAssigned")

    # Add an endpoint to the namespace
    namespace = run(
        f"az iot ops namespace endpoint add -n {namespace_name1} -g {rg} "
        f"--endpoint-id {eventgrid2['id']}"
    )
    assert_namespace_properties(
        result=namespace,
        name=namespace_name1,
        endpoint_ids_to_address={
            eventgrid1["id"]: eventgrid1["properties"]["endpoint"],
        },
        identity_type="SystemAssigned",
    )

    # Remove the endpoint from the namespace
    namespace = run(
        f"az iot ops namespace endpoint remove -n {namespace_name1} -g {rg} "
        f"--endpoint-id {eventgrid2['id']}"
    )
    assert_namespace_properties(result=namespace, identity_type="SystemAssigned")

    # Create a namespace with all parameters
    namespace_name2 = "testns" + generate_random_string()[:4]
    tags = {"key1": "value1", "key2": "value2"}
    tags_str = " ".join([f"{k}={v}" for k, v in tags.items()])
    namespace = run(
        f"az iot ops namespace create -n {namespace_name2} -g {rg} --mi-system-identity "
        f"--initial-endpoint-ids {eventgrid1['id']} {eventgrid2['id']} --tags {tags_str}"
    )
    tracked_resources.append(namespace["id"])
    assert_namespace_properties(
        result=namespace,
        name=namespace_name2,
        endpoint_ids_to_address={
            eventgrid1["id"]: eventgrid1["properties"]["endpoint"],
            eventgrid2["id"]: eventgrid2["properties"]["endpoint"],
        },
        identity_type="SystemAssigned",
        tags=tags
    )

    # List endpoints
    endpoints = run(
        f"az iot ops namespace endpoint list -n {namespace_name2} -g {rg}"
    )
    assert_namespace_endpoint_props(
        result_endpoints=endpoints,
        endpoint_ids_to_address={
            eventgrid1["id"]: eventgrid1["properties"]["endpoint"],
            eventgrid2["id"]: eventgrid2["properties"]["endpoint"],
        }
    )

    # Remove multiple endpoints from the namespace
    endpoints = run(
        f"az iot ops namespace endpoint remove -n {namespace_name2} -g {rg} "
        f"--endpoint-ids {eventgrid1['id']} {eventgrid2['id']}"
    )
    assert_namespace_endpoint_props(result_endpoints=endpoints)

    # Add multiple endpoints to the namespace
    endpoints = run(
        f"az iot ops namespace endpoint add -n {namespace_name2} -g {rg} "
        f"--endpoint-ids {eventgrid1['id']} {eventgrid2['id']}"
    )
    assert_namespace_endpoint_props(
        result_endpoints=endpoints,
        endpoint_ids_to_address={
            eventgrid1["id"]: eventgrid1["properties"]["endpoint"],
            eventgrid2["id"]: eventgrid2["properties"]["endpoint"],
        }
    )

    # List namespaces
    namespaces = run(
        f"az iot ops namespace list -g {rg}"
    )
    namespace_names = [ns["name"] for ns in namespaces]
    assert namespace_name1 in namespace_names
    assert namespace_name2 in namespace_names

    # Delete namespace
    run(f"az iot ops asset namespace delete -n {namespace_name1} -g {rg}")
    run(f"az iot ops asset namespace delete -n {namespace_name2} -g {rg}")
    tracked_resources.remove(namespace["id"])
    tracked_resources.remove(min_namespace["id"])


def assert_namespace_properties(result: dict, endpoint_ids_to_address: Optional[Dict[str, str]] = None, **expected):
    assert result["name"] == expected["name"]
    assert result["identity"]["type"] == expected["identity_type"]
    if expected.get("tags"):
        assert result["tags"] == expected["tags"]

    assert_namespace_endpoint_props(result["properties"]["messaging"]["endpoints"], endpoint_ids_to_address)


def assert_namespace_endpoint_props(result_endpoints: dict, endpoint_ids_to_address: Optional[Dict[str, str]] = None):
    endpoint_ids_to_address = endpoint_ids_to_address or {}

    assert len(result_endpoints) == len(endpoint_ids_to_address)
    for endpoint_id in endpoint_ids_to_address:
        endpoint_id_parts = endpoint_id.split('/')
        endpoint_resource_group = endpoint_id_parts[4]
        endpoint_name = endpoint_id_parts[-1]
        endpoint_key = f"{endpoint_resource_group}-{endpoint_name}"

        assert result_endpoints[endpoint_key]["resourceId"] == endpoint_id
        assert result_endpoints[endpoint_key]["resourceType"] == "Microsoft.EventGrid/topics"
        assert result_endpoints[endpoint_key]["address"] == endpoint_ids_to_address[endpoint_id]
