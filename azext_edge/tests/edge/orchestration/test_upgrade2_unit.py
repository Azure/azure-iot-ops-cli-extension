# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import re
from typing import Dict, List, Optional, Tuple, TypeVar
from unittest.mock import Mock, patch

import pytest
import requests
import responses
from azure.cli.core.azclierror import ValidationError
from azure.core.exceptions import HttpResponseError

from azext_edge.edge.providers.orchestration.common import (
    EXTENSION_ALIAS_TO_TYPE_MAP,
    EXTENSION_MONIKER_TO_ALIAS_MAP,
    EXTENSION_MONIKER_OPS,
    EXTENSION_TYPE_ACS,
    EXTENSION_TYPE_CM,
    EXTENSION_TYPE_OPS,
    EXTENSION_TYPE_PLATFORM,
    EXTENSION_TYPE_SSC,
    EXTENSION_TYPE_TO_MONIKER_MAP,
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
        self._build_defaults()

    def _build_defaults(self):
        for ext_type in EXTENSION_TYPE_TO_MONIKER_MAP:
            if ext_type in [EXTENSION_TYPE_ACS, EXTENSION_TYPE_PLATFORM]:
                continue
            vers = self.init_version_map[EXTENSION_TYPE_TO_MONIKER_MAP[ext_type]]["version"]
            train = self.init_version_map[EXTENSION_TYPE_TO_MONIKER_MAP[ext_type]]["train"]

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
                "name": EXTENSION_TYPE_TO_MONIKER_MAP[ext_type],
            }

    def set_cluster_connected_status(self: T, status: str) -> T:
        self.cluster_connected_status = status
        if status != ClusterConnectStatus.CONNECTED.value:
            self.expect_exception = ValidationError
        return self

    def set_user_kwargs(self: T, **kwargs) -> T:
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
        provisioning_state: Optional[str] = None,
        remove: bool = False,
    ) -> T:
        if remove:
            del self.extensions[ext_type]
            self.expect_exception = ValidationError
            return self
        if ext_vers:
            if ext_vers == BUILT_IN_VALUE:
                ext_vers = self.init_version_map[EXTENSION_TYPE_TO_MONIKER_MAP[ext_type]]["version"]
            self.extensions[ext_type]["properties"]["version"] = ext_vers
        if ext_train:
            self.extensions[ext_type]["properties"]["releaseTrain"] = ext_train
        if provisioning_state:
            self.extensions[ext_type]["properties"]["provisioningState"] = provisioning_state
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
        self.aux_kwargs = kwargs
        return self

    def set_instance_mock(self: T, mocked_responses: responses, instance_name: str, resource_group_name: str):
        mocked_responses.assert_all_requests_are_fired = False
        mock_instance_record = get_mock_instance_record(name=instance_name, resource_group_name=resource_group_name)
        mocked_responses.add(
            method=responses.GET,
            url=get_instance_endpoint(resource_group_name=resource_group_name, instance_name=instance_name),
            json=mock_instance_record,
            status=200,
            content_type="application/json",
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

    def patch_extension_response(self, request: requests.PreparedRequest) -> Optional[tuple]:
        ext_moniker = request.path_url.split("?")[0].split("/")[-1]
        assert_upgrade_headers(request.headers)
        self.last_correlation_id = request.headers.get("x-ms-correlation-request-id")
        for ext_type in EXTENSION_TYPE_TO_MONIKER_MAP:
            if EXTENSION_TYPE_TO_MONIKER_MAP[ext_type] == ext_moniker:
                status_code, response_body, headers = self.ext_type_response_map.get(ext_type) or (
                    HTTP_STATUS_OK,
                    json.loads(request.body),
                    {},
                )
                if response_body and "properties" in response_body:
                    response_body["properties"]["extensionType"] = ext_type
                self.patch_record[ext_type] = response_body
                response_headers = dict(STANDARD_HEADERS, **headers)
                return (status_code, response_headers, json.dumps(response_body))

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


def assert_no_upgrades_performed(upgrade_result, logger_mock):
    assert upgrade_result is None
    logger_mock.warning.assert_called_once_with(DEFAULT_LOG_WARNING_MESSAGE)


def assert_validation_error_raised(exc_info, expected_pattern: str):
    assert isinstance(exc_info.value, ValidationError)
    if expected_pattern:
        assert re.search(expected_pattern, str(exc_info.value))


def assert_retry_count(mock_response, expected_count: int = DEFAULT_RETRY_COUNT):
    assert len(mock_response.calls) == expected_count


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
            UpgradeScenario("Error: IoT Ops extension missing")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, remove=True),
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

    target_scenario.set_instance_mock(
        mocked_responses=mocked_responses, instance_name=instance_name, resource_group_name=resource_group_name
    )
    call_kwargs = {
        "cmd": mocked_cmd,
        "resource_group_name": resource_group_name,
        "instance_name": instance_name,
        "no_progress": no_progress,
        "confirm_yes": target_scenario.confirm_yes,
    }

    call_kwargs.update(target_scenario.user_kwargs)

    expect_exception = target_scenario.expect_exception
    exception_match = target_scenario.expect_exception_match

    if expect_exception:
        with pytest.raises(expect_exception, match=exception_match) as err:
            upgrade_instance(**call_kwargs)
        if isinstance(err.value, HttpResponseError):
            mocked_logger.error.assert_called_once_with(
                f"Correlation Id for failed upgrade operation: {target_scenario.last_correlation_id}"
            )
        assert_displays(spy_upgrade_displays, no_progress, error_context=err)
        return

    upgrade_result = upgrade_instance(**call_kwargs)

    if not expected_patched_ext_types:
        assert_no_upgrades_performed(upgrade_result, mocked_logger)
        assert_displays(spy_upgrade_displays, no_progress, 1)
        return

    assert upgrade_result
    assert len(upgrade_result) == len(expected_patched_ext_types)
    assert len(mocked_confirm.ask.mock_calls) == bool(not target_scenario.confirm_yes)

    assert_patch_order(upgrade_result, expected_patched_ext_types)
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
    if patch_status_code == HTTP_STATUS_ACCEPTED:
        # TODO Cheap pattern. Improve later.
        mocked_responses.add(
            method=target_scenario.aux_kwargs["async_method"],
            url=target_scenario.aux_kwargs["async_endpoint"],
            status=target_scenario.aux_kwargs["async_code"],
        )

    with pytest.raises(target_scenario.expect_exception) as err:
        upgrade_instance(**call_kwargs)

    mock_response = mocked_responses.registered()[-1]
    if patch_status_code == HTTP_STATUS_SERVICE_UNAVAILABLE:
        # Assert ext patch call retries
        error_status_code = patch_status_code
        assert mock_response.method == responses.PATCH
    if patch_status_code == HTTP_STATUS_ACCEPTED:
        # Assert async op fetch retries
        error_status_code = target_scenario.aux_kwargs["async_code"]
        assert mock_response.method == target_scenario.aux_kwargs["async_method"]

    assert err.value.status_code == error_status_code, f"Expected {error_status_code} but got {err.value.status_code}"
    assert_retry_count(mock_response)


def assert_result(
    target_scenario: UpgradeScenario, upgrade_result: List[dict], expected_types: Optional[Dict[str, dict]] = None
):
    user_kwargs = target_scenario.user_kwargs
    result_type_to_payload = {k["properties"]["extensionType"]: k for k in upgrade_result}
    for moniker in EXTENSION_MONIKER_TO_ALIAS_MAP:
        alias = EXTENSION_MONIKER_TO_ALIAS_MAP[moniker]
        ext_type = EXTENSION_ALIAS_TO_TYPE_MAP[alias]
        config = user_kwargs.get(f"{alias}_config")
        if config:
            parsed_config = parse_kvp_nargs(config)
            assert result_type_to_payload[ext_type]["properties"]["configurationSettings"] == parsed_config
        version = user_kwargs.get(f"{alias}_version")
        if version:
            assert result_type_to_payload[ext_type]["properties"]["version"] == version
        release_train = user_kwargs.get(f"{alias}_train")
        if release_train:
            assert result_type_to_payload[ext_type]["properties"]["releaseTrain"] == release_train

    if expected_types:
        for ext_type in expected_types:
            expected_version = expected_types[ext_type]["properties"].get("version")
            if expected_version == BUILT_IN_VALUE:
                expected_types[ext_type]["properties"]["version"] = target_scenario.init_version_map[
                    EXTENSION_TYPE_TO_MONIKER_MAP[ext_type]
                ]["version"]
            expected_train = expected_types[ext_type]["properties"].get("releaseTrain")
            if expected_train == BUILT_IN_VALUE:
                target_train = (
                    "stable"
                    if ext_type == EXTENSION_TYPE_OPS
                    else target_scenario.init_version_map[EXTENSION_TYPE_TO_MONIKER_MAP[ext_type]]["train"]
                )
                expected_types[ext_type]["properties"]["releaseTrain"] = target_train
        assert result_type_to_payload == expected_types
        assert len(upgrade_result) == len(expected_types)


def assert_patch_order(upgrade_result: List[dict], expected_types: Dict[str, dict]):
    result_type_to_payload = {k["properties"]["extensionType"]: k for k in upgrade_result}
    for ext_type in expected_types:
        assert ext_type in result_type_to_payload

    order_map = {}
    index = 0
    for key in EXTENSION_TYPE_TO_MONIKER_MAP:
        order_map[key] = index
        index = index + 1

    last_index = -1
    for patched_ext in upgrade_result:
        current_index = order_map[patched_ext["properties"]["extensionType"]]
        assert current_index > last_index
        last_index = current_index


def assert_displays(
    spy_upgrade_displays: Dict[str, Mock],
    no_progress: bool,
    progress_count: Optional[int] = None,
    error_context: Optional[Exception] = None,
    patched_ext_types: Optional[Dict[str, dict]] = None,
):
    # TODO: clean up function if spare cycles
    if error_context:
        error_context = error_context.value
        if isinstance(error_context, ValidationError):
            validation_err_str = str(error_context)
            progress_count = 1
            if validation_err_str.startswith("Installed") and no_progress:
                # Error is raised in first get_patch(). Table render is skipped if no_progress.
                progress_count += 1

    if not progress_count:
        progress_count = 2

    if all([not no_progress, not error_context, patched_ext_types]):
        table = spy_upgrade_displays["print"].mock_calls[1].args[1]
        assert table.title
        if patched_ext_types:
            table_monikers = list(table.columns[0].cells)
            # Ensures table column monikers exist and match the order of update
            patched_ext_types_keys = list(patched_ext_types.keys())
            for i in range(len(patched_ext_types_keys)):
                ext_type = patched_ext_types_keys[i]
                moniker = EXTENSION_TYPE_TO_MONIKER_MAP[ext_type]
                assert moniker == table_monikers[i]

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


def assert_upgrade_headers(headers: Dict[str, str]):
    assert headers.get("User-Agent").startswith("IotOperationsCliExtension/")
    assert headers.get("Accept") == "application/json"
    assert headers.get("Content-Type") == "application/json"
    assert headers.get("x-ms-correlation-request-id")
    assert headers.get("x-ms-client-request-id")
    assert headers.get("CommandName")


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
