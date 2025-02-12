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

from ._validators import validate_namespace, validate_resource_name
from .common import OpsServiceType
from .providers.check.common import ResourceOutputDetailLevel
from .providers.edge_api import (
    DeviceRegistryResourceKinds,
    MqResourceKinds,
    OpcuaResourceKinds,
)
from .providers.orchestration.common import (
    EXTENSION_MONIKER_TO_ALIAS_MAP,
    TRUST_SETTING_KEYS,
    IdentityUsageType,
    KubernetesDistroType,
    MqMemoryProfile,
    MqServiceType,
    SchemaFormat,
    SchemaType,
    ConfigSyncModeType,
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
            help="Instance tags. Property bag in key-value pairs with the following format: a=b c=d. "
            'Use --tags "" to remove all tags.',
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
                        OpcuaResourceKinds.ASSET_TYPE.value,
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

    with self.argument_context("iot ops dataflow endpoint") as context:
        context.argument(
            "endpoint_name",
            options_list=["--name", "-n"],
            help="Dataflow endpoint name.",
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
            help="Mqtt broker name.",
        )

    with self.argument_context("iot ops broker listener") as context:
        context.argument(
            "listener_name",
            options_list=["--name", "-n"],
            help="Mqtt broker listener name.",
        )
        context.argument(
            "broker_name",
            options_list=["--broker", "-b"],
            help="Mqtt broker name.",
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
                help="Resource sync rules will be included in the IoT Operations deployment.",
            )
            context.argument(
                "ensure_latest",
                options_list=["--ensure-latest"],
                arg_type=get_three_state_flag(),
                help="Ensure the latest IoT Ops CLI is being used, raising an error if an upgrade is available.",
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
                f"of service type {MqServiceType.load_balancer.value}, bound to port 1883 with no authN or authZ. "
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
            )
            context.argument(
                "ops_config",
                options_list=["--ops-config"],
                nargs="+",
                action="extend",
                help="IoT Operations arc extension custom configuration. Format is space-separated key=value pairs. "
                "--ops-config can be used one or more times. For advanced use cases.",
            )
            context.argument(
                "ops_version",
                options_list=["--ops-version"],
                help="Use to override the built-in IoT Operations arc extension version. ",
                deprecate_info=context.deprecate(hide=True),
            )
            context.argument(
                "ops_train",
                options_list=["--ops-train"],
                help="Use to override the built-in IoT Operations arc extension release train. ",
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
                help=f"Use to override the built-in {moniker} arc extension version. ",
                arg_group="Extension Config",
                deprecate_info=context.deprecate(hide=True),
            )
            context.argument(
                f"{alias}_train",
                options_list=[f"--{alias}-train"],
                help=f"Use to override the built-in {moniker} arc extension release train. ",
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
            "skip_role_assignments",
            options_list=["--skip-ra"],
            arg_type=get_three_state_flag(),
            help="When used the role assignment step of the operation will be skipped.",
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
            help="Schema registry tags. Property bag in key-value pairs with the following format: a=b c=d. "
            'Use --tags "" to remove all tags.',
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
        context.argument(
            "custom_role_id",
            options_list=["--custom-role-id"],
            help="Fully qualified role definition Id in the following format: "
            "/subscriptions/{subscriptionId}/providers/Microsoft.Authorization/roleDefinitions/{roleId}",
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
            help="The subject name string embedded in the application instance certificate."
            "Can be found under public key certificate.",
        )
        context.argument(
            "application_uri",
            options_list=["--application-uri", "--au"],
            help="The application instance URI embedded in the application instance."
            "Can be found under public key certificate.",
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
