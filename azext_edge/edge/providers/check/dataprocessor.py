# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict, List, Tuple
from .base import (
    CheckManager,
    add_display_and_eval,
    decorate_resource_status,
    check_post_deployment,
    evaluate_pod_health,
    generate_target_resource_name,
    get_resources_by_name,
    process_resource_properties,
    process_resource_property_by_type,
    get_resources_grouped_by_namespace,
)

from rich.padding import Padding

from ...common import (
    CheckTaskStatus,
    ListableEnum,
    ProvisioningState,
)

from .common import (
    DATA_PROCESSOR_AUTHENTICATION_REQUIRED_PROPERTIES,
    DATA_PROCESSOR_AUTHENTICATION_SECRET_REF,
    DATA_PROCESSOR_DESTINATION_REQUIRED_PROPERTIES,
    DATA_PROCESSOR_DESTINATION_STAGE_PROPERTIES,
    DATA_PROCESSOR_INTERMEDIATE_REQUIRED_PROPERTIES,
    DATA_PROCESSOR_INTERMEDIATE_STAGE_PROPERTIES,
    DATA_PROCESSOR_NATS_PREFIX,
    DATA_PROCESSOR_OPERATOR,
    DATA_PROCESSOR_READER_WORKER_PREFIX,
    DATA_PROCESSOR_REFDATA_STORE_PREFIX,
    DATA_PROCESSOR_RUNNER_WORKER_PREFIX,
    DATA_PROCESSOR_SOURCE_REQUIRED_PROPERTIES,
    DATA_PROCESSOR_SOURCE_DISPLAY_PROPERTIES,
    ERROR_NO_DETAIL,
    PADDING_SIZE,
    DataProcessorStageType,
    DataSourceStageType,
    DataprocessorAuthenticationType,
    DataprocessorDestinationStageType,
    ResourceOutputDetailLevel,
)

from ..edge_api import (
    DATA_PROCESSOR_API_V1,
    DataProcessorResourceKinds,
)


# TODO: @jiacju refactor this file since it's becoming too long
def check_dataprocessor_deployment(
    result: Dict[str, Any],
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_kinds: List[str] = None,
    resource_name: str = None,
) -> None:
    evaluate_funcs = {
        DataProcessorResourceKinds.INSTANCE: evaluate_instances,
        DataProcessorResourceKinds.PIPELINE: evaluate_pipelines,
        DataProcessorResourceKinds.DATASET: evaluate_datasets,
    }

    check_post_deployment(
        api_info=DATA_PROCESSOR_API_V1,
        check_name="enumerateDataProcessorApi",
        check_desc="Enumerate Data Processor API resources",
        result=result,
        resource_name=resource_name,
        evaluate_funcs=evaluate_funcs,
        as_list=as_list,
        detail_level=detail_level,
        resource_kinds=resource_kinds
    )


def evaluate_instances(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
) -> Dict[str, Any]:
    check_manager = CheckManager(check_name="evalInstances", check_desc="Evaluate Data processor instance")

    instance_namespace_conditions = ["len(instances)==1", "provisioningStatus"]

    target_instances = generate_target_resource_name(api_info=DATA_PROCESSOR_API_V1, resource_kind=DataProcessorResourceKinds.INSTANCE.value)

    all_instances = get_resources_by_name(
        api_info=DATA_PROCESSOR_API_V1,
        kind=DataProcessorResourceKinds.INSTANCE,
        resource_name=resource_name
    )

    if not all_instances:
        status = CheckTaskStatus.skipped.value if resource_name else CheckTaskStatus.error.value
        fetch_instances_error_text = f"Unable to fetch {DataProcessorResourceKinds.INSTANCE.value}s in any namespaces."
        check_manager.add_target(target_name=target_instances)
        check_manager.add_target_eval(
            target_name=target_instances,
            status=status,
            value=fetch_instances_error_text
        )
        check_manager.add_display(
            target_name=target_instances,
            display=Padding(fetch_instances_error_text, (0, 0, 0, 8))
        )
        return check_manager.as_dict(as_list)

    for (namespace, instances) in get_resources_grouped_by_namespace(all_instances):
        check_manager.add_target(target_name=target_instances, namespace=namespace, conditions=instance_namespace_conditions)
        check_manager.add_display(
            target_name=target_instances,
            namespace=namespace,
            display=Padding(
                f"Data processor instance in namespace {{[purple]{namespace}[/purple]}}",
                (0, 0, 0, 8)
            )
        )

        instances = list(instances)
        instances_count = len(instances)
        instances_count_text = "- Expecting [bright_blue]1[/bright_blue] instance resource. {}."

        if instances_count == 1:
            instances_count_text = instances_count_text.format(f"[green]Detected {instances_count}[/green]")
        else:
            instances_count_text = instances_count_text.format(f"[red]Detected {instances_count}[/red]")
            check_manager.set_target_status(
                target_name=target_instances,
                namespace=namespace,
                status=CheckTaskStatus.error.value
            )
        check_manager.add_display(
            target_name=target_instances,
            namespace=namespace,
            display=Padding(instances_count_text, (0, 0, 0, 8))
        )

        for i in instances:

            instance_name = i["metadata"]["name"]
            instance_provisionint_status = i["status"]["provisioningStatus"]
            instance_status = instance_provisionint_status["status"]

            target_instance_text = (
                f"- Instance {{[bright_blue]{instance_name}[/bright_blue]}} provisioning status {{{decorate_resource_status(instance_status)}}}."
            )
            check_manager.add_display(
                target_name=target_instances,
                namespace=namespace,
                display=Padding(target_instance_text, (0, 0, 0, 8))
            )

            instance_eval_value = {"provisioningStatus": instance_status}
            instance_eval_status = CheckTaskStatus.success.value

            if instance_status in [ProvisioningState.canceled.value, ProvisioningState.failed.value]:
                instance_eval_status = CheckTaskStatus.error.value
                error_message = instance_provisionint_status.get("error", {}).get("message", ERROR_NO_DETAIL)
                error_display_text = f"[red]Error: {error_message}[/red]"
                check_manager.add_display(
                    target_name=target_instances,
                    namespace=namespace,
                    display=Padding(error_display_text, (0, 0, 0, 10))
                )
            elif instance_status in [
                ProvisioningState.updating.value,
                ProvisioningState.provisioning.value,
                ProvisioningState.deleting.value,
                ProvisioningState.accepted.value
            ]:
                instance_eval_status = CheckTaskStatus.warning.value

            check_manager.add_target_eval(
                target_name=target_instances,
                namespace=namespace,
                status=instance_eval_status,
                value=instance_eval_value,
                resource_name=instance_name
            )

        if len(all_instances) > 0:
            check_manager.add_display(
                target_name=target_instances,
                namespace=namespace,
                display=Padding(
                    "\nRuntime Health",
                    (0, 0, 0, 8),
                ),
            )

            from ..support.dataprocessor import DATA_PROCESSOR_NAME_LABEL_V2, DATA_PROCESSOR_ONEOFF_LABEL

            for pod in [
                DATA_PROCESSOR_READER_WORKER_PREFIX,
                DATA_PROCESSOR_RUNNER_WORKER_PREFIX,
                DATA_PROCESSOR_REFDATA_STORE_PREFIX,
                DATA_PROCESSOR_OPERATOR,
            ]:
                evaluate_pod_health(
                    check_manager=check_manager,
                    target=target_instances,
                    pod=pod,
                    display_padding=12,
                    service_label=DATA_PROCESSOR_NAME_LABEL_V2,
                    namespace=namespace,
                    detail_level=detail_level,
                )

            # TODO: remove once the new label is stabled
            evaluate_pod_health(
                check_manager=check_manager,
                target=target_instances,
                pod=DATA_PROCESSOR_NATS_PREFIX,
                display_padding=12,
                service_label=DATA_PROCESSOR_ONEOFF_LABEL,
                namespace=namespace,
                detail_level=detail_level,
            )

    return check_manager.as_dict(as_list)


def evaluate_pipelines(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
) -> Dict[str, Any]:
    check_manager = CheckManager(check_name="evalPipelines", check_desc="Evaluate Data processor pipeline")

    target_pipelines = generate_target_resource_name(api_info=DATA_PROCESSOR_API_V1, resource_kind=DataProcessorResourceKinds.PIPELINE.value)
    pipeline_namespace_conditions = [
        "len(pipelines)>=1",
        "mode.enabled",
        "provisioningStatus",
        "sourceNodeCount == 1",
        "spec.input.partitionCount>=1",
        "format.type",
        "authentication.type",
        "destinationNodeCount==1"
    ]

    all_pipelines = get_resources_by_name(
        api_info=DATA_PROCESSOR_API_V1,
        kind=DataProcessorResourceKinds.PIPELINE,
        resource_name=resource_name
    )
    padding = 8

    if not all_pipelines:
        check_manager.add_target(target_name=target_pipelines)
        fetch_pipelines_error_text = f"Unable to fetch {DataProcessorResourceKinds.PIPELINE.value}s in any namespaces."
        check_manager.add_target_eval(
            target_name=target_pipelines,
            status=CheckTaskStatus.skipped.value,
            value=fetch_pipelines_error_text
        )
        check_manager.add_display(
            target_name=target_pipelines,
            display=Padding(fetch_pipelines_error_text, (0, 0, 0, padding))
        )
        return check_manager.as_dict(as_list)

    for (namespace, pipelines) in get_resources_grouped_by_namespace(all_pipelines):
        check_manager.add_target(target_name=target_pipelines, namespace=namespace, conditions=pipeline_namespace_conditions)
        check_manager.add_display(
            target_name=target_pipelines,
            namespace=namespace,
            display=Padding(
                f"Data processor pipeline in namespace {{[purple]{namespace}[/purple]}}",
                (0, 0, 0, 8)
            )
        )

        pipelines = list(pipelines)
        pipelines_count = len(pipelines)
        pipelines_count_text = "- Expecting [bright_blue]>=1[/bright_blue] pipeline resource per namespace. {}."

        if pipelines_count >= 1:
            pipelines_count_text = pipelines_count_text.format(f"[green]Detected {pipelines_count}[/green]")
        else:
            pipelines_count_text = pipelines_count_text.format(f"[red]Detected {pipelines_count}[/red]")
            check_manager.set_target_status(
                target_name=target_pipelines,
                namespace=namespace,
                status=CheckTaskStatus.error.value
            )
        check_manager.add_display(
            target_name=target_pipelines,
            namespace=namespace,
            display=Padding(pipelines_count_text, (0, 0, 0, padding))
        )

        for p in pipelines:
            pipeline_name = p["metadata"]["name"]
            pipeline_running_status = "running" if p["spec"]["enabled"] else "not running"

            pipeline_enabled_text = f"- Pipeline {{[bright_blue]{pipeline_name}[/bright_blue]}} is {{[bright_blue]{pipeline_running_status}[/bright_blue]}}."
            pipeline_eval_value = {"mode.enabled": pipeline_running_status}
            pipeline_eval_status = CheckTaskStatus.success.value

            if pipeline_running_status == "not running":
                pipieline_not_enabled_text = (
                    f"- Pipeline {{[bright_blue]{pipeline_name}[/bright_blue]}} is {{[yellow]not running[/yellow]}}."
                    "\n  [bright_white]Skipping pipeline evaluation[/bright_white]."
                )
                add_display_and_eval(
                    check_manager=check_manager,
                    target_name=target_pipelines,
                    display_text=pipieline_not_enabled_text,
                    eval_status=CheckTaskStatus.skipped.value,
                    eval_value=pipeline_eval_value,
                    resource_name=pipeline_name,
                    namespace=namespace
                )
                continue

            add_display_and_eval(
                check_manager=check_manager,
                target_name=target_pipelines,
                display_text=pipeline_enabled_text,
                eval_status=pipeline_eval_status,
                eval_value=pipeline_eval_value,
                resource_name=pipeline_name,
                namespace=namespace
            )

            pipeline_property_padding = padding + PADDING_SIZE

            # check provisioning status
            pipeline_provisioning_status = p["status"]["provisioningStatus"]
            pipeline_status = pipeline_provisioning_status["status"]
            status_display_text = f"- Provisioning status {{{decorate_resource_status(pipeline_status)}}}."

            pipeline_provisioningStatus_eval_value = {"provisioningStatus": pipeline_status}
            pipeline_provisioningStatus_eval_status = CheckTaskStatus.success.value

            error_display_text = ""
            if pipeline_status in [ProvisioningState.canceled.value, ProvisioningState.failed.value]:
                pipeline_provisioningStatus_eval_status = CheckTaskStatus.error.value
                error_message = pipeline_provisioning_status.get("error", {}).get("message", ERROR_NO_DETAIL)
                error_display_text = f"[red]Error: {error_message}[/red]"
            elif pipeline_status in [
                ProvisioningState.updating.value,
                ProvisioningState.provisioning.value,
                ProvisioningState.deleting.value,
                ProvisioningState.accepted.value
            ]:
                pipeline_provisioningStatus_eval_status = CheckTaskStatus.warning.value

            add_display_and_eval(
                check_manager=check_manager,
                target_name=target_pipelines,
                display_text=status_display_text,
                eval_status=pipeline_provisioningStatus_eval_status,
                eval_value=pipeline_provisioningStatus_eval_value,
                resource_name=pipeline_name,
                padding=(0, 0, 0, pipeline_property_padding),
                namespace=namespace
            )

            if error_display_text:
                check_manager.add_display(
                    target_name=target_pipelines,
                    namespace=namespace,
                    display=Padding(error_display_text, (0, 0, 0, pipeline_property_padding + PADDING_SIZE))
                )

            # pipeline source node
            _evaluate_source_node(
                pipeline_source_node=p["spec"]["input"],
                target_pipelines=target_pipelines,
                pipeline_name=pipeline_name,
                check_manager=check_manager,
                detail_level=detail_level,
                namespace=namespace,
                padding=pipeline_property_padding
            )

            # pipeline intermediate node
            pipeline_stages_node = p["spec"]["stages"]
            output_node: Tuple = ()
            for s in pipeline_stages_node:
                if "output" in pipeline_stages_node[s]["type"]:
                    output_node = (s, pipeline_stages_node[s])
                    break

            _evaluate_intermediate_nodes(
                output_node,
                pipeline_stages_node=pipeline_stages_node,
                target_pipelines=target_pipelines,
                check_manager=check_manager,
                detail_level=detail_level,
                namespace=namespace,
                padding=pipeline_property_padding
            )

            # pipeline destination node
            _evaluate_destination_node(
                output_node=output_node,
                target_pipelines=target_pipelines,
                pipeline_name=pipeline_name,
                check_manager=check_manager,
                detail_level=detail_level,
                namespace=namespace,
                padding=pipeline_property_padding
            )

    return check_manager.as_dict(as_list)


def evaluate_datasets(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
) -> Dict[str, Any]:
    check_manager = CheckManager(check_name="evalDatasets", check_desc="Evaluate Data processor dataset")

    target_datasets = generate_target_resource_name(api_info=DATA_PROCESSOR_API_V1, resource_kind=DataProcessorResourceKinds.DATASET.value)
    dataset_namespace_conditions = ["provisioningState"]
    padding = 8

    all_datasets = get_resources_by_name(
        api_info=DATA_PROCESSOR_API_V1,
        kind=DataProcessorResourceKinds.DATASET,
        resource_name=resource_name
    )

    if not all_datasets:
        check_manager.add_target(target_name=target_datasets)
        fetch_datasets_warn_text = f"Unable to fetch {DataProcessorResourceKinds.DATASET.value}s in any namespaces."
        add_display_and_eval(
            check_manager=check_manager,
            target_name=target_datasets,
            display_text=fetch_datasets_warn_text,
            eval_status=CheckTaskStatus.skipped.value,
            eval_value=fetch_datasets_warn_text
        )
        return check_manager.as_dict(as_list)

    for (namespace, datasets) in get_resources_grouped_by_namespace(all_datasets):
        check_manager.add_target(target_name=target_datasets, namespace=namespace, conditions=dataset_namespace_conditions)
        check_manager.add_display(
            target_name=target_datasets,
            namespace=namespace,
            display=Padding(
                f"Data processor dataset in namespace {{[purple]{namespace}[/purple]}}",
                (0, 0, 0, padding)
            )
        )

        datasets = list(datasets)
        datasets_count = len(datasets)

        datasets_count_text = "- Checking dataset resource in namespace. {}."
        dataset_eval_status = CheckTaskStatus.success.value

        if datasets_count > 0:
            datasets_count_text = datasets_count_text.format(f"[green]Detected {datasets_count}[/green]")
        else:
            check_manager.add_target_eval(
                target_name=target_datasets,
                namespace=namespace,
                status=CheckTaskStatus.skipped.value
            )
            no_dataset_text = (
                "Datasets [yellow]not[/yellow] detected."
                "\n[bright_white]Skipping dataset evaluation[/bright_white]."
            )
            check_manager.add_display(
                target_name=target_datasets,
                namespace=namespace,
                display=Padding(no_dataset_text, (0, 0, 0, padding))
            )
            return check_manager.as_dict(as_list)

        check_manager.add_display(
            target_name=target_datasets,
            namespace=namespace,
            display=Padding(datasets_count_text, (0, 0, 0, padding))
        )

        for d in datasets:
            dataset_name = d["metadata"]["name"]
            dataset_status = d["status"]["provisioningStatus"]["status"]
            property_padding = padding + PADDING_SIZE

            status_display_text = f"Provisiong Status: {{{decorate_resource_status(dataset_status)}}}"

            target_dataset_text = (
                f"- Dataset resource {{[bright_blue]{dataset_name}[/bright_blue]}}"
            )
            check_manager.add_display(
                target_name=target_datasets,
                namespace=namespace,
                display=Padding(target_dataset_text, (0, 0, 0, padding))
            )
            check_manager.add_display(
                target_name=target_datasets,
                namespace=namespace,
                display=Padding(status_display_text, (0, 0, 0, property_padding))
            )

            dataset_eval_value = {"provisioningState": dataset_status}
            dataset_eval_status = CheckTaskStatus.success.value

            if dataset_status in [ProvisioningState.canceled.value, ProvisioningState.failed.value]:
                dataset_eval_status = CheckTaskStatus.error.value
                error_message = d["status"]["provisioningStatus"]["error"]["message"]
                error_display_text = f"[red]Error: {error_message}[/red]"
                check_manager.add_display(
                    target_name=target_datasets,
                    namespace=namespace,
                    display=Padding(error_display_text, (0, 0, 0, property_padding + PADDING_SIZE)))
            elif dataset_status in [
                ProvisioningState.updating.value,
                ProvisioningState.provisioning.value,
                ProvisioningState.deleting.value,
                ProvisioningState.accepted.value
            ]:
                dataset_eval_status = CheckTaskStatus.warning.value

            check_manager.add_target_eval(
                target_name=target_datasets,
                status=dataset_eval_status,
                value=dataset_eval_value,
                resource_name=dataset_name,
                namespace=namespace
            )

            if detail_level != ResourceOutputDetailLevel.summary.value:
                dataset_spec: dict = d["spec"]
                dataset_payload = dataset_spec.get("payload", "")
                if dataset_payload:
                    check_manager.add_display(
                        target_name=target_datasets,
                        namespace=namespace,
                        display=Padding(
                            f"Payload path: [cyan]{dataset_payload}[/cyan]",
                            (0, 0, 0, property_padding),
                        ),
                    )

                dataset_timestamp = dataset_spec.get("timestamp", "")
                if dataset_timestamp:
                    check_manager.add_display(
                        target_name=target_datasets,
                        namespace=namespace,
                        display=Padding(
                            f"Timestamp: [cyan]{dataset_timestamp}[/cyan]",
                            (0, 0, 0, property_padding),
                        ),
                    )

                dataset_ttl = dataset_spec.get("ttl", "")
                if dataset_ttl:
                    check_manager.add_display(
                        target_name=target_datasets,
                        namespace=namespace,
                        display=Padding(
                            f"Expiration time: [cyan]{dataset_ttl}[/cyan]",
                            (0, 0, 0, property_padding),
                        ),
                    )

            if detail_level == ResourceOutputDetailLevel.verbose.value and dataset_spec.get("keys"):
                process_resource_property_by_type(
                    check_manager=check_manager,
                    target_name=target_datasets,
                    properties=d["spec"]["keys"],
                    display_name="Dataset configuration key",
                    padding=(0, 0, 0, property_padding),
                    namespace=namespace
                )

    return check_manager.as_dict(as_list)


def _process_stage_properties(
    check_manager: CheckManager,
    detail_level: int,
    target_name: str,
    stage: Dict[str, Any],
    stage_properties: Dict[str, Any],
    padding: tuple,
    namespace: str
) -> None:
    stage_type = stage["type"]

    for stage_value, properties in stage_properties.items():
        if stage_value in stage_type:
            process_resource_properties(
                check_manager=check_manager,
                detail_level=detail_level,
                target_name=target_name,
                prop_value=stage,
                properties=properties,
                padding=padding,
                namespace=namespace
            )


def _evaluate_source_node(
    pipeline_source_node: Dict[str, Any],
    target_pipelines: str,
    pipeline_name: str,
    check_manager: CheckManager,
    namespace: str,
    padding: int,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> None:
    # check data source node count
    pipeline_source_node_count = 1 if pipeline_source_node else 0
    source_count_display_text = f"- Expecting [bright_blue]1[/bright_blue] data source node. [green]Detected {pipeline_source_node_count}[/green]."

    pipeline_source_count_eval_value = {"sourceNodeCount": pipeline_source_node_count}
    pipeline_source_count_eval_status = CheckTaskStatus.success.value

    if pipeline_source_node_count != 1:
        pipeline_source_count_eval_status = CheckTaskStatus.error.value
        source_count_display_text = f"- Expecting [bright_blue]1[/bright_blue] data source node. {{[red]Detected {pipeline_source_node_count}[/red]}}."
    add_display_and_eval(
        check_manager=check_manager,
        target_name=target_pipelines,
        display_text=source_count_display_text,
        eval_status=pipeline_source_count_eval_status,
        eval_value=pipeline_source_count_eval_value,
        resource_name=pipeline_name,
        padding=(0, 0, 0, padding),
        namespace=namespace
    )

    property_padding = padding + PADDING_SIZE

    # get data source type
    stage_type = pipeline_source_node["type"]

    stage_display_text = f"Stage type: {{[cyan]{stage_type}[/cyan]}}"
    check_manager.add_display(
        target_name=target_pipelines,
        namespace=namespace,
        display=Padding(stage_display_text, (0, 0, 0, property_padding))
    )

    # check specific required properties
    _evaluate_required_properties(
        pipeline_node=pipeline_source_node,
        stage_name="input",
        stage_type=stage_type,
        stage_type_enums=DataSourceStageType,
        target_name=target_pipelines,
        resource_name=pipeline_name,
        required_properties=DATA_PROCESSOR_SOURCE_REQUIRED_PROPERTIES,
        check_manager=check_manager,
        namespace=namespace,
        detail_level=detail_level,
        padding=property_padding
    )

    # check common properties
    # check data source partition
    pipeline_source_node_partition_count = pipeline_source_node["partitionCount"]
    source_partition_count_display_text = "Expecting the number of partition [bright_blue]>=1[/bright_blue] and [bright_blue]<=100[/bright_blue]. {}."

    pipeline_source_partition_eval_value = {"spec.input.partitionCount": pipeline_source_node_partition_count}
    pipeline_source_partition_eval_status = CheckTaskStatus.success.value

    if pipeline_source_node_partition_count < 1 or pipeline_source_node_partition_count > 100:
        pipeline_source_partition_eval_status = CheckTaskStatus.error.value
        source_partition_count_display_text = source_partition_count_display_text.format(f"[red]Detected {pipeline_source_node_partition_count}[/red]")
    else:
        source_partition_count_display_text = source_partition_count_display_text.format(f"[green]Detected {pipeline_source_node_partition_count}[/green]")
    check_manager.add_display(
        target_name=target_pipelines,
        namespace=namespace,
        display=Padding(source_partition_count_display_text, (0, 0, 0, property_padding))
    )

    if detail_level != ResourceOutputDetailLevel.summary.value:
        pipeline_source_node_partition_strategy = pipeline_source_node["partitionStrategy"]["type"]
        source_partition_strategy_display_text = f"Partitioning strategy type: [cyan]{pipeline_source_node_partition_strategy}[/cyan]."
        check_manager.add_display(
            target_name=target_pipelines,
            namespace=namespace,
            display=Padding(source_partition_strategy_display_text, (0, 0, 0, property_padding))
        )

    check_manager.add_target_eval(
        target_name=target_pipelines,
        namespace=namespace,
        status=pipeline_source_partition_eval_status,
        value=pipeline_source_partition_eval_value,
        resource_name=pipeline_name
    )

    _evaluate_common_stage_properties(
        check_manager=check_manager,
        detail_level=detail_level,
        stage_name="input",
        stage_type=stage_type,
        stage_type_enums=DataSourceStageType,
        target_name=target_pipelines,
        pipeline_node=pipeline_source_node,
        padding=property_padding,
        namespace=namespace
    )

    if detail_level != ResourceOutputDetailLevel.summary.value:
        _process_stage_properties(
            check_manager,
            detail_level,
            target_name=target_pipelines,
            stage=pipeline_source_node,
            stage_properties=DATA_PROCESSOR_SOURCE_DISPLAY_PROPERTIES,
            padding=(0, 0, 0, property_padding),
            namespace=namespace
        )


def _evaluate_intermediate_nodes(
    output_node: Tuple,
    pipeline_stages_node: Dict[str, Any],
    target_pipelines: str,
    check_manager: CheckManager,
    namespace: str,
    padding: int,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> None:

    # number of intermediate stages should be total len(stages) - len(output stage)
    pipeline_intermediate_stages_node = pipeline_stages_node.copy()
    pipeline_intermediate_stages_node_count = len(pipeline_stages_node)
    if output_node:
        pipeline_intermediate_stages_node.pop(output_node[0])
        pipeline_intermediate_stages_node_count -= 1
    stage_count_display_text = f"- Pipeline contains [bright_blue]{pipeline_intermediate_stages_node_count}[/bright_blue] intermediate stages."

    check_manager.add_display(
        target_name=target_pipelines,
        namespace=namespace,
        display=Padding(stage_count_display_text, (0, 0, 0, padding))
    )

    property_padding = padding + PADDING_SIZE

    for stage_name in pipeline_intermediate_stages_node:
        stage_type = pipeline_intermediate_stages_node[stage_name]["type"]
        stage_display_text = f"- Stage resource {{[bright_blue]{stage_name}[/bright_blue]}} of type {{[bright_blue]{stage_type}[/bright_blue]}}"
        check_manager.add_display(
            target_name=target_pipelines,
            namespace=namespace,
            display=Padding(stage_display_text, (0, 0, 0, property_padding))
        )

        stage_enum = _get_stage_enum(stage_type=stage_type, stage_type_enums=DataProcessorStageType)

        _evaluate_required_properties(
            pipeline_node=pipeline_intermediate_stages_node[stage_name],
            stage_name=stage_name,
            stage_type=stage_type,
            stage_type_enums=DataProcessorStageType,
            target_name=target_pipelines,
            resource_name=stage_name,
            required_properties=DATA_PROCESSOR_INTERMEDIATE_REQUIRED_PROPERTIES,
            check_manager=check_manager,
            namespace=namespace,
            detail_level=detail_level,
            padding=property_padding + PADDING_SIZE
        )

        if stage_enum in [
            DataProcessorStageType.grpc.value,
            DataProcessorStageType.http.value,
        ]:
            _evaluate_authentication(
                pipeline_node=pipeline_intermediate_stages_node[stage_name],
                target_pipelines=target_pipelines,
                pipeline_name=stage_name,
                check_manager=check_manager,
                namespace=namespace,
                stage_name=stage_name,
                padding=property_padding + PADDING_SIZE,
                detail_level=detail_level
            )

        if detail_level != ResourceOutputDetailLevel.summary.value:
            _process_stage_properties(
                check_manager,
                detail_level,
                target_name=target_pipelines,
                stage=pipeline_intermediate_stages_node[stage_name],
                stage_properties=DATA_PROCESSOR_INTERMEDIATE_STAGE_PROPERTIES,
                padding=(0, 0, 0, property_padding + PADDING_SIZE),
                namespace=namespace
            )


def _evaluate_destination_node(
    output_node: Dict[str, Any],
    target_pipelines: str,
    pipeline_name: str,
    check_manager: CheckManager,
    namespace: str,
    padding: int,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> None:
    pipeline_destination_node_count = 1 if output_node else 0
    destination_count_display_text = f"- Expecting [bright_blue]1[/bright_blue] data destination node. [green]Detected {pipeline_destination_node_count}[/green]."

    pipeline_destination_eval_value = {"destinationNodeCount": pipeline_destination_node_count}
    pipeline_destination_eval_status = CheckTaskStatus.success.value

    if pipeline_destination_node_count != 1:
        pipeline_destination_eval_status = CheckTaskStatus.error.value
    add_display_and_eval(
        check_manager=check_manager,
        target_name=target_pipelines,
        display_text=destination_count_display_text,
        eval_status=pipeline_destination_eval_status,
        eval_value=pipeline_destination_eval_value,
        resource_name=pipeline_name,
        padding=(0, 0, 0, padding),
        namespace=namespace
    )

    if output_node:
        (name, node_properties) = output_node
        property_padding = padding + PADDING_SIZE

        # get data source type
        stage_type = node_properties["type"]

        stage_display_text = f"Stage type: {{[cyan]{stage_type}[/cyan]}}"
        check_manager.add_display(
            target_name=target_pipelines,
            namespace=namespace,
            display=Padding(stage_display_text, (0, 0, 0, property_padding))
        )

        _evaluate_required_properties(
            pipeline_node=node_properties,
            stage_name=name,
            stage_type=stage_type,
            stage_type_enums=DataprocessorDestinationStageType,
            target_name=target_pipelines,
            resource_name=pipeline_name,
            required_properties=DATA_PROCESSOR_DESTINATION_REQUIRED_PROPERTIES,
            check_manager=check_manager,
            namespace=namespace,
            detail_level=detail_level,
            padding=property_padding
        )

        _evaluate_common_stage_properties(
            check_manager=check_manager,
            detail_level=detail_level,
            stage_name=name,
            stage_type=stage_type,
            stage_type_enums=DataprocessorDestinationStageType,
            target_name=target_pipelines,
            pipeline_node=node_properties,
            padding=property_padding,
            namespace=namespace
        )

        if detail_level != ResourceOutputDetailLevel.summary.value:
            _process_stage_properties(
                check_manager,
                detail_level,
                target_name=target_pipelines,
                stage=node_properties,
                stage_properties=DATA_PROCESSOR_DESTINATION_STAGE_PROPERTIES,
                padding=(0, 0, 0, property_padding),
                namespace=namespace
            )


def _evaluate_common_stage_properties(
    check_manager: CheckManager,
    detail_level: int,
    stage_name: str,
    stage_type: str,
    stage_type_enums: ListableEnum,
    target_name: str,
    pipeline_node: Dict[str, Any],
    padding: int,
    namespace: str
) -> None:
    stage_enum = _get_stage_enum(stage_type=stage_type, stage_type_enums=stage_type_enums)
    # check format

    if stage_enum not in [
        DataprocessorDestinationStageType.data_explorer.value,
        DataprocessorDestinationStageType.fabric.value,
        DataprocessorDestinationStageType.grpc.value,
        DataprocessorDestinationStageType.http.value,
        DataprocessorDestinationStageType.reference_data.value,
    ]:
        pipeline_node_format = pipeline_node.get("format", {})
        format_type = pipeline_node_format.get("type", "")
        format_type_status = CheckTaskStatus.success.value
        format_type_display_text = f"Format: [cyan]{pipeline_node_format}[/cyan] [green]detected[/green]."
        if not format_type:
            format_type_status = CheckTaskStatus.error.value
            format_type_display_text = "Format: type [red]not detected[/red]."

        check_manager.add_display(
            target_name=target_name,
            namespace=namespace,
            display=Padding(format_type_display_text, (0, 0, 0, padding))
        )

        check_manager.add_target_eval(
            target_name=target_name,
            namespace=namespace,
            status=format_type_status,
            value={f"{stage_name}.format.type": format_type},
            resource_name=target_name
        )

    if stage_enum not in [
        DataprocessorDestinationStageType.file.value,
        DataprocessorDestinationStageType.reference_data.value,
    ]:
        _evaluate_authentication(
            pipeline_node=pipeline_node,
            target_pipelines=target_name,
            pipeline_name=target_name,
            check_manager=check_manager,
            namespace=namespace,
            padding=padding,
            stage_name=stage_name,
            detail_level=detail_level
        )


def _evaluate_authentication(
    pipeline_node: Dict[str, Any],
    target_pipelines: str,
    pipeline_name: str,
    check_manager: CheckManager,
    namespace: str,
    padding: int,
    stage_name: str,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> None:
    def add_verbose_display(
        check_manager: CheckManager,
        target_pipelines: str,
        namespace: str,
        padding: int,
        details: int = ResourceOutputDetailLevel.summary.value,
    ):
        for detail in details:
            if detail["value"]:
                label: str = detail["label"]
                if label.endswith("Password") or label.endswith("Secret"):
                    label += f" {DATA_PROCESSOR_AUTHENTICATION_SECRET_REF}"

                check_manager.add_display(
                    target_name=target_pipelines,
                    namespace=namespace,
                    display=Padding(f"{label}: [cyan]{detail['value']}[/cyan]", (0, 0, 0, padding + PADDING_SIZE))
                )

    auth_info = pipeline_node.get("authentication", {})
    auth_type = auth_info.get("type", "")

    if detail_level > ResourceOutputDetailLevel.summary.value:
        authentication_display_text = f"Authentication type: [cyan]{auth_type}[/cyan]"
        check_manager.add_display(
            target_name=target_pipelines,
            namespace=namespace,
            display=Padding(authentication_display_text, (0, 0, 0, padding))
        )

    authentication_status = CheckTaskStatus.success.value
    authentication_error_text = ""
    details_to_display = []

    if auth_type in DataprocessorAuthenticationType.list():
        required_fields = DATA_PROCESSOR_AUTHENTICATION_REQUIRED_PROPERTIES[auth_type]

        missing_fields = [field for field in required_fields if not auth_info.get(field)]
        if missing_fields:
            authentication_error_text = ", ".join(missing_fields) + " [red]not detected[/red]."
            authentication_status = CheckTaskStatus.error.value

        if detail_level == ResourceOutputDetailLevel.verbose.value:
            details_to_display = [{"label": field.capitalize(), "value": auth_info.get(field)} for field in required_fields]

    add_verbose_display(check_manager, target_pipelines, namespace, padding, details_to_display)

    if authentication_error_text:
        check_manager.add_display(
            target_name=target_pipelines,
            namespace=namespace,
            display=Padding(authentication_error_text, (0, 0, 0, padding + PADDING_SIZE))
        )

    check_manager.add_target_eval(
        target_name=target_pipelines,
        namespace=namespace,
        status=authentication_status,
        value={f"{stage_name}.authentication.type": auth_type},
        resource_name=pipeline_name
    )


def _evaluate_required_properties(
    check_manager: CheckManager,
    target_name: str,
    namespace: str,
    stage_name: str,
    stage_type: str,
    stage_type_enums: ListableEnum,
    required_properties: List[str],
    pipeline_node: Dict[str, Any],
    resource_name: str,
    padding: int,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
):
    # find the matching enum for stage_type, which should start with the enum value
    stage_type_value = _get_stage_enum(stage_type=stage_type, stage_type_enums=stage_type_enums)
    stage_required_properties = required_properties.get(stage_type_value, [])
    for prop in stage_required_properties:
        prop_value = pipeline_node.get(prop, "")
        prop_status = CheckTaskStatus.success.value
        # capitalize the first letter of the property
        prop_label = prop.capitalize()
        prop_display_text = f"{prop_label}: [cyan]{prop_value}[/cyan] [green]detected[/green]."
        check_manager.add_target_conditions(
            target_name=target_name,
            namespace=namespace,
            conditions=[f"spec.{stage_name}.{prop}"]
        )

        if not prop_value:
            prop_status = CheckTaskStatus.error.value
            prop_display_text = f"{prop} [red]not detected[/red]."

        if detail_level != ResourceOutputDetailLevel.summary.value:
            check_manager.add_display(
                target_name=target_name,
                namespace=namespace,
                display=Padding(prop_display_text, (0, 0, 0, padding))
            )

        check_manager.add_target_eval(
            target_name=target_name,
            namespace=namespace,
            status=prop_status,
            value={f"spec.{stage_name}.{prop}": prop_value},
            resource_name=resource_name
        )


def _get_stage_enum(stage_type: str, stage_type_enums: ListableEnum) -> str:
    return next((e for e in stage_type_enums.list() if stage_type.startswith(e)), None)
