# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from typing import List, Optional
from unittest.mock import Mock

import pytest
import responses
from azure.cli.core.azclierror import ValidationError
from azure.core.exceptions import ResourceNotFoundError

from azext_edge.edge.commands_edge import migrate_assets
from azext_edge.edge.providers.adr.assets import ASSET_RESOURCE_TYPE

from ...generators import generate_random_string, generate_resource_id
from .resources.conftest import (
    ADR_API_VERSION,
    ADR_RP,
    ARG_ENDPOINT,
    BASE_URL,
    get_base_endpoint,
)
from .resources.test_clusters_unit import get_cluster_url
from .resources.test_custom_locations_unit import get_mock_custom_location_record
from .resources.test_instances_unit import (
    get_instance_endpoint,
    get_mock_instance_record,
)


def get_namespace_migrate_endpoint(resource_group_name: str, namespace_name: str) -> str:
    """Get the namespace migrate endpoint URL."""
    return get_base_endpoint(
        resource_group_name=resource_group_name,
        resource_path=f"/namespaces/{namespace_name}/migrate",
        resource_provider=ADR_RP,
        api_version=ADR_API_VERSION,
    )


def get_mock_asset_record(name: str, resource_group_name: str, custom_location_id: str) -> dict:
    """Create an asset record as returned by Azure Resource Graph."""
    return {
        "id": generate_resource_id(
            resource_group_name=resource_group_name,
            resource_provider=ADR_RP,
            resource_path=f"/assets/{name}",
        ),
        "name": name,
        "type": ASSET_RESOURCE_TYPE,
        "extendedLocation": {"name": custom_location_id, "type": "CustomLocation"},
        "properties": {"provisioningState": "Succeeded"},
    }


def setup_migration_mocks(
    mocked_responses: responses,
    instance_name: str,
    resource_group_name: str,
    asset_names: List[str],
    namespace_name: Optional[str] = None,
    custom_location_name: Optional[str] = None,
    cluster_name: Optional[str] = None,
    cluster_connected: bool = True,
    has_namespace: bool = True,
    mock_instance: bool = True,
    mock_custom_location: bool = True,
) -> List[dict]:
    """Setup all necessary mocks for migration tests."""
    namespace_name = namespace_name or generate_random_string()
    custom_location_name = custom_location_name or generate_random_string()
    cluster_name = cluster_name or generate_random_string()

    custom_location_id = generate_resource_id(
        resource_group_name=resource_group_name,
        resource_provider="Microsoft.ExtendedLocation",
        resource_path=f"/customLocations/{custom_location_name}",
    )

    # Create instance record
    instance_record = get_mock_instance_record(
        name=instance_name,
        resource_group_name=resource_group_name,
        cl_name=custom_location_name,
        adr_namespace_name=namespace_name if has_namespace else None,
        version="1.2.0",
    )

    if not has_namespace:
        instance_record["properties"].pop("adrNamespaceRef", None)

    # Mock instance fetch
    instance_url = get_instance_endpoint(resource_group_name=resource_group_name, instance_name=instance_name)

    if mock_instance:
        mocked_responses.add(
            method=responses.GET,
            url=instance_url,
            json=instance_record,
            status=200,
        )
    else:
        mocked_responses.add(
            method=responses.GET,
            url=instance_url,
            status=404,
        )
        return []

    if not has_namespace:
        return []

    # Mock custom location fetch
    custom_location_url = f"{BASE_URL}{instance_record['extendedLocation']['name']}"

    if mock_custom_location:
        cl_record = get_mock_custom_location_record(
            name=custom_location_name,
            resource_group_name=resource_group_name,
            cluster_name=cluster_name,
        )
        mocked_responses.add(
            method=responses.GET,
            url=custom_location_url,
            json=cl_record,
            status=200,
        )
    else:
        mocked_responses.add(
            method=responses.GET,
            url=custom_location_url,
            status=404,
        )
        return []

    # Mock cluster fetch
    cluster_record = {
        "id": generate_resource_id(
            resource_group_name=resource_group_name,
            resource_provider="Microsoft.Kubernetes",
            resource_path=f"/connectedClusters/{cluster_name}",
        ),
        "name": cluster_name,
        "properties": {"connectivityStatus": "Connected" if cluster_connected else "Disconnected"},
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_cluster_url(cluster_rg=resource_group_name, cluster_name=cluster_name),
        json=cluster_record,
        status=200,
    )

    if not cluster_connected:
        return []

    # Create asset records
    assets = [
        get_mock_asset_record(
            name=name, resource_group_name=resource_group_name, custom_location_id=custom_location_id
        )
        for name in asset_names
    ]

    # Mock Resource Graph query
    mocked_responses.add(
        method=responses.POST,
        url=ARG_ENDPOINT,
        json={"data": assets},
        status=200,
    )

    return assets


def add_migration_response(
    mocked_responses: responses, resource_group_name: str, namespace_name: str, status: str = "Succeeded"
) -> None:
    """Add a mock migration operation response."""
    mocked_responses.add(
        method=responses.POST,
        url=get_namespace_migrate_endpoint(resource_group_name, namespace_name),
        json={"id": "operation_id", "status": status},
        status=200,
    )


def calculate_expected_asset_ids(assets: List[dict], name_patterns: Optional[List[str]]) -> List[str]:
    """Calculate expected asset IDs based on filtering patterns."""
    if not name_patterns:
        return [asset["id"] for asset in assets]

    from fnmatch import fnmatch

    expected_ids = []
    exact_names = {p for p in name_patterns if not any(c in p for c in "*?[")}
    patterns = [p for p in name_patterns if any(c in p for c in "*?[")]

    for asset in assets:
        asset_name = asset["name"]
        if asset_name in exact_names or any(fnmatch(asset_name, p) for p in patterns):
            expected_ids.append(asset["id"])

    return expected_ids


@pytest.fixture
def mock_prompt(mocker) -> Mock:
    """Mock confirmation prompt - always returns True by default."""
    return mocker.patch(
        "azext_edge.edge.providers.orchestration.migration.should_continue_prompt",
        return_value=True,
    )


@pytest.fixture
def mock_console(mocker) -> Mock:
    """Mock console output."""
    return mocker.patch("azext_edge.edge.providers.orchestration.migration.console")


@pytest.mark.parametrize(
    "name_patterns, asset_names, expected_count",
    [
        # No filter - migrate all
        (None, ["pump1", "pump2", "valve1"], 3),
        # Exact names only
        (["pump1", "valve2"], ["pump1", "pump2", "valve1", "valve2"], 2),
        # Single glob pattern
        (["pump*"], ["pump1", "pump2", "valve1"], 2),
        # Question mark pattern
        (["sensor?"], ["sensor1", "sensor2", "valve1"], 2),
        # Character class pattern
        (["asset[123]"], ["asset1", "asset2", "asset3", "asset4"], 3),
        # Mix of exact and glob
        (["pump1", "valve*"], ["pump1", "pump2", "valve1", "valve2"], 3),
        # No matches
        (["nonexistent"], ["pump1", "valve1"], 0),
        # Empty list with pattern
        (["*"], [], 0),
        # Complex patterns
        (["sensor[0-9]*", "valve?"], ["sensor123", "sensor456", "valve1", "valve2", "pump1"], 4),
        # Dash patterns
        (["device-*"], ["device-001", "device-002", "sensor-001"], 2),
    ],
)
def test_migrate_assets_filtering(
    mocked_cmd,
    mocked_responses: responses,
    name_patterns: Optional[List[str]],
    asset_names: List[str],
    expected_count: int,
):
    """Test asset migration with various filtering scenarios."""
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    namespace_name = generate_random_string()

    assets = setup_migration_mocks(
        mocked_responses=mocked_responses,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        asset_names=asset_names,
        namespace_name=namespace_name,
    )

    if expected_count > 0:
        add_migration_response(mocked_responses, resource_group_name, namespace_name)

    result = migrate_assets(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        name_patterns=name_patterns,
        confirm_yes=True,
        wait_sec=0.1,
    )

    if expected_count > 0:
        assert result is not None
        assert result["status"] == "Succeeded"

        # Verify the correct assets were sent in the migration request
        migration_request = mocked_responses.calls[-1].request
        expected_ids = calculate_expected_asset_ids(assets, name_patterns)

        request_body = json.loads(migration_request.body)
        assert set(request_body["resourceIds"]) == set(expected_ids)
        assert request_body["scope"] == "Resources"
    else:
        assert result is None


@pytest.mark.parametrize("asset_count", [1, 10, 100])
def test_migrate_assets_scale(
    mocked_cmd,
    mocked_responses: responses,
    asset_count: int,
):
    """Test migration with different numbers of assets."""
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    namespace_name = generate_random_string()
    asset_names = [f"asset_{i}" for i in range(asset_count)]

    setup_migration_mocks(
        mocked_responses=mocked_responses,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        asset_names=asset_names,
        namespace_name=namespace_name,
    )

    add_migration_response(mocked_responses, resource_group_name, namespace_name)

    result = migrate_assets(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=True,
        wait_sec=0.1,
    )

    assert result is not None
    assert result["status"] == "Succeeded"

    # Verify all assets were included
    migration_request = mocked_responses.calls[-1].request
    request_body = json.loads(migration_request.body)
    assert len(request_body["resourceIds"]) == asset_count


@pytest.mark.parametrize(
    "confirm_yes, user_continues, should_migrate",
    [
        (True, None, True),  # --yes flag bypasses prompt
        (False, True, True),  # User confirms at prompt
        (False, False, False),  # User declines at prompt
    ],
)
def test_user_confirmation(
    mocked_cmd,
    mocked_responses: responses,
    mocker,
    mock_console: Mock,
    confirm_yes: bool,
    user_continues: Optional[bool],
    should_migrate: bool,
):
    """Test user confirmation flow for asset migration."""
    prompt_return = True if confirm_yes else user_continues
    mock_prompt = mocker.patch(
        "azext_edge.edge.providers.orchestration.migration.should_continue_prompt",
        return_value=prompt_return,
    )

    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    namespace_name = generate_random_string()

    assets = setup_migration_mocks(
        mocked_responses=mocked_responses,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        asset_names=["asset1", "asset2"],
        namespace_name=namespace_name,
    )

    if should_migrate:
        add_migration_response(mocked_responses, resource_group_name, namespace_name)

    result = migrate_assets(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=confirm_yes,
        wait_sec=0.1,
    )

    # Verify prompt was called with correct arguments
    mock_prompt.assert_called_once_with(confirm_yes=confirm_yes, context="Migration")

    # Verify console output only when prompting
    if not confirm_yes:
        assert mock_console.print.call_count == 2
        mock_console.print_json.assert_called_once_with(data=[a["id"] for a in assets])
    else:
        mock_console.print.assert_not_called()
        mock_console.print_json.assert_not_called()

    # Verify result based on whether migration should proceed
    assert (result is not None) == should_migrate
    if should_migrate:
        assert result["status"] == "Succeeded"


def test_no_assets_in_instance(
    mocked_cmd,
    mocked_responses: responses,
    mocker,
):
    """Test behavior when instance has no root assets."""
    mock_prompt = mocker.patch("azext_edge.edge.providers.orchestration.migration.should_continue_prompt")
    mock_logger = mocker.patch("azext_edge.edge.providers.orchestration.migration.logger")

    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    setup_migration_mocks(
        mocked_responses=mocked_responses,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        asset_names=[],
    )

    result = migrate_assets(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=True,
        wait_sec=0.1,
    )

    assert result is None
    mock_prompt.assert_not_called()
    mock_logger.warning.assert_called_with("No root assets are associated with the instance.")


def test_no_assets_match_filter(
    mocked_cmd,
    mocked_responses: responses,
    mocker,
):
    """Test behavior when filtering results in no assets to migrate."""
    mock_logger = mocker.patch("azext_edge.edge.providers.orchestration.migration.logger")

    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    setup_migration_mocks(
        mocked_responses=mocked_responses,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        asset_names=["pump1", "pump2", "valve1"],
    )

    result = migrate_assets(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        name_patterns=["nonexistent*"],  # Pattern that matches nothing
        confirm_yes=True,
        wait_sec=0.1,
    )

    assert result is None
    mock_logger.warning.assert_called_with("No root assets to migrate found.")


@pytest.mark.parametrize(
    "error_scenario",
    [
        {
            "has_namespace": False,
            "error_message": "The instance does not have an associated ADR namespace",
        },
        {
            "cluster_connected": False,
            "error_message": "is not connected",
        },
    ],
)
def test_validation_errors(
    mocked_cmd,
    mocked_responses: responses,
    error_scenario: dict,
):
    """Test validation error scenarios for asset migration."""
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    setup_migration_mocks(
        mocked_responses=mocked_responses,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        asset_names=["test_asset"],
        has_namespace=error_scenario.get("has_namespace", True),
        cluster_connected=error_scenario.get("cluster_connected", True),
    )

    with pytest.raises(ValidationError) as exc_info:
        migrate_assets(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            confirm_yes=True,
        )

    assert error_scenario["error_message"] in str(exc_info.value)


@pytest.mark.parametrize(
    "mock_instance, mock_custom_location",
    [
        (False, True),  # Instance not found
        (True, False),  # Custom location not found
    ],
)
def test_resource_not_found(
    mocked_cmd,
    mocked_responses: responses,
    mock_instance: bool,
    mock_custom_location: bool,
):
    """Test resource not found error scenarios."""
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    setup_migration_mocks(
        mocked_responses=mocked_responses,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        asset_names=["test_asset"],
        mock_instance=mock_instance,
        mock_custom_location=mock_custom_location,
    )

    with pytest.raises(ResourceNotFoundError):
        migrate_assets(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            confirm_yes=True,
        )
