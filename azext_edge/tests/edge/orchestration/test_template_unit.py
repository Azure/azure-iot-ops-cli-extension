# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from unittest import TestCase

import pytest

from azext_edge.edge.providers.orchestration.template import (
    IOT_OPERATIONS_VERSION_MONIKER,
    M2_ENABLEMENT_TEMPLATE,
    M2_INSTANCE_TEMPLATE,
    TemplateBlueprint,
    get_insecure_listener,
)

from ...generators import generate_random_string

assert IOT_OPERATIONS_VERSION_MONIKER

EXPECTED_EXTENSION_RESOURCE_KEYS = frozenset(
    [
        "cluster",
        "aio_platform_extension",
        "secret_sync_controller_extension",
        "open_service_mesh_extension",
        "edge_storage_accelerator_extension",
        "aio_extension",
    ]
)


EXPECTED_INSTANCE_RESOURCE_KEYS = frozenset(
    [
        "cluster",
        "customLocation",
        "broker_syncRule",
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
    assert M2_ENABLEMENT_TEMPLATE.commit_id
    assert M2_ENABLEMENT_TEMPLATE.content

    for resource in EXPECTED_EXTENSION_RESOURCE_KEYS:
        assert M2_ENABLEMENT_TEMPLATE.get_resource_by_key(resource)

    for definition in EXPECTED_SHARED_DEFINITION_KEYS:
        assert M2_ENABLEMENT_TEMPLATE.get_type_definition(definition)


def test_instance_template():
    assert M2_INSTANCE_TEMPLATE.commit_id
    assert M2_INSTANCE_TEMPLATE.content

    for resource in EXPECTED_INSTANCE_RESOURCE_KEYS:
        assert M2_INSTANCE_TEMPLATE.get_resource_by_key(resource)

    for definition in EXPECTED_SHARED_DEFINITION_KEYS:
        assert M2_INSTANCE_TEMPLATE.get_type_definition(definition)

    instance = M2_INSTANCE_TEMPLATE.get_resource_by_type("Microsoft.IoTOperations/instances")
    assert instance and isinstance(instance, dict)

    # Copy test in other area
    m2_template_copy = M2_INSTANCE_TEMPLATE.copy()

    instance_name = generate_random_string()
    broker_name = generate_random_string()

    m2_template_copy.add_resource("insecure_listener", get_insecure_listener(instance_name, broker_name))
    listeners = m2_template_copy.get_resource_by_type(
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
