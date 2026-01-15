# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import hashlib
import json
import os
import requests
from jsonschema import validate
from typing import Any, Dict, Optional
from knack.log import get_logger
from azure.cli.core.azclierror import ValidationError
from ...util.az_client import AZURE_CLI_CREDENTIAL, get_iotops_mgmt_client

logger = get_logger(__name__)


class ConnectorMetadataValidator:
    """Validates Asset sub-resources against schemas from Connector Template metadata."""

    _METADATA_CACHE = {}
    _CONNECTOR_SCHEMA_CACHE = None
    CONNECTOR_TEMPLATE_MANIFEST_TYPE = "connectortemplate"
    _RESOURCE_TYPE_CONFIG_MEDIA_TYPES = {
        CONNECTOR_TEMPLATE_MANIFEST_TYPE: "application/vnd.microsoft.akri-connector.v1+json",
    }

    def _make_metadata_cache_key(self) -> str:
        """Generate a unique cache key for this endpoint's metadata."""
        subscription_id = (self.cmd.cli_ctx.data or {}).get("subscription_id", "unknown-subscription")
        endpoint_version = self.endpoint_version or "none"
        return ":".join(
            [
                str(subscription_id),
                str(self.resource_group_name or "unknown-rg"),
                str(self.instance_name or "unknown-instance"),
                str(self.endpoint_type or "unknown-endpoint"),
                str(endpoint_version),
            ]
        )

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
    def from_asset(cls, cmd, asset: Dict[str, Any], instance_name: str, instance_resource_group: str):
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
        import os

        current_dir = os.path.dirname(os.path.abspath(__file__))
        schema_file = os.path.join(current_dir, "schemas", "opcua_connector_metadata.json")

        if not os.path.exists(schema_file):
            raise ValidationError(f"OPC UA metadata file not found: {schema_file}")

        try:
            with open(schema_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            raise ValidationError(f"Failed to load local OPC UA metadata: {e}")

    def _get_metadata(self) -> Dict[str, Any]:
        """Retrieve connector metadata from cache, local file (OPC UA), or OCI registry."""
        cache_key = self._make_metadata_cache_key()
        if cache_key in self._METADATA_CACHE:
            return self._METADATA_CACHE[cache_key]

        # Use local bundled schema for OPC UA v1 (type Microsoft.OpcUa, no version)
        et_lower = (self.endpoint_type or "").lower()
        version_empty = (self.endpoint_version is None) or (str(self.endpoint_version).strip() == "")

        if et_lower == "microsoft.opcua" and version_empty:
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
    def fetch_oci_artifact(cls, image_ref: str, cmd=None) -> Dict[str, Any]:  # noqa: C901
        """Fetch a JSON artifact from an OCI registry."""
        logger.info(f"Fetching OCI artifact: {image_ref}")
        if "/" not in image_ref:
            raise ValidationError(f"Invalid OCI reference: {image_ref}")

        registry, remainder = image_ref.split("/", 1)
        if ":" in remainder:
            repository, tag = remainder.split(":", 1)
        else:
            repository = remainder
            tag = "latest"

        base_url = f"https://{registry}/v2/{repository}"
        headers = {
            "Accept": "application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json"
        }

        manifest_url = f"{base_url}/manifests/{tag}"

        # Prefer ACR token flow for ACR, fall back to registry challenge/anonymous for MCR.
        token = None
        if cls._is_acr_registry(registry):
            token = cls._get_acr_access_token(cmd=cmd, registry=registry, repository=repository)

        if not token:
            token = cls._get_auth_token(registry, repository)

        if token:
            headers["Authorization"] = f"Bearer {token}"

        response = requests.get(manifest_url, headers=headers, timeout=30)
        if response.status_code != 200:
            raise ValidationError(f"Failed to fetch manifest for {image_ref}: {response.status_code} {response.text}")

        manifest = response.json()

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

        layers = manifest.get("layers", [])
        if not layers:
            raise ValidationError(f"Manifest for {image_ref} has no layers.")

        target_digest = layers[0].get("digest")
        if not target_digest:
            raise ValidationError(
                f"First layer in manifest for {image_ref} is missing digest. Layer: {layers[0]}"
            )

        blob_url = f"{base_url}/blobs/{target_digest}"

        blob_response = requests.get(blob_url, headers=headers, timeout=30)
        if blob_response.status_code != 200:
            raise ValidationError(f"Failed to fetch blob {target_digest}: {blob_response.status_code}")

        if ":" not in target_digest:
            raise ValidationError(f"Invalid layer digest format: {target_digest}")

        algo, expected_hex = target_digest.split(":", 1)
        if algo.lower() != "sha256":
            raise ValidationError(f"Unsupported digest algorithm '{algo}' for layer {target_digest}")

        computed_hex = hashlib.sha256(blob_response.content).hexdigest()
        if computed_hex != expected_hex:
            raise ValidationError(
                f"Blob digest mismatch: expected {target_digest}, got sha256:{computed_hex}"
            )

        content_type = blob_response.headers.get("Content-Type", "")

        # Handle tar/gzip content or direct JSON
        if "tar" in content_type or blob_response.content[:2] == b"\x1f\x8b":
            import tarfile
            import io

            try:
                tar_bytes = io.BytesIO(blob_response.content)
                with tarfile.open(fileobj=tar_bytes, mode="r:*") as tar:
                    member_names = tar.getnames()

                    metadata_file = None
                    for member in member_names:
                        if member.endswith("connector-metadata.json"):
                            metadata_file = member
                            break

                    if not metadata_file and "connector-metadata.json" in member_names:
                        metadata_file = "connector-metadata.json"

                    if not metadata_file:
                        raise ValidationError(
                            f"connector-metadata.json not found in tar archive. "
                            f"Files: {member_names[:10]}"
                        )

                    extracted = tar.extractfile(metadata_file)
                    if not extracted:
                        raise ValidationError(f"Could not extract {metadata_file} from tar")

                    json_content = extracted.read().decode("utf-8")
                    metadata = json.loads(json_content)

            except (tarfile.TarError, IOError) as e:
                logger.error(f"Failed to extract tar archive: {e}")
                raise ValidationError(f"Failed to extract connector metadata from tar: {e}")
        else:
            try:
                metadata = blob_response.json()
            except json.JSONDecodeError as e:
                logger.error(f"Blob is not valid JSON: {e}")
                raise ValidationError(f"Artifact at {image_ref} is not valid JSON.")

        try:
            schema = cls._get_connector_metadata_schema()
            validate(instance=metadata, schema=schema)
        except Exception as e:
            raise ValidationError(f"Connector metadata does not match schema: {e}")

        if "inboundEndpoints" not in metadata:
            raise ValidationError(
                f"Artifact at {image_ref} does not contain expected connector metadata structure. "
                f"Found keys: {list(metadata.keys())}"
            )

        endpoint_count = len(metadata.get('inboundEndpoints', []))
        logger.info(
            f"Found valid connector metadata with {endpoint_count} inbound endpoints"
        )
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
        except Exception as e:
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
        except Exception as e:
            raise ValidationError(f"Failed to load connector metadata schema: {e}")

        return cls._CONNECTOR_SCHEMA_CACHE

    def validate_dataset(self, dataset: Dict[str, Any]):
        """Validate a dataset configuration against the connector schema."""
        if "datasetConfiguration" in dataset:
            config_str = dataset.get("datasetConfiguration")
            if not config_str:
                return
            try:
                config = json.loads(config_str) if isinstance(config_str, str) else config_str
            except (json.JSONDecodeError, TypeError) as e:
                raise ValidationError(f"Invalid datasetConfiguration JSON: {e}")
        else:
            config = dataset

        schema = self._get_schema("datasetConfigurationSchema")
        self._validate(config, schema, "Dataset")
        self._validate_destination(config, "datasets")

    def validate_datapoint(self, datapoint: Dict[str, Any]):
        """Validate a datapoint configuration against the connector schema."""
        datapoint_name = datapoint.get('name', 'unnamed')

        if "dataPointConfiguration" in datapoint:
            config_str = datapoint.get("dataPointConfiguration")
            if not config_str:
                config = {}
            else:
                try:
                    config = json.loads(config_str) if isinstance(config_str, str) else config_str
                except (json.JSONDecodeError, TypeError) as e:
                    raise ValidationError(
                        f"Invalid dataPointConfiguration JSON for datapoint '{datapoint_name}': {e}"
                    )
        else:
            config = {}

        schema = self._get_schema("dataPointConfigurationSchema")
        self._validate(config, schema, "Datapoint")
        self._validate_destination(config, "datapoints")

    def validate_event(self, event: Dict[str, Any]):
        """Validate an event configuration against the connector schema."""
        logger.debug(f"Validating event: {event}")

        if "eventConfiguration" in event:
            config_str = event.get("eventConfiguration")
            if not config_str:
                return

            try:
                config = json.loads(config_str) if isinstance(config_str, str) else config_str
            except (json.JSONDecodeError, TypeError) as e:
                event_name = event.get('name', 'unnamed')
                logger.error(
                    f"Invalid JSON in eventConfiguration for event '{event_name}': {e}"
                )
                raise ValidationError(
                    f"Invalid eventConfiguration JSON for event '{event_name}': {e}"
                )
        else:
            config = event

        schema = self._get_schema("eventConfigurationSchema")
        self._validate(config, schema, "Event")
        self._validate_destination(config, "events")

    def _get_schema(self, schema_key: str) -> Dict[str, Any]:
        """Extract a schema from the endpoint metadata by key."""
        endpoint = self._get_endpoint_metadata()

        schema = None
        if schema_key == "datasetConfigurationSchema":
            schema = endpoint.get("datasets", {}).get("datasetConfigurationSchema")
        elif schema_key == "dataPointConfigurationSchema":
            schema = endpoint.get("datasets", {}).get("dataPoints", {}).get("dataPointConfigurationSchema")
        elif schema_key == "eventConfigurationSchema":
            schema = endpoint.get("eventGroups", {}).get("events", {}).get("eventConfigurationSchema")
        elif schema_key == "eventGroupConfigurationSchema":
            schema = endpoint.get("eventGroups", {}).get("eventGroupConfigurationSchema")
        elif schema_key == "additionalConfigurationSchema":
            schema = endpoint.get("additionalConfigurationSchema")
        elif schema_key == "actionConfigurationSchema":
            schema = (
                endpoint.get("managementGroups", {})
                .get("managementGroupActions", {})
                .get("actionConfigurationSchema")
            )
        elif schema_key == "managementGroupConfigurationSchema":
            schema = endpoint.get("managementGroups", {}).get("managementGroupConfigurationSchema")

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

    def _validate_destination(self, config: Dict[str, Any], resource_kind: str):
        """Validate and auto-fill destination based on connector metadata."""
        endpoint = self._get_endpoint_metadata()
        if not endpoint:
            return

        if resource_kind == "datasets":
            dest_meta = endpoint.get("datasets", {}).get("destinations", {})
        elif resource_kind == "datapoints":
            dest_meta = endpoint.get("datasets", {}).get("dataPoints", {}).get("destinations", {})
        elif resource_kind == "events":
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
                if "Mqtt" in supported:
                    config["destination"] = "Mqtt"
                    return
                config["destination"] = supported[0]
                return
            return

        if supported and destination_value not in supported:
            raise ValidationError(
                f"Destination '{destination_value}' is not supported. Supported: {supported}"
            )

    def _validate(self, instance: Dict[str, Any], schema: Dict[str, Any], resource_name: str):
        try:
            validate(instance=instance, schema=schema)
            logger.debug(f"{resource_name} configuration is VALID")
        except Exception as e:
            raise ValidationError(f"{resource_name} configuration is invalid: {str(e)}")
