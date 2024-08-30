# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List, Optional, Tuple

from .template import (
    M2_ENABLEMENT_TEMPLATE,
    M2_INSTANCE_TEMPLATE,
    TemplateBlueprint,
    get_basic_dataflow_profile,
)
from .common import KubernetesDistroType, TrustSourceType


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
        broker_config: Optional[dict] = None,
        add_insecure_listener: Optional[bool] = None,
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
        self.broker_config = broker_config
        self.add_insecure_listener = add_insecure_listener
        self.kubernetes_distro = kubernetes_distro
        self.container_runtime_socket = container_runtime_socket

        self.trust_source = trust_source
        self.mi_user_assigned_identities = mi_user_assigned_identities

    def _sanitize_k8s_name(self, name: str) -> str:
        if not name:
            return name
        sanitized = str(name)
        sanitized = sanitized.lower()
        sanitized = sanitized.replace("_", "-")
        return sanitized

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
                "brokerConfig": "",
                "trustConfig": "",
            },
            template_blueprint=M2_INSTANCE_TEMPLATE,
        )
        instance = template.get_resource_by_key("aioInstance")
        instance["properties"]["description"] = self.instance_description

        broker = template.get_resource_by_key("broker")
        broker_authn = template.get_resource_by_key("broker_authn")
        broker_listener = template.get_resource_by_key("broker_listener")

        if self.instance_name:
            instance["name"] = self.instance_name
            broker["name"] = f"{self.instance_name}/broker"
            broker_authn["name"] = f"{self.instance_name}/broker/broker-authn"
            broker_listener["name"] = f"{self.instance_name}/broker/broker-listener"

            template.add_resource("dataflowProfile", get_basic_dataflow_profile(instance_name=self.instance_name))

        if self.mi_user_assigned_identities:
            mi_user_payload = {}
            for mi in self.mi_user_assigned_identities:
                mi_user_payload[mi] = {}
            instance["identity"] = {}
            instance["identity"]["type"] = "UserAssigned"
            instance["identity"]["userAssignedIdentities"] = mi_user_payload

        # deploy_resources: List[dict] = content.get("resources", [])
        # df_profile_instances = self.dataflow_profile_instances
        # deploy_resources.append(get_basic_dataflow_profile(instance_count=df_profile_instances))

        # if self.broker_config:
        #     broker_config = self.broker_config
        #     if "properties" in broker_config:
        #         broker_config = broker_config["properties"]
        #     broker: dict = template.get_resource_defs("Microsoft.IoTOperations/instances/brokers")
        #     broker["properties"] = broker_config

        # if self.add_insecure_listener:
        #     # This solution entirely relies on the form of the "standard" template.
        #     # TODO - @digimaun - default resource names
        #     # TODO - @digimaun - new listener
        #     default_listener = template.get_resource_defs("Microsoft.IoTOperations/instances/brokers/listeners")
        #     if default_listener:
        #         ports: list = default_listener["properties"]["ports"]
        #         ports.append({"port": 1883})

        return template.content, parameters
