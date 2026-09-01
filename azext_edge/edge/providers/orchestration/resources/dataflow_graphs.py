# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import yaml

from typing import TYPE_CHECKING, Iterable, Optional

from knack.log import get_logger
from rich.console import Console

from azure.cli.core.azclierror import InvalidArgumentValueError
from azure.core.exceptions import ResourceNotFoundError

from ....util.az_client import wait_for_terminal_state
from ....util.common import should_continue_prompt
from ....util.machinery import scoped_semver_import
from ....util.oci_client import get_oci_client
from ....util.queryable import Queryable
from ..common import DataflowEndpointType, KAFKA_ENDPOINT_TYPE, MQTT_ENDPOINT_TYPE
from .instances import Instances
from .reskit import get_file_config

logger = get_logger(__name__)
console = Console()

# Endpoint types supported in data flow graphs (MQTT family + Kafka family + OpenTelemetry).
# DataExplorer, DataLakeStorage, FabricOneLake, LocalStorage are not supported.
_GRAPH_SUPPORTED_ENDPOINT_TYPES = frozenset([
    # MQTT family
    DataflowEndpointType.AIOLOCALMQTT.value,
    DataflowEndpointType.EVENTGRID.value,
    DataflowEndpointType.CUSTOMMQTT.value,
    MQTT_ENDPOINT_TYPE,  # legacy generic Mqtt type
    # Kafka family
    DataflowEndpointType.EVENTHUB.value,
    DataflowEndpointType.FABRICREALTIME.value,
    DataflowEndpointType.CUSTOMKAFKA.value,
    KAFKA_ENDPOINT_TYPE,  # legacy generic Kafka type
    # OpenTelemetry
    DataflowEndpointType.OPENTELEMETRY.value,
])
# Destination-only endpoint types (cannot be used as a source node).
_DESTINATION_ONLY_ENDPOINT_TYPES = frozenset([
    DataflowEndpointType.FABRICREALTIME.value,
    DataflowEndpointType.OPENTELEMETRY.value,
])
# Valid node types in a dataflow graph config.
_VALID_NODE_TYPES = frozenset(["Source", "Graph", "Destination"])


if TYPE_CHECKING:
    from ....vendor.clients.iotopsmgmt.operations import (
        DataflowEndpointOperations,
        DataflowGraphOperations,
        RegistryEndpointOperations,
    )


class DataFlowGraphs(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.instances = Instances(cmd=cmd)
        self.iotops_mgmt_client = self.instances.iotops_mgmt_client
        self.ops: "DataflowGraphOperations" = self.iotops_mgmt_client.dataflow_graph
        self.ops_endpoint: "DataflowEndpointOperations" = self.iotops_mgmt_client.dataflow_endpoint
        self.ops_registry_endpoint: "RegistryEndpointOperations" = self.iotops_mgmt_client.registry_endpoint

    def show(
        self,
        name: str,
        dataflow_profile_name: str,
        instance_name: str,
        resource_group_name: str,
    ) -> dict:
        return self.ops.get(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_profile_name=dataflow_profile_name,
            dataflow_graph_name=name,
        )

    def list(
        self,
        dataflow_profile_name: str,
        instance_name: str,
        resource_group_name: str,
    ) -> Iterable[dict]:
        return self.ops.list_by_dataflow_profile(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_profile_name=dataflow_profile_name,
        )

    def apply(
        self,
        name: str,
        dataflow_profile_name: str,
        instance_name: str,
        resource_group_name: str,
        config_file: str,
        **kwargs,
    ) -> dict:
        resource = {}
        graph_config = get_file_config(config_file)

        self._validate_graph_config(graph_config, instance_name, resource_group_name)

        resource["extendedLocation"] = self.instances.get_ext_loc(
            name=instance_name,
            resource_group_name=resource_group_name,
        )
        resource["properties"] = graph_config

        with console.status("Working..."):
            poller = self.ops.begin_create_or_update(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                dataflow_profile_name=dataflow_profile_name,
                dataflow_graph_name=name,
                resource=resource,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def _validate_graph_config(
        self,
        graph_config: dict,
        instance_name: str,
        resource_group_name: str,
    ):
        nodes, name_to_type = self._validate_nodes(graph_config)

        source_nodes = [n for n in nodes if n.get("nodeType") == "Source"]
        destination_nodes = [n for n in nodes if n.get("nodeType") == "Destination"]
        graph_nodes = [n for n in nodes if n.get("nodeType") == "Graph"]

        if not source_nodes:
            raise InvalidArgumentValueError(
                "The dataflow graph config must contain at least one node with nodeType 'Source'."
            )
        if not destination_nodes:
            raise InvalidArgumentValueError(
                "The dataflow graph config must contain at least one node with nodeType 'Destination'."
            )

        self._validate_node_connections(graph_config, name_to_type)

        endpoint_cache: dict = {}

        def get_endpoint_cached(endpoint_ref: str) -> dict:
            if endpoint_ref not in endpoint_cache:
                endpoint_cache[endpoint_ref] = self._get_endpoint(
                    endpoint_ref, instance_name, resource_group_name
                )
            return endpoint_cache[endpoint_ref]

        self._validate_source_nodes(source_nodes, get_endpoint_cached)
        self._validate_destination_nodes(destination_nodes, get_endpoint_cached)

        registry_endpoint_cache: dict = {}

        def get_registry_endpoint_cached(registry_endpoint_ref: str) -> dict:
            if registry_endpoint_ref not in registry_endpoint_cache:
                registry_endpoint_cache[registry_endpoint_ref] = self._get_registry_endpoint(
                    registry_endpoint_ref, instance_name, resource_group_name
                )
            return registry_endpoint_cache[registry_endpoint_ref]

        artifact_info_cache: dict = {}

        def get_artifact_info_cached(image_ref: str):
            if image_ref not in artifact_info_cache:
                try:
                    artifact_info_cache[image_ref] = get_oci_client().fetch_first_layer(
                        image_ref=image_ref, cmd=self.cmd
                    )
                except Exception as ex:  # best-effort: skip validation on any fetch failure
                    logger.warning(
                        "Skipped optional client-side validation for OCI artifact '%s' (could not fetch); "
                        "resource creation is unaffected. Details: %s",
                        image_ref,
                        ex,
                    )
                    artifact_info_cache[image_ref] = None
            return artifact_info_cache[image_ref]

        # The target instance's installed runtime version is only needed when the graph
        # contains transform (Graph) nodes. Fetch it lazily to avoid an extra API call.
        instance_version = (
            self._get_instance_version(instance_name, resource_group_name) if graph_nodes else None
        )

        self._validate_graph_nodes(
            graph_nodes, get_registry_endpoint_cached, get_artifact_info_cached, instance_version
        )

    def _get_instance_version(self, instance_name: str, resource_group_name: str) -> Optional[str]:
        """Return the target instance's installed AIO runtime version, or None if it cannot be determined."""
        try:
            instance = self.instances.show(name=instance_name, resource_group_name=resource_group_name)
            return (instance or {}).get("properties", {}).get("version")
        except Exception as ex:  # best-effort: skip transform runtime compatibility check on any failure
            logger.debug(
                "Could not determine runtime version for instance '%s' — skipping transform runtime "
                "compatibility check. %s",
                instance_name,
                ex,
            )
            return None

    def _validate_nodes(self, graph_config: dict):
        nodes = graph_config.get("nodes", [])
        if not isinstance(nodes, list) or not nodes:
            raise InvalidArgumentValueError(
                "'nodes' is required and must contain at least one node in the dataflow graph config."
            )

        name_to_type: dict = {}
        for i, node in enumerate(nodes):
            if not isinstance(node, dict):
                raise InvalidArgumentValueError(
                    f"Node at index {i} must be an object, got {type(node).__name__}."
                )
            node_name = node.get("name", "")
            node_type = node.get("nodeType", "")

            if not node_name:
                raise InvalidArgumentValueError(
                    f"Node at index {i} is missing a 'name'."
                )
            if not node_type:
                raise InvalidArgumentValueError(
                    f"Node '{node_name}' is missing a 'nodeType'."
                )
            if node_type not in _VALID_NODE_TYPES:
                raise InvalidArgumentValueError(
                    f"Node '{node_name}' has invalid nodeType '{node_type}'. "
                    f"Valid nodeType values are: {', '.join(sorted(_VALID_NODE_TYPES))}."
                )
            if node_name in name_to_type:
                raise InvalidArgumentValueError(
                    f"Duplicate node name '{node_name}' found at index {i}. "
                    "Each node in the dataflow graph config must have a unique 'name'."
                )
            name_to_type[node_name] = node_type

        return nodes, name_to_type

    def _validate_node_connections(self, graph_config: dict, name_to_type: dict):
        node_connections = graph_config.get("nodeConnections", [])
        if not isinstance(node_connections, list) or not node_connections:
            raise InvalidArgumentValueError(
                "'nodeConnections' is required and must contain at least one connection in the dataflow graph config."
            )
        for i, conn in enumerate(node_connections):
            if not isinstance(conn, dict):
                raise InvalidArgumentValueError(
                    f"nodeConnection at index {i} must be an object, got {type(conn).__name__}."
                )
            from_val = conn.get("from")
            to_val = conn.get("to")
            if not isinstance(from_val, dict) or not from_val.get("name"):
                raise InvalidArgumentValueError(
                    f"nodeConnection at index {i} is missing a valid 'from.name' field."
                )
            if not isinstance(to_val, dict) or not to_val.get("name"):
                raise InvalidArgumentValueError(
                    f"nodeConnection at index {i} is missing a valid 'to.name' field."
                )
            from_name = from_val["name"]
            to_name = to_val["name"]
            if from_name == to_name:
                raise InvalidArgumentValueError(
                    f"nodeConnection at index {i} is a self-loop: 'from' and 'to' both reference node '{from_name}'."
                )
            if from_name not in name_to_type:
                raise InvalidArgumentValueError(
                    f"nodeConnection at index {i} references unknown 'from' node '{from_name}'. "
                    f"Declared node names: {', '.join(sorted(name_to_type))}."
                )
            if to_name not in name_to_type:
                raise InvalidArgumentValueError(
                    f"nodeConnection at index {i} references unknown 'to' node '{to_name}'. "
                    f"Declared node names: {', '.join(sorted(name_to_type))}."
                )
            if name_to_type[from_name] == "Destination":
                raise InvalidArgumentValueError(
                    f"nodeConnection at index {i} uses Destination node '{from_name}' as a 'from' (source). "
                    "Destination nodes are sinks and cannot be the source of a connection."
                )
            if name_to_type[to_name] == "Source":
                raise InvalidArgumentValueError(
                    f"nodeConnection at index {i} uses Source node '{to_name}' as a 'to' (destination). "
                    "Source nodes are producers and cannot be the destination of a connection."
                )

    def _validate_source_nodes(self, source_nodes: list, get_endpoint_cached):
        kafka_types = {DataflowEndpointType.EVENTHUB.value, DataflowEndpointType.CUSTOMKAFKA.value, KAFKA_ENDPOINT_TYPE}
        for node in source_nodes:
            source_settings = node.get("sourceSettings", {})
            if not isinstance(source_settings, dict):
                raise InvalidArgumentValueError(
                    f"Source node '{node.get('name')}' has an invalid 'sourceSettings' field: "
                    f"expected an object, got {type(source_settings).__name__}."
                )
            endpoint_ref = source_settings.get("endpointRef", "")
            if not endpoint_ref:
                raise InvalidArgumentValueError(
                    f"Source node '{node.get('name')}' is missing 'sourceSettings.endpointRef'."
                )
            endpoint_obj = get_endpoint_cached(endpoint_ref)
            endpoint_props = endpoint_obj.get("properties", {})
            endpoint_type = endpoint_props.get("endpointType", "")

            if endpoint_type and endpoint_type not in _GRAPH_SUPPORTED_ENDPOINT_TYPES:
                raise InvalidArgumentValueError(
                    f"Source node '{node.get('name')}' references endpoint '{endpoint_ref}' "
                    f"of type '{endpoint_type}', which is not supported in data flow graphs. "
                    f"Supported endpoint types are: "
                    f"{', '.join(sorted(_GRAPH_SUPPORTED_ENDPOINT_TYPES))}."
                )
            if endpoint_type in _DESTINATION_ONLY_ENDPOINT_TYPES:
                raise InvalidArgumentValueError(
                    f"Source node '{node.get('name')}' references endpoint '{endpoint_ref}' "
                    f"of type '{endpoint_type}', which is destination-only and cannot be used as a source."
                )

            if endpoint_type in kafka_types:
                kafka_settings = endpoint_props.get("kafkaSettings") or {}
                if not kafka_settings.get("consumerGroupId", ""):
                    raise InvalidArgumentValueError(
                        f"Source node '{node.get('name')}' references Kafka endpoint '{endpoint_ref}', "
                        f"but the endpoint does not have 'kafkaSettings.consumerGroupId' set. "
                        f"A consumer group ID is required for Kafka source endpoints."
                    )

    def _validate_destination_nodes(self, destination_nodes: list, get_endpoint_cached):
        for node in destination_nodes:
            dest_settings = node.get("destinationSettings", {})
            if not isinstance(dest_settings, dict):
                raise InvalidArgumentValueError(
                    f"Destination node '{node.get('name')}' has an invalid 'destinationSettings' field: "
                    f"expected an object, got {type(dest_settings).__name__}."
                )
            endpoint_ref = dest_settings.get("endpointRef", "")
            if not endpoint_ref:
                raise InvalidArgumentValueError(
                    f"Destination node '{node.get('name')}' is missing 'destinationSettings.endpointRef'."
                )
            endpoint_obj = get_endpoint_cached(endpoint_ref)
            endpoint_type = endpoint_obj.get("properties", {}).get("endpointType", "")

            if endpoint_type and endpoint_type not in _GRAPH_SUPPORTED_ENDPOINT_TYPES:
                raise InvalidArgumentValueError(
                    f"Destination node '{node.get('name')}' references endpoint '{endpoint_ref}' "
                    f"of type '{endpoint_type}', which is not supported in data flow graphs. "
                    f"Supported endpoint types are: "
                    f"{', '.join(sorted(_GRAPH_SUPPORTED_ENDPOINT_TYPES))}."
                )

    def _validate_graph_nodes(
        self,
        graph_nodes: list,
        get_registry_endpoint_cached,
        get_artifact_info_cached,
        instance_version: Optional[str] = None,
    ):
        for node in graph_nodes:
            graph_settings = node.get("graphSettings", {})
            if not isinstance(graph_settings, dict):
                raise InvalidArgumentValueError(
                    f"Graph node '{node.get('name')}' has an invalid 'graphSettings' field: "
                    f"expected an object, got {type(graph_settings).__name__}."
                )
            registry_endpoint_ref = graph_settings.get("registryEndpointRef", "")
            if not isinstance(registry_endpoint_ref, str) or not registry_endpoint_ref.strip():
                raise InvalidArgumentValueError(
                    f"Graph node '{node.get('name')}' is missing 'graphSettings.registryEndpointRef'."
                )
            registry_endpoint_obj = get_registry_endpoint_cached(registry_endpoint_ref)
            artifact = graph_settings.get("artifact", "")
            if not artifact:
                raise InvalidArgumentValueError(
                    f"Graph node '{node.get('name')}' is missing 'graphSettings.artifact'."
                )
            if ":" not in artifact or artifact.startswith(":") or artifact.endswith(":"):
                raise InvalidArgumentValueError(
                    f"Graph node '{node.get('name')}' has an invalid 'graphSettings.artifact' value '{artifact}'. "
                    "Expected format: '<artifact-name>:<version>'."
                )
            registry_host = (registry_endpoint_obj or {}).get("properties", {}).get("host", "")
            if not isinstance(registry_host, str) or not registry_host.strip():
                raise InvalidArgumentValueError(
                    f"Graph node '{node.get('name')}' artifact '{artifact}' references a misconfigured "
                    "registry endpoint: missing required 'properties.host'."
                )
            image_ref = f"{registry_host.strip().rstrip('/')}/{artifact}"
            self._validate_graph_node_artifact_config(
                node, graph_settings, image_ref, get_artifact_info_cached, instance_version
            )

    @staticmethod
    def _is_config_entry_provided(item: dict) -> bool:
        """Return True only when a configuration entry has a valid non-empty key and value."""
        if not isinstance(item, dict):
            return False
        key = item.get("key")
        if not isinstance(key, str) or not key.strip():
            return False
        if "value" not in item or item.get("value") is None:
            return False
        value = item.get("value")
        if isinstance(value, str) and not value.strip():
            return False
        return True

    def _validate_graph_node_artifact_config(
        self,
        node: dict,
        graph_settings: dict,
        image_ref: str,
        get_artifact_info_cached,
        instance_version: Optional[str] = None,
    ):
        """Fetch the OCI artifact YAML layer and validate the transform against the target instance.

        Two client-side checks are performed against the transform manifest:
          1. Runtime compatibility — the manifest's moduleRequirements.runtimeVersion must not be
             newer than the target instance's installed AIO runtime version.
          2. Required parameters — moduleConfigurations[*].parameters entries marked 'required'
             must each appear as a {"key": ..., "value": ...} entry in graphSettings.configuration.

        This is a best-effort, client-side check. If the OCI artifact cannot be fetched (e.g.,
        due to network issues, auth failure, or an invalid reference), a warning is logged and
        validation is skipped — the apply proceeds and server-side validation will catch any issues.
        """
        artifact_info = get_artifact_info_cached(image_ref)
        if artifact_info is None:
            return

        try:
            yaml_data = yaml.safe_load(artifact_info.content.decode("utf-8"))
        except (yaml.YAMLError, UnicodeDecodeError, AttributeError, TypeError) as ex:
            logger.debug(
                "OCI artifact '%s' does not contain valid YAML — skipping config validation. %s",
                image_ref,
                ex,
            )
            return
        if not isinstance(yaml_data, dict):
            logger.debug(
                "OCI artifact '%s' has unexpected YAML structure — skipping config validation.",
                image_ref,
            )
            return

        self._validate_transform_runtime_compatibility(node, graph_settings, yaml_data, instance_version)

        required_params: set = set()
        module_configurations = yaml_data.get("moduleConfigurations") or []
        if isinstance(module_configurations, list):
            for module_config in module_configurations:
                if not isinstance(module_config, dict):
                    continue
                parameters = module_config.get("parameters", {})
                if isinstance(parameters, dict):
                    for param_name, param_info in parameters.items():
                        if isinstance(param_info, dict) and param_info.get("required") is True:
                            required_params.add(param_name)

        if required_params:
            configuration = graph_settings.get("configuration") or []
            if not isinstance(configuration, list):
                configuration = []
            provided_keys = {
                item.get("key")
                for item in configuration
                if self._is_config_entry_provided(item)
            }
            missing = required_params - provided_keys
            if missing:
                artifact = graph_settings.get("artifact", "")
                artifact_description = (
                    f"artifact '{artifact}' (resolved image '{image_ref}')"
                    if artifact and artifact != image_ref
                    else f"image '{image_ref}'"
                )
                missing_params = ", ".join(f"'{p}'" for p in sorted(missing))
                raise InvalidArgumentValueError(
                    f"Graph node '{node.get('name')}' {artifact_description} requires "
                    f"configuration parameter(s) {missing_params} but they are not provided in "
                    "'graphSettings.configuration'. Each required parameter must be supplied as a "
                    '{"key": "<param-name>", "value": "<value>"} entry.'
                )

    def _validate_transform_runtime_compatibility(
        self,
        node: dict,
        graph_settings: dict,
        yaml_data: dict,
        instance_version: Optional[str],
    ):
        """Ensure the transform's required runtime is not newer than the target instance.

        The transform manifest declares its minimum runtime via
        moduleRequirements.runtimeVersion. If the target instance is running an older
        AIO runtime than the transform requires, the graph is incompatible and the apply
        is blocked — mirroring the UX (isRuntimeVersionCompatible in runtimeCompatibility.ts).

        This check deliberately fails open: if the required runtime or the instance version
        is missing or malformed (unparseable), validation is skipped and enforcement is
        deferred to the runtime. This handles both built-in and custom transforms.
        """
        module_requirements = yaml_data.get("moduleRequirements")
        if not isinstance(module_requirements, dict):
            return
        required_runtime = module_requirements.get("runtimeVersion")
        # Fail open when the transform does not declare a required runtime version.
        if not isinstance(required_runtime, str) or not required_runtime.strip():
            return
        # Fail open when the target instance version cannot be determined.
        if not isinstance(instance_version, str) or not instance_version.strip():
            logger.debug(
                "Target instance runtime version is unknown — skipping runtime compatibility "
                "check for graph node '%s'.",
                node.get("name"),
            )
            return

        semver = scoped_semver_import()
        try:
            parsed_required = semver.parse(required_runtime.strip(), optional_minor_and_patch=True)
            parsed_instance = semver.parse(instance_version.strip(), optional_minor_and_patch=True)
        except ValueError as ex:
            # Fail open on malformed versions; defer to runtime enforcement.
            logger.debug(
                "Could not compare runtime versions (required '%s', instance '%s') for graph node "
                "'%s' — skipping runtime compatibility check. %s",
                required_runtime,
                instance_version,
                node.get("name"),
                ex,
            )
            return

        if parsed_instance < parsed_required:
            artifact = graph_settings.get("artifact", "")
            raise InvalidArgumentValueError(
                f"Graph node '{node.get('name')}' transform '{artifact}' requires Azure IoT "
                f"Operations runtime version '{required_runtime}' or newer, but the target "
                f"instance is running '{instance_version}'. Select a transform version "
                "compatible with the installed runtime, or upgrade the instance."
            )

    def _get_endpoint(
        self,
        endpoint_name: str,
        instance_name: str,
        resource_group_name: str,
    ) -> dict:
        """Fetch a dataflow endpoint by name, raising a clear error if not found."""
        try:
            return self.ops_endpoint.get(
                instance_name=instance_name,
                resource_group_name=resource_group_name,
                dataflow_endpoint_name=endpoint_name,
            )
        except ResourceNotFoundError:
            raise ResourceNotFoundError(
                f"Dataflow endpoint '{endpoint_name}' not found in instance '{instance_name}'. "
                "Please provide a valid 'endpointRef' using --config-file."
            )

    def _get_registry_endpoint(
        self,
        registry_endpoint_name: str,
        instance_name: str,
        resource_group_name: str,
    ) -> dict:
        """Fetch a registry endpoint by name, raising a clear error if not found."""
        try:
            return self.ops_registry_endpoint.get(
                instance_name=instance_name,
                resource_group_name=resource_group_name,
                registry_endpoint_name=registry_endpoint_name,
            )
        except ResourceNotFoundError:
            raise ResourceNotFoundError(
                f"Registry endpoint '{registry_endpoint_name}' not found in instance '{instance_name}'. "
                "Please provide a valid 'registryEndpointRef' using --config-file."
            )

    def delete(
        self,
        name: str,
        dataflow_profile_name: str,
        instance_name: str,
        resource_group_name: str,
        confirm_yes: Optional[bool] = None,
        **kwargs,
    ):
        should_bail = not should_continue_prompt(confirm_yes=confirm_yes)
        if should_bail:
            return

        with console.status("Working..."):
            poller = self.ops.begin_delete(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                dataflow_profile_name=dataflow_profile_name,
                dataflow_graph_name=name,
            )
            return wait_for_terminal_state(poller, **kwargs)
