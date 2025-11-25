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
    def from_asset(cls, cmd, asset: Dict[str, Any]):
        """
        Factory method to create validator from an asset by looking up its device and endpoint.

        Args:
            cmd: The Azure CLI command context
            asset: The asset resource dictionary

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

        # Get the namespace from asset
        adr_namespace = asset.get("adrNamespace") or asset.get("properties", {}).get("adrNamespace")
        if not adr_namespace:
            raise ValidationError("Asset does not have adrNamespace specified.")

        namespace_id = parse_resource_id(adr_namespace)
        if not namespace_id:
            raise ValidationError(f"Invalid namespace ID: {adr_namespace}")

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
            namespace_id.subscription_id,
        )

        device = iotops_client.device.get(
            resource_group_name=namespace_id.resource_group_name,
            namespace_name=namespace_id.resource_name,
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

        # Extract instance name from namespace
        # Namespace format: aio-adr-ns-{instance_name_hash}
        instance_name = namespace_id.resource_name.replace("-ns-", "-").rsplit("-", 1)[0]  # Heuristic

        return cls(
            cmd=cmd,
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            endpoint_type=endpoint_type,
            endpoint_version=endpoint_version,
        )

    def _get_metadata(self) -> Dict[str, Any]:
        """
        Retrieves the metadata JSON for the connector by:
        1. Finding the matching Connector Template based on endpoint type/version
        2. Extracting the connectorMetadataRef (OCI URI)
        3. Fetching the OCI artifact containing the JSON metadata
        4. Caching the result for future use

        Returns:
            Dict containing the connector metadata JSON
        """
        # Check cache first
        cache_key = f"{self.endpoint_type}:{self.endpoint_version or 'none'}"
        if cache_key in self._METADATA_CACHE:
            logger.debug(f"Using cached metadata for {cache_key}")
            return self._METADATA_CACHE[cache_key]

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
    def fetch_oci_artifact(image_ref: str) -> Dict[str, Any]:
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

        # 3. Find the config layer or the specific JSON layer
        # We look for a layer with a specific media type or just the first application/json layer
        target_digest = None

        # Common media types for OCI artifacts containing config
        target_media_types = [
            "application/vnd.microsoft.akri-connector.v1+json",  # Example custom type
            "application/json",
            "application/octet-stream",  # Sometimes used for generic blobs
        ]

        layers = manifest.get("layers", [])
        # Also check config blob if it's not a standard image
        config = manifest.get("config", {})

        # Strategy: Look for the specific artifact layer
        for layer in layers:
            if (
                layer.get("mediaType") in target_media_types
                or layer.get("annotations", {}).get("org.opencontainers.image.title") == "connector-metadata.json"
            ):
                target_digest = layer["digest"]
                break

        if not target_digest:
            # Fallback: try the config blob if it's small and json
            if config.get("mediaType") in target_media_types:
                target_digest = config["digest"]

        if not target_digest:
            raise ValidationError(f"Could not find suitable JSON layer in {image_ref}")

        # 4. Fetch the Blob
        blob_url = f"{base_url}/blobs/{target_digest}"
        logger.debug(f"Fetching blob from {blob_url}")

        blob_response = requests.get(blob_url, headers=headers)
        if blob_response.status_code != 200:
            raise ValidationError(f"Failed to fetch blob {target_digest}: {blob_response.status_code}")

        try:
            return blob_response.json()
        except json.JSONDecodeError:
            raise ValidationError(f"Artifact at {image_ref} is not valid JSON.")

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

    def validate_dataset(self, dataset_config: Dict[str, Any]):
        logger.debug(f"Validating dataset configuration: {dataset_config}")
        schema = self._get_schema("datasetConfigurationSchema")
        if schema:
            logger.debug("Found dataset schema, performing validation")
            self._validate(dataset_config, schema, "Dataset")
        else:
            logger.warning(f"No dataset schema found for endpoint type '{self.endpoint_type}' - skipping validation")

    def validate_datapoint(self, datapoint_config: Dict[str, Any]):
        logger.debug(f"Validating datapoint configuration: {datapoint_config}")
        schema = self._get_schema("dataPointConfigurationSchema")
        if schema:
            logger.debug("Found datapoint schema, performing validation")
            self._validate(datapoint_config, schema, "Datapoint")
        else:
            logger.warning(f"No datapoint schema found for endpoint type '{self.endpoint_type}' - skipping validation")

    def validate_event(self, event_config: Dict[str, Any]):
        logger.debug(f"Validating event configuration: {event_config}")
        schema = self._get_schema("eventConfigurationSchema")
        if schema:
            logger.debug("Found event schema, performing validation")
            self._validate(event_config, schema, "Event")
        else:
            logger.warning(f"No event schema found for endpoint type '{self.endpoint_type}' - skipping validation")

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
