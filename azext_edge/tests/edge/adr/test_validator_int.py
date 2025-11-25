# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""
Integration tests for ConnectorMetadataValidator.
These tests validate the complete flow: Asset → Device → Connector Template → OCI Metadata → Validation
"""

import pytest
import json
from unittest.mock import patch, MagicMock, Mock
from azext_edge.edge.providers.adr.validator import ConnectorMetadataValidator
from azure.cli.core.azclierror import ValidationError

pytestmark = pytest.mark.integration


# Real metadata examples from actual connector metadata files
REST_HTTP_METADATA = {
    "$schema": "https://raw.githubusercontent.com/Azure/iot-operations-sdks/refs/heads/main/doc/akri_connector/connector-metadata-schema.json",
    "name": "Azure IoT Operations connector for REST/HTTP",
    "version": "1.0.5",
    "inboundEndpoints": [
        {
            "endpointType": "Microsoft.Http",
            "version": "1.0",
            "datasets": {
                "datasetConfigurationSchema": {
                    "$schema": "http://json-schema.org/draft-07/schema#",
                    "title": "REST Dataset Config Schema",
                    "type": "object",
                    "properties": {
                        "samplingIntervalInMilliseconds": {
                            "type": "integer",
                            "exclusiveMinimum": 0,
                            "maximum": 18446744073709551615
                        },
                        "transform": {
                            "type": "string"
                        }
                    }
                },
                "fields": {
                    "dataSource": {
                        "input": "required"
                    }
                }
            }
        }
    ]
}

ONVIF_METADATA = {
    "$schema": "https://raw.githubusercontent.com/Azure/iot-operations-sdks/refs/heads/main/doc/akri_connector/connector-metadata-schema.json",
    "name": "Azure IoT Operations connector for ONVIF",
    "version": "1.2.37",
    "inboundEndpoints": [
        {
            "endpointType": "Microsoft.Onvif",
            "additionalConfigurationSchema": {
                "type": "object",
                "properties": {
                    "acceptInvalidHostnames": {
                        "type": "boolean",
                        "default": False
                    },
                    "acceptInvalidCertificates": {
                        "type": "boolean",
                        "default": False
                    }
                },
                "required": []
            },
            "eventGroups": {
                "events": {
                    "eventConfigurationSchema": {}
                }
            },
            "managementGroups": {
                "managementGroupConfigurationSchema": {},
                "managementGroupActions": {
                    "actionConfigurationSchema": {}
                }
            }
        }
    ]
}


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
                "deviceInboundEndpointTypes": [
                    {
                        "endpointType": endpoint_type,
                        "version": version
                    }
                ],
                "connectorMetadataRef": metadata_ref or f"mcr.microsoft.com/azureiotoperations/akri-connectors/{endpoint_type.lower()}-metadata:1.0.0"
            }
        }

    # ========== Direct Constructor with Metadata Lookup Tests ==========

    @patch('azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client')
    def test_rest_constructor_with_connector_template_lookup(self, mock_get_client):
        """Test the complete flow: constructor → list templates → fetch OCI → validate."""
        cmd = self._create_mock_cmd()
        
        # Mock IoT Ops client
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        
        # Mock connector template list
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[
                self._create_mock_connector_template("Microsoft.Http", "1.0", 
                    "mcr.microsoft.com/azureiotoperations/akri-connectors/rest-metadata:1.0.5")
            ]
        )
        
        # Mock OCI fetch
        with patch.object(ConnectorMetadataValidator, 'fetch_oci_artifact', return_value=REST_HTTP_METADATA):
            validator = ConnectorMetadataValidator(
                cmd=cmd,
                resource_group_name="doe-int-e2e-2510",
                instance_name="aio-141713881",
                endpoint_type="Microsoft.Http",
                endpoint_version="1.0"
            )
            
            # Verify metadata was fetched
            assert validator.metadata == REST_HTTP_METADATA
            assert "inboundEndpoints" in validator.metadata
            
            # Verify connector template was queried
            mock_client.akri_connector_template.list_by_instance_resource.assert_called_once()

    @patch('azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client')
    def test_onvif_constructor_no_version(self, mock_get_client):
        """Test ONVIF connector which typically has no version."""
        cmd = self._create_mock_cmd()
        
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        
        # ONVIF template without version
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[
                self._create_mock_connector_template("Microsoft.Onvif", None, 
                    "mcr.microsoft.com/azureiotoperations/akri-connectors/onvif-metadata:1.2.37")
            ]
        )
        
        with patch.object(ConnectorMetadataValidator, 'fetch_oci_artifact', return_value=ONVIF_METADATA):
            validator = ConnectorMetadataValidator(
                cmd=cmd,
                resource_group_name="doe-int-e2e-2510",
                instance_name="aio-141713881",
                endpoint_type="Microsoft.Onvif",
                endpoint_version=None
            )
            
            assert validator.metadata == ONVIF_METADATA
            assert validator.endpoint_version is None

    # ========== Dataset Validation Tests ==========

    @patch('azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client')
    def test_validate_rest_dataset_valid(self, mock_get_client):
        """Test REST dataset validation with valid configuration."""
        cmd = self._create_mock_cmd()
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[self._create_mock_connector_template("Microsoft.Http", "1.0")]
        )
        
        with patch.object(ConnectorMetadataValidator, 'fetch_oci_artifact', return_value=REST_HTTP_METADATA):
            validator = ConnectorMetadataValidator(
                cmd=cmd,
                resource_group_name="test-rg",
                instance_name="test-instance",
                endpoint_type="Microsoft.Http",
                endpoint_version="1.0"
            )
            
            valid_config = {
                "samplingIntervalInMilliseconds": 5000,
                "transform": "http://example.com/transform.wasm"
            }
            
            # Should not raise
            validator.validate_dataset(valid_config)

    @patch('azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client')
    def test_validate_rest_dataset_invalid_negative_interval(self, mock_get_client):
        """Test REST dataset validation fails with negative sampling interval."""
        cmd = self._create_mock_cmd()
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[self._create_mock_connector_template("Microsoft.Http", "1.0")]
        )
        
        with patch.object(ConnectorMetadataValidator, 'fetch_oci_artifact', return_value=REST_HTTP_METADATA):
            validator = ConnectorMetadataValidator(
                cmd=cmd,
                resource_group_name="test-rg",
                instance_name="test-instance",
                endpoint_type="Microsoft.Http",
                endpoint_version="1.0"
            )
            
            invalid_config = {
                "samplingIntervalInMilliseconds": -100
            }
            
            with pytest.raises(ValidationError) as exc_info:
                validator.validate_dataset(invalid_config)
            assert "Dataset configuration is invalid" in str(exc_info.value)

    @patch('azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client')
    def test_validate_rest_dataset_invalid_zero_interval(self, mock_get_client):
        """Test REST dataset validation fails with zero (exclusiveMinimum)."""
        cmd = self._create_mock_cmd()
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[self._create_mock_connector_template("Microsoft.Http", "1.0")]
        )
        
        with patch.object(ConnectorMetadataValidator, 'fetch_oci_artifact', return_value=REST_HTTP_METADATA):
            validator = ConnectorMetadataValidator(
                cmd=cmd,
                resource_group_name="test-rg",
                instance_name="test-instance",
                endpoint_type="Microsoft.Http",
                endpoint_version="1.0"
            )
            
            invalid_config = {
                "samplingIntervalInMilliseconds": 0
            }
            
            with pytest.raises(ValidationError):
                validator.validate_dataset(invalid_config)

    # ========== Event Validation Tests ==========

    @patch('azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client')
    def test_validate_onvif_event_empty_schema(self, mock_get_client):
        """Test ONVIF event validation with empty schema (allows anything)."""
        cmd = self._create_mock_cmd()
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[self._create_mock_connector_template("Microsoft.Onvif", None)]
        )
        
        with patch.object(ConnectorMetadataValidator, 'fetch_oci_artifact', return_value=ONVIF_METADATA):
            validator = ConnectorMetadataValidator(
                cmd=cmd,
                resource_group_name="test-rg",
                instance_name="test-instance",
                endpoint_type="Microsoft.Onvif",
                endpoint_version=None
            )
            
            # Empty schema should allow any object
            config = {"filter": "Topic = 'motion'"}
            validator.validate_event(config)

    # ========== Schema Extraction Tests ==========

    @patch('azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client')
    def test_get_schema_dataset_configuration(self, mock_get_client):
        """Test extracting dataset configuration schema."""
        cmd = self._create_mock_cmd()
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[self._create_mock_connector_template("Microsoft.Http", "1.0")]
        )
        
        with patch.object(ConnectorMetadataValidator, 'fetch_oci_artifact', return_value=REST_HTTP_METADATA):
            validator = ConnectorMetadataValidator(
                cmd=cmd,
                resource_group_name="test-rg",
                instance_name="test-instance",
                endpoint_type="Microsoft.Http",
                endpoint_version="1.0"
            )
            
            schema = validator._get_schema("datasetConfigurationSchema")
            assert schema is not None
            assert "samplingIntervalInMilliseconds" in schema["properties"]

    @patch('azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client')
    def test_get_schema_additional_configuration(self, mock_get_client):
        """Test extracting additional configuration schema."""
        cmd = self._create_mock_cmd()
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[self._create_mock_connector_template("Microsoft.Onvif", None)]
        )
        
        with patch.object(ConnectorMetadataValidator, 'fetch_oci_artifact', return_value=ONVIF_METADATA):
            validator = ConnectorMetadataValidator(
                cmd=cmd,
                resource_group_name="test-rg",
                instance_name="test-instance",
                endpoint_type="Microsoft.Onvif",
                endpoint_version=None
            )
            
            schema = validator._get_schema("additionalConfigurationSchema")
            assert schema is not None
            assert "acceptInvalidHostnames" in schema["properties"]

    # ========== OCI Artifact Fetching Tests ==========

    @patch('azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator._get_auth_token')
    @patch('azext_edge.edge.providers.adr.validator.requests.get')
    def test_fetch_oci_artifact_success(self, mock_get, mock_get_auth_token):
        """Test successful OCI artifact fetching."""
        # Mock auth token
        mock_get_auth_token.return_value = None  # Anonymous access
        
        # Mock manifest response
        manifest_response = Mock()
        manifest_response.status_code = 200
        manifest_response.json.return_value = {
            "config": {
                "mediaType": "application/vnd.oci.image.config.v1+json",
                "digest": "sha256:config123"
            },
            "layers": [
                {
                    "mediaType": "application/vnd.microsoft.akri-connector.v1+json",
                    "digest": "sha256:abc123"
                }
            ]
        }
        
        # Mock blob response
        blob_response = Mock()
        blob_response.status_code = 200
        blob_response.json.return_value = REST_HTTP_METADATA
        
        mock_get.side_effect = [manifest_response, blob_response]
        
        result = ConnectorMetadataValidator.fetch_oci_artifact("mcr.microsoft.com/azureiotoperations/akri-connectors/rest-metadata:1.0.5")
        
        assert result == REST_HTTP_METADATA
        assert mock_get.call_count == 2

    def test_fetch_oci_artifact_invalid_reference(self):
        """Test OCI artifact fetching with invalid reference."""
        with pytest.raises(ValidationError) as exc_info:
            ConnectorMetadataValidator.fetch_oci_artifact("invalid-reference")
        assert "Invalid OCI reference" in str(exc_info.value)

    @patch('azext_edge.edge.providers.adr.validator.requests.get')
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

    @patch('azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client')
    def test_metadata_caching(self, mock_get_client):
        """Test that metadata is cached and not fetched multiple times."""
        cmd = self._create_mock_cmd()
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[self._create_mock_connector_template("Microsoft.Http", "1.0")]
        )
        
        with patch.object(ConnectorMetadataValidator, 'fetch_oci_artifact', return_value=REST_HTTP_METADATA) as mock_fetch:
            # First validator
            validator1 = ConnectorMetadataValidator(
                cmd=cmd,
                resource_group_name="test-rg",
                instance_name="test-instance",
                endpoint_type="Microsoft.Http",
                endpoint_version="1.0"
            )
            
            # Second validator with same endpoint type/version
            validator2 = ConnectorMetadataValidator(
                cmd=cmd,
                resource_group_name="test-rg",
                instance_name="test-instance",
                endpoint_type="Microsoft.Http",
                endpoint_version="1.0"
            )
            
            # OCI fetch should only happen once
            assert mock_fetch.call_count == 1
            assert validator1.metadata == validator2.metadata

    # ========== Error Handling Tests ==========

    @patch('azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client')
    def test_no_matching_connector_template(self, mock_get_client):
        """Test graceful handling when no connector template matches."""
        cmd = self._create_mock_cmd()
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[]  # No templates
        )
        
        validator = ConnectorMetadataValidator(
            cmd=cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Unknown",
            endpoint_version="1.0"
        )
        
        # Should return empty metadata
        assert validator.metadata == {}
        
        # Validation should be skipped
        validator.validate_dataset({"any": "data"})  # Should not raise

    @patch('azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client')
    def test_connector_template_missing_metadata_ref(self, mock_get_client):
        """Test handling when connector template has no connectorMetadataRef."""
        cmd = self._create_mock_cmd()
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.akri_connector_template = Mock()
        
        # Template without connectorMetadataRef
        template = {
            "name": "broken-template",
            "properties": {
                "deviceInboundEndpointTypes": [
                    {"endpointType": "Microsoft.Http", "version": "1.0"}
                ]
                # Missing connectorMetadataRef
            }
        }
        mock_client.akri_connector_template.list_by_instance_resource = Mock(return_value=[template])
        
        validator = ConnectorMetadataValidator(
            cmd=cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Http",
            endpoint_version="1.0"
        )
        
        assert validator.metadata == {}

    def test_validator_no_jsonschema_library(self):
        """Test validator gracefully handles missing jsonschema library."""
        cmd = self._create_mock_cmd()
        
        with patch.object(ConnectorMetadataValidator, '_get_metadata', return_value=REST_HTTP_METADATA):
            validator = ConnectorMetadataValidator(
                cmd=cmd,
                resource_group_name="test-rg",
                instance_name="test-instance",
                endpoint_type="Microsoft.Http",
                endpoint_version="1.0"
            )
            
            # Mock ImportError for jsonschema
            with patch('jsonschema.validate', side_effect=ImportError):
                config = {"samplingIntervalInMilliseconds": 1000}
                # Should not raise, just log warning
                validator.validate_dataset(config)
