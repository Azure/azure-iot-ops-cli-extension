# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""
Integration tests for ConnectorMetadataValidator.

These tests mock Azure Management interactions but perform real HTTP requests
to Microsoft Container Registry (MCR) and Azure Container Registry (ACR) to
validate real-world schema handling.
"""

import hashlib
import logging
import pytest
from unittest.mock import patch, Mock
from azext_edge.edge.providers.adr.validator import ConnectorMetadataValidator
from azext_edge.edge.util.oci_client import get_oci_client
from azure.cli.core.azclierror import ValidationError

pytestmark = [pytest.mark.integration, pytest.mark.requires_network]


class TestConnectorMetadataValidatorIntegration:

    def setup_method(self):
        ConnectorMetadataValidator._METADATA_CACHE.clear()

    def _create_mock_cmd(self):
        cmd = Mock()
        cmd.cli_ctx = Mock()
        cmd.cli_ctx.cloud = Mock()
        cmd.cli_ctx.cloud.endpoints = Mock()
        cmd.cli_ctx.cloud.endpoints.resource_manager = "https://management.azure.com"
        cmd.cli_ctx.data = {"subscription_id": "eab4c10d-b020-4cb2-8959-d53cf2df388d"}
        return cmd

    def _create_mock_connector_template(self, endpoint_type, version=None, metadata_ref=None):
        return {
            "name": f"{endpoint_type.lower()}-connector-template",
            "properties": {
                "deviceInboundEndpointTypes": [{"endpointType": endpoint_type, "version": version}],
                "connectorMetadataRef": metadata_ref
                or f"mcr.microsoft.com/azureiotoperations/akri-connectors/{endpoint_type.lower()}-metadata:1.0.0",
            },
        }

    @patch("azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client")
    def test_onvif_constructor_with_connector_template_lookup(self, mock_get_client):
        cmd = self._create_mock_cmd()

        mock_client = Mock()
        mock_get_client.return_value = mock_client

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

        validator = ConnectorMetadataValidator(
            cmd=cmd,
            resource_group_name="doe-int-e2e-2510",
            instance_name="aio-141713881",
            endpoint_type="Microsoft.Onvif",
            endpoint_version=None,
        )

        if not validator.metadata or "inboundEndpoints" not in validator.metadata:
            pytest.skip("Failed to fetch real OCI metadata from MCR - skipping integration test")

        assert validator.metadata is not None
        assert "inboundEndpoints" in validator.metadata
        assert validator.metadata["name"] == "Azure IoT Operations connector for ONVIF"
        mock_client.akri_connector_template.list_by_instance_resource.assert_called_once()
        mock_get_client.assert_called_once_with(
            subscription_id=cmd.cli_ctx.data.get("subscription_id"),
            endpoint=cmd.cli_ctx.cloud.endpoints.resource_manager,
        )

    @patch("azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client")
    def test_opcua_case_insensitivity_uses_local_schema(self, mock_get_client):
        cmd = self._create_mock_cmd()

        validator = ConnectorMetadataValidator(
            cmd=cmd,
            resource_group_name="rg",
            instance_name="instance",
            endpoint_type="Microsoft.opcua",
            endpoint_version=None,
        )

        assert validator.metadata is not None
        assert "inboundEndpoints" in validator.metadata
        mock_get_client.assert_not_called()

    @patch("azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client")
    def test_onvif_constructor_no_version(self, mock_get_client):
        cmd = self._create_mock_cmd()

        mock_client = Mock()
        mock_get_client.return_value = mock_client

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

        validator = ConnectorMetadataValidator(
            cmd=cmd,
            resource_group_name="doe-int-e2e-2510",
            instance_name="aio-141713881",
            endpoint_type="Microsoft.Onvif",
            endpoint_version=None,
        )

        if not validator.metadata or "inboundEndpoints" not in validator.metadata:
            pytest.skip("Failed to fetch real OCI metadata from MCR - skipping integration test")

        assert validator.metadata is not None
        assert validator.metadata["name"] == "Azure IoT Operations connector for ONVIF"
        assert validator.endpoint_version is None

    @patch("azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client")
    def test_validate_onvif_event_valid(self, mock_get_client):
        cmd = self._create_mock_cmd()
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[self._create_mock_connector_template(
                "Microsoft.Onvif", None, "mcr.microsoft.com/azureiotoperations/akri-connectors/onvif-metadata:1.2.37"
            )]
        )

        validator = ConnectorMetadataValidator(
            cmd=cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Onvif",
            endpoint_version=None,
        )

        if not validator.metadata or "inboundEndpoints" not in validator.metadata:
            pytest.skip("Failed to fetch real OCI metadata from MCR - skipping integration test")

        valid_config = {"topic": "tns1:Device/tnsaxis:Sensor/PIR", "endpointUrl": "http://example.com"}
        validator.validate_event(valid_config)

    @patch("azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client")
    def test_validate_onvif_event_empty_schema(self, mock_get_client):
        cmd = self._create_mock_cmd()
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[self._create_mock_connector_template(
                "Microsoft.Onvif", None, "mcr.microsoft.com/azureiotoperations/akri-connectors/onvif-metadata:1.2.37"
            )]
        )

        validator = ConnectorMetadataValidator(
            cmd=cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Onvif",
            endpoint_version=None,
        )

        if not validator.metadata or "inboundEndpoints" not in validator.metadata:
            pytest.skip("Failed to fetch real OCI metadata from MCR - skipping integration test")

        config = {"filter": "Topic = 'motion'"}
        validator.validate_event(config)

    @patch("azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client")
    def test_get_schema_additional_configuration(self, mock_get_client):
        cmd = self._create_mock_cmd()
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[self._create_mock_connector_template(
                "Microsoft.Onvif", None, "mcr.microsoft.com/azureiotoperations/akri-connectors/onvif-metadata:1.2.37"
            )]
        )

        validator = ConnectorMetadataValidator(
            cmd=cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Onvif",
            endpoint_version=None,
        )

        if not validator.metadata or "inboundEndpoints" not in validator.metadata:
            pytest.skip("Failed to fetch real OCI metadata from MCR - skipping integration test")

        schema = validator._get_schema("additionalConfigurationSchema")
        assert schema is not None
        assert "acceptInvalidHostnames" in schema["properties"]
        assert "acceptInvalidCertificates" in schema["properties"]

    @patch("azext_edge.edge.util.oci_client.OciRegistryClient._get_anonymous_token")
    @patch("azext_edge.edge.util.oci_client.OciRegistryClient.get")
    def test_fetch_oci_artifact_success(self, mock_get, mock_get_auth_token):
        mock_get_auth_token.return_value = None

        manifest_response = Mock()
        manifest_response.status_code = 200
        manifest_response.json.return_value = {
            "config": {
                "mediaType": "application/vnd.microsoft.akri-connector.v1+json",
                "digest": "sha256:config123",
            },
            "layers": [{"mediaType": "application/vnd.microsoft.akri-connector.v1+json", "digest": "sha256:abc123"}],
        }

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

        import json

        json_bytes = json.dumps(sample_metadata).encode('utf-8')
        real_blob_digest = hashlib.sha256(json_bytes).hexdigest()

        blob_response = Mock()
        blob_response.status_code = 200
        blob_response.headers = {"Content-Type": "application/json"}
        blob_response.content = json_bytes

        manifest_response.json.return_value["layers"][0]["digest"] = f"sha256:{real_blob_digest}"

        mock_get.side_effect = [manifest_response, blob_response]

        oci_client = get_oci_client()
        artifact_info = oci_client.fetch_first_layer(
            "mcr.microsoft.com/azureiotoperations/akri-connectors/rest-metadata:1.0.5",
            expected_config_media_type="application/vnd.microsoft.akri-connector.v1+json",
        )

        # Extract and validate metadata like the validator does
        metadata = ConnectorMetadataValidator._extract_metadata_from_blob(
            artifact_info.content, artifact_info.content_type, "test"
        )

        assert metadata == sample_metadata
        assert mock_get.call_count == 2

    @patch("azext_edge.edge.util.oci_client.OciRegistryClient._get_anonymous_token")
    @patch("azext_edge.edge.util.oci_client.OciRegistryClient.get")
    def test_fetch_oci_artifact_rejects_standard_oci_config_media_type(self, mock_get, mock_get_auth_token):
        mock_get_auth_token.return_value = None

        manifest_response = Mock()
        manifest_response.status_code = 200
        manifest_response.json.return_value = {
            "config": {
                "mediaType": "application/vnd.oci.image.config.v1+json",
                "digest": "sha256:config123",
            },
            "layers": [
                {"mediaType": "application/vnd.microsoft.akri-connector.v1+json", "digest": "sha256:abc123"}
            ],
        }

        blob_response = Mock()
        blob_response.status_code = 200
        blob_response.headers = {"Content-Type": "application/json"}
        blob_response.content = b"{}"

        mock_get.side_effect = [manifest_response, blob_response]

        oci_client = get_oci_client()
        with pytest.raises(ValidationError) as exc_info:
            oci_client.fetch_first_layer(
                "mcr.microsoft.com/azureiotoperations/akri-connectors/rest-metadata:1.0.5",
                expected_config_media_type="application/vnd.microsoft.akri-connector.v1+json",
            )

        assert "config media type" in str(exc_info.value)

    def test_fetch_oci_artifact_invalid_reference(self):
        oci_client = get_oci_client()
        with pytest.raises(ValidationError) as exc_info:
            oci_client.fetch_first_layer("invalid-reference")
        assert "Invalid OCI reference" in str(exc_info.value)

    @patch("azext_edge.edge.util.oci_client.OciRegistryClient._get_anonymous_token")
    @patch("azext_edge.edge.util.oci_client.OciRegistryClient.get")
    def test_fetch_oci_artifact_manifest_not_found(self, mock_get, mock_get_auth_token):
        mock_get_auth_token.return_value = None

        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text.return_value = "Not Found"
        mock_get.return_value = mock_response

        oci_client = get_oci_client()
        with pytest.raises(ValidationError) as exc_info:
            oci_client.fetch_first_layer("mcr.microsoft.com/repo:tag")
        assert "Failed to fetch manifest" in str(exc_info.value)

    @patch("azext_edge.edge.providers.adr.validator.get_oci_client")
    @patch("azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client")
    def test_metadata_caching(self, mock_get_client, mock_get_oci_client):
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

        # Mock the OCI client's fetch_first_layer method
        mock_oci_client = Mock()
        mock_get_oci_client.return_value = mock_oci_client
        fetch_count = {"count": 0}

        # Create a valid metadata that passes schema validation
        sample_metadata = {
            "$schema": "https://json.schemastore.org/aio-connector-metadata-9.0-preview.json",
            "name": "Test Connector",
            "version": "1.0.0",
            "supportedArchitectures": ["linux/amd64"],
            "imageConfigurationSettings": {"imageName": "test", "tag": "1.0.0"},
            "inboundEndpoints": [
                {
                    "endpointType": "Microsoft.Http",
                    "fields": {"address": {"input": "required"}},
                    "datasets": {
                        "limits": {"minimum": 0},
                        "fields": {
                            "dataSource": {"input": "optional"},
                            "typeRef": {"input": "optional"},
                        },
                    },
                }
            ],
        }

        import json as json_module

        def counting_fetch(*args, **kwargs):
            fetch_count["count"] += 1
            mock_artifact = Mock()
            mock_artifact.content = json_module.dumps(sample_metadata).encode('utf-8')
            mock_artifact.content_type = "application/json"
            return mock_artifact

        mock_oci_client.fetch_first_layer.side_effect = counting_fetch

        validator1 = ConnectorMetadataValidator(
            cmd=cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Http",
            endpoint_version="1.0",
        )

        validator2 = ConnectorMetadataValidator(
            cmd=cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Http",
            endpoint_version="1.0",
        )

        assert fetch_count["count"] == 1
        assert validator1.metadata == validator2.metadata

    @patch("azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client")
    def test_no_matching_connector_template(self, mock_get_client, caplog):
        """Test that when no connector template matches, metadata is None and validation is skipped."""
        cmd = self._create_mock_cmd()
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(return_value=[])

        caplog.set_level(logging.INFO, logger="cli.azext_edge.edge.providers.adr.validator")

        validator = ConnectorMetadataValidator(
            cmd=cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Unknown",
            endpoint_version="1.0",
        )

        # Metadata should be None when no template is found
        assert validator.metadata is None

        # Validation methods should skip without error
        validator.validate_dataset({"name": "test", "datasetConfiguration": "{}"})
        validator.validate_datapoint({"name": "test", "dataPointConfiguration": "{}"})
        validator.validate_event({"name": "test", "eventConfiguration": "{}"})

        # Should have logged about no template found
        assert any("No connector template found" in record.message for record in caplog.records)

    @patch("azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client")
    def test_connector_template_missing_metadata_ref(self, mock_get_client, caplog):
        cmd = self._create_mock_cmd()
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.akri_connector_template = Mock()

        template = {
            "name": "broken-template",
            "properties": {
                "deviceInboundEndpointTypes": [{"endpointType": "Microsoft.Http", "version": "1.0"}],
            },
        }
        mock_client.akri_connector_template.list_by_instance_resource = Mock(return_value=[template])

        caplog.set_level(logging.INFO, logger="cli.azext_edge.edge.providers.adr.validator")

        validator = ConnectorMetadataValidator(
            cmd=cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Http",
            endpoint_version="1.0",
        )

        # Metadata should be None when connectorMetadataRef is missing and validation should skip.
        assert validator.metadata is None

        assert any("missing connectorMetadataRef" in record.message for record in caplog.records)


@pytest.mark.acr
@pytest.mark.integration
class TestConnectorMetadataValidatorACR:
    """Integration tests for ACR-based artifact fetching."""

    @pytest.fixture(autouse=True)
    def setup(self, settings):
        from ...settings import EnvironmentVariables

        settings.add_to_config(EnvironmentVariables.acr_name.value)
        settings.add_to_config(EnvironmentVariables.acr_artifact.value)

        self.acr_name = getattr(settings.env, EnvironmentVariables.acr_name.value, None)
        self.acr_artifact = getattr(settings.env, EnvironmentVariables.acr_artifact.value, None)

        ConnectorMetadataValidator._METADATA_CACHE.clear()

    def _skip_if_no_acr_config(self):
        if not self.acr_name or not self.acr_artifact:
            pytest.skip(
                "ACR integration tests require azext_edge_acr_name and "
                "azext_edge_acr_artifact environment variables"
            )

    def _get_acr_reference(self, tag: str = "1.0.0") -> str:
        return f"{self.acr_name}.azurecr.io/{self.acr_artifact}:{tag}"

    def _create_cmd_with_cli_context(self):
        try:
            from azure.cli.core import get_default_cli
            from azure.cli.core._profile import Profile

            az_cli = get_default_cli()
            profile = Profile(cli_ctx=az_cli)
            _, _, tenant_id = profile.get_login_credentials()

            cmd = Mock()
            cmd.cli_ctx = az_cli
            cmd.cli_ctx.data = cmd.cli_ctx.data or {}
            cmd.cli_ctx.data["tenant_id"] = tenant_id
            return cmd
        except Exception as e:
            pytest.skip(f"Could not initialize Azure CLI context: {e}")

    def test_fetch_oci_artifact_from_private_acr(self):
        self._skip_if_no_acr_config()

        acr_reference = self._get_acr_reference()
        cmd = self._create_cmd_with_cli_context()

        try:
            oci_client = get_oci_client()
            artifact_info = oci_client.fetch_first_layer(
                acr_reference,
                cmd=cmd,
                expected_config_media_type="application/vnd.microsoft.akri-connector.v1+json",
            )
            metadata = ConnectorMetadataValidator._extract_metadata_from_blob(
                artifact_info.content, artifact_info.content_type, acr_reference
            )
        except ValidationError as e:
            if "401" in str(e) or "403" in str(e) or "authentication" in str(e).lower():
                pytest.skip(f"ACR authentication failed - ensure 'az login' has access to {self.acr_name}: {e}")
            elif "404" in str(e) or "not found" in str(e).lower():
                pytest.skip(f"Artifact not found at {acr_reference} - push test artifact first: {e}")
            raise

        assert metadata is not None, "Metadata should not be None"
        assert isinstance(metadata, dict), "Metadata should be a dictionary"
        assert "name" in metadata or "inboundEndpoints" in metadata, (
            f"Metadata should have 'name' or 'inboundEndpoints' field, got: {list(metadata.keys())}"
        )

    def test_acr_token_exchange_flow(self):
        self._skip_if_no_acr_config()

        cmd = self._create_cmd_with_cli_context()

        try:
            oci_client = get_oci_client()
            token = oci_client._get_acr_access_token(
                cmd=cmd,
                registry=f"{self.acr_name}.azurecr.io",
                repository=self.acr_artifact
            )
        except Exception as e:
            if "az login" in str(e).lower() or "credential" in str(e).lower():
                pytest.skip(f"Azure CLI not logged in or no access to ACR: {e}")
            raise

        if token is None:
            pytest.skip("Could not obtain ACR token - tenant_id not available in CLI context")

        assert isinstance(token, str), "Token should be a string"
        assert len(token) > 0, "Token should not be empty"

    def test_fetch_artifact_nonexistent_tag(self):
        self._skip_if_no_acr_config()

        cmd = self._create_cmd_with_cli_context()
        nonexistent_ref = self._get_acr_reference(tag="nonexistent-tag-99999")

        oci_client = get_oci_client()
        with pytest.raises(ValidationError) as exc_info:
            oci_client.fetch_first_layer(nonexistent_ref, cmd=cmd)

        error_msg = str(exc_info.value).lower()
        assert "404" in error_msg or "not found" in error_msg or "manifest" in error_msg, (
            f"Expected 404/not found error, got: {exc_info.value}"
        )

    def test_fetch_artifact_invalid_acr_name(self, caplog):
        self._skip_if_no_acr_config()
        import requests
        from azure.core.exceptions import ServiceRequestError

        invalid_ref = f"nonexistent-acr-12345.azurecr.io/{self.acr_artifact}:1.0.0"

        caplog.set_level(logging.CRITICAL, logger="cli.azext_edge.edge.util.oci_client")

        oci_client = get_oci_client()
        with pytest.raises((ValidationError, requests.exceptions.ConnectionError, ServiceRequestError)) as exc_info:
            oci_client.fetch_first_layer(invalid_ref)

        error_msg = str(exc_info.value).lower()
        assert any(term in error_msg for term in ["failed", "resolve", "connection", "name"]), (
            f"Expected connection/DNS error, got: {exc_info.value}"
        )

    def test_acr_metadata_caching(self):
        self._skip_if_no_acr_config()

        acr_reference = self._get_acr_reference()
        cmd = self._create_cmd_with_cli_context()

        fetch_count = {"count": 0}
        oci_client = get_oci_client()
        original_fetch = oci_client.fetch_first_layer

        def counting_fetch(*args, **kwargs):
            fetch_count["count"] += 1
            return original_fetch(*args, **kwargs)

        with patch.object(oci_client, "fetch_first_layer", side_effect=counting_fetch):
            try:
                artifact_info = counting_fetch(
                    acr_reference,
                    cmd=cmd,
                    expected_config_media_type="application/vnd.microsoft.akri-connector.v1+json",
                )
                metadata1 = ConnectorMetadataValidator._extract_metadata_from_blob(
                    artifact_info.content, artifact_info.content_type, acr_reference
                )
            except ValidationError as e:
                if "404" in str(e) or "401" in str(e) or "403" in str(e):
                    pytest.skip(f"ACR access issue: {e}")
                raise

            cache_key = "test_endpoint:1.0"
            ConnectorMetadataValidator._METADATA_CACHE[cache_key] = metadata1
            metadata2 = ConnectorMetadataValidator._METADATA_CACHE.get(cache_key)

            assert metadata1 == metadata2, "Cached metadata should match original"
            assert fetch_count["count"] == 1, "Should only fetch once, then use cache"
