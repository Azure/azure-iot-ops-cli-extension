# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import re
from fnmatch import fnmatch
from typing import Dict, List, Optional, Tuple
from unittest.mock import Mock

import pytest
import responses
from azure.cli.core.azclierror import AzureResponseError, ValidationError
from azure.core.exceptions import ResourceNotFoundError

from azext_edge.edge.commands_edge import migrate_assets
from azext_edge.edge.providers.adr.assets import ASSET_RESOURCE_TYPE
from azext_edge.edge.providers.orchestration.common import (
    ADR_RP_APP_ID,
    KUBERNETES_ARC_CONTRIBUTOR_ROLE_ID,
    MIN_INSTANCE_VERSION_FOR_MIGRATE,
)

from ...generators import (
    generate_random_string,
    generate_resource_id,
    generate_role_def_id,
    generate_uuid,
)
from .resources.conftest import (
    ADR_API_VERSION,
    ADR_RP,
    ARG_ENDPOINT,
    BASE_URL,
    ZEROED_SUBSCRIPTION,
    append_role_assignment_endpoint,
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


def get_sp_fetch_endpoint() -> str:
    """Get the service principal fetch endpoint URL."""
    return f"https://graph.microsoft.com/v1.0/servicePrincipals(appId='{ADR_RP_APP_ID}')"


def create_asset_record(name: str, resource_group_name: str, custom_location_id: str) -> dict:
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


def create_cluster_record(cluster_name: str, resource_group_name: str, connected: bool = True) -> dict:
    """Create a cluster record."""
    return {
        "id": generate_resource_id(
            resource_group_name=resource_group_name,
            resource_provider="Microsoft.Kubernetes",
            resource_path=f"/connectedClusters/{cluster_name}",
        ),
        "name": cluster_name,
        "properties": {"connectivityStatus": "Connected" if connected else "Disconnected"},
    }


# Setup functions for mocking Azure resources
def setup_base_resources(
    mocked_responses: responses,
    instance_name: str,
    resource_group_name: str,
    namespace_name: str,
    custom_location_name: str,
    cluster_name: str,
    has_namespace: bool = True,
    cluster_connected: bool = True,
    mock_instance: bool = True,
    mock_custom_location: bool = True,
    instance_version: str = MIN_INSTANCE_VERSION_FOR_MIGRATE,
) -> Tuple[dict, str]:
    """Setup base resources: instance, custom location, and cluster."""
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
        version=instance_version,
    )
    if not has_namespace:
        instance_record["properties"].pop("adrNamespaceRef", None)

    # Mock instance
    instance_url = get_instance_endpoint(resource_group_name=resource_group_name, instance_name=instance_name)
    mocked_responses.add(
        method=responses.GET,
        url=instance_url,
        json=instance_record if mock_instance else {},
        status=200 if mock_instance else 404,
    )

    from azext_edge.edge.util.machinery import scoped_semver_import

    semver = scoped_semver_import()

    # Early return if instance not mocked, no namespace, or version is too low
    if (
        not mock_instance
        or not has_namespace
        or semver.parse(instance_version) < semver.parse(MIN_INSTANCE_VERSION_FOR_MIGRATE)
    ):
        return instance_record, custom_location_id

    # Mock custom location
    custom_location_url = f"{BASE_URL}{custom_location_id}"
    if mock_custom_location:
        mocked_responses.add(
            method=responses.GET,
            url=custom_location_url,
            json=get_mock_custom_location_record(
                name=custom_location_name,
                resource_group_name=resource_group_name,
                cluster_name=cluster_name,
            ),
            status=200,
        )
    else:
        mocked_responses.add(
            method=responses.GET,
            url=custom_location_url,
            status=404,
        )
        return instance_record, custom_location_id

    # Mock cluster
    mocked_responses.add(
        method=responses.GET,
        url=get_cluster_url(cluster_rg=resource_group_name, cluster_name=cluster_name),
        json=create_cluster_record(cluster_name, resource_group_name, cluster_connected),
        status=200,
    )

    return instance_record, custom_location_id


def setup_role_assignment_mocks(
    mocked_responses: responses,
    custom_location_id: str,
    adr_sp_oid: Optional[str] = None,
    sp_lookup_success: bool = True,
    ra_exists: bool = False,
) -> str:
    """Setup role assignment related mocks."""
    target_sp_oid = adr_sp_oid or generate_uuid()

    if not adr_sp_oid:
        # Mock SP lookup
        mocked_responses.add(
            method=responses.GET,
            url=get_sp_fetch_endpoint(),
            json={"id": target_sp_oid, "appId": ADR_RP_APP_ID} if sp_lookup_success else {},
            status=200 if sp_lookup_success else 401,
        )

    if sp_lookup_success or adr_sp_oid:
        # Mock role assignment check
        ra_endpoint = append_role_assignment_endpoint(
            resource_endpoint=f"{BASE_URL}{custom_location_id}", filter_query=f"principalId eq '{target_sp_oid}'"
        )

        existing_ra = []
        if ra_exists:
            existing_ra = [
                {
                    "properties": {
                        "roleDefinitionId": generate_role_def_id(
                            subscription_id=ZEROED_SUBSCRIPTION, role_id=KUBERNETES_ARC_CONTRIBUTOR_ROLE_ID
                        ),
                        "principalId": target_sp_oid,
                    }
                }
            ]

        mocked_responses.add(
            method=responses.GET,
            url=ra_endpoint,
            json={"value": existing_ra},
            status=200,
        )

        # Mock role assignment creation if needed
        if not ra_exists:
            mocked_responses.add(
                method=responses.PUT,
                url=re.compile(
                    append_role_assignment_endpoint(resource_endpoint=f"{BASE_URL}{custom_location_id}", ra_name=".*")
                ),
                json={},
                status=200,
            )

    return target_sp_oid


def setup_assets_and_migration(
    mocked_responses: responses,
    resource_group_name: str,
    namespace_name: str,
    custom_location_id: str,
    asset_names: List[str],
    expect_migration: bool = True,
) -> List[dict]:
    """Setup asset records and migration endpoint."""
    # Create assets
    assets = [create_asset_record(name, resource_group_name, custom_location_id) for name in asset_names]

    # Mock Resource Graph query
    mocked_responses.add(
        method=responses.POST,
        url=ARG_ENDPOINT,
        json={"data": assets},
        status=200,
    )

    # Mock migration endpoint only if migration is expected
    if expect_migration and asset_names:
        mocked_responses.add(
            method=responses.POST,
            url=get_namespace_migrate_endpoint(resource_group_name, namespace_name),
            json={"id": "operation_id", "status": "Succeeded"},
            status=200,
        )

    return assets


def filter_assets(assets: List[dict], name_patterns: Optional[List[str]]) -> List[str]:
    """Filter assets based on name patterns and return their IDs."""
    if not name_patterns:
        return [asset["id"] for asset in assets]

    # Separate exact names from patterns
    exact_names = {p for p in name_patterns if not any(c in p for c in "*?[")}
    patterns = [p for p in name_patterns if any(c in p for c in "*?[")]

    result = []
    for asset in assets:
        name = asset["name"]
        if name in exact_names or any(fnmatch(name, p) for p in patterns):
            result.append(asset["id"])

    return result


def verify_migration_request(
    mocked_responses: responses,
    expected_asset_ids: List[str],
    mock_logger: Mock,
    correlation_id: str,
) -> None:
    """Verify the migration request was made correctly."""
    request = mocked_responses.calls[-1].request
    body = json.loads(request.body)

    assert set(body["resourceIds"]) == set(expected_asset_ids)
    assert body["scope"] == "Resources"
    assert request.headers["x-ms-correlation-request-id"] == correlation_id
    assert request.headers["CommandName"] == "iot ops migrate-assets"
    mock_logger.debug.assert_called_with(f"Migration correlation Id: {correlation_id}")


def verify_role_assignment_flow(
    mocked_responses: responses,
    role_assignment_scenario: dict,
    mock_logger_queryable: Mock,
) -> None:
    """Verify role assignment flow was executed correctly."""
    # Check if SP lookup was needed
    if not role_assignment_scenario.get("sp_oid"):
        mock_logger_queryable.debug.assert_any_call("Using aud: https://graph.microsoft.com")

    # Verify role assignment was checked
    ra_check_calls = [
        c for c in mocked_responses.calls if "roleAssignments" in c.request.url and c.request.method == "GET"
    ]
    assert len(ra_check_calls) == 1

    # Verify role assignment was created if it didn't exist
    if not role_assignment_scenario.get("ra_exists"):
        ra_put_calls = [
            c for c in mocked_responses.calls if "roleAssignments" in c.request.url and c.request.method == "PUT"
        ]
        assert len(ra_put_calls) == 1

        # Verify the role assignment payload
        ra_payload = json.loads(ra_put_calls[0].request.body)
        expected_role_def = generate_role_def_id(
            subscription_id=ZEROED_SUBSCRIPTION, role_id=KUBERNETES_ARC_CONTRIBUTOR_ROLE_ID
        )
        assert ra_payload["properties"]["roleDefinitionId"] == expected_role_def
        assert ra_payload["properties"]["principalType"] == "ServicePrincipal"


@pytest.fixture
def mock_console(mocker) -> Mock:
    """Mock console output."""
    return mocker.patch("azext_edge.edge.providers.orchestration.migration.console")


@pytest.fixture
def mock_logger(mocker) -> Mock:
    """Mock logger."""
    return mocker.patch("azext_edge.edge.providers.orchestration.migration.logger")


@pytest.fixture
def mock_logger_queryable(mocker) -> Mock:
    """Mock queryable logger."""
    return mocker.patch("azext_edge.edge.util.queryable.logger")


@pytest.fixture
def mock_correlation_id(mocker) -> str:
    """Mock UUID generation for correlation ID."""
    correlation_id = "test-correlation-id"
    mocker.patch("azext_edge.edge.providers.orchestration.migration.uuid4", return_value=correlation_id)
    return correlation_id


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
        # No matches - exact name
        (["nonexistent"], ["pump1", "valve1"], 0),
        # No matches - pattern
        (["sensor*"], ["pump1", "pump2"], 0),
        # Empty list with pattern
        (["*"], [], 0),
        # No assets - no filter
        (None, [], 0),
        # Complex patterns
        (["sensor[0-9]*", "valve?"], ["sensor123", "sensor456", "valve1", "valve2", "pump1"], 4),
        # Dash patterns
        (["device-*"], ["device-001", "device-002", "sensor-001"], 2),
    ],
)
def test_asset_filtering(
    mocked_cmd,
    mocked_responses: responses,
    mock_logger: Mock,
    mock_correlation_id: str,
    name_patterns: Optional[List[str]],
    asset_names: List[str],
    expected_count: int,
):
    """Test various asset filtering patterns."""
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    namespace_name = generate_random_string()

    _, custom_location_id = setup_base_resources(
        mocked_responses,
        instance_name,
        resource_group_name,
        namespace_name,
        generate_random_string(),
        generate_random_string(),
    )

    assets = setup_assets_and_migration(
        mocked_responses,
        resource_group_name,
        namespace_name,
        custom_location_id,
        asset_names,
        expect_migration=(expected_count > 0),
    )

    result = migrate_assets(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        name_patterns=name_patterns,
        confirm_yes=True,
        skip_role_assignments=True,
        wait_sec=0.1,
    )

    if expected_count > 0:
        assert result["status"] == "Succeeded"
        expected_ids = filter_assets(assets, name_patterns)
        verify_migration_request(mocked_responses, expected_ids, mock_logger, mock_correlation_id)
    else:
        assert result is None
        if not asset_names:
            mock_logger.warning.assert_called_with("No root assets are associated with the instance.")
        else:
            mock_logger.warning.assert_called_with("No root assets to migrate found.")


@pytest.mark.parametrize("asset_count", [1, 10, 100])
def test_asset_scale(
    mocked_cmd,
    mocked_responses: responses,
    mock_logger: Mock,
    mock_correlation_id: str,
    asset_count: int,
):
    """Test migration with different numbers of assets."""
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    namespace_name = generate_random_string()
    asset_names = [f"asset_{i}" for i in range(asset_count)]

    _, custom_location_id = setup_base_resources(
        mocked_responses,
        instance_name,
        resource_group_name,
        namespace_name,
        generate_random_string(),
        generate_random_string(),
    )

    assets = setup_assets_and_migration(
        mocked_responses,
        resource_group_name,
        namespace_name,
        custom_location_id,
        asset_names,
    )

    result = migrate_assets(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=True,
        skip_role_assignments=True,
        wait_sec=0.1,
    )

    assert result["status"] == "Succeeded"
    assert len(json.loads(mocked_responses.calls[-1].request.body)["resourceIds"]) == asset_count
    verify_migration_request(mocked_responses, [a["id"] for a in assets], mock_logger, mock_correlation_id)


@pytest.mark.parametrize(
    "scenario",
    [
        {"skip": True, "description": "Skip role assignments"},
        {"skip": False, "description": "Default flow"},
        {"skip": False, "sp_oid": generate_uuid(), "description": "User provides SP OID"},
        {"skip": False, "sp_lookup_fails": True, "should_fail": True, "description": "SP lookup fails"},
        {"skip": False, "ra_exists": True, "description": "Role assignment exists"},
    ],
)
def test_role_assignments(
    mocked_cmd,
    mocked_responses: responses,
    mock_logger_queryable: Mock,
    mock_correlation_id: str,
    mock_logger: Mock,
    scenario: Dict,
):
    """Test various role assignment scenarios."""
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    namespace_name = generate_random_string()

    _, custom_location_id = setup_base_resources(
        mocked_responses,
        instance_name,
        resource_group_name,
        namespace_name,
        generate_random_string(),
        generate_random_string(),
    )

    # Setup role assignment mocks if not skipping
    if not scenario.get("skip"):
        setup_role_assignment_mocks(
            mocked_responses,
            custom_location_id,
            adr_sp_oid=scenario.get("sp_oid"),
            sp_lookup_success=not scenario.get("sp_lookup_fails", False),
            ra_exists=scenario.get("ra_exists", False),
        )

    # Setup assets
    setup_assets_and_migration(
        mocked_responses,
        resource_group_name,
        namespace_name,
        custom_location_id,
        ["asset1", "asset2"],
        expect_migration=not scenario.get("should_fail", False),
    )

    # Execute migration
    if scenario.get("should_fail"):
        with pytest.raises(ValidationError, match="Unable to look up Device Registry"):
            migrate_assets(
                cmd=mocked_cmd,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
                confirm_yes=True,
                skip_role_assignments=False,
            )
        # Verify SP lookup was attempted
        mock_logger_queryable.debug.assert_any_call("Using aud: https://graph.microsoft.com")
    else:
        result = migrate_assets(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            confirm_yes=True,
            skip_role_assignments=scenario.get("skip", False),
            adr_sp_oid=scenario.get("sp_oid"),
            wait_sec=0.1,
        )
        assert result["status"] == "Succeeded"

        # Verify role assignment flow if not skipped
        if not scenario.get("skip"):
            verify_role_assignment_flow(mocked_responses, scenario, mock_logger_queryable)


@pytest.mark.parametrize(
    "ra_error_scenario",
    [
        {"error": Exception("Forbidden"), "error_msg": "Azure Kubernetes Service Arc Contributor Role"},
    ],
)
def test_role_assignment_errors(
    mocked_cmd,
    mocked_responses: responses,
    mocker,
    ra_error_scenario: Dict,
):
    """Test role assignment error handling."""
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    namespace_name = generate_random_string()

    # Mock permission manager to raise error
    mock_permission_manager = mocker.patch("azext_edge.edge.providers.orchestration.migration.PermissionManager")
    mock_permission_manager.return_value.apply_role_assignment.side_effect = ra_error_scenario["error"]

    _, custom_location_id = setup_base_resources(
        mocked_responses,
        instance_name,
        resource_group_name,
        namespace_name,
        generate_random_string(),
        generate_random_string(),
    )

    # Setup SP lookup mock
    mocked_responses.add(
        method=responses.GET,
        url=get_sp_fetch_endpoint(),
        json={"id": generate_uuid(), "appId": ADR_RP_APP_ID},
        status=200,
    )

    # Setup assets - don't expect migration as we'll error before that
    setup_assets_and_migration(
        mocked_responses,
        resource_group_name,
        namespace_name,
        custom_location_id,
        ["asset1"],
        expect_migration=False,
    )

    with pytest.raises(AzureResponseError) as exc_info:
        migrate_assets(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            confirm_yes=True,
            skip_role_assignments=False,
        )

    assert ra_error_scenario["error_msg"] in str(exc_info.value)


@pytest.mark.parametrize(
    "confirm_yes, user_continues, should_migrate",
    [
        (True, None, True),  # Auto-confirm
        (False, True, True),  # User confirms
        (False, False, False),  # User declines
    ],
)
def test_user_confirmation(
    mocked_cmd,
    mocked_responses: responses,
    mock_console: Mock,
    mock_logger: Mock,
    mock_correlation_id: str,
    mocker,
    confirm_yes: bool,
    user_continues: Optional[bool],
    should_migrate: bool,
):
    """Test user confirmation flow."""
    mock_prompt = mocker.patch(
        "azext_edge.edge.providers.orchestration.migration.should_continue_prompt",
        return_value=confirm_yes or user_continues,
    )

    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    namespace_name = generate_random_string()

    _, custom_location_id = setup_base_resources(
        mocked_responses,
        instance_name,
        resource_group_name,
        namespace_name,
        generate_random_string(),
        generate_random_string(),
    )

    assets = setup_assets_and_migration(
        mocked_responses,
        resource_group_name,
        namespace_name,
        custom_location_id,
        ["asset1", "asset2"],
        expect_migration=should_migrate,
    )

    result = migrate_assets(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=confirm_yes,
        skip_role_assignments=True,
        wait_sec=0.1,
    )

    mock_prompt.assert_called_once_with(confirm_yes=confirm_yes, context="Migration")

    if not confirm_yes:
        assert mock_console.print.call_count == 3
        mock_console.print_json.assert_called_once_with(data=[a["id"] for a in assets])

    assert (result is not None) == should_migrate
    if should_migrate:
        assert result["status"] == "Succeeded"
        verify_migration_request(mocked_responses, [a["id"] for a in assets], mock_logger, mock_correlation_id)


@pytest.mark.parametrize(
    "error_scenario",
    [
        {"has_namespace": False, "error_match": "does not have an associated ADR namespace"},
        {"cluster_connected": False, "error_match": "is not connected"},
        {
            "instance_version": "1.2.35",
            "error_match": f"must be at least version {MIN_INSTANCE_VERSION_FOR_MIGRATE} to migrate assets",
        },
        {
            "instance_version": "1.0.0",
            "error_match": f"must be at least version {MIN_INSTANCE_VERSION_FOR_MIGRATE} to migrate assets",
        },
        {
            "instance_version": "0.0.0",
            "error_match": f"must be at least version {MIN_INSTANCE_VERSION_FOR_MIGRATE} to migrate assets",
        },
    ],
)
def test_validation_errors(
    mocked_cmd,
    mocked_responses: responses,
    error_scenario: Dict,
):
    """Test validation error scenarios."""
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    setup_base_resources(
        mocked_responses,
        instance_name,
        resource_group_name,
        generate_random_string() if error_scenario.get("has_namespace", True) else "",
        generate_random_string(),
        generate_random_string(),
        has_namespace=error_scenario.get("has_namespace", True),
        cluster_connected=error_scenario.get("cluster_connected", True),
        instance_version=error_scenario.get("instance_version", MIN_INSTANCE_VERSION_FOR_MIGRATE),
    )

    with pytest.raises(ValidationError, match=error_scenario["error_match"]):
        migrate_assets(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            confirm_yes=True,
        )


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
    """Test resource not found scenarios."""
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    setup_base_resources(
        mocked_responses,
        instance_name,
        resource_group_name,
        generate_random_string(),
        generate_random_string(),
        generate_random_string(),
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
