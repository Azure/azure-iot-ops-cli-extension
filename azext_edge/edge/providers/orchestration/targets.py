# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, List, Optional, Tuple

from azure.cli.core.azclierror import InvalidArgumentValueError

from ...common import (
    DEFAULT_BROKER,
    DEFAULT_BROKER_AUTHN,
    DEFAULT_BROKER_LISTENER,
    DEFAULT_DATAFLOW_ENDPOINT,
    DEFAULT_DATAFLOW_PROFILE,
)
from ...util import assemble_nargs_to_dict
from ...util.az_client import parse_resource_id
from ..orchestration.common import (
    TRUST_ISSUER_KIND_KEY,
    TRUST_SETTING_KEYS,
)
from .common import KubernetesDistroType
from .template import (
    IOT_OPERATIONS_VERSION_MONIKER,
    M3_ENABLEMENT_TEMPLATE,
    M3_INSTANCE_TEMPLATE,
    TemplateBlueprint,
    get_insecure_listener,
)


class InitTargets:
    def __init__(
        self,
        cluster_name: str,
        resource_group_name: str,
        schema_registry_resource_id: Optional[str] = None,
        cluster_namespace: str = "azure-iot-operations",
        location: Optional[str] = None,
        custom_location_name: Optional[str] = None,
        enable_rsync_rules: Optional[bool] = None,
        instance_name: Optional[str] = None,
        instance_description: Optional[str] = None,
        tags: Optional[dict] = None,
        enable_fault_tolerance: Optional[bool] = None,
        ops_config: Optional[List[str]] = None,
        ops_version: Optional[str] = None,
        trust_settings: Optional[List[str]] = None,
        # Dataflow
        dataflow_profile_instances: int = 1,
        # Broker
        custom_broker_config: Optional[dict] = None,
        broker_memory_profile: Optional[str] = None,
        broker_service_type: Optional[str] = None,
        broker_backend_partitions: Optional[int] = None,
        broker_backend_workers: Optional[int] = None,
        broker_backend_redundancy_factor: Optional[int] = None,
        broker_frontend_workers: Optional[int] = None,
        broker_frontend_replicas: Optional[int] = None,
        add_insecure_listener: Optional[bool] = None,
        # Akri
        kubernetes_distro: str = KubernetesDistroType.k8s.value,
        container_runtime_socket: Optional[str] = None,
        **_,
    ):
        self.cluster_name = cluster_name
        self.resource_group_name = resource_group_name
        # TODO - @digimaun
        if schema_registry_resource_id:
            parse_resource_id(schema_registry_resource_id)
        self.schema_registry_resource_id = schema_registry_resource_id
        self.cluster_namespace = self._sanitize_k8s_name(cluster_namespace)
        self.location = location
        self.custom_location_name = self._sanitize_k8s_name(custom_location_name)
        self.deploy_resource_sync_rules = bool(enable_rsync_rules)
        self.instance_name = self._sanitize_k8s_name(instance_name)
        self.instance_description = instance_description
        self.tags = tags
        self.enable_fault_tolerance = enable_fault_tolerance
        self.ops_config = assemble_nargs_to_dict(ops_config)
        self.ops_version = ops_version
        self.trust_settings = assemble_nargs_to_dict(trust_settings)
        self.trust_config = self.get_trust_settings_target_map()
        self.advanced_config = self.get_advanced_config_target_map()

        # Dataflow
        self.dataflow_profile_instances = self._sanitize_int(dataflow_profile_instances)

        # Broker
        self.add_insecure_listener = add_insecure_listener
        self.broker_memory_profile = broker_memory_profile
        self.broker_service_type = broker_service_type
        self.broker_backend_partitions = self._sanitize_int(broker_backend_partitions)
        self.broker_backend_workers = self._sanitize_int(broker_backend_workers)
        self.broker_backend_redundancy_factor = self._sanitize_int(broker_backend_redundancy_factor)
        self.broker_frontend_workers = self._sanitize_int(broker_frontend_workers)
        self.broker_frontend_replicas = self._sanitize_int(broker_frontend_replicas)
        self.broker_config = self.get_broker_config_target_map()
        self.custom_broker_config = custom_broker_config

        # Akri
        self.kubernetes_distro = kubernetes_distro
        self.container_runtime_socket = container_runtime_socket

    def _sanitize_k8s_name(self, name: Optional[str]) -> Optional[str]:
        if not name:
            return name
        sanitized = str(name)
        sanitized = sanitized.lower()
        sanitized = sanitized.replace("_", "-")
        return sanitized

    def _sanitize_int(self, value: Optional[int]) -> Optional[int]:
        if value is None:
            return value
        return int(value)

    def _handle_apply_targets(
        self, param_to_target: dict, template_blueprint: TemplateBlueprint
    ) -> Tuple[TemplateBlueprint, dict]:
        template_copy = template_blueprint.copy()
        built_in_template_params = template_copy.parameters

        deploy_params = {}

        for param in param_to_target:
            if param in built_in_template_params and param_to_target[param] is not None:
                deploy_params[param] = {"value": param_to_target[param]}

        return template_copy, deploy_params

    @property
    def iot_operations_version(self):
        return IOT_OPERATIONS_VERSION_MONIKER

    def get_extension_versions(self) -> dict:
        # Don't need a deep copy here.
        return M3_ENABLEMENT_TEMPLATE.content["variables"]["VERSIONS"].copy()

    def get_ops_enablement_template(
        self,
    ) -> Tuple[dict, dict]:
        template, parameters = self._handle_apply_targets(
            param_to_target={
                "clusterName": self.cluster_name,
                "trustConfig": self.trust_config,
                "advancedConfig": self.advanced_config,
            },
            template_blueprint=M3_ENABLEMENT_TEMPLATE,
        )

        # TODO - @digimaun - expand trustSource for self managed & trustBundleSettings
        return template.content, parameters

    def get_ops_instance_template(
        self, cl_extension_ids: List[str],
        # ops_extension_config: Dict[str, str]
    ) -> Tuple[dict, dict]:
        # TODO - @c-ryan-k figure out wtf to do with this
        # trust_source = ops_extension_config.get("trustSource")

        # if trust_source == "CustomerManaged":
        #     trust_issuer_name = ops_extension_config.get("trustBundleSettings.issuer.name")
        #     trust_issuer_kind = ops_extension_config.get("trustBundleSettings.issuer.kind")
        #     trust_configmap_name = ops_extension_config.get("trustBundleSettings.configMap.name")
        #     trust_configmap_key = ops_extension_config.get("trustBundleSettings.configMap.key")
        #     self.trust_settings = {
        #         "issuerName": trust_issuer_name,
        #         "issuerKind": trust_issuer_kind,
        #         "configMapName": trust_configmap_name,
        #         "configMapKey": trust_configmap_key,
        #     }
        self.trust_config = self.get_trust_settings_target_map()

        template, parameters = self._handle_apply_targets(
            param_to_target={
                "clusterName": self.cluster_name,
                "clusterNamespace": self.cluster_namespace,
                "clusterLocation": self.location,
                "kubernetesDistro": self.kubernetes_distro,
                "containerRuntimeSocket": self.container_runtime_socket,
                "customLocationName": self.custom_location_name,
                "clExtentionIds": cl_extension_ids,
                "deployResourceSyncRules": self.deploy_resource_sync_rules,
                "schemaRegistryId": self.schema_registry_resource_id,
                "defaultDataflowinstanceCount": self.dataflow_profile_instances,
                "brokerConfig": self.broker_config,
                "trustConfig": self.trust_config,
            },
            template_blueprint=M3_INSTANCE_TEMPLATE,
        )

        if self.ops_config:
            aio_default_config: Dict[str, str] = template.content["variables"]["defaultAioConfigurationSettings"]
            aio_default_config.update(self.ops_config)

        if self.ops_version:
            template.content["variables"]["VERSIONS"]["iotOperations"] = self.ops_version

        instance = template.get_resource_by_key("aioInstance")
        instance["properties"]["description"] = self.instance_description

        instance["properties"]["schemaRegistryRef"] = {
            "resourceId": "[parameters('schemaRegistryId')]"
        }

        if self.tags:
            instance["tags"] = self.tags

        broker = template.get_resource_by_key("broker")
        broker_authn = template.get_resource_by_key("broker_authn")
        broker_listener = template.get_resource_by_key("broker_listener")
        dataflow_profile = template.get_resource_by_key("dataflow_profile")
        dataflow_endpoint = template.get_resource_by_key("dataflow_endpoint")

        if self.instance_name:
            instance["name"] = self.instance_name
            broker["name"] = f"{self.instance_name}/{DEFAULT_BROKER}"
            broker_authn["name"] = f"{self.instance_name}/{DEFAULT_BROKER}/{DEFAULT_BROKER_AUTHN}"
            broker_listener["name"] = f"{self.instance_name}/{DEFAULT_BROKER}/{DEFAULT_BROKER_LISTENER}"
            dataflow_profile["name"] = f"{self.instance_name}/{DEFAULT_DATAFLOW_PROFILE}"
            dataflow_endpoint["name"] = f"{self.instance_name}/{DEFAULT_DATAFLOW_ENDPOINT}"

        if self.custom_broker_config:
            if "properties" in self.custom_broker_config:
                self.custom_broker_config = self.custom_broker_config["properties"]
            broker["properties"] = self.custom_broker_config

        if self.add_insecure_listener:
            template.add_resource(
                resource_key="broker_listener_insecure",
                resource_def=get_insecure_listener(instance_name=self.instance_name, broker_name=DEFAULT_BROKER),
            )

        return template.content, parameters

    def get_broker_config_target_map(self):
        to_process_config_map = {
            "frontendReplicas": self.broker_frontend_replicas,
            "frontendWorkers": self.broker_frontend_workers,
            "backendRedundancyFactor": self.broker_backend_redundancy_factor,
            "backendWorkers": self.broker_backend_workers,
            "backendPartitions": self.broker_backend_partitions,
            "memoryProfile": self.broker_memory_profile,
            "serviceType": self.broker_service_type,
        }
        processed_config_map = {}

        validation_errors = []
        broker_config_def = M3_INSTANCE_TEMPLATE.get_type_definition("_1.BrokerConfig")["properties"]
        for config in to_process_config_map:
            if to_process_config_map[config] is None:
                continue
            processed_config_map[config] = to_process_config_map[config]

            if not broker_config_def:
                continue

            if isinstance(to_process_config_map[config], int):
                if config in broker_config_def and broker_config_def[config].get("type") == "int":
                    min_value = broker_config_def[config].get("minValue")
                    max_value = broker_config_def[config].get("maxValue")

                    if all([min_value is None, max_value is None]):
                        continue

                    if any([to_process_config_map[config] < min_value, to_process_config_map[config] > max_value]):
                        error_msg = f"{config} value range"

                        if min_value:
                            error_msg += f" min:{min_value}"
                        if max_value:
                            error_msg += f" max:{max_value}"
                        validation_errors.append(error_msg)

        if validation_errors:
            raise InvalidArgumentValueError("\n".join(validation_errors))

        return processed_config_map

    def get_advanced_config_target_map(self) -> dict:
        processed_config_map = {}
        if self.enable_fault_tolerance:
            processed_config_map["edgeStorageAccelerator"] = {"faultToleranceEnabled": True}

        return processed_config_map

    def get_trust_settings_target_map(self) -> dict:
        source = "SelfSigned"
        result = {"source": source}
        if self.trust_settings:
            target_settings: Dict[str, str] = {}
            result["source"] = "CustomerManaged"
            trust_bundle_def = M3_ENABLEMENT_TEMPLATE.get_type_definition("_1.TrustBundleSettings")["properties"]
            allowed_issuer_kinds: Optional[List[str]] = trust_bundle_def.get(TRUST_ISSUER_KIND_KEY, {}).get(
                "allowedValues"
            )
            for key in TRUST_SETTING_KEYS:
                if key not in self.trust_settings:
                    raise InvalidArgumentValueError(f"{key} is a required trust setting/key.")
                if key == TRUST_ISSUER_KIND_KEY:
                    if allowed_issuer_kinds and self.trust_settings[key] not in allowed_issuer_kinds:
                        raise InvalidArgumentValueError(f"{key} allowed values are {allowed_issuer_kinds}.")
                target_settings[key] = self.trust_settings[key]
            result["settings"] = target_settings

        return result
