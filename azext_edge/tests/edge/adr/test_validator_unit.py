# coding=utf-8
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
        "https://raw.githubusercontent.com/Azure/iot-operations-sdks/"
        "refs/heads/main/doc/akri_connector/connector-metadata-schema.json"
    ),
    "name": "Azure IoT Operations connector for REST/HTTP",
    "description": (
        "Azure IoT Operations connector for periodically sampling a REST server "
        "and forwarding the collected data."
    ),
    "version": "1.0.4",
    "imageConfigurationSettings": {
        "imageName": "azureiotoperations/akri-connectors/rest",
        "tag": "1.0.4"
    },
    "aioMetadata": {
        "aioMinVersion": "1.2.37"
    },
    "supportedArchitectures": [
        "linux/amd64"
    ],
    "sourceCode": {
        "language": "rust",
        "languageVersion": "1.87",
        "sdks": {
            "protocolPackageVersion": "0.12.0",
            "servicesPackageVersion": "0.13.1",
            "connectorPackageVersion": "0.5.2"
        }
    },
    "endpointsEnabledByDefault": True,
    "inboundEndpoints": [
        {
            "endpointType": "Microsoft.Http",
            "version": "1.0",
            "supportedAuthenticationTypes": ["usernamePassword", "anonymous", "x509Credentials"],
            "description": "An HTTP(S) REST endpoint",
            "assetsEnabledByDefault": True,
            "fields": {
                "address": {
                    "input": "required",
                    "exampleValue": "https://www.contoso.com:8080",
                    "regex": [r"^https?://"],
                    "description": (
                        "The address of the HTTP server to connect with in the format: "
                        "<https address>:<port>. HTTP can also be used but is intended only "
                        "for testing and not recommended for security purposes. "
                        "The provided HTTP URL should not include a trailing '\\' or '/' character."
                    )
                }
            },
            "datasets": {
                "limits": {
                    "minimum": 0
                },
                "datasetConfigurationSchema": {
                    "$schema": "http://json-schema.org/draft-07/schema#",
                    "title": "REST Dataset Config Schema",
                    "description": (
                        "The JSON schema for both the default dataset configuration field "
                        "on an asset and dataset-specific configuration fields"
                    ),
                    "type": "object",
                    "properties": {
                        "samplingIntervalInMilliseconds": {
                            "description": "How frequently to sample each dataset in milliseconds",
                            "type": "integer",
                            "exclusiveMinimum": 0,
                            "maximum": 18446744073709551615
                        },
                        "transform": {
                            "description": "WASM graph URL used to transform incoming data",
                            "type": "string"
                        }
                    }
                },
                "fields": {
                    "dataSource": {
                        "input": "required",
                        "exampleValue": "some/relative/http/path",
                        "description": "The relative HTTP path to retrieve data from"
                    },
                    "typeRef": {
                        "input": "unsupported"
                    }
                },
                "destinations": {
                    "supportedDestinations": ["Mqtt", "BrokerStateStore"]
                }
            }
        }
    ]
}

# Mock Metadata for Datapoint Testing (Generic)
DATAPOINT_METADATA = {
    "inboundEndpoints": [
        {
            "endpointType": "Microsoft.Test",
            "version": "1.0",
            "datasets": {
                "dataPoints": {
                    "dataPointConfigurationSchema": {
                        "$schema": "http://json-schema.org/draft-07/schema#",
                        "title": "Test Datapoint Config Schema",
                        "type": "object",
                        "properties": {
                            "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"]},
                            "headers": {"type": "object"},
                        },
                        "required": ["method"],
                    }
                }
            }
        }
    ]
}

# Mock Metadata for ONVIF
ONVIF_METADATA = {
    "$schema": (
        "https://raw.githubusercontent.com/Azure/iot-operations-sdks/"
        "refs/heads/main/doc/akri_connector/connector-metadata-schema.json"
    ),
    "name": "Azure IoT Operations connector for ONVIF",
    "description": "Azure IoT Operations connector for ONVIF",
    "version": "1.2.37",
    "isPreview": False,
    "maintainer": "aio-connectors@microsoft.com",
    "vendor": "Microsoft",
    "imageConfigurationSettings": {
        "imageName": "azureiotoperations/akri-connectors/onvif",
        "tag": "1.2.37"
    },
    "supportedArchitectures": [
        "linux/amd64"
    ],
    "aioMetadata": {
        "aioMinVersion": "1.2.80"
    },
    "endpointsEnabledByDefault": True,
    "recommendedAllocationPolicy": "bucketized",
    "inboundEndpoints": [
        {
            "endpointType": "Microsoft.Onvif",
            "description": "Connect to an ONVIF device.",
            "supportedAuthenticationTypes": [
                "anonymous",
                "usernamePassword"
            ],
            "assetsEnabledByDefault": True,
            "fields": {
                "address": {
                    "input": "required",
                    "description": "The endpoint URL of the ONVIF device to connect to.",
                    "regex": [
                        "^(http|https)://.+$"
                    ],
                    "exampleValue": "http://onvif-rtsp-simulator:8000/onvif/device_service"
                }
            },
            "additionalConfigurationSchema": {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "$id": (
                    "https://azure-iot-operations/schemas/device/"
                    "inboundendpoints/additionalconfiguration/onvif.json"
                ),
                "title": "AIO ONVIF Device inboundEndpoint additionalConfiguration schema",
                "description": (
                    "Schema of a Device additional configuration for endpointType Microsoft.ONVIF"
                ),
                "type": "object",
                "properties": {
                    "acceptInvalidHostnames": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Whether to accept invalid hostnames in certificates "
                            "for the ONVIF connection, defaults to false"
                        )
                    },
                    "acceptInvalidCertificates": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Whether to accept invalid certificates for the ONVIF connection, "
                            "defaults to false"
                        )
                    },
                    "fallbackToUsernameTokenAuth": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Whether to fallback to UsernameToken authentication if Digest "
                            "authentication fails for the ONVIF connection, defaults to false"
                        )
                    }
                },
                "required": []
            },
            "eventGroups": {
                "limits": {
                    "minimum": 0
                },
                "fields": {
                    "dataSource": {
                        "input": "optional"
                    },
                    "typeRef": {
                        "input": "optional"
                    }
                },
                "eventGroupConfigurationSchema": {},
                "events": {
                    "limits": {
                        "minimum": 0
                    },
                    "fields": {
                        "dataSource": {
                            "input": "optional"
                        },
                        "typeRef": {
                            "input": "optional"
                        }
                    },
                    "eventConfigurationSchema": {
                        "type": "object",
                        "properties": {
                            "filter": {
                                "type": "string"
                            }
                        }
                    },
                    "destinations": {
                        "supportedDestinations": [
                            "Mqtt"
                        ]
                    }
                }
            },
            "managementGroups": {
                "limits": {
                    "minimum": 0
                },
                "fields": {
                    "typeRef": {
                        "input": "optional"
                    }
                },
                "managementGroupConfigurationSchema": {},
                "managementGroupActions": {
                    "limits": {
                        "minimum": 0
                    },
                    "fields": {
                        "targetUri": {
                            "input": "required"
                        },
                        "typeRef": {
                            "input": "optional"
                        }
                    },
                    "actionConfigurationSchema": {}
                }
            }
        }
    ]
}


class TestConnectorMetadataValidator(unittest.TestCase):

    def setUp(self):
        # Patch _get_metadata to avoid network calls or complex lookup logic during init
        self.patcher = patch("azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator._get_metadata")
        self.mock_get_metadata = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

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
        self.mock_get_metadata.return_value = ONVIF_METADATA
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
        self.mock_get_metadata.return_value = DATAPOINT_METADATA
        mock_cmd = Mock()
        validator = ConnectorMetadataValidator(
            cmd=mock_cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Test",
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
        self.mock_get_metadata.return_value = DATAPOINT_METADATA
        mock_cmd = Mock()
        validator = ConnectorMetadataValidator(
            cmd=mock_cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Test",
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
        self.mock_get_metadata.return_value = DATAPOINT_METADATA
        mock_cmd = Mock()
        validator = ConnectorMetadataValidator(
            cmd=mock_cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Test",
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
        self.mock_get_metadata.return_value = DATAPOINT_METADATA
        mock_cmd = Mock()
        validator = ConnectorMetadataValidator(
            cmd=mock_cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Test",
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
        self.mock_get_metadata.return_value = DATAPOINT_METADATA
        mock_cmd = Mock()
        validator = ConnectorMetadataValidator(
            cmd=mock_cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Test",
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
        self.mock_get_metadata.return_value = DATAPOINT_METADATA
        mock_cmd = Mock()
        validator = ConnectorMetadataValidator(
            cmd=mock_cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Test",
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
