# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List, Optional, Tuple

from azure.cli.core.azclierror import InvalidArgumentValueError

from ...common import (
    DEFAULT_BROKER,
    DEFAULT_BROKER_AUTHN,
    DEFAULT_BROKER_LISTENER,
    DEFAULT_DATAFLOW_PROFILE,
)
from .common import KubernetesDistroType, TrustSourceType
from .template import (
    M2_ENABLEMENT_TEMPLATE,
    M2_INSTANCE_TEMPLATE,
    TemplateBlueprint,
    get_insecure_listener,
)

BROKER_NAME = DEFAULT_BROKER
BROKER_AUTHN_NAME = DEFAULT_BROKER_AUTHN
BROKER_LISTENER_NAME = DEFAULT_BROKER_LISTENER
DATAFLOW_PROFILE_NAME = DEFAULT_DATAFLOW_PROFILE


class InitTargets:
    def __init__(
        self,
        cluster_name: str,
        resource_group_name: str,
        schema_registry_resource_id: str,
        cluster_namespace: str = "azure-iot-operations",
        location: Optional[str] = None,
        custom_location_name: Optional[str] = None,
        disable_rsync_rules: Optional[bool] = None,
        instance_name: Optional[str] = None,
        instance_description: Optional[str] = None,
        enable_fault_tolerance: Optional[bool] = None,
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
        trust_source: str = TrustSourceType.self_signed.value,
        mi_user_assigned_identities: Optional[List[str]] = None,
        **_,
    ):
        self.cluster_name = cluster_name
        self.safe_cluster_name = self._sanitize_k8s_name(self.cluster_name)
        self.resource_group_name = resource_group_name
        self.schema_registry_resource_id = schema_registry_resource_id
        self.cluster_namespace = self._sanitize_k8s_name(cluster_namespace)
        self.location = location
        self.custom_location_name = self._sanitize_k8s_name(custom_location_name)
        self.deploy_resource_sync_rules: bool = not disable_rsync_rules
        self.instance_name = self._sanitize_k8s_name(instance_name)
        self.instance_description = instance_description
        self.enable_fault_tolerance = enable_fault_tolerance
        self.dataflow_profile_instances = dataflow_profile_instances

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

        self.trust_source = trust_source
        self.mi_user_assigned_identities = mi_user_assigned_identities

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
            if param in built_in_template_params and param_to_target[param]:
                deploy_params[param] = {"value": param_to_target[param]}

        return template_copy, deploy_params

    def get_ops_enablement_template(
        self,
    ) -> Tuple[dict, dict]:
        template, parameters = self._handle_apply_targets(
            param_to_target={
                "clusterName": self.cluster_name,
                "kubernetesDistro": self.kubernetes_distro,
                "containerRuntimeSocket": self.container_runtime_socket,
                "trustSource": self.trust_source,
                "schemaRegistryId": self.schema_registry_resource_id,
            },
            template_blueprint=M2_ENABLEMENT_TEMPLATE,
        )

        # TODO - @digimaun potentially temp
        esa_extension = template.get_resource_by_key("edge_storage_accelerator_extension")
        esa_extension["properties"]["extensionType"] = "microsoft.arc.containerstorage"
        esa_extension["properties"]["version"] = "2.1.0-preview"
        esa_extension["properties"]["releaseTrain"] = "stable"

        esa_extension_config = {
            "edgeStorageConfiguration.create": "true",
            "feature.diskStorageClass": "default,local-path",
        }
        if self.enable_fault_tolerance:
            esa_extension_config["feature.diskStorageClass"] = "acstor-arccontainerstorage-storage-pool"
            esa_extension_config["acstorConfiguration.create"] = "true"
            esa_extension_config["acstorConfiguration.properties.diskMountPoint"] = "/mnt"

        esa_extension["properties"]["configurationSettings"] = esa_extension_config

        # TODO - @digimaun - expand trustSource for self managed & trustBundleSettings

        return template.content, parameters

    def get_ops_instance_template(self, cl_extension_ids: List[str]) -> Tuple[dict, dict]:
        template, parameters = self._handle_apply_targets(
            param_to_target={
                "clusterName": self.cluster_name,
                "clusterNamespace": self.cluster_namespace,
                "clusterLocation": self.location,
                "customLocationName": self.custom_location_name,
                "clExtentionIds": cl_extension_ids,
                "deployResourceSyncRules": self.deploy_resource_sync_rules,
                "schemaRegistryId": self.schema_registry_resource_id,
                "defaultDataflowinstanceCount": self.dataflow_profile_instances,
                "brokerConfig": self.broker_config,
                "trustConfig": "",
            },
            template_blueprint=M2_INSTANCE_TEMPLATE,
        )
        instance = template.get_resource_by_key("aioInstance")
        instance["properties"]["description"] = self.instance_description

        broker = template.get_resource_by_key("broker")
        broker_authn = template.get_resource_by_key("broker_authn")
        broker_listener = template.get_resource_by_key("broker_listener")
        dataflow_profile = template.get_resource_by_key("dataflow_profile")

        if self.instance_name:
            instance["name"] = self.instance_name
            broker["name"] = f"{self.instance_name}/{BROKER_NAME}"
            broker_authn["name"] = f"{self.instance_name}/{BROKER_NAME}/{BROKER_AUTHN_NAME}"
            broker_listener["name"] = f"{self.instance_name}/{BROKER_NAME}/{BROKER_LISTENER_NAME}"
            dataflow_profile["name"] = f"{self.instance_name}/{DATAFLOW_PROFILE_NAME}"

        if self.mi_user_assigned_identities:
            mi_user_payload = {}
            for mi in self.mi_user_assigned_identities:
                mi_user_payload[mi] = {}
            instance["identity"] = {}
            instance["identity"]["type"] = "UserAssigned"
            instance["identity"]["userAssignedIdentities"] = mi_user_payload

        if self.custom_broker_config:
            if "properties" in self.custom_broker_config:
                self.custom_broker_config = self.custom_broker_config["properties"]
            broker["properties"] = self.custom_broker_config

        if self.add_insecure_listener:
            template.add_resource(
                resource_key="broker_listener_insecure",
                resource_def=get_insecure_listener(instance_name=self.instance_name, broker_name=BROKER_NAME),
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
        broker_config_def = M2_INSTANCE_TEMPLATE.get_type_definition("_1.BrokerConfig")["properties"]
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
                        error_msg = f"{config} value must be"

                        if min_value:
                            error_msg += f" >{min_value}"
                        if max_value:
                            error_msg += f" <{max_value}"
                        validation_errors.append(error_msg)

        if validation_errors:
            raise InvalidArgumentValueError("\n".join(validation_errors))

        return processed_config_map
