# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Callable, Dict, List, Optional, Tuple
from .base import (
    CheckManager,
    evaluate_pod_health,
    filter_by_namespace,
    filter_resources_by_name,
    get_resource_metadata_property,
    resources_grouped_by_namespace,
)

from rich.padding import Padding

from ...common import CheckTaskStatus

from .common import PADDING_SIZE, ResourceOutputDetailLevel

from ...providers.edge_api import MQ_ACTIVE_API, MqResourceKinds
from ..support.mq import MQ_LABEL


def process_cloud_connector(
    connector_target: str,
    topic_map_target: str,
    connector_display_name: str,
    topic_map_reference_key: str,
    connector_resource_kind: MqResourceKinds,
    topic_map_resource_kind: MqResourceKinds,
    connector_display_func: Callable[
        [CheckManager, str, str, Dict[str, str], str, Tuple[int, int, int, int]], None
    ],
    topic_map_display_func: Callable[
        [CheckManager, str, str, List[Dict[str, str]], str, Tuple[int, int, int, int]],
        None,
    ],
    detail_level: str = ResourceOutputDetailLevel.summary.value,
    as_list: bool = False,
    connector_resource_name: str = None,
):
    # Create check manager
    check_manager = CheckManager(
        check_name=f"eval{connector_resource_kind.value}s",
        check_desc=f"Evaluate {connector_display_name}s",
    )

    connector_padding = (0, 0, 0, 8)
    topic_map_padding = (0, 0, 0, 12)

    all_connectors = MQ_ACTIVE_API.get_resources(kind=connector_resource_kind).get(
        "items", []
    )
    all_topic_maps = MQ_ACTIVE_API.get_resources(kind=topic_map_resource_kind).get(
        "items", []
    )

    if connector_resource_name:
        filtered_connectors = filter_resources_by_name(
            resources=all_connectors, resource_name=connector_resource_name
        )

        excluded_connectors = [
            connector
            for connector in all_connectors
            if connector not in filtered_connectors
        ]

        all_connectors = filtered_connectors

        # get (name, namespace) tuples for excluded connectors
        excluded_connector_properties = [
            (
                get_resource_metadata_property(connector, prop_name="name"), 
                get_resource_metadata_property(connector, prop_name="namespace")
            ) for connector in excluded_connectors
        ]

        # filter out topic maps with both excluded connector name and namespace
        all_topic_maps = [
            map
            for map in all_topic_maps
            if (
                map.get("spec", {}).get(topic_map_reference_key),
                get_resource_metadata_property(map, prop_name="namespace"),
            )
            not in excluded_connector_properties
        ]

    # if we have no connectors of this type, mark as skipped
    if not all_connectors:
        _mark_connector_target_as_skipped(
            check_manager=check_manager,
            target=connector_target,
            message=f"No {connector_display_name} resources detected",
            padding=connector_padding,
        )
        if detail_level != ResourceOutputDetailLevel.summary.value and not connector_resource_name:
            for topic_maps, namespace in resources_grouped_by_namespace(
                all_topic_maps
            ):
                _display_invalid_topic_maps(
                    check_manager=check_manager,
                    target=connector_target,
                    namespace=namespace,
                    topic_maps=topic_maps,
                    ref_key=topic_map_reference_key,
                    padding=connector_padding,
                )

    # track displayed topic maps
    processed_maps = []
    for namespace, connectors in resources_grouped_by_namespace(all_connectors):
        namespace_topic_maps = filter_by_namespace(all_topic_maps, namespace)

        check_manager.add_target(target_name=connector_target, namespace=namespace)
        check_manager.set_target_conditions(
            target_name=connector_target,
            namespace=namespace,
            conditions=["status", "valid(spec)", "len(spec.instances)>=1"],
        )
        check_manager.add_display(
            target_name=connector_target,
            namespace=namespace,
            display=Padding(
                f"{connector_display_name}s in namespace {{[purple]{namespace}[/purple]}}",
                (0, 0, 0, 8),
            ),
        )

        connector_list = list(connectors)
        for connector in connector_list:
            connector_name = get_resource_metadata_property(connector, prop_name="name")
            # display connector info
            connector_display_func(
                check_manager=check_manager,
                target=connector_target,
                namespace=namespace,
                connector=connector,
                detail_level=detail_level,
                padding=connector_padding,
            )

            # map topic maps to connector
            connector_topic_maps = [
                map
                for map in namespace_topic_maps
                if map.get("spec", {}).get(topic_map_reference_key) == connector_name
            ]
            processed_maps.extend(connector_topic_maps)

            # display topic map info
            topic_map_display_func(
                check_manager=check_manager,
                target=connector_target,
                namespace=namespace,
                topic_maps=connector_topic_maps,
                detail_level=detail_level,
                padding=topic_map_padding,
            )

        if detail_level != ResourceOutputDetailLevel.summary.value:
            # invalid topic maps in this namespace
            invalid_maps = [
                map for map in namespace_topic_maps if map not in processed_maps
            ]
            processed_maps.extend(invalid_maps)
            _display_invalid_topic_maps(
                check_manager=check_manager,
                target=connector_target,
                namespace=namespace,
                ref_key=topic_map_reference_key,
                padding=connector_padding,
                topic_maps=invalid_maps,
            )

        # resource health
        _display_connector_runtime_health(
            check_manager=check_manager,
            target=connector_target,
            namespace=namespace,
            connectors=connector_list,
        )
    # only show invalid topic maps in other namespaces in non-summary detail-levels
    if detail_level != ResourceOutputDetailLevel.summary.value:
        invalid_maps = [map for map in all_topic_maps if map not in processed_maps]
        for namespace, maps in resources_grouped_by_namespace(invalid_maps):
            check_manager.add_target(
                target_name=topic_map_target,
                namespace=namespace,
                description="Invalid cloud connector topic maps",
            )
            check_manager.add_display(
                target_name=topic_map_target,
                namespace=namespace,
                display=Padding(
                    f"Invalid topic maps in namespace {{[purple]{namespace}[/purple]}}",
                    connector_padding,
                ),
            )
            check_manager.add_target_eval(
                target_name=topic_map_target,
                namespace=namespace,
                resource_kind=topic_map_resource_kind,
                status=CheckTaskStatus.skipped.value,
            )
            _display_invalid_topic_maps(
                check_manager=check_manager,
                target=topic_map_target,
                namespace=namespace,
                topic_maps=maps,
                ref_key=topic_map_reference_key,
                padding=connector_padding,
            )

    return check_manager.as_dict(as_list)


def _display_connector_runtime_health(
    check_manager: CheckManager,
    namespace: str,
    target: str,
    connectors: Optional[List[Dict[str, Any]]] = None,
    prefix: str = "aio-mq-",
    padding: int = 8,
):
    if connectors:
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(
                "\nRuntime Health",
                (0, 0, 0, padding),
            ),
        )
        padding += PADDING_SIZE
        pod_name_prefixes = [
            f"{prefix}{connector['metadata']['name']}" for connector in connectors
        ]
        for pod in pod_name_prefixes:
            evaluate_pod_health(
                check_manager=check_manager,
                target=target,
                namespace=namespace,
                pod=pod,
                display_padding=padding,
                service_label=MQ_LABEL,
            )


def _display_invalid_topic_maps(
    check_manager: CheckManager,
    target: str,
    namespace: str,
    topic_maps: List[Dict[str, Any]],
    ref_key: str,
    padding: tuple,
):
    for map in topic_maps:
        name = get_resource_metadata_property(map, prop_name="name")
        ref = map.get("spec", {}).get(ref_key)
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(
                f"\n- Topic map {{[red]{name}[/red]}} references invalid connector {{[red]{ref}[/red]}}",
                padding,
            ),
        )


def _mark_connector_target_as_skipped(
    check_manager: CheckManager, target: str, message: str, padding: int = 8
):
    check_manager.add_target(target_name=target)
    check_manager.add_target_eval(
        target_name=target,
        status=CheckTaskStatus.skipped.value,
        value=message,
    )
    check_manager.set_target_status(
        target_name=target, status=CheckTaskStatus.skipped.value
    )
    check_manager.add_display(target_name=target, display=Padding(message, padding))
