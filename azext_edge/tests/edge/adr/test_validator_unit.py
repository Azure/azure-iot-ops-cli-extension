# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import copy
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

    def test_validate_event_autofill_destination_single_supported(self):
        self.mock_get_metadata.return_value = ONVIF_METADATA
        mock_cmd = Mock()
        validator = ConnectorMetadataValidator(
            cmd=mock_cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Onvif",
            endpoint_version="1.0",
        )

        config = {"filter": "Topic = 'motion'"}

        # Expect destination to be auto-filled to the sole supported option (Mqtt).
        validator.validate_event(config)
        self.assertEqual(config.get("destination"), "Mqtt")

    def test_validate_event_destination_not_supported(self):
        self.mock_get_metadata.return_value = ONVIF_METADATA
        mock_cmd = Mock()
        validator = ConnectorMetadataValidator(
            cmd=mock_cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Onvif",
            endpoint_version="1.0",
        )

        with self.assertRaises(ValidationError):
            validator.validate_event({"filter": "Topic = 'motion'", "destination": "Storage"})

    def test_validate_event_autofill_destination_prefers_mqtt_when_multiple(self):
        metadata = copy.deepcopy(ONVIF_METADATA)
        metadata["inboundEndpoints"][0]["eventGroups"]["events"]["destinations"]["supportedDestinations"] = [
            "Storage",
            "Mqtt",
        ]
        self.mock_get_metadata.return_value = metadata
        mock_cmd = Mock()
        validator = ConnectorMetadataValidator(
            cmd=mock_cmd,
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Onvif",
            endpoint_version="1.0",
        )

        config = {"filter": "Topic = 'motion'"}

        # When multiple supported destinations exist, prefer Mqtt if available.
        validator.validate_event(config)
        self.assertEqual(config.get("destination"), "Mqtt")

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

        with self.assertRaises(ValidationError):
            validator._get_schema("datasetConfigurationSchema")

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

        with self.assertRaises(ValidationError):
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

        with self.assertRaises(ValidationError):
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


class TestConnectorMetadataValidatorFromAsset(unittest.TestCase):
    """Unit tests for the from_asset() factory method."""

    def setUp(self):
        # Patch both _get_metadata and get_registry_mgmt_client
        self.metadata_patcher = patch(
            "azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator._get_metadata"
        )
        # Patch at the source module where it's imported from inside from_asset()
        self.registry_client_patcher = patch(
            "azext_edge.edge.util.az_client.get_registry_mgmt_client"
        )
        self.mock_get_metadata = self.metadata_patcher.start()
        self.mock_get_registry_client = self.registry_client_patcher.start()

        # Default metadata return
        self.mock_get_metadata.return_value = ONVIF_METADATA

    def tearDown(self):
        self.metadata_patcher.stop()
        self.registry_client_patcher.stop()

    def _create_mock_cmd(self):
        """Helper to create a mock cmd object."""
        cmd = Mock()
        cmd.cli_ctx = Mock()
        cmd.cli_ctx.cloud = Mock()
        cmd.cli_ctx.cloud.endpoints = Mock()
        cmd.cli_ctx.cloud.endpoints.resource_manager = "https://management.azure.com"
        cmd.cli_ctx.data = {"subscription_id": "test-sub-id"}
        return cmd

    def _create_valid_asset(self):
        """Helper to create a valid asset dictionary."""
        return {
            "id": (
                "/subscriptions/test-sub-id/resourceGroups/test-rg/providers/"
                "Microsoft.DeviceRegistry/namespaces/test-namespace/assets/test-asset"
            ),
            "name": "test-asset",
            "deviceRef": {
                "deviceName": "test-device",
                "endpointName": "test-endpoint"
            }
        }

    def _create_mock_device(self, endpoint_type="Microsoft.Onvif", endpoint_version=None):
        """Helper to create a mock device response."""
        endpoint_config = {"endpointType": endpoint_type}
        if endpoint_version:
            endpoint_config["version"] = endpoint_version
        return {
            "properties": {
                "endpoints": {
                    "inbound": {
                        "test-endpoint": endpoint_config
                    }
                }
            }
        }

    def test_from_asset_valid(self):
        """Test from_asset with a valid asset creates a validator correctly."""
        cmd = self._create_mock_cmd()
        asset = self._create_valid_asset()

        # Setup mock registry client
        mock_client = Mock()
        mock_client.namespace_devices.get.return_value = self._create_mock_device()
        self.mock_get_registry_client.return_value = mock_client

        # Create validator from asset
        validator = ConnectorMetadataValidator.from_asset(
            cmd=cmd,
            asset=asset,
            instance_name="test-instance",
            instance_resource_group="test-rg"
        )

        # Verify validator was created with correct parameters
        self.assertEqual(validator.endpoint_type, "Microsoft.Onvif")
        self.assertIsNone(validator.endpoint_version)
        self.assertEqual(validator.instance_name, "test-instance")
        self.assertEqual(validator.resource_group_name, "test-rg")

        # Verify registry client was called correctly
        mock_client.namespace_devices.get.assert_called_once_with(
            resource_group_name="test-rg",
            namespace_name="test-namespace",
            device_name="test-device"
        )

    def test_from_asset_with_version(self):
        """Test from_asset correctly extracts endpoint version."""
        cmd = self._create_mock_cmd()
        asset = self._create_valid_asset()

        mock_client = Mock()
        mock_client.namespace_devices.get.return_value = self._create_mock_device(
            endpoint_type="Microsoft.Http",
            endpoint_version="1.0"
        )
        self.mock_get_registry_client.return_value = mock_client

        validator = ConnectorMetadataValidator.from_asset(
            cmd=cmd,
            asset=asset,
            instance_name="test-instance",
            instance_resource_group="test-rg"
        )

        self.assertEqual(validator.endpoint_type, "Microsoft.Http")
        self.assertEqual(validator.endpoint_version, "1.0")

    def test_from_asset_missing_asset_id(self):
        """Test from_asset raises ValidationError when asset has no ID."""
        cmd = self._create_mock_cmd()
        asset = {
            "name": "test-asset",
            "deviceRef": {"deviceName": "dev", "endpointName": "ep"}
        }  # No "id" field

        with self.assertRaises(ValidationError) as cm:
            ConnectorMetadataValidator.from_asset(
                cmd=cmd,
                asset=asset,
                instance_name="test-instance",
                instance_resource_group="test-rg"
            )
        self.assertIn("does not have an ID", str(cm.exception))

    def test_from_asset_invalid_asset_id_format(self):
        """Test from_asset raises ValidationError for malformed asset ID."""
        cmd = self._create_mock_cmd()
        asset = {
            "id": "/subscriptions/sub/resourceGroups/rg/providers/SomeOther/resource",
            "name": "test-asset",
            "deviceRef": {"deviceName": "dev", "endpointName": "ep"}
        }

        with self.assertRaises(ValidationError) as cm:
            ConnectorMetadataValidator.from_asset(
                cmd=cmd,
                asset=asset,
                instance_name="test-instance",
                instance_resource_group="test-rg"
            )
        self.assertIn("Could not extract namespace", str(cm.exception))

    def test_from_asset_missing_device_ref(self):
        """Test from_asset raises ValidationError when deviceRef is missing."""
        cmd = self._create_mock_cmd()
        asset = {
            "id": (
                "/subscriptions/test-sub-id/resourceGroups/test-rg/providers/"
                "Microsoft.DeviceRegistry/namespaces/test-namespace/assets/test-asset"
            ),
            "name": "test-asset"
            # No deviceRef
        }

        with self.assertRaises(ValidationError) as cm:
            ConnectorMetadataValidator.from_asset(
                cmd=cmd,
                asset=asset,
                instance_name="test-instance",
                instance_resource_group="test-rg"
            )
        self.assertIn("must reference a device and endpoint", str(cm.exception))

    def test_from_asset_missing_device_name(self):
        """Test from_asset raises ValidationError when deviceName is missing."""
        cmd = self._create_mock_cmd()
        asset = {
            "id": (
                "/subscriptions/test-sub-id/resourceGroups/test-rg/providers/"
                "Microsoft.DeviceRegistry/namespaces/test-namespace/assets/test-asset"
            ),
            "name": "test-asset",
            "deviceRef": {"endpointName": "ep"}  # Missing deviceName
        }

        with self.assertRaises(ValidationError) as cm:
            ConnectorMetadataValidator.from_asset(
                cmd=cmd,
                asset=asset,
                instance_name="test-instance",
                instance_resource_group="test-rg"
            )
        self.assertIn("must reference a device and endpoint", str(cm.exception))

    def test_from_asset_missing_endpoint_name(self):
        """Test from_asset raises ValidationError when endpointName is missing."""
        cmd = self._create_mock_cmd()
        asset = {
            "id": (
                "/subscriptions/test-sub-id/resourceGroups/test-rg/providers/"
                "Microsoft.DeviceRegistry/namespaces/test-namespace/assets/test-asset"
            ),
            "name": "test-asset",
            "deviceRef": {"deviceName": "dev"}  # Missing endpointName
        }

        with self.assertRaises(ValidationError) as cm:
            ConnectorMetadataValidator.from_asset(
                cmd=cmd,
                asset=asset,
                instance_name="test-instance",
                instance_resource_group="test-rg"
            )
        self.assertIn("must reference a device and endpoint", str(cm.exception))

    def test_from_asset_endpoint_not_found_on_device(self):
        """Test from_asset raises ValidationError when endpoint doesn't exist on device."""
        cmd = self._create_mock_cmd()
        asset = self._create_valid_asset()

        # Device has no matching endpoint
        mock_client = Mock()
        mock_client.namespace_devices.get.return_value = {
            "properties": {
                "endpoints": {
                    "inbound": {
                        "other-endpoint": {"endpointType": "Microsoft.Onvif"}
                    }
                }
            }
        }
        self.mock_get_registry_client.return_value = mock_client

        with self.assertRaises(ValidationError) as cm:
            ConnectorMetadataValidator.from_asset(
                cmd=cmd,
                asset=asset,
                instance_name="test-instance",
                instance_resource_group="test-rg"
            )
        self.assertIn("does not have inbound endpoint", str(cm.exception))

    def test_from_asset_endpoint_missing_type(self):
        """Test from_asset raises ValidationError when endpoint has no endpointType."""
        cmd = self._create_mock_cmd()
        asset = self._create_valid_asset()

        # Endpoint exists but has no endpointType
        mock_client = Mock()
        mock_client.namespace_devices.get.return_value = {
            "properties": {
                "endpoints": {
                    "inbound": {
                        "test-endpoint": {"version": "1.0"}  # No endpointType
                    }
                }
            }
        }
        self.mock_get_registry_client.return_value = mock_client

        with self.assertRaises(ValidationError) as cm:
            ConnectorMetadataValidator.from_asset(
                cmd=cmd,
                asset=asset,
                instance_name="test-instance",
                instance_resource_group="test-rg"
            )
        self.assertIn("does not have endpointType specified", str(cm.exception))

    def test_from_asset_device_ref_in_properties(self):
        """Test from_asset handles deviceRef nested in properties (alternative format)."""
        cmd = self._create_mock_cmd()
        asset = {
            "id": (
                "/subscriptions/test-sub-id/resourceGroups/test-rg/providers/"
                "Microsoft.DeviceRegistry/namespaces/test-namespace/assets/test-asset"
            ),
            "name": "test-asset",
            "properties": {
                "deviceRef": {
                    "deviceName": "test-device",
                    "endpointName": "test-endpoint"
                }
            }
        }

        mock_client = Mock()
        mock_client.namespace_devices.get.return_value = self._create_mock_device()
        self.mock_get_registry_client.return_value = mock_client

        validator = ConnectorMetadataValidator.from_asset(
            cmd=cmd,
            asset=asset,
            instance_name="test-instance",
            instance_resource_group="test-rg"
        )

        self.assertEqual(validator.endpoint_type, "Microsoft.Onvif")


class TestValidateDestination(unittest.TestCase):
    """Unit tests for _validate_destination() method."""

    def setUp(self):
        self.patcher = patch(
            "azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator._get_metadata"
        )
        self.mock_get_metadata = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def _create_metadata_with_destinations(
        self, supported_destinations=None, default_destination=None
    ):
        """Create metadata with configurable destination settings for events."""
        metadata = copy.deepcopy(ONVIF_METADATA)
        destinations = {}
        if supported_destinations is not None:
            destinations["supportedDestinations"] = supported_destinations
        if default_destination is not None:
            destinations["defaultDestination"] = default_destination
        metadata["inboundEndpoints"][0]["eventGroups"]["events"]["destinations"] = destinations
        return metadata

    def test_validate_destination_uses_default_destination(self):
        """Test that defaultDestination from metadata is used when no destination specified."""
        metadata = self._create_metadata_with_destinations(
            supported_destinations=["Mqtt", "Storage", "BrokerStateStore"],
            default_destination="Storage"
        )
        self.mock_get_metadata.return_value = metadata

        validator = ConnectorMetadataValidator(
            cmd=Mock(),
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Onvif",
            endpoint_version="1.0",
        )

        config = {"filter": "Topic = 'motion'"}  # No destination specified
        validator.validate_event(config)

        # Should use defaultDestination from metadata, not auto-select Mqtt
        self.assertEqual(config.get("destination"), "Storage")

    def test_validate_destination_fallback_first_when_mqtt_absent(self):
        """Test that first supported destination is used when Mqtt is not available."""
        metadata = self._create_metadata_with_destinations(
            supported_destinations=["Storage", "BrokerStateStore"]  # No Mqtt
        )
        self.mock_get_metadata.return_value = metadata

        validator = ConnectorMetadataValidator(
            cmd=Mock(),
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Onvif",
            endpoint_version="1.0",
        )

        config = {"filter": "Topic = 'motion'"}  # No destination specified
        validator.validate_event(config)

        # Should fall back to first supported destination
        self.assertEqual(config.get("destination"), "Storage")

    def test_validate_destination_explicit_overrides_default(self):
        """Test that explicit destination in config overrides defaultDestination."""
        metadata = self._create_metadata_with_destinations(
            supported_destinations=["Mqtt", "Storage"],
            default_destination="Storage"
        )
        self.mock_get_metadata.return_value = metadata

        validator = ConnectorMetadataValidator(
            cmd=Mock(),
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Onvif",
            endpoint_version="1.0",
        )

        config = {"filter": "Topic = 'motion'", "destination": "Mqtt"}
        validator.validate_event(config)

        # Should keep explicit value, not override with default
        self.assertEqual(config.get("destination"), "Mqtt")

    def test_validate_destination_no_destinations_defined(self):
        """Test that no destination is set when metadata has no destination config."""
        metadata = copy.deepcopy(ONVIF_METADATA)
        # Remove destinations entirely
        metadata["inboundEndpoints"][0]["eventGroups"]["events"]["destinations"] = {}
        self.mock_get_metadata.return_value = metadata

        validator = ConnectorMetadataValidator(
            cmd=Mock(),
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Onvif",
            endpoint_version="1.0",
        )

        config = {"filter": "Topic = 'motion'"}
        validator.validate_event(config)

        # Should not add destination if none defined in metadata
        self.assertIsNone(config.get("destination"))


class TestGetEndpointMetadata(unittest.TestCase):
    """Unit tests for _get_endpoint_metadata() method."""

    def setUp(self):
        self.patcher = patch(
            "azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator._get_metadata"
        )
        self.mock_get_metadata = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_version_relaxed_matching_metadata_omits_version(self):
        """Test that endpoint matches when metadata omits version but caller provides one."""
        # Create metadata where endpoint has no version
        metadata = copy.deepcopy(ONVIF_METADATA)
        # Ensure the endpoint has no version field
        if "version" in metadata["inboundEndpoints"][0]:
            del metadata["inboundEndpoints"][0]["version"]
        self.mock_get_metadata.return_value = metadata

        validator = ConnectorMetadataValidator(
            cmd=Mock(),
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Onvif",
            endpoint_version="2.0",  # Caller provides a version
        )

        # Should not raise - relaxed matching allows this
        endpoint = validator._get_endpoint_metadata()
        self.assertIsNotNone(endpoint)
        self.assertEqual(endpoint.get("endpointType"), "Microsoft.Onvif")

    def test_version_relaxed_matching_caller_omits_version(self):
        """Test that endpoint matches when caller omits version but metadata has one."""
        metadata = copy.deepcopy(ONVIF_METADATA)
        metadata["inboundEndpoints"][0]["version"] = "1.0"
        self.mock_get_metadata.return_value = metadata

        validator = ConnectorMetadataValidator(
            cmd=Mock(),
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Onvif",
            endpoint_version=None,  # Caller doesn't specify version
        )

        # Should not raise - matches because caller didn't specify a version
        endpoint = validator._get_endpoint_metadata()
        self.assertIsNotNone(endpoint)

    def test_version_strict_matching_when_both_specified(self):
        """Test that version mismatch fails when both sides specify versions."""
        metadata = copy.deepcopy(ONVIF_METADATA)
        metadata["inboundEndpoints"][0]["version"] = "1.0"
        self.mock_get_metadata.return_value = metadata

        validator = ConnectorMetadataValidator(
            cmd=Mock(),
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Onvif",
            endpoint_version="2.0",  # Different version
        )

        with self.assertRaises(ValidationError) as cm:
            validator._get_endpoint_metadata()
        self.assertIn("Connector metadata unavailable", str(cm.exception))

    def test_multiple_endpoints_selects_correct_type(self):
        """Test that correct endpoint is selected when metadata has multiple endpoints."""
        metadata = {
            "inboundEndpoints": [
                {
                    "endpointType": "Microsoft.Http",
                    "version": "1.0",
                    "datasets": {"datasetConfigurationSchema": {"type": "object"}},
                },
                {
                    "endpointType": "Microsoft.Onvif",
                    "version": "1.0",
                    "eventGroups": {"events": {"eventConfigurationSchema": {"type": "object"}}},
                },
                {
                    "endpointType": "Microsoft.OpcUa",
                    "version": "1.0",
                    "datasets": {"datasetConfigurationSchema": {"type": "object"}},
                },
            ]
        }
        self.mock_get_metadata.return_value = metadata

        validator = ConnectorMetadataValidator(
            cmd=Mock(),
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Onvif",
            endpoint_version="1.0",
        )

        endpoint = validator._get_endpoint_metadata()
        self.assertEqual(endpoint.get("endpointType"), "Microsoft.Onvif")

    def test_multiple_endpoints_same_type_different_versions(self):
        """Test that correct version is selected when same endpoint type has multiple versions."""
        metadata = {
            "inboundEndpoints": [
                {
                    "endpointType": "Microsoft.Http",
                    "version": "1.0",
                    "datasets": {"datasetConfigurationSchema": {"type": "object", "title": "v1.0"}},
                },
                {
                    "endpointType": "Microsoft.Http",
                    "version": "2.0",
                    "datasets": {"datasetConfigurationSchema": {"type": "object", "title": "v2.0"}},
                },
            ]
        }
        self.mock_get_metadata.return_value = metadata

        validator = ConnectorMetadataValidator(
            cmd=Mock(),
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Http",
            endpoint_version="2.0",
        )

        endpoint = validator._get_endpoint_metadata()
        self.assertEqual(endpoint.get("version"), "2.0")
        self.assertEqual(endpoint["datasets"]["datasetConfigurationSchema"]["title"], "v2.0")

    def test_endpoint_type_case_insensitive(self):
        """Test that endpoint type matching is case-insensitive."""
        self.mock_get_metadata.return_value = ONVIF_METADATA

        validator = ConnectorMetadataValidator(
            cmd=Mock(),
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="microsoft.onvif",  # lowercase
            endpoint_version=None,
        )

        endpoint = validator._get_endpoint_metadata()
        self.assertIsNotNone(endpoint)
        self.assertEqual(endpoint.get("endpointType"), "Microsoft.Onvif")

    def test_no_matching_endpoint_raises_error(self):
        """Test that ValidationError is raised when no endpoint matches."""
        self.mock_get_metadata.return_value = ONVIF_METADATA

        validator = ConnectorMetadataValidator(
            cmd=Mock(),
            resource_group_name="test-rg",
            instance_name="test-instance",
            endpoint_type="Microsoft.Unknown",
            endpoint_version="1.0",
        )

        with self.assertRaises(ValidationError) as cm:
            validator._get_endpoint_metadata()
        self.assertIn("Connector metadata unavailable", str(cm.exception))
        self.assertIn("Microsoft.Unknown", str(cm.exception))


class TestMakeCacheKey(unittest.TestCase):
    """Unit tests for _make_metadata_cache_key() method."""

    def setUp(self):
        self.patcher = patch(
            "azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator._get_metadata"
        )
        self.mock_get_metadata = self.patcher.start()
        self.mock_get_metadata.return_value = ONVIF_METADATA

    def tearDown(self):
        self.patcher.stop()

    def _create_mock_cmd(self, subscription_id="sub-123"):
        cmd = Mock()
        cmd.cli_ctx = Mock()
        cmd.cli_ctx.data = {"subscription_id": subscription_id}
        return cmd

    def test_cache_key_uniqueness_different_endpoints(self):
        """Test that different endpoint types produce different cache keys."""
        cmd = self._create_mock_cmd()

        validator1 = ConnectorMetadataValidator(
            cmd=cmd,
            resource_group_name="rg",
            instance_name="instance",
            endpoint_type="Microsoft.Onvif",
            endpoint_version="1.0",
        )

        validator2 = ConnectorMetadataValidator(
            cmd=cmd,
            resource_group_name="rg",
            instance_name="instance",
            endpoint_type="Microsoft.Http",
            endpoint_version="1.0",
        )

        key1 = validator1._make_metadata_cache_key()
        key2 = validator2._make_metadata_cache_key()

        self.assertNotEqual(key1, key2)

    def test_cache_key_uniqueness_different_versions(self):
        """Test that different endpoint versions produce different cache keys."""
        cmd = self._create_mock_cmd()

        validator1 = ConnectorMetadataValidator(
            cmd=cmd,
            resource_group_name="rg",
            instance_name="instance",
            endpoint_type="Microsoft.Http",
            endpoint_version="1.0",
        )

        validator2 = ConnectorMetadataValidator(
            cmd=cmd,
            resource_group_name="rg",
            instance_name="instance",
            endpoint_type="Microsoft.Http",
            endpoint_version="2.0",
        )

        key1 = validator1._make_metadata_cache_key()
        key2 = validator2._make_metadata_cache_key()

        self.assertNotEqual(key1, key2)

    def test_cache_key_same_params_same_key(self):
        """Test that same parameters produce identical cache keys."""
        cmd = self._create_mock_cmd()

        validator1 = ConnectorMetadataValidator(
            cmd=cmd,
            resource_group_name="rg",
            instance_name="instance",
            endpoint_type="Microsoft.Onvif",
            endpoint_version="1.0",
        )

        validator2 = ConnectorMetadataValidator(
            cmd=cmd,
            resource_group_name="rg",
            instance_name="instance",
            endpoint_type="Microsoft.Onvif",
            endpoint_version="1.0",
        )

        key1 = validator1._make_metadata_cache_key()
        key2 = validator2._make_metadata_cache_key()

        self.assertEqual(key1, key2)


if __name__ == "__main__":
    unittest.main()
