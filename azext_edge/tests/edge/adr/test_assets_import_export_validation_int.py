# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""
Integration tests for asset dataset/datapoint/event import/export with validation.
Tests the complete flow: File → Import → Validate → Azure Resource
"""

import pytest
import json
import tempfile
import os
from unittest.mock import patch, Mock
from azext_edge.edge.providers.adr.assets import Assets
from azext_edge.edge.commands_assets import (
    import_asset_data_points,
    export_asset_data_points,
    import_asset_events,
    export_asset_events
)

pytestmark = pytest.mark.integration


# Sample metadata for REST HTTP connector
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
                            "exclusiveMinimum": 0
                        },
                        "transform": {
                            "type": "string"
                        }
                    },
                    "required": ["samplingIntervalInMilliseconds"]
                },
                "dataPointConfigurationSchema": {
                    "$schema": "http://json-schema.org/draft-07/schema#",
                    "title": "REST Datapoint Config Schema",
                    "type": "object",
                    "properties": {
                        "method": {
                            "type": "string",
                            "enum": ["GET", "POST", "PUT", "DELETE"]
                        },
                        "headers": {
                            "type": "object"
                        }
                    },
                    "required": ["method"]
                }
            }
        }
    ]
}

# Sample metadata for ONVIF connector
ONVIF_METADATA = {
    "$schema": "https://raw.githubusercontent.com/Azure/iot-operations-sdks/refs/heads/main/doc/akri_connector/connector-metadata-schema.json",
    "name": "Azure IoT Operations connector for ONVIF",
    "version": "1.2.37",
    "inboundEndpoints": [
        {
            "endpointType": "Microsoft.Onvif",
            "eventGroups": {
                "events": {
                    "eventConfigurationSchema": {
                        "$schema": "http://json-schema.org/draft-07/schema#",
                        "type": "object",
                        "properties": {
                            "filter": {
                                "type": "string"
                            },
                            "priority": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 10
                            }
                        },
                        "required": ["filter"]
                    }
                }
            }
        }
    ]
}


class TestAssetDataPointImportWithValidation:
    """Test import_asset_data_points with validation."""

    def _create_mock_cmd(self):
        """Helper to create a mock cmd object."""
        cmd = Mock()
        cmd.cli_ctx = Mock()
        cmd.cli_ctx.cloud = Mock()
        cmd.cli_ctx.cloud.endpoints = Mock()
        cmd.cli_ctx.cloud.endpoints.resource_manager = "https://management.azure.com"
        cmd.cli_ctx.data = {"subscription_id": "eab4c10d-b020-4cb2-8959-d53cf2df388d"}
        return cmd

    def _create_mock_asset(self, endpoint_type="Microsoft.Http"):
        """Helper to create a mock asset with all required fields for validation."""
        return {
            "id": "/subscriptions/test-sub/resourceGroups/test-rg/providers/Microsoft.DeviceRegistry/assets/test-asset",
            "name": "test-asset",
            "type": "Microsoft.DeviceRegistry/assets",
            "extendedLocation": {
                "type": "CustomLocation",
                "name": "/subscriptions/test-sub/resourcegroups/test-rg/providers/microsoft.extendedlocation/customlocations/test-cl"
            },
            "properties": {
                "assetEndpointProfileRef": "test-endpoint-profile",
                "adrNamespace": "/subscriptions/test-sub/resourceGroups/test-rg/providers/Microsoft.IoTOperations/instances/test-instance/namespaces/aio-adr-ns-test-instance",
                "deviceRef": {
                    "deviceName": "test-device",
                    "endpointName": "test-endpoint"
                },
                "datasets": [
                    {
                        "name": "default",
                        "dataPoints": []
                    }
                ]
            }
        }

    def _create_mock_endpoint_profile(self, endpoint_type="Microsoft.Http"):
        """Helper to create a mock endpoint profile."""
        return {
            "name": "test-endpoint-profile",
            "properties": {
                "targetAddress": "http://example.com",
                "endpointType": endpoint_type,
                "endpointProfileType": "http",
                "configuration": "{}"
            }
        }

    def _create_mock_connector_template(self, endpoint_type="Microsoft.Http", version="1.0"):
        """Helper to create a mock connector template."""
        return {
            "name": f"{endpoint_type.lower()}-connector-template",
            "properties": {
                "deviceInboundEndpointTypes": [
                    {
                        "endpointType": endpoint_type,
                        "version": version
                    }
                ],
                "connectorMetadataRef": f"mcr.microsoft.com/azureiotoperations/akri-connectors/{endpoint_type.lower()}-metadata:1.0.0"
            }
        }

    @patch('azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client')
    @patch('azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator.fetch_oci_artifact')
    def test_import_datapoints_json_with_valid_data(self, mock_fetch_oci, mock_get_client):
        """Test importing valid datapoints from JSON file with validation."""
        cmd = self._create_mock_cmd()
        
        # Setup mocks
        mock_asset = self._create_mock_asset()
        mock_ops = Mock()
        mock_ops.get.return_value = mock_asset
        
        # Mock updated asset response
        updated_asset = mock_asset.copy()
        updated_asset["properties"]["datasets"][0]["dataPoints"] = [
            {
                "name": "temperature",
                "dataSource": "http://sensor/temp",
                "dataPointConfiguration": json.dumps({"method": "GET", "headers": {"Accept": "application/json"}})
            }
        ]
        mock_poller = Mock()
        mock_poller.result.return_value = updated_asset
        mock_ops.begin_create_or_replace.return_value = mock_poller
        
        # Mock validator setup
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        
        # Mock device.get() to return device with endpoint info
        mock_device = {
            "name": "test-device",
            "properties": {
                "endpoints": {
                    "inbound": {
                        "test-endpoint": {
                            "endpointType": "Microsoft.Http",
                            "version": "1.0"
                        }
                    }
                }
            }
        }
        mock_client.device = Mock()
        mock_client.device.get = Mock(return_value=mock_device)
        
        # Mock connector template list
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[self._create_mock_connector_template()]
        )
        mock_fetch_oci.return_value = REST_HTTP_METADATA
        
        # Create temporary JSON file with valid datapoints
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([
                {
                    "name": "temperature",
                    "dataSource": "http://sensor/temp",
                    "dataPointConfiguration": json.dumps({"method": "GET", "headers": {"Accept": "application/json"}})
                }
            ], f)
            temp_file = f.name
        
        try:
            # Execute import
            with patch('azext_edge.edge.providers.adr.helpers.check_cluster_connectivity'):
                assets_provider = Assets(cmd)
                with patch.object(assets_provider, 'ops', mock_ops):
                    result = assets_provider.import_dataset_data_points(
                        asset_name="test-asset",
                        dataset_name="default",
                        file_path=temp_file,
                        resource_group_name="test-rg",
                        replace=False,
                        wait_sec=0
                    )
            
            # Verify result
            assert len(result) == 1
            assert result[0]["name"] == "temperature"
            
            # Verify validation was called
            mock_get_client.assert_called()
            mock_client.device.get.assert_called_once()
            mock_fetch_oci.assert_called_once()
        finally:
            os.unlink(temp_file)

    @patch('azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client')
    @patch('azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator.fetch_oci_artifact')
    def test_import_datapoints_with_invalid_data_logs_warnings(self, mock_fetch_oci, mock_get_client):
        """Test importing datapoints with validation errors logs warnings but continues."""
        cmd = self._create_mock_cmd()
        
        # Setup mocks
        mock_asset = self._create_mock_asset()
        mock_ops = Mock()
        mock_ops.get.return_value = mock_asset
        
        # Mock updated asset - all points get imported even with validation errors
        updated_asset = mock_asset.copy()
        updated_asset["properties"]["datasets"][0]["dataPoints"] = [
            {
                "name": "temperature",
                "dataSource": "http://sensor/temp",
                "dataPointConfiguration": json.dumps({"method": "GET"})
            },
            {
                "name": "pressure",
                "dataSource": "http://sensor/pressure",
                "dataPointConfiguration": json.dumps({"headers": {"Accept": "application/json"}})  # Missing required "method"
            }
        ]
        mock_poller = Mock()
        mock_poller.result.return_value = updated_asset
        mock_ops.begin_create_or_replace.return_value = mock_poller
        
        # Mock validator setup
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[self._create_mock_connector_template()]
        )
        mock_fetch_oci.return_value = REST_HTTP_METADATA
        
        # Create temporary JSON file with mixed valid/invalid datapoints
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([
                {
                    "name": "temperature",
                    "dataSource": "http://sensor/temp",
                    "dataPointConfiguration": json.dumps({"method": "GET"})
                },
                {
                    "name": "pressure",
                    "dataSource": "http://sensor/pressure",
                    "dataPointConfiguration": json.dumps({"headers": {"Accept": "application/json"}})  # Missing method
                }
            ], f)
            temp_file = f.name
        
        try:
            # Execute import with logging capture
            with patch('azext_edge.edge.providers.adr.helpers.check_cluster_connectivity'):
                with patch('azext_edge.edge.providers.adr.assets.logger') as mock_logger:
                    assets_provider = Assets(cmd)
                    with patch.object(assets_provider, 'ops', mock_ops):
                        result = assets_provider.import_dataset_data_points(
                            asset_name="test-asset",
                            dataset_name="default",
                            file_path=temp_file,
                            resource_group_name="test-rg",
                            replace=False,
                            wait_sec=0
                        )
            
            # Verify result - both points should be imported despite validation error
            assert len(result) == 2
            
            # Verify warning was logged for validation failure
            # The logger is mocked, so we just verify the function was called
            assert mock_logger.warning.called, "Expected logger.warning to be called"
            # Optionally verify call count if needed
            assert mock_logger.warning.call_count >= 1, "Expected at least one warning call"
        finally:
            os.unlink(temp_file)

    @patch('azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client')
    @patch('azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator.fetch_oci_artifact')
    def test_import_datapoints_csv_format(self, mock_fetch_oci, mock_get_client):
        """Test importing datapoints from CSV file."""
        cmd = self._create_mock_cmd()
        
        # Setup mocks
        mock_asset = self._create_mock_asset()
        mock_ops = Mock()
        mock_ops.get.return_value = mock_asset
        
        updated_asset = mock_asset.copy()
        updated_asset["properties"]["datasets"][0]["dataPoints"] = [
            {
                "name": "temperature",
                "dataSource": "http://sensor/temp",
                "dataPointConfiguration": json.dumps({"method": "GET"}),
                "observabilityMode": "Log"
            }
        ]
        mock_poller = Mock()
        mock_poller.result.return_value = updated_asset
        mock_ops.begin_create_or_replace.return_value = mock_poller
        
        # Mock validator setup
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[self._create_mock_connector_template()]
        )
        mock_fetch_oci.return_value = REST_HTTP_METADATA
        
        # Create temporary CSV file
        csv_content = """name,dataSource,dataPointConfiguration,observabilityMode
temperature,http://sensor/temp,"{""method"": ""GET""}",Log
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            temp_file = f.name
        
        try:
            with patch('azext_edge.edge.providers.adr.helpers.check_cluster_connectivity'):
                assets_provider = Assets(cmd)
                with patch.object(assets_provider, 'ops', mock_ops):
                    result = assets_provider.import_dataset_data_points(
                        asset_name="test-asset",
                        dataset_name="default",
                        file_path=temp_file,
                        resource_group_name="test-rg",
                        replace=False,
                        wait_sec=0
                    )
            
            assert len(result) == 1
            assert result[0]["name"] == "temperature"
        finally:
            os.unlink(temp_file)

    @patch('azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client')
    def test_import_datapoints_no_connector_template_skips_validation(self, mock_get_client):
        """Test that import works when no connector template is found (validation skipped)."""
        cmd = self._create_mock_cmd()
        
        # Setup mocks
        mock_asset = self._create_mock_asset()
        mock_ops = Mock()
        mock_ops.get.return_value = mock_asset
        
        updated_asset = mock_asset.copy()
        updated_asset["properties"]["datasets"][0]["dataPoints"] = [
            {
                "name": "sensor1",
                "dataSource": "http://sensor1"
            }
        ]
        mock_poller = Mock()
        mock_poller.result.return_value = updated_asset
        mock_ops.begin_create_or_replace.return_value = mock_poller
        
        # Mock no connector templates found
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(return_value=[])
        
        # Create temporary JSON file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([
                {
                    "name": "sensor1",
                    "dataSource": "http://sensor1"
                }
            ], f)
            temp_file = f.name
        
        try:
            with patch('azext_edge.edge.providers.adr.helpers.check_cluster_connectivity'):
                with patch('azext_edge.edge.providers.adr.assets.logger') as mock_logger:
                    assets_provider = Assets(cmd)
                    with patch.object(assets_provider, 'ops', mock_ops):
                        result = assets_provider.import_dataset_data_points(
                            asset_name="test-asset",
                            dataset_name="default",
                            file_path=temp_file,
                            resource_group_name="test-rg",
                            replace=False,
                            wait_sec=0
                        )
            
            # Import should succeed
            assert len(result) == 1
            
            # Verify info log about validation
            info_calls = [call for call in mock_logger.info.call_args_list]
            assert any('validating' in str(call).lower() for call in info_calls)
        finally:
            os.unlink(temp_file)


class TestAssetEventImportWithValidation:
    """Test import_asset_events with validation."""

    def _create_mock_cmd(self):
        """Helper to create a mock cmd object."""
        cmd = Mock()
        cmd.cli_ctx = Mock()
        cmd.cli_ctx.cloud = Mock()
        cmd.cli_ctx.cloud.endpoints = Mock()
        cmd.cli_ctx.cloud.endpoints.resource_manager = "https://management.azure.com"
        cmd.cli_ctx.data = {"subscription_id": "eab4c10d-b020-4cb2-8959-d53cf2df388d"}
        return cmd

    def _create_mock_asset(self, endpoint_type="Microsoft.Onvif"):
        """Helper to create a mock asset for ONVIF."""
        return {
            "id": "/subscriptions/test-sub/resourceGroups/test-rg/providers/Microsoft.DeviceRegistry/assets/test-camera",
            "name": "test-camera",
            "type": "Microsoft.DeviceRegistry/assets",
            "extendedLocation": {
                "type": "CustomLocation",
                "name": "/subscriptions/test-sub/resourcegroups/test-rg/providers/microsoft.extendedlocation/customlocations/test-cl"
            },
            "properties": {
                "assetEndpointProfileRef": "test-onvif-profile",
                "adrNamespace": "/subscriptions/test-sub/resourceGroups/test-rg/providers/Microsoft.IoTOperations/instances/test-instance/namespaces/aio-adr-ns-test-instance",
                "deviceRef": {
                    "deviceName": "test-device",
                    "endpointName": "test-endpoint"
                },
                "events": []
            }
        }

    def _create_mock_connector_template(self, endpoint_type="Microsoft.Onvif"):
        """Helper to create a mock connector template."""
        return {
            "name": f"{endpoint_type.lower()}-connector-template",
            "properties": {
                "deviceInboundEndpointTypes": [
                    {
                        "endpointType": endpoint_type
                    }
                ],
                "connectorMetadataRef": f"mcr.microsoft.com/azureiotoperations/akri-connectors/{endpoint_type.lower()}-metadata:1.2.37"
            }
        }

    @patch('azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client')
    @patch('azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator.fetch_oci_artifact')
    def test_import_events_json_with_valid_data(self, mock_fetch_oci, mock_get_client):
        """Test importing valid events from JSON file with validation."""
        cmd = self._create_mock_cmd()
        
        # Setup mocks
        mock_asset = self._create_mock_asset()
        mock_ops = Mock()
        mock_ops.get.return_value = mock_asset
        
        # Mock updated asset response
        updated_asset = mock_asset.copy()
        updated_asset["properties"]["events"] = [
            {
                "name": "motion-detected",
                "eventNotifier": "ns=2;s=MotionDetector",
                "eventConfiguration": json.dumps({"filter": "Topic = 'motion'", "priority": 5})
            }
        ]
        mock_poller = Mock()
        mock_poller.result.return_value = updated_asset
        mock_ops.begin_create_or_replace.return_value = mock_poller
        
        # Mock validator setup
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        
        # Mock device.get() to return device with ONVIF endpoint info
        mock_device = {
            "name": "test-device",
            "properties": {
                "endpoints": {
                    "inbound": {
                        "test-endpoint": {
                            "endpointType": "Microsoft.Onvif",
                            "version": None
                        }
                    }
                }
            }
        }
        mock_client.device = Mock()
        mock_client.device.get = Mock(return_value=mock_device)
        
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[self._create_mock_connector_template()]
        )
        mock_fetch_oci.return_value = ONVIF_METADATA
        
        # Create temporary JSON file with valid events
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([
                {
                    "name": "motion-detected",
                    "eventNotifier": "ns=2;s=MotionDetector",
                    "eventConfiguration": json.dumps({"filter": "Topic = 'motion'", "priority": 5})
                }
            ], f)
            temp_file = f.name
        
        try:
            # Execute import
            with patch('azext_edge.edge.providers.adr.helpers.check_cluster_connectivity'):
                assets_provider = Assets(cmd)
                with patch.object(assets_provider, 'ops', mock_ops):
                    result = assets_provider.import_events(
                        asset_name="test-camera",
                        file_path=temp_file,
                        resource_group_name="test-rg",
                        replace=False,
                        wait_sec=0
                    )
            
            # Verify result
            assert len(result) == 1
            assert result[0]["name"] == "motion-detected"
            
            # Verify validation was called
            mock_get_client.assert_called()
            mock_client.device.get.assert_called_once()
            mock_fetch_oci.assert_called_once()
        finally:
            os.unlink(temp_file)

    @patch('azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client')
    @patch('azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator.fetch_oci_artifact')
    def test_import_events_with_invalid_priority(self, mock_fetch_oci, mock_get_client):
        """Test importing events with validation errors (priority out of range)."""
        cmd = self._create_mock_cmd()
        
        # Setup mocks
        mock_asset = self._create_mock_asset()
        mock_ops = Mock()
        mock_ops.get.return_value = mock_asset
        
        # Events still get imported despite validation errors
        updated_asset = mock_asset.copy()
        updated_asset["properties"]["events"] = [
            {
                "name": "tamper-detected",
                "eventNotifier": "ns=2;s=TamperDetector",
                "eventConfiguration": json.dumps({"filter": "Topic = 'tamper'", "priority": 99})  # Out of range
            }
        ]
        mock_poller = Mock()
        mock_poller.result.return_value = updated_asset
        mock_ops.begin_create_or_replace.return_value = mock_poller
        
        # Mock validator setup
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        
        # Mock device.get()
        mock_device = {
            "name": "test-device",
            "properties": {
                "endpoints": {
                    "inbound": {
                        "test-endpoint": {
                            "endpointType": "Microsoft.Onvif",
                            "version": None
                        }
                    }
                }
            }
        }
        mock_client.device = Mock()
        mock_client.device.get = Mock(return_value=mock_device)
        
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[self._create_mock_connector_template()]
        )
        mock_fetch_oci.return_value = ONVIF_METADATA
        
        # Create temporary JSON file with invalid event
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([
                {
                    "name": "tamper-detected",
                    "eventNotifier": "ns=2;s=TamperDetector",
                    "eventConfiguration": json.dumps({"filter": "Topic = 'tamper'", "priority": 99})
                }
            ], f)
            temp_file = f.name
        
        try:
            with patch('azext_edge.edge.providers.adr.helpers.check_cluster_connectivity'):
                with patch('azext_edge.edge.providers.adr.assets.logger') as mock_logger:
                    assets_provider = Assets(cmd)
                    with patch.object(assets_provider, 'ops', mock_ops):
                        result = assets_provider.import_events(
                            asset_name="test-camera",
                            file_path=temp_file,
                            resource_group_name="test-rg",
                            replace=False,
                            wait_sec=0
                        )
            
            # Event should still be imported
            assert len(result) == 1
            
            # Verify warning was logged
            warning_calls = [call for call in mock_logger.warning.call_args_list if 'validation failed' in str(call).lower()]
            assert len(warning_calls) > 0
        finally:
            os.unlink(temp_file)

    @patch('azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client')
    @patch('azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator.fetch_oci_artifact')
    def test_import_events_replace_mode(self, mock_fetch_oci, mock_get_client):
        """Test importing events with replace=True replaces existing events."""
        cmd = self._create_mock_cmd()
        
        # Setup mocks - asset with existing event
        mock_asset = self._create_mock_asset()
        mock_asset["properties"]["events"] = [
            {
                "name": "old-event",
                "eventNotifier": "ns=2;s=OldNotifier",
                "eventConfiguration": json.dumps({"filter": "old"})
            }
        ]
        mock_ops = Mock()
        mock_ops.get.return_value = mock_asset
        
        # Mock updated asset - only new event
        updated_asset = mock_asset.copy()
        updated_asset["properties"]["events"] = [
            {
                "name": "new-event",
                "eventNotifier": "ns=2;s=NewNotifier",
                "eventConfiguration": json.dumps({"filter": "Topic = 'new'", "priority": 3})
            }
        ]
        mock_poller = Mock()
        mock_poller.result.return_value = updated_asset
        mock_ops.begin_create_or_replace.return_value = mock_poller
        
        # Mock validator setup
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        
        # Mock device.get()
        mock_device = {
            "name": "test-device",
            "properties": {
                "endpoints": {
                    "inbound": {
                        "test-endpoint": {
                            "endpointType": "Microsoft.Onvif",
                            "version": None
                        }
                    }
                }
            }
        }
        mock_client.device = Mock()
        mock_client.device.get = Mock(return_value=mock_device)
        
        mock_client.akri_connector_template = Mock()
        mock_client.akri_connector_template.list_by_instance_resource = Mock(
            return_value=[self._create_mock_connector_template()]
        )
        mock_fetch_oci.return_value = ONVIF_METADATA
        
        # Create temporary JSON file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([
                {
                    "name": "new-event",
                    "eventNotifier": "ns=2;s=NewNotifier",
                    "eventConfiguration": json.dumps({"filter": "Topic = 'new'", "priority": 3})
                }
            ], f)
            temp_file = f.name
        
        try:
            with patch('azext_edge.edge.providers.adr.helpers.check_cluster_connectivity'):
                assets_provider = Assets(cmd)
                with patch.object(assets_provider, 'ops', mock_ops):
                    result = assets_provider.import_events(
                        asset_name="test-camera",
                        file_path=temp_file,
                        resource_group_name="test-rg",
                        replace=True,
                        wait_sec=0
                    )
            
            # Should only have the new event
            assert len(result) == 1
            assert result[0]["name"] == "new-event"
        finally:
            os.unlink(temp_file)


class TestExportWithImportRoundTrip:
    """Test export → import round-trip to verify file format compatibility."""

    def _create_mock_cmd(self):
        """Helper to create a mock cmd object."""
        cmd = Mock()
        cmd.cli_ctx = Mock()
        cmd.cli_ctx.cloud = Mock()
        cmd.cli_ctx.cloud.endpoints = Mock()
        cmd.cli_ctx.cloud.endpoints.resource_manager = "https://management.azure.com"
        cmd.cli_ctx.data = {"subscription_id": "eab4c10d-b020-4cb2-8959-d53cf2df388d"}
        return cmd

    @patch('azext_edge.edge.providers.adr.validator.get_iotops_mgmt_client')
    @patch('azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator.fetch_oci_artifact')
    def test_export_import_datapoints_roundtrip_json(self, mock_fetch_oci, mock_get_client):
        """Test export → import round-trip for datapoints in JSON format."""
        cmd = self._create_mock_cmd()
        
        # Mock asset with datapoints for export
        mock_ops = Mock()
        export_asset = {
            "id": "/subscriptions/test-sub/resourceGroups/test-rg/providers/Microsoft.DeviceRegistry/assets/test-asset",
            "name": "test-asset",
            "properties": {
                "assetEndpointProfileRef": "test-profile",
                "datasets": [
                    {
                        "name": "default",
                        "dataPoints": [
                            {
                                "name": "sensor1",
                                "dataSource": "http://sensor1",
                                "dataPointConfiguration": json.dumps({"method": "GET"}),
                                "observabilityMode": "Log"
                            },
                            {
                                "name": "sensor2",
                                "dataSource": "http://sensor2",
                                "dataPointConfiguration": json.dumps({"method": "POST", "headers": {"Content-Type": "application/json"}}),
                                "observabilityMode": "None"
                            }
                        ]
                    }
                ]
            }
        }
        
        temp_dir = tempfile.mkdtemp()
        try:
            # Export datapoints
            mock_ops.get.return_value = export_asset
            
            # Mock the device registry client to prevent real Azure calls
            with patch('azext_edge.edge.providers.adr.assets.get_registry_mgmt_client') as mock_get_registry:
                mock_registry_client = Mock()
                mock_registry_client.assets = mock_ops
                mock_get_registry.return_value = mock_registry_client
                
                assets_provider = Assets(cmd)
                export_result = assets_provider.export_dataset_data_points(
                    asset_name="test-asset",
                    dataset_name="default",
                    resource_group_name="test-rg",
                    extension="json",
                    output_dir=temp_dir,
                    replace=True
                )
            
            exported_file = export_result["file_path"]
            assert os.path.exists(exported_file)
            
            # Verify exported content
            with open(exported_file, 'r') as f:
                exported_data = json.load(f)
            assert len(exported_data) == 2
            assert exported_data[0]["name"] == "sensor1"
            assert exported_data[1]["name"] == "sensor2"
            
            # Now import the exported file
            import_asset = {
                "id": "/subscriptions/test-sub/resourceGroups/test-rg/providers/Microsoft.DeviceRegistry/assets/test-asset-2",
                "name": "test-asset-2",
                "properties": {
                    "assetEndpointProfileRef": "test-profile",
                    "adrNamespace": "/subscriptions/test-sub/resourceGroups/test-rg/providers/Microsoft.IoTOperations/instances/test-instance/namespaces/aio-adr-ns-test-instance",
                    "deviceRef": {
                        "deviceName": "test-device",
                        "endpointName": "test-endpoint"
                    },
                    "datasets": [{"name": "default", "dataPoints": []}]
                }
            }
            mock_ops.get.return_value = import_asset
            
            imported_asset = import_asset.copy()
            imported_asset["properties"]["datasets"][0]["dataPoints"] = exported_data
            mock_poller = Mock()
            mock_poller.result.return_value = imported_asset
            mock_ops.begin_create_or_replace.return_value = mock_poller
            
            # Mock validator
            mock_client = Mock()
            mock_get_client.return_value = mock_client
            
            # Mock device.get()
            mock_device = {
                "name": "test-device",
                "properties": {
                    "endpoints": {
                        "inbound": {
                            "test-endpoint": {
                                "endpointType": "Microsoft.Http",
                                "version": "1.0"
                            }
                        }
                    }
                }
            }
            mock_client.device = Mock()
            mock_client.device.get = Mock(return_value=mock_device)
            
            mock_client.akri_connector_template = Mock()
            mock_client.akri_connector_template.list_by_instance_resource = Mock(
                return_value=[{
                    "name": "http-template",
                    "properties": {
                        "deviceInboundEndpointTypes": [{"endpointType": "Microsoft.Http", "version": "1.0"}],
                        "connectorMetadataRef": "mcr.microsoft.com/test:1.0"
                    }
                }]
            )
            mock_fetch_oci.return_value = REST_HTTP_METADATA
            
            # Create new Assets instance for import with mocked registry client
            with patch('azext_edge.edge.providers.adr.assets.get_registry_mgmt_client') as mock_get_registry_import:
                mock_registry_client_import = Mock()
                mock_registry_client_import.assets = mock_ops
                mock_get_registry_import.return_value = mock_registry_client_import
                
                assets_provider_import = Assets(cmd)
                
                with patch('azext_edge.edge.providers.adr.helpers.check_cluster_connectivity'):
                    import_result = assets_provider_import.import_dataset_data_points(
                        asset_name="test-asset-2",
                        dataset_name="default",
                        file_path=exported_file,
                        resource_group_name="test-rg",
                        replace=False,
                        wait_sec=0
                    )
            
            # Verify imported datapoints match exported ones
            assert len(import_result) == 2
            assert import_result[0]["name"] == "sensor1"
            assert import_result[1]["name"] == "sensor2"
            
        finally:
            # Cleanup
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
