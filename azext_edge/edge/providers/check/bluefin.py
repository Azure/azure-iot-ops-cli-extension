# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from typing import Any, List, Optional, Tuple
from azext_edge.edge.providers.check.base import (
    CheckManager,
    decorate_resource_status,
    check_post_deployment,
    check_pre_deployment,
    evaluate_pod_health,
    process_as_list,
)

from rich.padding import Padding

from ...common import (
    CheckTaskStatus,
    ProvisioningState,
)

from .common import (
    BLUEFIN_DESTINATION_STAGE_PROPERTIES,
    BLUEFIN_INTERMEDIATE_STAGE_PROPERTIES,
    BLUEFIN_NATS_PREFIX,
    BLUEFIN_OPERATOR_CONTROLLER_MANAGER,
    BLUEFIN_READER_WORKER_PREFIX,
    BLUEFIN_REFDATA_STORE_PREFIX,
    BLUEFIN_RUNNER_WORKER_PREFIX,
    ResourceOutputDetailLevel,
)

from ...providers.edge_api import (
    BLUEFIN_API_V1,
    BluefinResourceKinds,
)


def check_bluefin_deployment(
    detail_level: Optional[str] = ResourceOutputDetailLevel.summary.value,
    namespace: Optional[str] = None,
    pre_deployment: bool = True,
    post_deployment: bool = True,
    as_list: bool = False,
    resource_kinds: List[str] = None,
    result: dict = None,
):
    if pre_deployment:
        check_pre_deployment(result, as_list)

    if post_deployment:
        if not namespace:
            from ..base import DEFAULT_NAMESPACE

            namespace = DEFAULT_NAMESPACE
        result["postDeployment"] = []

        # check post deployment according to edge_service type
        check_bluefin_post_deployment(detail_level=detail_level, namespace=namespace, result=result, as_list=as_list, resource_kinds=resource_kinds)

    if not as_list:
        return result

    process_as_list(result=result, namespace=namespace)


def check_bluefin_post_deployment(
    namespace: str,
    result: dict,
    as_list: bool = False,
    detail_level: Optional[str] = ResourceOutputDetailLevel.summary.value,
    resource_kinds: List[str] = None
):
    evaluate_funcs = {
        BluefinResourceKinds.INSTANCE: evaluate_instances,
        BluefinResourceKinds.PIPELINE: evaluate_pipelines,
        BluefinResourceKinds.DATASET: evaluate_datasets,
    }

    return check_post_deployment(
        api_info=BLUEFIN_API_V1,
        check_name="enumerateBluefinApi",
        check_desc="Enumerate Bluefin API resources",
        namespace=namespace,
        result=result,
        resource_kinds_enum=BluefinResourceKinds,
        evaluate_funcs=evaluate_funcs,
        as_list=as_list,
        detail_level=detail_level,
        resource_kinds=resource_kinds
    )


def evaluate_instances(
    namespace: str,
    as_list: bool = False,
    detail_level: Optional[str] = ResourceOutputDetailLevel.summary.value,
):
    check_manager = CheckManager(check_name="evalInstances", check_desc="Evaluate Bluefin instance", namespace=namespace)

    target_instances = "instances.bluefin.az-bluefin.com"
    instance_conditions = ["len(instances)==1", "provisioningState"]
    check_manager.add_target(target_name=target_instances, conditions=instance_conditions)

    instance_list: dict = BLUEFIN_API_V1.get_resources(BluefinResourceKinds.INSTANCE, namespace=namespace)
    if not instance_list:
        fetch_instances_error_text = f"Unable to fetch namespace {BluefinResourceKinds.INSTANCE.value}s."
        check_manager.add_target_eval(
            target_name=target_instances, status=CheckTaskStatus.error.value, value=fetch_instances_error_text
        )
        check_manager.add_display(target_name=target_instances, display=Padding(fetch_instances_error_text, (0, 0, 0, 8)))
        return check_manager.as_dict(as_list)

    instances: List[dict] = instance_list.get("items", [])
    instances_count = len(instances)
    instances_count_text = "- Expecting [bright_blue]1[/bright_blue] instance resource per namespace. {}."

    if instances_count == 1:
        instances_count_text = instances_count_text.format(f"[green]Detected {instances_count}[/green]")
    else:
        instances_count_text = instances_count_text.format(f"[red]Detected {instances_count}[/red]")
        check_manager.set_target_status(target_name=target_instances, status=CheckTaskStatus.error.value)
    check_manager.add_display(target_name=target_instances, display=Padding(instances_count_text, (0, 0, 0, 8)))

    for i in instances:

        instance_name = i["metadata"]["name"]
        instance_status = i["status"]["provisioningStatus"]["status"]

        target_instance_text = (
            f"\n- Instance {{[bright_blue]{instance_name}[/bright_blue]}} provisioning status {{{decorate_resource_status(instance_status)}}}."
        )
        check_manager.add_display(target_name=target_instances, display=Padding(target_instance_text, (0, 0, 0, 8)))

        instance_eval_value = {"provisioningState": instance_status}
        instance_eval_status = CheckTaskStatus.success.value

        if instance_status in [ProvisioningState.canceled.value, ProvisioningState.failed.value]:
            instance_eval_status = CheckTaskStatus.error.value
            error_message = i["status"]["provisioningStatus"]["error"]["message"]
            error_display_text = f"[red]Error: {error_message}[/red]"
            check_manager.add_display(target_name=target_instances, display=Padding(error_display_text, (0, 0, 0, 10)))
        elif instance_status in [
            ProvisioningState.updating.value,
            ProvisioningState.provisioning.value,
            ProvisioningState.deleting.value,
            ProvisioningState.accepted.value
        ]:
            instance_eval_status = CheckTaskStatus.warning.value

        check_manager.add_target_eval(
            target_name=target_instances, status=instance_eval_status, value=instance_eval_value, resource_name=instance_name
        )

    if instances_count > 0:
        check_manager.add_display(
            target_name=target_instances,
            display=Padding(
                "\nRuntime Health",
                (0, 0, 0, 8),
            ),
        )

        from ..support.bluefin import BLUEFIN_APP_LABEL

        evaluate_pod_health(
            check_manager=check_manager,
            namespace=namespace,
            pod=BLUEFIN_READER_WORKER_PREFIX,
            display_padding=12,
            service_label=BLUEFIN_APP_LABEL
        )
        evaluate_pod_health(
            check_manager=check_manager,
            namespace=namespace,
            pod=BLUEFIN_RUNNER_WORKER_PREFIX,
            display_padding=12,
            service_label=BLUEFIN_APP_LABEL
        )
        evaluate_pod_health(
            check_manager=check_manager,
            namespace=namespace,
            pod=BLUEFIN_REFDATA_STORE_PREFIX,
            display_padding=12,
            service_label=BLUEFIN_APP_LABEL
        )
        evaluate_pod_health(
            check_manager=check_manager,
            namespace=namespace,
            pod=BLUEFIN_NATS_PREFIX,
            display_padding=12,
            service_label=BLUEFIN_APP_LABEL
        )
        evaluate_pod_health(
            check_manager=check_manager,
            namespace=namespace,
            pod=BLUEFIN_OPERATOR_CONTROLLER_MANAGER,
            display_padding=12,
            service_label=BLUEFIN_APP_LABEL
        )

    return check_manager.as_dict(as_list)


def evaluate_pipelines(
    namespace: str,
    as_list: bool = False,
    detail_level: Optional[str] = ResourceOutputDetailLevel.summary.value,
):
    check_manager = CheckManager(check_name="evalPipelines", check_desc="Evaluate Bluefin pipeline", namespace=namespace)

    target_pipelines = "pipelines.bluefin.az-bluefin.com"
    pipeline_conditions = ["len(pipelines)>=1",
                           "mode.enabled",
                           "provisioningStatus",
                           "sourceNodeCount == 1",
                           "len(spec.input.topics)>=1",
                           "spec.input.partitionCount>=1",
                           "destinationNodeCount==1"]
    check_manager.add_target(target_name=target_pipelines, conditions=pipeline_conditions)

    pipeline_list: dict = BLUEFIN_API_V1.get_resources(BluefinResourceKinds.PIPELINE, namespace=namespace)
    if not pipeline_list:
        fetch_pipelines_error_text = f"Unable to fetch namespace {BluefinResourceKinds.PIPELINE.value}s."
        add_display_and_eval(check_manager, target_pipelines, fetch_pipelines_error_text, CheckTaskStatus.error.value, fetch_pipelines_error_text)
        return check_manager.as_dict(as_list)

    pipelines: List[dict] = pipeline_list.get("items", [])
    pipelines_count = len(pipelines)
    pipelines_count_text = "- Expecting [bright_blue]>=1[/bright_blue] pipeline resource per namespace. {}."
    pipeline_eval_status = CheckTaskStatus.success.value

    if pipelines_count >= 1:
        pipelines_count_text = pipelines_count_text.format(f"[green]Detected {pipelines_count}[/green]")
    else:
        pipelines_count_text = pipelines_count_text.format(f"[red]Detected {pipelines_count}[/red]")
        check_manager.set_target_status(target_name=target_pipelines, status=CheckTaskStatus.error.value)
    check_manager.add_display(target_name=target_pipelines, display=Padding(pipelines_count_text, (0, 0, 0, 8)))

    for p in pipelines:
        pipeline_name = p["metadata"]["name"]
        pipeline_running_status = "running" if p["spec"]["enabled"] else "not running"

        pipeline_enabled_text = f"\n- Pipeline {{[bright_blue]{pipeline_name}[/bright_blue]}} is {{[bright_blue]{pipeline_running_status}[/bright_blue]}}."
        pipeline_eval_value = {"mode.enabled": pipeline_running_status}
        pipeline_eval_status = CheckTaskStatus.success.value

        if pipeline_running_status == "not running":
            pipieline_not_enabled_text = (
                f"\n- Pipeline {{[bright_blue]{pipeline_name}[/bright_blue]}} is {{[yellow]not running[/yellow]}}."
                "\n  [bright_white]Skipping pipeline evaluation[/bright_white]."
            )
            add_display_and_eval(check_manager, target_pipelines, pipieline_not_enabled_text, CheckTaskStatus.skipped.value, pipeline_eval_value, pipeline_name)
            continue

        add_display_and_eval(check_manager, target_pipelines, pipeline_enabled_text, pipeline_eval_status, pipeline_eval_value, pipeline_name)

        # check provisioning status
        pipeline_status = p["status"]["provisioningStatus"]["status"]
        status_display_text = f"- Provisioning status {{{decorate_resource_status(pipeline_status)}}}."

        pipeline_provisioningStatus_eval_value = {"provisioningStatus": pipeline_status}
        pipeline_provisioningStatus_eval_status = CheckTaskStatus.success.value

        error_display_text = ""
        if pipeline_status in [ProvisioningState.canceled.value, ProvisioningState.failed.value]:
            pipeline_provisioningStatus_eval_status = CheckTaskStatus.error.value
            error_message = p["status"]["provisioningStatus"]["error"]["message"]
            error_display_text = f"[red]Error: {error_message}[/red]"
        elif pipeline_status in [
            ProvisioningState.updating.value,
            ProvisioningState.provisioning.value,
            ProvisioningState.deleting.value,
            ProvisioningState.accepted.value
        ]:
            pipeline_provisioningStatus_eval_status = CheckTaskStatus.warning.value

        add_display_and_eval(check_manager, target_pipelines, status_display_text, pipeline_provisioningStatus_eval_status, pipeline_provisioningStatus_eval_value, pipeline_name, (0, 0, 0, 12))

        if error_display_text:
            check_manager.add_display(target_name=target_pipelines, display=Padding(error_display_text, (0, 0, 0, 14)))

        # pipeline source node
        _evaluate_source_node(
            pipeline_source_node=p["spec"]["input"],
            target_pipelines=target_pipelines,
            pipeline_name=pipeline_name,
            check_manager=check_manager,
            detail_level=detail_level
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
            detail_level=detail_level
        )

        # pipeline destination node
        _evaluate_destination_node(
            output_node=output_node,
            target_pipelines=target_pipelines,
            pipeline_name=pipeline_name,
            check_manager=check_manager,
            detail_level=detail_level
        )

    return check_manager.as_dict(as_list)


def evaluate_datasets(
    namespace: str,
    as_list: bool = False,
    detail_level: Optional[str] = ResourceOutputDetailLevel.summary.value,
):
    check_manager = CheckManager(check_name="evalDatasets", check_desc="Evaluate Bluefin dataset", namespace=namespace)

    target_datasets = "datasets.bluefin.az-bluefin.com"
    dataset_conditions = ["provisioningState"]
    check_manager.add_target(target_name=target_datasets, conditions=dataset_conditions)

    dataset_list: dict = BLUEFIN_API_V1.get_resources(BluefinResourceKinds.DATASET, namespace=namespace)
    datasets: List[dict] = dataset_list.get("items", [])
    datasets_count = len(datasets)

    datasets_count_text = "- Checking dataset resource in namespace. {}."
    dataset_eval_status = CheckTaskStatus.success.value

    if datasets_count > 0:
        datasets_count_text = datasets_count_text.format(f"[green]Detected {datasets_count}[/green]")
    else:
        check_manager.add_target_eval(target_name=target_datasets, status=CheckTaskStatus.skipped.value)
        no_dataset_text = (
            "Datasets [yellow]not[/yellow] detected."
            "\n[bright_white]Skipping dataset evaluation[/bright_white]."
        )
        check_manager.add_display(target_name=target_datasets, display=Padding(no_dataset_text, (0, 0, 0, 8)))
        return check_manager.as_dict(as_list)
    check_manager.add_display(target_name=target_datasets, display=Padding(datasets_count_text, (0, 0, 0, 8)))

    for d in datasets:
        dataset_name = d["metadata"]["name"]
        dataset_status = d["status"]["provisioningStatus"]["status"]

        status_display_text = f"Provisiong Status: {{{decorate_resource_status(dataset_status)}}}"

        target_dataset_text = (
            f"\n- Dataset resource {{[bright_blue]{dataset_name}[/bright_blue]}}"
        )
        check_manager.add_display(target_name=target_datasets, display=Padding(target_dataset_text, (0, 0, 0, 8)))
        check_manager.add_display(target_name=target_datasets, display=Padding(status_display_text, (0, 0, 0, 12)))

        dataset_eval_value = {"provisioningState": dataset_status}
        dataset_eval_status = CheckTaskStatus.success.value

        if dataset_status in [ProvisioningState.canceled.value, ProvisioningState.failed.value]:
            dataset_eval_status = CheckTaskStatus.error.value
            error_message = d["status"]["provisioningStatus"]["error"]["message"]
            error_display_text = f"[red]Error: {error_message}[/red]"
            check_manager.add_display(target_name=target_datasets, display=Padding(error_display_text, (0, 0, 0, 14)))
        elif dataset_status in [
            ProvisioningState.updating.value,
            ProvisioningState.provisioning.value,
            ProvisioningState.deleting.value,
            ProvisioningState.accepted.value
        ]:
            dataset_eval_status = CheckTaskStatus.warning.value

        check_manager.add_target_eval(
            target_name=target_datasets, status=dataset_eval_status, value=dataset_eval_value, resource_name=dataset_name
        )

        if detail_level != ResourceOutputDetailLevel.summary.value:
            dataset_spec: dict = d["spec"]
            dataset_payload = dataset_spec.get("payload", "")
            if dataset_payload:
                check_manager.add_display(
                    target_name=target_datasets,
                    display=Padding(
                        f"Payload path: [cyan]{dataset_payload}[/cyan]",
                        (0, 0, 0, 12),
                    ),
                )

            dataset_timestamp = dataset_spec.get("timestamp", "")
            if dataset_timestamp:
                check_manager.add_display(
                    target_name=target_datasets,
                    display=Padding(
                        f"Timestamp: [cyan]{dataset_timestamp}[/cyan]",
                        (0, 0, 0, 12),
                    ),
                )

            dataset_ttl = dataset_spec.get("ttl", "")
            if dataset_ttl:
                check_manager.add_display(
                    target_name=target_datasets,
                    display=Padding(
                        f"Expiration time: [cyan]{dataset_ttl}[/cyan]",
                        (0, 0, 0, 12),
                    ),
                )

        if detail_level == ResourceOutputDetailLevel.verbose.value and dataset_spec.get("keys"):
            _process_verbose_only_property(
                check_manager=check_manager,
                detail_level=detail_level,
                target_name=target_datasets,
                stage_properties=d["spec"]["keys"],
                display_name="Dataset configuration key",
                padding=(0, 0, 0, 12)
            )

    return check_manager.as_dict(as_list)


def _process_stage_properties(
    check_manager: CheckManager,
    detail_level: Optional[str],
    target_name: str,
    stage: dict,
    stage_properties: dict,
    padding: tuple
):
    stage_type = stage["type"]

    for stage_value, properties in stage_properties.items():
        if stage_value in stage_type:
            for prop, display_name, verbose_only in properties:
                keys = prop.split('.')
                prop_value = stage
                for key in keys:
                    prop_value = prop_value.get(key)
                if prop_value is None:
                    continue
                if verbose_only:
                    _process_verbose_only_property(
                        check_manager,
                        detail_level,
                        target_name,
                        stage_properties=prop_value,
                        display_name=display_name,
                        padding=padding
                    )
                else:
                    if prop == "descriptor":
                        prop_value = prop_value[:5] + "..."
                    elif prop.endswith("clientSecret"):
                        prop_value = "*" * len(prop_value)
                    display_text = f"{display_name}: [bright_blue]{prop_value}[/bright_blue]"
                    check_manager.add_display(target_name=target_name, display=Padding(display_text, padding))


def _process_verbose_only_property(
    check_manager: CheckManager,
    detail_level: Optional[str],
    target_name: str,
    stage_properties: Any,
    display_name: str,
    padding: tuple
):
    if detail_level != ResourceOutputDetailLevel.verbose.value:
        return

    if isinstance(stage_properties, list):
        if len(stage_properties) == 0:
            return

        display_text = f"{display_name}:"
        check_manager.add_display(target_name=target_name, display=Padding(display_text, padding))

        for property in stage_properties:
            display_text = f"  - {display_name} [bright_blue]{stage_properties.index(property) + 1}[/bright_blue]"
            check_manager.add_display(target_name=target_name, display=Padding(display_text, padding))
            for prop, value in property.items():
                display_text = f"    {prop}: [bright_blue]{value}[/bright_blue]"
                check_manager.add_display(target_name=target_name, display=Padding(display_text, padding))
            check_manager.add_display(target_name=target_name, display=Padding("", padding))
    elif isinstance(stage_properties, str):
        display_text = f"{display_name}: [bright_blue]{stage_properties}[/bright_blue]"
        check_manager.add_display(target_name=target_name, display=Padding(display_text, padding))
    elif isinstance(stage_properties, dict):
        display_text = f"{display_name}:"
        check_manager.add_display(target_name=target_name, display=Padding(display_text, padding))
        for prop, value in stage_properties.items():
            display_text = f"  {prop}: [bright_blue]{value}[/bright_blue]"
            check_manager.add_display(target_name=target_name, display=Padding(display_text, padding))
        check_manager.add_display(target_name=target_name, display=Padding("", padding))


def add_display_and_eval(
    check_manager: CheckManager,
    target_name: str,
    display_text: str,
    eval_status: str,
    eval_value: str,
    resource_name: Optional[str] = None,
    padding: Tuple[int, int, int, int] = (0, 0, 0, 8)
):
    check_manager.add_display(target_name=target_name, display=Padding(display_text, padding))
    check_manager.add_target_eval(target_name=target_name, status=eval_status, value=eval_value, resource_name=resource_name)


def _evaluate_source_node(
    pipeline_source_node: dict,
    target_pipelines: str,
    pipeline_name: str,
    check_manager: CheckManager,
    detail_level: Optional[str] = ResourceOutputDetailLevel.summary.value,
):

    # check data source node count
    pipeline_source_node_count = 1 if pipeline_source_node else 0
    source_count_display_text = f"- Expecting [bright_blue]1[/bright_blue] MQTT data source node. [green]Detected {pipeline_source_node_count}[/green]."

    pipeline_source_count_eval_value = {"sourceNodeCount": pipeline_source_node_count}
    pipeline_source_count_eval_status = CheckTaskStatus.success.value

    if pipeline_source_node_count != 1:
        pipeline_source_count_eval_status = CheckTaskStatus.error.value
        source_count_display_text = f"- Expecting [bright_blue]1[/bright_blue] MQTT data source node. {{[red]Detected {pipeline_source_node_count}[/red]}}."
    add_display_and_eval(check_manager, target_pipelines, source_count_display_text, pipeline_source_count_eval_status, pipeline_source_count_eval_value, pipeline_name, (0, 0, 0, 12))

    # check data source topics
    pipeline_source_node_topics = pipeline_source_node["topics"]
    pipeline_source_node_topics_count = len(pipeline_source_node_topics)
    source_topics_display_text = f"- Expecting [bright_blue]>=1[/bright_blue] and [bright_blue]<=50[/bright_blue] topics. [green]Detected {pipeline_source_node_topics_count}[/green]."

    pipeline_source_topics_eval_value = {"len(spec.input.topics)": pipeline_source_node_topics_count}
    pipeline_source_topics_eval_status = CheckTaskStatus.success.value

    if pipeline_source_node_topics_count < 1 or pipeline_source_node_topics_count > 50:
        pipeline_source_topics_eval_status = CheckTaskStatus.error.value
    check_manager.add_display(target_name=target_pipelines, display=Padding(source_topics_display_text, (0, 0, 0, 16)))

    check_manager.add_target_eval(
        target_name=target_pipelines, status=pipeline_source_topics_eval_status, value=pipeline_source_topics_eval_value, resource_name=pipeline_name
    )

    if detail_level != ResourceOutputDetailLevel.summary.value:
        # data source topics detail
        for topic in pipeline_source_node_topics:
            topic_display_text = f"Topic {{[bright_blue]{topic}[/bright_blue]}} detected."
            check_manager.add_display(target_name=target_pipelines, display=Padding(topic_display_text, (0, 0, 0, 18)))

        # data source broker URL
        pipeline_source_node_broker = pipeline_source_node["broker"]
        source_broker_display_text = f"- Broker URL: [bright_blue]{pipeline_source_node_broker}[/bright_blue]"

        check_manager.add_display(target_name=target_pipelines, display=Padding(source_broker_display_text, (0, 0, 0, 16)))

        # data source message format type
        pipeline_source_node_format_type = pipeline_source_node["format"]["type"]
        source_format_type_display_text = f"- Source message type: [bright_blue]{pipeline_source_node_format_type}[/bright_blue]"
        check_manager.add_display(target_name=target_pipelines, display=Padding(source_format_type_display_text, (0, 0, 0, 16)))

        # data source qos
        pipeline_source_node_qos = pipeline_source_node["qos"]
        source_qos_display_text = f"- QoS: [bright_blue]{pipeline_source_node_qos}[/bright_blue]"
        check_manager.add_display(target_name=target_pipelines, display=Padding(source_qos_display_text, (0, 0, 0, 16)))

        # check data source partition
        pipeline_source_node_partition_count = pipeline_source_node["partitionCount"]
        pipeline_source_node_partition_strategy = pipeline_source_node["partitionStrategy"]["type"]
        source_partition_count_display_text = f"- Expecting the number of partition [bright_blue]>=1[/bright_blue] and [bright_blue]<=100[/bright_blue]. [green]Detected {pipeline_source_node_partition_count}[/green]."
        source_partition_strategy_display_text = f"The type of partitioning strategy is {{[bright_blue]{pipeline_source_node_partition_strategy}[/bright_blue]}}."

        pipeline_source_partition_eval_value = {"spec.input.partitionCount": pipeline_source_node_partition_count}
        pipeline_source_partition_eval_status = CheckTaskStatus.success.value

        if pipeline_source_node_partition_count < 1 or pipeline_source_node_partition_count > 100:
            pipeline_source_partition_eval_status = CheckTaskStatus.error.value
        check_manager.add_display(target_name=target_pipelines, display=Padding(source_partition_count_display_text, (0, 0, 0, 16)))
        check_manager.add_display(target_name=target_pipelines, display=Padding(source_partition_strategy_display_text, (0, 0, 0, 18)))

        check_manager.add_target_eval(
            target_name=target_pipelines, status=pipeline_source_partition_eval_status, value=pipeline_source_partition_eval_value, resource_name=pipeline_name
        )

    # data source authentication
    pipeline_source_node_authentication = pipeline_source_node["authentication"]["type"]
    if pipeline_source_node_authentication == "usernamePassword":
        source_authentication_display_text = f"- Authentication type: [bright_blue]{pipeline_source_node_authentication}[/bright_blue]"
        check_manager.add_display(target_name=target_pipelines, display=Padding(source_authentication_display_text, (0, 0, 0, 16)))

        if detail_level != ResourceOutputDetailLevel.summary.value:
            authentication_username = pipeline_source_node["authentication"]["username"]
            authentication_password = pipeline_source_node["authentication"]["password"]
            masked_password = '*' * len(authentication_password)
            check_manager.add_display(target_name=target_pipelines, display=Padding(f"Username: [cyan]{authentication_username}[/cyan]", (0, 0, 0, 20)))
            check_manager.add_display(target_name=target_pipelines, display=Padding(f"Password: [cyan]{masked_password}[/cyan]", (0, 0, 0, 20)))


def _evaluate_intermediate_nodes(
    output_node: Tuple,
    pipeline_stages_node: dict,
    target_pipelines: str,
    check_manager: CheckManager,
    detail_level: Optional[str] = ResourceOutputDetailLevel.summary.value,
):

    # number of intermediate stages should be total len(stages) - len(output stage)
    pipeline_intermediate_stages_node = pipeline_stages_node.copy()
    pipeline_intermediate_stages_node_count = len(pipeline_stages_node)
    if output_node:
        pipeline_intermediate_stages_node.pop(output_node[0])
        pipeline_intermediate_stages_node_count -= 1
    stage_count_display_text = f"- Pipeline contains [bright_blue]{pipeline_intermediate_stages_node_count}[/bright_blue] intermediate stages."

    check_manager.add_display(target_name=target_pipelines, display=Padding(stage_count_display_text, (0, 0, 0, 12)))

    if detail_level != ResourceOutputDetailLevel.summary.value:
        for s in pipeline_intermediate_stages_node:
            stage_name = s
            stage_type = pipeline_intermediate_stages_node[s]["type"]
            stage_display_text = f"- Stage resource {{[bright_blue]{stage_name}[/bright_blue]}} of type {{[bright_blue]{stage_type}[/bright_blue]}}"
            check_manager.add_display(target_name=target_pipelines, display=Padding(stage_display_text, (0, 0, 0, 16)))

            _process_stage_properties(
                check_manager,
                detail_level,
                target_name=target_pipelines,
                stage=pipeline_intermediate_stages_node[s],
                stage_properties=BLUEFIN_INTERMEDIATE_STAGE_PROPERTIES,
                padding=(0, 0, 0, 20)
            )


def _evaluate_destination_node(
    output_node: dict,
    target_pipelines: str,
    pipeline_name: str,
    check_manager: CheckManager,
    detail_level: Optional[str] = ResourceOutputDetailLevel.summary.value,
):
    pipeline_destination_node_count = 0
    if output_node:
        pipeline_destination_node_count = 1
    destination_count_display_text = f"- Expecting [bright_blue]1[/bright_blue] data destination node. [green]Detected {pipeline_destination_node_count}[/green]."

    pipeline_destination_eval_value = {"destinationNodeCount": pipeline_destination_node_count}
    pipeline_destination_eval_status = CheckTaskStatus.success.value

    if pipeline_destination_node_count != 1:
        pipeline_destination_eval_status = CheckTaskStatus.error.value
    add_display_and_eval(check_manager, target_pipelines, destination_count_display_text, pipeline_destination_eval_status, pipeline_destination_eval_value, pipeline_name, (0, 0, 0, 12))

    if output_node:
        if detail_level != ResourceOutputDetailLevel.summary.value:
            _process_stage_properties(
                check_manager,
                detail_level,
                target_name=target_pipelines,
                stage=output_node[1],
                stage_properties=BLUEFIN_DESTINATION_STAGE_PROPERTIES,
                padding=(0, 0, 0, 16)
            )
