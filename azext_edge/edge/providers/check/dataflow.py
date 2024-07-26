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


def _process_dataflow_sourcesettings(
    check_manager: CheckManager, target: str, namespace: str, resource: dict, detail_level: int, padding: int
):
    settings = resource.get("sourceSettings", {})
    check_manager.add_display(
        target_name=target, namespace=namespace, display=Padding("\nSource:", (0, 0, 0, padding))
    )

    padding += 4

    # show endpoint ref
    # TODO - validate endpoint ref
    endpoint_ref = settings.get("endpointRef")
    check_manager.add_display(
        target_name=target,
        namespace=namespace,
        display=Padding(
            f"Dataflow Endpoint: {{{COLOR_STR_FORMAT.format(color='bright_blue', value=endpoint_ref)}}}",
            (0, 0, 0, padding),
        ),
    )

    # extra properties
    for label, key in [
        # TODO - validate asset ref / colorize
        ("DeviceRegistry Asset Reference", "assetRef"),
        ("Schema Reference", "schemaRef"),
        # TODO - jsonschema
        ("Serialization Format", "serializationFormat"),
    ]:
        val = settings.get(key)
        if val:
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(f"{label}: {val}", (0, 0, 0, padding)),
            )

    # data source strings
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
    for label, key in [
        ("Schema Reference", "schemaRef"),
        ("Serialization Format", "serializationFormat"),
    ]:
        # TODO - validate endpoint ref
        val = settings.get(key)
        if val:
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(f"{label}: {val}", (0, 0, 0, padding)),
            )

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
            # TODO - schema ref json
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
        for label, key in [
            ("Description", "description"),
            ("Expression", "expression"),
            ("Operation Type", "type"),
        ]:
            # TODO - schema ref json
            val = filter.get(key)
            if val:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(f"{label}: {val}", (0, 0, 0, padding + 4)),
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
            # TODO - schema ref json
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
    check_manager: CheckManager, target: str, namespace: str, resource: dict, detail_level: int, padding: int
):
    settings = resource.get("destinationSettings", {})
    check_manager.add_display(
        target_name=target, namespace=namespace, display=Padding("\nDestination:", (0, 0, 0, padding))
    )
    padding += 4
    for label, key in [
        ("Data Destination", "dataDestination"),
        ("Dataflow Endpoint", "endpointRef"),
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
        ("Client ID Prefix", "clientIdPrefix"),
        ("MQTT Host", "host"),
        ("Keep Alive (s)", "keepAliveSeconds"),
        ("Max Inflight Messages", "maxInflightMessages"),
        ("Protocol", "protocol"),
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
        ("Compression", "compression"),
        ("Consumer Group ID", "consumerGroupId"),
        ("Copy MQTT Properties", "copyMqttProperties"),
        ("Kafka Host", "host"),
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

    batching = settings.get("batching", {})
    check_manager.add_display(
        target_name=target,
        namespace=namespace,
        display=Padding("Batching", (0, 0, 0, padding)),
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
        display=Padding("Batching", (0, 0, 0, padding)),
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
    settings = spec.get("datalakestoragesettings", {})
    for label, key in [("DataLake Host", "host")]:
        val = settings.get(key)
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
        display=Padding("Batching", (0, 0, 0, padding)),
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
    settings = spec.get("dataexplorersettings", {})
    for label, key in [("Database Name", "database"), ("Data Explorer Host", "host")]:
        val = settings.get(key)
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
        display=Padding("Batching", (0, 0, 0, padding)),
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
        check_manager.add_target(target_name=target, namespace=namespace)
        padding = 8
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(f"Dataflows in namespace {{[purple]{namespace}[/purple]}}", (0, 0, 0, padding)),
        )
        for dataflow in list(dataflows):
            padding = 8
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
            padding += 4
            mode = spec.get("mode")
            profile_ref = spec.get("profileRef")
            for label, val in [
                ("Dataflow Profile", f"{{{COLOR_STR_FORMAT.format(color='bright_blue', value=profile_ref)}}}"),
                ("Mode", mode),
            ]:
                # TODO - validate profile ref
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(f"{label}: {val}", (0, 0, 0, padding)),
                )
            operations = spec.get("operations", [])
            # TODO - error if no operations?
            processor_dict = {
                DataflowOperationType.source.value: _process_dataflow_sourcesettings,
                DataflowOperationType.builtin_transformation.value: _process_dataflow_transformationsettings,
                DataflowOperationType.destination.value: _process_dataflow_destinationsettings,
            }

            for operation in operations:
                # TODO - group by type
                # TODO - "Dataflow must have 3 operations max"
                # TODO - "Dataflow must have a local MQ source or a local MQ target."
                op_type = operation.get("operationType")
                if op_type and op_type.lower() not in processor_dict:
                    raise CLIInternalError(f"Invalid operation type {op_type}")
                processor_dict[op_type.lower()](
                    check_manager=check_manager,
                    target=target,
                    namespace=namespace,
                    resource=operation,
                    detail_level=detail_level,
                    padding=padding,
                )

            check_manager.add_target_eval(
                target_name=target,
                namespace=namespace,
                status=CheckTaskStatus.success.value,
                resource_name=dataflow_name,
                resource_kind=DataflowResourceKinds.DATAFLOW.value,
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
        check_manager.add_target(target_name=target, namespace=namespace)
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
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(
                    f"\n- Endpoint {{{COLOR_STR_FORMAT.format(color='bright_blue', value=endpoint_name)}}} {COLOR_STR_FORMAT.format(color='green', value='detected')}",
                    (0, 0, 0, padding),
                ),
            )
            # TODO - figure out status
            padding += 4
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(
                    f"Type: {COLOR_STR_FORMAT.format(color='bright_blue', value=endpoint_type)}", (0, 0, 0, padding)
                ),
            )

            # endpoint auth
            auth = spec.get("authentication", {})
            auth_method = auth.get("method")
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(f"Authentication Method: {auth_method}", (0, 0, 0, padding)),
            )

            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(f"Type: {COLOR_STR_FORMAT.format(color='bright_blue', value=endpoint_type)}", (0, 0, 0, padding)),
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
            if endpoint_type and endpoint_type.lower() not in endpoint_processor_dict:
                logger.warn(f"Unknown dataflow endpoint type: {endpoint_type}")

            endpoint_processor_dict[endpoint_type.lower()](check_manager=check_manager, target=target, namespace=namespace, spec=spec, detail_level=detail_level, padding=padding)

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
        check_manager.add_target(target_name=target, namespace=namespace)
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

            padding += 4
            # TODO - figure out status / conditions
            for label, key in [
                ("Instance Count", "instanceCount"),
            ]:
                val = spec.get(key)
                if val:
                    check_manager.add_display(
                        target_name=target,
                        namespace=namespace,
                        display=Padding(f"{label}: {val}", (0, 0, 0, padding)),
                    )
            diagnostics = spec.get("diagnostics", {})
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding("Diagnostic Logs:", (0, 0, 0, padding)),
            )
            diagnostic_logs = diagnostics.get("logs", {})
            diagnostic_log_level = diagnostic_logs.get("level")
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(f"Log Level: {diagnostic_log_level}", (0, 0, 0, padding + 4)),
            )
            diagnostic_log_otelconfig = diagnostic_logs.get("openTelemetryExportConfig", {})
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
