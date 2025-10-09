# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from enum import IntEnum
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

from azure.cli.core.azclierror import InvalidArgumentValueError

from ...common import (
    DEFAULT_BROKER,
    DEFAULT_BROKER_AUTHN,
    DEFAULT_BROKER_LISTENER,
    DEFAULT_DATAFLOW_ENDPOINT,
    DEFAULT_DATAFLOW_PROFILE,
    DEFAULT_ARTIFACT_REGISTRY,
)
from ...util import parse_kvp_nargs, url_safe_hash_phrase
from ...util.id_tools import is_valid_resource_id, parse_resource_id
from ..orchestration.common import (
    EXTENSION_MONIKER_CM,
    EXTENSION_MONIKER_OPS,
    EXTENSION_MONIKER_SSC,
    TRUST_ISSUER_KIND_KEY,
    TRUST_SETTING_KEYS,
)
from ..orchestration.resources.brokers import Brokers
from ..orchestration.resources.instances import parse_feature_kvp_nargs
from .template import (
    TEMPLATE_BLUEPRINT_ENABLEMENT,
    TEMPLATE_BLUEPRINT_INSTANCE,
    TemplateBlueprint,
    get_insecure_listener,
)


class InstancePhase(IntEnum):
    EXT = 1
    INSTANCE = 2
    RESOURCES = 3


PHASE_KEY_MAP: Dict[str, Set[str]] = {
    InstancePhase.EXT: {"cluster", "aioExtension"},
    InstancePhase.INSTANCE: {"aioInstance"},
}


class VarAttr(NamedTuple):
    value: str
    template_key: str
    moniker: str


class InitTargets:
    def __init__(
        self,
        cluster_name: str,
        resource_group_name: str,
        schema_registry_resource_id: Optional[str] = None,
        adr_namespace_resource_id: Optional[str] = None,
        cluster_namespace: str = "azure-iot-operations",
        location: Optional[str] = None,
        custom_location_name: Optional[str] = None,
        instance_name: Optional[str] = None,
        instance_description: Optional[str] = None,
        instance_features: Optional[List[str]] = None,
        tags: Optional[dict] = None,
        # Extension config
        ops_config: Optional[List[str]] = None,
        ops_version: Optional[str] = None,
        ops_train: Optional[str] = None,
        ssc_config: Optional[List[str]] = None,
        ssc_version: Optional[str] = None,
        ssc_train: Optional[str] = None,
        cm_config: Optional[List[str]] = None,
        cm_version: Optional[str] = None,
        cm_train: Optional[str] = None,
        # Dataflow
        dataflow_profile_instances: int = 1,
        # Broker
        custom_broker_config: Optional[dict] = None,
        broker_memory_profile: Optional[str] = None,
        broker_backend_partitions: Optional[int] = None,
        broker_backend_workers: Optional[int] = None,
        broker_backend_redundancy_factor: Optional[int] = None,
        broker_frontend_workers: Optional[int] = None,
        broker_frontend_replicas: Optional[int] = None,
        add_insecure_listener: Optional[bool] = None,
        # Broker data persistence
        persist_max_size: Optional[str] = None,
        persist_pvc_sc: Optional[str] = None,
        persist_mode: Optional[List[str]] = None,
        # User Trust Config
        user_trust: Optional[bool] = None,
        trust_settings: Optional[List[str]] = None,
        **_,
    ):
        self.cluster_name = cluster_name
        self.resource_group_name = resource_group_name
        self.schema_registry_resource_id = ensure_resource_id(
            schema_registry_resource_id,
            match_context={
                "resource_provider": "Microsoft.DeviceRegistry",
                "resource_type": "schemaRegistries",
            },
            parameter="--sr-resource-id",
        )
        self.adr_namespace_resource_id = ensure_resource_id(
            adr_namespace_resource_id,
            match_context={
                "resource_group": resource_group_name,
                "resource_provider": "Microsoft.DeviceRegistry",
                "resource_type": "namespaces",
            },
            parameter="--ns-resource-id",
        )
        self.cluster_namespace = self._sanitize_k8s_name(cluster_namespace)
        self.location = location
        if not custom_location_name:
            custom_location_name = get_default_cl_name(
                resource_group_name=resource_group_name, cluster_name=cluster_name, namespace=cluster_namespace
            )
        else:
            # We need to do this because the RP doesnt :)
            if len(custom_location_name) > 63:
                raise InvalidArgumentValueError("Custom location name must be 63 characters or less.")

        self.custom_location_name = self._sanitize_k8s_name(custom_location_name)
        self.instance_name = self._sanitize_k8s_name(instance_name)
        self.instance_description = instance_description
        self.instance_features = parse_feature_kvp_nargs(instance_features, strict=True)
        self.tags = tags

        # Extensions
        self.extension_manager = ExtensionConfigManager()
        self.extension_manager.register_extension(
            moniker=EXTENSION_MONIKER_CM,
            version=cm_version,
            train=cm_train,
            user_config=parse_kvp_nargs(cm_config),
            default_config_getter=get_default_cm_config,
        )
        self.extension_manager.register_extension(
            moniker=EXTENSION_MONIKER_SSC,
            version=ssc_version,
            train=ssc_train,
            user_config=parse_kvp_nargs(ssc_config),
            default_config_getter=get_default_ssc_config,
        )
        self.extension_manager.register_extension(
            moniker=EXTENSION_MONIKER_OPS,
            version=ops_version,
            train=ops_train,
            user_config=parse_kvp_nargs(ops_config),
        )

        self.user_trust = user_trust
        self.trust_settings = parse_kvp_nargs(trust_settings)
        self.trust_config = self.get_trust_settings_target_map()

        # Dataflow
        self.dataflow_profile_instances = self._sanitize_int(dataflow_profile_instances)

        # Broker
        self.add_insecure_listener = add_insecure_listener
        self.broker_memory_profile = broker_memory_profile
        self.broker_backend_partitions = self._sanitize_int(broker_backend_partitions)
        self.broker_backend_workers = self._sanitize_int(broker_backend_workers)
        self.broker_backend_redundancy_factor = self._sanitize_int(broker_backend_redundancy_factor)
        self.broker_frontend_workers = self._sanitize_int(broker_frontend_workers)
        self.broker_frontend_replicas = self._sanitize_int(broker_frontend_replicas)
        self.custom_broker_config = custom_broker_config
        self.persist_max_size = persist_max_size
        self.persist_pvc_sc = persist_pvc_sc
        self.persist_mode = parse_kvp_nargs(persist_mode)
        self.broker_config = self.get_broker_config_target_map()

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

    def get_extension_versions(self, for_enablement: bool = True) -> dict:
        version_map = {}
        get_template_method = self.get_ops_enablement_template
        if not for_enablement:
            get_template_method = self.get_ops_instance_template
        template, _ = get_template_method()
        template_vars = template["variables"]
        for moniker in template_vars["VERSIONS"]:
            version_map[moniker] = {"version": template_vars["VERSIONS"][moniker]}
        for moniker in template_vars["TRAINS"]:
            version_map[moniker]["train"] = template_vars["TRAINS"][moniker]

        return version_map

    def get_ops_enablement_template(
        self,
    ) -> Tuple[dict, dict]:
        template, parameters = self._handle_apply_targets(
            param_to_target={
                "clusterName": self.cluster_name,
                "trustConfig": self.trust_config,
            },
            template_blueprint=TEMPLATE_BLUEPRINT_ENABLEMENT,
        )

        self.extension_manager.apply_to_template(template.content)

        if self.user_trust:
            # patch enablement template expecting full trust settings for source: CustomerManaged
            template.get_type_definition("_1.CustomerManaged")["properties"]["settings"]["nullable"] = True
        return template.content, parameters

    def get_ops_instance_template(
        self,
        cl_extension_ids: Optional[List[str]] = None,
        phase: Optional[InstancePhase] = None,
    ) -> Tuple[dict, dict]:
        if not cl_extension_ids:
            cl_extension_ids = []
        template, parameters = self._handle_apply_targets(
            param_to_target={
                "clusterName": self.cluster_name,
                "clusterNamespace": self.cluster_namespace,
                "clusterLocation": self.location,
                "customLocationName": self.custom_location_name,
                "clExtensionIds": cl_extension_ids,
                "schemaRegistryId": self.schema_registry_resource_id,
                "adrNamespaceId": self.adr_namespace_resource_id,
                "defaultDataflowInstanceCount": self.dataflow_profile_instances,
                "brokerConfig": self.broker_config,
                "trustConfig": self.trust_config,
            },
            template_blueprint=TEMPLATE_BLUEPRINT_INSTANCE,
        )

        self.extension_manager.apply_to_template(template.content, template_type="instance")

        instance = template.get_resource_by_key("aioInstance")
        broker = template.get_resource_by_key("broker")
        broker_authn = template.get_resource_by_key("brokerAuthn")
        broker_listener = template.get_resource_by_key("brokerListener")
        dataflow_profile = template.get_resource_by_key("dataflowProfile")
        dataflow_endpoint = template.get_resource_by_key("dataflowEndpoint")
        artifact_registry_endpoint = template.get_resource_by_key("artifactRegistryEndpoint")

        instance["properties"] = get_default_instance_config(
            description=self.instance_description,
            features=self.instance_features,
        )

        if self.instance_name:
            instance["name"] = self.instance_name
            broker["name"] = f"{self.instance_name}/{DEFAULT_BROKER}"
            broker_authn["name"] = f"{self.instance_name}/{DEFAULT_BROKER}/{DEFAULT_BROKER_AUTHN}"
            broker_listener["name"] = f"{self.instance_name}/{DEFAULT_BROKER}/{DEFAULT_BROKER_LISTENER}"
            dataflow_profile["name"] = f"{self.instance_name}/{DEFAULT_DATAFLOW_PROFILE}"
            dataflow_endpoint["name"] = f"{self.instance_name}/{DEFAULT_DATAFLOW_ENDPOINT}"
            artifact_registry_endpoint["name"] = f"{self.instance_name}/{DEFAULT_ARTIFACT_REGISTRY}"

            template.content["outputs"]["aio"]["value"]["name"] = self.instance_name

        if self.tags:
            instance["tags"] = self.tags

        if self.custom_broker_config:
            if "properties" in self.custom_broker_config:
                self.custom_broker_config = self.custom_broker_config["properties"]
            broker["properties"] = self.custom_broker_config

        if self.add_insecure_listener:
            template.add_resource(
                resource_key="brokerListenerInsecure",
                resource_def=get_insecure_listener(instance_name=self.instance_name, broker_name=DEFAULT_BROKER),
            )

        resources: Dict[str, Dict[str, dict]] = template.content.get("resources", {})
        if phase == InstancePhase.EXT:
            del_if_not_in(resources, PHASE_KEY_MAP[InstancePhase.EXT])
            return template.content, parameters

        tracked_keys = (
            PHASE_KEY_MAP[InstancePhase.EXT].union(PHASE_KEY_MAP[InstancePhase.INSTANCE]).union({"customLocation"})
        )
        if phase == InstancePhase.INSTANCE:
            del_if_not_in(
                resources,
                tracked_keys,
            )
            set_read_only(resources, PHASE_KEY_MAP[InstancePhase.EXT].union({"customLocation"}))
            return template.content, parameters

        if phase == InstancePhase.RESOURCES:
            set_read_only(resources, tracked_keys)

        return template.content, parameters

    def get_broker_config_target_map(self):
        to_process_config_map = {
            "frontendReplicas": self.broker_frontend_replicas,
            "frontendWorkers": self.broker_frontend_workers,
            "backendRedundancyFactor": self.broker_backend_redundancy_factor,
            "backendWorkers": self.broker_backend_workers,
            "backendPartitions": self.broker_backend_partitions,
            "memoryProfile": self.broker_memory_profile,
        }
        processed_config_map = {}

        validation_errors = []
        broker_config_def = TEMPLATE_BLUEPRINT_INSTANCE.get_type_definition("_1.BrokerConfig")["properties"]
        if not broker_config_def:
            return to_process_config_map
        # TODO @digimaun - replace with longer term pattern
        broker_config_def["backendRedundancyFactor"]["minValue"] = 2

        for config in to_process_config_map:
            if to_process_config_map[config] is None:
                continue
            processed_config_map[config] = to_process_config_map[config]

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

        built_config = Brokers.build_broker_config(
            persist_max_size=self.persist_max_size,
            persist_pvc_sc=self.persist_pvc_sc,
            persist_mode=self.persist_mode,
        )
        if built_config:
            processed_config_map.update(built_config)

        return processed_config_map

    def get_trust_settings_target_map(self) -> dict:
        source = "SelfSigned"
        if self.trust_settings or self.user_trust:
            source = "CustomerManaged"
        result = {"source": source}
        if self.trust_settings:
            target_settings: Dict[str, str] = {}
            trust_bundle_def = TEMPLATE_BLUEPRINT_ENABLEMENT.get_type_definition("_1.TrustBundleSettings")["properties"]
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


def get_default_cl_name(resource_group_name: str, cluster_name: str, namespace: str) -> str:
    return "location-" + url_safe_hash_phrase(f"{resource_group_name}{cluster_name}{namespace}")[:5]


def set_read_only(resources: Dict[str, Dict[str, dict]], resource_keys: Set[str]):
    for r in resource_keys:
        res: dict = resources.get(r, {})
        for k in list(res.keys()):
            if k not in {"type", "apiVersion", "name", "scope", "condition"}:
                del res[k]
        res["existing"] = True


def del_if_not_in(resources: Dict[str, Dict[str, dict]], include_keys: Set[str]):
    for k in list(resources.keys()):
        if k not in include_keys:
            del resources[k]


def get_default_instance_config(
    description: Optional[str] = None,
    features: Optional[dict] = None,
) -> dict:
    return {
        "schemaRegistryRef": {"resourceId": "[parameters('schemaRegistryId')]"},
        "adrNamespaceRef": {"resourceId": "[parameters('adrNamespaceId')]"},
        "description": description,
        "features": features,
    }


def ensure_resource_id(
    resource_id: Optional[str], match_context: Optional[dict] = None, parameter: Optional[str] = None
) -> Optional[str]:
    if not resource_id:
        return
    parameter = parameter or f"Resource Id '{resource_id}'"
    if is_valid_resource_id(resource_id):
        parsed_id = parse_resource_id(resource_id)  # Validate the resource ID format
        resource_name = parsed_id.get("name")
        if resource_name:
            if match_context:
                match_resource_group: str = match_context.get("resource_group", "")
                match_rp = match_context.get("resource_provider", "")
                match_type = match_context.get("resource_type", "")
                if match_resource_group:
                    if parsed_id.get("resource_group", "").lower() != match_resource_group.lower():
                        raise InvalidArgumentValueError(
                            f"{parameter} value must match the resource group '{match_resource_group}'."
                        )
                if match_rp and match_type:
                    if any(
                        [
                            parsed_id.get("namespace", "").lower() != match_rp.lower(),
                            parsed_id.get("type", "").lower() != match_type.lower(),
                        ]
                    ):
                        raise InvalidArgumentValueError(f"{parameter} value must be of type {match_rp}/{match_type}.")
            return resource_id

    raise InvalidArgumentValueError(
        f"{parameter} is malformed. An Azure resource Id has the form:\n"
        "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroup}"
        "/providers/Microsoft.Provider/{resourceType}/{resourceName}"
    )


class ExtensionConfig(NamedTuple):
    moniker: str
    version: Optional[str] = None
    train: Optional[str] = None
    config: Optional[Dict[str, str]] = None
    default_config_getter: Optional[callable] = None


class ExtensionConfigManager:
    def __init__(self):
        self.extensions: Dict[str, ExtensionConfig] = {}
        # Map monikers to their resource keys in templates
        self.resource_key_map = {
            EXTENSION_MONIKER_CM: "certManagerExtension",
            EXTENSION_MONIKER_SSC: "secretStoreExtension",
            EXTENSION_MONIKER_OPS: "aioExtension",
        }

    def register_extension(
        self,
        moniker: str,
        version: Optional[str] = None,
        train: Optional[str] = None,
        user_config: Optional[Dict[str, str]] = None,
        default_config_getter: Optional[callable] = None,
    ) -> None:
        self.extensions[moniker] = ExtensionConfig(
            moniker=moniker,
            version=version,
            train=train,
            config=user_config,
            default_config_getter=default_config_getter,
        )

    def get_merged_config(self, moniker: str, template_defaults: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        if moniker not in self.extensions:
            return {}

        ext = self.extensions[moniker]
        config = {}

        # Use template defaults if provided (for iotOperations)
        if template_defaults:
            config = template_defaults.copy()
        elif ext.default_config_getter:
            config = ext.default_config_getter()

        if ext.config:
            config.update(ext.config)

        return config

    def apply_to_template(self, template: dict, template_type: str = "enablement") -> None:
        """Apply all extension configurations to a template.

        Args:
            template: The template dictionary to modify
            template_type: Either "enablement" or "instance" to handle different templates
        """
        for ext in self.extensions.values():
            resource_key = self.resource_key_map.get(ext.moniker)
            if not resource_key:
                continue

            # Apply config settings
            if resource_key in template.get("resources", {}):
                if ext.moniker == EXTENSION_MONIKER_OPS and template_type == "instance":
                    # For IoT Operations, merge with existing defaultAioConfigurationSettings
                    default_config = template.get("variables", {}).get("defaultAioConfigurationSettings", {})
                    merged_config = self.get_merged_config(ext.moniker, default_config)
                    if merged_config:
                        template["variables"]["defaultAioConfigurationSettings"] = merged_config
                else:
                    # Standard extension configuration
                    config = self.get_merged_config(ext.moniker)
                    if config:
                        template["resources"][resource_key]["properties"]["configurationSettings"] = config

            if ext.version:
                template.setdefault("variables", {}).setdefault("VERSIONS", {})[ext.moniker] = ext.version

            if ext.train:
                template.setdefault("variables", {}).setdefault("TRAINS", {})[ext.moniker] = ext.train


def get_default_ssc_config() -> Dict[str, str]:
    return {
        "rotationPollIntervalInSeconds": "120",
        "validatingAdmissionPolicies.applyPolicies": "false",
    }


def get_default_cm_config() -> Dict[str, str]:
    return {
        "AgentOperationTimeoutInMinutes": "20",
        "global.telemetry.enabled": "true",
    }
