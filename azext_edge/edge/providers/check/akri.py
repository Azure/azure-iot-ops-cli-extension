# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import re
from itertools import groupby
from kubernetes.client.models import V1Pod
from rich.padding import Padding
from typing import Any, Dict, List

from ...common import CheckTaskStatus

from ..edge_api import (
    AKRI_API_V0,
    AkriResourceKinds,
)

from ..support.akri import AKRI_PREFIXES

from .base import (
    CheckManager,
    check_post_deployment,
    generate_target_resource_name,
    get_namespaced_pods_by_prefix,
    process_dict_resource,
    process_pods_status,
    resources_grouped_by_namespace,
)

from .common import (
    PADDING_SIZE,
    CoreServiceResourceKinds,
    ResourceOutputDetailLevel,
)


def check_akri_deployment(
    result: Dict[str, Any],
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_kinds: List[str] = None
) -> None:
    evaluate_funcs = {
        CoreServiceResourceKinds.RUNTIME_RESOURCE: evaluate_core_service_runtime,
        AkriResourceKinds.CONFIGURATION: evaluate_configurations,
        AkriResourceKinds.INSTANCE: evaluate_instances,
    }

    check_post_deployment(
        api_info=AKRI_API_V0,
        check_name="enumerateAkriApi",
        check_desc="Enumerate Akri API resources",
        result=result,
        resource_kinds_enum=AkriResourceKinds,
        evaluate_funcs=evaluate_funcs,
        as_list=as_list,
        detail_level=detail_level,
        resource_kinds=resource_kinds,
    )


def evaluate_core_service_runtime(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> Dict[str, Any]:
    check_manager = CheckManager(check_name="evalCoreServiceRuntime", check_desc="Evaluate Akri core service")

    padding = 6
    akri_runtime_resources: List[dict] = []
    for prefix in AKRI_PREFIXES:
        akri_runtime_resources.extend(
            get_namespaced_pods_by_prefix(
                prefix=prefix,
                namespace="",
                label_selector="",
            )
        )

    def get_namespace(pod: V1Pod) -> str:
        return pod.metadata.namespace

    akri_runtime_resources.sort(key=get_namespace)

    for (namespace, pods) in groupby(akri_runtime_resources, get_namespace):
        check_manager.add_target(target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value, namespace=namespace)
        check_manager.add_display(
            target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value,
            namespace=namespace,
            display=Padding(
                f"Akri runtime resources in namespace {{[purple]{namespace}[/purple]}}",
                (0, 0, 0, padding)
            )
        )

        process_pods_status(
            check_manager=check_manager,
            target_service_pod="",
            target=CoreServiceResourceKinds.RUNTIME_RESOURCE.value,
            pods=list(pods),
            namespace=namespace,
            display_padding=padding + PADDING_SIZE,
        )

    return check_manager.as_dict(as_list)


def evaluate_configurations(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> Dict[str, Any]:
    check_manager = CheckManager(check_name="evalConfigurations", check_desc="Evaluate Akri configurations")

    target_configurations = generate_target_resource_name(api_info=AKRI_API_V0, resource_kind=AkriResourceKinds.CONFIGURATION.value)
    configuration_conditions = []

    all_configurations: dict = AKRI_API_V0.get_resources(AkriResourceKinds.CONFIGURATION).get("items", [])

    if not all_configurations:
        fetch_configurations_error_text = "Unable to fetch Akri configurations in any namespaces."
        check_manager.add_target(target_name=target_configurations)
        check_manager.add_target_eval(
            target_name=target_configurations,
            status=CheckTaskStatus.error.value,
            value={"configurations": fetch_configurations_error_text}
        )
        check_manager.add_display(target_name=target_configurations, display=Padding(fetch_configurations_error_text, (0, 0, 0, 8)))

    for (namespace, configurations) in resources_grouped_by_namespace(all_configurations):
        check_manager.add_target(
            target_name=target_configurations,
            namespace=namespace,
            conditions=configuration_conditions
        )
        check_manager.add_display(
            target_name=target_configurations,
            namespace=namespace,
            display=Padding(
                f"Akri configurations in namespace {{[purple]{namespace}[/purple]}}",
                (0, 0, 0, 8)
            )
        )

        padding = 10
        configurations: List[dict] = list(configurations)
        configurations_count = len(configurations)
        configurations_count_text = "- {}."

        configurations_count_text = configurations_count_text.format(f"Detected [blue]{configurations_count}[/blue] configurations")

        check_manager.add_display(
            target_name=target_configurations,
            namespace=namespace,
            display=Padding(configurations_count_text, (0, 0, 0, padding))
        )

        for configuration in configurations:
            configuration_name = configuration["metadata"]["name"]

            configuration_text = (
                f"- Akri configuration {{[bright_blue]{configuration_name}[/bright_blue]}} detected."
            )

            configuration_padding = padding + PADDING_SIZE
            check_manager.add_display(
                target_name=target_configurations,
                namespace=namespace,
                display=Padding(configuration_text, (0, 0, 0, configuration_padding))
            )

            spec = configuration["spec"]
            discovery_handler = spec.get("discoveryHandler", {})
            capacity = spec.get("capacity", {})
            broker_spec = spec.get("brokerSpec", {})
            instance_service_spec = spec.get("instanceServiceSpec", {})
            configuration_service_spec = spec.get("configurationServiceSpec", {})
            broker_properties = spec.get("brokerProperties", {})

            property_padding = configuration_padding + PADDING_SIZE
            _evaluate_discovery_handler(
                check_manager=check_manager,
                target_name=target_configurations,
                namespace=namespace,
                discovery_handler=discovery_handler,
                detail_level=detail_level,
                padding=property_padding,
            )

            if detail_level >= ResourceOutputDetailLevel.detail.value and capacity:
                check_manager.add_display(
                    target_name=target_configurations,
                    namespace=namespace,
                    display=Padding(
                        f"Capacity: [cyan]{capacity}[/cyan]",
                        (0, 0, 0, property_padding),
                    ),
                )

            if detail_level == ResourceOutputDetailLevel.verbose.value:
                for prop_name, prop_value in {
                    "Broker spec": broker_spec,
                    "Instance service spec": instance_service_spec,
                    "Configuration service spec": configuration_service_spec,
                }.items():
                    if prop_value:
                        process_dict_resource(
                            check_manager=check_manager,
                            target_name=target_configurations,
                            resource=prop_value,
                            namespace=namespace,
                            padding=16,
                            prop_name=prop_name,
                        )

                # broker properties
                if broker_properties:
                    for key, value in broker_properties:
                        check_manager.add_display(
                            target_name=target_configurations,
                            namespace=namespace,
                            display=Padding(
                                f"Broker property [cyan]{key}[/cyan]: [cyan]{value}[/cyan]",
                                (0, 0, 0, 16),
                            ),
                        )

    return check_manager.as_dict(as_list)


def evaluate_instances(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> Dict[str, Any]:
    check_manager = CheckManager(check_name="evalInstances", check_desc="Evaluate Akri instances")

    target_instances = generate_target_resource_name(api_info=AKRI_API_V0, resource_kind=AkriResourceKinds.INSTANCE.value)
    instance_conditions = []
    check_manager.add_target(target_name=target_instances, conditions=instance_conditions)

    all_instances: dict = AKRI_API_V0.get_resources(AkriResourceKinds.INSTANCE).get("items", [])

    if not all_instances:
        fetch_instances_skip_text = "Unable to fetch Akri instances in any namespaces."
        check_manager.add_target_eval(
            target_name=target_instances,
            status=CheckTaskStatus.skipped.value,
            value={"instances": fetch_instances_skip_text}
        )
        check_manager.add_display(target_name=target_instances, display=Padding(fetch_instances_skip_text, (0, 0, 0, 8)))

    for (namespace, instances) in resources_grouped_by_namespace(all_instances):
        check_manager.add_target(
            target_name=target_instances,
            namespace=namespace,
            conditions=instance_conditions
        )
        check_manager.add_display(
            target_name=target_instances,
            namespace=namespace,
            display=Padding(
                f"Akri instances in namespace {{[purple]{namespace}[/purple]}}",
                (0, 0, 0, 8)
            )
        )

        instances: List[dict] = list(instances)
        instances_count = len(instances)
        instances_count_text = "- {}."
        padding = 10

        instances_count_text = instances_count_text.format(f"Detected [blue]{instances_count}[/blue] instances")

        check_manager.add_display(
            target_name=target_instances,
            namespace=namespace,
            display=Padding(instances_count_text, (0, 0, 0, padding))
        )

        for instance in instances:
            spec = instance["spec"]
            instance_name = instance["metadata"]["name"]
            instance_padding = padding + PADDING_SIZE

            instance_text = (
                f"- Akri instance {{[bright_blue]{instance_name}[/bright_blue]}} detected."
            )

            check_manager.add_display(
                target_name=target_instances,
                namespace=namespace,
                display=Padding(instance_text, (0, 0, 0, instance_padding))
            )

            property_padding = instance_padding + PADDING_SIZE
            if detail_level >= ResourceOutputDetailLevel.detail.value:
                configuration_name = spec.get("configurationName", "")
                if configuration_name:
                    check_manager.add_display(
                        target_name=target_instances,
                        namespace=namespace,
                        display=Padding(
                            f"Configuration name: [cyan]{configuration_name}[/cyan]",
                            (0, 0, 0, property_padding),
                        ),
                    )

                shared = spec.get("shared", False)
                check_manager.add_display(
                    target_name=target_instances,
                    namespace=namespace,
                    display=Padding(
                        f"Shared: [cyan]{str(shared)}[/cyan]",
                        (0, 0, 0, property_padding),
                    ),
                )

                if detail_level == ResourceOutputDetailLevel.verbose.value:
                    broker_properties = spec.get("brokerProperties", {})
                    if broker_properties:
                        process_dict_resource(
                            check_manager=check_manager,
                            target_name=target_instances,
                            resource=broker_properties,
                            namespace=namespace,
                            padding=property_padding,
                            prop_name="Broker properties",
                        )

                    # nodes
                    nodes = spec.get("nodes", [])
                    for node in nodes:
                        check_manager.add_display(
                            target_name=target_instances,
                            namespace=namespace,
                            display=Padding(
                                f"Node: [cyan]{node}[/cyan]",
                                (0, 0, 0, property_padding),
                            ),
                        )

                    # deviceUsage
                    device_usage = spec.get("deviceUsage", {})
                    if device_usage:
                        process_dict_resource(
                            check_manager=check_manager,
                            target_name=target_instances,
                            resource=device_usage,
                            namespace=namespace,
                            padding=property_padding,
                            prop_name="Device usage",
                        )

    return check_manager.as_dict(as_list)


def _validate_one_of_conditions(
        conditions: List[tuple],
        check_manager: CheckManager,
        eval_value: dict,
        namespace: str,
        target_name: str,
        padding: int,
) -> None:
    if len(conditions) == 1:
        return

    non_empty_conditions_count = len([condition for condition in conditions if condition[1]])

    eval_status = CheckTaskStatus.success.value
    conditions_names = ", ".join([f"'{condition[0]}'" for condition in conditions])
    if non_empty_conditions_count == 0:
        check_manager.add_display(
            target_name=target_name,
            namespace=namespace,
            display=Padding(
                f"One of {conditions_names} should be specified",
                (0, 0, 0, padding),
            ),
        )
        eval_status = CheckTaskStatus.error.value
    elif non_empty_conditions_count > 1:
        check_manager.add_display(
            target_name=target_name,
            namespace=namespace,
            display=Padding(
                f"Only one of {conditions_names} should be specified",
                (0, 0, 0, padding),
            ),
        )
        eval_status = CheckTaskStatus.error.value

    check_manager.add_target_conditions(
        target_name=target_name,
        namespace=namespace,
        conditions=[condition[0] for condition in conditions]
    )
    check_manager.add_target_eval(
        target_name=target_name,
        namespace=namespace,
        status=eval_status,
        value=eval_value
    )


def _evaluate_discovery_handler(
    check_manager: CheckManager,
    target_name: str,
    namespace: str,
    discovery_handler: dict,
    detail_level: int,
    padding: int,
) -> None:
    if discovery_handler:
        name = discovery_handler.get("name", "")
        discovery_details = discovery_handler.get("discoveryDetails", "")
        discovery_properties = discovery_handler.get("discoveryProperties", [])

        if detail_level >= ResourceOutputDetailLevel.detail.value:
            check_manager.add_display(
                target_name=target_name,
                namespace=namespace,
                display=Padding(
                    f"Name: [cyan]{name}[/cyan]",
                    (0, 0, 0, padding),
                ),
            )

            if discovery_details:
                check_manager.add_display(
                    target_name=target_name,
                    namespace=namespace,
                    display=Padding(
                        "Discovery details:",
                        (0, 0, 0, padding),
                    ),
                )

                check_manager.add_display(
                    target_name=target_name,
                    namespace=namespace,
                    display=Padding(
                        f"[cyan]{discovery_details}[/cyan]",
                        (0, 0, 0, padding + PADDING_SIZE),
                    ),
                )

        property_header_padding = padding + PADDING_SIZE

        if discovery_properties:
            check_manager.add_display(
                target_name=target_name,
                namespace=namespace,
                display=Padding(
                    "Discovery properties:",
                    (0, 0, 0, padding),
                ),
            )
            for property in discovery_properties:
                property_name: str = property.get("name", "")
                property_condition_str = f"spec.discoveryHandler.discoveryProperties['{property_name}']"

                # name
                check_manager.set_target_conditions(
                    target_name=target_name,
                    namespace=namespace,
                    conditions=[f"{property_condition_str}.name"],
                )

                check_manager.add_display(
                    target_name=target_name,
                    namespace=namespace,
                    display=Padding(
                        f"- Property [cyan]{property_name}[/cyan] detected.",
                        (0, 0, 0, property_header_padding),
                    ),
                )
                property_name_eval_value = {f"{property_condition_str}.name": property_name}
                property_name_eval_status = CheckTaskStatus.success.value
                name_pattern = "^[_A-Za-z][_A-Za-z0-9]*$"
                property_padding = property_header_padding + PADDING_SIZE

                # name should be a valid identifier match the pattern
                if not property_name or not re.match(name_pattern, property_name):
                    property_name_error_text = (
                        f"[red]Property name should be a valid identifier that matches the pattern {name_pattern}.[/red]"
                    )
                    property_name_eval_status = CheckTaskStatus.error.value
                    check_manager.add_display(
                        target_name=target_name,
                        namespace=namespace,
                        display=Padding(property_name_error_text, (0, 0, 0, property_padding)),
                    )

                check_manager.add_target_eval(
                    target_name=target_name,
                    namespace=namespace,
                    status=property_name_eval_status,
                    value=property_name_eval_value
                )

                # "value" and "valueFrom" are mutually exclusive
                value = property.get("value", "")
                value_from = property.get("valueFrom", "")
                value_eval_value = {
                    f"{property_condition_str}.value": value,
                    f"{property_condition_str}.valueFrom": value_from
                }
                _validate_one_of_conditions(
                    conditions=[
                        ("value", value),
                        ("valueFrom", value_from)
                    ],
                    check_manager=check_manager,
                    eval_value=value_eval_value,
                    namespace=namespace,
                    target_name=target_name,
                    padding=property_padding
                )

                if value:
                    if detail_level >= ResourceOutputDetailLevel.detail.value:
                        check_manager.add_display(
                            target_name=target_name,
                            namespace=namespace,
                            display=Padding(
                                f"Property value: [cyan]{value}[/cyan]",
                                (0, 0, 0, property_padding),
                            ),
                        )
                elif value_from:
                    check_manager.add_display(
                        target_name=target_name,
                        namespace=namespace,
                        display=Padding(
                            "Value from:",
                            (0, 0, 0, property_padding),
                        ),
                    )

                    key_ref_padding = property_padding + PADDING_SIZE
                    secret_key_ref = value_from.get("secretKeyRef", {})
                    config_map_key_ref = value_from.get("configMapKeyRef", {})
                    key_ref_eval_value = {
                        f"{property_condition_str}.valueFrom.secretKeyRef": secret_key_ref,
                        f"{property_condition_str}.valueFrom.configMapKeyRef": config_map_key_ref
                    }
                    _validate_one_of_conditions(
                        conditions=[
                            ("secretKeyRef", secret_key_ref),
                            ("configMapKeyRef", config_map_key_ref)
                        ],
                        check_manager=check_manager,
                        eval_value=key_ref_eval_value,
                        namespace=namespace,
                        target_name=target_name,
                        padding=key_ref_padding
                    )

                    if secret_key_ref or config_map_key_ref:
                        key_ref_property = ("secret_key_ref", secret_key_ref) if secret_key_ref else ("config_map_key_ref", config_map_key_ref)
                        key_ref_name = key_ref_property[1].get("name", "")
                        key_ref_key = key_ref_property[1].get("key", "")
                        key_ref_namespace = key_ref_property[1].get("namespace", "")
                        key_ref_optional = key_ref_property[1].get("optional", False)

                        check_manager.add_target_conditions(
                            target_name=target_name,
                            namespace=namespace,
                            conditions=[
                                f"{property_condition_str}.valueFrom.{key_ref_property[0]}.name",
                            ],
                        )

                        key_ref_name_eval_value = {f"{property_condition_str}.valueFrom.{key_ref_property[0]}.name": key_ref_name}
                        key_ref_name_eval_status = CheckTaskStatus.success.value
                        if not key_ref_name:
                            key_ref_name_error_text = f"[red]Property {key_ref_property[0]} name is required.[/red]"
                            key_ref_name_eval_status = CheckTaskStatus.error.value
                            check_manager.add_display(
                                target_name=target_name,
                                namespace=namespace,
                                display=Padding(key_ref_name_error_text, (0, 0, 0, key_ref_padding)),
                            )
                        else:
                            check_manager.add_display(
                                target_name=target_name,
                                namespace=namespace,
                                display=Padding(
                                    f"Property {key_ref_property[0]} {{[cyan]{key_ref_name}[/cyan]}} detected.",
                                    (0, 0, 0, key_ref_padding),
                                ),
                            )

                        check_manager.add_target_eval(
                            target_name=target_name,
                            namespace=namespace,
                            status=key_ref_name_eval_status,
                            value=key_ref_name_eval_value
                        )

                        if detail_level >= ResourceOutputDetailLevel.detail.value:
                            key_ref_property_padding = key_ref_padding + PADDING_SIZE
                            if key_ref_key:
                                check_manager.add_display(
                                    target_name=target_name,
                                    namespace=namespace,
                                    display=Padding(
                                        f"Key: [cyan]{key_ref_key}[/cyan]",
                                        (0, 0, 0, key_ref_property_padding),
                                    ),
                                )

                            if key_ref_namespace:
                                check_manager.add_display(
                                    target_name=target_name,
                                    namespace=namespace,
                                    display=Padding(
                                        f"Namespace: [cyan]{key_ref_namespace}[/cyan]",
                                        (0, 0, 0, key_ref_property_padding),
                                    ),
                                )

                            if key_ref_optional:
                                check_manager.add_display(
                                    target_name=target_name,
                                    namespace=namespace,
                                    display=Padding(
                                        f"Optional: [cyan]{str(key_ref_optional)}[/cyan]",
                                        (0, 0, 0, key_ref_property_padding),
                                    ),
                                )
