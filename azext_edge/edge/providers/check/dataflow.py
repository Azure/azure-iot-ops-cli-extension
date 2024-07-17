# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict, List

from azure.cli.core.azclierror import CLIInternalError
from rich.padding import Padding

from azext_edge.edge.providers.check.base.pod import process_pod_status
from azext_edge.edge.providers.check.base.resource import filter_resources_by_name
from azext_edge.edge.providers.edge_api.dataflow import (
    DATAFLOW_API_V1B1,
    DataflowResourceKinds,
)

from ...common import CheckTaskStatus
from ..base import get_namespaced_pods_by_prefix
from ..support.dataflow import DATAFLOW_NAME_LABEL, DATAFLOW_OPERATOR_PREFIX
from .base import (
    CheckManager,
    check_post_deployment,
    get_resources_by_name,
    get_resources_grouped_by_namespace,
)
from .common import (
    PADDING_SIZE,
    CoreServiceResourceKinds,
    DataflowEndpointType,
    DataflowOperationType,
    ResourceOutputDetailLevel,
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
        DataflowResourceKinds.DATAFLOW: evaluate_dataflows,
        DataflowResourceKinds.DATAFLOWENDPOINT: evaluate_dataflow_endpoints,
        DataflowResourceKinds.DATAFLOWPROFILE: evaluate_dataflow_profiles,
    }

    check_post_deployment(
        api_info=DATAFLOW_API_V1B1,
        check_name="enumerateDataflowApi",
        check_desc="Enumerate Dataflow API resources",
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
        check_name="evalDataflowRuntime",
        check_desc="Evaluate Dataflow Runtime Resources",
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
        check_manager.add_target(
            target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value
        )
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


def _process_dataflow_sourcesettings(check_manager: CheckManager, target: str, namespace: str, resource: dict):
    padding = 8
    settings = resource.get("sourceSettings", {})
    data_sources = settings.get("dataSources", [])
    check_manager.add_display(
        target_name=target,
        namespace=namespace,
        display=Padding("Data Sources", (0, 0, 0, padding))
    )
    for data_source in data_sources:
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(f"- {data_source}", (0, 0, 0, padding))
        )
    for label, key in [
        ("Dataflow Endpoint", "endpointRef"),
        ("DeviceRegistry Asset Reference:", "assetRef"),
        ("Schema Reference", "schemaRef"),
        # TODO - jsonschema
        ("Serialization Format", "serializationFormat"),
    ]:
        # TODO - validate endpoint ref
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(
                f"{label}: {settings.get(key)}",
                (0, 0, 0, padding)
            )
        )


def _process_dataflow_transformationsettings(check_manager: CheckManager, target: str, namespace: str, resource: dict):
    padding = 8
    settings = resource.get("builtInTransformationSettings", {})
    datasets = settings.get("datasets", [])
    for dataset in datasets:
        inputs = dataset.get("inputs", [])
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding("Dataset Inputs", (0, 0, 0, padding))
        )
        for input in inputs:
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(f"- {input}", (0, 0, 0, padding))
            )
        for label, key in [
            ("Description", "description"),
            ("Key", "key"),
            ("Expression", "expression"),
            ("Schema", "schemaRef"),
        ]:
            # TODO - schema ref json
            check_manager.add_display(
                target_name=target,
                namespace=namespace,

                display=Padding(
                    f"{label}: {dataset.get(key)}",
                    (0, 0, 0, padding)
                )
            )

    filters = settings.get("filter", [])
    for filter in filters:
        inputs = filter.get("inputs", [])
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding("Filter Inputs", (0, 0, 0, padding))
        )
        for input in inputs:
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(f"- {input}", (0, 0, 0, padding))
            )
        for label, key in [
            ("Description", "description"),
            ("Expression", "expression"),
            ("Operation Type", "type"),
        ]:
            # TODO - schema ref json
            check_manager.add_display(
                target_name=target,
                namespace=namespace,

                display=Padding(
                    f"{label}: {filter.get(key)}",
                    (0, 0, 0, padding)
                )
            )
    maps = settings.get("maps", [])
    for map in maps:
        inputs = map.get("inputs", [])
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding("Map Inputs", (0, 0, 0, padding))
        )
        for input in inputs:
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(f"- {input}", (0, 0, 0, padding))
            )
        for label, key in [
            ("Description", "description"),
            ("Expression", "expression"),
            ("Output", "output"),
            ("Transformation Type", "type"),
        ]:
            # TODO - schema ref json
            check_manager.add_display(
                target_name=target,
                namespace=namespace,

                display=Padding(
                    f"{label}: {filter.get(key)}",
                    (0, 0, 0, padding)
                )
            )
            # TODO - remaining values
    # "builtInTransformationSettings": {
    #     "schemaRef": "str",  # Optional. Reference to
    #       the schema that describes the output of the transformation.
    #     "serializationFormat": "str"  # Optional.
    #       Serialization format. Optional; defaults to JSON. Allowed value
    #       JSON Schema/draft-7, Parquet. Default: Json. Known values are:
    #       "Delta", "Json", and "Parquet".
    # },


def _process_dataflow_destinationsettings(check_manager: CheckManager, target: str, namespace: str, resource: dict):
    padding = 8
    settings = resource.get("destinationSettings", {})
    for label, key in [
        ("Data Destination", "dataDestination"),
        ("Dataflow Endpoint", "endpointRef"),
    ]:
        # TODO - validate endpoint ref
        check_manager.add_display(
            target_name=target,
            namespace=namespace,

            display=Padding(
                f"{label}: {settings.get(key)}",
                (0, 0, 0, padding)
            )
        )


def evaluate_dataflows(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
):
    check_manager = CheckManager(
        check_name="evalDataflows",
        check_desc="Evaluate Dataflows",
    )
    all_dataflows = get_resources_by_name(
        api_info=DATAFLOW_API_V1B1,
        kind=DataflowResourceKinds.DATAFLOW,
        resource_name=resource_name,
    )
    target = "dataflows.connectivity.iotoperations.azure.com"
    for namespace, dataflows in get_resources_grouped_by_namespace(all_dataflows):
        check_manager.add_target(target_name=target, namespace=namespace)
        padding = 8
        for dataflow in list(dataflows):
            spec = dataflow.get("spec", {})

            for label, key in [
                ("Mode", "mode"),
                ("Dataflow Profile", "profileRef"),
            ]:
                # TODO - validate profile ref
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(
                        f"{label}: {spec.get(key)}",
                        (0, 0, 0, padding)
                    )
                )

            operations = spec.get("operations", [])
            # TODO - error if no operations?
            processor_dict = {
                # TODO - enumerate source/transform/destination
                DataflowOperationType.source.value: _process_dataflow_sourcesettings,
                DataflowOperationType.builtin_transformation.value: _process_dataflow_transformationsettings,
                DataflowOperationType.destination.value: _process_dataflow_destinationsettings
            }

            for operation in operations:
                op_type = operation.get('operationType')
                if op_type not in processor_dict:
                    raise CLIInternalError(f"Invalid operation type {op_type}")
                processor_dict[op_type](check_manager=check_manager, target=target, namespace=namespace, resource=operation)

        # TODO - determine status
        check_manager.set_target_status(
            target_name=target,
            namespace=namespace,
            status=CheckTaskStatus.success.value,
        )
    return check_manager.as_dict(as_list=as_list)


def _process_endpoint_mqttsettings(
    check_manager: CheckManager, target: str, namespace: str, spec: dict
) -> None:
    padding = 8
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
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(f"{label}: {settings.get(key)}", (0, 0, 0, padding)),
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
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(f"{label}: {tls.get(key)}", (0, 0, 0, padding + 4)),
        )


def _process_endpoint_kafkasettings(
    check_manager: CheckManager, target: str, namespace: str, spec: dict
) -> None:
    padding = 8
    settings = spec.get("kafkaSettings", {})

    for label, key in [
        ("Compression", "compression"),
        ("Consumer Group ID", "consumerGroupId"),
        ("Copy MQTT Properties", "copyMqttProperties"),
        ("Kafka Host", "host"),
        ("Acks", "kafkaAcks"),
        ("Partition Strategy", "partitionStrategy"),
    ]:
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(f"{label}: {settings.get(key)}", (0, 0, 0, padding)),
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
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(f"{label}: {tls.get(key)}", (0, 0, 0, padding + 4)),
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
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(f"{label}: {batching.get(key)}", (0, 0, 0, padding + 4)),
        )


def _process_endpoint_fabriconelakesettings(
    check_manager: CheckManager, target: str, namespace: str, spec: dict
) -> None:
    padding = 8
    settings = spec.get("fabricOneLakeSettings", {})
    for label, key in [("Fabric Host", "host"), ("Path Type", "oneLakePathType")]:
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(f"{label}: {settings.get(key)}", (0, 0, 0, padding)),
        )

    names = settings.get("names", {})
    for label, key in [
        ("Lakehouse Name", "lakehouseName"),
        ("Workspace Name", "workspaceName"),
    ]:
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(f"{label}: {names.get(key)}", (0, 0, 0, padding)),
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
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(f"{label}: {batching.get(key)}", (0, 0, 0, padding)),
        )


def _process_endpoint_datalakestoragesettings(
    check_manager: CheckManager, target: str, namespace: str, spec: dict
) -> None:
    padding = 8
    settings = spec.get("datalakestoragesettings", {})
    for label, key in [("DataLake Host", "host")]:
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(f"{label}: {settings.get(key)}", (0, 0, 0, padding)),
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
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(f"{label}: {batching.get(key)}", (0, 0, 0, padding)),
        )


def _process_endpoint_dataexplorersettings(
    check_manager: CheckManager, target: str, namespace: str, spec: dict
) -> None:
    padding = 8
    settings = spec.get("dataexplorersettings", {})
    for label, key in [("Database Name", "database"), ("Data Explorer Host", "host")]:
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(f"{label}: {settings.get(key)}", (0, 0, 0, padding)),
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
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(f"{label}: {batching.get(key)}", (0, 0, 0, padding)),
        )


def _process_endpoint_localstoragesettings(
    check_manager: CheckManager, target: str, namespace: str, spec: dict
) -> None:
    # TODO - validate reference
    settings = spec.get("localStorageSettings", {})
    persistent_volume_claim = settings.get("persistentVolumeClaimRef", {}).get("name")
    check_manager.add_display(
        target_name=target,
        namespace=namespace,
        display=Padding(
            f"Persistent Volume Claim: {persistent_volume_claim}", (0, 0, 0, 8)
        ),
    )


def evaluate_dataflow_endpoints(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
):
    check_manager = CheckManager(
        check_name="evalDataflowEndpoints",
        check_desc="Evaluate Dataflow Endpoints",
    )
    all_endpoints = get_resources_by_name(
        api_info=DATAFLOW_API_V1B1,
        kind=DataflowResourceKinds.DATAFLOWENDPOINT,
        resource_name=resource_name,
    )
    target = "dataflowendpoints.connectivity.iotoperations.azure.com"
    for namespace, endpoints in get_resources_grouped_by_namespace(all_endpoints):
        check_manager.add_target(target_name=target, namespace=namespace)
        for endpoint in list(endpoints):
            spec = endpoint.get("spec", {})
            # TODO - figure out status

            endpoint_type = spec.get("endpointType")
            endpoint_processor_dict = {
                DataflowEndpointType.mqtt.value: _process_endpoint_mqttsettings,
                DataflowEndpointType.kafka.value: _process_endpoint_kafkasettings,
                DataflowEndpointType.fabric_onelake.value: _process_endpoint_fabriconelakesettings,
                DataflowEndpointType.datalake.value: _process_endpoint_datalakestoragesettings,
                DataflowEndpointType.data_explorer.value: _process_endpoint_dataexplorersettings,
                DataflowEndpointType.local_storage.value: _process_endpoint_localstoragesettings,
            }
            # process endpoint settings
            if endpoint_type not in endpoint_processor_dict:
                raise CLIInternalError(
                    f"Unknown dataflow endpoint type: {endpoint_type}"
                )

            endpoint_processor_dict[endpoint_type](
                check_manager, target, namespace, spec
            )

            # endpoint auth
            auth = spec.get("authentication", {})
            auth_method = auth.get("method")
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(f"Authentication Method: {auth_method}", (0, 0, 0, 0)),
            )

        check_manager.set_target_status(
            target_name=target,
            namespace=namespace,
            status=CheckTaskStatus.success.value,
        )

    return check_manager.as_dict(as_list=as_list)


def evaluate_dataflow_profiles(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
):
    check_manager = CheckManager(
        check_name="evalDataflowProfiles",
        check_desc="Evaluate Dataflow Profiles",
    )
    all_profiles = get_resources_by_name(
        api_info=DATAFLOW_API_V1B1,
        kind=DataflowResourceKinds.DATAFLOWPROFILE,
        resource_name=resource_name,
    )
    target = "dataflowprofiles.connectivity.iotoperations.azure.com"
    for namespace, profiles in get_resources_grouped_by_namespace(all_profiles):
        check_manager.add_target(target_name=target, namespace=namespace)    
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(profiles, (0, 0, 0, 0)),
        )
        check_manager.set_target_status(
            target_name=target,
            namespace=namespace,
            status=CheckTaskStatus.success.value,
        )
    return check_manager.as_dict(as_list=as_list)
