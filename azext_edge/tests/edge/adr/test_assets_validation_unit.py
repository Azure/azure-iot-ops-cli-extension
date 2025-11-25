# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""
Unit tests for asset validation integration with ConnectorMetadataValidator.
Tests that validation is properly called during add/import operations.
"""

import pytest
from unittest.mock import Mock, patch
from azure.cli.core.azclierror import ValidationError
from azext_edge.edge.providers.adr.assets import Assets


@pytest.fixture
def mock_asset():
    """Fixture providing a mock asset record."""
    return {
        "id": "/subscriptions/sub-id/resourceGroups/rg/providers/Microsoft.DeviceRegistry/assets/test-asset",
        "name": "test-asset",
        "extendedLocation": {
            "name": (
                "/subscriptions/sub-id/resourceGroups/rg/providers/"
                "Microsoft.ExtendedLocation/customLocations/test-instance"
            ),
            "type": "CustomLocation",
        },
        "properties": {
            "assetEndpointProfileRef": "test-aep",
            "datasets": [
                {
                    "name": "default",
                    "dataPoints": [{"name": "existing-point", "dataSource": "tag1", "observabilityMode": "None"}],
                }
            ],
            "events": [{"name": "existing-event", "eventNotifier": "notifier1", "observabilityMode": "None"}],
        },
    }

    # ========== add_dataset_data_point Tests ==========


@patch("azext_edge.edge.providers.adr.assets.wait_for_terminal_state")
@patch("azext_edge.edge.providers.adr.assets.console")
@patch("azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator")
def test_add_data_point_with_validation_success(mock_validator_class, mock_console, mock_wait, mocked_cmd, mock_asset):
    """Test add_dataset_data_point validates successfully."""
    assets = Assets(mocked_cmd)

    # Mock show() and ops to prevent Azure calls
    with patch.object(assets, "show", return_value=mock_asset), patch.object(assets, "ops"):
        # Mock validator
        mock_validator = Mock()
        mock_validator_class.from_asset.return_value = mock_validator
        mock_validator.validate_datapoint.return_value = None  # Success

        # Mock poller
        mock_wait.return_value = mock_asset

        # Call method
        result = assets.add_dataset_data_point(
            asset_name="test-asset",
            dataset_name="default",
            data_point_name="new-point",
            data_source="tag2",
            resource_group_name="test-rg",
            wait_sec=0,
        )

        # Verify validator was created and called
        mock_validator_class.from_asset.assert_called_once_with(mocked_cmd, mock_asset)
        mock_validator.validate_datapoint.assert_called_once()

        # Verify data point was added
        assert isinstance(result, list)


@patch("azext_edge.edge.providers.adr.assets.wait_for_terminal_state")
@patch("azext_edge.edge.providers.adr.assets.console")
@patch("azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator")
def test_add_data_point_validation_fails_but_continues(
    mock_validator_class, mock_console, mock_wait, mocked_cmd, mock_asset
):
    """Test add_dataset_data_point continues even if validation fails."""
    assets = Assets(mocked_cmd)

    with patch.object(assets, "show", return_value=mock_asset), patch.object(assets, "ops"):
        # Mock validator to raise ValidationError
        mock_validator = Mock()
        mock_validator_class.from_asset.return_value = mock_validator
        mock_validator.validate_datapoint.side_effect = ValidationError("Invalid configuration")

        mock_wait.return_value = mock_asset

        # Should not raise, validation is logged as warning
        result = assets.add_dataset_data_point(
            asset_name="test-asset",
            dataset_name="default",
            data_point_name="new-point",
            data_source="tag2",
            resource_group_name="test-rg",
            wait_sec=0,
        )

        # Verify validator was called
        mock_validator.validate_datapoint.assert_called_once()

        # Verify data point was still added despite validation failure
        assert isinstance(result, list)


@patch("azext_edge.edge.providers.adr.assets.wait_for_terminal_state")
@patch("azext_edge.edge.providers.adr.assets.console")
@patch("azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator")
def test_add_data_point_validator_import_fails(mock_validator_class, mock_console, mock_wait, mocked_cmd, mock_asset):
    """Test add_dataset_data_point handles validator import failure gracefully."""
    assets = Assets(mocked_cmd)

    with patch.object(assets, "show", return_value=mock_asset), patch.object(assets, "ops"):
        # Mock validator import failure
        mock_validator_class.from_asset.side_effect = ImportError("Cannot import validator")

        mock_wait.return_value = mock_asset

        # Should not raise
        result = assets.add_dataset_data_point(
            asset_name="test-asset",
            dataset_name="default",
            data_point_name="new-point",
            data_source="tag2",
            resource_group_name="test-rg",
            wait_sec=0,
        )

        # Verify operation completed
        assert isinstance(result, list)

    # ========== import_dataset_data_points Tests ==========


@patch("azext_edge.edge.providers.adr.assets.wait_for_terminal_state")
@patch("azext_edge.edge.providers.adr.assets.console")
@patch("azext_edge.edge.providers.adr.assets._process_asset_sub_points_file_path")
@patch("azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator")
def test_import_data_points_with_validation_all_pass(
    mock_validator_class, mock_process_file, mock_console, mock_wait, mocked_cmd, mock_asset
):
    """Test import_dataset_data_points validates all points successfully."""
    assets = Assets(mocked_cmd)

    with patch.object(assets, "show", return_value=mock_asset), patch.object(assets, "ops"):
        # Mock file processing
        new_points = [
            {"name": "point1", "dataSource": "tag1"},
            {"name": "point2", "dataSource": "tag2"},
            {"name": "point3", "dataSource": "tag3"},
        ]
        mock_process_file.return_value = new_points

        # Mock validator
        mock_validator = Mock()
        mock_validator_class.from_asset.return_value = mock_validator
        mock_validator.validate_datapoint.return_value = None  # All pass

        mock_wait.return_value = mock_asset

        result = assets.import_dataset_data_points(
            asset_name="test-asset",
            dataset_name="default",
            file_path="/path/to/file.json",
            resource_group_name="test-rg",
            wait_sec=0,
        )

        # Verify validator was created
        mock_validator_class.from_asset.assert_called_once_with(mocked_cmd, mock_asset)

        # Verify all points were validated
        assert mock_validator.validate_datapoint.call_count == 3
        calls = mock_validator.validate_datapoint.call_args_list
        assert calls[0][0][0] == new_points[0]
        assert calls[1][0][0] == new_points[1]
        assert calls[2][0][0] == new_points[2]

        assert isinstance(result, list)


@patch("azext_edge.edge.providers.adr.assets.wait_for_terminal_state")
@patch("azext_edge.edge.providers.adr.assets.console")
@patch("azext_edge.edge.providers.adr.assets._process_asset_sub_points_file_path")
@patch("azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator")
def test_import_data_points_with_validation_some_fail(
    mock_validator_class, mock_process_file, mock_console, mock_wait, mocked_cmd, mock_asset
):
    """Test import_dataset_data_points logs errors when some validations fail."""
    assets = Assets(mocked_cmd)

    with patch.object(assets, "show", return_value=mock_asset), patch.object(assets, "ops"):
        new_points = [{"name": "valid-point", "dataSource": "tag1"}, {"name": "invalid-point", "dataSource": "tag2"}]
        mock_process_file.return_value = new_points

        # Mock validator - first passes, second fails
        mock_validator = Mock()
        mock_validator_class.from_asset.return_value = mock_validator
        mock_validator.validate_datapoint.side_effect = [
            None,  # First point passes
            ValidationError("Invalid configuration"),  # Second point fails
        ]

        mock_wait.return_value = mock_asset

        # Should complete despite validation errors
        result = assets.import_dataset_data_points(
            asset_name="test-asset",
            dataset_name="default",
            file_path="/path/to/file.json",
            resource_group_name="test-rg",
            wait_sec=0,
        )

        # Verify both points were validated
        assert mock_validator.validate_datapoint.call_count == 2

        # Import should still proceed
        assert isinstance(result, list)


@patch("azext_edge.edge.providers.adr.assets.wait_for_terminal_state")
@patch("azext_edge.edge.providers.adr.assets.console")
@patch("azext_edge.edge.providers.adr.assets._process_asset_sub_points_file_path")
@patch("azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator")
def test_import_data_points_empty_list(
    mock_validator_class, mock_process_file, mock_console, mock_wait, mocked_cmd, mock_asset
):
    """Test import_dataset_data_points handles empty data points list."""
    assets = Assets(mocked_cmd)

    with patch.object(assets, "show", return_value=mock_asset), patch.object(assets, "ops"):
        mock_process_file.return_value = []

        mock_validator = Mock()
        mock_validator_class.from_asset.return_value = mock_validator

        mock_wait.return_value = mock_asset

        result = assets.import_dataset_data_points(
            asset_name="test-asset",
            dataset_name="default",
            file_path="/path/to/file.json",
            resource_group_name="test-rg",
            wait_sec=0,
        )

        # Validator should not be called for empty list
        mock_validator.validate_datapoint.assert_not_called()
        assert isinstance(result, list)

    # ========== import_events Tests ==========


@patch("azext_edge.edge.providers.adr.assets.wait_for_terminal_state")
@patch("azext_edge.edge.providers.adr.assets.console")
@patch("azext_edge.edge.providers.adr.assets._process_asset_sub_points_file_path")
@patch("azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator")
def test_import_events_with_validation_all_pass(
    mock_validator_class, mock_process_file, mock_console, mock_wait, mocked_cmd, mock_asset
):
    """Test import_events validates all events successfully."""
    assets = Assets(mocked_cmd)

    with patch.object(assets, "show", return_value=mock_asset), patch.object(assets, "ops"):
        new_events = [
            {"name": "event1", "eventNotifier": "notifier1"},
            {"name": "event2", "eventNotifier": "notifier2"},
        ]
        mock_process_file.return_value = new_events

        # Mock validator
        mock_validator = Mock()
        mock_validator_class.from_asset.return_value = mock_validator
        mock_validator.validate_event.return_value = None

        mock_wait.return_value = mock_asset

        result = assets.import_events(
            asset_name="test-asset", file_path="/path/to/events.json", resource_group_name="test-rg", wait_sec=0
        )

        # Verify validator was created
        mock_validator_class.from_asset.assert_called_once_with(mocked_cmd, mock_asset)

        # Verify all events were validated
        assert mock_validator.validate_event.call_count == 2
        calls = mock_validator.validate_event.call_args_list
        assert calls[0][0][0] == new_events[0]
        assert calls[1][0][0] == new_events[1]

        assert isinstance(result, list)


@patch("azext_edge.edge.providers.adr.assets.console")
@patch("azext_edge.edge.providers.adr.assets.wait_for_terminal_state")
@patch("azext_edge.edge.providers.adr.assets._process_asset_sub_points_file_path")
@patch("azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator")
def test_import_events_with_validation_failure(
    mock_validator_class, mock_process_file, mock_wait, mock_console, mocked_cmd, mock_asset
):
    """Test import_events logs errors but continues when validation fails."""
    assets = Assets(mocked_cmd)

    with patch.object(assets, "show", return_value=mock_asset), patch.object(assets, "ops"):
        new_events = [
            {"name": "valid-event", "eventNotifier": "notifier1"},
            {"name": "invalid-event", "eventNotifier": "notifier2"},
        ]
        mock_process_file.return_value = new_events

        # Mock validator - first passes, second fails
        mock_validator = Mock()
        mock_validator_class.from_asset.return_value = mock_validator
        mock_validator.validate_event.side_effect = [None, ValidationError("Invalid event configuration")]

        mock_wait.return_value = mock_asset

        # Should complete despite validation error
        result = assets.import_events(
            asset_name="test-asset", file_path="/path/to/events.json", resource_group_name="test-rg", wait_sec=0
        )

        # Verify both events were validated
        assert mock_validator.validate_event.call_count == 2

        # Import should still proceed
        assert isinstance(result, list)


@patch("azext_edge.edge.providers.adr.assets.wait_for_terminal_state")
@patch("azext_edge.edge.providers.adr.assets.console")
@patch("azext_edge.edge.providers.adr.assets._process_asset_sub_points_file_path")
@patch("azext_edge.edge.providers.adr.validator.ConnectorMetadataValidator")
def test_import_events_validator_creation_fails(
    mock_validator_class, mock_process_file, mock_console, mock_wait, mocked_cmd, mock_asset
):
    """Test import_events handles validator creation failure gracefully."""
    assets = Assets(mocked_cmd)

    with patch.object(assets, "show", return_value=mock_asset), patch.object(assets, "ops"):
        new_events = [{"name": "event1", "eventNotifier": "notifier1"}]
        mock_process_file.return_value = new_events

        # Mock validator creation failure
        mock_validator_class.from_asset.side_effect = Exception("Failed to create validator")

        mock_wait.return_value = mock_asset

        # Should not raise, just log warning
        result = assets.import_events(
            asset_name="test-asset", file_path="/path/to/events.json", resource_group_name="test-rg", wait_sec=0
        )

        # Import should still complete
        assert isinstance(result, list)
