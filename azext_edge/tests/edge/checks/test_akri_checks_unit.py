# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


import pytest
from azext_edge.edge.providers.check.akri import (
    evaluate_configurations,
    evaluate_core_service_runtime,
    evaluate_instances
)
from azext_edge.edge.providers.check.common import (
    CoreServiceResourceKinds,
    ResourceOutputDetailLevel
)
from azext_edge.edge.providers.edge_api.akri import AkriResourceKinds

from .conftest import (
    assert_check_by_resource_types,
    assert_conditions,
    assert_evaluations,
    generate_pod_stub,
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
        CoreServiceResourceKinds.RUNTIME_RESOURCE.value:
            "azext_edge.edge.providers.check.akri.evaluate_core_service_runtime",
        AkriResourceKinds.CONFIGURATION.value: "azext_edge.edge.providers.check.akri.evaluate_configurations",
        AkriResourceKinds.INSTANCE.value: "azext_edge.edge.providers.check.akri.evaluate_instances",
    }

    assert_check_by_resource_types(ops_service, mocker, mock_resource_types, resource_kinds, eval_lookup)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("resource_name", [None, "test*", "test-configuration"])
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
                                    "name": "example",
                                    "value": "example"
                                }
                            ]
                        },
                    }
                }
            ],
            # conditions
            [
                "spec.discoveryHandler.discoveryProperties['example'].name",
            ],
            # evaluations
            [
                [
                    ("status", "success"),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].name", "example"),
                ],
            ],
        ),
        # invalid discoveryProperties name
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
        # no discoveryProperties value nor valueFrom
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
                                    "name": "example",
                                }
                            ]
                        },
                    }
                }
            ],
            # conditions
            [
                "spec.discoveryHandler.discoveryProperties['example'].name",
                "value",
                "valueFrom",
            ],
            # evaluations
            [
                [
                    ("status", "success"),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].name", "example"),
                ],
                [
                    ("status", "error"),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].value", ""),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].valueFrom", ""),
                ],
            ],
        ),
        # both discoveryProperties value and valueFrom defined
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
                                    "name": "example",
                                    "value": "example",
                                    "valueFrom": "example"
                                }
                            ]
                        },
                    }
                }
            ],
            # conditions
            [
                "spec.discoveryHandler.discoveryProperties['example'].name",
                "value",
                "valueFrom",
            ],
            # evaluations
            [
                [
                    ("status", "success"),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].name", "example"),
                ],
                [
                    ("status", "error"),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].value", "example"),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].valueFrom", "example"),
                ],
            ],
        ),
        # no valueFrom secretKeyRef or configMapKeyRef defined
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
                                    "name": "example",
                                    "valueFrom": {
                                        "hello": "world"
                                    }
                                }
                            ]
                        },
                    }
                }
            ],
            # conditions
            [
                "spec.discoveryHandler.discoveryProperties['example'].name",
                "value",
                "valueFrom",
                "secretKeyRef",
                "configMapKeyRef",
            ],
            # evaluations
            [
                [
                    ("status", "success"),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].name", "example"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].value", ""),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].valueFrom", {"hello": "world"}),
                ],
                [
                    ("status", "error"),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].valueFrom.secretKeyRef", {}),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].valueFrom.configMapKeyRef", {}),
                ],
            ],
        ),
        # both valueFrom secretKeyRef and configMapKeyRef defined
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
                                    "name": "example",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": "example",
                                            "key": "example"
                                        },
                                        "configMapKeyRef": {
                                            "name": "example",
                                            "key": "example"
                                        }
                                    }
                                }
                            ]
                        },
                    }
                }
            ],
            # conditions
            [
                "spec.discoveryHandler.discoveryProperties['example'].name",
                "value",
                "valueFrom",
                "secretKeyRef",
                "configMapKeyRef",
            ],
            # evaluations
            [
                [
                    ("status", "success"),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].name", "example"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].value", ""),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].valueFrom", {
                        "secretKeyRef": {
                            "name": "example",
                            "key": "example"
                        },
                        "configMapKeyRef": {
                            "name": "example",
                            "key": "example"
                        }
                    }),
                ],
                [
                    ("status", "error"),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].valueFrom.secretKeyRef", {
                        "name": "example",
                        "key": "example"
                    }),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].valueFrom.configMapKeyRef", {
                        "name": "example",
                        "key": "example"
                    }),
                ],
            ],
        ),
        # secretKeyRef defined but no name
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
                                    "name": "example",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "key": "example"
                                        }
                                    }
                                }
                            ]
                        },
                    }
                }
            ],
            # conditions
            [
                "spec.discoveryHandler.discoveryProperties['example'].name",
                "value",
                "valueFrom",
                "secretKeyRef",
                "configMapKeyRef",
                "spec.discoveryHandler.discoveryProperties['example'].valueFrom.secret_key_ref.name",
            ],
            # evaluations
            [
                [
                    ("status", "success"),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].name", "example"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].value", ""),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].valueFrom", {
                        "secretKeyRef": {
                            "key": "example"
                        }
                    }),
                ],
                [
                    ("status", "success"),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].valueFrom.secretKeyRef", {
                        "key": "example"
                    }),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].valueFrom.configMapKeyRef", {}),
                ],
                [
                    ("status", "error"),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].valueFrom.secret_key_ref.name", ""),
                ],
            ],
        ),
        # configMapKeyRef defined but no name
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
                                    "name": "example",
                                    "valueFrom": {
                                        "configMapKeyRef": {
                                            "key": "example"
                                        }
                                    }
                                }
                            ]
                        },
                    }
                }
            ],
            # conditions
            [
                "spec.discoveryHandler.discoveryProperties['example'].name",
                "value",
                "valueFrom",
                "secretKeyRef",
                "configMapKeyRef",
                "spec.discoveryHandler.discoveryProperties['example'].valueFrom.config_map_key_ref.name",
            ],
            # evaluations
            [
                [
                    ("status", "success"),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].name", "example"),
                ],
                [
                    ("status", "success"),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].value", ""),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].valueFrom", {
                        "configMapKeyRef": {
                            "key": "example"
                        }
                    }),
                ],
                [
                    ("status", "success"),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].valueFrom.secretKeyRef", {}),
                    ("value/spec.discoveryHandler.discoveryProperties['example'].valueFrom.configMapKeyRef", {
                        "key": "example"
                    }),
                ],
                [
                    ("status", "error"),
                    (
                        "value/spec.discoveryHandler.discoveryProperties['example'].valueFrom.config_map_key_ref.name",
                        ""
                    ),
                ],
            ],
        ),
        # no configuration
        (
            # configurations
            [],
            # conditions
            [],
            # evaluations
            [
                [
                    ("status", "error"),
                    ("value/configurations", "Unable to fetch Akri configurations in any namespaces."),
                ]
            ],
        ),
    ],
)
def test_evaluate_configurations(
    mocker,
    configurations,
    conditions,
    evaluations,
    detail_level,
    resource_name,
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        side_effect=[{"items": configurations}],
    )

    namespace = generate_generic_id()
    for configuration in configurations:
        configuration['metadata']['namespace'] = namespace
    result = evaluate_configurations(detail_level=detail_level, resource_name=resource_name)

    assert result["name"] == "evalConfigurations"
    assert result["targets"]["configurations.akri.sh"]
    target = result["targets"]["configurations.akri.sh"]

    for namespace in target:
        assert namespace in result["targets"]["configurations.akri.sh"]

        target[namespace]["conditions"] = [] if not target[namespace]["conditions"] else target[namespace]["conditions"]
        assert_conditions(target[namespace], conditions)
        assert_evaluations(target[namespace], evaluations)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("resource_name", [None, "test*", "test-instance"])
@pytest.mark.parametrize(
    "instances, conditions, evaluations",
    [
        (
            # instances
            [
                {
                    "metadata": {
                        "name": "test-instance",
                    },
                    "spec": {
                        "configurationName": "test-configuration",
                        "brokerProperties": {
                            "name": "example",
                            "value": "example"
                        },
                    }
                }
            ],
            # conditions
            [],
            # evaluations
            [],
        ),
        # no instance
        (
            # instances
            [],
            # conditions
            [],
            # evaluations
            [
                [
                    ("status", "skipped"),
                    ("value/instances", "Unable to fetch Akri instances in any namespaces."),
                ]
            ],
        ),
    ],
)
def test_evaluate_instances(
    mocker,
    instances,
    conditions,
    evaluations,
    detail_level,
    resource_name,
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.edge_api.base.EdgeResourceApi.get_resources",
        side_effect=[{"items": instances}],
    )

    namespace = generate_generic_id()
    for instance in instances:
        instance['metadata']['namespace'] = namespace
    result = evaluate_instances(detail_level=detail_level, resource_name=resource_name)

    assert result["name"] == "evalInstances"
    assert result["targets"]["instances.akri.sh"]
    target = result["targets"]["instances.akri.sh"]

    for namespace in target:
        assert namespace in result["targets"]["instances.akri.sh"]

        target[namespace]["conditions"] = [] if not target[namespace]["conditions"] else target[namespace]["conditions"]
        assert_conditions(target[namespace], conditions)
        assert_evaluations(target[namespace], evaluations)


@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("resource_name", [None, "akri-*", "AKRI-*"])
@pytest.mark.parametrize(
    "pods, namespace_conditions, namespace_evaluations",
    [
        (
            # pods
            [
                generate_pod_stub(
                    name="akri-1",
                    phase="Running",
                )
            ],
            # namespace conditions str
            [],
            # namespace evaluations str
            [
                [
                    ("status", "success"),
                    ("value/status.phase", "Running"),
                ],
            ]
        ),
        (
            # pods
            [
                generate_pod_stub(
                    name="akri-1",
                    phase="Failed",
                )
            ],
            # namespace conditions str
            [],
            # namespace evaluations str
            [
                [
                    ("status", "error")
                ],
            ]
        ),
    ]
)
def test_evaluate_core_service_runtime(
    mocker,
    pods,
    namespace_conditions,
    namespace_evaluations,
    detail_level,
    resource_name,
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.check.akri.get_namespaced_pods_by_prefix",
        return_value=pods,
    )

    namespace = generate_generic_id()
    for pod in pods:
        pod.metadata.namespace = namespace
    result = evaluate_core_service_runtime(detail_level=detail_level, resource_name=resource_name)

    assert result["name"] == "evalCoreServiceRuntime"
    assert result["targets"][CoreServiceResourceKinds.RUNTIME_RESOURCE.value]
    target = result["targets"][CoreServiceResourceKinds.RUNTIME_RESOURCE.value]

    for namespace in target:
        assert namespace in result["targets"][CoreServiceResourceKinds.RUNTIME_RESOURCE.value]

        target[namespace]["conditions"] = [] if not target[namespace]["conditions"] else target[namespace]["conditions"]
        assert_conditions(target[namespace], namespace_conditions)
        assert_evaluations(target[namespace], namespace_evaluations)
