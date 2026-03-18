# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import os
from typing import Any, Dict, Optional, Tuple
from knack.log import get_logger
from azure.cli.core.azclierror import ValidationError
from azure.cli.core.commands.client_factory import get_subscription_id
from ...util.az_client import get_iotops_mgmt_client
from ...util.oci_client import get_oci_client

logger = get_logger(__name__)


class ConnectorMetadataValidator:
    """Validates Asset sub-resources against schemas from Connector Template metadata."""

    _METADATA_CACHE = {}
    _CONNECTOR_SCHEMA_CACHE = None

    CONNECTOR_TEMPLATE_MANIFEST_TYPE = "connectortemplate"
    _RESOURCE_TYPE_CONFIG_MEDIA_TYPES = {
        CONNECTOR_TEMPLATE_MANIFEST_TYPE: "application/vnd.microsoft.akri-connector.v1+json",
    }

    _CONFIG_KEY_DATASET = "datasetConfiguration"
    _CONFIG_KEY_DATAPOINT = "dataPointConfiguration"
    _CONFIG_KEY_EVENT = "eventConfiguration"
    _CONFIG_KEY_EVENT_GROUP = "eventGroupConfiguration"

    _SCHEMA_KEY_DATASET = "datasetConfigurationSchema"
    _SCHEMA_KEY_DATAPOINT = "dataPointConfigurationSchema"
    _SCHEMA_KEY_EVENT = "eventConfigurationSchema"
    _SCHEMA_KEY_EVENT_GROUP = "eventGroupConfigurationSchema"
    _SCHEMA_KEY_ADDITIONAL = "additionalConfigurationSchema"
    _SCHEMA_KEY_ACTION = "actionConfigurationSchema"
    _SCHEMA_KEY_MGMT_GROUP = "managementGroupConfigurationSchema"

    _RESOURCE_KIND_DATASETS = "datasets"
    _RESOURCE_KIND_DATAPOINTS = "datapoints"
    _RESOURCE_KIND_EVENTS = "events"
    _RESOURCE_KIND_EVENT_GROUPS = "event_groups"

    _ENDPOINT_TYPE_OPCUA = "microsoft.opcua"

    _SCHEMA_PATHS: Dict[str, Tuple[str, ...]] = {}

    @classmethod
    def _init_schema_paths(cls) -> None:
        """Initialize schema paths mapping for traversing endpoint metadata."""
        if not cls._SCHEMA_PATHS:
            cls._SCHEMA_PATHS = {
                cls._SCHEMA_KEY_DATASET: ("datasets", cls._SCHEMA_KEY_DATASET),
                cls._SCHEMA_KEY_DATAPOINT: ("datasets", "dataPoints", cls._SCHEMA_KEY_DATAPOINT),
                cls._SCHEMA_KEY_EVENT: ("eventGroups", "events", cls._SCHEMA_KEY_EVENT),
                cls._SCHEMA_KEY_EVENT_GROUP: ("eventGroups", cls._SCHEMA_KEY_EVENT_GROUP),
                cls._SCHEMA_KEY_ADDITIONAL: (cls._SCHEMA_KEY_ADDITIONAL,),
                cls._SCHEMA_KEY_ACTION: ("managementGroups", "managementGroupActions", cls._SCHEMA_KEY_ACTION),
                cls._SCHEMA_KEY_MGMT_GROUP: ("managementGroups", cls._SCHEMA_KEY_MGMT_GROUP),
            }

    def _make_metadata_cache_key(self) -> str:
        """Generate a unique cache key for this endpoint's metadata."""
        return ":".join([
            get_subscription_id(cli_ctx=self.cmd.cli_ctx) or "unknown-subscription",
            self.resource_group_name or "unknown-rg",
            self.instance_name or "unknown-instance",
            self.endpoint_type or "unknown-endpoint",
            self.endpoint_version or "none",
        ])

    def __init__(
        self,
        cmd,
        resource_group_name: str,
        instance_name: str,
        endpoint_type: str,
        endpoint_version: Optional[str] = None,
    ):
        self.cmd = cmd
        self.resource_group_name = resource_group_name
        self.instance_name = instance_name
        self.endpoint_type = endpoint_type
        self.endpoint_version = endpoint_version
        self.metadata = self._get_metadata()
        self._matched_endpoint = None

    @classmethod
    def from_asset(
        cls, cmd, asset: Dict[str, Any], instance_name: str, instance_resource_group: str
    ) -> "ConnectorMetadataValidator":
        """Create validator from an asset by looking up its device and endpoint."""
        from ...util.id_tools import parse_resource_id

        asset_id_str = asset.get("id", "")
        if not asset_id_str:
            raise ValidationError("Asset does not have an ID.")

        asset_id = parse_resource_id(asset_id_str)
        if not asset_id:
            raise ValidationError(f"Invalid asset ID: {asset_id_str}")

        asset_resource_group = asset_id.get("resource_group")

        namespace_name = None
        namespace_value = (asset_id.get("namespace") or "").lower()
        type_value = (asset_id.get("type") or "").lower()
        child_type_value = (asset_id.get("child_type_1") or "").lower()

        if (
            namespace_value == "microsoft.deviceregistry"
            and type_value == "namespaces"
            and child_type_value == "assets"
        ):
            namespace_name = asset_id.get("name")

        if not namespace_name:
            raise ValidationError(
                f"Could not extract namespace from asset ID: {asset_id_str}. "
                f"Expected format: .../namespaces/{{namespace}}/assets/{{asset}}"
            )

        device_ref = asset.get("deviceRef") or asset.get("properties", {}).get("deviceRef", {})
        device_name = device_ref.get("deviceName")
        endpoint_name = device_ref.get("endpointName")

        if not device_name or not endpoint_name:
            raise ValidationError(
                "Asset must reference a device and endpoint via deviceRef.deviceName and deviceRef.endpointName"
            )

        from ...util.az_client import get_registry_mgmt_client

        registry_client = get_registry_mgmt_client(
            subscription_id=asset_id.get("subscription"),
        )

        device = registry_client.namespace_devices.get(
            resource_group_name=asset_resource_group,
            namespace_name=namespace_name,
            device_name=device_name,
        )

        endpoints_inbound = device.get("properties", {}).get("endpoints", {}).get("inbound", {})
        endpoint = endpoints_inbound.get(endpoint_name)

        if not endpoint:
            raise ValidationError(f"Device '{device_name}' does not have inbound endpoint '{endpoint_name}'.")

        endpoint_type = endpoint.get("endpointType")
        endpoint_version = endpoint.get("version")

        if not endpoint_type:
            raise ValidationError(f"Endpoint '{endpoint_name}' does not have endpointType specified.")

        return cls(
            cmd=cmd,
            resource_group_name=instance_resource_group,
            instance_name=instance_name,
            endpoint_type=endpoint_type,
            endpoint_version=endpoint_version,
        )

    def _load_local_opcua_metadata(self) -> Dict[str, Any]:
        """Load OPC UA connector metadata from local bundled JSON file."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        schema_file = os.path.join(current_dir, "schemas", "opcua_connector_metadata.json")

        if not os.path.exists(schema_file):
            raise ValidationError(f"OPC UA metadata file not found: {schema_file}")

        try:
            with open(schema_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (OSError, IOError) as e:
            raise ValidationError(f"Failed to read local OPC UA metadata file: {e}")
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON in local OPC UA metadata file: {e}")

    def _get_metadata(self) -> Optional[Dict[str, Any]]:
        """Retrieve connector metadata from cache, local file (OPC UA), or OCI registry."""
        cache_key = self._make_metadata_cache_key()
        if cache_key in self._METADATA_CACHE:
            return self._METADATA_CACHE[cache_key]

        et_lower = (self.endpoint_type or "").lower()
        version_empty = (self.endpoint_version is None) or (str(self.endpoint_version).strip() == "")

        if et_lower == self._ENDPOINT_TYPE_OPCUA and version_empty:
            metadata = self._load_local_opcua_metadata()
            self._METADATA_CACHE[cache_key] = metadata
            return metadata

        try:
            from ...vendor.clients.iotopsmgmt import MicrosoftIoTOperationsManagementService

            iotops_client: MicrosoftIoTOperationsManagementService = get_iotops_mgmt_client(
                subscription_id=get_subscription_id(cli_ctx=self.cmd.cli_ctx),
                endpoint=self.cmd.cli_ctx.cloud.endpoints.resource_manager,
            )

            connector_templates = list(
                iotops_client.akri_connector_template.list_by_instance_resource(
                    resource_group_name=self.resource_group_name, instance_name=self.instance_name
                )
            )

            matched_template = None
            for template in connector_templates:
                template_name = template.get("name")
                device_endpoint_types = template.get("properties", {}).get("deviceInboundEndpointTypes", [])

                for endpoint_type_info in device_endpoint_types:
                    et = endpoint_type_info.get("endpointType")
                    ev = endpoint_type_info.get("version")

                    # Match endpoint type
                    if not et or et.lower() != self.endpoint_type.lower():
                        continue

                    # If device specifies a version, template must have the same version
                    if self.endpoint_version:
                        if not ev or str(ev) != str(self.endpoint_version):
                            continue

                    logger.info(
                        f"Matched connector template '{template_name}' for endpoint type "
                        f"'{self.endpoint_type}' version '{self.endpoint_version or ev}'"
                    )
                    matched_template = template
                    break

                if matched_template:
                    break

            if not matched_template:
                logger.info(
                    f"No connector template found for endpoint type '{self.endpoint_type}' "
                    f"version '{self.endpoint_version}'. Validation will be skipped."
                )
                return None

            connector_metadata_ref = matched_template.get("properties", {}).get("connectorMetadataRef")
            if not connector_metadata_ref:
                logger.info(
                    f"Connector template '{matched_template.get('name')}' is missing connectorMetadataRef. "
                    "Validation will be skipped."
                )
                return None

            logger.info(f"Fetching connector metadata from OCI: {connector_metadata_ref}")
            metadata = self._fetch_connector_metadata_from_oci(connector_metadata_ref)
            self._METADATA_CACHE[cache_key] = metadata

            return metadata

        except Exception as e:
            logger.error(f"Failed to fetch connector metadata: {e}")
            raise

    def _fetch_connector_metadata_from_oci(self, image_ref: str) -> Dict[str, Any]:
        """Fetch connector metadata from an OCI registry.

        Args:
            image_ref: OCI image reference (e.g., "registry/repo:tag").

        Returns:
            Parsed and validated connector metadata dictionary.
        """
        logger.info(f"Fetching OCI artifact: {image_ref}")

        oci_client = get_oci_client()
        expected_media_type = self._get_expected_config_media_type(self.CONNECTOR_TEMPLATE_MANIFEST_TYPE)

        # Fetch first layer using the OCI client's high-level API
        artifact_info = oci_client.fetch_first_layer(
            image_ref=image_ref,
            cmd=self.cmd,
            expected_config_media_type=expected_media_type,
        )

        # Extract metadata from blob content
        metadata = self._extract_metadata_from_blob(
            content=artifact_info.content,
            content_type=artifact_info.content_type,
            image_ref=image_ref,
        )

        # Validate metadata structure and schema
        self._validate_connector_metadata(metadata, image_ref)

        endpoint_count = len(metadata.get('inboundEndpoints', []))
        logger.info(f"Found valid connector metadata with {endpoint_count} inbound endpoints")

        return metadata

    @classmethod
    def _get_expected_config_media_type(cls, manifest_type: str) -> Optional[str]:
        """Return the expected config media type for a manifest type."""
        if manifest_type == cls.CONNECTOR_TEMPLATE_MANIFEST_TYPE:
            override = os.environ.get("AZ_IOTOPS_CONNECTOR_TEMPLATE_CONFIG_MEDIA_TYPE")
            if override:
                return override

        return cls._RESOURCE_TYPE_CONFIG_MEDIA_TYPES.get(manifest_type)

    @classmethod
    def _extract_metadata_from_blob(cls, content: bytes, content_type: str, image_ref: str) -> Dict[str, Any]:
        """Parse connector metadata blob as JSON."""
        try:
            return json.loads(content.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise ValidationError(f"Artifact at {image_ref} is not valid JSON: {e}")

    @classmethod
    def _validate_connector_metadata(cls, metadata: Dict[str, Any], image_ref: str) -> None:
        """Validate connector metadata against schema."""
        import jsonschema

        try:
            schema = cls._get_connector_metadata_schema()
            jsonschema.validate(instance=metadata, schema=schema)
        except jsonschema.ValidationError as e:
            raise ValidationError(f"Connector metadata does not match schema: {e.message}")
        except jsonschema.SchemaError as e:
            raise ValidationError(f"Invalid connector metadata schema: {e.message}")

        if "inboundEndpoints" not in metadata:
            raise ValidationError(
                f"Artifact at {image_ref} does not contain expected connector metadata structure. "
                f"Found keys: {list(metadata.keys())}"
            )

    @classmethod
    def _get_connector_metadata_schema(cls) -> Dict[str, Any]:
        """Load and cache the official connector metadata JSON schema."""
        if cls._CONNECTOR_SCHEMA_CACHE is not None:
            return cls._CONNECTOR_SCHEMA_CACHE

        current_dir = os.path.dirname(os.path.abspath(__file__))
        schema_path = os.path.join(current_dir, "schemas", "connector_metadata_schema.json")

        if not os.path.exists(schema_path):
            raise ValidationError(f"Connector metadata schema file not found: {schema_path}")

        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                cls._CONNECTOR_SCHEMA_CACHE = json.load(f)
        except (OSError, IOError) as e:
            raise ValidationError(f"Failed to read connector metadata schema file: {e}")
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON in connector metadata schema file: {e}")

        return cls._CONNECTOR_SCHEMA_CACHE

    def _parse_config(
        self,
        data: Dict[str, Any],
        config_key: str,
        resource_name: str,
        default_if_empty: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Parse JSON configuration from a resource payload. Returns None to skip validation."""
        if config_key not in data:
            return default_if_empty or {}

        config_str = data.get(config_key)
        if not config_str:
            return default_if_empty

        try:
            return json.loads(config_str) if isinstance(config_str, str) else config_str
        except (json.JSONDecodeError, TypeError) as e:
            raise ValidationError(f"Invalid {config_key} JSON for {resource_name}: {e}")

    def validate_dataset(self, dataset: Dict[str, Any]) -> None:
        """Validate a dataset configuration against the connector schema."""
        if self.metadata is None:
            logger.info("Skipping dataset validation: no connector metadata available.")
            return

        config = self._parse_config(
            data=dataset,
            config_key=self._CONFIG_KEY_DATASET,
            resource_name="dataset",
        )
        if config is None:
            return

        schema = self._get_schema(self._SCHEMA_KEY_DATASET)
        self._validate(config, schema, "Dataset")
        self._validate_and_apply_destination(config, self._RESOURCE_KIND_DATASETS)

    def validate_datapoint(self, datapoint: Dict[str, Any]) -> None:
        """Validate a datapoint configuration against the connector schema."""
        if self.metadata is None:
            logger.info("Skipping datapoint validation: no connector metadata available.")
            return

        datapoint_name = datapoint.get('name', 'unnamed')

        config = self._parse_config(
            data=datapoint,
            config_key=self._CONFIG_KEY_DATAPOINT,
            resource_name=f"datapoint '{datapoint_name}'",
        )
        if config is None:
            return

        schema = self._get_schema(self._SCHEMA_KEY_DATAPOINT)
        self._validate(config, schema, "Datapoint")
        self._validate_and_apply_destination(config, self._RESOURCE_KIND_DATAPOINTS)

    def validate_event(self, event: Dict[str, Any]) -> None:
        """Validate an event configuration against the connector schema."""
        if self.metadata is None:
            logger.info("Skipping event validation: no connector metadata available.")
            return

        event_name = event.get('name', 'unnamed')

        config = self._parse_config(
            data=event,
            config_key=self._CONFIG_KEY_EVENT,
            resource_name=f"event '{event_name}'",
        )
        if config is None:
            return

        schema = self._get_schema(self._SCHEMA_KEY_EVENT)
        self._validate(config, schema, "Event")
        self._validate_and_apply_destination(event, self._RESOURCE_KIND_EVENTS)

    def validate_event_group(self, event_group: Dict[str, Any]) -> None:
        """Validate an event-group configuration against the connector schema."""
        if self.metadata is None:
            logger.info("Skipping event-group validation: no connector metadata available.")
            return

        event_group_name = event_group.get('name', 'unnamed')

        config = self._parse_config(
            data=event_group,
            config_key=self._CONFIG_KEY_EVENT_GROUP,
            resource_name=f"event-group '{event_group_name}'",
        )
        if config is None:
            return

        schema = self._get_schema(self._SCHEMA_KEY_EVENT_GROUP)
        self._validate(config, schema, "Event-group")

    def validate_stream(self, stream: Dict[str, Any]) -> None:
        """Validate a stream against field constraints.

        Validates:
        - name: required, 1-128 characters
        """
        name = stream.get("name", "")

        if not name:
            raise ValidationError("Stream name is required.")
        if len(name) > 128:
            raise ValidationError(
                f"Stream name must be at most 128 characters. Got {len(name)} characters."
            )

        logger.debug(f"Stream '{name}' field validation passed.")

    def validate_management_group(self, mgmt_group: Dict[str, Any]) -> None:
        """Validate a management group against field constraints.

        Validates:
        - name: required, 1-128 characters
        - defaultTopic: optional, max 128 characters
        - defaultTimeoutInSeconds: optional, non-negative integer
        """
        name = mgmt_group.get("name", "")

        if not name:
            raise ValidationError("Management group name is required.")
        if len(name) > 128:
            raise ValidationError(
                f"Management group name must be at most 128 characters. Got {len(name)} characters."
            )

        default_topic = mgmt_group.get("defaultTopic")
        if default_topic and len(default_topic) > 128:
            raise ValidationError(
                f"Management group defaultTopic must be at most 128 characters. "
                f"Got {len(default_topic)} characters."
            )

        timeout = mgmt_group.get("defaultTimeoutInSeconds")
        if timeout is not None:
            if not isinstance(timeout, int) or timeout < 0:
                raise ValidationError(
                    f"Management group defaultTimeoutInSeconds must be a non-negative integer. "
                    f"Got: {timeout}"
                )

        logger.debug(f"Management group '{name}' field validation passed.")

    def validate_action(self, action: Dict[str, Any]) -> None:
        """Validate a management action against field constraints.

        Validates:
        - name: required, 1-128 characters
        - targetUri: required, 1-512 characters
        - topic: optional, max 128 characters
        - timeoutInSeconds: optional, non-negative integer
        - actionType: optional, must be 'Call', 'Read', or 'Write'
        """
        name = action.get("name", "")
        target_uri = action.get("targetUri", "")

        # Required field: name
        if not name:
            raise ValidationError("Action name is required.")
        if len(name) > 128:
            raise ValidationError(
                f"Action name must be at most 128 characters. Got {len(name)} characters."
            )

        # Required field: targetUri
        if not target_uri:
            raise ValidationError("Action targetUri is required.")
        if len(target_uri) > 512:
            raise ValidationError(
                f"Action targetUri must be at most 512 characters. Got {len(target_uri)} characters."
            )

        # Optional field: topic
        topic = action.get("topic")
        if topic and len(topic) > 128:
            raise ValidationError(
                f"Action topic must be at most 128 characters. Got {len(topic)} characters."
            )

        # Optional field: timeoutInSeconds
        timeout = action.get("timeoutInSeconds")
        if timeout is not None:
            if not isinstance(timeout, int) or timeout < 0:
                raise ValidationError(
                    f"Action timeoutInSeconds must be a non-negative integer. Got: {timeout}"
                )

        # Optional field: actionType
        action_type = action.get("actionType")
        valid_action_types = ["Call", "Read", "Write"]
        if action_type and action_type not in valid_action_types:
            raise ValidationError(
                f"Action actionType must be one of {valid_action_types}. Got: '{action_type}'"
            )

        logger.debug(f"Action '{name}' field validation passed.")

    def _get_schema(self, schema_key: str) -> Dict[str, Any]:
        """Extract a schema from endpoint metadata by key."""
        self._init_schema_paths()
        endpoint = self._get_endpoint_metadata()

        path = self._SCHEMA_PATHS.get(schema_key)
        if path is None:
            raise ValidationError(f"Unknown schema key: '{schema_key}'")

        schema = endpoint
        for i, key in enumerate(path):
            if not isinstance(schema, dict):
                schema = None
                break
            is_last = (i == len(path) - 1)
            schema = schema.get(key) if is_last else schema.get(key, {})

        if schema is None:
            raise ValidationError(
                f"Connector metadata is missing '{schema_key}' for endpoint type '{self.endpoint_type}' "
                f"version '{self.endpoint_version}'."
            )

        return schema

    def _get_endpoint_metadata(self) -> Dict[str, Any]:
        """Find the matching inbound endpoint from metadata."""
        if self._matched_endpoint:
            return self._matched_endpoint

        if self.metadata is None:
            raise ValidationError("Cannot get endpoint metadata: connector metadata is not available.")

        inbound_endpoints = self.metadata.get("inboundEndpoints", [])

        for endpoint in inbound_endpoints:
            endpoint_type = endpoint.get("endpointType")
            if not endpoint_type or endpoint_type.lower() != self.endpoint_type.lower():
                continue

            endpoint_version = endpoint.get("version")

            if endpoint_version is not None and self.endpoint_version is not None:
                if str(endpoint_version) != str(self.endpoint_version):
                    continue

            self._matched_endpoint = endpoint
            return endpoint

        available = [
            f"type={ep.get('endpointType')}, version={ep.get('version')}" for ep in inbound_endpoints
        ]
        raise ValidationError(
            "Connector metadata unavailable for requested endpoint: "
            f"type='{self.endpoint_type}', version='{self.endpoint_version}'. "
            f"Available inbound endpoints: {available or 'none found'}"
        )

    def _validate_and_apply_destination(self, resource: Dict[str, Any], resource_kind: str) -> None:
        """Validate existing destinations against connector metadata.

        If destinations are present, validates that each target is in the
        supported list.  If destinations are absent, leaves them unset so
        that callers (e.g. import fallback) can apply proper defaults."""
        endpoint = self._get_endpoint_metadata()

        if resource_kind == self._RESOURCE_KIND_DATASETS:
            dest_meta = endpoint.get("datasets", {}).get("destinations", {})
        elif resource_kind == self._RESOURCE_KIND_DATAPOINTS:
            dest_meta = endpoint.get("datasets", {}).get("dataPoints", {}).get("destinations", {})
        elif resource_kind == self._RESOURCE_KIND_EVENTS:
            dest_meta = endpoint.get("eventGroups", {}).get("events", {}).get("destinations", {})
        else:
            dest_meta = {}

        if not isinstance(dest_meta, dict):
            return

        supported = dest_meta.get("supportedDestinations")
        default_dest = dest_meta.get("defaultDestination")

        # If no supportedDestinations in metadata, do nothing
        if not supported:
            return

        if not isinstance(supported, list):
            raise ValidationError("supportedDestinations must be an array if specified in connector metadata.")
        if default_dest is not None and default_dest not in supported:
            raise ValidationError(
                f"defaultDestination '{default_dest}' is not listed in supportedDestinations: {supported}"
            )

        # Check if resource already has destinations
        existing_destinations = resource.get("destinations")

        if existing_destinations is not None:
            # Validate existing destinations
            if not isinstance(existing_destinations, list):
                raise ValidationError("destinations must be an array.")
            for dest in existing_destinations:
                target = dest.get("target") if isinstance(dest, dict) else None
                if target and target not in supported:
                    raise ValidationError(
                        f"Destination target '{target}' is not supported. Supported: {supported}"
                    )
            return

        # No destinations specified — leave absent.
        # Downstream logic (import fallback or API defaults) will handle assignment.

    def _validate(self, instance: Dict[str, Any], schema: Dict[str, Any], resource_name: str) -> None:
        import jsonschema

        try:
            jsonschema.validate(instance=instance, schema=schema)
            logger.debug(f"{resource_name} configuration is VALID")
        except jsonschema.ValidationError as e:
            raise ValidationError(f"{resource_name} configuration is invalid: {e.message}")
        except jsonschema.SchemaError as e:
            raise ValidationError(f"{resource_name} schema is invalid: {e.message}")
