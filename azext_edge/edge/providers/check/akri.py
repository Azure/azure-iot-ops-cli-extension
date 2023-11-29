# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict, List

from .base import (
    CheckManager,
    check_post_deployment,
    evaluate_pod_health,
    resources_grouped_by_namespace,
)

from rich.padding import Padding

from ...common import CheckTaskStatus

from .common import (
    ResourceOutputDetailLevel,
)

from ..edge_api import (
    AKRI_API_V0,
    AkriResourceKinds,
)

from ..support.akri import AKRI_PREFIXES, AKRI_NAME_LABEL


def check_akri_deployment(
    result: Dict[str, Any],
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_kinds: List[str] = None
) -> None:
    evaluate_funcs = {
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


def evaluate_configurations(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> Dict[str, Any]:
    check_manager = CheckManager(check_name="evalAssetTypes", check_desc="Evaluate OPCUA asset types")

    target_configurations = "configurations.akri.sh"
    configuration_conditions = ["len(configurations)>=0"]
    check_manager.add_target(target_name=target_configurations, conditions=configuration_conditions)

    all_configurations: dict = AKRI_API_V0.get_resources(AkriResourceKinds.CONFIGURATION).get("items", [])

    if not all_configurations:
        fetch_configurations_error_text = "Unable to fetch Akri configurations in any namespaces."
        check_manager.add_target_eval(
            target_name=target_configurations,
            status=CheckTaskStatus.error.value,
            value={"configurations": fetch_configurations_error_text}
        )
        check_manager.add_display(target_name=target_configurations, display=Padding(fetch_configurations_error_text, (0, 0, 0, 8)))

    for (namespace, configurations) in resources_grouped_by_namespace(all_configurations):
        check_manager.add_target(target_name=target_configurations, namespace=namespace, conditions=configuration_conditions)
        check_manager.add_display(
            target_name=target_configurations,
            namespace=namespace,
            display=Padding(
                f"Akri configurations in namespace {{[purple]{namespace}[/purple]}}",
                (0, 0, 0, 8)
            )
        )

        configurations: List[dict] = list(configurations)
        configurations_count = len(configurations)
        configurations_count_text = "- Expecting [bright_blue]>=1[/bright_blue] instance resource per namespace. {}."

        if configurations_count >= 1:
            configurations_count_text = configurations_count_text.format(f"[green]Detected {configurations_count}[/green]")
        else:
            configurations_count_text = configurations_count_text.format(f"[red]Detected {configurations_count}[/red]")
            check_manager.set_target_status(target_name=all_configurations, status=CheckTaskStatus.error.value)
        check_manager.add_display(
            target_name=target_configurations,
            namespace=namespace,
            display=Padding(configurations_count_text, (0, 0, 0, 10))
        )

        for configuration in configurations:
            configuration_name = configuration["metadata"]["name"]

            configuration_text = (
                f"- Akri configuration {{[bright_blue]{configuration_name}[/bright_blue]}} detected."
            )

            check_manager.add_display(
                target_name=target_configurations,
                namespace=namespace,
                display=Padding(configuration_text, (0, 0, 0, 12))
            )

            if detail_level >= ResourceOutputDetailLevel.detail.value:
                spec = configuration["spec"]
            

        if configurations_count > 0:
            check_manager.add_display(
                target_name=target_configurations,
                namespace=namespace,
                display=Padding(
                    "\nRuntime Health",
                    (0, 0, 0, 10),
                ),
            )

            for pod in AKRI_PREFIXES:
                evaluate_pod_health(
                    check_manager=check_manager,
                    target=target_configurations,
                    pod=pod,
                    display_padding=12,
                    service_label=AKRI_NAME_LABEL if pod == "" else AKRI_NAME_LABEL,
                    namespace=namespace,
                )

    return check_manager.as_dict(as_list)


def evaluate_instances(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> Dict[str, Any]:
    check_manager = CheckManager(check_name="evalAssetTypes", check_desc="Evaluate OPCUA asset types")

    target_asset_types = "instances.akri.sh"
    asset_type_conditions = ["len(asset_types)>=0"]
    check_manager.add_target(target_name=target_asset_types, conditions=asset_type_conditions)

    all_instances: dict = AKRI_API_V0.get_resources(AkriResourceKinds.INSTANCE).get("items", [])

    if not all_instances:
        fetch_asset_types_error_text = "Unable to fetch OPCUA asset types in any namespaces."
        check_manager.add_target_eval(
            target_name=target_asset_types,
            status=CheckTaskStatus.skipped.value,
            value={"asset_types": fetch_asset_types_error_text}
        )
        check_manager.add_display(target_name=target_asset_types, display=Padding(fetch_asset_types_error_text, (0, 0, 0, 8)))

    for (namespace, asset_types) in resources_grouped_by_namespace(all_instances):
        check_manager.add_target(target_name=target_asset_types, namespace=namespace, conditions=asset_type_conditions)
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
            check_manager.set_target_status(target_name=all_instances, status=CheckTaskStatus.error.value)
        check_manager.add_display(
            target_name=target_asset_types,
            namespace=namespace,
            display=Padding(asset_types_count_text, (0, 0, 0, 10))
        )

        for asset_type in asset_types:
            asset_type_name = asset_type["metadata"]["name"]

            asset_type_text = (
                f"- Opcua asset type {{[bright_blue]{asset_type_name}[/bright_blue]}} detected."
            )

            check_manager.add_display(
                target_name=target_asset_types,
                namespace=namespace,
                display=Padding(asset_type_text, (0, 0, 0, 12))
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
                    padding=16,
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

            for pod in ["", OPC_PREFIX]:
                evaluate_pod_health(
                    check_manager=check_manager,
                    target=target_asset_types,
                    pod=pod,
                    display_padding=12,
                    service_label=OPC_NAME_LABEL if pod == "" else OPC_APP_LABEL,
                    namespace=namespace,
                )

    return check_manager.as_dict(as_list)


def _process_schema(
        check_manager: CheckManager,
        target_asset_types: str,
        namespace: str,
        schema: str,
        padding: int,
        detail_level: int = ResourceOutputDetailLevel.summary.value
) -> None:

    if detail_level == ResourceOutputDetailLevel.detail.value:
        # convert JSON string to dict
        import json

        schema_dict = json.loads(schema)

        schema_items = {
            "DTDL version": ("@context", lambda x: x.split(";")[1] if ';' in x else None),
            "Type": ("@type", lambda x: x)
        }

        schema_id = schema_dict["@id"]
        check_manager.add_display(
            target_name=target_asset_types,
            namespace=namespace,
            display=Padding(f"Schema {{[cyan]{schema_id}[/cyan]}} detected.", (0, 0, 0, padding)),
        )

        padding += 4

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
                (0, 0, 0, padding + 4),
            ),
        )
