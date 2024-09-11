# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List

from knack.log import get_logger
from rich.padding import Padding

from ...common import DEFAULT_DATAFLOW_PROFILE, CheckTaskStatus, ResourceState
from ..base import get_namespaced_pods_by_prefix
from ..edge_api.dataflow import DATAFLOW_API_V1B1, DataflowResourceKinds
from ..support.dataflow import DATAFLOW_NAME_LABEL, DATAFLOW_OPERATOR_PREFIX, DATAFLOW_PROFILE_POD_PREFIX
from .base import CheckManager, check_post_deployment, get_resources_by_name, get_resources_grouped_by_namespace
from .base.display import basic_property_display, colorize_string
from .base.pod import process_pod_status
from .base.resource import filter_resources_by_name
from .common import (
    DEFAULT_PADDING,
    DEFAULT_PROPERTY_DISPLAY_COLOR,
    PADDING_SIZE,
    CoreServiceResourceKinds,
    DataFlowEndpointAuthenticationType,
    DataflowEndpointType,
    DataflowOperationType,
    ResourceOutputDetailLevel,
)

logger = get_logger(__name__)

PADDING = DEFAULT_PADDING
INNER_PADDING = PADDING + PADDING_SIZE

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

valid_source_endpoint_types = [DataflowEndpointType.kafka.value, DataflowEndpointType.mqtt.value]


def _process_dataflow_sourcesettings(
    check_manager: CheckManager,
    target: str,
    namespace: str,
    dataflow_name: str,
    endpoints: List[dict],
    operation: dict,
    detail_level: int,
    padding: int,
):
    inner_padding = padding + PADDING_SIZE
    settings = operation.get("sourceSettings", {})

    # show endpoint ref
    # TODO - lots of shared code for validating source/dest endpoints, consider refactoring
    endpoint_ref = settings.get("endpointRef")

    # currently we are only looking for endpoint references in the same namespace
    # duplicate names should not exist, so check the first endpoint that matches the name ref
    endpoint_ref_string = "not found"
    endpoint_ref_status = endpoint_type_status = CheckTaskStatus.error
    endpoint_type_status_string = "invalid"

    found_endpoint = next(
        (endpoint for endpoint in endpoints if "name" in endpoint and endpoint["name"] == endpoint_ref), None
    )
    endpoint_type = found_endpoint["type"] if found_endpoint and "type" in found_endpoint else None

    if found_endpoint:
        endpoint_ref_status = CheckTaskStatus.success
        endpoint_ref_string = "detected"
        endpoint_type_valid = endpoint_type and endpoint_type.lower() in valid_source_endpoint_types
        endpoint_type_status = CheckTaskStatus.success if endpoint_type_valid else CheckTaskStatus.error
        endpoint_type_status_string = "valid" if endpoint_type_valid else f"has invalid type: {endpoint_type}"

    endpoint_ref_display = colorize_string(value=endpoint_ref_string, color=endpoint_ref_status.color)
    endpoint_validity_display = colorize_string(color=endpoint_type_status.color, value=endpoint_type_status_string)

    # valid endpoint ref eval
    check_manager.add_target_eval(
        target_name=target,
        namespace=namespace,
        status=endpoint_ref_status.value,
        resource_name=dataflow_name,
        resource_kind=DataflowResourceKinds.DATAFLOW.value,
        value={"spec.operations[*].sourceSettings.endpointRef": endpoint_ref},
    )

    # valid source endpoint type eval
    check_manager.add_target_eval(
        target_name=target,
        namespace=namespace,
        status=endpoint_type_status.value,
        resource_name=dataflow_name,
        resource_kind=DataflowResourceKinds.DATAFLOW.value,
        value={"ref(spec.operations[*].sourceSettings.endpointRef).endpointType": endpoint_type},
    )

    if detail_level > ResourceOutputDetailLevel.summary.value:
        check_manager.add_display(
            target_name=target, namespace=namespace, display=Padding("\nSource:", (0, 0, 0, padding))
        )
        endpoint_name_display = f"{{{colorize_string(value=endpoint_ref)}}}"
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(
                f"Dataflow Endpoint {endpoint_name_display} {endpoint_ref_display}, {endpoint_validity_display}",
                (0, 0, 0, padding + PADDING_SIZE),
            ),
        )
    elif not found_endpoint or not endpoint_type_valid:
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding("[red]Invalid source endpoint reference[/red]", (0, 0, 0, padding - PADDING_SIZE)),
        )

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
                    display=basic_property_display(label=label, value=val, padding=inner_padding),
                )

    # data source strings - not on summary
    if detail_level > ResourceOutputDetailLevel.summary.value:
        data_sources = settings.get("dataSources", [])
        if data_sources:
            check_manager.add_display(
                target_name=target, namespace=namespace, display=Padding("Data Sources:", (0, 0, 0, inner_padding))
            )
            for data_source in data_sources:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(f"- {colorize_string(data_source)}", (0, 0, 0, inner_padding + 2)),
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
        padding += PADDING_SIZE
        inner_padding = padding + PADDING_SIZE

        def _process_inputs(inputs: List[str]):
            if inputs:
                check_manager.add_display(
                    target_name=target, namespace=namespace, display=Padding("Inputs:", (0, 0, 0, inner_padding))
                )
                for input in inputs:
                    check_manager.add_display(
                        target_name=target,
                        namespace=namespace,
                        display=Padding(f"- {colorize_string(input)}", (0, 0, 0, inner_padding + 2)),
                    )

        # extra properties
        for datasets_label, key in [
            ("Schema Reference", "schemaRef"),
            ("Serialization Format", "serializationFormat"),
        ]:
            val = settings.get(key)
            if val:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=basic_property_display(label=datasets_label, value=val, padding=padding),
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
                            display=basic_property_display(label=label, value=val, padding=inner_padding),
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
                            display=basic_property_display(label=datasets_label, value=val, padding=padding),
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
                            display=basic_property_display(label=label, value=val, padding=inner_padding),
                        )
                inputs = map.get("inputs", [])
                _process_inputs(inputs)


def _process_dataflow_destinationsettings(
    check_manager: CheckManager,
    target: str,
    namespace: str,
    dataflow_name: str,
    endpoints: List[dict],
    operation: dict,
    detail_level: int,
    padding: int,
):
    settings = operation.get("destinationSettings", {})
    if detail_level > ResourceOutputDetailLevel.summary.value:
        check_manager.add_display(
            target_name=target, namespace=namespace, display=Padding("\nDestination:", (0, 0, 0, padding))
        )
    endpoint_ref = settings.get("endpointRef")

    # currently we are only looking for endpoint references in the same namespace
    # duplicate names should not exist, so check the first endpoint that matches the name ref
    endpoint_match = next(
        (endpoint for endpoint in endpoints if "name" in endpoint and endpoint["name"] == endpoint_ref), None
    )

    endpoint_validity = "valid"
    endpoint_status = CheckTaskStatus.success
    if not endpoint_match:
        endpoint_validity = "not found"
        endpoint_status = CheckTaskStatus.error
    # valid endpoint ref eval
    check_manager.add_target_eval(
        target_name=target,
        namespace=namespace,
        status=endpoint_status.value,
        resource_name=dataflow_name,
        resource_kind=DataflowResourceKinds.DATAFLOW.value,
        value={"spec.operations[*].destinationSettings.endpointRef": endpoint_ref},
    )
    # show dataflow endpoint ref on detail
    if detail_level > ResourceOutputDetailLevel.summary.value:
        padding += PADDING_SIZE
        endpoint_name_display = f"{{{colorize_string(value=endpoint_ref)}}}"
        endpoint_validity_display = colorize_string(color=endpoint_status.color, value=endpoint_validity)
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(
                f"Dataflow Endpoint {endpoint_name_display} {endpoint_validity_display}",
                (0, 0, 0, padding),
            ),
        )
    elif not endpoint_match:
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding("[red]Invalid destination endpoint reference[/red]", (0, 0, 0, padding - PADDING_SIZE)),
        )
    # only show destination on verbose
    if detail_level > ResourceOutputDetailLevel.detail.value:
        for label, key in [
            ("Data Destination", "dataDestination"),
        ]:
            val = settings.get(key)
            if val:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=basic_property_display(label=label, value=val, padding=padding),
                )


def _process_endpoint_authentication(
    endpoint_settings: dict, check_manager: CheckManager, target: str, namespace: str, padding: int, detail_level: int
) -> None:
    auth_property_dict = {
        DataFlowEndpointAuthenticationType.access_token.value: {
            "key": "accessTokenSettings",
            "displays": [
                ("Secret Reference", "secretRef"),
            ],
        },
        DataFlowEndpointAuthenticationType.system_assigned.value: {
            "key": "systemAssignedManagedIdentitySettings",
            "displays": [
                ("Audience", "audience"),
            ],
        },
        DataFlowEndpointAuthenticationType.user_assigned.value: {
            "key": "userAssignedManagedIdentitySettings",
            "displays": [
                ("Client ID", "clientId"),
                ("Scope", "scope"),
                ("Tenant ID", "tenantId"),
            ],
        },
        DataFlowEndpointAuthenticationType.x509.value: {
            "key": "x509CertificateSettings",
            "displays": [
                ("Secret Ref", "secretRef"),
            ],
        },
        DataFlowEndpointAuthenticationType.service_account_token.value: {
            "key": "serviceAccountTokenSettings",
            "displays": [
                ("Audience", "audience"),
            ],
        },
        DataFlowEndpointAuthenticationType.sasl.value: {
            "key": "saslSettings",
            "displays": [
                ("Type", "saslType"),
                ("Secret Ref", "secretRef"),
            ],
        },
        DataFlowEndpointAuthenticationType.anonymous.value: {
            "key": "anonymousSettings",
            "displays": [],
        },
    }

    auth: dict = endpoint_settings.get("authentication", {})
    auth_method = auth.get("method")

    # display unkown auth method
    if auth_method not in auth_property_dict:
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(f"[red]Unknown authentication method: {auth_method}", (0, 0, 0, padding)),
        )
        return

    # display auth method
    check_manager.add_display(
        target_name=target,
        namespace=namespace,
        display=basic_property_display(label="Authentication Method", value=auth_method, padding=padding),
    )

    # show details for various auth methods
    if detail_level > ResourceOutputDetailLevel.detail.value:
        auth_properties: dict = auth_property_dict.get(auth_method, {})
        auth_settings_key = auth_properties.get("key")
        auth_obj = auth.get(auth_settings_key)
        if auth_obj:
            for label, key in auth_properties.get("displays", []):
                val = auth_obj.get(key)
                if val:
                    check_manager.add_display(
                        target_name=target,
                        namespace=namespace,
                        display=basic_property_display(label=label, value=val, padding=padding + PADDING_SIZE),
                    )


def _process_endpoint_TLS(
    tls_settings: dict, check_manager: CheckManager, target: str, namespace: str, padding: int
) -> None:
    check_manager.add_display(
        target_name=target,
        namespace=namespace,
        display=Padding("TLS:", (0, 0, 0, padding)),
    )
    for label, key in [
        ("Mode", "mode"),
        ("Trusted CA ConfigMap", "trustedCaCertificateConfigMapRef"),
    ]:
        # TODO - validate ref?
        val = tls_settings.get(key)
        if val:
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=basic_property_display(label=label, value=val, padding=(padding + PADDING_SIZE)),
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
                display=basic_property_display(label=label, value=val, padding=padding),
            )

    # endpoint authentication details
    _process_endpoint_authentication(
        endpoint_settings=settings,
        check_manager=check_manager,
        target=target,
        namespace=namespace,
        padding=INNER_PADDING,
        detail_level=detail_level,
    )

    if detail_level > ResourceOutputDetailLevel.detail.value:
        for label, key in [
            ("Cloud Event Attributes", "cloudEventAttributes"),
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
                    display=basic_property_display(label=label, value=val, padding=padding),
                )

        # TLS
        tls = settings.get("tls", {})
        if tls:
            _process_endpoint_TLS(
                tls_settings=tls, check_manager=check_manager, target=target, namespace=namespace, padding=padding
            )


def _process_endpoint_kafkasettings(
    check_manager: CheckManager, target: str, namespace: str, spec: dict, detail_level: int, padding: int
) -> None:
    inner_padding = padding + PADDING_SIZE
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
                display=basic_property_display(label=label, value=val, padding=padding),
            )

    # endpoint authentication details
    _process_endpoint_authentication(
        endpoint_settings=settings,
        check_manager=check_manager,
        target=target,
        namespace=namespace,
        padding=INNER_PADDING,
        detail_level=detail_level,
    )

    if detail_level > ResourceOutputDetailLevel.detail.value:
        # extra properties
        for label, key in [
            ("Cloud Event Attributes", "cloudEventAttributes"),
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
                    display=basic_property_display(label=label, value=val, padding=padding),
                )
        # TLS
        tls = settings.get("tls", {})
        if tls:
            _process_endpoint_TLS(
                tls_settings=tls, check_manager=check_manager, target=target, namespace=namespace, padding=padding
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
                    display=basic_property_display(label=label, value=val, padding=inner_padding),
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
                display=basic_property_display(label=label, value=val, padding=padding),
            )

    # endpoint authentication details
    _process_endpoint_authentication(
        endpoint_settings=settings,
        check_manager=check_manager,
        target=target,
        namespace=namespace,
        padding=INNER_PADDING,
        detail_level=detail_level,
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
                    display=basic_property_display(label=label, value=val, padding=padding),
                )

        batching = settings.get("batching", {})
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding("Batching:", (0, 0, 0, padding)),
        )

        padding += PADDING_SIZE
        for label, key in [
            ("Latency (s)", "latencySeconds"),
            ("Max Messages", "maxMessages"),
        ]:
            val = batching.get(key)
            if val:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=basic_property_display(label=label, value=val, padding=padding),
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
                display=basic_property_display(label=label, value=val, padding=padding),
            )

    # endpoint authentication details
    _process_endpoint_authentication(
        endpoint_settings=settings,
        check_manager=check_manager,
        target=target,
        namespace=namespace,
        padding=INNER_PADDING,
        detail_level=detail_level,
    )

    if detail_level > ResourceOutputDetailLevel.detail.value:
        batching = settings.get("batching", {})
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding("Batching:", (0, 0, 0, padding)),
        )
        padding += PADDING_SIZE
        for label, key in [
            ("Latency (s)", "latencySeconds"),
            ("Max Messages", "maxMessages"),
        ]:
            val = batching.get(key)
            if val:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=basic_property_display(label=label, value=val, padding=padding),
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
                display=basic_property_display(label=label, value=val, padding=padding),
            )

    # endpoint authentication details
    _process_endpoint_authentication(
        endpoint_settings=settings,
        check_manager=check_manager,
        target=target,
        namespace=namespace,
        padding=INNER_PADDING,
        detail_level=detail_level,
    )

    if detail_level > ResourceOutputDetailLevel.detail.value:
        batching = settings.get("batching", {})
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding("Batching:", (0, 0, 0, padding)),
        )

        padding += PADDING_SIZE
        for label, key in [
            ("Latency (s)", "latencySeconds"),
            ("Max Messages", "maxMessages"),
        ]:
            val = batching.get(key)
            if val:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=basic_property_display(label=label, value=val, padding=padding),
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
    # endpoint authentication details
    _process_endpoint_authentication(
        endpoint_settings=settings,
        check_manager=check_manager,
        target=target,
        namespace=namespace,
        padding=INNER_PADDING,
        detail_level=detail_level,
    )


def check_dataflows_deployment(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_kinds: List[str] = None,
    resource_name: str = None,
) -> List[dict]:
    evaluate_funcs = {
        CoreServiceResourceKinds.RUNTIME_RESOURCE: evaluate_core_service_runtime,
        DataflowResourceKinds.DATAFLOWPROFILE: evaluate_dataflow_profiles,
        DataflowResourceKinds.DATAFLOWENDPOINT: evaluate_dataflow_endpoints,
        DataflowResourceKinds.DATAFLOW: evaluate_dataflows,
    }

    return check_post_deployment(
        api_info=DATAFLOW_API_V1B1,
        check_name=dataflow_api_check_name,
        check_desc=dataflow_api_check_desc,
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

    operators = get_namespaced_pods_by_prefix(
        prefix=DATAFLOW_OPERATOR_PREFIX,
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
            display=Padding("Unable to fetch pods.", (0, 0, 0, PADDING)),
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
                f"Dataflow operator in namespace {{[purple]{namespace}[/purple]}}",
                (0, 0, 0, PADDING),
            ),
        )

        process_pod_status(
            check_manager=check_manager,
            target_service_pod=f"pod/{DATAFLOW_OPERATOR_PREFIX}",
            target=CoreServiceResourceKinds.RUNTIME_RESOURCE.value,
            pods=pods,
            namespace=namespace,
            display_padding=PADDING + 2,
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

    # No dataflows - skip
    if not all_dataflows:
        no_dataflows_text = "No Dataflow resources detected in any namespace."
        check_manager.add_target(target_name=target)
        check_manager.add_target_eval(
            target_name=target, status=CheckTaskStatus.skipped.value, value={"dataflows": no_dataflows_text}
        )
        check_manager.add_display(
            target_name=target,
            display=Padding(no_dataflows_text, (0, 0, 0, PADDING)),
        )
        return check_manager.as_dict(as_list=as_list)
    for namespace, dataflows in get_resources_grouped_by_namespace(all_dataflows):
        check_manager.add_target(target_name=target, namespace=namespace)
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(f"Dataflows in namespace {{[purple]{namespace}[/purple]}}", (0, 0, 0, PADDING)),
        )
        # conditions
        check_manager.add_target_conditions(
            target_name=target,
            namespace=namespace,
            conditions=[
                # at least a source and destination operation
                "len(spec.operations)<=3",
                # valid source endpoint
                "spec.operations[*].sourceSettings.endpointRef",
                "ref(spec.operations[*].sourceSettings.endpointRef).endpointType in ('kafka','mqtt')",
                # valid destination endpoint
                "spec.operations[*].destinationSettings.endpointRef",
                # single source/destination
                "len(spec.operations[*].sourceSettings)==1",
                "len(spec.operations[*].destinationSettings)==1",
            ],
        )

        # profile names for reference lookup
        all_profiles = get_resources_by_name(
            api_info=DATAFLOW_API_V1B1,
            kind=DataflowResourceKinds.DATAFLOWPROFILE,
            namespace=namespace,
            resource_name=None,
        )
        profile_names = {profile.get("metadata", {}).get("name") for profile in all_profiles}

        all_endpoints = get_resources_by_name(
            api_info=DATAFLOW_API_V1B1,
            kind=DataflowResourceKinds.DATAFLOWENDPOINT,
            namespace=namespace,
            resource_name=None,
        )

        endpoints = [
            {"name": endpoint.get("metadata", {}).get("name"), "type": endpoint.get("spec", {}).get("endpointType")}
            for endpoint in all_endpoints
        ]

        for dataflow in list(dataflows):
            spec = dataflow.get("spec", {})
            dataflow_name = dataflow.get("metadata", {}).get("name")
            mode = spec.get("mode")
            mode_lower = str(mode).lower() if mode else "unknown"
            dataflow_enabled = mode_lower == "enabled"
            mode_display = colorize_string(value=mode_lower)
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(
                    f"\n- Dataflow {{{colorize_string(value=dataflow_name)}}} is {mode_display}",
                    (0, 0, 0, PADDING),
                ),
            )

            # if dataflow is disabled, skip evaluations and displays
            if not dataflow_enabled:
                check_manager.add_target_eval(
                    target_name=target,
                    namespace=namespace,
                    status=CheckTaskStatus.skipped.value,
                    resource_name=dataflow_name,
                    resource_kind=DataflowResourceKinds.DATAFLOW.value,
                    value={"spec.mode": mode},
                )
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(
                        colorize_string(
                            value=f"{CheckTaskStatus.skipped.emoji} Skipping evaluation of disabled dataflow",
                            color=CheckTaskStatus.skipped.color,
                        ),
                        (0, 0, 0, PADDING + 2),
                    ),
                )
                continue

            profile_ref = spec.get("profileRef")
            # profileRef is optional, only show an error if it exists but is invalid
            if profile_ref:
                profile_ref_status = (
                    CheckTaskStatus.error if profile_ref not in profile_names else CheckTaskStatus.success
                )

                # valid profileRef eval
                check_manager.add_target_eval(
                    target_name=target,
                    namespace=namespace,
                    status=profile_ref_status.value,
                    resource_name=dataflow_name,
                    resource_kind=DataflowResourceKinds.DATAFLOW.value,
                    value={"spec.profileRef": profile_ref},
                )

                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(
                        f"Dataflow Profile: {{{colorize_string(color=profile_ref_status.color, value=profile_ref)}}}",
                        (0, 0, 0, INNER_PADDING),
                    ),
                )
                if profile_ref_status == CheckTaskStatus.error:
                    check_manager.add_display(
                        target_name=target,
                        namespace=namespace,
                        display=Padding(
                            colorize_string(color=profile_ref_status.color, value="Invalid Dataflow Profile reference"),
                            (0, 0, 0, INNER_PADDING),
                        ),
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
                    display=Padding("Operations:", (0, 0, 0, INNER_PADDING)),
                )
            operation_padding = INNER_PADDING + PADDING_SIZE
            sources = destinations = 0
            for operation in operations:
                op_type = operation.get("operationType", "").lower()
                if op_type == DataflowOperationType.source.value:
                    sources += 1
                    _process_dataflow_sourcesettings(
                        check_manager=check_manager,
                        target=target,
                        namespace=namespace,
                        dataflow_name=dataflow_name,
                        endpoints=endpoints,
                        operation=operation,
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
                    destinations += 1
                    _process_dataflow_destinationsettings(
                        check_manager=check_manager,
                        target=target,
                        namespace=namespace,
                        dataflow_name=dataflow_name,
                        endpoints=endpoints,
                        operation=operation,
                        detail_level=detail_level,
                        padding=operation_padding,
                    )
            # eval source amount (1)
            sources_status = destinations_status = CheckTaskStatus.success.value
            if sources != 1:
                sources_status = CheckTaskStatus.error.value
                message = "Missing source operation" if sources == 0 else f"Too many source operations: {sources}"
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(f"[red]{message}[/red]", (0, 0, 0, INNER_PADDING)),
                )
            check_manager.add_target_eval(
                target_name=target,
                namespace=namespace,
                status=sources_status,
                resource_name=dataflow_name,
                resource_kind=DataflowResourceKinds.DATAFLOW.value,
                value={"len(spec.operations[*].sourceSettings)": sources},
            )

            if destinations != 1:
                destinations_status = CheckTaskStatus.error.value
                message = (
                    "Missing destination operation"
                    if destinations == 0
                    else f"Too many destination operations: {destinations}"
                )
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(f"[red]{message}[/red]", (0, 0, 0, INNER_PADDING)),
                )
            check_manager.add_target_eval(
                target_name=target,
                namespace=namespace,
                status=destinations_status,
                resource_name=dataflow_name,
                resource_kind=DataflowResourceKinds.DATAFLOW.value,
                value={"len(spec.operations[*].destinationSettings)": destinations},
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
    if not all_endpoints:
        no_endpoints_text = "No Dataflow Endpoints detected in any namespace."
        check_manager.add_target(target_name=target)
        check_manager.add_target_eval(
            target_name=target, status=CheckTaskStatus.skipped.value, value={"endpoints": no_endpoints_text}
        )
        check_manager.add_display(
            target_name=target,
            display=Padding(no_endpoints_text, (0, 0, 0, PADDING)),
        )
        return check_manager.as_dict(as_list=as_list)
    for namespace, endpoints in get_resources_grouped_by_namespace(all_endpoints):
        check_manager.add_target(target_name=target, namespace=namespace, conditions=["spec.endpointType"])
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(f"Dataflow Endpoints in namespace {{[purple]{namespace}[/purple]}}", (0, 0, 0, PADDING)),
        )
        for endpoint in list(endpoints):
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

            endpoint_string = f"Endpoint {{{colorize_string(value=endpoint_name)}}}"
            detected_string = colorize_string(color="green", value="detected")
            type_string = f"type: {colorize_string(color=DEFAULT_PROPERTY_DISPLAY_COLOR if valid_endpoint_type else 'red', value=endpoint_type)}"
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(
                    f"\n- {endpoint_string} {detected_string}, {type_string}",
                    (0, 0, 0, PADDING),
                ),
            )

            # endpoint details at higher detail levels
            if detail_level > ResourceOutputDetailLevel.summary.value:

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
                    endpoint_processor_dict[endpoint_type.lower()](
                        check_manager=check_manager,
                        target=target,
                        namespace=namespace,
                        spec=spec,
                        detail_level=detail_level,
                        padding=INNER_PADDING,
                    )
                else:
                    check_manager.add_display(
                        target_name=target,
                        namespace=namespace,
                        display=Padding(
                            colorize_string(color="red", value=f"Unknown endpoint type: {endpoint_type}"),
                            (0, 0, 0, INNER_PADDING),
                        ),
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
    target = dataflow_profile_target

    all_profiles = get_resources_by_name(
        api_info=DATAFLOW_API_V1B1,
        kind=DataflowResourceKinds.DATAFLOWPROFILE,
        resource_name=resource_name,
    )
    if not all_profiles:
        no_profiles_text = "No Dataflow Profiles detected in any namespace."
        check_manager.add_target(target_name=target)
        # if we may have manually filtered out the default profile by input, skip instead of warn
        default_profile_status = CheckTaskStatus.skipped if resource_name else CheckTaskStatus.warning
        check_manager.add_target_eval(
            target_name=target, status=default_profile_status.value, value={"profiles": no_profiles_text}
        )
        check_manager.add_display(
            target_name=target,
            display=Padding(no_profiles_text, (0, 0, 0, PADDING)),
        )
        return check_manager.as_dict(as_list=as_list)
    for namespace, profiles in get_resources_grouped_by_namespace(all_profiles):
        check_manager.add_target(
            target_name=target,
            namespace=namespace,
            conditions=["spec.instanceCount", f"[*].metadata.name=='{DEFAULT_DATAFLOW_PROFILE}'"],
        )
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(f"Dataflow Profiles in namespace {{[purple]{namespace}[/purple]}}", (0, 0, 0, PADDING)),
        )

        # warn if no default dataflow profile (unless possibly filtered)
        default_profile_status = CheckTaskStatus.skipped if resource_name else CheckTaskStatus.warning
        for profile in list(profiles):
            profile_name = profile.get("metadata", {}).get("name")
            # check for default dataflow profile
            if profile_name == DEFAULT_DATAFLOW_PROFILE:
                default_profile_status = CheckTaskStatus.success
            spec = profile.get("spec", {})
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(
                    f"\n- Profile {{{colorize_string(value=profile_name)}}} {colorize_string(color='green', value='detected')}",
                    (0, 0, 0, PADDING),
                ),
            )
            profile_status = profile.get("status", {})
            status_level = profile_status.get("configStatusLevel")
            status_description = profile_status.get("statusDescription")
            # add eval for status if present
            if profile_status:
                check_manager.add_target_eval(
                    target_name=target,
                    namespace=namespace,
                    resource_name=profile_name,
                    resource_kind=DataflowResourceKinds.DATAFLOWPROFILE.value,
                    status=ResourceState.map_to_status(status_level).value,
                    value={"status": profile_status},
                )
            # show status description (colorized) if it exists
            if status_description:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=basic_property_display(
                        label="Status",
                        value=status_description,
                        color=ResourceState.map_to_color(status_level),
                        padding=INNER_PADDING,
                    ),
                )
            instance_count = spec.get("instanceCount")
            has_instances = instance_count is not None and int(instance_count) >= 0
            instance_status = CheckTaskStatus.success if has_instances else CheckTaskStatus.error
            check_manager.add_target_eval(
                target_name=target,
                namespace=namespace,
                status=instance_status.value,
                resource_name=profile_name,
                resource_kind=DataflowResourceKinds.DATAFLOWPROFILE.value,
                value={"spec.instanceCount": instance_count},
            )
            if has_instances:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=basic_property_display(
                        label="Instance count", value=instance_count, color=instance_status.color, padding=INNER_PADDING
                    ),
                )
            else:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding("[red]No instance count set[/red]", (0, 0, 0, INNER_PADDING)),
                )

            # diagnostics on higher detail levels
            if detail_level > ResourceOutputDetailLevel.summary.value:
                log_padding = PADDING + PADDING_SIZE
                log_inner_padding = log_padding + PADDING_SIZE
                diagnostics = spec.get("diagnostics", {})
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding("Diagnostic Logs:", (0, 0, 0, log_padding)),
                )

                # diagnostic logs
                diagnostic_logs = diagnostics.get("logs", {})
                diagnostic_log_level = diagnostic_logs.get("level")
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=basic_property_display(
                        label="Log Level", value=diagnostic_log_level, padding=log_inner_padding
                    ),
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
                                    display=basic_property_display(label=label, value=val, padding=log_inner_padding),
                                )

                    # diagnostic metrics
                    diagnostic_metrics = diagnostics.get("metrics", {})
                    check_manager.add_display(
                        target_name=target,
                        namespace=namespace,
                        display=Padding("Diagnostic Metrics:", (0, 0, 0, log_padding)),
                    )

                    diagnostic_metrics_prometheusPort = diagnostic_metrics.get("prometheusPort")
                    check_manager.add_display(
                        target_name=target,
                        namespace=namespace,
                        display=basic_property_display(
                            label="Prometheus Port", value=diagnostic_metrics_prometheusPort, padding=log_inner_padding
                        ),
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
                                    display=basic_property_display(label=label, value=val, padding=log_inner_padding),
                                )
            # pod health - trailing `-` is important in case profiles have similar prefixes
            pod_prefix = f"{DATAFLOW_PROFILE_POD_PREFIX}{profile_name}-"
            profile_pods = get_namespaced_pods_by_prefix(
                prefix=pod_prefix,
                namespace=namespace,
                label_selector=DATAFLOW_NAME_LABEL,
            )
            # only show pods if they exist
            if profile_pods:
                process_pod_status(
                    check_manager=check_manager,
                    target_service_pod=f"pod/{pod_prefix}",
                    target=target,
                    pods=profile_pods,
                    namespace=namespace,
                    display_padding=INNER_PADDING,
                    detail_level=detail_level,
                )

        # default dataflow profile status, display warning if not success
        check_manager.add_target_eval(
            target_name=target,
            namespace=namespace,
            status=default_profile_status.value,
            resource_kind=DataflowResourceKinds.DATAFLOWPROFILE.value,
            resource_name=DEFAULT_DATAFLOW_PROFILE,
            value={f"[*].metadata.name=='{DEFAULT_DATAFLOW_PROFILE}'": default_profile_status.value},
        )
        if default_profile_status not in [CheckTaskStatus.success, CheckTaskStatus.skipped]:
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(
                    colorize_string(
                        color=default_profile_status.color,
                        value=f"\nDefault Dataflow Profile '{DEFAULT_DATAFLOW_PROFILE}' not found in namespace '{namespace}'",
                    ),
                    (0, 0, 0, PADDING),
                ),
            )

    return check_manager.as_dict(as_list=as_list)
