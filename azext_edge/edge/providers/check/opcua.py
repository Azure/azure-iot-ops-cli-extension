# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict, List, Tuple

from azext_edge.edge.providers.base import get_namespaced_pods_by_prefix

from .base import (
    CheckManager,
    add_display_and_eval,
    check_post_deployment,
    decorate_pod_phase,
    evaluate_pod_health,
    process_properties,
    resources_grouped_by_namespace,
)

from rich.padding import Padding
from kubernetes.client.models import V1Pod

from ...common import CheckTaskStatus

from .common import (
    AIO_LNM_PREFIX,
    LNM_ALLOWLIST_PROPERTIES,
    LNM_EXCLUDED_SUBRESOURCE,
    LNM_IMAGE_PROPERTIES,
    LNM_POD_CONDITION_TEXT_MAP,
    LNM_REST_PROPERTIES,
    ResourceOutputDetailLevel,
)

from ..edge_api import (
    OPCUA_API_V1,
    OpcuaResourceKinds,
)

from ..support.opcua import OPC_APP_LABEL, OPC_PREFIX


def check_opcua_deployment(
    result: Dict[str, Any],
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_kinds: List[str] = None
) -> None:
    evaluate_funcs = {
        OpcuaResourceKinds.ASSET_TYPE: evaluate_asset_types,
    }

    check_post_deployment(
        api_info=OPCUA_API_V1,
        check_name="enumerateOpcuaApi",
        check_desc="Enumerate OPCUA API resources",
        result=result,
        resource_kinds_enum=OpcuaResourceKinds,
        evaluate_funcs=evaluate_funcs,
        as_list=as_list,
        detail_level=detail_level,
        resource_kinds=resource_kinds,
    )


def evaluate_asset_types(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> Dict[str, Any]:
    check_manager = CheckManager(check_name="evalAssetTypes", check_desc="Evaluate OPCUA asset types")

    target_asset_types = "assettypes.opcuabroker.iotoperations.azure.com"
    asset_type_namespace_conditions = ["len(asset_types)>=0", "status.configStatusLevel", "spec.allowList", "spec.image"]

    all_asset_types: dict = OPCUA_API_V1.get_resources(OpcuaResourceKinds.ASSET_TYPE).get("items", [])

    if not all_asset_types:
        fetch_asset_types_error_text = "Unable to fetch OPCUA asset types in any namespaces."
        check_manager.add_target_eval(
            target_name=target_asset_types,
            status=CheckTaskStatus.skipped.value,
            value={"asset_types": fetch_asset_types_error_text}
        )
        check_manager.add_display(target_name=target_asset_types, display=Padding(fetch_asset_types_error_text, (0, 0, 0, 8)))

    for (namespace, asset_types) in resources_grouped_by_namespace(all_asset_types):
        check_manager.add_target(target_name=target_asset_types, namespace=namespace, conditions=asset_type_namespace_conditions)
        check_manager.add_display(
            target_name=target_asset_types,
            namespace=namespace,
            display=Padding(
                f"OPCUA asset types in namespace {{[purple]{namespace}[/purple]}}",
                (0, 0, 0, 8)
            )
        )

        asset_types: List[dict] = list(asset_types)
        asset_types_count = len(asset_types)
        asset_types_count_text = "- Expecting [bright_blue]>=1[/bright_blue] instance resource per namespace. {}."

        if asset_types_count >= 1:
            asset_types_count_text = asset_types_count_text.format(f"[green]Detected {asset_types_count}[/green]")
        else:
            asset_types_count_text = asset_types_count_text.format(f"[red]Detected {asset_types_count}[/red]")
            check_manager.set_target_status(target_name=all_asset_types, status=CheckTaskStatus.error.value)
        check_manager.add_display(
            target_name=target_asset_types,
            namespace=namespace,
            display=Padding(asset_types_count_text, (0, 0, 0, 10))
        )

        for asset_type in asset_types:
            asset_type_name = asset_type["metadata"]["name"]

            lnm_text = (
                f"- Opcua asset type {{[bright_blue]{asset_type_name}[/bright_blue]}} detected."
            )

            check_manager.add_display(
                target_name=target_asset_types,
                namespace=namespace,
                display=Padding(lnm_text, (0, 0, 0, 12))
            )

            spec = asset_type["spec"]
            if detail_level >= ResourceOutputDetailLevel.detail.value:
                # label summarize
                labels = spec["labels"]
                check_manager.add_display(
                    target_name=target_asset_types,
                    namespace=namespace,
                    display=Padding(
                        f"Detected [cyan]{len(labels)}[/cyan] labels",
                        (0, 0, 0, 16),
                    ),
                )

                if detail_level == ResourceOutputDetailLevel.verbose.value:
                    # remove repeated labels
                    non_repeated_labels = list(set(labels))

                    if len(non_repeated_labels) > 0:
                        check_manager.add_display(
                            target_name=target_asset_types,
                            namespace=namespace,
                            display=Padding(
                                "[yellow](Only non repeatative labels will be displayed)[/yellow]",
                                (0, 0, 0, 20),
                            ),
                        )

                        check_manager.add_display(
                            target_name=target_asset_types,
                            namespace=namespace,
                            display=Padding(
                                f"[cyan]{', '.join(non_repeated_labels)}[/cyan]",
                                (0, 0, 0, 20),
                            ),
                        )

                # schema summarize
                schema = spec["schema"]
                _process_schema(
                    check_manager=check_manager,
                    target_asset_types=target_asset_types,
                    namespace=namespace,
                    schema=schema,
                    detail_level=detail_level
                )

        if asset_types_count > 0:
            check_manager.add_display(
                target_name=target_asset_types,
                namespace=namespace,
                display=Padding(
                    "\nRuntime Health",
                    (0, 0, 0, 10),
                ),
            )

            evaluate_pod_health(
                check_manager=check_manager,
                target=target_asset_types,
                pod=OPC_PREFIX,
                display_padding=12,
                service_label=OPC_APP_LABEL,
                namespace=namespace,
            )

    return check_manager.as_dict(as_list)


def _process_schema(check_manager: CheckManager, target_asset_types: str, namespace: str, schema: str, detail_level: int = ResourceOutputDetailLevel.summary.value) -> None:
    # convert JSON string to dict
    import json
    schema_dict = json.loads(schema)

    if detail_level == ResourceOutputDetailLevel.detail.value:
        # get the schema id
        schema_id = schema_dict["@id"]

        check_manager.add_display(
            target_name=target_asset_types,
            namespace=namespace,
            display=Padding(
                f"Schema {{[cyan]{schema_id}[/cyan]}} detected",
                (0, 0, 0, 16),
            ),
        )

        # get the schema version in @context and the string looks like "dtmi:dtdl:context;3"
        schema_version = schema_dict["@context"].split(";")[1]

        check_manager.add_display(
            target_name=target_asset_types,
            namespace=namespace,
            display=Padding(
                f"DTDL version: [cyan]{schema_version}[/cyan]",
                (0, 0, 0, 20),
            ),
        )

        # get the schema type
        schema_type = schema_dict["@type"]

        check_manager.add_display(
            target_name=target_asset_types,
            namespace=namespace,
            display=Padding(
                f"Type: [cyan]{schema_type}[/cyan]",
                (0, 0, 0, 20),
            ),
        )
    elif detail_level == ResourceOutputDetailLevel.verbose.value:
        from rich.json import JSON
        schema_json = JSON(schema, indent=2)
        check_manager.add_display(
            target_name=target_asset_types,
            namespace=namespace,
            display=Padding(
                "Schema: ",
                (0, 0, 0, 16),
            ),
        )
        check_manager.add_display(
            target_name=target_asset_types,
            namespace=namespace,
            display=Padding(
                schema_json,
                (0, 0, 0, 20),
            ),
        )
