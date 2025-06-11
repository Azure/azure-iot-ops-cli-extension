# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""
CLI parameter definitions.
"""

from azure.cli.core.commands.parameters import (
    get_enum_type,
    get_three_state_flag,
    tags_type,
)
from knack.arguments import CaseInsensitiveList

from azext_edge.edge.providers.edge_api.dataflow import DataflowResourceKinds

from ._validators import (
    validate_namespace,
    validate_resource_name,
)
from .common import OpsServiceType
from .providers.check.common import ResourceOutputDetailLevel
from .providers.edge_api import (
    DeviceRegistryResourceKinds,
    MqResourceKinds,
)
from .providers.orchestration.common import (
    EXTENSION_MONIKER_TO_ALIAS_MAP,
    TRUST_SETTING_KEYS,
    X509_ISSUER_REF_KEYS,
    AuthenticationSaslType,
    CloneSummaryMode,
    CloneTemplateMode,
    CloneTemplateParams,
    ConfigSyncModeType,
    DataflowEndpointAuthenticationType,
    DataflowEndpointFabricPathType,
    DataflowEndpointKafkaAcksType,
    IdentityUsageType,
    KafkaCloudEventAttributeType,
    KafkaCompressionType,
    KafkaPartitionStrategyType,
    KubernetesDistroType,
    ListenerProtocol,
    MqMemoryProfile,
    MqServiceType,
    MqttRetainType,
    SchemaFormat,
    SchemaType,
    TlsKeyAlgo,
    TlsKeyRotation,
)


def load_iotops_arguments(self, _):
    """
    Load CLI Args for Knack parser
    """

    with self.argument_context("iot ops") as context:
        context.argument(
            "context_name",
            options_list=["--context"],
            help="Kubeconfig context name to use for k8s cluster communication. "
            "If no context is provided current_context is used.",
            arg_group="K8s Cluster",
        )
        context.argument(
            "namespace",
            options_list=["--namespace", "-n"],
            help="K8s cluster namespace the command should operate against. "
            "If no namespace is provided the kubeconfig current_context namespace will be used. "
            "If not defined, the fallback value `azure-iot-operations` will be used. ",
            validator=validate_namespace,
        )
        context.argument(
            "confirm_yes",
            options_list=["--yes", "-y"],
            arg_type=get_three_state_flag(),
            help="Confirm [y]es without a prompt. Useful for CI and automation scenarios.",
        )
        context.argument(
            "no_progress",
            options_list=["--no-progress"],
            arg_type=get_three_state_flag(),
            help="Disable visual representation of work.",
        )
        context.argument(
            "force",
            options_list=["--force"],
            arg_type=get_three_state_flag(),
            help="Force the operation to execute.",
        )
        context.argument(
            "tags",
            options_list=["--tags"],
            arg_type=tags_type,
        )
        context.argument(
            "instance_name",
            options_list=["--name", "-n"],
            help="IoT Operations instance name.",
        )
        context.argument(
            "instance_description",
            options_list=["--description"],
            help="Description of the IoT Operations instance.",
        )
        context.argument(
            "broker_name",
            options_list=["--broker", "-b"],
            help="Mqtt broker name.",
        )
        context.argument(
            "mi_user_assigned",
            options_list=["--mi-user-assigned"],
            help="The resource Id for the desired user-assigned managed identity to use with the instance.",
        )
        context.argument(
            "federated_credential_name",
            options_list=["--fc"],
            help="The federated credential name.",
        )
        context.argument(
            "use_self_hosted_issuer",
            options_list=["--self-hosted-issuer"],
            arg_type=get_three_state_flag(),
            help="Use the self-hosted oidc issuer for federation.",
        )
        context.argument(
            "config_file",
            options_list=["--config-file"],
            help="Path to a config file containing resource properties in json format. The config file "
            "should contain an object with properties compatible with the ARM representation of the resource. "
            "The object correlates directly with 'properties:{}' of the ARM resource.",
            arg_group="Config",
        )
        context.argument(
            "show_config",
            options_list=["--show-config"],
            arg_type=get_three_state_flag(),
            help="Show the generated resource config instead of invoking the API with it.",
        )
        context.argument(
            "custom_role_id",
            options_list=["--custom-role-id"],
            help="Fully qualified role definition Id in the following format: "
            "/subscriptions/{subscriptionId}/providers/Microsoft.Authorization/roleDefinitions/{roleId}",
        )
        context.argument(
            "skip_role_assignments",
            options_list=["--skip-ra"],
            arg_type=get_three_state_flag(),
            help="When used the role assignment step of the operation will be skipped.",
        )

    with self.argument_context("iot ops identity") as context:
        context.argument(
            "usage_type",
            options_list=["--usage"],
            arg_type=get_enum_type(IdentityUsageType),
            help="Indicates the usage type of the associated identity.",
        )

    with self.argument_context("iot ops show") as context:
        context.argument(
            "show_tree",
            options_list=["--tree"],
            arg_type=get_three_state_flag(),
            help="Use to visualize the IoT Operations deployment against the backing cluster.",
        )

    with self.argument_context("iot ops support") as context:
        context.argument(
            "ops_services",
            nargs="+",
            action="extend",
            options_list=["--ops-service", "--svc"],
            choices=CaseInsensitiveList(OpsServiceType.list()),
            help="The IoT Operations service the support bundle creation should apply to. "
            "If no service is provided, the operation will default to capture all services. "
            "--ops-service can be used one or more times.",
        )
        context.argument(
            "log_age_seconds",
            options_list=["--log-age"],
            help="Container log age in seconds.",
            type=int,
        )
        context.argument(
            "bundle_dir",
            options_list=["--bundle-dir"],
            help="The local directory the produced bundle will be saved to. "
            "If no directory is provided the current directory is used.",
        )
        context.argument(
            "include_mq_traces",
            options_list=["--broker-traces"],
            arg_type=get_three_state_flag(),
            help="Include mqtt broker traces in the support bundle. "
            "Usage may add considerable size to the produced bundle.",
        )

    with self.argument_context("iot ops check") as context:
        context.argument(
            "pre_deployment_checks",
            options_list=["--pre"],
            help="Run pre-requisite checks to determine if the minimum "
            "requirements of a service deployment are fulfilled.",
            arg_type=get_three_state_flag(),
        )
        context.argument(
            "post_deployment_checks",
            options_list=["--post"],
            help="Run post-deployment checks.",
            arg_type=get_three_state_flag(),
        )
        context.argument(
            "as_object",
            options_list=["--as-object"],
            help="Output check content and validations in a CI friendly data structure.",
            arg_type=get_three_state_flag(),
            arg_group="Format",
        )
        context.argument(
            "ops_service",
            options_list=["--ops-service", "--svc"],
            choices=CaseInsensitiveList(OpsServiceType.list_check_services()),
            help="The IoT Operations service deployment that will be evaluated.",
        )
        context.argument(
            "resource_kinds",
            nargs="*",
            options_list=["--resources"],
            choices=CaseInsensitiveList(
                set(
                    [
                        DeviceRegistryResourceKinds.ASSET.value,
                        DeviceRegistryResourceKinds.ASSETENDPOINTPROFILE.value,
                        MqResourceKinds.BROKER.value,
                        MqResourceKinds.BROKER_LISTENER.value,
                        MqResourceKinds.BROKER_AUTHENTICATION.value,
                        MqResourceKinds.BROKER_AUTHORIZATION.value,
                        DataflowResourceKinds.DATAFLOW.value,
                        DataflowResourceKinds.DATAFLOWENDPOINT.value,
                        DataflowResourceKinds.DATAFLOWPROFILE.value,
                    ]
                )
            ),
            help="Only run checks on specific resource kinds. Use space-separated values.",
        ),
        context.argument(
            "detail_level",
            options_list=["--detail-level"],
            default=ResourceOutputDetailLevel.summary.value,
            choices=ResourceOutputDetailLevel.list(),
            arg_type=get_enum_type(ResourceOutputDetailLevel),
            help="Controls the level of detail displayed in the check output. "
            "Choose 0 for a summary view (minimal output), "
            "1 for a detailed view (more comprehensive information), "
            "or 2 for a verbose view (all available information).",
        ),
        context.argument(
            "resource_name",
            options_list=["--resource-name", "--rn"],
            help="Only run checks for the specific resource name. "
            "The name is case insensitive. "
            "Glob patterns '*' and '?' are supported. "
            "Note: Only alphanumeric characters, hyphens, '?' and '*' are allowed.",
            validator=validate_resource_name,
        ),

    with self.argument_context("iot ops dataflow") as context:
        context.argument(
            "instance_name",
            options_list=["--instance", "-i"],
            help="IoT Operations instance name.",
        )
        context.argument(
            "dataflow_name",
            options_list=["--name", "-n"],
            help="Dataflow name.",
        )
        context.argument(
            "profile_name",
            options_list=["--profile", "-p"],
            help="Dataflow profile name.",
        )

    with self.argument_context("iot ops dataflow profile") as context:
        context.argument(
            "profile_name",
            options_list=["--name", "-n"],
            help="Dataflow profile name.",
        )
        context.argument(
            "profile_instances",
            type=int,
            options_list=["--profile-instances"],
            help="The number of pods that run associated dataflows. Min value: 1, max value: 20.",
        )
        context.argument(
            "log_level",
            options_list=["--log-level"],
            help="The level of detail given in diagnostic logs. "
            "Levels: 'error', 'warn', 'info', 'debug', 'trace', 'off'. "
            "For advanced usage you can specify a comma-separated list of module=level pairs.",
        )

    with self.argument_context("iot ops dataflow endpoint") as context:
        # TODO: move dataflow params to separate file
        context.argument(
            "endpoint_name",
            options_list=["--name", "-n"],
            help="Dataflow endpoint name.",
        )
        context.argument(
            "authentication_type",
            options_list=["--auth-type"],
            choices=CaseInsensitiveList(
                [
                    DataflowEndpointAuthenticationType.ACCESSTOKEN.value,
                    DataflowEndpointAuthenticationType.SASL.value,
                    DataflowEndpointAuthenticationType.SERVICEACCESSTOKEN.value,
                    DataflowEndpointAuthenticationType.SYSTEMASSIGNED.value,
                    DataflowEndpointAuthenticationType.USERASSIGNED.value,
                    DataflowEndpointAuthenticationType.X509.value,
                ]
            ),
            help="The authentication type for the dataflow endpoint. "
            "Note: When not specified, the authentication type is determinded by other authentication parameters.",
        )
        context.argument(
            "client_id",
            options_list=["--client-id", "--cid"],
            help="The client ID of the user assigned identity",
            arg_group="User Assigned Managed Identity",
        )
        context.argument(
            "scope",
            options_list=["--scope"],
            help="Resource identifier (application ID URI) of the resource, affixed with the .default suffix.",
            arg_group="User Assigned Managed Identity",
        )
        context.argument(
            "tenant_id",
            options_list=["--tenant-id", "--tid"],
            help="The tenant ID of the user assigned identity.",
            arg_group="User Assigned Managed Identity",
        )
        context.argument(
            "no_auth",
            options_list=["--no-auth"],
            arg_type=get_three_state_flag(),
            help="No authentication for the endpoint.",
        )
        context.argument(
            "latency",
            options_list=["--latency", "-l"],
            help="The batching latency in seconds. Min value: 0, max value: 65535.",
            type=int,
            arg_group="Batching Configuration",
        )
        context.argument(
            "message_count",
            options_list=["--message-count", "--mc"],
            help="Maximum number of messages in a batch. Min value: 0, max value: 4294967295.",
            type=int,
            arg_group="Batching Configuration",
        )
        context.argument(
            "audience",
            options_list=["--audience", "--aud"],
            help="Audience of the service to authenticate against.",
            arg_group="System Assigned Managed Identity",
        )
        context.argument(
            "acks",
            options_list=["--acks"],
            arg_type=get_enum_type(DataflowEndpointKafkaAcksType, default=DataflowEndpointKafkaAcksType.ALL.value),
            help="Level of acknowledgment from the Kafka broker to "
            "ensure that the message sent by producer is successfully "
            "written to the topic and replicated across the Kafka cluster.",
        )
        context.argument(
            "batching_disabled",
            options_list=["--disable-batching", "--db"],
            arg_type=get_three_state_flag(),
            help="Disable batching.",
            arg_group="Batching Configuration",
        )
        context.argument(
            "max_bytes",
            options_list=["--max-bytes", "--mb"],
            help="Maximum number of bytes in a batch.",
            type=int,
            arg_group="Batching Configuration",
        )
        context.argument(
            "cloud_event_attribute",
            options_list=["--cloud-event-attribute", "--cea"],
            arg_type=get_enum_type(
                KafkaCloudEventAttributeType,
                default=KafkaCloudEventAttributeType.PROPAGATE.value,
            ),
            help="CloudEvent settings type to map events to cloud. "
            "Different message format are required by different setting.",
            arg_group="Cloud Event",
        )
        context.argument(
            "compression",
            options_list=["--compression"],
            arg_type=get_enum_type(KafkaCompressionType, default=KafkaCompressionType.NONE.value),
            help="Compression type for the messages sent to Kafka topics.",
        )
        context.argument(
            "config_map_reference",
            options_list=["--config-map-ref", "--cm"],
            help="Config map reference for Trusted CA certificate for Kafka/MQTT endpoint. "
            "Note: This ConfigMap should contain the CA certificate in PEM format. "
            "The ConfigMap must be in the same namespace as the Kafka/MQTT data flow resource.",
            arg_group="Transport Layer Security (TLS)",
        )
        context.argument(
            "copy_broker_props_disabled",
            options_list=["--disable-broker-props-copy", "--dbpc"],
            arg_type=get_three_state_flag(),
            help="Disable MQTT broker properties copy to Kafka user headers.",
        )
        context.argument(
            "group_id",
            options_list=["--group-id", "--gid"],
            help="ID of consumer group that the data flow uses to read messages " "from the Kafka topic.",
        )
        context.argument(
            "partition_strategy",
            options_list=["--partition-strategy", "--ps"],
            arg_type=get_enum_type(KafkaPartitionStrategyType, default=KafkaPartitionStrategyType.DEFAULT.value),
            help="The partition handling strategy controls how messages are "
            "assigned to Kafka partitions when sending them to Kafka topics.",
        )
        context.argument(
            "sasl_type",
            options_list=["--sasl-type"],
            arg_type=get_enum_type(AuthenticationSaslType, default=None),
            help="The type of SASL authentication.",
            arg_group="SASL Authentication",
        )
        context.argument(
            "tls_disabled",
            options_list=["--disable-tls"],
            arg_type=get_three_state_flag(),
            help="The data flow uses an insecure connection to the Kafka/MQTT broker.",
            arg_group="Transport Layer Security (TLS)",
        )
        context.argument(
            "client_id_prefix",
            options_list=["--client-id-prefix"],
            help="The client id prefix for MQTT client. "
            "Note: Changing the client ID prefix after IoT "
            "Operations deployment might result in data loss.",
        )
        context.argument(
            "keep_alive",
            options_list=["--keep-alive", "--ka"],
            help="The maximum time in seconds that the data flow client can "
            "be idle before sending a PINGREQ message to the broker. "
            "Min value: 0.",
            type=int,
        )
        context.argument(
            "max_inflight_messages",
            options_list=["--max-inflight-msg", "--mim"],
            help="The maximum number of inflight messages that the data flow MQTT client can have. Min value: 0.",
            type=int,
        )
        context.argument(
            "protocol",
            options_list=["--protocol"],
            arg_type=get_enum_type(ListenerProtocol, default=ListenerProtocol.MQTT.value),
            help="Protocol to use for client connections.",
        )
        context.argument(
            "qos",
            options_list=["--qos"],
            help="Quality of Service (QoS) level for the MQTT messages. Only 0 or 1 are supported.",
            type=int,
        )
        context.argument(
            "retain",
            options_list=["--retain"],
            arg_type=get_enum_type(MqttRetainType, default=MqttRetainType.KEEP.value),
            help="Retain setting to specify whether the data flow should keep the retain "
            "flag on MQTT messages. Setting this ensures whether or not the remote broker "
            "has the same messages retained as the local broker.",
        )
        context.argument(
            "session_expiry",
            options_list=["--session-expiry"],
            help="The session expiry interval in seconds for the data flow MQTT client. " "Min value: 0.",
            type=int,
        )

    for cmd_space in ["iot ops dataflow endpoint create adx", "iot ops dataflow endpoint update adx"]:
        with self.argument_context(cmd_space) as context:
            context.argument(
                "database_name",
                options_list=["--database", "--db"],
                help="The name of the Azure Data Explorer database.",
            )
            context.argument(
                "host",
                options_list=["--host"],
                help="Host of the Azure Data Explorer is "
                "Azure Data Explorer cluster URI. In the form "
                "of https://cluster.region.kusto.windows.net",
            )
            context.argument(
                "authentication_type",
                options_list=["--auth-type"],
                choices=CaseInsensitiveList(
                    [
                        DataflowEndpointAuthenticationType.SYSTEMASSIGNED.value,
                        DataflowEndpointAuthenticationType.USERASSIGNED.value,
                    ]
                ),
            )

    for cmd_space in [
        "iot ops dataflow endpoint create adls",
        "iot ops dataflow endpoint update adls",
    ]:
        with self.argument_context(cmd_space) as context:
            context.argument(
                "secret_name",
                options_list=["--secret-name", "-s"],
                help="The name for the kubernetes secret that contains SAS token.",
                arg_group="Access Token",
            )
            context.argument(
                "storage_account_name",
                options_list=["--storage-account", "--sa"],
                help="The name of Azure Data Lake Storage Gen2 account.",
            )
            context.argument(
                "authentication_type",
                options_list=["--auth-type"],
                choices=CaseInsensitiveList(
                    [
                        DataflowEndpointAuthenticationType.SYSTEMASSIGNED.value,
                        DataflowEndpointAuthenticationType.USERASSIGNED.value,
                        DataflowEndpointAuthenticationType.ACCESSTOKEN.value,
                    ]
                ),
            )

    for cmd_space in [
        "iot ops dataflow endpoint create fabric-onelake",
        "iot ops dataflow endpoint update fabric-onelake",
    ]:
        with self.argument_context(cmd_space) as context:
            context.argument(
                "workspace_name",
                options_list=["--workspace"],
                help="The Microsoft Fabric workspace name. Note: The default 'my workspace' isn't supported.",
            )
            context.argument(
                "lakehouse_name",
                options_list=["--lakehouse"],
                help="The Microsoft Fabric lakehouse name under provided workspace.",
            )
            context.argument(
                "path_type",
                options_list=["--path-type", "--pt"],
                arg_type=get_enum_type(DataflowEndpointFabricPathType, default=None),
                help="The type of path used in OneLake.",
            )
            context.argument(
                "authentication_type",
                options_list=["--auth-type"],
                choices=CaseInsensitiveList(
                    [
                        DataflowEndpointAuthenticationType.SYSTEMASSIGNED.value,
                        DataflowEndpointAuthenticationType.USERASSIGNED.value,
                    ]
                ),
            )

    for cmd_space in [
        "iot ops dataflow endpoint create eventhub",
        "iot ops dataflow endpoint update eventhub",
    ]:
        with self.argument_context(cmd_space) as context:
            context.argument(
                "eventhub_namespace",
                options_list=["--eventhub-namespace", "--ehns"],
                help="The name of the Event Hubs namespace.",
            )
            context.argument(
                "latency",
                options_list=["--latency", "-l"],
                help="The batching latency in milliseconds. Min value: 0, max value: 65535.",
                type=int,
                arg_group="Batching Configuration",
            )
            context.argument(
                "secret_name",
                options_list=["--secret-name", "-s"],
                help="The name for the kubernetes secret that contains event hub connection string. "
                "Note: The secret must be in the same namespace as the Kafka data flow endpoint. "
                "The secret must have both the username and password as key-value pairs. "
                "For more information about secret format, please refer to link in command description.",
                arg_group="SASL Authentication",
            )
            context.argument(
                "authentication_type",
                options_list=["--auth-type"],
                choices=CaseInsensitiveList(
                    [
                        DataflowEndpointAuthenticationType.SYSTEMASSIGNED.value,
                        DataflowEndpointAuthenticationType.USERASSIGNED.value,
                        DataflowEndpointAuthenticationType.SASL.value,
                    ]
                ),
            )

    for cmd_space in [
        "iot ops dataflow endpoint create fabric-realtime",
        "iot ops dataflow endpoint update fabric-realtime",
    ]:
        with self.argument_context(cmd_space) as context:
            context.argument(
                "host",
                options_list=["--host"],
                help="Host of the Fabric real-time is the "
                "'Bootstrap server' value. Can be found in "
                "event stream destination -- 'SAS Key Authentication' "
                "section. In the form of *.servicebus.windows.net:9093",
            )
            context.argument(
                "latency",
                options_list=["--latency", "-l"],
                help="The batching latency in milliseconds. Min value: 0, max value: 65535.",
                type=int,
                arg_group="Batching Configuration",
            )
            context.argument(
                "secret_name",
                options_list=["--secret-name", "-s"],
                help="The name for the kubernetes secret that contains Connection string-primary key value. "
                "Can be found in event stream destination -- 'SAS Key Authentication' section. "
                "Note: The secret must be in the same namespace as the Kafka data flow endpoint. "
                "For more information about secret format, please refer to link in command description.",
                arg_group="SASL Authentication",
            )
            context.argument(
                "authentication_type",
                options_list=["--auth-type"],
                choices=CaseInsensitiveList(
                    [
                        DataflowEndpointAuthenticationType.SYSTEMASSIGNED.value,
                        DataflowEndpointAuthenticationType.USERASSIGNED.value,
                        DataflowEndpointAuthenticationType.SASL.value,
                    ]
                ),
            )

    for cmd_space in [
        "iot ops dataflow endpoint create custom-kafka",
        "iot ops dataflow endpoint update custom-kafka",
    ]:
        with self.argument_context(cmd_space) as context:
            context.argument(
                "hostname",
                options_list=["--hostname"],
                help="The hostname of the Kafka broker host setting.",
            )
            context.argument(
                "port",
                options_list=["--port"],
                help="The port number of the Kafka broker host setting.",
                type=int,
            )
            context.argument(
                "latency",
                options_list=["--latency", "-l"],
                help="The batching latency in milliseconds. Min value: 0, max value: 65535.",
                type=int,
                arg_group="Batching Configuration",
            )
            context.argument(
                "secret_name",
                options_list=["--secret-name", "-s"],
                help="The name of the Kubernetes secret that contains the SASL token.",
                arg_group="SASL Authentication",
            )
            context.argument(
                "authentication_type",
                options_list=["--auth-type"],
                choices=CaseInsensitiveList(
                    [
                        DataflowEndpointAuthenticationType.SYSTEMASSIGNED.value,
                        DataflowEndpointAuthenticationType.USERASSIGNED.value,
                        DataflowEndpointAuthenticationType.SASL.value,
                    ]
                ),
            )

    for cmd_space in [
        "iot ops dataflow endpoint create local-storage",
        "iot ops dataflow endpoint update local-storage",
    ]:
        with self.argument_context(cmd_space) as context:
            context.argument(
                "pvc_reference",
                options_list=["--pvc-ref"],
                help="The name of the PersistentVolumeClaim (PVC) to use for local storage. "
                "Note: The PVC must be in the same namespace as the data flow endpoint.",
            )

    for cmd_space in [
        "iot ops dataflow endpoint create local-mqtt",
        "iot ops dataflow endpoint update local-mqtt",
    ]:
        with self.argument_context(cmd_space) as context:
            context.argument(
                "hostname",
                options_list=["--hostname"],
                help="The hostname of the local MQTT broker.",
            )
            context.argument(
                "port",
                options_list=["--port"],
                help="The port number of the local MQTT broker.",
                type=int,
            )
            context.argument(
                "audience",
                options_list=["--audience", "--aud"],
                help="The audience of the Kubernetes service account token (SAT).",
                arg_group="Kubernetes Service Account Token",
            )
            context.argument(
                "secret_name",
                options_list=["--secret-name", "-s"],
                help="The name for the kubernetes secret that contains the X509 client certificate, private key "
                "corresponding to the client certificate, and intermediate certificates for the client certificate "
                "chain. "
                "Note: The certificate and private key must be in PEM format and not password protected.",
                arg_group="X509 Authentication",
            )
            context.argument(
                "authentication_type",
                options_list=["--auth-type"],
                choices=CaseInsensitiveList(
                    [
                        DataflowEndpointAuthenticationType.SERVICEACCESSTOKEN.value,
                        DataflowEndpointAuthenticationType.X509.value,
                    ]
                ),
            )

    for cmd_space in [
        "iot ops dataflow endpoint create eventgrid",
        "iot ops dataflow endpoint update eventgrid",
    ]:
        with self.argument_context(cmd_space) as context:
            context.argument(
                "hostname",
                options_list=["--hostname"],
                help="The hostname of the event grid namespace. Can"
                " be found in 'Http hostname' property. In the form "
                "of NAMESPACE.REGION-1.ts.eventgrid.azure.net",
            )
            context.argument(
                "port",
                options_list=["--port"],
                help="The port number of the event grid namespace.",
                type=int,
            )
            context.argument(
                "secret_name",
                options_list=["--secret-name", "-s"],
                help="The name for the kubernetes secret that contains the X509 client certificate, private key "
                "corresponding to the client certificate, and intermediate certificates for the client certificate "
                "chain. "
                "Note: The certificate and private key must be in PEM format and not password protected.",
                arg_group="X509 Authentication",
            )
            context.argument(
                "authentication_type",
                options_list=["--auth-type"],
                choices=CaseInsensitiveList(
                    [
                        DataflowEndpointAuthenticationType.SYSTEMASSIGNED.value,
                        DataflowEndpointAuthenticationType.USERASSIGNED.value,
                        DataflowEndpointAuthenticationType.X509.value,
                    ]
                ),
            )

    for cmd_space in [
        "iot ops dataflow endpoint create custom-mqtt",
        "iot ops dataflow endpoint update custom-mqtt",
    ]:
        with self.argument_context(cmd_space) as context:
            context.argument(
                "hostname",
                options_list=["--hostname"],
                help="The hostname of the custom MQTT broker host setting.",
            )
            context.argument(
                "port",
                options_list=["--port"],
                help="The port number of the custom MQTT broker host setting.",
                type=int,
            )
            context.argument(
                "secret_name",
                options_list=["--secret-name", "-s"],
                help="The name for the kubernetes secret that contains the X509 client certificate, private key "
                "corresponding to the client certificate, and intermediate certificates for the client certificate "
                "chain. "
                "Note: The certificate and private key must be in PEM format and not password protected.",
                arg_group="X509 Authentication",
            )
            context.argument(
                "sami_audience",
                options_list=["--sami-audience", "--sami-aud"],
                help="The audience of the system assigned managed identity.",
                arg_group="System Assigned Managed Identity",
            )
            context.argument(
                "sat_audience",
                options_list=["--sat-audience", "--sat-aud"],
                help="The audience of the Kubernetes service account token (SAT).",
                arg_group="Kubernetes Service Account Token",
            )
            context.argument(
                "authentication_type",
                options_list=["--auth-type"],
                choices=CaseInsensitiveList(
                    [
                        DataflowEndpointAuthenticationType.SERVICEACCESSTOKEN.value,
                        DataflowEndpointAuthenticationType.SYSTEMASSIGNED.value,
                        DataflowEndpointAuthenticationType.USERASSIGNED.value,
                        DataflowEndpointAuthenticationType.X509.value,
                    ]
                ),
            )

    with self.argument_context("iot ops broker") as context:
        context.argument(
            "instance_name",
            options_list=["--instance", "-i"],
            help="IoT Operations instance name.",
        )
        context.argument(
            "broker_name",
            options_list=["--name", "-n"],
            help="Broker name.",
        )

    with self.argument_context("iot ops broker listener") as context:
        context.argument(
            "listener_name",
            options_list=["--name", "-n"],
            help="Listener name.",
        )
        context.argument(
            "broker_name",
            options_list=["--broker", "-b"],
            help="Broker name.",
        )

    with self.argument_context("iot ops broker listener port") as context:
        context.argument(
            "listener_name",
            options_list=["--listener", "-n"],
            help="Listener name.",
        )
        context.argument(
            "port",
            type=int,
            options_list=["--port"],
            help="Listener service port.",
        )
        context.argument(
            "nodeport",
            type=int,
            options_list=["--nodeport"],
            help="The listener service will exposes a static port on each Node's IP address. "
            "Only relevant when this port is associated with a NodePort listener.",
            arg_group="Node Port",
        )
        context.argument(
            "service_name",
            options_list=["--service-name"],
            help="Kubernetes service name of the listener. Used when a target listener does not exist.",
        )
        context.argument(
            "service_type",
            options_list=["--service-type"],
            arg_type=get_enum_type(MqServiceType, default=None),
            help="Kubernetes service type of the listener. Used when a target listener does not exist.",
        )
        context.argument(
            "protocol",
            options_list=["--protocol"],
            arg_type=get_enum_type(ListenerProtocol, default=None),
            help="Protocol to use for client connections.",
        )
        context.argument(
            "authn_ref", options_list=["--authn-ref"], help="Authentication reference (name).", arg_group="Auth"
        )
        context.argument(
            "authz_ref", options_list=["--authz-ref"], help="Authorization reference (name).", arg_group="Auth"
        )
        context.argument(
            "tls_auto_issuer_ref",
            options_list=["--tls-issuer-ref"],
            nargs="+",
            help="Cert-manager issuer reference. Format is space-separated "
            f"key=value pairs. The following keys are supported: `{'`, `'.join(X509_ISSUER_REF_KEYS)}`. "
            "`kind` and `name` are required, while `group` has a default value of 'cert-manager.io'.",
            arg_group="TLS Auto",
        )
        context.argument(
            "tls_auto_duration",
            options_list=["--tls-duration"],
            help="Lifetime of certificate. Must be specified using a time.Duration format (h|m|s). "
            "E.g. 240h for 240 hours and 45m for 45 minutes.",
            arg_group="TLS Auto",
        )
        context.argument(
            "tls_auto_key_algo",
            options_list=["--tls-key-algo"],
            arg_type=get_enum_type(TlsKeyAlgo, default=None),
            help="Algorithm for private key. ",
            arg_group="TLS Auto",
        )
        context.argument(
            "tls_auto_key_rotation_policy",
            options_list=["--tls-key-rotation"],
            arg_type=get_enum_type(TlsKeyRotation, default=None),
            help="Cert-manager private key rotation policy.",
            arg_group="TLS Auto",
        )
        context.argument(
            "tls_auto_renew_before",
            options_list=["--tls-renew-before"],
            help="When to begin renewing certificate. Must be specified using a Go time.Duration format (h|m|s). "
            "E.g. 240h for 240 hours and 45m for 45 minutes.",
            arg_group="TLS Auto",
        )
        context.argument(
            "tls_auto_san_dns",
            options_list=["--tls-san-dns"],
            nargs="+",
            help="DNS subject alternative names for the certificate. Use space-separated values.",
            arg_group="TLS Auto",
        )
        context.argument(
            "tls_auto_san_ip",
            options_list=["--tls-san-ip"],
            nargs="+",
            help="IP subject alternative names for the certificate. Use space-separated values.",
            arg_group="TLS Auto",
        )
        context.argument(
            "tls_auto_secret_name",
            options_list=["--tls-secret-name"],
            help="Secret for storing server certificate. Any existing data will be overwritten. This is a reference to "
            "the secret through an identifying name, not the secret itself.",
            arg_group="TLS Auto",
        )
        context.argument(
            "tls_manual_secret_ref",
            options_list=["--tls-man-secret-ref"],
            help="Secret containing an X.509 client certificate. This is a "
            "reference to the secret through an identifying name, not the secret itself.",
            arg_group="TLS Manual",
        )

    with self.argument_context("iot ops broker authn") as context:
        context.argument(
            "authn_name",
            options_list=["--name", "-n"],
            help="Mqtt broker authentication resource name.",
        )
        context.argument(
            "broker_name",
            options_list=["--broker", "-b"],
            help="Mqtt broker name.",
        )

    with self.argument_context("iot ops broker authn method add") as context:
        context.argument(
            "authn_name",
            options_list=["--authn", "-n"],
            help="Mqtt broker authentication resource name.",
        )
        context.argument(
            "sat_audiences",
            options_list=["--sat-aud"],
            nargs="+",
            help="Space-separated list of allowed audiences.",
            arg_group="SAT",
        )
        context.argument(
            "x509_client_ca_cm",
            options_list=["--x509-client-ca-ref"],
            help="Name of the configmap containing the trusted client ca cert resource. Default value is 'client-ca'.",
            arg_group="x509",
        )
        context.argument(
            "x509_attrs",
            options_list=["--x509-attr"],
            nargs="+",
            action="extend",
            help="Specify attributes in the authentication resource for authorizing clients based on their "
            "certificate properties. You can apply authorization rules to clients by using x509 certificates "
            "with these attributes. Format is space-separated key=value pairs where the key uses object dot notation "
            "such as 'a.b.c=value'. Can be used one or more times.",
            arg_group="x509",
        )
        context.argument(
            "custom_endpoint",
            options_list=["--custom-ep"],
            help="Endpoint to use for the custom auth service. Format is `https://.*`.",
            arg_group="Custom",
        )
        context.argument(
            "custom_ca_cm",
            options_list=["--custom-ca-ref"],
            help="Name of the configmap containing the CA certificate for validating the "
            "custom authentication server's certificate.",
            arg_group="Custom",
        )
        context.argument(
            "custom_x509_secret_ref",
            options_list=["--custom-x509-secret-ref"],
            help="Reference to Kubernetes secret containing a client certificate.",
            arg_group="Custom",
        )
        context.argument(
            "custom_http_headers",
            options_list=["--custom-header"],
            nargs="+",
            action="extend",
            help="http headers to pass to the custom authentication server. Format is space-separated key=value pairs. "
            "Can be used one or more times.",
            arg_group="Custom",
        )

    with self.argument_context("iot ops broker authz") as context:
        context.argument(
            "authz_name",
            options_list=["--name", "-n"],
            help="Mqtt broker authorization resource name.",
        )
        context.argument(
            "broker_name",
            options_list=["--broker", "-b"],
            help="Mqtt broker name.",
        )

    for cmd_space in ["iot ops init", "iot ops create"]:
        with self.argument_context(cmd_space) as context:
            context.argument(
                "cluster_name",
                options_list=["--cluster"],
                help="Target cluster name for IoT Operations deployment.",
            )
            context.argument(
                "cluster_namespace",
                options_list=["--cluster-namespace"],
                help="The cluster namespace IoT Operations infra will be deployed to. Must be lowercase.",
            )
            context.argument(
                "custom_location_name",
                options_list=["--custom-location"],
                help="The custom location name corresponding to the IoT Operations deployment. "
                "The default is in the form 'location-{hash(5)}'.",
            )
            context.argument(
                "location",
                options_list=["--location"],
                help="The region that will be used for provisioned resource collateral. "
                "If not provided the connected cluster location will be used.",
            )
            context.argument(
                "enable_rsync_rules",
                options_list=["--enable-rsync"],
                arg_type=get_three_state_flag(),
                deprecate_info=context.deprecate(),
                help="Resource sync rules will be included in the IoT Operations deployment. **Attention**: this flag "
                "has been deprecated in favor of the `az iot ops rsync enable` command.",
            )
            context.argument(
                "ensure_latest",
                options_list=["--ensure-latest"],
                arg_type=get_three_state_flag(),
                help="Ensure the latest IoT Ops CLI is being used, raising an error if an upgrade is available.",
            )
            # Cluster Precheck opt-in
            context.argument(
                "check_cluster",
                options_list=["--check-cluster"],
                arg_type=get_three_state_flag(),
                help="Enforce a check for minimum cluster requirements before bootstrapping.",
                is_preview=True,
            )

            # Schema Registry
            context.argument(
                "schema_registry_resource_id",
                options_list=["--sr-resource-id"],
                help="The schema registry resource Id to use with IoT Operations.",
            )
            # Akri
            context.argument(
                "container_runtime_socket",
                options_list=["--runtime-socket"],
                help="The default node path of the container runtime socket. If not provided (default), the "
                "socket path is determined by --kubernetes-distro.",
                arg_group="Akri",
            )
            context.argument(
                "kubernetes_distro",
                arg_type=get_enum_type(KubernetesDistroType),
                options_list=["--kubernetes-distro"],
                help="The Kubernetes distro to use for Akri configuration. The selected distro implies the "
                "default container runtime socket path when no --runtime-socket value is provided.",
                arg_group="Akri",
            )
            # Broker
            context.argument(
                "custom_broker_config_file",
                options_list=["--broker-config-file"],
                help="Path to a json file with custom broker config properties. "
                "File config content is used over individual broker config parameters. "
                "Useful for advanced scenarios. "
                "The expected format is described at https://aka.ms/aziotops-broker-config.",
                arg_group="Broker",
            )
            context.argument(
                "add_insecure_listener",
                options_list=[
                    "--add-insecure-listener",
                    context.deprecate(
                        target="--mq-insecure",
                        redirect="--add-insecure-listener",
                        hide=True,
                    ),
                ],
                arg_type=get_three_state_flag(),
                help="When enabled the mqtt broker deployment will include a listener "
                f"of service type {MqServiceType.LOADBALANCER.value}, bound to port 1883 with no authN or authZ. "
                "For non-production workloads only.",
                arg_group="Broker",
            )
            # Broker Config
            context.argument(
                "broker_frontend_replicas",
                type=int,
                options_list=["--broker-frontend-replicas", "--fr"],
                help="Mqtt broker frontend replicas. Min value: 1, max value: 16.",
                arg_group="Broker",
            )
            context.argument(
                "broker_frontend_workers",
                type=int,
                options_list=["--broker-frontend-workers", "--fw"],
                help="Mqtt broker frontend workers. Min value: 1, max value: 16.",
                arg_group="Broker",
            )
            context.argument(
                "broker_backend_redundancy_factor",
                type=int,
                options_list=["--broker-backend-rf", "--br"],
                help="Mqtt broker backend redundancy factor. Min value: 1, max value: 5.",
                arg_group="Broker",
            )
            context.argument(
                "broker_backend_workers",
                type=int,
                options_list=["--broker-backend-workers", "--bw"],
                help="Mqtt broker backend workers. Min value: 1, max value: 16.",
                arg_group="Broker",
            )
            context.argument(
                "broker_backend_partitions",
                type=int,
                options_list=["--broker-backend-part", "--bp"],
                help="Mqtt broker backend partitions. Min value: 1, max value: 16.",
                arg_group="Broker",
            )
            context.argument(
                "broker_memory_profile",
                arg_type=get_enum_type(MqMemoryProfile),
                options_list=["--broker-mem-profile", "--mp"],
                help="Mqtt broker memory profile.",
                arg_group="Broker",
            )
            context.argument(
                "broker_service_type",
                arg_type=get_enum_type(MqServiceType),
                options_list=["--broker-listener-type", "--lt"],
                help="Service type associated with the default mqtt broker listener.",
                arg_group="Broker",
                deprecate_info=context.deprecate(hide=True),
            )
            context.argument(
                "enable_fault_tolerance",
                arg_type=get_three_state_flag(),
                options_list=["--enable-fault-tolerance"],
                help="Enable fault tolerance for Azure Arc Container Storage. At least 3 cluster nodes are required.",
                arg_group="Container Storage",
            )
            context.argument(
                "dataflow_profile_instances",
                type=int,
                options_list=["--df-profile-instances"],
                help="The instance count associated with the default dataflow profile.",
                arg_group="Dataflow",
            )
            context.argument(
                "trust_settings",
                options_list=["--trust-settings"],
                nargs="+",
                action="store",
                help="Settings for user provided trust bundle. Used for component TLS. Format is space-separated "
                f"key=value pairs. The following keys are required: `{'`, `'.join(TRUST_SETTING_KEYS)}`. If not "
                "used, a system provided self-signed trust bundle is configured.",
                arg_group="Trust",
            )
            context.argument(
                "user_trust",
                options_list=["--user-trust", "--ut"],
                arg_type=get_three_state_flag(),
                help="Skip the deployment of the system cert-manager and trust-manager "
                "in favor of a user-provided configuration.",
                arg_group="Trust",
            )

            for moniker in EXTENSION_MONIKER_TO_ALIAS_MAP:
                alias = EXTENSION_MONIKER_TO_ALIAS_MAP[moniker]
                if alias in ["acs", "ssc", "ops"]:
                    context.argument(
                        f"{alias}_config",
                        options_list=[f"--{alias}-config"],
                        nargs="+",
                        action="extend",
                        help=f"{moniker} arc extension custom config. Format is space-separated key=value pairs "
                        f"or just the key. This option can be used one or more times.",
                        arg_group="Extension Config",
                    )
                    context.argument(
                        f"{alias}_version",
                        options_list=[f"--{alias}-version"],
                        help=f"Use to override the built-in {moniker} arc extension version.",
                        arg_group="Extension Config",
                        deprecate_info=context.deprecate(hide=True),
                    )
                    context.argument(
                        f"{alias}_train",
                        options_list=[f"--{alias}-train"],
                        help=f"Use to override the built-in {moniker} arc extension release train.",
                        arg_group="Extension Config",
                        deprecate_info=context.deprecate(hide=True),
                    )

    for cmd_space in ["iot ops create", "iot ops update"]:
        with self.argument_context(cmd_space) as context:
            context.argument(
                "instance_features",
                options_list=["--feature"],
                nargs="+",
                action="extend",
                help="Instance feature config. The settings of a component and/or it's mode can be configured. "
                "Component mode syntax is `{component}.mode={mode}` where known mode values are: "
                "`Stable`, `Preview` and `Disabled`. Component setting syntax is "
                "`{component}.settings.{setting}={value}` where known setting values are `Enabled` or `Disabled`. "
                "This option can be used one or more times.",
            )

    with self.argument_context("iot ops upgrade") as context:
        for moniker in EXTENSION_MONIKER_TO_ALIAS_MAP:
            alias = EXTENSION_MONIKER_TO_ALIAS_MAP[moniker]
            context.argument(
                f"{alias}_config",
                options_list=[f"--{alias}-config"],
                nargs="+",
                action="extend",
                help=f"{moniker} arc extension custom config. Format is space-separated key=value pairs "
                f"or just the key. This option can be used one or more times.",
                arg_group="Extension Config",
            )
            context.argument(
                f"{alias}_config_sync_mode",
                options_list=[f"--{alias}-config-sync"],
                help=f"{moniker} arc extension config sync mode. This option is applicable if an upgrade is "
                "requested to a known version. Mode 'full' will alter current config to the target, "
                "'add' will apply additive changes only, 'none' is a no-op.",
                arg_type=get_enum_type(ConfigSyncModeType, default=ConfigSyncModeType.FULL.value),
                arg_group="Extension Config",
                deprecate_info=context.deprecate(hide=True),
            )
            context.argument(
                f"{alias}_version",
                options_list=[f"--{alias}-version"],
                help=f"Use to override the built-in {moniker} arc extension version.",
                arg_group="Extension Config",
                deprecate_info=context.deprecate(hide=True),
            )
            context.argument(
                f"{alias}_train",
                options_list=[f"--{alias}-train"],
                help=f"Use to override the built-in {moniker} arc extension release train.",
                arg_group="Extension Config",
                deprecate_info=context.deprecate(hide=True),
            )
        context.argument(
            "force",
            options_list=["--force"],
            arg_type=get_three_state_flag(),
            help="Force the operation to continue. Use to get around guards, such as those preventing downgrade.",
            arg_group="Extension Config",
            deprecate_info=context.deprecate(hide=True),
        )

    with self.argument_context("iot ops delete") as context:
        context.argument(
            "include_dependencies",
            options_list=["--include-deps"],
            arg_type=get_three_state_flag(),
            help="Indicates the command should remove IoT Operations dependencies. "
            "This option is intended to reverse the application of init.",
        )
        context.argument(
            "cluster_name",
            options_list=["--cluster"],
            help="Target cluster name for IoT Operations deletion.",
        )

    with self.argument_context("iot ops secretsync") as context:
        context.argument(
            "keyvault_resource_id",
            options_list=["--kv-resource-id"],
            help="Key Vault ARM resource Id.",
        )
        context.argument(
            "spc_name",
            options_list=["--spc"],
            help="The default secret provider class name for secret sync enablement. "
            "The default pattern is 'spc-ops-{hash}'.",
        )
        context.argument(
            "instance_name",
            options_list=["--instance", "-i", "-n"],
            help="IoT Operations instance name.",
        )

    with self.argument_context("iot ops schema") as context:
        context.argument(
            "schema_name",
            options_list=["--name", "-n"],
            help="Schema name.",
        )
        context.argument(
            "schema_registry_name",
            options_list=["--registry"],
            help="Schema registry name.",
        )
        context.argument(
            "schema_format", options_list=["--format"], help="Schema format.", arg_type=get_enum_type(SchemaFormat)
        )
        context.argument(
            "schema_type", options_list=["--type"], help="Schema type.", arg_type=get_enum_type(SchemaType)
        )
        context.argument(
            "description",
            options_list=["--desc"],
            help="Description for the schema.",
        )
        context.argument(
            "display_name",
            options_list=["--display-name"],
            help="Display name for the schema.",
        )
        context.argument(
            "schema_version",
            options_list=["--version", "--ver"],
            help="Schema version name.",
            type=int,
            arg_group="Version",
        )
        context.argument(
            "schema_version_content",
            options_list=["--version-content", "--vc"],
            help="File path containing or inline content for the version.",
            arg_group="Version",
        )
        context.argument(
            "schema_version_description",
            options_list=["--version-desc", "--vd"],
            help="Description for the version.",
            arg_group="Version",
        )

    with self.argument_context("iot ops schema show-dataflow-refs") as context:
        context.argument(
            "schema_name",
            options_list=["--schema"],
            help="Schema name. Required if using --version.",
        )
        context.argument(
            "schema_version",
            options_list=["--version", "--ver"],
            help="Schema version name. If used, --latest will be ignored.",
            type=int,
            arg_group=None,
        )
        context.argument(
            "latest",
            options_list=["--latest"],
            help="Flag to show only the latest version(s).",
            arg_type=get_three_state_flag(),
        )

    with self.argument_context("iot ops schema registry") as context:
        context.argument(
            "schema_registry_name",
            options_list=["--name", "-n"],
            help="Schema registry name.",
        )
        context.argument(
            "registry_namespace",
            options_list=["--registry-namespace", "--rn"],
            help="Schema registry namespace. Uniquely identifies a schema registry within a tenant.",
        )
        context.argument(
            "tags",
            options_list=["--tags"],
            arg_type=tags_type,
        )
        context.argument(
            "description",
            options_list=["--desc"],
            help="Description for the schema registry.",
        )
        context.argument(
            "display_name",
            options_list=["--display-name"],
            help="Display name for the schema registry.",
        )
        context.argument(
            "location",
            options_list=["--location", "-l"],
            help="Region to create the schema registry. "
            "If no location is provided the resource group location will be used.",
        )
        context.argument(
            "storage_account_resource_id",
            options_list=["--sa-resource-id"],
            help="Storage account resource Id to be used with the schema registry.",
        )
        context.argument(
            "storage_container_name",
            options_list=["--sa-container"],
            help="Storage account container name where schemas will be stored.",
        )

    with self.argument_context("iot ops connector opcua") as context:
        context.argument(
            "instance_name",
            options_list=["--instance", "-i", "-n"],
            help="IoT Operations instance name.",
        )
        context.argument(
            "resource_group",
            options_list=["--resource-group", "-g"],
            help="Instance resource group.",
        )
        context.argument(
            "include_secrets",
            options_list=["--include-secrets"],
            help="Indicates the command should remove the key vault secrets "
            "associated with the certificate(s). This option will delete and "
            "purge the secrets.",
            arg_type=get_three_state_flag(),
        )
        context.argument(
            "certificate_names",
            options_list=["--certificate-names", "--cn"],
            nargs="+",
            help="Space-separated certificate names to remove. "
            "Note: the names can be found under the corresponding "
            "secretsync resource property 'targetKey'.",
        )
        context.argument(
            "overwrite_secret",
            options_list=["--overwrite-secret"],
            arg_type=get_three_state_flag(),
            help="Confirm [y]es without a prompt to overwrite secret. "
            "if secret name existed in Azure key vault. Useful for "
            "CI and automation scenarios.",
        )

    with self.argument_context("iot ops connector opcua trust") as context:
        context.argument(
            "file",
            options_list=["--certificate-file", "--cf"],
            help="Path to the certificate file in .der or .crt format.",
        )
        context.argument(
            "secret_name",
            options_list=["--secret-name", "-s"],
            help="Secret name in the Key Vault. If not provided, the "
            "certificate file name will be used to generate the secret name.",
        )

    with self.argument_context("iot ops connector opcua issuer") as context:
        context.argument(
            "file",
            options_list=["--certificate-file", "--cf"],
            help="Path to the certificate file in .der, .crt or .crl format.",
        )
        context.argument(
            "secret_name",
            options_list=["--secret-name", "-s"],
            help="Secret name in the Key Vault. If not provided, the "
            "certificate file name will be used to generate the secret name.",
        )

    with self.argument_context("iot ops connector opcua client") as context:
        context.argument(
            "public_key_file",
            options_list=["--public-key-file", "--pkf"],
            help="File that contains the enterprise grade application "
            "instance certificate public key in .der format. File "
            "name will be used to generate the public key secret name.",
        )
        context.argument(
            "private_key_file",
            options_list=["--private-key-file", "--prkf"],
            help="File that contains the enterprise grade application "
            "instance certificate private key in .pem format. File name "
            "will be used to generate the private key secret name.",
        )
        context.argument(
            "subject_name",
            options_list=["--subject-name", "--sn"],
            help="The subject name string embedded in the application instance certificate. "
            "Can be found under public key certificate. When provided, the value will be used to "
            "validate the certificate's subject name.",
        )
        context.argument(
            "application_uri",
            options_list=["--application-uri", "--au"],
            help="The application instance URI embedded in the application instance. "
            "Can be found under public key certificate. When provided, the value will be used to "
            "validate the certificate's application URI.",
        )
        context.argument(
            "public_key_secret_name",
            options_list=["--public-key-secret-name", "--pks"],
            help="Public key secret name in the Key Vault. If not provided, the "
            "certificate file name will be used to generate the secret name.",
        )
        context.argument(
            "private_key_secret_name",
            options_list=["--private-key-secret-name", "--prks"],
            help="Private key secret name in the Key Vault. If not provided, the "
            "certificate file name will be used to generate the secret name.",
        )

    with self.argument_context("iot ops schema version") as context:
        context.argument("version_name", options_list=["--name", "-n"], help="Schema version name.", type=int)
        context.argument(
            "schema_name",
            options_list=["--schema"],
            help="Schema name.",
        )
        context.argument(
            "description",
            options_list=["--desc"],
            help="Description for the schema version.",
        )
        context.argument(
            "schema_version_content",
            options_list=["--content"],
            help="File path containing or inline content for the version.",
            arg_group=None,
        )

    with self.argument_context("iot ops clone") as context:
        context.argument(
            "summary_mode",
            options_list=["--summary"],
            arg_type=get_enum_type(CloneSummaryMode, default=CloneSummaryMode.SIMPLE.value),
            help="Deployment summary option.",
        )
        context.argument(
            "instance_name",
            options_list=["--name", "-n"],
            help="The model instance to clone.",
        )
        context.argument(
            "resource_group_name",
            options_list=["--resource-group", "-g"],
            help="The resource group the model instance to clone resides in.",
        )
        context.argument(
            "to_dir",
            options_list=["--to-dir"],
            help="The local directory the instance clone definitions will be stored in.",
            arg_group="Local Target",
        )
        context.argument(
            "template_mode",
            options_list=["--mode"],
            arg_type=get_enum_type(CloneTemplateMode, default=CloneTemplateMode.NESTED.value),
            help="When mode 'nested' is used, sub-deployments will be self-contained in the root deployment. "
            "When mode 'linked' is used, asset related sub-deployments will be split and stored as separate files "
            "linked by the root deployment.",
        )
        context.argument(
            "linked_base_uri",
            options_list=["--base-uri"],
            help="Base URI to use for template links. If not provided a relative path strategy will be used. "
            "Relevant when --mode is set to 'linked'. "
            "Example: `https://raw.githubusercontent.com/myorg/myproject/main/myclones/`.",
            arg_group="Local Target",
        )
        context.argument(
            "to_cluster_id",
            options_list=["--to-cluster-id"],
            help="The resource Id of the connected cluster the clone will be applied to.",
            arg_group="Cluster Target",
        )
        context.argument(
            "to_cluster_params",
            options_list=["--param", "-p"],
            nargs="+",
            action="extend",
            help="Parameter overrides when replicating the clone to a connected cluster. If omitted "
            "default values from the model instance are used. Format is space-separated key=value pairs where the "
            "key represents a clone definition parameter. The following keys can be set: "
            f"{', '.join([m.value for m in CloneTemplateParams])}. Can be used one or more times.",
            arg_group="Cluster Target",
        )
        context.argument(
            "use_self_hosted_issuer",
            options_list=["--self-hosted-issuer"],
            arg_type=get_three_state_flag(),
            help="Use the self-hosted oidc issuer for federation. Only applicable if "
            "user-assigned managed identities are associated to the model instance.",
            arg_group="Cluster Target",
        )

    with self.argument_context("iot ops rsync") as context:
        context.argument(
            "rule_ops_name",
            options_list=["--rule-ops-name"],
            help="The desired name of the resource sync rule to create for IoT Operations.",
            arg_group="Custom Rule",
        )
        context.argument(
            "rule_adr_name",
            options_list=["--rule-adr-name"],
            help="The desired name of the resource sync rule to create for Device Registry.",
            arg_group="Custom Rule",
        )
        context.argument(
            "rule_ops_pri",
            type=int,
            options_list=["--rule-ops-pri"],
            help="The desired priority of the resource sync rule to create for IoT Operations.",
            arg_group="Custom Rule",
        )
        context.argument(
            "rule_adr_pri",
            type=int,
            options_list=["--rule-adr-pri"],
            help="The desired priority of the resource sync rule to create for Device Registry.",
            arg_group="Custom Rule",
        )
        context.argument(
            "k8_bridge_sp_oid",
            options_list=["--k8-bridge-sp-oid"],
            help="Provide an explicit K8 Bridge service principal OID for the custom location role assignment. "
            "This is useful if the logged-in principal does not have permission to query apps from MS Graph.",
        )
