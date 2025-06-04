# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List
import pytest
from knack.log import get_logger
from ....generators import generate_random_string
from ....helpers import run

logger = get_logger(__name__)

# pytest mark for rpsaas (cloud-side) tests
pytestmark = pytest.mark.rpsaas


def test_namespace_lifecycle(tracked_resources: List[str], settings_with_rg):
    rg = settings_with_rg.env.azext_edge_rg

    # Create a minimal namespace
    namespace_name1 = "testns" + generate_random_string(force_lower=True)[:4]
    min_namespace = run(
        f"az iot ops namespace create -n {namespace_name1} -g {rg}"
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
        f"az iot ops namespace update -n {namespace_name1} -g {rg} --mi-system-assigned "
    )
    assert_namespace_properties(result=namespace, name=namespace_name1, identity_type="SystemAssigned")

    # Create a namespace with all parameters
    namespace_name2 = "testns" + generate_random_string(force_lower=True)[:4]
    tags = {"key1": "value1", "key2": "value2"}
    tags_str = " ".join([f"{k}={v}" for k, v in tags.items()])
    namespace = run(
        f"az iot ops namespace create -n {namespace_name2} -g {rg} --mi-system-assigned "
        f"--tags {tags_str}"
    )
    tracked_resources.append(namespace["id"])
    assert_namespace_properties(
        result=namespace,
        name=namespace_name2,
        identity_type="SystemAssigned",
        tags=tags
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


def assert_namespace_properties(result: dict, **expected):
    assert result["name"] == expected["name"]
    assert result["identity"]["type"] == expected["identity_type"]
    if expected.get("tags"):
        assert result["tags"] == expected["tags"]
