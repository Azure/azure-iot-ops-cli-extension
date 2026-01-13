# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""
Integration tests for ConnectorMetadataValidator.

These tests employ a "Hybrid" approach:
1. **Mocked Control Plane**: Azure Management interactions (Resource Graph, IoT Ops Client) are mocked.
   This isolates the tests from Azure resource provisioning requirements and API latency.
2. **Real Data Plane**: The tests perform actual HTTP requests to the Microsoft Container Registry (MCR).
   This validates that the code can correctly fetch, decompress, and parse the real-world schemas
   currently published in production, ensuring resilience against schema changes or artifact structure updates.
"""

import hashlib
import logging
import pytest
from unittest.mock import patch, Mock
from azext_edge.edge.providers.adr.validator import ConnectorMetadataValidator
from azure.cli.core.azclierror import ValidationError

pytestmark = [pytest.mark.integration, pytest.mark.requires_network]


# Note: These tests fetch real connector metadata from Microsoft Container Registry (MCR)
# at mcr.microsoft.com/azureiotoperations/akri-connectors/
# They require network access and may fail if MCR is unavailable or if metadata versions change.


class TestConnectorMetadataValidatorIntegration:
    """Integration tests for ConnectorMetadataValidator with the complete lookup flow."""

    def setup_method(self):
        """Reset the metadata cache before each test."""
        ConnectorMetadataValidator._METADATA_CACHE.clear()

    def _create_mock_cmd(self):
        """Helper to create a mock cmd object."""
        cmd = Mock()
        cmd.cli_ctx = Mock()
        cmd.cli_ctx.cloud = Mock()
        cmd.cli_ctx.cloud.endpoints = Mock()
        cmd.cli_ctx.cloud.endpoints.resource_manager = "https://management.azure.com"
        cmd.cli_ctx.data = {"subscription_id": "eab4c10d-b020-4cb2-8959-d53cf2df388d"}
        return cmd

    def _create_mock_connector_template(self, endpoint_type, version=None, metadata_ref=None):
        """Helper to create a mock connector template response."""
        return {
            "name": f"{endpoint_type.lower()}-connector-template",
            "properties": {
                "deviceInboundEndpointTypes": [{"endpointType": endpoint_type, "version": version}],
                "connectorMetadataRef": metadata_ref
                or f"mcr.microsoft.com/azureiotoperations/akri-connectors/{endpoint_type.lower()}-metadata:1.0.0",
            },
        }

    # ========== Direct Constructor with Metadata Lookup Tests ==========

    @patch("azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client")
    def test_onvif_constructor_with_connector_template_lookup(self, mock_get_client):
        """Test the complete flow: constructor → list templates → fetch real OCI metadata → validate."""
        cmd = self._create_mock_cmd()

        # Mock IoT Ops client
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        # Mock connector template list
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[
                self._create_mock_connector_template(
                    "Microsoft.Onvif",
                    None,
                    "mcr.microsoft.com/azureiotoperations/akri-connectors/onvif-metadata:1.2.37"
                )
            ]
        )

        # Fetch real OCI metadata from MCR
        validator = ConnectorMetadataValidator(
            cmd=cmd,
            resource_group_name="doe-int-e2e-2510",
            instance_name="aio-141713881",
            endpoint_type="Microsoft.Onvif",
            endpoint_version=None,
        )

        # Skip test if metadata fetch failed (network issue, registry unavailable, etc.)
        if not validator.metadata or "inboundEndpoints" not in validator.metadata:
            pytest.skip("Failed to fetch real OCI metadata from MCR - skipping integration test")

        # Verify metadata was fetched from real MCR
        assert validator.metadata is not None
        assert "inboundEndpoints" in validator.metadata
        assert validator.metadata["name"] == "Azure IoT Operations connector for ONVIF"

        # Verify connector template was queried
        mock_client.akri_connector_template.list_by_instance_resource.assert_called_once()

        # Verify client initialization (Regression check for argument order bug)
        mock_get_client.assert_called_once_with(
            subscription_id=cmd.cli_ctx.data.get("subscription_id"),
            endpoint=cmd.cli_ctx.cloud.endpoints.resource_manager,
        )

    @patch("azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client")
    def test_opcua_case_insensitivity_uses_local_schema(self, mock_get_client):
        """
        Regression Test: Verify that 'Microsoft.opcua' (lowercase) correctly matches
        the local schema logic and DOES NOT attempt to fetch from OCI.
        """
        cmd = self._create_mock_cmd()

        # Initialize with lowercase 'opcua' which previously triggered a bug (fallback to OCI)
        validator = ConnectorMetadataValidator(
            cmd=cmd,
            resource_group_name="rg",
            instance_name="instance",
            endpoint_type="Microsoft.opcua",  # Mixed/Lower case
            endpoint_version=None,  # Empty version is required to trigger local OPC UA schema
        )

        # Should have loaded metadata
        assert validator.metadata is not None
        # Should be the local OPC UA metadata (check for a known key or value)
        assert "inboundEndpoints" in validator.metadata

        # CRITICAL: Ensure we did NOT try to use the client to fetch from OCI
        mock_get_client.assert_not_called()

    @patch("azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client")
    def test_onvif_constructor_no_version(self, mock_get_client):
        """Test ONVIF connector which typically has no version, fetches real OCI metadata."""
        cmd = self._create_mock_cmd()

        mock_client = Mock()
        mock_get_client.return_value = mock_client

        # ONVIF template without version
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[
                self._create_mock_connector_template(
                    "Microsoft.Onvif",
                    None,
                    "mcr.microsoft.com/azureiotoperations/akri-connectors/onvif-metadata:1.2.37",
                )
            ]
        )

        # Fetch real ONVIF metadata from MCR
        validator = ConnectorMetadataValidator(
            cmd=cmd,
            resource_group_name="doe-int-e2e-2510",
            instance_name="aio-141713881",
            endpoint_type="Microsoft.Onvif",
            endpoint_version=None,
        )

        # Skip test if metadata fetch failed
        if not validator.metadata or "inboundEndpoints" not in validator.metadata:
            pytest.skip("Failed to fetch real OCI metadata from MCR - skipping integration test")

        assert validator.metadata is not None
        assert validator.metadata["name"] == "Azure IoT Operations connector for ONVIF"
        assert validator.endpoint_version is None

    # ========== Dataset Validation Tests ==========

    @patch("azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client")
    def test_validate_onvif_event_valid(self, mock_get_client):
        """Test ONVIF event validation with valid configuration using real OCI metadata."""
        cmd = self._create_mock_cmd()
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[self._create_mock_connector_template(
                "Microsoft.Onvif", None, "mcr.microsoft.com/azureiotoperations/akri-connectors/onvif-metadata:1.2.37"
            )]
        )

        # Fetch real metadata from MCR
        validator = ConnectorMetadataValidator(
            cmd=cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Onvif",
            endpoint_version=None,
        )

        # Skip test if metadata fetch failed
        if not validator.metadata or "inboundEndpoints" not in validator.metadata:
            pytest.skip("Failed to fetch real OCI metadata from MCR - skipping integration test")

        valid_config = {"topic": "tns1:Device/tnsaxis:Sensor/PIR", "endpointUrl": "http://example.com"}

        # Should not raise
        validator.validate_event(valid_config)

    # ========== Event Validation Tests ==========

    @patch("azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client")
    def test_validate_onvif_event_empty_schema(self, mock_get_client):
        """Test ONVIF event validation with empty schema (allows anything) using real OCI metadata."""
        cmd = self._create_mock_cmd()
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[self._create_mock_connector_template(
                "Microsoft.Onvif", None, "mcr.microsoft.com/azureiotoperations/akri-connectors/onvif-metadata:1.2.37"
            )]
        )

        # Fetch real ONVIF metadata from MCR
        validator = ConnectorMetadataValidator(
            cmd=cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Onvif",
            endpoint_version=None,
        )

        # Skip test if metadata fetch failed
        if not validator.metadata or "inboundEndpoints" not in validator.metadata:
            pytest.skip("Failed to fetch real OCI metadata from MCR - skipping integration test")

        # Empty schema should allow any object
        config = {"filter": "Topic = 'motion'"}
        validator.validate_event(config)

    # ========== Schema Extraction Tests ==========

    @patch("azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client")
    def test_get_schema_additional_configuration(self, mock_get_client):
        """Test extracting additional configuration schema from real OCI metadata."""
        cmd = self._create_mock_cmd()
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[self._create_mock_connector_template(
                "Microsoft.Onvif", None, "mcr.microsoft.com/azureiotoperations/akri-connectors/onvif-metadata:1.2.37"
            )]
        )

        # Fetch real ONVIF metadata from MCR
        validator = ConnectorMetadataValidator(
            cmd=cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Onvif",
            endpoint_version=None,
        )

        # Skip test if metadata fetch failed
        if not validator.metadata or "inboundEndpoints" not in validator.metadata:
            pytest.skip("Failed to fetch real OCI metadata from MCR - skipping integration test")

        schema = validator._get_schema("additionalConfigurationSchema")
        assert schema is not None
        assert "acceptInvalidHostnames" in schema["properties"]
        assert "acceptInvalidCertificates" in schema["properties"]

    # ========== OCI Artifact Fetching Tests ==========

    @patch("azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator._get_auth_token")
    @patch("azext_edge.edge.providers.adr.validator.requests.get")
    def test_fetch_oci_artifact_success(self, mock_get, mock_get_auth_token):
        """Test successful OCI artifact fetching with mocked HTTP responses."""
        # Mock auth token
        mock_get_auth_token.return_value = None  # Anonymous access

        # Mock manifest response
        manifest_response = Mock()
        manifest_response.status_code = 200
        manifest_response.json.return_value = {
            "config": {
                # DOE requires connector template manifests to use the connector media type
                "mediaType": "application/vnd.microsoft.akri-connector.v1+json",
                "digest": "sha256:config123",
            },
            "layers": [{"mediaType": "application/vnd.microsoft.akri-connector.v1+json", "digest": "sha256:abc123"}],
        }

        # Mock blob response with sample metadata as tar
        sample_metadata = {
            "$schema": "https://example.com/schema.json",
            "name": "Test Connector",
            "version": "1.0.0",
            "supportedArchitectures": ["linux/amd64"],
            "imageConfigurationSettings": {"imageName": "test", "tag": "1.0.0"},
            "inboundEndpoints": [
                {
                    "endpointType": "Microsoft.Test",
                    "fields": {"address": {"input": "required"}},
                    "datasets": {
                        "limits": {"minimum": 0},
                        "fields": {"dataSource": {"input": "optional"}, "typeRef": {"input": "optional"}},
                    },
                }
            ],
        }

        # Create a tar file with the metadata JSON
        import tarfile
        import io
        import json

        tar_buffer = io.BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
            json_bytes = json.dumps(sample_metadata).encode('utf-8')
            tarinfo = tarfile.TarInfo(name="connector-metadata.json")
            tarinfo.size = len(json_bytes)
            tar.addfile(tarinfo, io.BytesIO(json_bytes))

        # Compute the real digest of the blob so the manifest matches the content we serve
        real_blob_digest = hashlib.sha256(tar_buffer.getvalue()).hexdigest()

        blob_response = Mock()
        blob_response.status_code = 200
        blob_response.headers = {"Content-Type": "application/vnd.oci.image.layer.v1.tar"}
        blob_response.content = tar_buffer.getvalue()

        # Update manifest to advertise the actual blob digest
        manifest_response.json.return_value["layers"][0]["digest"] = f"sha256:{real_blob_digest}"

        mock_get.side_effect = [manifest_response, blob_response]

        result = ConnectorMetadataValidator.fetch_oci_artifact(
            "mcr.microsoft.com/azureiotoperations/akri-connectors/rest-metadata:1.0.5"
        )

        assert result == sample_metadata
        assert mock_get.call_count == 2

    @patch("azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator._get_auth_token")
    @patch("azext_edge.edge.providers.adr.validator.requests.get")
    def test_fetch_oci_artifact_rejects_standard_oci_config_media_type(self, mock_get, mock_get_auth_token):
        """Verify manifests using the generic OCI config media type are rejected (DOE parity)."""
        mock_get_auth_token.return_value = None

        manifest_response = Mock()
        manifest_response.status_code = 200
        manifest_response.json.return_value = {
            "config": {
                "mediaType": "application/vnd.oci.image.config.v1+json",  # Not allowed for connector templates
                "digest": "sha256:config123",
            },
            "layers": [
                {"mediaType": "application/vnd.microsoft.akri-connector.v1+json", "digest": "sha256:abc123"}
            ],
        }

        blob_response = Mock()
        blob_response.status_code = 200
        blob_response.headers = {"Content-Type": "application/vnd.oci.image.layer.v1.tar"}
        blob_response.content = b"dummy"

        mock_get.side_effect = [manifest_response, blob_response]

        with pytest.raises(ValidationError) as exc_info:
            ConnectorMetadataValidator.fetch_oci_artifact(
                "mcr.microsoft.com/azureiotoperations/akri-connectors/rest-metadata:1.0.5"
            )

        assert "config media type" in str(exc_info.value)

    def test_fetch_oci_artifact_invalid_reference(self):
        """Test OCI artifact fetching with invalid reference."""
        with pytest.raises(ValidationError) as exc_info:
            ConnectorMetadataValidator.fetch_oci_artifact("invalid-reference")
        assert "Invalid OCI reference" in str(exc_info.value)

    @patch("azext_edge.edge.providers.adr.validator.requests.get")
    def test_fetch_oci_artifact_manifest_not_found(self, mock_get):
        """Test OCI artifact fetching when manifest is not found."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_get.return_value = mock_response

        with pytest.raises(ValidationError) as exc_info:
            ConnectorMetadataValidator.fetch_oci_artifact("mcr.microsoft.com/repo:tag")
        assert "Failed to fetch manifest" in str(exc_info.value)

    # ========== Caching Tests ==========

    @patch("azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client")
    def test_metadata_caching(self, mock_get_client):
        """Test that metadata is cached and not fetched multiple times from real MCR."""
        cmd = self._create_mock_cmd()
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[self._create_mock_connector_template(
                "Microsoft.Http", "1.0",
                "mcr.microsoft.com/azureiotoperations/akri-connectors/rest-metadata:1.0.4"
            )]
        )

        # Track real OCI fetches using spy
        original_fetch = ConnectorMetadataValidator.fetch_oci_artifact
        fetch_count = {"count": 0}

        def counting_fetch(*args, **kwargs):
            fetch_count["count"] += 1
            return original_fetch(*args, **kwargs)

        with patch.object(ConnectorMetadataValidator, "fetch_oci_artifact", side_effect=counting_fetch):
            # First validator
            validator1 = ConnectorMetadataValidator(
                cmd=cmd,
                resource_group_name="test-rg",
                instance_name="test-instance",
                endpoint_type="Microsoft.Http",
                endpoint_version="1.0",
            )

            # Second validator with same endpoint type/version
            validator2 = ConnectorMetadataValidator(
                cmd=cmd,
                resource_group_name="test-rg",
                instance_name="test-instance",
                endpoint_type="Microsoft.Http",
                endpoint_version="1.0",
            )

            # OCI fetch should only happen once due to caching
            assert fetch_count["count"] == 1
            assert validator1.metadata == validator2.metadata

    # ========== Error Handling Tests ==========

    @patch("azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client")
    def test_no_matching_connector_template(self, mock_get_client, caplog):
        """Test graceful handling when no connector template matches."""
        # Silence expected error log from the validator while asserting it raises.
        cmd = self._create_mock_cmd()
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(return_value=[])  # No templates

        caplog.set_level(logging.CRITICAL, logger="cli.azext_edge.edge.providers.adr.validator")

        with pytest.raises(ValidationError):
            ConnectorMetadataValidator(
                cmd=cmd,
                resource_group_name="test-rg",
                instance_name="test-instance",
                endpoint_type="Microsoft.Unknown",
                endpoint_version="1.0",
            )

    @patch("azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client")
    def test_connector_template_missing_metadata_ref(self, mock_get_client, caplog):
        """Test handling when connector template has no connectorMetadataRef."""
        # Silence expected error log from the validator while asserting it raises.
        cmd = self._create_mock_cmd()
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.akri_connector_template = Mock()

        # Template without connectorMetadataRef
        template = {
            "name": "broken-template",
            "properties": {
                "deviceInboundEndpointTypes": [{"endpointType": "Microsoft.Http", "version": "1.0"}]
                # Missing connectorMetadataRef
            },
        }
        mock_client.akri_connector_template.list_by_instance_resource = Mock(return_value=[template])

        caplog.set_level(logging.CRITICAL, logger="cli.azext_edge.edge.providers.adr.validator")

        with pytest.raises(ValidationError):
            ConnectorMetadataValidator(
                cmd=cmd,
                resource_group_name="test-rg",
                instance_name="test-instance",
                endpoint_type="Microsoft.Http",
                endpoint_version="1.0",
            )

    @patch("azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client")
    def test_validator_no_jsonschema_library(self, mock_get_client):
        """Test validator gracefully handles missing jsonschema library."""
        cmd = self._create_mock_cmd()
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[self._create_mock_connector_template(
                "Microsoft.Onvif", None, "mcr.microsoft.com/azureiotoperations/akri-connectors/onvif-metadata:1.2.37"
            )]
        )

        # Fetch real metadata
        validator = ConnectorMetadataValidator(
            cmd=cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Onvif",
            endpoint_version=None,
        )

        # Skip test if metadata fetch failed
        if not validator.metadata or "inboundEndpoints" not in validator.metadata:
            pytest.skip("Failed to fetch real OCI metadata from MCR - skipping integration test")

        # Mock ImportError for jsonschema
        with patch("jsonschema.validate", side_effect=ImportError):
            config = {"topic": "tns1:Device/tnsaxis:Sensor/PIR"}
            # Should not raise, just log warning
            validator.validate_event(config)
