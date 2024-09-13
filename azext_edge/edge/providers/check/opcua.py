# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from rich.padding import Padding
from typing import Any, Dict, List

from ..base import get_namespaced_pods_by_prefix

from .base import (
    CheckManager,
    check_post_deployment,
    filter_resources_by_name,
    generate_target_resource_name,
    get_resources_by_name,
    evaluate_pod_health,
    get_resources_grouped_by_namespace,
)

from ...common import CheckTaskStatus

from .common import (
    PADDING_SIZE,
    CoreServiceResourceKinds,
    ResourceOutputDetailLevel,
)

from ..edge_api import (
    OPCUA_API_V1,
    OpcuaResourceKinds,
)

from ..support.opcua import OPC_NAME_VAR_LABEL, OPCUA_NAME_LABEL


def check_opcua_deployment(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_kinds: List[str] = None,
    resource_name: str = None,
) -> List[dict]:
    evaluate_funcs = {
        CoreServiceResourceKinds.RUNTIME_RESOURCE: evaluate_core_service_runtime,
        OpcuaResourceKinds.ASSET_TYPE: evaluate_asset_types,
    }

    return check_post_deployment(
        api_info=OPCUA_API_V1,
        check_name="enumerateOpcUaBrokerApi",
        check_desc="Enumerate OPC UA broker API resources",
        evaluate_funcs=evaluate_funcs,
        as_list=as_list,
        detail_level=detail_level,
        resource_kinds=resource_kinds,
        resource_name=resource_name,
    )


def evaluate_core_service_runtime(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
) -> Dict[str, Any]:
    check_manager = CheckManager(check_name="evalCoreServiceRuntime", check_desc="Evaluate OPC UA broker core service")

    padding = 6
    opcua_runtime_resources: List[dict] = []
    for label_selector in [OPC_NAME_VAR_LABEL, OPCUA_NAME_LABEL]:
        opcua_runtime_resources.extend(
            get_namespaced_pods_by_prefix(
                prefix="",
                namespace="",
                label_selector=label_selector,
            )
        )

    if resource_name:
        opcua_runtime_resources = filter_resources_by_name(
            resources=opcua_runtime_resources,
            resource_name=resource_name,
        )

        if not opcua_runtime_resources:
            check_manager.add_target(target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value)
            check_manager.add_display(
                target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value,
                display=Padding("Unable to fetch pods.", (0, 0, 0, padding + 2)),
            )

    for namespace, pods in get_resources_grouped_by_namespace(opcua_runtime_resources):
        check_manager.add_target(target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value, namespace=namespace)
        check_manager.add_display(
            target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value,
            namespace=namespace,
            display=Padding(
                f"OPC UA broker runtime resources in namespace {{[purple]{namespace}[/purple]}}", (0, 0, 0, padding)
            ),
        )

        evaluate_pod_health(
            check_manager=check_manager,
            target=CoreServiceResourceKinds.RUNTIME_RESOURCE.value,
            namespace=namespace,
            padding=padding + PADDING_SIZE,
            detail_level=detail_level,
            pods=pods,
        )

    return check_manager.as_dict(as_list)


def evaluate_asset_types(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
) -> Dict[str, Any]:
    check_manager = CheckManager(check_name="evalAssetTypes", check_desc="Evaluate OPC UA broker asset types")
    asset_type_conditions = ["len(asset_types)>=0"]

    all_asset_types: dict = get_resources_by_name(
        api_info=OPCUA_API_V1,
        kind=OpcuaResourceKinds.ASSET_TYPE,
        resource_name=resource_name,
    )
    target_asset_types = generate_target_resource_name(
        api_info=OPCUA_API_V1, resource_kind=OpcuaResourceKinds.ASSET_TYPE.value
    )

    if not all_asset_types:
        fetch_asset_types_error_text = "Unable to fetch OPC UA broker asset types in any namespaces."
        check_manager.add_target(target_name=target_asset_types)
        check_manager.add_target_eval(
            target_name=target_asset_types,
            status=CheckTaskStatus.skipped.value,
            value={"asset_types": fetch_asset_types_error_text},
        )
        check_manager.add_display(
            target_name=target_asset_types, display=Padding(fetch_asset_types_error_text, (0, 0, 0, 8))
        )

    for namespace, asset_types in get_resources_grouped_by_namespace(all_asset_types):
        check_manager.add_target(target_name=target_asset_types, namespace=namespace, conditions=asset_type_conditions)
        check_manager.add_display(
            target_name=target_asset_types,
            namespace=namespace,
            display=Padding(f"OPC UA broker asset types in namespace {{[purple]{namespace}[/purple]}}", (0, 0, 0, 8)),
        )

        asset_types: List[dict] = list(asset_types)
        asset_types_count = len(asset_types)
        asset_types_count_text = "- Expecting [bright_blue]>=1[/bright_blue] asset type resource per namespace. {}."
        padding = 10

        if asset_types_count >= 1:
            asset_types_count_text = asset_types_count_text.format(f"[green]Detected {asset_types_count}[/green]")
        else:
            asset_types_count_text = asset_types_count_text.format(f"[red]Detected {asset_types_count}[/red]")
            check_manager.set_target_status(target_name=all_asset_types, status=CheckTaskStatus.error.value)
        check_manager.add_display(
            target_name=target_asset_types,
            namespace=namespace,
            display=Padding(asset_types_count_text, (0, 0, 0, padding)),
        )

        for asset_type in asset_types:
            asset_type_name = asset_type["metadata"]["name"]

            asset_type_text = f"- Asset type {{[bright_blue]{asset_type_name}[/bright_blue]}} detected."
            asset_type_padding = padding + PADDING_SIZE

            check_manager.add_display(
                target_name=target_asset_types,
                namespace=namespace,
                display=Padding(asset_type_text, (0, 0, 0, asset_type_padding)),
            )

            spec = asset_type["spec"]
            property_padding = asset_type_padding + PADDING_SIZE

            if detail_level >= ResourceOutputDetailLevel.detail.value:
                # label summarize
                labels = spec["labels"]

                # remove repeated labels
                non_repeated_labels = list(set(labels))
                check_manager.add_display(
                    target_name=target_asset_types,
                    namespace=namespace,
                    display=Padding(
                        f"Detected [cyan]{len(non_repeated_labels)}[/cyan] unique labels",
                        (0, 0, 0, property_padding),
                    ),
                )

                if detail_level == ResourceOutputDetailLevel.verbose.value:
                    if len(non_repeated_labels) > 0:
                        check_manager.add_display(
                            target_name=target_asset_types,
                            namespace=namespace,
                            display=Padding(
                                f"[cyan]{', '.join(non_repeated_labels)}[/cyan]",
                                (0, 0, 0, property_padding + PADDING_SIZE),
                            ),
                        )

                # schema summarize
                schema = spec["schema"]
                _process_schema(
                    check_manager=check_manager,
                    target_asset_types=target_asset_types,
                    namespace=namespace,
                    schema=schema,
                    padding=property_padding,
                    detail_level=detail_level,
                )

    return check_manager.as_dict(as_list)


def _process_schema(
    check_manager: CheckManager,
    target_asset_types: str,
    namespace: str,
    schema: str,
    padding: int,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> None:

    if detail_level == ResourceOutputDetailLevel.detail.value:
        # convert JSON string to dict
        import json

        schema_dict = json.loads(schema)

        schema_items = {
            "DTDL version": ("@context", lambda x: x.split(";")[1] if ";" in x else None),
            "Type": ("@type", lambda x: x),
        }

        schema_id = schema_dict["@id"]
        check_manager.add_display(
            target_name=target_asset_types,
            namespace=namespace,
            display=Padding(f"Schema {{[cyan]{schema_id}[/cyan]}} detected.", (0, 0, 0, padding)),
        )

        padding += PADDING_SIZE

        for item_label, (schema_key, value_extractor) in schema_items.items():
            # Extract value using the defined lambda function
            item_value = value_extractor(schema_dict[schema_key])

            # Skip adding the display if the extracted value is None
            if item_value is None:
                continue

            message = f"{item_label}: [cyan]{item_value}[/cyan]"
            check_manager.add_display(
                target_name=target_asset_types,
                namespace=namespace,
                display=Padding(message, (0, 0, 0, padding)),
            )
    elif detail_level == ResourceOutputDetailLevel.verbose.value:
        from rich.json import JSON

        schema_json = JSON(schema, indent=2)
        check_manager.add_display(
            target_name=target_asset_types,
            namespace=namespace,
            display=Padding(
                "Schema: ",
                (0, 0, 0, padding),
            ),
        )
        check_manager.add_display(
            target_name=target_asset_types,
            namespace=namespace,
            display=Padding(
                schema_json,
                (0, 0, 0, padding + PADDING_SIZE),
            ),
        )
