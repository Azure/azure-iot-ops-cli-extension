# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import unittest
from unittest.mock import patch, Mock
from azext_edge.edge.providers.adr.validator import ConnectorMetadataValidator
from azure.cli.core.azclierror import ValidationError

# Mock Metadata for REST
REST_METADATA = {
    "$schema": "https://raw.githubusercontent.com/Azure/iot-operations-sdks/refs/heads/main/doc/akri_connector/connector-metadata-schema.json",
    "name": "Azure IoT Operations connector for REST/HTTP",
    "version": "1.0.4",
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
                        "samplingIntervalInMilliseconds": {"type": "integer", "exclusiveMinimum": 0},
                        "transform": {"type": "string"},
                    },
                    "required": ["samplingIntervalInMilliseconds"],
                }
            },
        }
    ],
}

# Mock Metadata for ONVIF
ONVIF_METADATA = {
    "$schema": "https://raw.githubusercontent.com/Azure/iot-operations-sdks/refs/heads/main/doc/akri_connector/connector-metadata-schema.json",
    "name": "Azure IoT Operations connector for ONVIF",
    "version": "1.2.37",
    "inboundEndpoints": [
        {
            "endpointType": "Microsoft.Onvif",
            "additionalConfigurationSchema": {
                "type": "object",
                "properties": {"acceptInvalidHostnames": {"type": "boolean"}},
            },
            "eventGroups": {
                "events": {"eventConfigurationSchema": {"type": "object", "properties": {"filter": {"type": "string"}}}}
            },
        }
    ],
}


class TestConnectorMetadataValidator(unittest.TestCase):

    def setUp(self):
        # Patch _get_metadata to avoid network calls or complex lookup logic during init
        self.patcher = patch("azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator._get_metadata")
        self.mock_get_metadata = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_validate_dataset_rest_valid(self):
        self.mock_get_metadata.return_value = REST_METADATA
        mock_cmd = Mock()
        validator = ConnectorMetadataValidator(
            cmd=mock_cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Http",
            endpoint_version="1.0",
        )

        valid_config = {"samplingIntervalInMilliseconds": 1000, "transform": "http://example.com/transform.wasm"}

        # Should not raise exception
        validator.validate_dataset(valid_config)

    def test_validate_dataset_rest_invalid(self):
        self.mock_get_metadata.return_value = REST_METADATA
        mock_cmd = Mock()
        validator = ConnectorMetadataValidator(
            cmd=mock_cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Http",
            endpoint_version="1.0",
        )

        invalid_config = {"samplingIntervalInMilliseconds": -10}  # Invalid: exclusiveMinimum 0

        with self.assertRaises(ValidationError) as cm:
            validator.validate_dataset(invalid_config)
        self.assertIn("Dataset configuration is invalid", str(cm.exception))

    def test_validate_dataset_rest_missing_required(self):
        self.mock_get_metadata.return_value = REST_METADATA
        mock_cmd = Mock()
        validator = ConnectorMetadataValidator(
            cmd=mock_cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Http",
            endpoint_version="1.0",
        )

        invalid_config = {"transform": "http://example.com/transform.wasm"}
        # Missing samplingIntervalInMilliseconds

        with self.assertRaises(ValidationError) as cm:
            validator.validate_dataset(invalid_config)
        self.assertIn("Dataset configuration is invalid", str(cm.exception))

    def test_validate_event_onvif_valid(self):
        self.mock_get_metadata.return_value = ONVIF_METADATA
        mock_cmd = Mock()
        validator = ConnectorMetadataValidator(
            cmd=mock_cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Onvif",
            endpoint_version="1.0",
        )

        valid_config = {"filter": "Topic = 'motion'"}

        validator.validate_event(valid_config)

    def test_validate_event_onvif_invalid(self):
        self.mock_get_metadata.return_value = ONVIF_METADATA
        mock_cmd = Mock()
        validator = ConnectorMetadataValidator(
            cmd=mock_cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Onvif",
            endpoint_version="1.0",
        )

        invalid_config = {"filter": 123}  # Should be string

        with self.assertRaises(ValidationError):
            validator.validate_event(invalid_config)

    def test_get_schema_traversal(self):
        self.mock_get_metadata.return_value = ONVIF_METADATA
        mock_cmd = Mock()
        validator = ConnectorMetadataValidator(
            cmd=mock_cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Onvif",
            endpoint_version="1.0",
        )

        # Test additionalConfigurationSchema extraction
        schema = validator._get_schema("additionalConfigurationSchema")
        self.assertIsNotNone(schema)
        self.assertIn("acceptInvalidHostnames", schema["properties"])

    def test_no_schema_found(self):
        self.mock_get_metadata.return_value = REST_METADATA
        # Wrong endpoint type
        mock_cmd = Mock()
        validator = ConnectorMetadataValidator(
            cmd=mock_cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Mqtt",
            endpoint_version="1.0",
        )

        schema = validator._get_schema("datasetConfigurationSchema")
        self.assertIsNone(schema)


if __name__ == "__main__":
    unittest.main()
