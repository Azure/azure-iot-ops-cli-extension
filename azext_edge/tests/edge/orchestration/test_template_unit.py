# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from unittest import TestCase

import pytest

from azext_edge.edge.providers.orchestration.template import (
    TEMPLATE_BLUEPRINT_ENABLEMENT,
    TEMPLATE_BLUEPRINT_INSTANCE,
    TemplateBlueprint,
    get_insecure_listener,
)

from ...generators import generate_random_string


EXPECTED_EXTENSION_RESOURCE_KEYS = frozenset(
    [
        "cluster",
        "aio_platform_extension",
        "secret_store_extension",
        "container_storage_extension",
    ]
)


EXPECTED_INSTANCE_RESOURCE_KEYS = frozenset(
    [
        "cluster",
        "aio_extension",
        "customLocation",
        "aio_syncRule",
        "deviceRegistry_syncRule",
        "aioInstance",
        "broker",
        "broker_authn",
        "broker_listener",
        "dataflow_profile",
        "dataflow_endpoint",
    ]
)

EXPECTED_SHARED_DEFINITION_KEYS = frozenset(
    [
        "_1.AdvancedConfig",
        "_1.BrokerConfig",
        "_1.CustomerManaged",
        "_1.SelfSigned",
        "_1.TrustBundleSettings",
    ]
)


def test_enablement_template():
    assert TEMPLATE_BLUEPRINT_ENABLEMENT.commit_id
    assert TEMPLATE_BLUEPRINT_ENABLEMENT.content

    for key in EXPECTED_EXTENSION_RESOURCE_KEYS:
        assert key in TEMPLATE_BLUEPRINT_ENABLEMENT.content["resources"]

    for definition in EXPECTED_SHARED_DEFINITION_KEYS:
        assert TEMPLATE_BLUEPRINT_ENABLEMENT.get_type_definition(definition)["properties"]


def test_instance_template():
    assert TEMPLATE_BLUEPRINT_INSTANCE.commit_id
    assert TEMPLATE_BLUEPRINT_INSTANCE.content

    for key in EXPECTED_INSTANCE_RESOURCE_KEYS:
        assert key in TEMPLATE_BLUEPRINT_INSTANCE.content["resources"]

    assert not TEMPLATE_BLUEPRINT_INSTANCE.get_resource_by_key("doesnotexist")["properties"]
    for definition in EXPECTED_SHARED_DEFINITION_KEYS:
        assert TEMPLATE_BLUEPRINT_INSTANCE.get_type_definition(definition)["properties"]

    instance = TEMPLATE_BLUEPRINT_INSTANCE.get_resource_by_type("Microsoft.IoTOperations/instances")
    assert instance and isinstance(instance, dict)

    # Copy test in other area
    blueprint_template_copy = TEMPLATE_BLUEPRINT_INSTANCE.copy()

    instance_name = generate_random_string()
    broker_name = generate_random_string()

    blueprint_template_copy.add_resource("insecure_listener", get_insecure_listener(instance_name, broker_name))
    listeners = blueprint_template_copy.get_resource_by_type(
        "Microsoft.IoTOperations/instances/brokers/listeners", first=False
    )
    assert listeners and isinstance(listeners, list)
    assert len(listeners) == 2


@pytest.mark.parametrize(
    "content",
    [
        {
            "definitions": {
                "_1.SelfSigned": {
                    "type": "object",
                    "properties": {"source": {"type": "string", "allowedValues": ["SelfSigned"]}},
                    "metadata": {"__bicep_imported_from!": {"sourceTemplate": "types.bicep"}},
                }
            },
            "resources": {
                "cluster": {
                    "existing": True,
                    "type": "Microsoft.Kubernetes/connectedClusters",
                    "apiVersion": "2021-03-01",
                    "name": "[parameters('clusterName')]",
                }
            },
            "parameters": {"clusterName": {"type": "string"}},
        }
    ],
)
def test_template_blueprint(content: dict):
    commit_id = generate_random_string()
    blueprint = TemplateBlueprint(commit_id=commit_id, content=content)

    assert blueprint.commit_id == commit_id

    content_resources = content.get("resources", {})
    for r in content_resources:
        assert r in blueprint.content["resources"]
        assert blueprint.get_resource_by_key(r) == content_resources[r]

    content_definitions = content.get("definitions", {})
    for d in content_definitions:
        blueprint_def = blueprint.get_type_definition(d)
        assert blueprint_def == content_definitions[d]

    content_parameters = content.get("parameters", {})
    for p in content_parameters:
        assert p in blueprint.parameters
        assert blueprint.parameters[p] == content_parameters[p]

    blueprint_copy = blueprint.copy()
    TestCase().assertDictEqual(blueprint.content, blueprint_copy.content, "Blueprint copy does not match blueprint.")
    assert blueprint.commit_id == blueprint_copy.commit_id
