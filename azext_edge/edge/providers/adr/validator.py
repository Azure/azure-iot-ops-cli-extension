# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import hashlib
import io
import json
import jsonschema
import os
import requests
import tarfile
from jsonschema import validate
from typing import Any, Dict, Optional, Tuple
from knack.log import get_logger
from azure.cli.core.azclierror import ValidationError
from ...util.az_client import AZURE_CLI_CREDENTIAL, get_iotops_mgmt_client

logger = get_logger(__name__)


class ConnectorMetadataValidator:
    """Validates Asset sub-resources against schemas from Connector Template metadata."""

    # Cache storage
    _METADATA_CACHE = {}
    _CONNECTOR_SCHEMA_CACHE = None

    # OCI artifact constants
    CONNECTOR_TEMPLATE_MANIFEST_TYPE = "connectortemplate"
    _RESOURCE_TYPE_CONFIG_MEDIA_TYPES = {
        CONNECTOR_TEMPLATE_MANIFEST_TYPE: "application/vnd.microsoft.akri-connector.v1+json",
    }

    # Configuration keys (used in asset/datapoint/event payloads)
    _CONFIG_KEY_DATASET = "datasetConfiguration"
    _CONFIG_KEY_DATAPOINT = "dataPointConfiguration"
    _CONFIG_KEY_EVENT = "eventConfiguration"

    # Schema keys (used to look up schemas in connector metadata)
    _SCHEMA_KEY_DATASET = "datasetConfigurationSchema"
    _SCHEMA_KEY_DATAPOINT = "dataPointConfigurationSchema"
    _SCHEMA_KEY_EVENT = "eventConfigurationSchema"
    _SCHEMA_KEY_EVENT_GROUP = "eventGroupConfigurationSchema"
    _SCHEMA_KEY_ADDITIONAL = "additionalConfigurationSchema"
    _SCHEMA_KEY_ACTION = "actionConfigurationSchema"
    _SCHEMA_KEY_MGMT_GROUP = "managementGroupConfigurationSchema"

    # Resource kind constants (for destination validation)
    _RESOURCE_KIND_DATASETS = "datasets"
    _RESOURCE_KIND_DATAPOINTS = "datapoints"
    _RESOURCE_KIND_EVENTS = "events"

    # Endpoint type constants
    _ENDPOINT_TYPE_OPCUA = "microsoft.opcua"

    # Destination constants
    _DEFAULT_DESTINATION_MQTT = "Mqtt"

    # Error message display limits
    _MAX_TAR_FILES_IN_ERROR = 5  # Limit file list in errors to avoid overwhelming output

    # Schema path mapping: schema_key -> tuple of nested keys to traverse in endpoint metadata
    # Each tuple represents the path to reach the schema in the endpoint dict
    _SCHEMA_PATHS: Dict[str, Tuple[str, ...]] = {}

    @classmethod
    def _init_schema_paths(cls) -> None:
        """Initialize schema paths mapping (called once when class attributes are set)."""
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
        parts = [
            (self.cmd.cli_ctx.data or {}).get("subscription_id") or "unknown-subscription",
            self.resource_group_name or "unknown-rg",
            self.instance_name or "unknown-instance",
            self.endpoint_type or "unknown-endpoint",
            self.endpoint_version or "none",
        ]
        return ":".join(parts)

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
            # namespace_name is in the "name" field (the namespaces resource name)
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
        endpoint_version = endpoint.get("version")  # May be None

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

    def _get_metadata(self) -> Dict[str, Any]:
        """Retrieve connector metadata from cache, local file (OPC UA), or OCI registry."""
        cache_key = self._make_metadata_cache_key()
        if cache_key in self._METADATA_CACHE:
            return self._METADATA_CACHE[cache_key]

        # Use local bundled schema for OPC UA v1 (type Microsoft.OpcUa, no version)
        et_lower = (self.endpoint_type or "").lower()
        version_empty = (self.endpoint_version is None) or (str(self.endpoint_version).strip() == "")

        if et_lower == self._ENDPOINT_TYPE_OPCUA and version_empty:
            metadata = self._load_local_opcua_metadata()
            self._METADATA_CACHE[cache_key] = metadata
            return metadata

        try:
            from ...vendor.clients.iotopsmgmt import MicrosoftIoTOperationsManagementService

            iotops_client: MicrosoftIoTOperationsManagementService = get_iotops_mgmt_client(
                subscription_id=self.cmd.cli_ctx.data.get("subscription_id"),
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
                raise ValidationError(
                    f"No connector template found for endpoint type '{self.endpoint_type}' "
                    f"version '{self.endpoint_version}'."
                )

            connector_metadata_ref = matched_template.get("properties", {}).get("connectorMetadataRef")
            if not connector_metadata_ref:
                raise ValidationError(
                    f"Connector template '{matched_template.get('name')}' is missing connectorMetadataRef."
                )

            logger.info(f"Fetching connector metadata from OCI: {connector_metadata_ref}")
            metadata = self.fetch_oci_artifact(connector_metadata_ref, cmd=self.cmd)
            self._METADATA_CACHE[cache_key] = metadata

            return metadata

        except Exception as e:
            logger.error(f"Failed to fetch connector metadata: {e}")
            raise

    @classmethod
    def _parse_oci_reference(cls, image_ref: str) -> tuple:
        """Parse an OCI image reference into its components.

        Args:
            image_ref: OCI reference string (e.g., 'registry.io/repo/name:tag')

        Returns:
            Tuple of (registry, repository, tag)
        """
        if "/" not in image_ref:
            raise ValidationError(f"Invalid OCI reference: {image_ref}")

        registry, remainder = image_ref.split("/", 1)
        if ":" in remainder:
            repository, tag = remainder.split(":", 1)
        else:
            repository = remainder
            tag = "latest"

        return registry, repository, tag

    @classmethod
    def _get_oci_auth_headers(cls, registry: str, repository: str, cmd=None) -> Dict[str, str]:
        """Build HTTP headers with authentication for OCI registry requests.

        Args:
            registry: Registry hostname
            repository: Repository path
            cmd: Azure CLI command context (optional, for ACR auth)

        Returns:
            Dict of HTTP headers including Authorization if token obtained
        """
        headers = {
            "Accept": "application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json"
        }

        # Prefer ACR token flow for ACR, fall back to registry challenge/anonymous for MCR
        token = None
        if cls._is_acr_registry(registry):
            token = cls._get_acr_access_token(cmd=cmd, registry=registry, repository=repository)

        if not token:
            token = cls._get_auth_token(registry, repository)

        if token:
            headers["Authorization"] = f"Bearer {token}"

        return headers

    @classmethod
    def _fetch_oci_manifest(cls, base_url: str, tag: str, headers: Dict[str, str], image_ref: str) -> Dict[str, Any]:
        """Fetch and validate the OCI manifest.

        Args:
            base_url: Base OCI registry URL
            tag: Image tag
            headers: HTTP headers with auth
            image_ref: Original image reference (for error messages)

        Returns:
            Parsed manifest dict
        """
        manifest_url = f"{base_url}/manifests/{tag}"
        response = requests.get(manifest_url, headers=headers, timeout=30)

        if response.status_code != 200:
            raise ValidationError(f"Failed to fetch manifest for {image_ref}: {response.status_code} {response.text}")

        manifest = response.json()

        # Validate config media type
        expected_config_media_type = cls._get_expected_config_media_type(cls.CONNECTOR_TEMPLATE_MANIFEST_TYPE)
        manifest_config = manifest.get("config") or {}
        actual_config_media_type = manifest_config.get("mediaType")

        if expected_config_media_type:
            if not actual_config_media_type:
                raise ValidationError(
                    f"Missing artifact config media type; expected '{expected_config_media_type}'."
                )
            if actual_config_media_type != expected_config_media_type:
                raise ValidationError(
                    f"Artifact config media type '{actual_config_media_type}' does not match expected "
                    f"'{expected_config_media_type}'."
                )
        elif not actual_config_media_type:
            raise ValidationError("Missing artifact config media type.")

        return manifest

    @classmethod
    def _fetch_and_verify_blob(
        cls, base_url: str, digest: str, headers: Dict[str, str], image_ref: str
    ) -> Tuple[bytes, str]:
        """Fetch a blob from OCI registry and verify its digest.

        Args:
            base_url: Base OCI registry URL
            digest: Expected blob digest (e.g., 'sha256:abc123...')
            headers: HTTP headers with auth
            image_ref: Original image reference (for error messages)

        Returns:
            Tuple of (blob content as bytes, content-type string)
        """
        if ":" not in digest:
            raise ValidationError(f"Invalid layer digest format: {digest}")

        algo, expected_hex = digest.split(":", 1)
        if algo.lower() != "sha256":
            raise ValidationError(f"Unsupported digest algorithm '{algo}' for layer {digest}")

        blob_url = f"{base_url}/blobs/{digest}"
        blob_response = requests.get(blob_url, headers=headers, timeout=30)

        if blob_response.status_code != 200:
            raise ValidationError(f"Failed to fetch blob {digest}: {blob_response.status_code}")

        # Verify digest
        computed_hex = hashlib.sha256(blob_response.content).hexdigest()
        if computed_hex != expected_hex:
            raise ValidationError(
                f"Blob digest mismatch: expected {digest}, got sha256:{computed_hex}"
            )

        return blob_response.content, blob_response.headers.get("Content-Type", "")

    @classmethod
    def _extract_metadata_from_blob(cls, content: bytes, content_type: str, image_ref: str) -> Dict[str, Any]:
        """Extract connector metadata from blob content.

        Handles both tar/gzip archives and direct JSON content.

        Args:
            content: Raw blob bytes
            content_type: HTTP Content-Type header value
            image_ref: Original image reference (for error messages)

        Returns:
            Parsed metadata dict
        """
        # Check for tar/gzip content
        is_tar = "tar" in content_type or content[:2] == b"\x1f\x8b"

        if is_tar:
            try:
                tar_bytes = io.BytesIO(content)
                with tarfile.open(fileobj=tar_bytes, mode="r:*") as tar:
                    member_names = tar.getnames()

                    # Find connector-metadata.json in archive
                    metadata_file = None
                    for member in member_names:
                        if member.endswith("connector-metadata.json"):
                            metadata_file = member
                            break

                    if not metadata_file and "connector-metadata.json" in member_names:
                        metadata_file = "connector-metadata.json"

                    if not metadata_file:
                        # Show limited file list to help debugging without overwhelming output
                        sample_files = member_names[:cls._MAX_TAR_FILES_IN_ERROR]
                        total_files = len(member_names)
                        file_hint = f"Found {total_files} files, showing first {len(sample_files)}: {sample_files}"
                        raise ValidationError(
                            f"connector-metadata.json not found in tar archive. {file_hint}"
                        )

                    extracted = tar.extractfile(metadata_file)
                    if not extracted:
                        raise ValidationError(f"Could not extract {metadata_file} from tar")

                    json_content = extracted.read().decode("utf-8")
                    return json.loads(json_content)

            except (tarfile.TarError, IOError) as e:
                raise ValidationError(f"Failed to extract connector metadata from tar: {e}")
        else:
            try:
                return json.loads(content.decode("utf-8"))
            except json.JSONDecodeError as e:
                raise ValidationError(f"Artifact at {image_ref} is not valid JSON: {e}")

    @classmethod
    def _validate_connector_metadata(cls, metadata: Dict[str, Any], image_ref: str) -> None:
        """Validate connector metadata against schema and structure requirements.

        Args:
            metadata: Parsed metadata dict
            image_ref: Original image reference (for error messages)
        """
        try:
            schema = cls._get_connector_metadata_schema()
            validate(instance=metadata, schema=schema)
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
    def fetch_oci_artifact(cls, image_ref: str, cmd=None) -> Dict[str, Any]:
        """Fetch a JSON artifact from an OCI registry.

        Args:
            image_ref: OCI image reference (e.g., 'mcr.microsoft.com/repo:tag')
            cmd: Azure CLI command context (optional, for ACR authentication)

        Returns:
            Parsed connector metadata dict
        """
        logger.info(f"Fetching OCI artifact: {image_ref}")

        # Parse reference
        registry, repository, tag = cls._parse_oci_reference(image_ref)
        base_url = f"https://{registry}/v2/{repository}"

        # Get auth headers
        headers = cls._get_oci_auth_headers(registry, repository, cmd)

        # Fetch manifest
        manifest = cls._fetch_oci_manifest(base_url, tag, headers, image_ref)

        # Get first layer digest
        layers = manifest.get("layers", [])
        if not layers:
            raise ValidationError(f"Manifest for {image_ref} has no layers.")

        target_digest = layers[0].get("digest")
        if not target_digest:
            raise ValidationError(
                f"First layer in manifest for {image_ref} is missing digest. Layer: {layers[0]}"
            )

        # Fetch and verify blob
        content, content_type = cls._fetch_and_verify_blob(base_url, target_digest, headers, image_ref)

        # Extract metadata from blob
        metadata = cls._extract_metadata_from_blob(content, content_type, image_ref)

        # Validate metadata
        cls._validate_connector_metadata(metadata, image_ref)

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

    @staticmethod
    def _get_auth_token(registry: str, repository: str) -> Optional[str]:
        """Get an anonymous auth token for public registries (MCR/Docker Hub)."""
        auth_url = f"https://{registry}/v2/"
        try:
            resp = requests.get(auth_url, timeout=30)

            if resp.status_code == 401 and "Www-Authenticate" in resp.headers:
                auth_header = resp.headers["Www-Authenticate"]
                parts = {}
                for part in auth_header.replace("Bearer ", "").split(","):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        parts[k.strip()] = v.strip().strip('"')

                if "realm" in parts:
                    token_params = {"service": parts.get("service")}
                    if "scope" not in parts:
                        token_params["scope"] = f"repository:{repository}:pull"
                    else:
                        token_params["scope"] = parts.get("scope")

                    token_resp = requests.get(parts["realm"], params=token_params, timeout=30)

                    if token_resp.status_code == 200:
                        token = token_resp.json().get("token")
                        logger.info(
                            f"Successfully obtained anonymous auth token (length: {len(token) if token else 0})"
                        )
                        return token
                    else:
                        logger.warning(f"Token request failed: {token_resp.status_code} {token_resp.text}")
        except requests.RequestException as e:
            logger.warning(f"Failed to obtain auth token: {e}")
        return None

    @staticmethod
    def _is_acr_registry(registry: str) -> bool:
        return registry.endswith(".azurecr.io")

    @staticmethod
    def _get_acr_access_token(cmd, registry: str, repository: str) -> Optional[str]:
        """Acquire an ACR access token using Azure CLI credentials."""

        if cmd is None:
            logger.warning("ACR access token requested without command context; skipping ACR auth.")
            return None

        try:
            arm_token = AZURE_CLI_CREDENTIAL.get_token("https://management.azure.com/.default").token
        except Exception as ex:  # pragma: no cover - credential failures
            logger.warning(f"Failed to obtain ARM token for ACR: {ex}")
            return None

        tenant_id = (cmd.cli_ctx.data or {}).get("tenant_id")
        if not tenant_id:
            logger.warning("Tenant ID not found in CLI context; cannot acquire ACR token.")
            return None

        exchange_url = f"https://{registry}/oauth2/exchange"
        exchange_payload = {
            "grant_type": "access_token",
            "service": registry,
            "tenant": tenant_id,
            "access_token": arm_token,
        }

        try:
            exchange_resp = requests.post(exchange_url, data=exchange_payload, timeout=30)
        except Exception as ex:  # pragma: no cover - network errors
            logger.warning(f"ACR exchange request failed: {ex}")
            return None

        if exchange_resp.status_code != 200:
            logger.warning(
                f"ACR exchange failed ({exchange_resp.status_code}): {exchange_resp.text[:200]}"
            )
            return None

        refresh_token = exchange_resp.json().get("refresh_token")
        if not refresh_token:
            logger.warning("ACR exchange response missing refresh_token")
            return None

        token_url = f"https://{registry}/oauth2/token"
        token_payload = {
            "grant_type": "refresh_token",
            "service": registry,
            "scope": f"repository:{repository}:pull",
            "refresh_token": refresh_token,
        }

        try:
            token_resp = requests.post(token_url, data=token_payload, timeout=30)
        except Exception as ex:  # pragma: no cover - network errors
            logger.warning(f"ACR token request failed: {ex}")
            return None

        if token_resp.status_code != 200:
            logger.warning(f"ACR token fetch failed ({token_resp.status_code}): {token_resp.text[:200]}")
            return None

        return token_resp.json().get("access_token")

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
        """Parse configuration from a resource payload.

        Args:
            data: The resource payload (dataset, datapoint, or event dict).
            config_key: The key to look for (e.g., 'datasetConfiguration').
            resource_name: Human-readable name for error messages (e.g., "datapoint 'temp'").
            default_if_empty: Value to return if config_key exists but is empty/falsy.
                              If None, returns None (signals caller to skip validation).

        Returns:
            Parsed config dict, default_if_empty, or None to signal early return.
        """
        if config_key not in data:
            # No config key present - use the data itself or default
            return default_if_empty if default_if_empty is not None else data

        config_str = data.get(config_key)
        if not config_str:
            # Config key present but empty/falsy
            return default_if_empty

        try:
            return json.loads(config_str) if isinstance(config_str, str) else config_str
        except (json.JSONDecodeError, TypeError) as e:
            raise ValidationError(f"Invalid {config_key} JSON for {resource_name}: {e}")

    def validate_dataset(self, dataset: Dict[str, Any]) -> None:
        """Validate a dataset configuration against the connector schema."""
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
        self._validate_and_apply_destination(config, self._RESOURCE_KIND_EVENTS)

    def _get_schema(self, schema_key: str) -> Dict[str, Any]:
        """Extract a schema from the endpoint metadata by key."""
        self._init_schema_paths()
        endpoint = self._get_endpoint_metadata()

        path = self._SCHEMA_PATHS.get(schema_key)
        if path is None:
            raise ValidationError(f"Unknown schema key: '{schema_key}'")

        # Traverse nested path; empty dict {} is a valid JSON schema
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

    def _validate_and_apply_destination(self, config: Dict[str, Any], resource_kind: str) -> None:
        """Validate and auto-fill destination based on connector metadata.

        Note: This method modifies `config` in-place by setting the 'destination' key
        if not already present and a default can be determined.
        """
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

        if supported is not None and not isinstance(supported, list):
            raise ValidationError("supportedDestinations must be an array if specified in connector metadata.")
        if supported and default_dest is not None and default_dest not in supported:
            raise ValidationError(
                f"defaultDestination '{default_dest}' is not listed in supportedDestinations: {supported}"
            )

        destination_value = config.get("destination")

        if destination_value is None:
            if default_dest is not None:
                config["destination"] = default_dest
                return
            if supported:
                if len(supported) == 1:
                    config["destination"] = supported[0]
                    return
                if self._DEFAULT_DESTINATION_MQTT in supported:
                    config["destination"] = self._DEFAULT_DESTINATION_MQTT
                    return
                config["destination"] = supported[0]
                return
            return

        if supported and destination_value not in supported:
            raise ValidationError(
                f"Destination '{destination_value}' is not supported. Supported: {supported}"
            )

    def _validate(self, instance: Dict[str, Any], schema: Dict[str, Any], resource_name: str) -> None:
        try:
            validate(instance=instance, schema=schema)
            logger.debug(f"{resource_name} configuration is VALID")
        except jsonschema.ValidationError as e:
            raise ValidationError(f"{resource_name} configuration is invalid: {e.message}")
        except jsonschema.SchemaError as e:
            raise ValidationError(f"{resource_name} schema is invalid: {e.message}")
