# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict, List

from azure.cli.core.azclierror import CLIInternalError
from knack.log import get_logger
from rich.padding import Padding

from azext_edge.edge.providers.check.base.pod import process_pod_status
from azext_edge.edge.providers.check.base.resource import filter_resources_by_name
from azext_edge.edge.providers.edge_api.dataflow import DATAFLOW_API_V1B1, DataflowResourceKinds

from ...common import CheckTaskStatus
from ..base import get_namespaced_pods_by_prefix
from ..support.dataflow import DATAFLOW_NAME_LABEL, DATAFLOW_OPERATOR_PREFIX
from .base import CheckManager, check_post_deployment, get_resources_by_name, get_resources_grouped_by_namespace
from .common import (
    COLOR_STR_FORMAT,
    PADDING_SIZE,
    CoreServiceResourceKinds,
    DataflowEndpointType,
    DataflowOperationType,
    ResourceOutputDetailLevel,
)

logger = get_logger(__name__)

dataflow_api_check_name = "enumerateDataflowApi"
dataflow_api_check_desc = "Enumerate Dataflow API resources"

dataflow_runtime_check_name = "evalCoreServiceRuntime"
dataflow_runtime_check_desc = "Evaluate Dataflow core service"

dataflows_check_name = "evalDataflows"
dataflows_check_desc = "Evaluate Dataflows"

dataflow_endpoint_check_name = "evalDataflowEndpoints"
dataflow_endpoint_check_desc = "Evaluate Dataflow Endpoints"

dataflow_profile_check_name = "evalDataflowProfiles"
dataflow_profile_check_desc = "Evaluate Dataflow Profiles"

dataflow_target = "dataflows.connectivity.iotoperations.azure.com"
dataflow_endpoint_target = "dataflowendpoints.connectivity.iotoperations.azure.com"
dataflow_profile_target = "dataflowprofiles.connectivity.iotoperations.azure.com"


# TODO - consolidate TLS.mode checks

def _process_dataflow_sourcesettings(
    check_manager: CheckManager, target: str, namespace: str, endpoint_tuples: List[tuple[str,str]], resource: dict, detail_level: int, padding: int
):
    settings = resource.get("sourceSettings", {})

    # show endpoint ref
    # TODO - validate endpoint ref
    # TODO - sourcetype only mqtt and kafka
    endpoint_ref = settings.get("endpointRef")

    endpoint_match = next((endpoint for endpoint in endpoint_tuples if endpoint[0] == endpoint_ref), None)

    endpoint_status_color = "green" 
    endpoint_status = CheckTaskStatus.success.value
    if not endpoint_match:
        endpoint_status = CheckTaskStatus.error.value
        endpoint_status_color = "red"
    
    # valid endpoint ref eval
    check_manager.add_target_eval(
        target_name=target,
        namespace=namespace,
        status=endpoint_status,
        resource_name=endpoint_ref,
        resource_kind=DataflowResourceKinds.DATAFLOWENDPOINT.value,
        value={"spec.operations[*].sourceSettings.endpointRef": endpoint_ref},
    )


    if detail_level > ResourceOutputDetailLevel.summary.value:
        check_manager.add_display(
            target_name=target, namespace=namespace, display=Padding("\nSource:", (0, 0, 0, padding))
        )

        padding += 4
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(
                f"Dataflow Endpoint: {{{COLOR_STR_FORMAT.format(color=endpoint_status_color, value=endpoint_ref)}}}",
                (0, 0, 0, padding),
            ),
        )
        if not endpoint_match:
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding("[red]Invalid Dataflow Endpoint reference[/red]", (0, 0, 0, padding)),
            )

    # TODO extra properties - only on verbose
    if detail_level > ResourceOutputDetailLevel.detail.value:
        for label, key in [
            # TODO - validate asset ref / colorize
            ("DeviceRegistry Asset Reference", "assetRef"),
            ("Schema Reference", "schemaRef"),
            ("Serialization Format", "serializationFormat"),
        ]:
            val = settings.get(key)
            if val:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(f"{label}: {val}", (0, 0, 0, padding)),
                )

    # data source strings - not on summary
    if detail_level > ResourceOutputDetailLevel.summary.value:
        data_sources = settings.get("dataSources", [])
        if data_sources:
            check_manager.add_display(
                target_name=target, namespace=namespace, display=Padding("Data Sources:", (0, 0, 0, padding))
            )
            for data_source in data_sources:
                check_manager.add_display(
                    target_name=target, namespace=namespace, display=Padding(f"- {data_source}", (0, 0, 0, padding + 2))
                )


def _process_dataflow_transformationsettings(
    check_manager: CheckManager, target: str, namespace: str, resource: dict, detail_level: int, padding: int
):
    settings = resource.get("builtInTransformationSettings", {})

    # only show details on non-summary
    if detail_level > ResourceOutputDetailLevel.summary.value:
        check_manager.add_display(
            target_name=target, namespace=namespace, display=Padding("\nBuilt-In Transformation:", (0, 0, 0, padding))
        )
        padding += 4
        inner_padding = padding + 4

        def _process_inputs(inputs: List[str]):
            if inputs:
                check_manager.add_display(
                    target_name=target, namespace=namespace, display=Padding("Inputs:", (0, 0, 0, inner_padding))
                )
                for input in inputs:
                    check_manager.add_display(
                        target_name=target, namespace=namespace, display=Padding(f"- {input}", (0, 0, 0, inner_padding + 2))
                    )
        # extra properties
        for datasets_label, key in [
            ("Schema Reference", "schemaRef"),
            ("Serialization Format", "serializationFormat"),
        ]:
            # TODO - validate endpoint ref
            val = settings.get(key)
            if val:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(f"{datasets_label}: {val}", (0, 0, 0, padding)),
                )

    # only show datasets, filters, maps on verbose
    if detail_level > ResourceOutputDetailLevel.detail.value:
        # datasets
        datasets = settings.get("datasets", [])
        if datasets:
            check_manager.add_display(
                target_name=target, namespace=namespace, display=Padding("Datasets:", (0, 0, 0, padding))
            )
        for dataset in datasets:
            for label, key in [
                ("Description", "description"),
                ("Key", "key"),
                ("Expression", "expression"),
                ("Schema", "schemaRef"),
            ]:
                val = dataset.get(key)
                if val:
                    check_manager.add_display(
                        target_name=target,
                        namespace=namespace,
                        display=Padding(f"{label}: {val}", (0, 0, 0, inner_padding)),
                    )
            inputs = dataset.get("inputs", [])
            _process_inputs(inputs)

        # filters
        filters = settings.get("filter", [])
        if filters:
            check_manager.add_display(
                target_name=target, namespace=namespace, display=Padding("Filters:", (0, 0, 0, padding))
            )
        for filter in filters:
            for datasets_label, key in [
                ("Description", "description"),
                ("Expression", "expression"),
                ("Operation Type", "type"),
            ]:
                val = filter.get(key)
                if val:
                    check_manager.add_display(
                        target_name=target,
                        namespace=namespace,
                        display=Padding(f"{datasets_label}: {val}", (0, 0, 0, padding + 4)),
                    )
            inputs = filter.get("inputs", [])
            _process_inputs(inputs)

        # maps
        maps = settings.get("map", [])
        if maps:
            check_manager.add_display(
                target_name=target, namespace=namespace, display=Padding("Maps:", (0, 0, 0, padding))
            )
        for map in maps:
            for label, key in [
                ("Description", "description"),
                ("Expression", "expression"),
                ("Output", "output"),
                ("Transformation Type", "type"),
            ]:
                val = map.get(key)
                if val:
                    check_manager.add_display(
                        target_name=target,
                        namespace=namespace,
                        display=Padding(f"{label}: {val}", (0, 0, 0, inner_padding)),
                    )
            inputs = map.get("inputs", [])
            _process_inputs(inputs)


def _process_dataflow_destinationsettings(
    check_manager: CheckManager, target: str, namespace: str, endpoint_tuples: List[tuple[str,str]], resource: dict, detail_level: int, padding: int
):
    settings = resource.get("destinationSettings", {})
    if detail_level > ResourceOutputDetailLevel.summary.value:
        check_manager.add_display(
            target_name=target, namespace=namespace, display=Padding("\nDestination:", (0, 0, 0, padding))
        )
    padding += 4
    # TODO - validate endpoint ref
    endpoint_ref = settings.get("endpointRef")

    endpoint_match = next((endpoint for endpoint in endpoint_tuples if endpoint[0] == endpoint_ref), None)

    endpoint_status_color = "green" 
    endpoint_status = CheckTaskStatus.success.value
    if not endpoint_match:
        endpoint_status = CheckTaskStatus.error.value
        endpoint_status_color = "red"
    
    # valid endpoint ref eval
    check_manager.add_target_eval(
        target_name=target,
        namespace=namespace,
        status=endpoint_status,
        resource_name=endpoint_ref,
        resource_kind=DataflowResourceKinds.DATAFLOWENDPOINT.value,
        value={"spec.operations[*].destinationSettings.endpointRef": endpoint_ref},
    )
    # show dataflow endpoint ref on detail
    if detail_level > ResourceOutputDetailLevel.summary.value:
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(
                f"Dataflow Endpoint: {{{COLOR_STR_FORMAT.format(color=endpoint_status_color, value=endpoint_ref)}}}",
                (0, 0, 0, padding),
            ),
        )
        if not endpoint_match:
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding("[red]Invalid Dataflow Endpoint reference[/red]", (0, 0, 0, padding)),
            )
        # only show destination on verbose
        if detail_level > ResourceOutputDetailLevel.detail.value:
            for label, key in [
                ("Data Destination", "dataDestination"),
            ]:
                # TODO - validate endpoint ref
                val = settings.get(key)
                if val:
                    check_manager.add_display(
                        target_name=target,
                        namespace=namespace,
                        display=Padding(f"{label}: {val}", (0, 0, 0, padding)),
                    )


def _process_endpoint_mqttsettings(
    check_manager: CheckManager, target: str, namespace: str, spec: dict, detail_level: int, padding: int
) -> None:
    settings = spec.get("mqttSettings", {})
    for label, key in [
        ("MQTT Host", "host"),
        ("Protocol", "protocol"),
    ]:
        val = settings.get(key)
        if val:
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(f"{label}: {val}", (0, 0, 0, padding)),
            )
    if detail_level > ResourceOutputDetailLevel.detail.value:
        for label, key in [
            ("Client ID Prefix", "clientIdPrefix"),
            ("Keep Alive (s)", "keepAliveSeconds"),
            ("Max Inflight Messages", "maxInflightMessages"),
            ("QOS", "qos"),
            ("Retain", "retain"),
            ("Session Expiry (s)", "sessionExpirySeconds"),
        ]:
            val = settings.get(key)
            if val:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(f"{label}: {val}", (0, 0, 0, padding)),
                )

        tls = settings.get("tls", {})
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding("TLS", (0, 0, 0, padding)),
        )
        for label, key in [
            ("Mode", "mode"),
            ("Trusted CA ConfigMap", "trustedCaCertificateConfigMapRef"),
        ]:
            # TODO - validate ref?
            val = tls.get(key)
            if val:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(f"{label}: {val}", (0, 0, 0, padding + 4)),
                )


def _process_endpoint_kafkasettings(
    check_manager: CheckManager, target: str, namespace: str, spec: dict, detail_level: int, padding: int
) -> None:
    settings = spec.get("kafkaSettings", {})

    for label, key in [
        ("Kafka Host", "host"),
        ("Consumer Group ID", "consumerGroupId"),
    ]:
        val = settings.get(key)
        if val:
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(f"{label}: {val}", (0, 0, 0, padding)),
            )

    if detail_level > ResourceOutputDetailLevel.detail.value:
        # extra properties
        for label, key in [
            ("Compression", "compression"),
            ("Copy MQTT Properties", "copyMqttProperties"),
            ("Acks", "kafkaAcks"),
            ("Partition Strategy", "partitionStrategy"),
        ]:
            val = settings.get(key)
            if val:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(f"{label}: {val}", (0, 0, 0, padding)),
                )
        # tls
        tls = settings.get("tls", {})
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding("TLS", (0, 0, 0, padding)),
        )
        for label, key in [
            ("Mode", "mode"),
            ("Trusted CA ConfigMap", "trustedCaCertificateConfigMapRef"),
        ]:
            # TODO - validate ref?
            val = tls.get(key)
            if val:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(f"{label}: {val}", (0, 0, 0, padding + 4)),
                )

        # batching
        batching = settings.get("batching", {})
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding("Batching:", (0, 0, 0, padding)),
        )

        for label, key in [
            ("Latency (ms)", "latencyMs"),
            ("Max Bytes", "maxBytes"),
            ("Max Messages", "maxMessages"),
            ("Mode", "mode"),
        ]:
            val = batching.get(key)
            if val:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(f"{label}: {val}", (0, 0, 0, padding + 4)),
                )


def _process_endpoint_fabriconelakesettings(
    check_manager: CheckManager, target: str, namespace: str, spec: dict, detail_level: int, padding: int
) -> None:
    settings = spec.get("fabricOneLakeSettings", {})
    for label, key in [("Fabric Host", "host"), ("Path Type", "oneLakePathType")]:
        val = settings.get(key)
        if val:
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(f"{label}: {val}", (0, 0, 0, padding)),
            )
    if detail_level > ResourceOutputDetailLevel.detail.value:
        names = settings.get("names", {})
        for label, key in [
            ("Lakehouse Name", "lakehouseName"),
            ("Workspace Name", "workspaceName"),
        ]:
            val = names.get(key)
            if val:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(f"{label}: {val}", (0, 0, 0, padding)),
                )

        batching = settings.get("batching", {})
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding("Batching:", (0, 0, 0, padding)),
        )

        padding += 4
        for label, key in [
            ("Latency (s)", "latencySeconds"),
            ("Max Messages", "maxMessages"),
        ]:
            val = batching.get(key)
            if val:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(f"{label}: {val}", (0, 0, 0, padding)),
                )


def _process_endpoint_datalakestoragesettings(
    check_manager: CheckManager, target: str, namespace: str, spec: dict, detail_level: int, padding: int
) -> None:
    settings = spec.get("datalakeStorageSettings", {})
    for label, key in [("DataLake Host", "host")]:
        val = settings.get(key)
        if val:
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(f"{label}: {val}", (0, 0, 0, padding)),
            )

    if detail_level > ResourceOutputDetailLevel.detail.value:
        batching = settings.get("batching", {})
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding("Batching:", (0, 0, 0, padding)),
        )
        padding += 4
        for label, key in [
            ("Latency (s)", "latencySeconds"),
            ("Max Messages", "maxMessages"),
        ]:
            val = batching.get(key)
            if val:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(f"{label}: {val}", (0, 0, 0, padding)),
                )


def _process_endpoint_dataexplorersettings(
    check_manager: CheckManager, target: str, namespace: str, spec: dict, detail_level: int, padding: int
) -> None:
    settings = spec.get("dataExplorerSettings", {})
    for label, key in [("Database Name", "database"), ("Data Explorer Host", "host")]:
        val = settings.get(key)
        if val:
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(f"{label}: {val}", (0, 0, 0, padding)),
            )

    if detail_level > ResourceOutputDetailLevel.detail.value:
        batching = settings.get("batching", {})
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding("Batching:", (0, 0, 0, padding)),
        )

        padding += 4
        for label, key in [
            ("Latency (s)", "latencySeconds"),
            ("Max Messages", "maxMessages"),
        ]:
            val = batching.get(key)
            if val:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(f"{label}: {val}", (0, 0, 0, padding)),
                )


def _process_endpoint_localstoragesettings(
    check_manager: CheckManager, target: str, namespace: str, spec: dict, detail_level: int, padding: int
) -> None:
    # TODO - validate reference
    settings = spec.get("localStorageSettings", {})
    persistent_volume_claim = settings.get("persistentVolumeClaimRef")
    check_manager.add_display(
        target_name=target,
        namespace=namespace,
        display=Padding(f"Persistent Volume Claim: {persistent_volume_claim}", (0, 0, 0, padding)),
    )


def check_dataflows_deployment(
    result: Dict[str, Any],
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_kinds: List[str] = None,
    resource_name: str = None,
) -> None:
    evaluate_funcs = {
        CoreServiceResourceKinds.RUNTIME_RESOURCE: evaluate_core_service_runtime,
        DataflowResourceKinds.DATAFLOWPROFILE: evaluate_dataflow_profiles,
        DataflowResourceKinds.DATAFLOW: evaluate_dataflows,
        DataflowResourceKinds.DATAFLOWENDPOINT: evaluate_dataflow_endpoints,
    }

    check_post_deployment(
        api_info=DATAFLOW_API_V1B1,
        check_name=dataflow_api_check_name,
        check_desc=dataflow_api_check_desc,
        result=result,
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
):
    check_manager = CheckManager(
        check_name=dataflow_runtime_check_name,
        check_desc=dataflow_runtime_check_desc,
    )

    padding = 6
    operators = get_namespaced_pods_by_prefix(
        prefix="",
        namespace="",
        label_selector=DATAFLOW_NAME_LABEL,
    )
    if resource_name:
        operators = filter_resources_by_name(
            resources=operators,
            resource_name=resource_name,
        )

    if not operators:
        check_manager.add_target(target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value)
        check_manager.add_display(
            target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value,
            display=Padding("Unable to fetch pods.", (0, 0, 0, padding + 2)),
        )

    for namespace, pods in get_resources_grouped_by_namespace(operators):
        check_manager.add_target(
            target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value,
            namespace=namespace,
        )
        check_manager.add_display(
            target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value,
            namespace=namespace,
            display=Padding(
                f"Dataflow runtime resources in namespace {{[purple]{namespace}[/purple]}}",
                (0, 0, 0, padding),
            ),
        )

        process_pod_status(
            check_manager=check_manager,
            target_service_pod=f"pod/{DATAFLOW_OPERATOR_PREFIX}",
            target=CoreServiceResourceKinds.RUNTIME_RESOURCE.value,
            pods=pods,
            namespace=namespace,
            display_padding=padding + PADDING_SIZE,
            detail_level=detail_level,
        )

    return check_manager.as_dict(as_list)


def evaluate_dataflows(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
):
    check_manager = CheckManager(
        check_name=dataflows_check_name,
        check_desc=dataflows_check_desc,
    )
    all_dataflows = get_resources_by_name(
        api_info=DATAFLOW_API_V1B1,
        kind=DataflowResourceKinds.DATAFLOW,
        resource_name=resource_name,
    )
    target = dataflow_target
    padding = 8

    # No dataflows - skip
    if not all_dataflows:
        no_dataflows_text = "No Dataflow resources detected in any namespace."
        check_manager.add_target(target_name=target)
        check_manager.add_target_eval(
            target_name=target, status=CheckTaskStatus.skipped.value, value={"dataflows": no_dataflows_text}
        )
        check_manager.add_display(
            target_name=target,
            display=Padding(no_dataflows_text, (0, 0, 0, padding)),
        )
        return check_manager.as_dict(as_list=as_list)
    for namespace, dataflows in get_resources_grouped_by_namespace(all_dataflows):
        padding = 8
        check_manager.add_target(target_name=target, namespace=namespace)
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(f"Dataflows in namespace {{[purple]{namespace}[/purple]}}", (0, 0, 0, padding)),
        )
        # conditions
        check_manager.add_target_conditions(
            target_name=target,
            namespace=namespace,
            conditions=[
                # valid dataflow profile reference
                "spec.profileRef"
                # at least a source and destination operation
                "2<=len(spec.operations)<=3",
                # valid endpoint refs
                "spec.operations[*].sourceSettings.endpointRef",
                "spec.operations[*].destinationSettings.endpointRef",
            ]
        )

        # profile names for reference lookup
        all_profiles = get_resources_by_name(
            api_info=DATAFLOW_API_V1B1,
            kind=DataflowResourceKinds.DATAFLOWPROFILE,
            namespace=namespace,
            resource_name=None,
        )
        profile_names = {profile.get("metadata", {}).get("name") for profile in all_profiles}
        for dataflow in list(dataflows):
            spec = dataflow.get("spec", {})
            dataflow_name = dataflow.get("metadata", {}).get("name")
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(
                    f"\n- Dataflow {{{COLOR_STR_FORMAT.format(color='bright_blue', value=dataflow_name)}}} {COLOR_STR_FORMAT.format(color='green', value='detected')}",
                    (0, 0, 0, padding),
                ),
            )

            mode = spec.get("mode")
            profile_ref = spec.get("profileRef")
            profile_ref_status = CheckTaskStatus.success.value
            profile_ref_status_color = "green"
            if profile_ref and profile_ref not in profile_names:
                profile_ref_status = CheckTaskStatus.error.value
                profile_ref_status_color = "red"

            # valid profileRef eval
            check_manager.add_target_eval(
                target_name=target,
                namespace=namespace,
                status=profile_ref_status,
                resource_name=dataflow_name,
                resource_kind=DataflowResourceKinds.DATAFLOWPROFILE.value,
                value={"spec.profileRef": profile_ref},
            )

            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(f"Dataflow Profile: {{{COLOR_STR_FORMAT.format(color=profile_ref_status_color, value=profile_ref)}}}", (0, 0, 0, padding + 4)),
            )
            if profile_ref_status == CheckTaskStatus.error.value and detail_level > ResourceOutputDetailLevel.summary.value:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(COLOR_STR_FORMAT.format(color="red", value="Invalid Dataflow Profile reference"), (0, 0, 0, padding + 4)),
                )
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(f"Mode: {mode}", (0, 0, 0, padding + 4)),
            )

            operations = spec.get("operations", [])

            # check operations count
            operations_status = CheckTaskStatus.success.value
            if not operations or not (2 <= len(operations) <= 3):
                operations_status = CheckTaskStatus.error.value
            check_manager.add_target_eval(
                target_name=target,
                namespace=namespace,
                status=operations_status,
                resource_name=dataflow_name,
                resource_kind=DataflowResourceKinds.DATAFLOW.value,
                value={"len(operations)": len(operations)},
            )

            if operations and detail_level > ResourceOutputDetailLevel.summary.value:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding("Operations:", (0, 0, 0, padding + 4)),
                )
            all_endpoints = get_resources_by_name(
                api_info=DATAFLOW_API_V1B1,
                kind=DataflowResourceKinds.DATAFLOWENDPOINT,
                namespace=namespace,
                resource_name=None,
            )
            endpoint_tuples = [(endpoint.get("metadata", {}).get("name"), endpoint.get("spec", {}).get("endpointType")) for endpoint in all_endpoints]
            operation_padding = padding + 8
            for operation in operations:
                op_type = operation.get("operationType", "").lower()
                if op_type == DataflowOperationType.source.value:
                    _process_dataflow_sourcesettings(
                        check_manager=check_manager,
                        target=target,
                        namespace=namespace,
                        endpoint_tuples=endpoint_tuples,
                        resource=operation,
                        detail_level=detail_level,
                        padding=operation_padding,
                    )
                elif op_type == DataflowOperationType.builtin_transformation.value:
                    _process_dataflow_transformationsettings(
                        check_manager=check_manager,
                        target=target,
                        namespace=namespace,
                        resource=operation,
                        detail_level=detail_level,
                        padding=operation_padding,
                    )
                elif op_type == DataflowOperationType.destination.value:
                    _process_dataflow_destinationsettings(
                        check_manager=check_manager,
                        target=target,
                        namespace=namespace,
                        endpoint_tuples=endpoint_tuples,
                        resource=operation,
                        detail_level=detail_level,
                        padding=operation_padding,
                    )
    return check_manager.as_dict(as_list=as_list)


def evaluate_dataflow_endpoints(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
):
    check_manager = CheckManager(
        check_name=dataflow_endpoint_check_name,
        check_desc=dataflow_endpoint_check_desc,
    )
    all_endpoints = get_resources_by_name(
        api_info=DATAFLOW_API_V1B1,
        kind=DataflowResourceKinds.DATAFLOWENDPOINT,
        resource_name=resource_name,
    )
    target = dataflow_endpoint_target
    padding = 8
    if not all_endpoints:
        no_endpoints_text = "No Dataflow Endpoints detected in any namespace."
        check_manager.add_target(target_name=target)
        check_manager.add_target_eval(
            target_name=target, status=CheckTaskStatus.skipped.value, value={"endpoints": no_endpoints_text}
        )
        check_manager.add_display(
            target_name=target,
            display=Padding(no_endpoints_text, (0, 0, 0, padding)),
        )
        return check_manager.as_dict(as_list=as_list)
    for namespace, endpoints in get_resources_grouped_by_namespace(all_endpoints):
        padding = 8
        check_manager.add_target(target_name=target, namespace=namespace, conditions=["valid(spec.endpointType)"])
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(f"Dataflow Endpoints in namespace {{[purple]{namespace}[/purple]}}", (0, 0, 0, padding)),
        )
        for endpoint in list(endpoints):
            padding = 8
            spec = endpoint.get("spec", {})
            endpoint_name = endpoint.get("metadata", {}).get("name")
            endpoint_type = spec.get("endpointType")
            valid_endpoint_type = endpoint_type and endpoint_type.lower() in DataflowEndpointType.list()
            check_manager.add_target_eval(
                target_name=target,
                namespace=namespace,
                status=CheckTaskStatus.success.value if valid_endpoint_type else CheckTaskStatus.error.value,
                resource_name=endpoint_name,
                resource_kind=DataflowResourceKinds.DATAFLOWENDPOINT.value,
                value={"spec.endpointType": endpoint_type},
            )

            endpoint_string = f"Endpoint {{{COLOR_STR_FORMAT.format(color='bright_blue', value=endpoint_name)}}}"
            detected_string = COLOR_STR_FORMAT.format(color='green', value='detected')
            type_string = f"type: {COLOR_STR_FORMAT.format(color='bright_blue' if valid_endpoint_type else 'red', value=endpoint_type)}"
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(
                    f"\n- {endpoint_string} {detected_string}, {type_string}",
                    (0, 0, 0, padding),
                ),
            )

            # endpoint auth
            if detail_level > ResourceOutputDetailLevel.summary.value:
                auth = spec.get("authentication", {})
                auth_method = auth.get("method")
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(f"Authentication Method: {auth_method}", (0, 0, 0, padding + 4)),
                )

                endpoint_processor_dict = {
                    DataflowEndpointType.mqtt.value: _process_endpoint_mqttsettings,
                    DataflowEndpointType.kafka.value: _process_endpoint_kafkasettings,
                    DataflowEndpointType.fabric_onelake.value: _process_endpoint_fabriconelakesettings,
                    DataflowEndpointType.datalake.value: _process_endpoint_datalakestoragesettings,
                    DataflowEndpointType.data_explorer.value: _process_endpoint_dataexplorersettings,
                    DataflowEndpointType.local_storage.value: _process_endpoint_localstoragesettings,
                }
                # process endpoint settings
                if endpoint_type and endpoint_type.lower() in endpoint_processor_dict:
                    endpoint_processor_dict[endpoint_type.lower()](check_manager=check_manager, target=target, namespace=namespace, spec=spec, detail_level=detail_level, padding=padding + 4)
                else:
                    logger.warn(f"Unknown dataflow endpoint type: {endpoint_type}")
                    check_manager.add_display(
                        target_name=target,
                        namespace=namespace,
                        display=Padding(f"[red]Unknown endpoint type: {endpoint_type}[/red]", (0, 0, 0, padding + 4)),
                    )

            check_manager.add_target_eval(
                target_name=target,
                namespace=namespace,
                status=CheckTaskStatus.success.value,
                resource_name=endpoint_name,
                resource_kind=DataflowResourceKinds.DATAFLOWENDPOINT.value,
            )
    return check_manager.as_dict(as_list=as_list)


def evaluate_dataflow_profiles(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
):
    check_manager = CheckManager(
        check_name=dataflow_profile_check_name,
        check_desc=dataflow_profile_check_desc,
    )
    all_profiles = get_resources_by_name(
        api_info=DATAFLOW_API_V1B1,
        kind=DataflowResourceKinds.DATAFLOWPROFILE,
        resource_name=resource_name,
    )
    target = dataflow_profile_target
    padding = 8
    if not all_profiles:
        no_profiles_text = "No Dataflow Profiles detected in any namespace."
        check_manager.add_target(target_name=target)
        check_manager.add_target_eval(
            target_name=target, status=CheckTaskStatus.skipped.value, value={"profiles": no_profiles_text}
        )
        check_manager.add_display(
            target_name=target,
            display=Padding(no_profiles_text, (0, 0, 0, padding)),
        )
        return check_manager.as_dict(as_list=as_list)
    for namespace, profiles in get_resources_grouped_by_namespace(all_profiles):
        padding = 8
        check_manager.add_target(target_name=target, namespace=namespace, conditions=["spec.instanceCount"])
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(f"Dataflow Profiles in namespace {{[purple]{namespace}[/purple]}}", (0, 0, 0, padding)),
        )
        for profile in list(profiles):
            padding = 8
            profile_name = profile.get("metadata", {}).get("name")
            spec = profile.get("spec", {})
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(
                    f"\n- Profile {{{COLOR_STR_FORMAT.format(color='bright_blue', value=profile_name)}}} {COLOR_STR_FORMAT.format(color='green', value='detected')}",
                    (0, 0, 0, padding),
                ),
            )
            # TODO - figure out status / conditions
            instance_count = spec.get("instanceCount")
            has_instances = (instance_count is not None and int(instance_count) >= 0)
            instance_status = CheckTaskStatus.success.value if has_instances else CheckTaskStatus.error.value
            check_manager.add_target_eval(
                target_name=target,
                namespace=namespace,
                status=instance_status,
                resource_name=profile_name,
                resource_kind=DataflowResourceKinds.DATAFLOWPROFILE.value,
                value={"spec.instanceCount": instance_count},
            )
            if has_instances:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(f"Instance count: {instance_count}", (0, 0, 0, padding + 4)),
                )
            else:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding("[red]No instance count set[/red]", (0, 0, 0, padding + 4)),
                )

            # diagnostics on higher detail levels
            if detail_level > ResourceOutputDetailLevel.summary.value:
                padding += 4
                diagnostics = spec.get("diagnostics", {})
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding("Diagnostic Logs:", (0, 0, 0, padding)),
                )

                # diagnostic logs
                diagnostic_logs = diagnostics.get("logs", {})
                diagnostic_log_level = diagnostic_logs.get("level")
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(f"Log Level: {diagnostic_log_level}", (0, 0, 0, padding + 4)),
                )

                if detail_level > ResourceOutputDetailLevel.detail.value:
                    diagnostic_log_otelconfig = diagnostic_logs.get("openTelemetryExportConfig", {})
                    if diagnostic_log_otelconfig:
                        for label, key in [
                            ("Endpoint", "otlpGrpcEndpoint"),
                            ("Interval (s)", "intervalSeconds"),
                            ("Level", "level"),
                        ]:
                            val = diagnostic_log_otelconfig.get(key)
                            if val:
                                check_manager.add_display(
                                    target_name=target,
                                    namespace=namespace,
                                    display=Padding(f"{label}: {val}", (0, 0, 0, padding + 4)),
                                )

                    # diagnostic metrics
                    diagnostic_metrics = diagnostics.get("metrics", {})
                    check_manager.add_display(
                        target_name=target,
                        namespace=namespace,
                        display=Padding("Diagnostic Metrics:", (0, 0, 0, padding)),
                    )

                    diagnostic_metrics_prometheusPort = diagnostic_metrics.get("prometheusPort")
                    check_manager.add_display(
                        target_name=target,
                        namespace=namespace,
                        display=Padding(f"Prometheus Port: {diagnostic_metrics_prometheusPort}", (0, 0, 0, padding + 4)),
                    )

                    diagnostic_metrics_otelconfig = diagnostic_metrics.get("openTelemetryExportConfig", {})
                    if diagnostic_metrics_otelconfig:
                        for label, key in [
                            ("Endpoint", "otlpGrpcEndpoint"),
                            ("Interval (s)", "intervalSeconds"),
                        ]:
                            val = diagnostic_metrics_otelconfig.get(key)
                            if val:
                                check_manager.add_display(
                                    target_name=target,
                                    namespace=namespace,
                                    display=Padding(f"{label}: {val}", (0, 0, 0, padding + 4)),
                                )
                # TODO - determine status
            check_manager.add_target_eval(
                target_name=target,
                namespace=namespace,
                status=CheckTaskStatus.success.value,
                resource_name=profile_name,
                resource_kind=DataflowResourceKinds.DATAFLOWPROFILE.value,
            )
    return check_manager.as_dict(as_list=as_list)
