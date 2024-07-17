# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict, List

from azure.cli.core.azclierror import CLIInternalError

from azext_edge.edge.providers.check.base.pod import process_pod_status
from azext_edge.edge.providers.check.base.resource import filter_resources_by_name
from azext_edge.edge.providers.edge_api.dataflow import DATAFLOW_API_V1B1, DataflowResourceKinds
from .base import (
    CheckManager,
    check_post_deployment,
    get_resources_by_name,
    get_resources_grouped_by_namespace,
)

from rich.padding import Padding

from ...common import (
    CheckTaskStatus,
)

from .common import (
    PADDING_SIZE,
    CoreServiceResourceKinds,
    DataflowEndpointType,
    ResourceOutputDetailLevel,
)

from ..support.dataflow import DATAFLOW_NAME_LABEL, DATAFLOW_OPERATOR_PREFIX

from ..base import get_namespaced_pods_by_prefix


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
        check_manager.add_target(target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value)
        check_manager.add_display(
            target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value,
            display=Padding("Unable to fetch pods.", (0, 0, 0, padding + 2)),
        )

    for namespace, pods in get_resources_grouped_by_namespace(operators):
        check_manager.add_target(target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value, namespace=namespace)
        check_manager.add_display(
            target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value,
            namespace=namespace,
            display=Padding(
                f"Dataflow runtime resources in namespace {{[purple]{namespace}[/purple]}}", (0, 0, 0, padding)
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
        check_manager.add_display(target_name=target, namespace=namespace, display=Padding(dataflows, (0, 0, 0, 0)))
        check_manager.set_target_status(target_name=target, namespace=namespace, status=CheckTaskStatus.success.value)
    return check_manager.as_dict(as_list=as_list)


def _process_endpoint_mqttsettings(
    check_manager: CheckManager, target: str, namespace: str, mqttsettings: dict
) -> None:
    props = mqttsettings.get("properties", {})
# "mqttSettings": {
#     "clientIdPrefix": "str",  # Optional. Client ID prefix.
#         Client ID generated by the dataflow is :code:`<prefix>`-TBD. Optional; no
#         prefix if omitted.
#     "host": "aio-mq-dmqtt-frontend:1883",  # Optional. Default
#         value is "aio-mq-dmqtt-frontend:1883". Host of the Broker in the form of
#         :code:`<hostname>`::code:`<port>`. Optional; connects to Broker if
#         omitted.
#     "keepAliveSeconds": 60,  # Optional. Default value is 60.
#         Broker KeepAlive for connection in seconds.
#     "maxInflightMessages": 100,  # Optional. Default value is
#         100. The max number of messages to keep in flight. For subscribe, this is
#         the receive maximum. For publish, this is the maximum number of messages
#         to send before waiting for an ack.
#     "protocol": "str",  # Optional. Enable or disable websockets.
#         Known values are: "Mqtt" and "WebSockets".
#     "qos": 1,  # Optional. Default value is 1. Qos for Broker
#         connection.
#     "retain": "str",  # Optional. Whether or not to keep the
#         retain setting. Known values are: "Keep" and "Never".
#     "sessionExpirySeconds": 3600,  # Optional. Default value is
#         3600. Session expiry in seconds.
#     "tls": {
#         "mode": "str",  # Optional. Mode for TLS. Known
#             values are: "Enabled" and "Disabled".
#         "trustedCaCertificateConfigMapRef": "str"  #
#             Optional. Trusted CA certificate config map.
#     }
# },


def _process_endpoint_kafkasettings(
    check_manager: CheckManager, target: str, namespace: str, kafkasettings: dict
) -> None:
    props = kafkasettings.get("properties", {})
#     "kafkaSettings": {
#         "tls": {
#             "mode": "str",  # Optional. Mode for TLS. Known
#                 values are: "Enabled" and "Disabled".
#             "trustedCaCertificateConfigMapRef": "str"  #
#                 Optional. Trusted CA certificate config map.
#         },
#         "batching": {
#             "latencyMs": 5,  # Optional. Default value is 5.
#                 Batching latency in milliseconds.
#             "maxBytes": 1000000,  # Optional. Default value is
#                 1000000. Maximum number of bytes in a batch.
#             "maxMessages": 100000,  # Optional. Default value is
#                 100000. Maximum number of messages in a batch.
#             "mode": "str"  # Optional. Mode for batching. Known
#                 values are: "Enabled" and "Disabled".
#         },
#         "compression": "str",  # Optional. Compression. Can be none,
#             gzip, lz4, or snappy. No effect if the endpoint is used as a source.
#             Known values are: "None", "Gzip", "Snappy", and "Lz4".
#         "consumerGroupId": "str",  # Optional. Consumer group ID.
#         "copyMqttProperties": "str",  # Optional. Copy Broker
#             properties. No effect if the endpoint is used as a source or if the
#             dataflow doesn't have an Broker source. Known values are: "Enabled" and
#             "Disabled".
#         "host": "str",  # Optional. Kafka endpoint host.
#         "kafkaAcks": "str",  # Optional. Kafka acks. Can be all, one,
#             or zero. No effect if the endpoint is used as a source. Known values are:
#             "Zero", "One", and "All".
#         "partitionStrategy": "str"  # Optional. Partition handling
#             strategy. Can be default or static. No effect if the endpoint is used as
#             a source. Known values are: "Default", "Static", "Topic", and "Property".
# },


def _process_endpoint_fabriconelakesettings(
    check_manager: CheckManager, target: str, namespace: str, fabriconelakesettings: dict
) -> None:
    props = fabriconelakesettings.get("properties", {})
    # "fabricOneLakeSettings": {
    #     "host": "str",  # Host of the Microsoft Fabric in the form of
    #         https://:code:`<host>`.fabric.microsoft.com. Required.
    #     "names": {
    #         "lakehouseName": "str",  # Lakehouse name. Required.
    #         "workspaceName": "str"  # Workspace name. Required.
    #     },
    #     "oneLakePathType": "str",  # Type of location of the data in
    #         the workspace. Can be either tables or files. Required. Known values are:
    #         "Files" and "Tables".
    #     "batching": {
    #         "latencySeconds": 60,  # Optional. Default value is
    #             60. Batching latency in seconds.
    #         "maxMessages": 100000  # Optional. Default value is
    #             100000. Maximum number of messages in a batch.
    #     }
    # },


def _process_endpoint_datalakestoragesettings(
    check_manager: CheckManager, target: str, namespace: str, datalakestoragesettings: dict
) -> None:
    props = datalakestoragesettings.get("properties", {})
    #  "dataLakeStorageSettings": {
    #     "host": "str",  # Host of the Azure Data Lake in the form of
    #         :code:`<account>`.blob.core.windows.net . Required.
    #     "batching": {
    #         "latencySeconds": 60,  # Optional. Default value is
    #             60. Batching latency in seconds.
    #         "maxMessages": 100000  # Optional. Default value is
    #             100000. Maximum number of messages in a batch.
    #     }
    # },


def _process_endpoint_dataexplorersettings(
    check_manager: CheckManager, target: str, namespace: str, dataexplorersettings: dict
) -> None:
    props = dataexplorersettings.get("properties", {})
    # "dataExplorerSettings": {
    #   "database": "str",  # Database name. Required.
    #   "host": "str",  # Host of the Azure Data Explorer in the form
    #       of :code:`<cluster>`.:code:`<region>`.kusto.windows.net . Required.
    #   "batching": {
    #       "latencySeconds": 60,  # Optional. Default value is
    #           60. Batching latency in seconds.
    #       "maxMessages": 100000  # Optional. Default value is
    #           100000. Maximum number of messages in a batch.
    #   }
    # },


def _process_endpoint_localstoragesettings(
    check_manager: CheckManager, target: str, namespace: str, localstoragesettings: dict
) -> None:
    props = localstoragesettings.get("properties", {})
#     "localStorageSettings": {
#     "persistentVolumeClaimRef": "str"  # Persistent volume claim
#         name. Required.
# },


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
        check_manager.add_display(target_name=target, namespace=namespace, display=Padding(endpoints, (0, 0, 0, 0)))
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
                raise CLIInternalError(f"Unknown dataflow endpoint type: {endpoint_type}")
            
            endpoint_processor_dict[endpoint_type](check_manager, target, namespace, spec)

            # endpoint auth
            auth = spec.get("authentication", {})


        # spec:
        #   group: connectivity.iotoperations.azure.com
        #   names:
        #     kind: DataflowEndpoint
        #     listKind: DataflowEndpointList
        #     plural: dataflowendpoints
        #     singular: dataflowendpoint
        #   scope: Namespaced
        #   versions:
        #   - additionalPrinterColumns:
        #     - description: More information about current state
        #       jsonPath: .status.statusDescription
        #       name: Description
        #       type: string
        #     name: v1beta1
        #     schema:
        #       openAPIV3Schema:
        #         description: Auto-generated derived type for DataflowEndpointSpec via `CustomResource`
        #         properties:
        #           spec:
        #             properties:
        #               authentication:
        #                 oneOf:
        #                 - required:
        #                   - systemAssignedManagedIdentitySettings
        #                 - required:
        #                   - userAssignedManagedIdentitySettings
        #                 - required:
        #                   - x509CredentialsSettings
        #                 - required:
        #                   - saslSettings
        #                 - required:
        #                   - serviceAccountTokenSettings
        #                 - required:
        #                   - accessTokenSecretRef
        #                 properties:
        #                   accessTokenSecretRef:
        #                     type: string
        #                   method:
        #                     description: Selector used to determine which of the oneOf values
        #                       to use.
        #                     type: string
        #                   saslSettings:
        #                     properties:
        #                       saslType:
        #                         description: Type of SASL authentication. Can be PLAIN, SCRAM-SHA-256,
        #                           or SCRAM-SHA-512. Required.
        #                         enum:
        #                         - plain
        #                         - scramSha256
        #                         - scramSha512
        #                         type: string
        #                       tokenSecretName:
        #                         type: string
        #                     required:
        #                     - saslType
        #                     - tokenSecretName
        #                     type: object
        #                   serviceAccountTokenSettings:
        #                     properties:
        #                       audience:
        #                         description: Audience of the service account. Required.
        #                         type: string
        #                     required:
        #                     - audience
        #                     type: object
        #                   systemAssignedManagedIdentitySettings:
        #                     properties:
        #                       audience:
        #                         description: Audience of the service to authenticate against.
        #                           Optional; defaults to the audience for Azure Data Explorer
        #                           host configuration.
        #                         type: string
        #                     required:
        #                     - audience
        #                     type: object
        #                   userAssignedManagedIdentitySettings:
        #                     properties:
        #                       clientId:
        #                         description: Client ID for the user-assigned managed identity.
        #                           Required
        #                         type: string
        #                       scope:
        #                         description: Resource identifier (application ID URI) of the
        #                           resource, affixed with the .default suffix. Required.
        #                         type: string
        #                       tenantId:
        #                         description: Tenant ID. Required.
        #                         type: string
        #                     required:
        #                     - clientId
        #                     - scope
        #                     - tenantId
        #                     type: object
        #                   x509CredentialsSettings:
        #                     properties:
        #                       secretRef:
        #                         description: Secret name of the X.509 certificate. Required.
        #                         type: string
        #                     required:
        #                     - secretRef
        #                     type: object
        #                 required:
        #                 - method
        #                 type: object
        #               dataExplorerSettings:
        #                 properties:
        #                   batching:
        #                     default:
        #                       latencySeconds: 60
        #                       maxMessages: 100000
        #                     description: Batching configuration. Optional; no batching if
        #                       omitted.
        #                     properties:
        #                       latencySeconds:
        #                         default: 60
        #                         description: Batching latency in seconds. Optional; defaults
        #                           to 60.
        #                         format: uint16
        #                         maximum: 65535
        #                         minimum: 0
        #                         type: integer
        #                       maxMessages:
        #                         default: 100000
        #                         description: Maximum number of messages in a batch. Optional;
        #                           defaults to 100000.
        #                         format: uint32
        #                         maximum: 4294967295
        #                         minimum: 0
        #                         type: integer
        #                     type: object
        #                   database:
        #                     description: Database name. Required
        #                     type: string
        #                   host:
        #                     description: Host of the Azure Data Explorer in the form of <cluster>.<region>.kusto.windows.net.
        #                     pattern: .*\.*\.kusto\.windows\.net
        #                     type: string
        #                 required:
        #                 - database
        #                 - host
        #                 type: object
        #               datalakeStorageSettings:
        #                 properties:
        #                   batching:
        #                     default:
        #                       latencySeconds: 60
        #                       maxMessages: 100000
        #                     description: Batching configuration. Optional; no batching if
        #                       omitted.
        #                     properties:
        #                       latencySeconds:
        #                         default: 60
        #                         format: uint16
        #                         maximum: 65535
        #                         minimum: 0
        #                         type: integer
        #                       maxMessages:
        #                         default: 100000
        #                         format: uint32
        #                         maximum: 4294967295
        #                         minimum: 0
        #                         type: integer
        #                     type: object
        #                   host:
        #                     description: Host of the Azure Data Lake in the form of <account>.blob.core.windows.net.
        #                       Required.
        #                     pattern: .*\.blob\.core\.windows\.net
        #                     type: string
        #                 required:
        #                 - host
        #                 type: object
        #               endpointType:
        #                 description: Selector used to determine which of the oneOf values
        #                   to use.
        #                 type: string
        #               fabricOneLakeSettings:
        #                 properties:
        #                   batching:
        #                     default:
        #                       latencySeconds: 60
        #                       maxMessages: 100000
        #                     description: Batching configuration. Optional; no batching if
        #                       omitted.
        #                     properties:
        #                       latencySeconds:
        #                         default: 60
        #                         description: Batching latency in seconds. Optional; defaults
        #                           to 60.
        #                         format: uint16
        #                         maximum: 65535
        #                         minimum: 0
        #                         type: integer
        #                       maxMessages:
        #                         default: 100000
        #                         description: Maximum number of messages in a batch. Optional;
        #                           defaults to 100000.
        #                         format: uint32
        #                         maximum: 4294967295
        #                         minimum: 0
        #                         type: integer
        #                     type: object
        #                   host:
        #                     description: Host of the Microsoft Fabric in the form of https://<host>.fabric.microsoft.com.
        #                       Required.
        #                     pattern: .*\.fabric\.microsoft\.com
        #                     type: string
        #                   names:
        #                     description: Names of the workspace and lakehouse. Required.
        #                     properties:
        #                       lakehouseName:
        #                         description: Lakehouse name.
        #                         type: string
        #                       workspaceName:
        #                         description: Workspace name.
        #                         type: string
        #                     required:
        #                     - lakehouseName
        #                     - workspaceName
        #                     type: object
        #                   oneLakePathType:
        #                     description: Type of location of the data in the workspace. Can
        #                       be either tables or files. Required.
        #                     enum:
        #                     - Files
        #                     - Tables
        #                     type: string
        #                 required:
        #                 - host
        #                 - names
        #                 - oneLakePathType
        #                 type: object
        #               kafkaSettings:
        #                 properties:
        #                   batching:
        #                     default:
        #                       latencyMs: 5
        #                       maxBytes: 1000000
        #                       maxMessages: 100000
        #                       mode: Enabled
        #                     description: Batching configuration.
        #                     properties:
        #                       latencyMs:
        #                         default: 5
        #                         description: Batching latency in milliseconds.
        #                         format: uint16
        #                         maximum: 65535
        #                         minimum: 0
        #                         type: integer
        #                       maxBytes:
        #                         default: 1000000
        #                         description: Maximum number of bytes in a batch.
        #                         format: uint32
        #                         maximum: 4294967295
        #                         minimum: 0
        #                         type: integer
        #                       maxMessages:
        #                         default: 100000
        #                         description: Maximum number of messages in a batch.
        #                         format: uint32
        #                         maximum: 4294967295
        #                         minimum: 0
        #                         type: integer
        #                       mode:
        #                         default: Enabled
        #                         description: Mode for batching.
        #                         enum:
        #                         - Enabled
        #                         - enabled
        #                         - Disabled
        #                         - disabled
        #                         type: string
        #                     type: object
        #                   compression:
        #                     default: None
        #                     description: Compression. Can be none, gzip, lz4, or snappy. No
        #                       effect if the endpoint is used as a source.
        #                     enum:
        #                     - None
        #                     - Gzip
        #                     - Snappy
        #                     - Lz4
        #                     type: string
        #                   consumerGroupId:
        #                     description: Consumer group ID.
        #                     nullable: true
        #                     type: string
        #                   copyMqttProperties:
        #                     default: Disabled
        #                     description: Copy Broker properties. No effect if the endpoint
        #                       is used as a source or if the dataflow doesn't have an Broker
        #                       source.
        #                     enum:
        #                     - Enabled
        #                     - enabled
        #                     - Disabled
        #                     - disabled
        #                     type: string
        #                   host:
        #                     description: Kafka endpoint host.
        #                     nullable: true
        #                     type: string
        #                   kafkaAcks:
        #                     default: All
        #                     description: Kafka acks. Can be all, one, or zero. No effect if
        #                       the endpoint is used as a source.
        #                     enum:
        #                     - Zero
        #                     - One
        #                     - All
        #                     type: string
        #                   partitionStrategy:
        #                     default: Default
        #                     description: Partition handling strategy. Can be default or static.
        #                       No effect if the endpoint is used as a source.
        #                     enum:
        #                     - Default
        #                     - Static
        #                     - Topic
        #                     - Property
        #                     type: string
        #                   tls:
        #                     description: TLS configuration.
        #                     properties:
        #                       mode:
        #                         default: Disabled
        #                         description: Mode for TLS.
        #                         enum:
        #                         - Enabled
        #                         - Disabled
        #                         type: string
        #                       trustedCaCertificateConfigMapRef:
        #                         description: Trusted CA certificate config map.
        #                         nullable: true
        #                         type: string
        #                     type: object
        #                 required:
        #                 - tls
        #                 type: object
        #               localStorageSettings:
        #                 properties:
        #                   persistentVolumeClaimRef:
        #                     description: Persistent volume claim name.
        #                     type: string
        #                 required:
        #                 - persistentVolumeClaimRef
        #                 type: object
        #               mqttSettings:
        #                 properties:
        #                   clientIdPrefix:
        #                     description: Client ID prefix. Client ID generated by the dataflow
        #                       is <prefix>-TBD. Optional; no prefix if omitted.
        #                     nullable: true
        #                     type: string
        #                   host:
        #                     default: aio-mq-dmqtt-frontend:1883
        #                     description: Host of the MQTT broker in the form of <hostname>:<port>.
        #                       Optional; connects to MQ broker if omitted.
        #                     type: string
        #                   keepAliveSeconds:
        #                     default: 60
        #                     description: Broker `KeepAlive` for connection in seconds.
        #                     format: uint16
        #                     minimum: 0
        #                     type: integer
        #                   maxInflightMessages:
        #                     default: 100
        #                     description: The max number of messages to keep in flight. For
        #                       subscribe, this is the receive maximum. For publish, this is
        #                       the maximum number of messages to send before waiting for an
        #                       ack.
        #                     format: uint16
        #                     minimum: 0
        #                     type: integer
        #                   protocol:
        #                     default: Mqtt
        #                     description: Enable or disable websockets. Optional; defaults
        #                       to mqtt
        #                     enum:
        #                     - Mqtt
        #                     - WebSockets
        #                     type: string
        #                   qos:
        #                     default: 1
        #                     description: Qos for Broker connection.
        #                     format: uint8
        #                     maximum: 2
        #                     minimum: 0
        #                     type: integer
        #                   retain:
        #                     default: Keep
        #                     description: Whether or not to keep the retain setting. Optional;
        #                       defaults to true
        #                     enum:
        #                     - Keep
        #                     - Never
        #                     type: string
        #                   sessionExpirySeconds:
        #                     default: 3600
        #                     description: Session expiry in seconds. Optional; defaults to
        #                       3600
        #                     format: uint32
        #                     minimum: 0
        #                     type: integer
        #                   tls:
        #                     default:
        #                       mode: Disabled
        #                       trustedCaCertificateConfigMapRef: null
        #                     description: TLS configuration. Optional; omit for no TLS
        #                     properties:
        #                       mode:
        #                         default: Disabled
        #                         description: Mode for TLS.
        #                         enum:
        #                         - Enabled
        #                         - Disabled
        #                         type: string
        #                       trustedCaCertificateConfigMapRef:
        #                         description: Trusted CA certificate config map.
        #                         nullable: true
        #                         type: string
        #                     type: object
        #                 type: object
        #             required:
        #             - authentication
        #             - endpointType
        #             type: object
        #         required:
        #         - spec
        #         title: DataflowEndpoint
        #         type: object
        #     served: true
        #     storage: true
        #     subresources: {}
        # status:
        #   acceptedNames:
        #     kind: DataflowEndpoint
        #     listKind: DataflowEndpointList
        #     plural: dataflowendpoints
        #     singular: dataflowendpoint
        #   conditions:
        #   - lastTransitionTime: "2024-07-16T00:18:38Z"
        #     message: no conflicts found
        #     reason: NoConflicts
        #     status: "True"
        #     type: NamesAccepted
        #   - lastTransitionTime: "2024-07-16T00:18:38Z"
        #     message: the initial names have been accepted
        #     reason: InitialNamesAccepted
        #     status: "True"
        #     type: Established
        #   storedVersions:
        #   - v1beta1

        check_manager.set_target_status(target_name=target, namespace=namespace, status=CheckTaskStatus.success.value)

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
        check_manager.add_display(target_name=target, namespace=namespace, display=Padding(profiles, (0, 0, 0, 0)))
        check_manager.set_target_status(target_name=target, namespace=namespace, status=CheckTaskStatus.success.value)
    return check_manager.as_dict(as_list=as_list)
