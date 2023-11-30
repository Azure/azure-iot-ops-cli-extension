# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


from azext_edge.edge.providers.check.common import ResourceOutputDetailLevel
import pytest
from azext_edge.edge.providers.edge_api.akri import AkriResourceKinds
from azext_edge.edge.providers.check.akri import evaluate_configurations, evaluate_instances

from .conftest import (
    assert_check_by_resource_types,
    assert_conditions,
    assert_evaluations,
    generate_resource_stub
)
from ...generators import generate_generic_id


@pytest.mark.parametrize(
    "resource_kinds",
    [
        None,
        [],
        [AkriResourceKinds.CONFIGURATION.value],
        [AkriResourceKinds.INSTANCE.value],
        [AkriResourceKinds.CONFIGURATION.value, AkriResourceKinds.INSTANCE.value],
    ],
)
@pytest.mark.parametrize('ops_service', ['akri'])
def test_check_akri_by_resource_types(ops_service, mocker, mock_resource_types, resource_kinds):
    eval_lookup = {
        AkriResourceKinds.CONFIGURATION.value: "azext_edge.edge.providers.check.akri.evaluate_configurations",
        AkriResourceKinds.INSTANCE.value: "azext_edge.edge.providers.check.akri.evaluate_instances",
    }

    assert_check_by_resource_types(ops_service, mocker, mock_resource_types, resource_kinds, eval_lookup)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize(
    "configurations, conditions, evaluations",
    [
        (
            # configurations
            [
                {
                    "metadata": {
                        "name": "test-configuration",
                    },
                    "spec": {
                        "discoveryHandler": {
                            "discoveryProperties": [
                                {
                                    "name": "123_example",
                                    "value": "123_example"
                                }
                            ]
                        },
                    }
                }
            ],
            # conditions
            [
                "spec.discoveryHandler.discoveryProperties['123_example'].name",
            ],
            # evaluations
            [
                [
                    ("status", "error"),
                    ("value/spec.discoveryHandler.discoveryProperties['123_example'].name", "123_example"),
                ],
            ],
        ),
    ],
)
def test_evaluate_configurations(
    mocker,
    mock_evaluate_akri_pod_health,
    configurations,
    conditions,
    evaluations,
    detail_level,
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        side_effect=[{"items": configurations}],
    )

    namespace = generate_generic_id()
    for configuration in configurations:
        configuration['metadata']['namespace'] = namespace
    result = evaluate_configurations(detail_level=detail_level)

    assert result["name"] == "evalConfigurations"
    assert result["targets"]["configurations.akri.sh"]
    target = result["targets"]["configurations.akri.sh"]

    for namespace in target:
        assert namespace in result["targets"]["configurations.akri.sh"]

        target[namespace]["conditions"] = [] if not target[namespace]["conditions"] else target[namespace]["conditions"]
        assert_conditions(target[namespace], conditions)
        assert_evaluations(target[namespace], evaluations)
