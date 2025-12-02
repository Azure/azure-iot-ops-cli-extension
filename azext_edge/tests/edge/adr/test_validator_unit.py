# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import unittest
from unittest.mock import patch, Mock
from azext_edge.edge.providers.adr.validator import ConnectorMetadataValidator
from azure.cli.core.azclierror import ValidationError

# Mock Metadata for REST
REST_METADATA = {
    "$schema": (
        "https://raw.githubusercontent.com/Azure/iot-operations-sdks/refs/heads/main/"
        "doc/akri_connector/connector-metadata-schema.json"
    ),
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
                },
                "dataPointConfigurationSchema": {
                    "$schema": "http://json-schema.org/draft-07/schema#",
                    "title": "REST Datapoint Config Schema",
                    "type": "object",
                    "properties": {
                        "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"]},
                        "headers": {"type": "object"},
                    },
                    "required": ["method"],
                },
            },
        }
    ],
}

# Mock Metadata for ONVIF
ONVIF_METADATA = {
    "$schema": (
        "https://raw.githubusercontent.com/Azure/iot-operations-sdks/refs/heads/main/"
        "doc/akri_connector/connector-metadata-schema.json"
    ),
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

    # ========== Tests for Real-World Scenarios (Full Objects with JSON Strings) ==========

    def test_validate_datapoint_with_json_string(self):
        """Test validating a full datapoint object with dataPointConfiguration as JSON string."""
        self.mock_get_metadata.return_value = REST_METADATA
        mock_cmd = Mock()
        validator = ConnectorMetadataValidator(
            cmd=mock_cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Http",
            endpoint_version="1.0",
        )

        # This is how datapoints come from Azure - full object with JSON string
        datapoint = {
            "name": "temperature",
            "dataSource": "http://sensor/temp",
            "dataPointConfiguration": json.dumps({"method": "GET", "headers": {"Accept": "application/json"}}),
        }

        # Should not raise exception
        validator.validate_datapoint(datapoint)

    def test_validate_datapoint_with_invalid_json_string(self):
        """Test that invalid JSON in dataPointConfiguration is caught."""
        self.mock_get_metadata.return_value = REST_METADATA
        mock_cmd = Mock()
        validator = ConnectorMetadataValidator(
            cmd=mock_cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Http",
            endpoint_version="1.0",
        )

        datapoint = {
            "name": "bad-point",
            "dataSource": "http://sensor",
            "dataPointConfiguration": "{invalid json}",  # Invalid JSON
        }

        with self.assertRaises(ValidationError) as cm:
            validator.validate_datapoint(datapoint)
        self.assertIn("Invalid dataPointConfiguration JSON", str(cm.exception))

    def test_validate_datapoint_json_string_schema_violation(self):
        """Test that schema violations in parsed JSON config are caught."""
        self.mock_get_metadata.return_value = REST_METADATA
        mock_cmd = Mock()
        validator = ConnectorMetadataValidator(
            cmd=mock_cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Http",
            endpoint_version="1.0",
        )

        # Missing required "method" field in the configuration
        datapoint = {
            "name": "invalid-point",
            "dataSource": "http://sensor",
            "dataPointConfiguration": json.dumps({"headers": {"Accept": "application/json"}}),
        }

        with self.assertRaises(ValidationError) as cm:
            validator.validate_datapoint(datapoint)
        self.assertIn("configuration is invalid", str(cm.exception))

    def test_validate_event_with_json_string(self):
        """Test validating a full event object with eventConfiguration as JSON string."""
        self.mock_get_metadata.return_value = ONVIF_METADATA
        mock_cmd = Mock()
        validator = ConnectorMetadataValidator(
            cmd=mock_cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Onvif",
            endpoint_version="1.0",
        )

        # Full event object with JSON string configuration
        event = {
            "name": "motion-detected",
            "eventNotifier": "ns=2;s=MotionDetector",
            "eventConfiguration": json.dumps({"filter": "Topic = 'motion'"}),
        }

        validator.validate_event(event)

    def test_validate_datapoint_empty_configuration(self):
        """Test that empty dataPointConfiguration is handled gracefully."""
        self.mock_get_metadata.return_value = REST_METADATA
        mock_cmd = Mock()
        validator = ConnectorMetadataValidator(
            cmd=mock_cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Http",
            endpoint_version="1.0",
        )

        datapoint = {
            "name": "empty-point",
            "dataSource": "http://sensor",
            "dataPointConfiguration": "",  # Empty string
        }

        # Should not raise - empty config is skipped
        validator.validate_datapoint(datapoint)

    def test_validate_datapoint_missing_configuration(self):
        """Test that missing dataPointConfiguration is handled gracefully."""
        self.mock_get_metadata.return_value = REST_METADATA
        mock_cmd = Mock()
        validator = ConnectorMetadataValidator(
            cmd=mock_cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Http",
            endpoint_version="1.0",
        )

        datapoint = {
            "name": "no-config-point",
            "dataSource": "http://sensor",
            # No dataPointConfiguration field
        }

        # Should not raise - missing config is skipped
        validator.validate_datapoint(datapoint)

    def test_validate_datapoint_with_already_parsed_dict(self):
        """Test that already parsed configuration dict still works (backward compatibility)."""
        self.mock_get_metadata.return_value = REST_METADATA
        mock_cmd = Mock()
        validator = ConnectorMetadataValidator(
            cmd=mock_cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Http",
            endpoint_version="1.0",
        )

        # If dataPointConfiguration is already a dict (not common but possible)
        datapoint = {
            "name": "temp",
            "dataSource": "http://sensor",
            "dataPointConfiguration": {"method": "POST"},  # Already a dict
        }

        # Should work
        validator.validate_datapoint(datapoint)


if __name__ == "__main__":
    unittest.main()
