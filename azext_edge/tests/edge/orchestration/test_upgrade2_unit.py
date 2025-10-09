# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import re
from copy import deepcopy
from typing import Dict, List, Optional, Tuple, TypeVar
from unittest.mock import Mock, patch

import pytest
import requests
import responses
from azure.cli.core.azclierror import ValidationError
from azure.core.exceptions import HttpResponseError

from azext_edge.edge.providers.orchestration.common import (
    EXTENSION_ALIAS_TO_TYPE_MAP,
    EXTENSION_MONIKER_OPS,
    EXTENSION_TYPE_ACS,
    EXTENSION_TYPE_CM,
    EXTENSION_TYPE_OPS,
    EXTENSION_TYPE_PLATFORM,
    EXTENSION_TYPE_SSC,
    EXTENSION_TYPE_TO_MONIKER_MAP,
    MIN_INSTANCE_VERSION_FOR_CM_MIGRATE,
    PROVISIONING_STATE_FAILED,
    PROVISIONING_STATE_SUCCESS,
    ClusterConnectStatus,
    ConfigSyncModeType,
)
from azext_edge.edge.providers.orchestration.targets import InitTargets
from azext_edge.edge.util import parse_kvp_nargs

from ...generators import generate_random_string
from .resources.conftest import (
    BASE_URL,
    CLUSTER_EXTENSIONS_API_VERSION,
    CLUSTER_EXTENSIONS_URL_MATCH_RE,
    CONNECTED_CLUSTER_API_VERSION,
    get_base_endpoint,
    get_mock_resource,
)
from .resources.registry_endpoint.test_registry_endpoints_unit import (
    get_registry_endpoint_endpoint,
)
from .resources.test_instances_unit import (
    get_instance_endpoint,
    get_mock_cl_record,
    get_mock_instance_record,
)

T = TypeVar("T", bound="UpgradeScenario")
STANDARD_HEADERS = {"content-type": "application/json"}

BUILT_IN_VALUE = "x.y.z"

DEFAULT_RETRY_COUNT = 4  # 1 initial + 3 retries
DEFAULT_LOG_WARNING_MESSAGE = "Nothing to upgrade :)"
HTTP_STATUS_OK = 200
HTTP_STATUS_ACCEPTED = 202
HTTP_STATUS_SERVICE_ERROR = 500
HTTP_STATUS_SERVICE_UNAVAILABLE = 503

expected_default_registry = {
    "name": "default",
    "type": "Microsoft.IoTOperations/instances/registryEndpoints",
    "properties": {
        "host": "mcr.microsoft.com",
        "authentication": {"method": "Anonymous", "anonymousSettings": {}},
        "provisioningState": "Succeeded",
    },
}


def expects_registry_creation(target_scenario: "UpgradeScenario") -> bool:
    return (
        hasattr(target_scenario, "aux_kwargs")
        and target_scenario.aux_kwargs.get("default_registry_exists") is False
        and target_scenario.user_kwargs.get("ops_version", "") >= MIN_INSTANCE_VERSION_FOR_CM_MIGRATE
    )


def get_mock_cluster_record(
    resource_group_name: str,
    name: str = "mycluster",
    connected_status: str = ClusterConnectStatus.CONNECTED.value,
) -> dict:
    return get_mock_resource(
        name=name,
        properties={"connectivityStatus": connected_status},
        resource_group_name=resource_group_name,
    )


def get_cluster_endpoint(resource_group_name: str, name: str = "mycluster") -> dict:
    resource_path = "/connectedClusters"
    if name:
        resource_path += f"/{name}"
    endpoint = get_base_endpoint(
        resource_group_name=resource_group_name,
        resource_path=resource_path,
        resource_provider="Microsoft.Kubernetes",
        api_version=CONNECTED_CLUSTER_API_VERSION,
    )
    endpoint = endpoint.replace("/resourceGroups/", "/resourcegroups/", 1)
    return endpoint


def get_cluster_extensions_endpoint(resource_group_name: str, cluster_name: str = "mycluster") -> dict:
    resource_path = f"/connectedClusters/{cluster_name}/providers/Microsoft.KubernetesConfiguration/extensions"
    return get_base_endpoint(
        resource_group_name=resource_group_name,
        resource_path=resource_path,
        resource_provider="Microsoft.Kubernetes",
        api_version=CLUSTER_EXTENSIONS_API_VERSION,
    )


@pytest.fixture
def mocked_logger(mocker):
    yield mocker.patch(
        "azext_edge.edge.providers.orchestration.upgrade2.logger",
    )


@pytest.fixture
def spy_upgrade_displays(mocker):
    from azext_edge.edge.providers.orchestration.upgrade2 import Console, Progress

    yield {
        "print": mocker.spy(Console, "print"),
        "progress.__init__": mocker.spy(Progress, "__init__"),
    }


@pytest.fixture
def mocked_upgrade_manager():
    # Patch InitTargets.get_extension_versions to return stable trains for testing
    original_get_extension_versions = InitTargets.get_extension_versions

    def patched_get_extension_versions(self, for_enablement=True):
        versions = original_get_extension_versions(self, for_enablement)
        # Override non-stable trains for IoT Operations only
        if EXTENSION_MONIKER_OPS in versions and versions[EXTENSION_MONIKER_OPS].get("train", "").lower() != "stable":
            versions[EXTENSION_MONIKER_OPS]["train"] = "stable"
        return versions

    with patch.object(InitTargets, "get_extension_versions", patched_get_extension_versions) as mock:
        yield mock


class UpgradeScenario:
    def __init__(self, description: Optional[str] = None, confirm_yes: bool = True):
        self.extensions: Dict[str, dict] = {}
        self.targets = InitTargets(cluster_name=generate_random_string(), resource_group_name=generate_random_string())
        self.init_version_map: Dict[str, dict] = {
            **self.targets.get_extension_versions(),
            **self.targets.get_extension_versions(False),
        }
        self.user_kwargs: Dict[str, dict] = {}
        self.patch_record: Dict[str, dict] = {}
        self.ext_type_response_map: Dict[str, Tuple[int, Optional[dict], Optional[dict]]] = {}
        self.expect_exception: Optional[Exception] = None
        self.expect_exception_match: Optional[str] = None
        self.last_correlation_id: str = ""
        self.description = description
        self.confirm_yes = confirm_yes
        self.cluster_connected_status = ClusterConnectStatus.CONNECTED.value
        self.delete_record: Dict[str, bool] = {}
        self.create_record: Dict[str, dict] = {}
        self.patch_call_count = 0
        self.instance_adr_namespace_resource_id: Optional[str] = None
        self.expect_instance_update = False
        self.remove_adr_for_test = False

        self._build_defaults()

    def _build_defaults(self):
        for ext_type in EXTENSION_TYPE_TO_MONIKER_MAP:
            # Skip platform (deprecated) and ACS (optional)
            if ext_type in [EXTENSION_TYPE_ACS, EXTENSION_TYPE_PLATFORM]:
                continue

            ext_moniker = EXTENSION_TYPE_TO_MONIKER_MAP[ext_type]
            vers = self.init_version_map[ext_moniker]["version"]
            train = self.init_version_map[ext_moniker]["train"]

            # Override train to "stable" for IoT Operations extension in test defaults
            # to avoid triggering the preview train validation during tests
            if ext_type == EXTENSION_TYPE_OPS and train.lower() != "stable":
                train = "stable"

            self.extensions[ext_type] = {
                "properties": {
                    "extensionType": ext_type,
                    "version": vers,
                    "releaseTrain": train,
                    "configurationSettings": {},
                    "provisioningState": PROVISIONING_STATE_SUCCESS,
                },
                "name": ext_moniker,
            }

    def set_cluster_connected_status(self: T, status: str) -> T:
        self.cluster_connected_status = status
        if status != ClusterConnectStatus.CONNECTED.value:
            self.expect_exception = ValidationError
        return self

    def set_user_kwargs(self: T, **kwargs) -> T:
        if "ns_resource_id" in kwargs:
            self.instance_adr_namespace_resource_id = kwargs["ns_resource_id"]
        self.user_kwargs.update(kwargs)
        return self

    def set_expected_exception(self: T, exc: Exception, match: Optional[str] = None) -> T:
        self.expect_exception = exc
        self.expect_exception_match = match
        return self

    def set_extension(
        self: T,
        ext_type: str,
        ext_vers: Optional[str] = None,
        ext_train: Optional[str] = None,
        config_settings: Optional[dict] = None,
        provisioning_state: Optional[str] = None,
        remove: bool = False,
    ) -> T:
        if remove:
            if ext_type in self.extensions:
                del self.extensions[ext_type]
            # Only expect ValidationError if removing IoT Ops
            if ext_type == EXTENSION_TYPE_OPS:
                self.expect_exception = ValidationError
            return self

        # Create extension if it doesn't exist (for adding platform in tests)
        if ext_type not in self.extensions:
            ext_moniker = EXTENSION_TYPE_TO_MONIKER_MAP[ext_type]
            # Get version from init_version_map or use defaults
            default_vers = self.init_version_map.get(ext_moniker, {}).get("version", "1.0.0")
            default_train = self.init_version_map.get(ext_moniker, {}).get("train", "stable")

            self.extensions[ext_type] = {
                "properties": {
                    "extensionType": ext_type,
                    "version": ext_vers or default_vers,
                    "releaseTrain": ext_train or default_train,
                    "configurationSettings": config_settings or {},
                    "provisioningState": provisioning_state or PROVISIONING_STATE_SUCCESS,
                },
                "name": ext_moniker,
            }
        else:
            # Update existing extension
            if ext_vers:
                if ext_vers == BUILT_IN_VALUE:
                    ext_vers = self.init_version_map[EXTENSION_TYPE_TO_MONIKER_MAP[ext_type]]["version"]
                self.extensions[ext_type]["properties"]["version"] = ext_vers
            if ext_train:
                self.extensions[ext_type]["properties"]["releaseTrain"] = ext_train
            if provisioning_state:
                self.extensions[ext_type]["properties"]["provisioningState"] = provisioning_state
            if config_settings is not None:
                self.extensions[ext_type]["properties"]["configurationSettings"] = config_settings
        return self

    def set_response_on_patch(
        self: T, ext_type: str, code: int = HTTP_STATUS_OK, body: Optional[dict] = None, headers: Optional[dict] = None
    ) -> T:
        if code not in (HTTP_STATUS_OK, HTTP_STATUS_ACCEPTED):
            self.expect_exception = HttpResponseError
        if not headers:
            headers = {}
        self.ext_type_response_map[ext_type] = (code, body, headers)
        return self

    def set_auxiliary_kwargs(self: T, **kwargs):
        if "remove_adr_for_test" in kwargs:
            self.remove_adr_for_test = kwargs["remove_adr_for_test"]
        if "expect_instance_update" in kwargs:
            self.expect_instance_update = kwargs["expect_instance_update"]
        if "default_registry_exists" in kwargs:
            self.default_registry_exists = kwargs["default_registry_exists"]
        if "registry_list_error" in kwargs:
            self.registry_list_error = kwargs["registry_list_error"]

        self.aux_kwargs = kwargs
        return self

    def set_instance_mock(self: T, mocked_responses: responses, instance_name: str, resource_group_name: str) -> T:
        mocked_responses.assert_all_requests_are_fired = False

        # Always use version 1.2.0+ (which includes ADR namespace)
        # unless explicitly testing scenario without ADR
        if self.remove_adr_for_test:
            # Explicitly create instance without ADR namespace for testing
            mock_instance_record = get_mock_instance_record(
                name=instance_name,
                resource_group_name=resource_group_name,
                version="1.1.15",
            )
        else:
            mock_instance_record = get_mock_instance_record(
                name=instance_name,
                resource_group_name=resource_group_name,
                version="1.2.0",  # >= 1.2.0, includes ADR namespace
                adr_namespace_name="default-adr",
            )

        mocked_responses.add(
            method=responses.GET,
            url=get_instance_endpoint(resource_group_name=resource_group_name, instance_name=instance_name),
            json=mock_instance_record,
            status=200,
            content_type="application/json",
        )

        # Add instance update mock if expected
        if self.expect_instance_update:

            def instance_update_callback(request):
                return (200, STANDARD_HEADERS, request.body)

            mocked_responses.add_callback(
                method=responses.PUT,
                url=get_instance_endpoint(resource_group_name=resource_group_name, instance_name=instance_name),
                callback=instance_update_callback,
            )

        cl_name = generate_random_string()
        mock_cl_record = get_mock_cl_record(name=cl_name, resource_group_name=resource_group_name)
        mocked_responses.add(
            method=responses.GET,
            url=f"{BASE_URL}{mock_instance_record['extendedLocation']['name']}",
            json=mock_cl_record,
            status=200,
            content_type="application/json",
        )

        mock_cluster_record = get_mock_cluster_record(
            resource_group_name=resource_group_name, connected_status=self.cluster_connected_status
        )
        mocked_responses.add(
            method=responses.GET,
            url=get_cluster_endpoint(resource_group_name=resource_group_name),
            json=mock_cluster_record,
            status=200,
            content_type="application/json",
        )
        mocked_responses.add(
            method=responses.GET,
            url=get_cluster_extensions_endpoint(resource_group_name=resource_group_name),
            json={"value": self.get_extensions()},
            status=200,
            content_type="application/json",
        )

        mocked_responses.add_callback(
            method=responses.PATCH,
            url=re.compile(CLUSTER_EXTENSIONS_URL_MATCH_RE),
            callback=self.patch_extension_response,
        )
        mocked_responses.add_callback(
            method=responses.DELETE,
            url=re.compile(CLUSTER_EXTENSIONS_URL_MATCH_RE),
            callback=self.delete_extension_response,
        )
        mocked_responses.add_callback(
            method=responses.PUT,
            url=re.compile(CLUSTER_EXTENSIONS_URL_MATCH_RE),
            callback=self.create_extension_response,
        )

        # Always setup registry endpoint mocks when IoT Ops extension exists
        # The upgrade code checks registry endpoints when target version >= migration version
        if EXTENSION_TYPE_OPS in self.extensions:
            self._setup_registry_endpoint_mocks(mocked_responses, instance_name, resource_group_name)

        return self

    def _setup_registry_endpoint_mocks(self, mocked_responses: responses, instance_name: str, resource_group_name: str):
        """Set up registry endpoint mocks for tests.

        By default:
        - GET returns a default registry endpoint (simulating it already exists)
        - PUT is mocked to handle any creation attempts

        This can be overridden via auxiliary kwargs for specific test scenarios.
        """
        list_endpoint = get_registry_endpoint_endpoint(
            instance_name=instance_name, resource_group_name=resource_group_name
        )

        # Check if we have explicit test configuration
        has_explicit_config = hasattr(self, "aux_kwargs")
        registry_list_error = has_explicit_config and self.aux_kwargs.get("registry_list_error", False)
        default_exists = has_explicit_config and self.aux_kwargs.get("default_registry_exists", False)

        if registry_list_error:
            # Simulate an error when listing endpoints
            mocked_responses.add(
                method=responses.GET,
                url=list_endpoint,
                status=500,
                json={"error": {"message": "Failed to list registry endpoints", "code": "InternalServerError"}},
                content_type="application/json",
            )
        else:
            # Determine what to return for GET request
            existing_endpoints = []

            # Add default endpoint if:
            # 1. Explicitly configured to exist (default_registry_exists=True), OR
            # 2. No explicit configuration (simulate it exists to prevent unwanted creation)
            if default_exists or not has_explicit_config:
                # Use the global expected_default_registry and add the ID
                endpoint = deepcopy(expected_default_registry)
                endpoint["id"] = f"{list_endpoint}/default"
                existing_endpoints.append(endpoint)

            mocked_responses.add(
                method=responses.GET,
                url=list_endpoint,
                json={"value": existing_endpoints},
                status=200,
                content_type="application/json",
            )

        # Always add PUT mock to handle creation attempts
        # This prevents "Connection refused" errors for any test where creation might be attempted
        create_endpoint = get_registry_endpoint_endpoint(
            instance_name=instance_name, resource_group_name=resource_group_name, registry_endpoint_name="default"
        )

        def registry_create_callback(request):
            assert_upgrade_headers(request.headers)
            self.last_correlation_id = request.headers.get("x-ms-correlation-request-id")

            # Parse body to verify correct payload
            body = json.loads(request.body)
            assert "properties" in body
            assert body["properties"]["host"] == expected_default_registry["properties"]["host"]
            assert body["properties"]["authentication"] == expected_default_registry["properties"]["authentication"]

            # Return the created endpoint (reuse expected_default_registry)
            response_body = deepcopy(expected_default_registry)
            response_body["id"] = create_endpoint

            return (200, STANDARD_HEADERS, json.dumps(response_body))

        mocked_responses.add_callback(
            method=responses.PUT,
            url=create_endpoint,
            callback=registry_create_callback,
        )

    def delete_extension_response(self, request: requests.PreparedRequest) -> Optional[tuple]:
        ext_moniker = request.path_url.split("?")[0].split("/")[-1]
        assert_upgrade_headers(request.headers)
        self.last_correlation_id = request.headers.get("x-ms-correlation-request-id")

        for ext_type in EXTENSION_TYPE_TO_MONIKER_MAP:
            if EXTENSION_TYPE_TO_MONIKER_MAP[ext_type] == ext_moniker:
                self.delete_record[ext_type] = True
                return (204, STANDARD_HEADERS, "")

        return (HTTP_STATUS_SERVICE_UNAVAILABLE, STANDARD_HEADERS, json.dumps({"error": "server error"}))

    def create_extension_response(self, request: requests.PreparedRequest) -> Optional[tuple]:
        assert_upgrade_headers(request.headers)
        self.last_correlation_id = request.headers.get("x-ms-correlation-request-id")

        # Parse the body to get the extension type
        body = json.loads(request.body)
        ext_type = body.get("properties", {}).get("extensionType")

        if ext_type:
            self.create_record[ext_type] = body
            # Return the created extension as if it was successful
            return (HTTP_STATUS_OK, STANDARD_HEADERS, json.dumps(body))

        return (HTTP_STATUS_SERVICE_UNAVAILABLE, STANDARD_HEADERS, json.dumps({"error": "server error"}))

    def patch_extension_response(self, request: requests.PreparedRequest) -> Optional[tuple]:
        self.patch_call_count += 1  # Increment counter for retry testing
        ext_moniker = request.path_url.split("?")[0].split("/")[-1]
        assert_upgrade_headers(request.headers)
        self.last_correlation_id = request.headers.get("x-ms-correlation-request-id")
        for ext_type in EXTENSION_TYPE_TO_MONIKER_MAP:
            if EXTENSION_TYPE_TO_MONIKER_MAP[ext_type] == ext_moniker:
                self.patch_record[ext_type] = json.loads(request.body)

                # Check if we have a specific response configured for this extension type
                if ext_type in self.ext_type_response_map:
                    code, body, headers = self.ext_type_response_map[ext_type]
                    if not body:
                        body = self.patch_record[ext_type]
                    return (code, {**STANDARD_HEADERS, **headers}, json.dumps(body) if body else "")

                # Default success response - ensure extensionType is included
                response_body = self.patch_record[ext_type]
                # Add extensionType if not present (patch requests might only send changed fields)
                if "properties" not in response_body:
                    response_body = {"properties": response_body}
                if "extensionType" not in response_body["properties"]:
                    response_body["properties"]["extensionType"] = ext_type

                return (HTTP_STATUS_OK, STANDARD_HEADERS, json.dumps(response_body))

        return (HTTP_STATUS_SERVICE_UNAVAILABLE, STANDARD_HEADERS, json.dumps({"error": "server error"}))

    def get_extensions(self) -> List[dict]:
        return list(self.extensions.values())

    def with_failed_extension(self: T, ext_type: str) -> T:
        return self.set_extension(
            ext_type=ext_type, ext_vers=BUILT_IN_VALUE, provisioning_state=PROVISIONING_STATE_FAILED
        )

    def expecting_validation_error(self: T, match: Optional[str] = None) -> T:
        return self.set_expected_exception(ValidationError, match=match)


def build_extension_props(ext_type: str, version: str = None, train: str = None, config: dict = None) -> dict:
    """Build standard extension properties dict."""
    props = {"properties": {"extensionType": ext_type}}
    if version:
        props["properties"]["version"] = version
    if train:
        props["properties"]["releaseTrain"] = train
    if config:
        props["properties"]["configurationSettings"] = config
    return props


def assert_upgrade_headers(headers: Dict[str, str]):
    assert headers.get("User-Agent").startswith("IotOperationsCliExtension/")
    assert headers.get("Accept") == "application/json"
    # DELETE requests have no body, so no Content-Type header
    if headers.get("Content-Length") != "0":
        assert headers.get("Content-Type") == "application/json"
    assert headers.get("x-ms-correlation-request-id")
    assert headers.get("x-ms-client-request-id")
    assert headers.get("CommandName")


def assert_no_upgrades_performed(upgrade_result, logger_mock):
    assert upgrade_result is None
    logger_mock.warning.assert_called_once_with(DEFAULT_LOG_WARNING_MESSAGE)


def assert_retry_count(mock_response, expected_count: int = DEFAULT_RETRY_COUNT):
    assert len(mock_response.calls) == expected_count


def assert_operation_order(target_scenario: UpgradeScenario, upgrade_result: List[dict]):
    """Assert operations happen in correct order: DELETE -> CREATE -> UPDATE -> INSTANCE_UPDATE -> REGISTRY_CREATE.
    Also validates extension type order within each operation group."""

    # Group results by operation type
    deletes = []
    creates = []
    updates = []
    instance_updates = []
    registry_creates = []

    for result in upgrade_result:
        props = result.get("properties", {})
        ext_type = props.get("extensionType")

        # Check if this is a registry endpoint creation
        if (
            result.get("name") == "default"
            and result.get("type") == "Microsoft.IoTOperations/instances/registryEndpoints"
        ):
            registry_creates.append(result)
            continue

        # Check if this is an instance update (has adrNamespaceRef but no extensionType)
        if not ext_type and "adrNamespaceRef" in props:
            instance_updates.append(result)
            continue

        # Skip if no extension type and not an instance update or registry endpoint
        if not ext_type:
            continue

        if props.get("provisioningState") == "Deleted":
            deletes.append(ext_type)
        elif ext_type in target_scenario.create_record:
            creates.append(ext_type)
        else:
            updates.append(ext_type)

    # Verify operation groups match scenario expectations
    assert set(deletes) == set(
        target_scenario.delete_record.keys()
    ), f"DELETE operations mismatch. Expected {set(target_scenario.delete_record.keys())}, got {set(deletes)}"
    assert set(creates) == set(
        target_scenario.create_record.keys()
    ), f"CREATE operations mismatch. Expected {set(target_scenario.create_record.keys())}, got {set(creates)}"

    # If instance update is expected, verify it exists
    if target_scenario.expect_instance_update:
        assert len(instance_updates) == 1, "Expected exactly one instance update"

    # If registry creation is expected, verify it's last
    if expects_registry_creation(target_scenario):
        assert len(registry_creates) == 1, "Expected exactly one registry endpoint creation"
        # Verify it's the last operation in the result list
        if len(upgrade_result) > 0:
            last_result = upgrade_result[-1]
            assert last_result.get("name") == "default", "Registry endpoint creation should be last operation"

    # Build the actual operation sequence (non-empty groups only)
    operation_sequence = []
    if deletes:
        operation_sequence.append(("DELETE", deletes))
    if creates:
        operation_sequence.append(("CREATE", creates))
    if updates:
        operation_sequence.append(("UPDATE", updates))

    # Verify operations are in the correct order (DELETE -> CREATE -> UPDATE)
    operation_types = [op[0] for op in operation_sequence]
    expected_order = ["DELETE", "CREATE", "UPDATE"]
    expected_types = [op for op in expected_order if op in operation_types]

    assert (
        operation_types == expected_types
    ), f"Operations not in correct order. Expected {expected_types}, got {operation_types}"

    # Within UPDATE operations, verify extension type order matches EXTENSION_TYPE_TO_MONIKER_MAP
    if updates:
        expected_update_order = [ext for ext in EXTENSION_TYPE_TO_MONIKER_MAP.keys() if ext in updates]
        assert (
            updates == expected_update_order
        ), f"UPDATE operations not in expected extension order. Expected {expected_update_order}, got {updates}"


@pytest.mark.parametrize("no_progress", [False, True])
@pytest.mark.parametrize(
    "target_scenario,expected_patched_ext_types",
    [
        # ========== No-op scenarios - Nothing to upgrade ==========
        (UpgradeScenario("No-op: All extensions at desired versions"), {}),
        (
            UpgradeScenario("No-op: Extension ahead of desired version").set_extension(
                ext_type=EXTENSION_TYPE_CM, ext_vers="9.9.9"
            ),
            {},
        ),
        (
            UpgradeScenario("No-op: Version ahead with different train").set_extension(
                ext_type=EXTENSION_TYPE_OPS, ext_vers="9.9.9", ext_train="custom-train"
            ),
            {},
        ),
        # ========== Train-only updates (version unchanged) ==========
        (
            UpgradeScenario("Train update: Auto-increment when version matches desired").set_extension(
                ext_type=EXTENSION_TYPE_OPS, ext_train="old-train"
            ),
            {EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, train=BUILT_IN_VALUE)},
        ),
        (
            UpgradeScenario("Train update: Explicit train override").set_user_kwargs(ops_train="custom-train"),
            {EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, train="custom-train")},
        ),
        (
            UpgradeScenario("Train update: No auto-increment with explicit version")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_train="old-train")
            .set_user_kwargs(ops_version="9.9.9", force=True),
            {EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version="9.9.9")},
        ),
        # ========== Standard version upgrades ==========
        (
            UpgradeScenario("Version upgrade: Non-ops extension").set_extension(
                ext_type=EXTENSION_TYPE_CM, ext_vers="0.5.0"
            ),
            {EXTENSION_TYPE_CM: build_extension_props(EXTENSION_TYPE_CM, version=BUILT_IN_VALUE)},
        ),
        (
            UpgradeScenario("Version upgrade: Compatible ops upgrade")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.1.0")
            .set_user_kwargs(ops_version="1.2.0"),
            {EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version="1.2.0")},
        ),
        (
            UpgradeScenario("Version upgrade: Dev version string")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.1.0-main.20250425.8")
            .set_user_kwargs(ops_version="1.1.0-main.20250425.9"),
            {EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version="1.1.0-main.20250425.9")},
        ),
        # ========== Downgrade validation ==========
        (
            UpgradeScenario("Downgrade blocked: Any extension")
            .set_extension(ext_type=EXTENSION_TYPE_CM, ext_vers="1.0.0")
            .set_user_kwargs(cm_version="0.9.9")
            .expecting_validation_error(r"is a downgrade which is not supported"),
            {},
        ),
        (
            UpgradeScenario("Downgrade allowed with force")
            .set_extension(ext_type=EXTENSION_TYPE_CM, ext_vers="1.0.0")
            .set_user_kwargs(cm_version="0.9.9", force=True),
            {EXTENSION_TYPE_CM: build_extension_props(EXTENSION_TYPE_CM, version="0.9.9")},
        ),
        # ========== Major version validation (ops only) ==========
        (
            UpgradeScenario("Major version blocked: Different major")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="0.1.0")
            .set_user_kwargs(ops_version="1.0.0")
            .expecting_validation_error(r"incompatible \(different major version\)"),
            {},
        ),
        (
            UpgradeScenario("Major version allowed with force")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="0.1.0")
            .set_user_kwargs(ops_version="1.0.0", force=True),
            {EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version="1.0.0")},
        ),
        # ========== Minor version gap validation (ops only) ==========
        (
            UpgradeScenario("Minor version blocked: More than 2 versions ahead")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.0.0")
            .set_user_kwargs(ops_version="1.3.0")
            .expecting_validation_error(r"incompatible \(more than 2 minor versions ahead\)"),
            {},
        ),
        (
            UpgradeScenario("Minor version allowed: Exactly 2 versions ahead")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.0.0")
            .set_user_kwargs(ops_version="1.2.0"),
            {EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version="1.2.0")},
        ),
        (
            UpgradeScenario("Minor version allowed with force: 3+ versions")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.0.0")
            .set_user_kwargs(ops_version="1.3.0", force=True),
            {EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version="1.3.0")},
        ),
        # ========== Minimum version requirement for v2 (ops only) ==========
        (
            UpgradeScenario("Min v2 blocked: From 1.0.0 to 1.2.36")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.0.0")
            .set_user_kwargs(ops_version="1.2.36")
            .expecting_validation_error(r"min compatible upgrade version.*1\.1\.59"),
            {},
        ),
        (
            UpgradeScenario("Min v2 blocked: From 1.1.58 to 1.2.36")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.1.58")
            .set_user_kwargs(ops_version="1.2.36")
            .expecting_validation_error(r"min compatible upgrade version.*1\.1\.59"),
            {},
        ),
        (
            UpgradeScenario("Min v2 allowed: From 1.1.59 to 1.2.36")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.1.59")
            .set_user_kwargs(ops_version="1.2.36"),
            {EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version="1.2.36")},
        ),
        (
            UpgradeScenario("Min v2 allowed: From 1.2.0 to 1.2.36")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(ops_version="1.2.36"),
            {EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version="1.2.36")},
        ),
        (
            UpgradeScenario("Min v2 not checked: Target below 1.2.36")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.0.0")
            .set_user_kwargs(ops_version="1.2.35"),
            {EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version="1.2.35")},
        ),
        (
            UpgradeScenario("Min v2 allowed with force")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.0.0")
            .set_user_kwargs(ops_version="1.2.36", force=True),
            {EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version="1.2.36")},
        ),
        # ========== Preview train validation (blocks all changes except identical version+train) ==========
        (
            UpgradeScenario("Preview train blocked: From preview to stable with version change")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.0.0", ext_train="preview")
            .set_user_kwargs(ops_version="1.1.0")
            .expecting_validation_error(r"Upgrades to or from non-stable release trains are not supported"),
            {},
        ),
        (
            UpgradeScenario("Preview train blocked: From stable to preview with version change")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.0.0", ext_train="stable")
            .set_user_kwargs(ops_version="1.1.0", ops_train="preview")
            .expecting_validation_error(r"Upgrades to or from non-stable release trains are not supported"),
            {},
        ),
        (
            UpgradeScenario("Preview train blocked: Same version different train")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.1.0", ext_train="stable")
            .set_user_kwargs(ops_version="1.1.0", ops_train="preview")
            .expecting_validation_error(r"Upgrades to or from non-stable release trains are not supported"),
            {},
        ),
        (
            UpgradeScenario("Preview train blocked: Preview to different preview with same version")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.1.0", ext_train="preview")
            .set_user_kwargs(ops_version="1.1.0", ops_train="canary")
            .expecting_validation_error(r"Upgrades to or from non-stable release trains are not supported"),
            {},
        ),
        (
            UpgradeScenario("Preview train blocked: Preview to preview with version change")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.0.0", ext_train="preview")
            .set_user_kwargs(ops_version="1.1.0", ops_train="preview")
            .expecting_validation_error(r"Upgrades to or from non-stable release trains are not supported"),
            {},
        ),
        (
            UpgradeScenario("Preview train allowed: Identical version and train")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.1.0", ext_train="preview")
            .set_user_kwargs(ops_version="1.1.0", ops_train="preview"),
            {EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version="1.1.0", train="preview")},
        ),
        (
            UpgradeScenario("Preview train allowed with force")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.0.0", ext_train="preview")
            .set_user_kwargs(ops_version="1.1.0", ops_train="stable", force=True),
            {EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version="1.1.0", train="stable")},
        ),
        # ========== Configuration updates ==========
        (
            UpgradeScenario("Config update: Single setting").set_user_kwargs(ops_config=["a=b"]),
            {EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, config={"a": "b"})},
        ),
        (
            UpgradeScenario("Config update: Multiple settings").set_user_kwargs(ssc_config=["c=d", "e=f"]),
            {EXTENSION_TYPE_SSC: build_extension_props(EXTENSION_TYPE_SSC, config={"c": "d", "e": "f"})},
        ),
        (
            UpgradeScenario("Config update: Empty config no-op").set_user_kwargs(ops_config=[]),
            {},
        ),
        # ========== Failed state recovery ==========
        (
            UpgradeScenario("Failed state: Re-apply current version").with_failed_extension(EXTENSION_TYPE_OPS),
            {EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version=BUILT_IN_VALUE)},
        ),
        (
            UpgradeScenario("Failed state: With version upgrade")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.0.0", provisioning_state=PROVISIONING_STATE_FAILED)
            .set_user_kwargs(ops_version="1.1.0"),
            {EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version="1.1.0")},
        ),
        (
            UpgradeScenario("Failed state: With preview train and version change")
            .set_extension(
                ext_type=EXTENSION_TYPE_OPS,
                ext_vers="1.0.0",
                ext_train="preview",
                provisioning_state=PROVISIONING_STATE_FAILED,
            )
            .set_user_kwargs(ops_version="1.1.0")
            .expecting_validation_error(r"Upgrades to or from non-stable release trains are not supported"),
            {},
        ),
        (
            UpgradeScenario("Failed state: Preview train allowed with force")
            .set_extension(
                ext_type=EXTENSION_TYPE_OPS,
                ext_vers="1.0.0",
                ext_train="preview",
                provisioning_state=PROVISIONING_STATE_FAILED,
            )
            .set_user_kwargs(ops_version="1.1.0", force=True),
            {EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version="1.1.0")},
        ),
        # ========== Multi-extension scenarios ==========
        (
            UpgradeScenario("Multi-extension: All upgradeable")
            .set_extension(ext_type=EXTENSION_TYPE_CM, ext_vers="0.5.0")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_SSC, ext_vers="0.3.0")
            .set_user_kwargs(ops_version="1.1.0"),
            {
                EXTENSION_TYPE_CM: build_extension_props(EXTENSION_TYPE_CM, version=BUILT_IN_VALUE),
                EXTENSION_TYPE_SSC: build_extension_props(EXTENSION_TYPE_SSC, version=BUILT_IN_VALUE),
                EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version="1.1.0"),
            },
        ),
        (
            UpgradeScenario("Multi-extension: Mixed overrides")
            .set_extension(ext_type=EXTENSION_TYPE_SSC, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="0.1.0")
            .set_user_kwargs(
                ssc_config=["c=d"],
                ssc_version="1.1.1",
                ssc_train="custom",
                force=True,
            ),
            {
                EXTENSION_TYPE_SSC: build_extension_props(
                    EXTENSION_TYPE_SSC, version="1.1.1", train="custom", config={"c": "d"}
                ),
                EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version=BUILT_IN_VALUE),
            },
        ),
        # ========== Error scenarios ==========
        (
            UpgradeScenario("Error: Cluster not connected")
            .set_extension(ext_type=EXTENSION_TYPE_CM, ext_vers="0.5.0")
            .set_cluster_connected_status("Disconnected"),
            {},
        ),
        (
            UpgradeScenario("Error: IoT Ops extension missing").set_extension(ext_type=EXTENSION_TYPE_OPS, remove=True),
            {},
        ),
        (
            UpgradeScenario("Error: Service error response")
            .set_extension(ext_type=EXTENSION_TYPE_CM, ext_vers="0.5.0")
            .set_response_on_patch(
                ext_type=EXTENSION_TYPE_CM, code=HTTP_STATUS_SERVICE_ERROR, body={"error": "server error"}
            ),
            {EXTENSION_TYPE_CM: {}},
        ),
        # ========== Combined validation scenarios ==========
        (
            UpgradeScenario("Combined: Min version takes precedence over preview train")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.0.0", ext_train="preview")
            .set_user_kwargs(ops_version="1.2.36")
            .expecting_validation_error(r"min compatible upgrade version.*1\.1\.59"),
            {},
        ),
        (
            UpgradeScenario("Combined: Preview train validation after min version passes")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.1.59", ext_train="preview")  # Meets min version
            .set_user_kwargs(ops_version="1.2.36")
            .expecting_validation_error(r"Upgrades to or from non-stable release trains are not supported"),
            {},
        ),
        (
            UpgradeScenario("Combined: All validations bypassed with force")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.0.0", ext_train="preview")
            .set_user_kwargs(ops_version="1.2.36", ops_train="stable", force=True),
            {EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version="1.2.36", train="stable")},
        ),
        # ========== User confirmation test ==========
        (
            UpgradeScenario("Confirm prompt: User confirmation required", confirm_yes=False).set_extension(
                ext_type=EXTENSION_TYPE_CM, ext_vers="0.5.0"
            ),
            {EXTENSION_TYPE_CM: build_extension_props(EXTENSION_TYPE_CM, version=BUILT_IN_VALUE)},
        ),
        # ========== Platform to CertManager Migration (>= MIN_INSTANCE_VERSION_FOR_CM_MIGRATE) ==========
        (
            UpgradeScenario("Migration: Platform exists, IoT Ops >= MIN_INSTANCE_VERSION_FOR_CM_MIGRATE")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE),
            {
                EXTENSION_TYPE_CM: build_extension_props(EXTENSION_TYPE_CM, version=BUILT_IN_VALUE),
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS, version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE
                ),
            },
        ),
        (
            UpgradeScenario("Migration: Platform already deleted, create CertManager")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE),
            {
                EXTENSION_TYPE_CM: build_extension_props(EXTENSION_TYPE_CM, version=BUILT_IN_VALUE),
                EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version=BUILT_IN_VALUE),
            },
        ),
        (
            UpgradeScenario("No Migration: IoT Ops < MIN_INSTANCE_VERSION_FOR_CM_MIGRATE")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(ops_version="1.2.82"),
            {
                EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version="1.2.82"),
                # No platform delete, no certmanager create
            },
        ),
        (
            UpgradeScenario("No Migration: CertManager already exists")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, ext_vers="0.5.0")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE),
            {
                # Platform is deleted, CM is UPDATED (not created since it exists)
                EXTENSION_TYPE_CM: build_extension_props(EXTENSION_TYPE_CM, version=BUILT_IN_VALUE),
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS, version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE
                ),
            },
        ),
        (
            UpgradeScenario("No Migration: Platform exists, CM doesn't, IoT Ops < MIN_INSTANCE_VERSION_FOR_CM_MIGRATE")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(ops_version="1.2.82"),
            {
                # No platform delete or CM create since IoT Ops < MIN_INSTANCE_VERSION_FOR_CM_MIGRATE
                EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version="1.2.82"),
            },
        ),
        (
            UpgradeScenario("Migration: With other extension updates")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_extension(ext_type=EXTENSION_TYPE_SSC, ext_vers="0.3.0")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE),
            {
                # Platform is deleted, not in expected
                EXTENSION_TYPE_CM: build_extension_props(EXTENSION_TYPE_CM, version=BUILT_IN_VALUE),
                EXTENSION_TYPE_SSC: build_extension_props(EXTENSION_TYPE_SSC, version=BUILT_IN_VALUE),
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS, version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE
                ),
            },
        ),
        # ========== ADR Namespace ==========
        (
            UpgradeScenario("ADR Required: Migration to v2 without ADR namespace")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE)  # Triggers v2 migration
            .set_auxiliary_kwargs(remove_adr_for_test=True)
            .expecting_validation_error(r"The instance requires an ADR namespace for migration to v2"),
            {},
        ),
        (
            UpgradeScenario("ADR Provided: Migration to v2 with ADR namespace")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(
                ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE,
                ns_resource_id="PLACEHOLDER_ADR_NAMESPACE_ID",
            )
            .set_auxiliary_kwargs(remove_adr_for_test=True, expect_instance_update=True, default_registry_exists=False),
            {
                EXTENSION_TYPE_CM: build_extension_props(EXTENSION_TYPE_CM, version=BUILT_IN_VALUE),
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS, version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE
                ),
            },
        ),
        # ========== MQTT Broker Configuration Migration (>= MIN_INSTANCE_VERSION_FOR_CM_MIGRATE) ==========
        (
            UpgradeScenario("MQTT Migration: Basic migration with default token")
            .set_extension(
                ext_type=EXTENSION_TYPE_OPS,
                ext_vers="1.2.0",
                config_settings={
                    "connectors.values.mqttBroker.address": "mqtts://aio-broker.azure-iot-operations:18883",
                    "connectors.values.mqttBroker.serviceAccountTokenAudience": "aio-internal",
                },
            )
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE),
            {
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS,
                    version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE,
                    config={
                        "dataFlows.values.tinyKube.mqttBroker.hostName": "aio-broker.azure-iot-operations",
                        "dataFlows.values.tinyKube.mqttBroker.port": "18883",
                        "dataFlows.values.tinyKube.mqttBroker.authentication.serviceAccountTokenAudience": (
                            "aio-internal"
                        ),
                    },
                ),
            },
        ),
        (
            UpgradeScenario("MQTT Migration: Custom broker with IP address")
            .set_extension(
                ext_type=EXTENSION_TYPE_OPS,
                ext_vers="1.2.0",
                config_settings={
                    "connectors.values.mqttBroker.address": "mqtts://192.168.1.1:8883",
                    "connectors.values.mqttBroker.serviceAccountTokenAudience": "aio-internal",
                },
            )
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE),
            {
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS,
                    version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE,
                    config={
                        "dataFlows.values.tinyKube.mqttBroker.hostName": "192.168.1.1",
                        "dataFlows.values.tinyKube.mqttBroker.port": "8883",
                        "dataFlows.values.tinyKube.mqttBroker.authentication.serviceAccountTokenAudience": (
                            "aio-internal"
                        ),
                    },
                ),
            },
        ),
        (
            UpgradeScenario("MQTT No Migration: Version < MIN_INSTANCE_VERSION_FOR_CM_MIGRATE")
            .set_extension(
                ext_type=EXTENSION_TYPE_OPS,
                ext_vers="1.2.0",
                config_settings={
                    "connectors.values.mqttBroker.address": "mqtts://aio-broker.azure-iot-operations:18883",
                    "connectors.values.mqttBroker.serviceAccountTokenAudience": "aio-internal",
                },
            )
            .set_user_kwargs(ops_version="1.2.82"),
            {
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS,
                    version="1.2.82",
                ),
            },
        ),
        (
            UpgradeScenario("MQTT No Migration: Missing MQTT config")
            .set_extension(
                ext_type=EXTENSION_TYPE_OPS,
                ext_vers="1.2.0",
                config_settings={"some.other.setting": "value"},
            )
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE),
            {
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS,
                    version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE,
                ),
            },
        ),
        (
            UpgradeScenario("MQTT Migration: Without token audience")
            .set_extension(
                ext_type=EXTENSION_TYPE_OPS,
                ext_vers="1.2.0",
                config_settings={
                    "connectors.values.mqttBroker.address": "mqtts://broker-without-port",
                },
            )
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE),
            {
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS,
                    version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE,
                    config={
                        "dataFlows.values.tinyKube.mqttBroker.hostName": "broker-without-port",
                    },
                ),
            },
        ),
        (
            UpgradeScenario("MQTT Migration: Existing keys not overwritten")
            .set_extension(
                ext_type=EXTENSION_TYPE_OPS,
                ext_vers="1.2.0",
                config_settings={
                    "connectors.values.mqttBroker.address": "mqtts://aio-broker.azure-iot-operations:18883",
                    "connectors.values.mqttBroker.serviceAccountTokenAudience": "aio-internal",
                    "dataFlows.values.tinyKube.mqttBroker.hostName": "existing-broker",
                    "dataFlows.values.tinyKube.mqttBroker.port": "9999",
                },
            )
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE),
            {
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS,
                    version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE,
                    config={
                        "dataFlows.values.tinyKube.mqttBroker.authentication.serviceAccountTokenAudience": (
                            "aio-internal"
                        )
                    },
                ),
            },
        ),
        (
            UpgradeScenario("MQTT Migration: Invalid URL only migrates token")
            .set_extension(
                ext_type=EXTENSION_TYPE_OPS,
                ext_vers="1.2.0",
                config_settings={
                    "connectors.values.mqttBroker.address": "not-a-valid-url",
                    "connectors.values.mqttBroker.serviceAccountTokenAudience": "aio-internal",
                },
            )
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE),
            {
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS,
                    version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE,
                    config={
                        "dataFlows.values.tinyKube.mqttBroker.authentication.serviceAccountTokenAudience": (
                            "aio-internal"
                        )
                    },
                ),
            },
        ),
        (
            UpgradeScenario("MQTT Migration: With Platform migration")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(
                ext_type=EXTENSION_TYPE_OPS,
                ext_vers="1.2.0",
                config_settings={
                    "connectors.values.mqttBroker.address": "mqtts://aio-broker.azure-iot-operations:18883",
                    "connectors.values.mqttBroker.serviceAccountTokenAudience": "aio-internal",
                },
            )
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE),
            {
                EXTENSION_TYPE_CM: build_extension_props(EXTENSION_TYPE_CM, version=BUILT_IN_VALUE),
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS,
                    version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE,
                    config={
                        "dataFlows.values.tinyKube.mqttBroker.hostName": "aio-broker.azure-iot-operations",
                        "dataFlows.values.tinyKube.mqttBroker.port": "18883",
                        "dataFlows.values.tinyKube.mqttBroker.authentication.serviceAccountTokenAudience": (
                            "aio-internal"
                        ),
                    },
                ),
            },
        ),
        # ========== Registry Endpoint Creation (>= MIN_INSTANCE_VERSION_FOR_CM_MIGRATE) ==========
        (
            UpgradeScenario("Registry: Create default endpoint on v2 migration")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE)
            .set_auxiliary_kwargs(default_registry_exists=False),
            {
                EXTENSION_TYPE_CM: build_extension_props(EXTENSION_TYPE_CM, version=BUILT_IN_VALUE),
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS, version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE
                ),
            },
        ),
        (
            UpgradeScenario("Registry: Skip creation when default exists")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE)
            .set_auxiliary_kwargs(default_registry_exists=True),
            {
                EXTENSION_TYPE_CM: build_extension_props(EXTENSION_TYPE_CM, version=BUILT_IN_VALUE),
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS, version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE
                ),
            },
        ),
        (
            UpgradeScenario("Registry: No creation when version < MIN_INSTANCE_VERSION_FOR_CM_MIGRATE")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(ops_version="1.2.82")
            .set_auxiliary_kwargs(default_registry_exists=False),
            {
                EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version="1.2.82"),
            },
        ),
        (
            UpgradeScenario("Registry: Handle error gracefully when checking endpoints")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE)
            .set_auxiliary_kwargs(registry_list_error=True),
            {
                EXTENSION_TYPE_CM: build_extension_props(EXTENSION_TYPE_CM, version=BUILT_IN_VALUE),
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS, version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE
                ),
            },
        ),
    ],
)
def test_ops_upgrade(
    mocked_cmd: Mock,
    mocked_responses: responses,
    target_scenario: UpgradeScenario,
    expected_patched_ext_types: Dict[str, dict],
    no_progress: bool,
    mocked_logger: Mock,
    mocked_sleep: Mock,
    spy_upgrade_displays: Dict[str, Mock],
    mocked_confirm: Mock,
    mocked_upgrade_manager: Mock,
):
    from azext_edge.edge.commands_edge import upgrade_instance

    resource_group_name = generate_random_string()
    instance_name = generate_random_string()

    ns_resource_id = target_scenario.user_kwargs.get("ns_resource_id")
    if ns_resource_id and ns_resource_id == "PLACEHOLDER_ADR_NAMESPACE_ID":
        # TODO: Placeholder is temp due to DOE limitation (same rg constraint).
        ns_resource_id = (
            f"/subscriptions/sub1/resourceGroups/{resource_group_name}"
            f"/providers/Microsoft.DeviceRegistry/namespaces/adr1"
        )

    target_scenario.set_instance_mock(
        mocked_responses=mocked_responses, instance_name=instance_name, resource_group_name=resource_group_name
    )
    call_kwargs = {
        "cmd": mocked_cmd,
        "resource_group_name": resource_group_name,
        "instance_name": instance_name,
        "no_progress": no_progress,
        "force": target_scenario.user_kwargs.get("force"),
        "confirm_yes": target_scenario.confirm_yes,
        "adr_namespace_resource_id": ns_resource_id,
    }

    for key, value in target_scenario.user_kwargs.items():
        if key not in ["force", "ns_resource_id"]:  # Skip already handled keys
            call_kwargs[key] = value

    expect_exception = target_scenario.expect_exception
    exception_match = target_scenario.expect_exception_match

    if expect_exception:
        with pytest.raises(expect_exception, match=exception_match) as err:
            upgrade_instance(**call_kwargs)
        if isinstance(err.value, HttpResponseError):
            mocked_logger.error.assert_called_once_with(
                f"Correlation Id for failed update operation: {target_scenario.last_correlation_id}"
            )
        assert_displays(spy_upgrade_displays, no_progress, error_context=err)
        return

    upgrade_result = upgrade_instance(**call_kwargs)

    if not expected_patched_ext_types:
        assert_no_upgrades_performed(upgrade_result, mocked_logger)
        assert_displays(spy_upgrade_displays, no_progress, 1)
        return

    assert upgrade_result

    # Count expected operations
    delete_count = len(target_scenario.delete_record)
    create_count = len(target_scenario.create_record)
    # For updates, only count extensions that exist and are being updated (not created)
    update_count = len(
        [
            ext
            for ext in expected_patched_ext_types
            if ext not in target_scenario.delete_record and ext not in target_scenario.create_record
        ]
    )
    instance_count = int(target_scenario.expect_instance_update)
    registry_count = int(expects_registry_creation(target_scenario))

    expected_count = delete_count + create_count + update_count + instance_count + registry_count

    assert len(upgrade_result) == expected_count
    assert len(mocked_confirm.ask.mock_calls) == int(not target_scenario.confirm_yes)

    assert_operation_order(target_scenario, upgrade_result)
    assert_result(target_scenario, upgrade_result, expected_patched_ext_types)
    assert_displays(spy_upgrade_displays, no_progress, patched_ext_types=expected_patched_ext_types)


@pytest.mark.parametrize(
    "target_scenario",
    [
        UpgradeScenario("Retry test")
        .set_extension(ext_type=EXTENSION_TYPE_CM, ext_vers="0.5.0")
        .set_response_on_patch(
            ext_type=EXTENSION_TYPE_CM,
            code=HTTP_STATUS_SERVICE_UNAVAILABLE,
            body={"error": "temporary problems"},
        ),
        UpgradeScenario("Retry test from async header")
        .set_extension(ext_type=EXTENSION_TYPE_CM, ext_vers="0.5.0")
        .set_response_on_patch(
            ext_type=EXTENSION_TYPE_CM,
            code=HTTP_STATUS_ACCEPTED,
            headers={"Azure-AsyncOperation": "https://localhost/async-operation"},
        )
        .set_auxiliary_kwargs(
            async_endpoint="https://localhost/async-operation", async_code=503, async_method=responses.GET
        )
        .set_expected_exception(HttpResponseError),
    ],
)
def test_ops_upgrade_retry_assertion(
    mocked_cmd: Mock,
    mocked_responses: responses,
    target_scenario: UpgradeScenario,
    mocked_logger: Mock,
    mocked_sleep: Mock,
    spy_upgrade_displays: Dict[str, Mock],
):
    from azext_edge.edge.commands_edge import upgrade_instance

    resource_group_name = generate_random_string()
    instance_name = generate_random_string()

    target_scenario.set_instance_mock(
        mocked_responses=mocked_responses, instance_name=instance_name, resource_group_name=resource_group_name
    )

    call_kwargs = {
        "cmd": mocked_cmd,
        "resource_group_name": resource_group_name,
        "instance_name": instance_name,
        "no_progress": True,
        "confirm_yes": True,
    }

    patch_status_code = target_scenario.ext_type_response_map[EXTENSION_TYPE_CM][0]
    async_mock = None

    if patch_status_code == HTTP_STATUS_ACCEPTED:
        # For async operations, add the async endpoint mock
        async_mock = mocked_responses.add(
            method=target_scenario.aux_kwargs["async_method"],
            url=target_scenario.aux_kwargs["async_endpoint"],
            status=target_scenario.aux_kwargs["async_code"],
        )
        error_status_code = target_scenario.aux_kwargs["async_code"]
    else:
        error_status_code = patch_status_code

    with pytest.raises(target_scenario.expect_exception) as err:
        upgrade_instance(**call_kwargs)

    assert err.value.status_code == error_status_code

    # Verify retries based on scenario type
    if patch_status_code == HTTP_STATUS_SERVICE_UNAVAILABLE:
        # Direct patch failure - verify callback was called DEFAULT_RETRY_COUNT times
        assert (
            target_scenario.patch_call_count == DEFAULT_RETRY_COUNT
        ), f"Expected {DEFAULT_RETRY_COUNT} patch calls, got {target_scenario.patch_call_count}"
    elif patch_status_code == HTTP_STATUS_ACCEPTED and async_mock:
        # Async operation failure - verify async endpoint was retried
        assert_retry_count(async_mock)


def assert_result(
    target_scenario: UpgradeScenario, upgrade_result: List[dict], expected_types: Optional[Dict[str, dict]] = None
):
    if not upgrade_result:
        return

    result_by_type = {}
    deleted_types = set()
    created_types = set()
    instance_updates = []
    registry_endpoints = []

    for result in upgrade_result:
        props = result.get("properties", {})
        ext_type = props.get("extensionType")

        # Check if this is a registry endpoint
        if (
            result.get("name") == "default"
            and result.get("type") == "Microsoft.IoTOperations/instances/registryEndpoints"
        ):
            registry_endpoints.append(result)
            continue

        # Separate instance updates from extension operations
        if not ext_type:
            # Instance updates don't have extensionType but should have specific properties
            if "adrNamespaceRef" in props:
                instance_updates.append(result)
            continue

        # Process extension operations
        if props.get("provisioningState") == "Deleted":
            deleted_types.add(ext_type)
        else:
            result_by_type[ext_type] = result
            if ext_type in target_scenario.create_record:
                created_types.add(ext_type)

    # Validate instance updates
    if target_scenario.expect_instance_update:
        assert instance_updates, "Expected instance update but none found in results"
        assert len(instance_updates) == 1, f"Expected exactly 1 instance update, found {len(instance_updates)}"
    else:
        assert (
            not instance_updates
        ), f"Unexpected instance update(s) in results. Found {len(instance_updates)} instance update(s)"

    # Validate registry endpoint creation
    if expects_registry_creation(target_scenario):
        assert registry_endpoints, "Expected registry endpoint creation but none found in results"
        assert len(registry_endpoints) == 1, f"Expected exactly 1 registry endpoint, found {len(registry_endpoints)}"
        endpoint = registry_endpoints[0]
        assert endpoint["properties"]["host"] == expected_default_registry["properties"]["host"]
        assert endpoint["properties"]["authentication"] == expected_default_registry["properties"]["authentication"]
    else:
        assert not registry_endpoints, f"Unexpected registry endpoint(s) in results. Found {len(registry_endpoints)}"

    _assert_user_kwargs_applied(target_scenario.user_kwargs, result_by_type, deleted_types)

    # Validate expected types if provided
    if expected_types:
        _assert_expected_types(expected_types, result_by_type, deleted_types, created_types, target_scenario)


def _assert_user_kwargs_applied(user_kwargs: dict, result_by_type: dict, deleted_types: set):
    for alias in EXTENSION_ALIAS_TO_TYPE_MAP:
        ext_type = EXTENSION_ALIAS_TO_TYPE_MAP[alias]

        if ext_type in deleted_types or ext_type not in result_by_type:
            continue

        result = result_by_type[ext_type]
        props = result["properties"]

        # Check each type of override
        for suffix, prop_name in [
            ("config", "configurationSettings"),
            ("version", "version"),
            ("train", "releaseTrain"),
        ]:
            key = f"{alias}_{suffix}"
            if key in user_kwargs:
                value = user_kwargs[key]
                if suffix == "config":
                    value = parse_kvp_nargs(value)
                if value:
                    assert props.get(prop_name) == value, f"Expected {prop_name}={value} for {alias}"


def _assert_expected_types(
    expected_types: dict, result_by_type: dict, deleted_types: set, created_types: set, scenario
):
    expected = deepcopy(expected_types)
    results = deepcopy(result_by_type)

    for ext_type in expected:
        _replace_built_in_values(expected[ext_type], ext_type, scenario)

    assert deleted_types == set(scenario.delete_record.keys())
    assert created_types == set(scenario.create_record.keys())

    for ext_type in deleted_types:
        if ext_type in expected:
            del expected[ext_type]

    for ext_type in created_types:
        if ext_type in results and ext_type in expected:
            _validate_created_extension(results[ext_type], expected[ext_type])
            del results[ext_type]
            del expected[ext_type]

    assert results == expected


def _replace_built_in_values(expected_ext: dict, ext_type: str, scenario):
    props = expected_ext.get("properties", {})
    moniker = EXTENSION_TYPE_TO_MONIKER_MAP[ext_type]

    if props.get("version") == BUILT_IN_VALUE:
        props["version"] = scenario.init_version_map[moniker]["version"]

    if props.get("releaseTrain") == BUILT_IN_VALUE:
        default_train = "stable" if ext_type == EXTENSION_TYPE_OPS else scenario.init_version_map[moniker]["train"]
        props["releaseTrain"] = default_train


def _validate_created_extension(actual: dict, expected: dict):
    assert actual["properties"]["extensionType"] == expected["properties"]["extensionType"]
    assert actual["properties"]["version"] == expected["properties"]["version"]
    if "releaseTrain" in expected["properties"]:
        assert actual["properties"]["releaseTrain"] == expected["properties"]["releaseTrain"]


def assert_displays(
    spy_upgrade_displays: Dict[str, Mock],
    no_progress: bool,
    progress_count: Optional[int] = None,
    error_context: Optional[Exception] = None,
    patched_ext_types: Optional[Dict[str, dict]] = None,
):
    # Handle error scenarios
    if error_context:
        error_context = error_context.value
        if isinstance(error_context, ValidationError):
            validation_err_str = str(error_context)
            progress_count = 1
            if validation_err_str.startswith("Installed") and no_progress:
                # Error is raised in first get_patch(). Table render is skipped if no_progress.
                progress_count = 2

    if not progress_count:
        progress_count = 2

    if not no_progress and not error_context and patched_ext_types:
        table = spy_upgrade_displays["print"].mock_calls[1].args[1]
        assert table.title

        table_monikers = list(table.columns[0].cells)
        expected_update_monikers = {EXTENSION_TYPE_TO_MONIKER_MAP[ext_type] for ext_type in patched_ext_types.keys()}

        for moniker in expected_update_monikers:
            assert moniker in table_monikers, f"Expected {moniker} to be in table"

        table_has_delete = any("Remove" in str(cell) for col in table.columns for cell in col.cells)
        table_has_create = any("Not Installed" in str(cell) for col in table.columns for cell in col.cells)

        if not table_has_delete and not table_has_create:
            # Verify UPDATE-only scenarios maintain extension type order
            update_monikers_in_table = [m for m in table_monikers if m in expected_update_monikers]
            expected_order = sorted(
                update_monikers_in_table, key=lambda m: list(EXTENSION_TYPE_TO_MONIKER_MAP.values()).index(m)
            )
            assert (
                update_monikers_in_table == expected_order
            ), f"Extensions not in expected order. Got {update_monikers_in_table}, expected {expected_order}"

    # Verify progress bar initialization
    assert len(spy_upgrade_displays["progress.__init__"].mock_calls) == progress_count
    assert spy_upgrade_displays["progress.__init__"].mock_calls[0].kwargs == {
        "transient": True,
        "disable": no_progress,
    }
    if progress_count > 1:
        assert spy_upgrade_displays["progress.__init__"].mock_calls[1].kwargs == {
            "transient": False,
            "disable": no_progress,
        }


@pytest.mark.parametrize(
    "current,target,expected,sync_mode",
    [
        ({}, {}, {}, ConfigSyncModeType.FULL.value),
        ({}, {"a": "b"}, {"a": "b"}, ConfigSyncModeType.FULL.value),
        ({}, {"a": "b", "c": "d"}, {"a": "b", "c": "d"}, ConfigSyncModeType.FULL.value),
        ({"a": "b"}, {"a": "c"}, {"a": "c"}, ConfigSyncModeType.FULL.value),
        ({"a": "b"}, {}, {"a": None}, ConfigSyncModeType.FULL.value),
        ({"a": "b", "c": "d"}, {"c": "e"}, {"a": None, "c": "e"}, ConfigSyncModeType.FULL.value),
        ({"a": "b"}, {"c": "d"}, {}, ConfigSyncModeType.NONE.value),
        ({"a": "b"}, {"c": None, "d": "e"}, {}, ConfigSyncModeType.NONE.value),
        ({"a": "b"}, {"a": "c"}, {}, ConfigSyncModeType.ADD.value),
        ({"a": "b"}, {"a": "c", "d": "e"}, {"d": "e"}, ConfigSyncModeType.ADD.value),
        ({"a": "b"}, {"a": "c"}, {}, ConfigSyncModeType.ADD.value),
    ],
)
def test_calculate_config_delta(
    current: Dict[str, str], target: Dict[str, str], expected: Dict[str, str], sync_mode: str
):
    from azext_edge.edge.providers.orchestration.upgrade2 import calculate_config_delta

    result = calculate_config_delta(current=current, target=target, sync_mode=sync_mode)
    assert result == expected
