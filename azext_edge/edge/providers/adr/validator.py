# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import requests
from typing import Any, Dict, Optional
from knack.log import get_logger
from azure.cli.core.azclierror import ValidationError
from ...util.az_client import get_iotops_mgmt_client

logger = get_logger(__name__)


class ConnectorMetadataValidator:
    """
    Validates Asset sub-resources (datasets, events, etc.) against schemas defined
    in the associated Connector Template's metadata (stored as OCI artifacts).
    """

    _METADATA_CACHE = {}

    def __init__(
        self,
        cmd,
        resource_group_name: str,
        instance_name: str,
        endpoint_type: str,
        endpoint_version: Optional[str] = None,
    ):
        """
        Args:
            cmd: The Azure CLI command context
            resource_group_name: Resource group containing the IoT Operations instance
            instance_name: Name of the IoT Operations instance
            endpoint_type: The endpoint type (e.g., "Microsoft.Http", "Microsoft.Onvif")
            endpoint_version: Optional version of the endpoint (e.g., "1.0")
        """
        self.cmd = cmd
        self.resource_group_name = resource_group_name
        self.instance_name = instance_name
        self.endpoint_type = endpoint_type
        self.endpoint_version = endpoint_version
        self.metadata = self._get_metadata()

    @classmethod
    def from_asset(cls, cmd, asset: Dict[str, Any], instance_name: str):
        """
        Factory method to create validator from an asset by looking up its device and endpoint.

        Args:
            cmd: The Azure CLI command context
            asset: The asset resource dictionary
            instance_name: The IoT Operations instance name

        Returns:
            ConnectorMetadataValidator instance
        """
        # Extract resource group and instance from asset's extended location or ID
        from ...util.az_client import parse_resource_id

        asset_id_str = asset.get("id", "")
        if not asset_id_str:
            raise ValidationError("Asset does not have an ID.")

        asset_id = parse_resource_id(asset_id_str)
        if not asset_id:
            raise ValidationError(f"Invalid asset ID: {asset_id_str}")

        resource_group_name = asset_id.resource_group_name

        # Parse namespace from asset ID path
        # Asset ID format: /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.DeviceRegistry/namespaces/{namespace}/assets/{asset}
        # The namespace is in the parent path of the asset
        namespace_name = None
        if asset_id.resource_type == "Microsoft.DeviceRegistry/namespaces/assets":
            # namespace_name is in the child_name_1 field
            namespace_name = asset_id.child_name_1
        
        if not namespace_name:
            raise ValidationError(
                f"Could not extract namespace from asset ID: {asset_id_str}. "
                f"Expected format: .../namespaces/{{namespace}}/assets/{{asset}}"
            )
        
        logger.debug(f"Extracted namespace '{namespace_name}' from asset ID")

        # Get device reference
        device_ref = asset.get("deviceRef") or asset.get("properties", {}).get("deviceRef", {})
        device_name = device_ref.get("deviceName")
        endpoint_name = device_ref.get("endpointName")

        if not device_name or not endpoint_name:
            raise ValidationError(
                "Asset must reference a device and endpoint via deviceRef.deviceName and deviceRef.endpointName"
            )

        # Fetch the device to get endpoint type/version
        from ...vendor.clients.iotopsmgmt import MicrosoftIoTOperationsManagementService

        iotops_client: MicrosoftIoTOperationsManagementService = get_iotops_mgmt_client(
            cmd.cli_ctx.cloud.endpoints.resource_manager,
            asset_id.subscription_id,
        )

        device = iotops_client.device.get(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            device_name=device_name,
        )

        # Get endpoint from device
        endpoints_inbound = device.get("properties", {}).get("endpoints", {}).get("inbound", {})
        endpoint = endpoints_inbound.get(endpoint_name)

        if not endpoint:
            raise ValidationError(f"Device '{device_name}' does not have inbound endpoint '{endpoint_name}'.")

        endpoint_type = endpoint.get("endpointType")
        endpoint_version = endpoint.get("version")  # May be None

        if not endpoint_type:
            raise ValidationError(f"Endpoint '{endpoint_name}' does not have endpointType specified.")

        logger.debug(f"Using instance name '{instance_name}' for connector metadata lookup")

        return cls(
            cmd=cmd,
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            endpoint_type=endpoint_type,
            endpoint_version=endpoint_version,
        )

    def _load_local_opcua_metadata(self) -> Dict[str, Any]:
        """
        Loads OPC UA connector metadata from local bundled JSON file.

        Returns:
            Dict containing the connector metadata JSON, or empty dict if load fails
        """
        try:
            import os
            # Get the directory where this validator.py file is located
            current_dir = os.path.dirname(os.path.abspath(__file__))
            schema_file = os.path.join(current_dir, "schemas", "opcua_connector_metadata.json")
            
            logger.debug(f"Loading OPC UA metadata from: {schema_file}")
            
            if not os.path.exists(schema_file):
                logger.error(f"OPC UA metadata file not found: {schema_file}")
                return {}
            
            with open(schema_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            logger.info(f"Successfully loaded local OPC UA metadata (version {metadata.get('version', 'unknown')})")
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to load local OPC UA metadata: {e}")
            return {}

    def _get_metadata(self) -> Dict[str, Any]:
        """
        Retrieves the metadata JSON for the connector by:
        1. For OPC UA endpoints, loads from local bundled schema file
        2. For other endpoints, fetches from OCI registry:
           - Finding the matching Connector Template based on endpoint type/version
           - Extracting the connectorMetadataRef (OCI URI)
           - Fetching the OCI artifact containing the JSON metadata
        3. Caching the result for future use

        Returns:
            Dict containing the connector metadata JSON
        """
        # Check cache first
        cache_key = f"{self.endpoint_type}:{self.endpoint_version or 'none'}"
        if cache_key in self._METADATA_CACHE:
            logger.debug(f"Using cached metadata for {cache_key}")
            return self._METADATA_CACHE[cache_key]

        # Use local bundled schema for OPC UA
        if self.endpoint_type in ["Microsoft.OpcUa", "Microsoft.DeviceRegistry.OpcUa", "opcua"]:
            logger.info(f"Loading local OPC UA metadata for endpoint type '{self.endpoint_type}'")
            metadata = self._load_local_opcua_metadata()
            if metadata:
                self._METADATA_CACHE[cache_key] = metadata
                return metadata
            else:
                logger.warning("Failed to load local OPC UA metadata, will attempt OCI fetch")
                # Fall through to OCI fetch as fallback

        try:
            # Step 1: Get IoT Operations management client
            from ...vendor.clients.iotopsmgmt import MicrosoftIoTOperationsManagementService

            logger.debug("Creating IoT Operations management client")
            iotops_client: MicrosoftIoTOperationsManagementService = get_iotops_mgmt_client(
                self.cmd.cli_ctx.cloud.endpoints.resource_manager,
                self.cmd.cli_ctx.data.get("subscription_id"),
            )

            # Step 2: List all connector templates in the instance
            logger.debug(
                f"Listing connector templates for instance '{self.instance_name}' "
                f"in resource group '{self.resource_group_name}'"
            )
            connector_templates = list(
                iotops_client.akri_connector_template.list_by_instance_resource(
                    resource_group_name=self.resource_group_name, instance_name=self.instance_name
                )
            )

            logger.debug(f"Found {len(connector_templates)} connector templates")

            # Step 3: Find matching connector template
            matched_template = None
            for template in connector_templates:
                template_name = template.get("name")
                device_endpoint_types = template.get("properties", {}).get("deviceInboundEndpointTypes", [])
                logger.debug(f"Checking template '{template_name}' with {len(device_endpoint_types)} endpoint types")

                for endpoint_type_info in device_endpoint_types:
                    et = endpoint_type_info.get("endpointType")
                    ev = endpoint_type_info.get("version")
                    logger.debug(f"  Endpoint: type='{et}', version='{ev}'")

                    # Match endpoint type
                    if et != self.endpoint_type:
                        logger.debug(f"    Type mismatch: '{et}' != '{self.endpoint_type}'")
                        continue

                    # Match version (if both specified, they must match; if either is None, match)
                    if self.endpoint_version and ev and self.endpoint_version != ev:
                        logger.debug(f"    Version mismatch: '{self.endpoint_version}' != '{ev}'")
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
                logger.warning(
                    f"No connector template found for endpoint type '{self.endpoint_type}' "
                    f"version '{self.endpoint_version}'. Validation will be skipped."
                )
                return {}

            # Step 4: Extract connectorMetadataRef
            connector_metadata_ref = matched_template.get("properties", {}).get("connectorMetadataRef")
            logger.debug(f"Connector metadata reference: {connector_metadata_ref}")

            if not connector_metadata_ref:
                logger.warning(
                    f"Connector template '{matched_template.get('name')}' does not have connectorMetadataRef. "
                    "Validation will be skipped."
                )
                return {}

            logger.info(f"Fetching connector metadata from OCI: {connector_metadata_ref}")

            # Step 5: Fetch OCI artifact
            metadata = self.fetch_oci_artifact(connector_metadata_ref)

            # Step 6: Cache the result
            self._METADATA_CACHE[cache_key] = metadata

            return metadata

        except Exception as e:
            logger.warning(f"Failed to fetch connector metadata: {e}. Validation will be skipped.")
            return {}

    @staticmethod
    def fetch_oci_artifact(image_ref: str) -> Dict[str, Any]:  # noqa: C901
        """
        Fetches a JSON artifact from an OCI registry without requiring the 'oras' CLI.

        Args:
            image_ref: The OCI image reference (e.g., mcr.microsoft.com/repo:tag)

        Returns:
            The parsed JSON content of the artifact.
        """
        logger.info(f"Fetching OCI artifact: {image_ref}")
        # 1. Parse the reference
        # Format: registry/repo:tag
        if "/" not in image_ref:
            raise ValidationError(f"Invalid OCI reference: {image_ref}")

        registry, remainder = image_ref.split("/", 1)
        if ":" in remainder:
            repository, tag = remainder.split(":", 1)
        else:
            repository = remainder
            tag = "latest"

        logger.debug(f"Parsed OCI reference - Registry: {registry}, Repository: {repository}, Tag: {tag}")

        # Handle mcr.microsoft.com specific logic if needed, or generic OCI
        # MCR redirects to data endpoints, so standard requests usually work if we follow redirects.

        base_url = f"https://{registry}/v2/{repository}"
        headers = {
            "Accept": "application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json"
        }

        # 2. Get Manifest
        manifest_url = f"{base_url}/manifests/{tag}"
        logger.debug(f"Fetching manifest from {manifest_url}")

        # Note: For private registries, we'd need authentication (Bearer token).
        # MCR public images usually allow anonymous pull but might require a token handshake.
        # For simplicity in this draft, we'll assume public access or implement a basic token flow.

        token = ConnectorMetadataValidator._get_auth_token(registry, repository)
        if token:
            logger.debug(f"Using Bearer token for authentication (token length: {len(token)})")
            headers["Authorization"] = f"Bearer {token}"
        else:
            logger.debug("No authentication token obtained, attempting anonymous access")

        logger.debug(f"Fetching manifest with headers: {list(headers.keys())}")
        response = requests.get(manifest_url, headers=headers)
        logger.debug(f"Manifest fetch response: HTTP {response.status_code}")
        if response.status_code != 200:
            raise ValidationError(f"Failed to fetch manifest for {image_ref}: {response.status_code} {response.text}")

        manifest = response.json()
        logger.debug(f"Manifest structure: {json.dumps(manifest, indent=2)}")

        # 3. Find the connector-metadata.json layer
        # The connector metadata is stored as a file named "connector-metadata.json" in the OCI artifact
        target_digest = None

        layers = manifest.get("layers", [])
        logger.debug(f"Found {len(layers)} layers in manifest")

        # Strategy 1: Look for layer with title annotation containing "connector-metadata.json"
        for idx, layer in enumerate(layers):
            media_type = layer.get("mediaType", "")
            annotations = layer.get("annotations", {})
            title = annotations.get("org.opencontainers.image.title", "")
            logger.debug(f"Layer {idx}: mediaType={media_type}, title={title}, digest={layer.get('digest')}")

            # Match if title ends with connector-metadata.json
            # (handles paths like "azure_iot_operations_rest_connector/connector-metadata.json")
            if title.endswith("connector-metadata.json"):
                target_digest = layer["digest"]
                logger.info(f"Found connector-metadata.json layer: {target_digest}")
                break

        # Strategy 2: If not found by title, look for application/json media type
        if not target_digest:
            logger.debug("connector-metadata.json not found by title, trying by media type")
            for layer in layers:
                media_type = layer.get("mediaType", "")
                if "json" in media_type.lower():
                    target_digest = layer["digest"]
                    logger.info(f"Found JSON layer by media type: {target_digest}")
                    break

        # Strategy 3: Try the first layer as fallback
        if not target_digest and len(layers) > 0:
            target_digest = layers[0]["digest"]
            logger.warning(f"Using first layer as fallback: {target_digest}")

        if not target_digest:
            raise ValidationError(
                f"Could not find connector-metadata.json layer in {image_ref}. "
                f"Manifest has {len(layers)} layers but none match expected structure."
            )

        # 4. Fetch the Blob
        blob_url = f"{base_url}/blobs/{target_digest}"
        logger.debug(f"Fetching blob from {blob_url}")

        blob_response = requests.get(blob_url, headers=headers)
        if blob_response.status_code != 200:
            raise ValidationError(f"Failed to fetch blob {target_digest}: {blob_response.status_code}")

        # Check if the blob is a tar file (common for OCI artifacts)
        content_type = blob_response.headers.get("Content-Type", "")
        logger.debug(f"Blob content-type: {content_type}, size: {len(blob_response.content)} bytes")

        # If it's a tar file, extract the connector-metadata.json from it
        if "tar" in content_type or blob_response.content[:2] == b"\x1f\x8b":  # Check for gzip magic number too
            logger.debug("Blob appears to be a tar archive, extracting connector-metadata.json")
            import tarfile
            import io

            try:
                # Create tar file object from bytes
                tar_bytes = io.BytesIO(blob_response.content)
                with tarfile.open(fileobj=tar_bytes, mode="r:*") as tar:
                    # List all files in tar
                    member_names = tar.getnames()
                    logger.debug(f"Tar contains {len(member_names)} files: {member_names[:10]}")  # Show first 10

                    # Find connector-metadata.json file (may be in root or subdirectory)
                    metadata_file = None
                    for member in member_names:
                        if member.endswith("connector-metadata.json"):
                            metadata_file = member
                            logger.info(f"Found connector-metadata.json in tar: {metadata_file}")
                            break

                    # If not found with path, try exact match (ONVIF case)
                    if not metadata_file and "connector-metadata.json" in member_names:
                        metadata_file = "connector-metadata.json"
                        logger.info("Found connector-metadata.json in tar root")

                    if not metadata_file:
                        raise ValidationError(
                            f"connector-metadata.json not found in tar archive. "
                            f"Files: {member_names[:10]}"
                        )

                    # Extract and parse the JSON file
                    extracted = tar.extractfile(metadata_file)
                    if not extracted:
                        raise ValidationError(f"Could not extract {metadata_file} from tar")

                    json_content = extracted.read().decode("utf-8")
                    metadata = json.loads(json_content)
                    logger.debug(f"Successfully extracted and parsed JSON, keys: {list(metadata.keys())}")

            except (tarfile.TarError, IOError) as e:
                logger.error(f"Failed to extract tar archive: {e}")
                raise ValidationError(f"Failed to extract connector metadata from tar: {e}")
        else:
            # Try to parse as direct JSON
            try:
                metadata = blob_response.json()
                logger.debug(f"Successfully parsed blob as JSON, keys: {list(metadata.keys())}")
            except json.JSONDecodeError as e:
                logger.error(f"Blob is not valid JSON: {e}")
                logger.debug(f"Blob content preview: {blob_response.text[:500]}")
                raise ValidationError(f"Artifact at {image_ref} is not valid JSON.")

        # Validate the metadata structure
        if "inboundEndpoints" in metadata:
            endpoint_count = len(metadata.get('inboundEndpoints', []))
            logger.info(
                f"Found valid connector metadata with {endpoint_count} inbound endpoints"
            )
            return metadata
        else:
            logger.warning(f"Metadata does not contain 'inboundEndpoints', keys found: {list(metadata.keys())}")
            raise ValidationError(
                f"Artifact at {image_ref} does not contain expected connector metadata structure. "
                f"Found keys: {list(metadata.keys())}"
            )

    @staticmethod
    def _get_auth_token(registry: str, repository: str) -> Optional[str]:
        """
        Helper to get an anonymous auth token for the registry if required (common for MCR/Docker Hub).

        This implements the Docker Registry v2 authentication flow:
        1. Attempt unauthenticated access to /v2/ endpoint
        2. If 401 with WWW-Authenticate header is returned, parse the authentication challenge
        3. Request a token from the auth realm with the required service and scope
        4. Return the token for use in subsequent requests

        For public registries like MCR, this allows anonymous pull access without credentials.
        """
        auth_url = f"https://{registry}/v2/"
        logger.debug(f"Attempting to obtain auth token for registry: {registry}, repository: {repository}")
        try:
            # Ping v2 endpoint to get Www-Authenticate header
            logger.debug(f"Pinging registry v2 endpoint: {auth_url}")
            resp = requests.get(auth_url)
            logger.debug(f"Registry v2 response: HTTP {resp.status_code}")

            if resp.status_code == 401 and "Www-Authenticate" in resp.headers:
                auth_header = resp.headers["Www-Authenticate"]
                logger.debug(f"Received WWW-Authenticate header: {auth_header}")

                # Format: Bearer realm="...",service="...",scope="..."
                # Simple parser
                parts = {}
                for part in auth_header.replace("Bearer ", "").split(","):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        parts[k.strip()] = v.strip().strip('"')

                logger.debug(f"Parsed auth challenge: realm={parts.get('realm')}, service={parts.get('service')}")

                if "realm" in parts:
                    token_params = {"service": parts.get("service")}
                    if "scope" not in parts:
                        token_params["scope"] = f"repository:{repository}:pull"
                    else:
                        token_params["scope"] = parts.get("scope")

                    logger.debug(f"Requesting token from {parts['realm']} with params: {token_params}")
                    token_resp = requests.get(parts["realm"], params=token_params)
                    logger.debug(f"Token response: HTTP {token_resp.status_code}")

                    if token_resp.status_code == 200:
                        token = token_resp.json().get("token")
                        logger.info(
                            f"Successfully obtained anonymous auth token (length: {len(token) if token else 0})"
                        )
                        return token
                    else:
                        logger.warning(f"Token request failed: {token_resp.status_code} {token_resp.text}")
            else:
                logger.debug(f"No authentication required (HTTP {resp.status_code})")
        except Exception as e:
            logger.warning(f"Failed to obtain auth token: {e}")
        return None

    def validate_dataset(self, dataset: Dict[str, Any]):
        """Validate a dataset object or its configuration.

        Args:
            dataset: Can be either:
                - A full dataset object with 'datasetConfiguration' as JSON string
                - A parsed configuration dictionary (for backward compatibility)
        """
        logger.debug(f"Validating dataset: {dataset}")

        # Check if this is a full dataset object or just the configuration
        if "datasetConfiguration" in dataset:
            # Full dataset object - extract and parse configuration
            config_str = dataset.get("datasetConfiguration")
            if not config_str:
                logger.debug("No datasetConfiguration found, skipping validation")
                return

            try:
                config = json.loads(config_str) if isinstance(config_str, str) else config_str
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"Invalid JSON in datasetConfiguration: {e}")
                raise ValidationError(f"Invalid datasetConfiguration JSON: {e}")
        else:
            # Assume it's already a parsed configuration dict (backward compatibility)
            config = dataset

        schema = self._get_schema("datasetConfigurationSchema")
        if schema:
            logger.debug("Found dataset schema, performing validation")
            self._validate(config, schema, "Dataset")
        else:
            logger.warning(f"No dataset schema found for endpoint type '{self.endpoint_type}' - skipping validation")

    def validate_datapoint(self, datapoint: Dict[str, Any]):
        """Validate a datapoint object or its configuration.

        Args:
            datapoint: Can be either:
                - A full datapoint object with 'dataPointConfiguration' as JSON string
                - A parsed configuration dictionary (for backward compatibility)
        """
        logger.debug(f"Validating datapoint: {datapoint}")

        # Check if this is a full datapoint object or just the configuration
        if "dataPointConfiguration" in datapoint:
            # Full datapoint object - extract and parse configuration
            config_str = datapoint.get("dataPointConfiguration")
            if not config_str:
                logger.debug("No dataPointConfiguration found, skipping validation")
                return

            try:
                config = json.loads(config_str) if isinstance(config_str, str) else config_str
            except (json.JSONDecodeError, TypeError) as e:
                datapoint_name = datapoint.get('name', 'unnamed')
                logger.error(
                    f"Invalid JSON in dataPointConfiguration for datapoint '{datapoint_name}': {e}"
                )
                raise ValidationError(
                    f"Invalid dataPointConfiguration JSON for datapoint '{datapoint_name}': {e}"
                )
        elif "name" in datapoint or "dataSource" in datapoint:
            # Has datapoint fields but no configuration - skip validation
            datapoint_name = datapoint.get('name', 'unnamed')
            logger.debug(
                f"Datapoint '{datapoint_name}' has no dataPointConfiguration, skipping validation"
            )
            return
        else:
            # Assume it's already a parsed configuration dict (backward compatibility)
            config = datapoint

        schema = self._get_schema("dataPointConfigurationSchema")
        if schema:
            logger.debug("Found datapoint schema, performing validation")
            self._validate(config, schema, "Datapoint")
        else:
            logger.warning(f"No datapoint schema found for endpoint type '{self.endpoint_type}' - skipping validation")

    def validate_event(self, event: Dict[str, Any]):
        """Validate an event object or its configuration.

        Args:
            event: Can be either:
                - A full event object with 'eventConfiguration' as JSON string
                - A parsed configuration dictionary (for backward compatibility)
        """
        logger.debug(f"Validating event: {event}")

        # Check if this is a full event object or just the configuration
        if "eventConfiguration" in event:
            # Full event object - extract and parse configuration
            config_str = event.get("eventConfiguration")
            if not config_str:
                logger.debug("No eventConfiguration found, skipping validation")
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
            # Assume it's already a parsed configuration dict (backward compatibility)
            config = event

        schema = self._get_schema("eventConfigurationSchema")
        if schema:
            logger.debug("Found event schema, performing validation")
            self._validate(config, schema, "Event")
        else:
            logger.warning(
                f"No event schema found for endpoint type '{self.endpoint_type}' - skipping validation"
            )

    def _get_schema(self, schema_key: str) -> Optional[Dict[str, Any]]:
        """
        Extracts the specific schema from the metadata based on the endpoint type and version.
        """
        logger.debug(f"Looking for schema '{schema_key}' in metadata for endpoint type '{self.endpoint_type}'")
        inbound_endpoints = self.metadata.get("inboundEndpoints", [])
        logger.debug(f"Found {len(inbound_endpoints)} inbound endpoints in metadata")

        for idx, endpoint in enumerate(inbound_endpoints):
            endpoint_type = endpoint.get("endpointType")
            logger.debug(f"Checking endpoint {idx}: type='{endpoint_type}'")

            if endpoint_type == self.endpoint_type:
                logger.debug(f"Matched endpoint type '{self.endpoint_type}', extracting schema for '{schema_key}'")
                # Version check if needed, for now assume type is unique or we take the first match
                # if self.endpoint_version and endpoint.get("version") != self.endpoint_version:
                #     continue

                # Navigate the structure based on the key
                schema = None
                if schema_key == "datasetConfigurationSchema":
                    schema = endpoint.get("datasets", {}).get("datasetConfigurationSchema")
                elif schema_key == "dataPointConfigurationSchema":
                    schema = endpoint.get("datasets", {}).get("dataPointConfigurationSchema")
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

                if schema:
                    logger.debug(f"Found schema for '{schema_key}'")
                    return schema
                else:
                    logger.warning(f"Schema key '{schema_key}' not found in endpoint structure")
                    return None

        logger.warning(f"No endpoint found matching type '{self.endpoint_type}'")
        return None

    def _validate(self, instance: Dict[str, Any], schema: Dict[str, Any], resource_name: str):
        logger.debug(f"Validating {resource_name} against schema")
        try:
            from jsonschema import validate

            validate(instance=instance, schema=schema)
            logger.info(f"{resource_name} configuration is valid")
        except ImportError:
            logger.warning("jsonschema library not found. Skipping validation.")
        except Exception as e:
            logger.error(f"{resource_name} validation failed: {str(e)}")
            raise ValidationError(f"{resource_name} configuration is invalid: {str(e)}")
