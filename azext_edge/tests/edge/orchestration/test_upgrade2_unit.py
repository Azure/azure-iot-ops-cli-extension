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
import yaml
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
    MIN_INSTANCE_VERSION_FOR_OPCUA_CONNECTOR_TEMPLATE,
    OPCUA_CONNECTOR_ENDPOINT_TYPE,
    OPCUA_CONNECTOR_TEMPLATE_NAME_PREFIX,
    OPCUA_CONNECTOR_VERSION,
    PROVISIONING_STATE_FAILED,
    PROVISIONING_STATE_SUCCESS,
    ClusterConnectStatus,
    ConfigSyncModeType,
)
from azext_edge.edge.providers.orchestration.resources.instances import (
    SECRET_SYNC_RESOURCE_TYPE,
    SPC_RESOURCE_TYPE,
)
from azext_edge.edge.providers.orchestration.targets import InitTargets
from azext_edge.edge.providers.orchestration.template import TEMPLATE_BLUEPRINT_INSTANCE
from azext_edge.edge.util import parse_kvp_nargs
from azext_edge.edge.util.machinery import scoped_semver_import

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
from .resources.connector.akri.test_connector_templates_unit import (
    get_connector_template_endpoint,
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

DEFAULT_SPC_NAME = "spc-ops-abc123"
OPC_UA_SPC_NAME = "opc-ua-connector"

expected_default_registry = {
    "name": "default",
    "type": "Microsoft.IoTOperations/instances/registryEndpoints",
    "properties": {
        "host": "mcr.microsoft.com",
        "authentication": {"method": "Anonymous", "anonymousSettings": {}},
        "provisioningState": "Succeeded",
    },
}

expected_default_opcua_template = {
    "name": "azureiotoperationsconnectorforopcua-abcd",
    "type": "Microsoft.IoTOperations/instances/akriConnectorTemplates",
    "properties": {
        "connectorMetadataRef": (
            f"mcr.microsoft.com/azureiotoperations/aio-connectors/opcua-metadata:{OPCUA_CONNECTOR_VERSION}"
        ),
        "runtimeConfiguration": {
            "runtimeConfigurationType": "ManagedConfiguration",
            "managedConfigurationSettings": {
                "managedConfigurationType": "ImageConfiguration",
                "imageConfigurationSettings": {
                    "imageName": "azureiotoperations/aio-connectors/supervisor",
                    "tagDigestSettings": {"tagDigestType": "Tag", "tag": OPCUA_CONNECTOR_VERSION},
                },
            },
        },
        "deviceInboundEndpointTypes": [{"endpointType": OPCUA_CONNECTOR_ENDPOINT_TYPE}],
        "provisioningState": "Succeeded",
    },
}

# Fine in testing context.
semver = scoped_semver_import()
# The CLI's pinned iotOperations target; a default upgrade (no --ops-version) resolves this.
PINNED_IOTOPS_VERSION = TEMPLATE_BLUEPRINT_INSTANCE.content["variables"]["VERSIONS"]["iotOperations"]


def build_spc_resource_id(resource_group_name: str, spc_name: str) -> str:
    """Build a properly formatted SPC resource ID."""
    return (
        f"/subscriptions/sub1/resourceGroups/{resource_group_name}/providers/"
        f"Microsoft.SecretSyncController/azureKeyVaultSecretProviderClasses/{spc_name}"
    )


def build_secretsync_resource_id(resource_group_name: str, secretsync_name: str) -> str:
    """Build a properly formatted SecretSync resource ID."""
    return (
        f"/subscriptions/sub1/resourceGroups/{resource_group_name}/providers/"
        f"Microsoft.SecretSyncController/secretSyncs/{secretsync_name}"
    )


def expects_registry_creation(target_scenario: "UpgradeScenario") -> bool:
    return (
        hasattr(target_scenario, "aux_kwargs")
        and target_scenario.aux_kwargs.get("default_registry_exists") is False
        and semver.parse(target_scenario.user_kwargs.get("ops_version", ""))
        >= semver.parse(MIN_INSTANCE_VERSION_FOR_CM_MIGRATE)
    )


def expects_connector_template_creation(target_scenario: "UpgradeScenario") -> bool:
    if not hasattr(target_scenario, "aux_kwargs"):
        return False
    aux = target_scenario.aux_kwargs
    # A list error is swallowed, so no creation is attempted.
    if aux.get("connector_template_list_error"):
        return False
    # Satisfied only if a prefix-named template exists and is not in a terminal failed state; a
    # failed template is repaired, and an OPC UA template under a non-adopt name is not counted.
    exists = aux.get("opcua_connector_template_exists", True)
    name = aux.get("opcua_connector_template_name", expected_default_opcua_template["name"])
    state = aux.get("opcua_connector_template_provisioning_state", PROVISIONING_STATE_SUCCESS)
    satisfied = (
        exists
        and name.lower().startswith(OPCUA_CONNECTOR_TEMPLATE_NAME_PREFIX)
        and state.lower() != PROVISIONING_STATE_FAILED.lower()
    )
    if satisfied:
        return False
    # A default upgrade (no --ops-version) resolves the pinned manifest as the target.
    target_version = target_scenario.user_kwargs.get("ops_version") or PINNED_IOTOPS_VERSION
    return semver.parse(target_version) >= semver.parse(MIN_INSTANCE_VERSION_FOR_OPCUA_CONNECTOR_TEMPLATE)


def expects_secretsync_migration(target_scenario: "UpgradeScenario") -> bool:
    return (
        hasattr(target_scenario, "aux_kwargs")
        and target_scenario.aux_kwargs.get("secretsync_migration_needed") is True
        and semver.parse(target_scenario.user_kwargs.get("ops_version", ""))
        >= semver.parse(MIN_INSTANCE_VERSION_FOR_CM_MIGRATE)
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
        self.expect_instance_update = False
        self.remove_adr_for_test = False
        self.secretsync_migration_needed = False
        self.secretsync_resources = {}
        self.aux_kwargs = {}

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
        self.user_kwargs.update(kwargs)
        return self

    def set_expected_exception(self: T, exc: Exception, match: Optional[str] = None) -> T:
        self.expect_exception = exc
        self.expect_exception_match = match
        return self

    def set_extension(
        self: T,
        ext_type: str,
        ext_vers: Optional[str] = BUILT_IN_VALUE,
        ext_train: Optional[str] = BUILT_IN_VALUE,
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

        ext_moniker = EXTENSION_TYPE_TO_MONIKER_MAP[ext_type]

        # Resolve BUILT_IN_VALUE to actual defaults from init_version_map
        actual_vers = None
        if ext_vers == BUILT_IN_VALUE:
            actual_vers = self.init_version_map.get(ext_moniker, {}).get("version", "1.0.0")
        elif ext_vers:
            actual_vers = ext_vers

        actual_train = None
        if ext_train == BUILT_IN_VALUE:
            actual_train = self.init_version_map.get(ext_moniker, {}).get("train", "stable")
            # Override train to "stable" for IoT Operations extension to avoid
            # triggering preview train validation during tests (matches _build_defaults behavior)
            if ext_type == EXTENSION_TYPE_OPS and actual_train.lower() != "stable":
                actual_train = "stable"
        elif ext_train:
            actual_train = ext_train

        # Create extension if it doesn't exist
        if ext_type not in self.extensions:
            self.extensions[ext_type] = {
                "properties": {
                    "extensionType": ext_type,
                    "version": actual_vers,
                    "releaseTrain": actual_train,
                    "configurationSettings": config_settings or {},
                    "provisioningState": provisioning_state or PROVISIONING_STATE_SUCCESS,
                },
                "name": ext_moniker,
            }
        else:
            # Update existing extension
            self.extensions[ext_type]["properties"]["version"] = actual_vers
            self.extensions[ext_type]["properties"]["releaseTrain"] = actual_train
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
        self.aux_kwargs = kwargs

        # Set instance attributes for commonly used flags
        if "remove_adr_for_test" in kwargs:
            self.remove_adr_for_test = kwargs["remove_adr_for_test"]
        if "expect_instance_update" in kwargs:
            self.expect_instance_update = kwargs["expect_instance_update"]
        if "secretsync_migration_needed" in kwargs:
            self.secretsync_migration_needed = kwargs["secretsync_migration_needed"]

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

        # Add existing SPC reference if specified in aux_kwargs
        if self.aux_kwargs.get("has_existing_spc_ref"):
            mock_instance_record["properties"]["defaultSecretProviderClassRef"] = {
                "resourceId": build_spc_resource_id(resource_group_name, DEFAULT_SPC_NAME)
            }

        mocked_responses.add(
            method=responses.GET,
            url=get_instance_endpoint(resource_group_name=resource_group_name, instance_name=instance_name),
            json=mock_instance_record,
            status=200,
            content_type="application/json",
        )

        # Track if instance update was called
        self.instance_update_called = False

        # Add instance update mock if expected
        if self.expect_instance_update:

            def instance_update_callback(request):
                self.instance_update_called = True
                body = json.loads(request.body)

                # Build a minimal but complete response that the upgrade code will recognize
                response_data = {
                    "id": mock_instance_record["id"],
                    "name": instance_name,
                    "type": "Microsoft.IoTOperations/instances",
                    "location": mock_instance_record.get("location", "eastus"),
                    "properties": {},
                }

                # Apply the updates from the request body
                if "properties" in body:
                    # Track what was updated
                    if "defaultSecretProviderClassRef" in body["properties"]:
                        self.spc_ref_updated = True

                    # Only include the fields that were updated
                    if "adrNamespaceRef" in body["properties"]:
                        response_data["properties"]["adrNamespaceRef"] = body["properties"]["adrNamespaceRef"]

                    if "defaultSecretProviderClassRef" in body["properties"]:
                        response_data["properties"]["defaultSecretProviderClassRef"] = body["properties"][
                            "defaultSecretProviderClassRef"
                        ]

                response_body = json.dumps(response_data)
                return (200, STANDARD_HEADERS, response_body)

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

        self.instance_record = mock_instance_record

        # Always setup registry endpoint mocks when IoT Ops extension exists
        # The upgrade code checks registry endpoints when target version >= migration version
        if EXTENSION_TYPE_OPS in self.extensions:
            self._setup_registry_endpoint_mocks(mocked_responses, instance_name, resource_group_name)
            self._setup_connector_template_mocks(mocked_responses, instance_name, resource_group_name)

        self._setup_secretsync_mocks(mocked_responses, resource_group_name)

        return self

    def _setup_secretsync_mocks(self, mocked_responses: responses, resource_group_name: str):
        """Set up SecretSync resource graph mock and migration API mocks if needed."""
        self.mock_calls_tracker = {"resource_graph": [], "patch_spc": [], "patch_secretsync": [], "delete_spc": []}

        if self.secretsync_migration_needed:
            # Set up resources with both opc-ua-connector and default SPCs
            # Using realistic YAML format with proper indentation
            self.secretsync_resources = {
                SPC_RESOURCE_TYPE: [
                    {
                        "id": build_spc_resource_id(resource_group_name, OPC_UA_SPC_NAME),
                        "name": OPC_UA_SPC_NAME,
                        "type": SPC_RESOURCE_TYPE,
                        "properties": {
                            "objects": (
                                "array:\n"
                                "  - |\n"
                                "    objectName: cert-der\n"
                                "    objectType: secret\n"
                                "    objectEncoding: hex\n"
                            )
                        },
                    },
                    {
                        "id": build_spc_resource_id(resource_group_name, DEFAULT_SPC_NAME),
                        "name": DEFAULT_SPC_NAME,
                        "type": SPC_RESOURCE_TYPE,
                        "properties": {
                            "objects": (
                                "array:\n"
                                "  - |\n"
                                "    objectName: cert2-der\n"
                                "    objectType: secret\n"
                                "    objectEncoding: hex\n"
                                "  - |\n"
                                "    objectName: cert-san-app-der\n"
                                "    objectType: secret\n"
                                "    objectEncoding: hex\n"
                            )
                        },
                    },
                ],
                SECRET_SYNC_RESOURCE_TYPE: [
                    {
                        "id": build_secretsync_resource_id(resource_group_name, "secretsync1"),
                        "name": "secretsync1",
                        "type": SECRET_SYNC_RESOURCE_TYPE,
                        "properties": {"secretProviderClassName": OPC_UA_SPC_NAME},
                    },
                    {
                        "id": build_secretsync_resource_id(resource_group_name, "secretsync2"),
                        "name": "secretsync2",
                        "type": SECRET_SYNC_RESOURCE_TYPE,
                        "properties": {"secretProviderClassName": OPC_UA_SPC_NAME},
                    },
                ],
            }
        elif self.aux_kwargs.get("has_default_spc_only"):
            # Only default SPC exists (no migration needed)
            self.secretsync_resources = {
                SPC_RESOURCE_TYPE: [
                    {
                        "id": build_spc_resource_id(resource_group_name, DEFAULT_SPC_NAME),
                        "name": DEFAULT_SPC_NAME,
                        "type": SPC_RESOURCE_TYPE,
                        "properties": {"objects": "array: []"},  # Empty array
                    },
                ],
                SECRET_SYNC_RESOURCE_TYPE: [],
            }
        else:
            self.secretsync_resources = {}

        def handle_resource_graph_query(request: requests.PreparedRequest):
            from .resources.conftest import get_request_kpis

            request_kpis = get_request_kpis(request)
            if request_kpis.body_str:
                request_payload = json.loads(request_kpis.body_str)
                query = request_payload.get("query", "")

                if "microsoft.secretsynccontroller" in query.lower():
                    self.mock_calls_tracker["resource_graph"].append(
                        {"query": query, "resources_returned": len(self.secretsync_resources)}
                    )

                    response_data = {"data": []}
                    if self.secretsync_resources:
                        for resource_type, resources in self.secretsync_resources.items():
                            for resource in resources:
                                response_data["data"].append(
                                    {
                                        "id": resource["id"],
                                        "type": resource_type,
                                        "name": resource["name"],
                                        "properties": resource["properties"],
                                    }
                                )

                    return request_kpis.respond_with(200, response_body=response_data)
            return None

        mocked_responses.add_callback(
            method="POST",
            url=re.compile(
                r"https://management\.azure\.com/providers/Microsoft\.ResourceGraph/resources\?api-version=.*"
            ),
            callback=handle_resource_graph_query,
        )

        if self.secretsync_migration_needed:

            def create_patch_callback(operation_name: str, response_factory):
                """Factory to create PATCH callbacks with common logic."""

                def callback(request):
                    assert_upgrade_headers(request.headers)
                    body = json.loads(request.body)

                    # Common validations for PATCH
                    assert "properties" in body, f"PATCH {operation_name} request should have properties"

                    # Track the call
                    self.mock_calls_tracker[f"patch_{operation_name}"].append(
                        {
                            "url": request.path_url,
                            "body": body,
                            "name": request.path_url.split("/")[-1].split("?")[0],  # Extract resource name
                        }
                    )

                    return (200, STANDARD_HEADERS, json.dumps(response_factory(request, body)))

                return callback

            # SPC PATCH mock
            def spc_response_factory(_, body):
                assert "objects" in body["properties"], "PATCH SPC should update objects"
                # Return merged objects in the same YAML format, including the "id" field
                return {
                    "id": build_spc_resource_id(resource_group_name, DEFAULT_SPC_NAME),
                    "name": DEFAULT_SPC_NAME,
                    "type": SPC_RESOURCE_TYPE,
                    "properties": {
                        "objects": (
                            "array:\n"
                            "  - |\n"
                            "    objectName: cert2-der\n"
                            "    objectType: secret\n"
                            "    objectEncoding: hex\n"
                            "  - |\n"
                            "    objectName: cert-san-app-der\n"
                            "    objectType: secret\n"
                            "    objectEncoding: hex\n"
                            "  - |\n"
                            "    objectName: cert-der\n"
                            "    objectType: secret\n"
                            "    objectEncoding: hex\n"
                        )
                    },
                }

            mocked_responses.add_callback(
                method=responses.PATCH,
                url=re.compile(rf".*azureKeyVaultSecretProviderClasses/{DEFAULT_SPC_NAME}.*"),
                callback=create_patch_callback("spc", spc_response_factory),
            )

            # SecretSync PATCH
            def secretsync_response_factory(request, body):
                name = request.path_url.split("/")[-1].split("?")[0]
                assert "secretProviderClassName" in body["properties"], "PATCH SecretSync should update SPC reference"
                assert body["properties"]["secretProviderClassName"] == DEFAULT_SPC_NAME, (
                    f"SecretSync should reference {DEFAULT_SPC_NAME}, "
                    f"got {body['properties']['secretProviderClassName']}"
                )
                return {"name": name, "properties": {"secretProviderClassName": DEFAULT_SPC_NAME}}

            mocked_responses.add_callback(
                method=responses.PATCH,
                url=re.compile(r".*/secretSyncs/secretsync.*"),
                callback=create_patch_callback("secretsync", secretsync_response_factory),
            )

            # DELETE callback
            def delete_spc_callback(request):
                assert_upgrade_headers(request.headers)
                assert (
                    OPC_UA_SPC_NAME in request.path_url
                ), f"Should delete {OPC_UA_SPC_NAME}, but URL is {request.path_url}"
                self.mock_calls_tracker["delete_spc"].append({"url": request.path_url})
                return (204, {}, "")

            mocked_responses.add_callback(
                method=responses.DELETE,
                url=re.compile(rf".*azureKeyVaultSecretProviderClasses/{OPC_UA_SPC_NAME}.*"),
                callback=delete_spc_callback,
            )

    def _setup_registry_endpoint_mocks(self, mocked_responses: responses, instance_name: str, resource_group_name: str):
        """Set up registry endpoint mocks for tests."""
        list_endpoint = get_registry_endpoint_endpoint(
            instance_name=instance_name, resource_group_name=resource_group_name
        )

        # Determine test configuration
        registry_list_error = self.aux_kwargs.get("registry_list_error", False)
        default_exists = self.aux_kwargs.get("default_registry_exists", True)

        if registry_list_error:
            mocked_responses.add(
                method=responses.GET,
                url=list_endpoint,
                status=500,
                json={"error": {"message": "Failed to list registry endpoints", "code": "InternalServerError"}},
                content_type="application/json",
            )
        else:
            existing_endpoints = []
            if default_exists:
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

        # Always add PUT mock for creation attempts
        create_endpoint = get_registry_endpoint_endpoint(
            instance_name=instance_name, resource_group_name=resource_group_name, registry_endpoint_name="default"
        )

        def registry_create_callback(request):
            assert_upgrade_headers(request.headers)
            self.last_correlation_id = request.headers.get("x-ms-correlation-request-id")

            body = json.loads(request.body)
            assert "properties" in body
            assert body["properties"]["host"] == expected_default_registry["properties"]["host"]
            assert body["properties"]["authentication"] == expected_default_registry["properties"]["authentication"]

            response_body = deepcopy(expected_default_registry)
            response_body["id"] = create_endpoint
            return (200, STANDARD_HEADERS, json.dumps(response_body))

        mocked_responses.add_callback(
            method=responses.PUT,
            url=create_endpoint,
            callback=registry_create_callback,
        )

    def _setup_connector_template_mocks(
        self, mocked_responses: responses, instance_name: str, resource_group_name: str
    ):
        """Set up default OPC UA connector template mocks for tests."""
        list_endpoint = get_connector_template_endpoint(
            instance_name=instance_name, resource_group_name=resource_group_name
        )
        base_list_url = list_endpoint.split("?")[0]

        template_list_error = self.aux_kwargs.get("connector_template_list_error", False)
        opcua_exists = self.aux_kwargs.get("opcua_connector_template_exists", True)
        opcua_name = self.aux_kwargs.get("opcua_connector_template_name", expected_default_opcua_template["name"])
        opcua_state = self.aux_kwargs.get("opcua_connector_template_provisioning_state", PROVISIONING_STATE_SUCCESS)

        if template_list_error:
            mocked_responses.add(
                method=responses.GET,
                url=list_endpoint,
                status=500,
                json={"error": {"message": "Failed to list connector templates", "code": "InternalServerError"}},
                content_type="application/json",
            )
        else:
            existing_templates = []
            if opcua_exists:
                template = deepcopy(expected_default_opcua_template)
                template["name"] = opcua_name
                template["id"] = f"{base_list_url}/{opcua_name}"
                template["properties"]["provisioningState"] = opcua_state
                existing_templates.append(template)

            mocked_responses.add(
                method=responses.GET,
                url=list_endpoint,
                json={"value": existing_templates},
                status=200,
                content_type="application/json",
            )

        # Always add PUT mock for creation attempts (name is instance-derived).
        create_endpoint = re.compile(re.escape(base_list_url) + r"/azureiotoperationsconnectorforopcua-[a-z0-9]+")

        def connector_template_create_callback(request):
            assert_upgrade_headers(request.headers)
            self.last_correlation_id = request.headers.get("x-ms-correlation-request-id")

            body = json.loads(request.body)
            assert "properties" in body
            props = body["properties"]
            assert props["deviceInboundEndpointTypes"][0]["endpointType"] == OPCUA_CONNECTOR_ENDPOINT_TYPE
            image_settings = props["runtimeConfiguration"]["managedConfigurationSettings"][
                "imageConfigurationSettings"
            ]
            assert image_settings["imageName"] == "azureiotoperations/aio-connectors/supervisor"
            assert image_settings["tagDigestSettings"]["tag"] == OPCUA_CONNECTOR_VERSION

            template_name = request.path_url.split("?")[0].split("/")[-1]
            response_body = deepcopy(body)
            response_body["type"] = "Microsoft.IoTOperations/instances/akriConnectorTemplates"
            response_body["name"] = template_name
            response_body["id"] = f"{base_list_url}/{template_name}"
            response_body["properties"]["provisioningState"] = "Succeeded"
            return (200, STANDARD_HEADERS, json.dumps(response_body))

        mocked_responses.add_callback(
            method=responses.PUT,
            url=create_endpoint,
            callback=connector_template_create_callback,
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
    logger_mock.warning.assert_called_with(DEFAULT_LOG_WARNING_MESSAGE)


def assert_retry_count(mock_response, expected_count: int = DEFAULT_RETRY_COUNT):
    assert len(mock_response.calls) == expected_count


def assert_operation_order(target_scenario: UpgradeScenario, upgrade_result: List[dict]):  # noqa: C901
    """Assert operations happen in correct order:
    DELETE -> CREATE -> UPDATE -> INSTANCE_UPDATE -> REGISTRY_CREATE -> SECRETSYNC_MIGRATION.
    Also validates extension type order within each operation group."""

    # Group results by operation type
    deletes = []
    creates = []
    updates = []
    instance_updates = []
    registry_creates = []
    connector_template_creates = []
    secretsync_migrations = []

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

        # Check if this is an OPC UA connector template creation
        if result.get("type") == "Microsoft.IoTOperations/instances/akriConnectorTemplates":
            connector_template_creates.append(result)
            continue

        # Check if this is a secretsync migration result (patched default SPC)
        if not ext_type and result.get("name", "").startswith("spc-ops-") and "objects" in props:
            secretsync_migrations.append(result)
            continue

        # Check if this is an instance update (has adrNamespaceRef but no extensionType)
        if not ext_type and "adrNamespaceRef" in props:
            instance_updates.append(result)
            continue

        # Skip if no extension type and not a special operation
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

    # Verify registry and secretsync ordering at the end of operations
    expects_registry = expects_registry_creation(target_scenario)
    expects_secretsync = expects_secretsync_migration(target_scenario)
    expects_connector_template = expects_connector_template_creation(target_scenario)

    if expects_registry:
        assert len(registry_creates) == 1, "Expected exactly one registry endpoint creation"

    if expects_connector_template:
        assert len(connector_template_creates) == 1, "Expected exactly one connector template creation"

    if expects_secretsync:
        assert len(secretsync_migrations) == 1, "Expected exactly one secretsync migration"

    # Aux operations run in a fixed tail order: registry -> connector template -> secretsync.
    # Assert relative ordering of whichever are present, and that the last present one is last overall.
    aux_pipeline = []
    if expects_registry:
        aux_pipeline.append(("registry endpoint", registry_creates[0]))
    if expects_connector_template:
        aux_pipeline.append(("connector template", connector_template_creates[0]))
    if expects_secretsync:
        aux_pipeline.append(("secretsync migration", secretsync_migrations[0]))

    if aux_pipeline:
        positions = [upgrade_result.index(item) for _, item in aux_pipeline]
        assert positions == sorted(positions), (
            "Aux operations out of order; expected registry -> connector template -> secretsync, got "
            f"{[name for name, _ in aux_pipeline]} at positions {positions}"
        )
        assert (
            upgrade_result[-1] == aux_pipeline[-1][1]
        ), f"Expected '{aux_pipeline[-1][0]}' to be the last operation"

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
            UpgradeScenario("Failed state: Re-apply current version with a stale CLI").set_extension(
                ext_type=EXTENSION_TYPE_OPS, ext_vers="9.9.9", provisioning_state=PROVISIONING_STATE_FAILED
            ),
            {EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version="9.9.9")},
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
        # ========== no_cm_install flag tests ==========
        (
            UpgradeScenario("No CM Install: Skip cert-manager creation during v2 migration")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE, no_cm_install=True),
            {
                # Platform is deleted, but CM is NOT created due to no_cm_install
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS, version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE
                ),
            },
        ),
        (
            UpgradeScenario("No CM Install: Skip cert-manager when platform already deleted")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE, no_cm_install=True),
            {
                # No CM creation due to no_cm_install
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS, version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE
                ),
            },
        ),
        (
            UpgradeScenario("No CM Install: No effect when cert-manager already exists")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, ext_vers="0.5.0")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE, no_cm_install=True),
            {
                # Platform deleted, CM updated normally (no_cm_install only affects creation)
                EXTENSION_TYPE_CM: build_extension_props(EXTENSION_TYPE_CM, version=BUILT_IN_VALUE),
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS, version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE
                ),
            },
        ),
        (
            UpgradeScenario("No CM Install: Works with other migrations (registry, secretsync)")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE, no_cm_install=True)
            .set_auxiliary_kwargs(default_registry_exists=False, secretsync_migration_needed=True),
            {
                # No CM creation, but other migrations still happen
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
        # ========== OPC UA Connector Template Backfill (>= MIN_INSTANCE_VERSION_FOR_OPCUA_CONNECTOR_TEMPLATE) ====
        (
            UpgradeScenario("OPC UA Template: Create default when missing on 2608+ upgrade")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.4.0")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_OPCUA_CONNECTOR_TEMPLATE)
            .set_auxiliary_kwargs(opcua_connector_template_exists=False),
            {
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS, version=MIN_INSTANCE_VERSION_FOR_OPCUA_CONNECTOR_TEMPLATE
                ),
            },
        ),
        (
            UpgradeScenario("OPC UA Template: Create on default upgrade (no --ops-version)")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.4.0")
            .set_auxiliary_kwargs(opcua_connector_template_exists=False),
            {
                EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version=BUILT_IN_VALUE),
            },
        ),
        (
            UpgradeScenario("OPC UA Template: Repair when existing template failed to provision")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.4.0")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_OPCUA_CONNECTOR_TEMPLATE)
            .set_auxiliary_kwargs(
                opcua_connector_template_exists=True,
                # A prefix-matching name the CLI's sha256 4-hex suffix could never derive, so the
                # assertion below only passes if the repair reuses this discovered ARM name.
                opcua_connector_template_name="azureiotoperationsconnectorforopcua-repairtarget",
                opcua_connector_template_provisioning_state=PROVISIONING_STATE_FAILED,
            ),
            {
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS, version=MIN_INSTANCE_VERSION_FOR_OPCUA_CONNECTOR_TEMPLATE
                ),
            },
        ),
        (
            UpgradeScenario("OPC UA Template: Create when existing template lacks adopt prefix")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.4.0")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_OPCUA_CONNECTOR_TEMPLATE)
            .set_auxiliary_kwargs(
                opcua_connector_template_exists=True,
                opcua_connector_template_name="my-custom-opcua-template",
            ),
            {
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS, version=MIN_INSTANCE_VERSION_FOR_OPCUA_CONNECTOR_TEMPLATE
                ),
            },
        ),
        (
            UpgradeScenario("OPC UA Template: Skip when existing template is provisioning (transient)")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.4.0")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_OPCUA_CONNECTOR_TEMPLATE)
            .set_auxiliary_kwargs(
                opcua_connector_template_exists=True,
                opcua_connector_template_provisioning_state="Accepted",
            ),
            {
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS, version=MIN_INSTANCE_VERSION_FOR_OPCUA_CONNECTOR_TEMPLATE
                ),
            },
        ),
        (
            UpgradeScenario("OPC UA Template: Skip creation when template already exists")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.4.0")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_OPCUA_CONNECTOR_TEMPLATE)
            .set_auxiliary_kwargs(opcua_connector_template_exists=True),
            {
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS, version=MIN_INSTANCE_VERSION_FOR_OPCUA_CONNECTOR_TEMPLATE
                ),
            },
        ),
        (
            UpgradeScenario("OPC UA Template: No creation when version < threshold")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(ops_version="1.4.0")
            .set_auxiliary_kwargs(opcua_connector_template_exists=False),
            {
                EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version="1.4.0"),
            },
        ),
        (
            UpgradeScenario("OPC UA Template: Handle error gracefully when checking template")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.4.0")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_OPCUA_CONNECTOR_TEMPLATE)
            .set_auxiliary_kwargs(connector_template_list_error=True),
            {
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS, version=MIN_INSTANCE_VERSION_FOR_OPCUA_CONNECTOR_TEMPLATE
                ),
            },
        ),
        (
            UpgradeScenario("Combined: registry + OPC UA template + secretsync ordering")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.4.0")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_OPCUA_CONNECTOR_TEMPLATE)
            .set_auxiliary_kwargs(
                secretsync_migration_needed=True,
                default_registry_exists=False,
                opcua_connector_template_exists=False,
            ),
            {
                EXTENSION_TYPE_CM: build_extension_props(EXTENSION_TYPE_CM, version=BUILT_IN_VALUE),
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS, version=MIN_INSTANCE_VERSION_FOR_OPCUA_CONNECTOR_TEMPLATE
                ),
            },
        ),
        # ========== SecretSync Migration (>= MIN_INSTANCE_VERSION_FOR_CM_MIGRATE) ==========
        (
            UpgradeScenario("SecretSync: Migrate opc-ua-connector SPC to default")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE)
            .set_auxiliary_kwargs(secretsync_migration_needed=True, default_registry_exists=False),
            {
                EXTENSION_TYPE_CM: build_extension_props(EXTENSION_TYPE_CM, version=BUILT_IN_VALUE),
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS, version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE
                ),
            },
        ),
        (
            UpgradeScenario("SecretSync: No migration when version < MIN_INSTANCE_VERSION_FOR_CM_MIGRATE")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(ops_version="1.2.82")
            .set_auxiliary_kwargs(secretsync_migration_needed=False, default_registry_exists=True),
            {
                EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version="1.2.82"),
            },
        ),
        (
            UpgradeScenario("SecretSync: No migration when has_v1_spc returns False")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE)
            .set_auxiliary_kwargs(secretsync_migration_needed=False, default_registry_exists=False),
            {
                EXTENSION_TYPE_CM: build_extension_props(EXTENSION_TYPE_CM, version=BUILT_IN_VALUE),
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS, version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE
                ),
            },
        ),
        (
            UpgradeScenario("SecretSync: Migration without registry creation")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE)
            .set_auxiliary_kwargs(secretsync_migration_needed=True, default_registry_exists=True),
            {
                EXTENSION_TYPE_CM: build_extension_props(EXTENSION_TYPE_CM, version=BUILT_IN_VALUE),
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS, version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE
                ),
            },
        ),
        (
            UpgradeScenario("SecretSync: Migration with all other migrations")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(
                ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE,
                ns_resource_id="PLACEHOLDER_ADR_NAMESPACE_ID",
            )
            .set_auxiliary_kwargs(
                remove_adr_for_test=True,
                expect_instance_update=True,
                default_registry_exists=False,
                secretsync_migration_needed=True,
            ),
            {
                EXTENSION_TYPE_CM: build_extension_props(EXTENSION_TYPE_CM, version=BUILT_IN_VALUE),
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS, version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE
                ),
            },
        ),
        # ========== Default SPC Reference Update (>= MIN_INSTANCE_VERSION_FOR_CM_MIGRATE) ==========
        (
            UpgradeScenario("SPC Ref: Add reference when default SPC exists but not linked")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE)
            .set_auxiliary_kwargs(has_default_spc_only=True, expect_instance_update=False),
            {
                EXTENSION_TYPE_CM: build_extension_props(EXTENSION_TYPE_CM, version=BUILT_IN_VALUE),
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS, version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE
                ),
            },
        ),
        (
            UpgradeScenario("SPC Ref: Skip update when reference already exists")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE)
            .set_auxiliary_kwargs(has_existing_spc_ref=True, has_default_spc_only=True),
            {
                EXTENSION_TYPE_CM: build_extension_props(EXTENSION_TYPE_CM, version=BUILT_IN_VALUE),
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS, version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE
                ),
            },
        ),
        (
            UpgradeScenario("SPC Ref: No update when default SPC doesn't exist")
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
            UpgradeScenario("SPC Ref: Update with both ADR namespace and SPC reference")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(
                ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE,
                ns_resource_id="PLACEHOLDER_ADR_NAMESPACE_ID",
            )
            .set_auxiliary_kwargs(
                remove_adr_for_test=True,
                expect_instance_update=True,
                has_default_spc_only=True,
            ),
            {
                EXTENSION_TYPE_CM: build_extension_props(EXTENSION_TYPE_CM, version=BUILT_IN_VALUE),
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS, version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE
                ),
            },
        ),
        (
            UpgradeScenario("SPC Ref: Add reference during secretsync migration")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE)
            .set_auxiliary_kwargs(secretsync_migration_needed=True),
            {
                EXTENSION_TYPE_CM: build_extension_props(EXTENSION_TYPE_CM, version=BUILT_IN_VALUE),
                EXTENSION_TYPE_OPS: build_extension_props(
                    EXTENSION_TYPE_OPS, version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE
                ),
            },
        ),
        (
            UpgradeScenario("SPC Ref: No update when version < MIN_INSTANCE_VERSION_FOR_CM_MIGRATE")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0")
            .set_user_kwargs(ops_version="1.2.82")
            .set_auxiliary_kwargs(has_default_spc_only=True),
            {
                EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version="1.2.82"),
            },
        ),
        # ========== Early Validation - IoT Ops validation blocks migration operations ==========
        (
            UpgradeScenario("Missing data: Current version is None blocks upgrade")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers=None)
            .set_user_kwargs(ops_version="1.2.0")
            .expecting_validation_error(r"Unable to determine installed version for.*Cannot validate upgrade path"),
            {},
        ),
        (
            UpgradeScenario("Missing data: Current train is None blocks upgrade")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.1.0", ext_train=None)
            .set_user_kwargs(ops_version="1.2.0")
            .expecting_validation_error(
                r"Unable to determine release train for installed.*Cannot validate upgrade path"
            ),
            {},
        ),
        (
            UpgradeScenario("Missing data: Force bypasses missing version check")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers=None)
            .set_user_kwargs(ops_version="1.2.0", force=True),
            {EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version="1.2.0")},
        ),
        (
            UpgradeScenario("Missing data: Force bypasses missing train check")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.1.0", ext_train=None)
            .set_user_kwargs(ops_version="1.2.0", force=True),
            {EXTENSION_TYPE_OPS: build_extension_props(EXTENSION_TYPE_OPS, version="1.2.0")},
        ),
        (
            UpgradeScenario("Early Validation: IoT Ops downgrade blocks platform migration")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE)
            .set_user_kwargs(ops_version="1.2.0")  # Downgrade from MIN_INSTANCE_VERSION_FOR_CM_MIGRATE
            .expecting_validation_error(r"is a downgrade which is not supported"),
            {},
        ),
        (
            UpgradeScenario("Early Validation: IoT Ops minor version gap blocks platform migration")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.1.59")  # Meets min v1 requirement
            .set_user_kwargs(ops_version="1.5.0")
            .expecting_validation_error(r"incompatible \(more than 2 minor versions ahead\)"),
            {},
        ),
        (
            UpgradeScenario("Early Validation: IoT Ops preview train blocks platform migration")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.2.0", ext_train="preview")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE)
            .expecting_validation_error(r"Upgrades to or from non-stable release trains are not supported"),
            {},
        ),
        (
            UpgradeScenario("Early Validation: IoT Ops min v2 requirement blocks platform migration")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.0.0")
            .set_user_kwargs(ops_version="1.2.36")  # Current is below min v1 version (1.1.59) required for v2 upgrade
            .expecting_validation_error(r"min compatible upgrade version.*1\.1\.59"),
            {},
        ),
        (
            UpgradeScenario("Early Validation: Force bypasses validation and allows migration")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0")
            .set_extension(ext_type=EXTENSION_TYPE_CM, remove=True)
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="1.0.0")
            .set_user_kwargs(ops_version=MIN_INSTANCE_VERSION_FOR_CM_MIGRATE, force=True),
            {
                # Platform deleted, CM created, IoT Ops upgraded - all operations proceed with force
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
    connector_template_count = int(expects_connector_template_creation(target_scenario))
    secretsync_count = int(expects_secretsync_migration(target_scenario))

    expected_count = (
        delete_count
        + create_count
        + update_count
        + instance_count
        + registry_count
        + connector_template_count
        + secretsync_count
    )

    assert len(upgrade_result) == expected_count
    assert len(mocked_confirm.ask.mock_calls) == int(not target_scenario.confirm_yes)

    assert_operation_order(target_scenario, upgrade_result)
    assert_result(target_scenario, upgrade_result, expected_patched_ext_types)
    assert_displays(spy_upgrade_displays, no_progress, patched_ext_types=expected_patched_ext_types)
    assert_secretsync_migration(target_scenario)


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


def assert_secretsync_migration(target_scenario: UpgradeScenario):
    """Verify SecretSync migration mocks were called correctly."""
    if not expects_secretsync_migration(target_scenario):
        # Verify no migration operations occurred when not expected
        if hasattr(target_scenario, "mock_calls_tracker"):
            tracker = target_scenario.mock_calls_tracker
            assert len(tracker["resource_graph"]) == 1, "Resource graph should be called even when no migration"
            assert len(tracker["patch_spc"]) == 0, "No SPC patches should occur when migration not needed"
            assert len(tracker["patch_secretsync"]) == 0, "No SecretSync patches should occur when migration not needed"
            assert len(tracker["delete_spc"]) == 0, "No SPC deletes should occur when migration not needed"
        return

    tracker = target_scenario.mock_calls_tracker

    # Verify resource graph query
    assert len(tracker["resource_graph"]) == 1, "Resource graph query should be called during init"

    # Verify PATCH operations
    assert len(tracker["patch_spc"]) == 1, f"Expected 1 PATCH SPC call, got {len(tracker['patch_spc'])}"

    if tracker["patch_spc"]:
        patched_objects_yaml = tracker["patch_spc"][0]["body"]["properties"]["objects"]
        patched_objects = yaml.safe_load(patched_objects_yaml)
        # The merged SPC should have 3 objects (1 from opc-ua + 2 from default)
        assert (
            len(patched_objects["array"]) == 3
        ), f"Merged SPC should have 3 secrets, got {len(patched_objects['array'])}"

    # Two v1 SecretSyncs need to be patched based on our test data
    assert (
        len(tracker["patch_secretsync"]) == 2
    ), f"Expected 2 PATCH SecretSync calls, got {len(tracker['patch_secretsync'])}"

    # Verify DELETE operation
    assert len(tracker["delete_spc"]) == 1, f"Expected 1 DELETE SPC call, got {len(tracker['delete_spc'])}"


def assert_connector_template_result(target_scenario: UpgradeScenario, connector_templates: List[dict]):
    """Validate OPC UA connector template creation/repair in the upgrade result."""
    if not expects_connector_template_creation(target_scenario):
        assert not connector_templates, f"Unexpected connector template(s) in results. Found {len(connector_templates)}"
        return

    assert connector_templates, "Expected OPC UA connector template creation but none found in results"
    assert len(connector_templates) == 1, f"Expected exactly 1 connector template, found {len(connector_templates)}"
    template = connector_templates[0]

    endpoint_types = template["properties"]["deviceInboundEndpointTypes"]
    assert endpoint_types[0]["endpointType"] == OPCUA_CONNECTOR_ENDPOINT_TYPE
    image_settings = template["properties"]["runtimeConfiguration"]["managedConfigurationSettings"][
        "imageConfigurationSettings"
    ]
    assert image_settings["imageName"] == "azureiotoperations/aio-connectors/supervisor"
    assert image_settings["tagDigestSettings"]["tag"] == OPCUA_CONNECTOR_VERSION

    # When repairing a discovered failed template, the create must reuse that exact ARM name
    # rather than deriving a new CLI name (otherwise it would orphan the failed resource).
    aux = target_scenario.aux_kwargs
    is_repair = (
        aux.get("opcua_connector_template_exists")
        and (aux.get("opcua_connector_template_provisioning_state") or "").lower() == PROVISIONING_STATE_FAILED.lower()
        and (aux.get("opcua_connector_template_name") or "").lower().startswith(OPCUA_CONNECTOR_TEMPLATE_NAME_PREFIX)
    )
    if is_repair:
        assert template["name"] == aux["opcua_connector_template_name"], (
            f"Repair must reuse the discovered template name '{aux['opcua_connector_template_name']}', "
            f"got '{template['name']}'"
        )


def assert_result(
    target_scenario: UpgradeScenario, upgrade_result: List[dict], expected_types: Optional[Dict[str, dict]] = None
):
    if not upgrade_result:
        return

    result_by_type = {}
    deleted_types = set()
    created_types = set()
    created_extensions = {}
    instance_updates = []
    registry_endpoints = []
    connector_templates = []
    secretsync_migrations = []

    for result in upgrade_result:
        props = result.get("properties", {})
        ext_type = props.get("extensionType")

        # Check if this is a registry endpoint creation
        if (
            result.get("name") == "default"
            and result.get("type") == "Microsoft.IoTOperations/instances/registryEndpoints"
        ):
            registry_endpoints.append(result)
            continue

        # Check if this is an OPC UA connector template creation
        if result.get("type") == "Microsoft.IoTOperations/instances/akriConnectorTemplates":
            connector_templates.append(result)
            continue

        # Check if this is a secretsync migration result (patched default SPC)
        if not ext_type and result.get("name", "").startswith("spc-ops-") and "objects" in props:
            secretsync_migrations.append(result)
            continue

        # Check if this is an instance update (has adrNamespaceRef or defaultSecretProviderClassRef)
        if not ext_type and ("adrNamespaceRef" in props or "defaultSecretProviderClassRef" in props):
            instance_updates.append(result)
            continue

        # Skip if no extension type and not a special operation
        if not ext_type:
            continue

        if props.get("provisioningState") == "Deleted":
            deleted_types.add(ext_type)
        elif ext_type in target_scenario.create_record:
            created_types.add(ext_type)
            created_extensions[ext_type] = result
        else:
            result_by_type[ext_type] = result

    # Validate instance updates
    if target_scenario.expect_instance_update:
        assert len(instance_updates) == 1, f"Expected exactly one instance update, got {len(instance_updates)}"
        instance_update = instance_updates[0]
        props = instance_update.get("properties", {})

        # Check ADR namespace update if provided
        if target_scenario.user_kwargs.get("ns_resource_id"):
            assert "adrNamespaceRef" in props, "Expected adrNamespaceRef in instance update"
            assert props["adrNamespaceRef"]["resourceId"], "Expected resourceId in adrNamespaceRef"

        # Check SPC reference update based on scenario flags
        has_default_spc = (
            target_scenario.aux_kwargs.get("has_default_spc_only") or target_scenario.secretsync_migration_needed
        )
        has_existing_ref = target_scenario.aux_kwargs.get("has_existing_spc_ref")

        if has_default_spc and not has_existing_ref:
            assert "defaultSecretProviderClassRef" in props, "Expected defaultSecretProviderClassRef in instance update"
            assert props["defaultSecretProviderClassRef"][
                "resourceId"
            ], "Expected resourceId in defaultSecretProviderClassRef"
            # Verify it points to the correct SPC
            expected_spc_name = DEFAULT_SPC_NAME
            assert expected_spc_name in props["defaultSecretProviderClassRef"]["resourceId"], (
                f"Expected SPC reference to contain '{expected_spc_name}', "
                f"got {props['defaultSecretProviderClassRef']['resourceId']}"
            )
        elif target_scenario.user_kwargs.get("ns_resource_id") and not has_default_spc:
            # ADR-only update should not include SPC reference
            assert (
                "defaultSecretProviderClassRef" not in props
            ), "Should not include defaultSecretProviderClassRef when no default SPC exists"
    else:
        assert len(instance_updates) == 0, f"Expected no instance updates, got {len(instance_updates)}"

    # Validate registry endpoint creation
    if expects_registry_creation(target_scenario):
        assert registry_endpoints, "Expected registry endpoint creation but none found in results"
        assert len(registry_endpoints) == 1, f"Expected exactly 1 registry endpoint, found {len(registry_endpoints)}"
        endpoint = registry_endpoints[0]
        assert endpoint["properties"]["host"] == expected_default_registry["properties"]["host"]
        assert endpoint["properties"]["authentication"] == expected_default_registry["properties"]["authentication"]
    else:
        assert not registry_endpoints, f"Unexpected registry endpoint(s) in results. Found {len(registry_endpoints)}"

    assert_connector_template_result(target_scenario, connector_templates)

    # Validate secretsync migration
    if expects_secretsync_migration(target_scenario):
        assert secretsync_migrations, "Expected secretsync migration but none found in results"
        assert (
            len(secretsync_migrations) == 1
        ), f"Expected exactly 1 secretsync migration, found {len(secretsync_migrations)}"
        migration = secretsync_migrations[0]
        # Verify the objects were merged correctly
        objects_yaml = migration["properties"]["objects"]
        objects = yaml.safe_load(objects_yaml)
        assert len(objects["array"]) == 3, f"Expected 3 merged secrets in default SPC, got {len(objects['array'])}"

        # Verify all secrets from both SPCs are present by checking object names
        object_names = set()
        for obj_str in objects["array"]:
            obj_data = yaml.safe_load(obj_str)
            if "objectName" in obj_data:
                object_names.add(obj_data["objectName"])

        expected_names = {"cert-der", "cert2-der", "cert-san-app-der"}
        assert object_names == expected_names, f"Expected object names {expected_names}, got {object_names}"
    else:
        assert (
            not secretsync_migrations
        ), f"Unexpected secretsync migration(s) in results. Found {len(secretsync_migrations)}"

    _assert_user_kwargs_applied(target_scenario.user_kwargs, result_by_type, deleted_types)

    # Validate expected types if provided
    if expected_types:
        _assert_expected_types(
            expected_types, result_by_type, deleted_types, created_types, created_extensions, target_scenario
        )


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
    expected_types: dict,
    result_by_type: dict,
    deleted_types: set,
    created_types: set,
    created_extensions: dict,
    scenario,
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
        if ext_type in created_extensions and ext_type in expected:
            _validate_created_extension(created_extensions[ext_type], expected[ext_type])
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
    """Assert that upgrade displays are shown correctly."""

    # Auto-calculate expected progress count
    if progress_count is None:
        if error_context:
            error_value = error_context.value if hasattr(error_context, "value") else error_context

            if isinstance(error_value, ValidationError):
                error_msg = str(error_value)

                # These errors occur early (before table render), only 1 progress init
                early_errors = [
                    "is not connected",
                    "IoT Operations extension not detected",
                    "requires an ADR namespace",
                ]

                ops_validation_patterns = [
                    "is a downgrade",
                    "incompatible",
                    "min compatible upgrade version",
                    "non-stable release trains",
                    "Unable to determine",
                ]
                is_ops_validation_error = EXTENSION_MONIKER_OPS in error_msg and any(
                    pattern in error_msg for pattern in ops_validation_patterns
                )

                if any(phrase in error_msg for phrase in early_errors):
                    progress_count = 1
                elif is_ops_validation_error:
                    # IoT Operations validation errors are early (gatekeeper for entire upgrade)
                    progress_count = 1
                else:
                    # Other validation errors (e.g., certManager downgrade) are late
                    progress_count = 2
            elif isinstance(error_value, HttpResponseError):
                # HTTP errors occur during apply_upgrades, after table render
                progress_count = 2
            else:
                # Other errors default to 1
                progress_count = 1
        else:
            # Success scenarios
            progress_count = 2

    # Verify progress initialization count
    progress_calls = spy_upgrade_displays["progress.__init__"].mock_calls
    actual_count = len(progress_calls)

    assert actual_count == progress_count, f"Expected {progress_count} progress init(s), got {actual_count}"

    # Verify progress parameters
    if actual_count > 0:
        assert progress_calls[0].kwargs.get("transient") is True
        assert progress_calls[0].kwargs.get("disable") == no_progress

    if actual_count > 1:
        assert progress_calls[1].kwargs.get("transient") is False
        assert progress_calls[1].kwargs.get("disable") == no_progress

    # Verify table display for success scenarios
    if not no_progress and not error_context and patched_ext_types:
        print_calls = spy_upgrade_displays["print"].mock_calls
        assert len(print_calls) > 0, "Expected Console.print for table display"


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


def test_spc_resource_id_extraction(mocked_cmd: Mock):
    """Test that SPC resource ID is correctly extracted from secretsync resources."""
    from azext_edge.edge.providers.orchestration.migration import SecretSyncMigrationManager

    mock_instance = {"id": "test-instance"}
    mock_resource_map = Mock()

    secretsync_resources = {
        SPC_RESOURCE_TYPE: [
            {
                "id": "/subscriptions/sub1/resourceGroups/rg1/.../secretProviderClasses/opc-ua-connector",
                "name": "opc-ua-connector",
                "type": SPC_RESOURCE_TYPE,
                "properties": {"objects": "array: []"},
            },
            {
                "id": "/subscriptions/sub1/resourceGroups/rg1/.../secretProviderClasses/spc-ops-12345",
                "name": "spc-ops-12345",
                "type": SPC_RESOURCE_TYPE,
                "properties": {"objects": "array: []"},
            },
        ]
    }

    manager = SecretSyncMigrationManager(
        cmd=mocked_cmd,
        instance_record=mock_instance,
        resource_map=mock_resource_map,
        secretsync_resources=secretsync_resources,
    )

    assert manager.spc_opcua is not None
    assert manager.spc_opcua["name"] == "opc-ua-connector"
    assert manager.spc_default is not None
    assert manager.spc_default["name"] == "spc-ops-12345"
    assert manager.spc_default["id"] == "/subscriptions/sub1/resourceGroups/rg1/.../secretProviderClasses/spc-ops-12345"
    assert manager.has_v1_spc() is True

    # Test with only default SPC
    secretsync_resources_only_default = {
        SPC_RESOURCE_TYPE: [
            {
                "id": "/subscriptions/sub1/resourceGroups/rg1/.../secretProviderClasses/spc-ops-67890",
                "name": "spc-ops-67890",
                "type": SPC_RESOURCE_TYPE,
                "properties": {"objects": "array: []"},
            },
        ]
    }

    manager2 = SecretSyncMigrationManager(
        cmd=mocked_cmd,
        instance_record=mock_instance,
        resource_map=mock_resource_map,
        secretsync_resources=secretsync_resources_only_default,
    )

    assert manager2.spc_opcua is None
    assert manager2.spc_default is not None
    assert manager2.spc_default["name"] == "spc-ops-67890"
    assert manager2.has_v1_spc() is False

    # Test with no SPCs
    manager3 = SecretSyncMigrationManager(
        cmd=mocked_cmd,
        instance_record=mock_instance,
        resource_map=mock_resource_map,
        secretsync_resources={},
    )

    assert manager3.spc_opcua is None
    assert manager3.spc_default is None
    assert manager3.has_v1_spc() is False


def test_opcua_connector_template_backfill_active_by_default():
    """Guard the alignment between the OPC UA backfill gate and the pinned manifest version.

    A default `az iot ops upgrade` (no --ops-version) resolves the pinned
    TEMPLATE_BLUEPRINT_INSTANCE iotOperations version as the target, so the backfill is active by
    default only while that pinned version is at/above MIN_INSTANCE_VERSION_FOR_OPCUA_CONNECTOR_TEMPLATE.
    This fails if a manifest regression drops below the gate and silently makes the backfill inert.
    """
    assert semver.parse(PINNED_IOTOPS_VERSION) >= semver.parse(MIN_INSTANCE_VERSION_FOR_OPCUA_CONNECTOR_TEMPLATE), (
        f"Pinned iotOperations manifest ({PINNED_IOTOPS_VERSION}) is below the OPC UA connector template "
        f"gate ({MIN_INSTANCE_VERSION_FOR_OPCUA_CONNECTOR_TEMPLATE}); a default upgrade would skip the "
        "backfill. Re-align the gate or the manifest."
    )


def test_opcua_connector_version_matches_template_tag():
    """Guard that the upgrade-side OPCUA_CONNECTOR_VERSION matches the tag stamped by the template.

    `az iot ops create` stamps the connectors tag from the OPCUA_CONNECTOR_VERSION ARM variable in
    TEMPLATE_BLUEPRINT_INSTANCE, while `az iot ops upgrade` stamps the OPCUA_CONNECTOR_VERSION
    constant. Nothing else couples them, so this fails if a template regeneration bumps one without
    the other (which would otherwise stamp two different tags on the same release).
    """
    import re

    opcua_var = TEMPLATE_BLUEPRINT_INSTANCE.content["variables"].get("OPCUA_CONNECTOR_VERSION")
    assert opcua_var, "OPCUA_CONNECTOR_VERSION variable missing from the instance template."
    # The connectors tag is the coalesce fallback literal, i.e. the last single-quoted token.
    quoted_literals = re.findall(r"'([^']*)'", opcua_var)
    template_tag = quoted_literals[-1] if quoted_literals else None
    assert template_tag == OPCUA_CONNECTOR_VERSION, (
        f"OPCUA_CONNECTOR_VERSION constant ({OPCUA_CONNECTOR_VERSION}) does not match the connectors "
        f"tag stamped by the instance template ({template_tag}); update the constant during the "
        "release bump so create and upgrade stamp the same tag."
    )


def test_check_opcua_connector_template_needed_disabled():
    """Upgrade must not create the default OPC UA connector template when the instance has
    opcua.mode=Disabled. With the feature off the OPC UA supervisor is not deployed, so the
    akriConnectorTemplates PUT never reaches a terminal state and hangs the upgrade.
    """
    from azext_edge.edge.providers.orchestration.upgrade2 import UpgradeManager

    manager = UpgradeManager.__new__(UpgradeManager)
    manager.instance_name = generate_random_string()
    manager.resource_group_name = generate_random_string()
    manager._opcua_template_name_to_repair = None
    manager.instance_record = {"properties": {"features": {"opcua": {"mode": "Disabled"}}}}
    manager.connector_templates = Mock()
    manager.connector_templates.list.return_value = []

    needed, repair_name = manager._check_opcua_connector_template_needed()

    assert needed is False
    assert repair_name is None


def build_ext_upgrade_state(
    ext_type: str = EXTENSION_TYPE_CM,
    current_version: Optional[str] = "1.4.73",
    current_train: Optional[str] = "stable",
    built_in_version: Optional[str] = "1.3.105",
    built_in_train: Optional[str] = "stable",
    provisioning_state: str = PROVISIONING_STATE_SUCCESS,
    version_override: Optional[str] = None,
    train_override: Optional[str] = None,
    desired_config: Optional[Dict[str, str]] = None,
    force: bool = False,
    operation_type=None,
):
    """Build an ExtensionUpgradeState directly, bypassing cluster discovery."""
    from azext_edge.edge.providers.orchestration.upgrade2 import ConfigOverride, ExtensionUpgradeState

    props: Dict[str, str] = {"extensionType": ext_type, "provisioningState": provisioning_state}
    if current_version:
        props["version"] = current_version
    if current_train:
        props["releaseTrain"] = current_train

    return ExtensionUpgradeState(
        extension={"name": generate_random_string(), "properties": props},
        desired_version_map={"version": built_in_version, "train": built_in_train},
        desired_config=desired_config,
        override=ConfigOverride(version=version_override, train=train_override),
        force=force,
        operation_type=operation_type,
    )


def test_desired_state_ignores_built_in_target_when_no_version_is_sent():
    """Only configuration is sent, so Desired State must report the version that stays deployed."""
    from azext_edge.edge.providers.orchestration.upgrade2 import format_extension_row

    ext = build_ext_upgrade_state(desired_config={"a": "b"})
    current, desired, action = format_extension_row(ext)

    assert "version" not in ext.get_patch()["properties"]
    assert "1.4.73" in current
    assert "1.4.73" in desired
    assert "1.3.105" not in desired
    assert "[dim]" in desired
    assert "cyan" not in desired
    assert "Set a: [bold]b[/bold]" in action


def test_desired_state_version_only_patch_keeps_current_train():
    """A user supplied version suppresses the train delta, so the train must not come from the map."""
    from azext_edge.edge.providers.orchestration.upgrade2 import format_extension_row

    ext = build_ext_upgrade_state(built_in_version="1.5.0", built_in_train="preview", version_override="1.6.0")
    _, desired, _ = format_extension_row(ext)

    assert "releaseTrain" not in ext.get_patch()["properties"]
    assert "1.6.0" in desired
    assert "stable" in desired
    assert "preview" not in desired


@pytest.mark.parametrize(
    "built_in_version,provisioning_state,expected_action,rejected_action",
    [
        pytest.param(
            "1.3.105",
            PROVISIONING_STATE_FAILED,
            "Reconcile at version [bold]1.4.73[/bold]",
            "Update version to",
            id="same-version retry reads as reconcile",
        ),
        pytest.param(
            "1.5.0",
            PROVISIONING_STATE_SUCCESS,
            "Update version to [bold]1.5.0[/bold]",
            "Reconcile at version",
            id="real upgrade still reads as update",
        ),
    ],
)
def test_action_distinguishes_reconcile_from_update(
    built_in_version, provisioning_state, expected_action, rejected_action
):
    from azext_edge.edge.providers.orchestration.upgrade2 import format_extension_row

    ext = build_ext_upgrade_state(built_in_version=built_in_version, provisioning_state=provisioning_state)
    _, desired, action = format_extension_row(ext)

    assert expected_action in action
    assert rejected_action not in action
    assert "1.3.105" not in desired


def test_failed_non_ops_extension_no_longer_renders_unknown():
    from azext_edge.edge.providers.orchestration.upgrade2 import format_extension_row

    ext = build_ext_upgrade_state(ext_type=EXTENSION_TYPE_CM, provisioning_state=PROVISIONING_STATE_FAILED)

    assert ext.can_upgrade() is True
    current, desired, action = format_extension_row(ext)

    assert "Unknown" not in current + desired + action
    assert "Check configuration" not in action
    assert ext.get_patch()["properties"]["version"] == "1.4.73"


@pytest.mark.parametrize(
    "built_in_version,provisioning_state,force,expected_version",
    [
        pytest.param("1.5.0", PROVISIONING_STATE_SUCCESS, False, "1.5.0", id="real upgrade"),
        pytest.param("1.5.0", PROVISIONING_STATE_FAILED, False, "1.5.0", id="real upgrade over a failed state"),
        pytest.param(
            "1.3.105",
            PROVISIONING_STATE_FAILED,
            False,
            "1.4.73",
            id="stale CLI repairs a failed extension",
        ),
        pytest.param("1.4.73", PROVISIONING_STATE_FAILED, False, "1.4.73", id="same-version retry"),
        pytest.param("1.3.105", PROVISIONING_STATE_FAILED, True, "1.4.73", id="force alone never downgrades"),
        pytest.param("1.3.105", PROVISIONING_STATE_SUCCESS, True, None, id="force alone sends nothing"),
    ],
)
def test_get_patch_version_selection(built_in_version, provisioning_state, force, expected_version):
    ext = build_ext_upgrade_state(built_in_version=built_in_version, provisioning_state=provisioning_state, force=force)

    ext.validate_upgrade()
    assert ext.get_patch().get("properties", {}).get("version") == expected_version


def test_failed_extension_without_installed_version_is_bypassed_by_force():
    ext = build_ext_upgrade_state(current_version=None, provisioning_state=PROVISIONING_STATE_FAILED, force=True)

    ext.validate_upgrade()
    assert ext.get_patch()["properties"]["version"] == "1.3.105"


def test_failed_extension_never_emits_a_null_version():
    """Extensions absent from the built-in map must raise rather than patch "version": None."""
    ext = build_ext_upgrade_state(
        current_version=None,
        built_in_version=None,
        provisioning_state=PROVISIONING_STATE_FAILED,
        force=True,
    )

    with pytest.raises(ValidationError, match="Unable to determine installed version"):
        ext.validate_upgrade()
    with pytest.raises(ValidationError, match="Unable to determine installed version"):
        ext.get_patch()


@pytest.mark.parametrize("op_type_name", ["CREATE", "DELETE"])
def test_validate_upgrade_skips_non_update_operations(op_type_name):
    from azext_edge.edge.providers.orchestration.upgrade2 import ExtensionOperation

    ext = build_ext_upgrade_state(
        current_version=None,
        provisioning_state=PROVISIONING_STATE_FAILED,
        operation_type=getattr(ExtensionOperation, op_type_name),
    )

    ext.validate_upgrade()
    assert not ext.get_patch()


@pytest.mark.parametrize(
    "built_in_train,train_override",
    [
        pytest.param("preview", None, id="train delta from built-in target"),
        pytest.param("stable", "preview", id="train delta from --ops-train override"),
    ],
)
def test_reconcile_cannot_bypass_release_train_guard(built_in_train, train_override):
    """Both routes are covered: an --ops-train override short circuits before the version compare."""
    ext = build_ext_upgrade_state(
        ext_type=EXTENSION_TYPE_OPS,
        built_in_version="1.4.73",
        built_in_train=built_in_train,
        train_override=train_override,
        provisioning_state=PROVISIONING_STATE_FAILED,
    )

    with pytest.raises(ValidationError, match="non-stable release trains are not supported"):
        ext.validate_upgrade()
    with pytest.raises(ValidationError, match="non-stable release trains are not supported"):
        ext.get_patch()


def test_reconcile_train_delta_validates_the_version_the_patch_sends():
    # A train override re-runs the guard, it must compare the reconcile version, not the stale built-in.
    ext = build_ext_upgrade_state(
        ext_type=EXTENSION_TYPE_OPS,
        current_version="1.4.73",
        built_in_version="1.3.105",
        train_override="stable",
        provisioning_state=PROVISIONING_STATE_FAILED,
    )

    ext.validate_upgrade()

    assert ext.get_patch()["properties"]["version"] == "1.4.73"


def test_reconcile_repairs_a_failed_extension_on_a_preview_train():
    ext = build_ext_upgrade_state(
        ext_type=EXTENSION_TYPE_OPS,
        current_version="1.4.73",
        current_train="preview",
        built_in_version="1.3.105",
        built_in_train="preview",
        provisioning_state=PROVISIONING_STATE_FAILED,
    )

    ext.validate_upgrade()

    assert ext.get_patch()["properties"]["version"] == "1.4.73"


@pytest.mark.parametrize("provisioning_state", [PROVISIONING_STATE_SUCCESS, PROVISIONING_STATE_FAILED])
def test_explicit_downgrade_still_blocked(provisioning_state):
    ext = build_ext_upgrade_state(version_override="1.0.0", provisioning_state=provisioning_state)

    with pytest.raises(ValidationError, match="downgrade which is not supported"):
        ext.validate_upgrade()
    with pytest.raises(ValidationError, match="downgrade which is not supported"):
        ext.get_patch()


@pytest.mark.parametrize("provisioning_state", [PROVISIONING_STATE_SUCCESS, PROVISIONING_STATE_FAILED])
def test_explicit_downgrade_allowed_with_force(provisioning_state):
    ext = build_ext_upgrade_state(version_override="1.0.0", provisioning_state=provisioning_state, force=True)

    ext.validate_upgrade()
    assert ext.get_patch()["properties"]["version"] == "1.0.0"


@pytest.mark.parametrize(
    "built_in_version,current_version,version_override,operation_type_name,expected",
    [
        ("1.3.105", "1.4.73", None, None, True),
        ("1.5.0", "1.4.73", None, None, False),
        ("1.4.73", "1.4.73", None, None, False),
        # An explicit version override decides what is sent, so a stale built-in must not warn.
        ("1.4.73", "1.4.73", "1.0.0", None, False),
        ("1.4.73", "1.4.90", "1.5.0", None, False),
        ("1.3.105", "1.4.73", "1.4.73", None, False),
        (None, "1.4.73", None, None, False),
        ("1.3.105", None, None, None, False),
        ("1.3.105", "not-a-version", None, None, False),
        ("1.3.105", "1.4.73", None, "DELETE", False),
        ("1.3.105", "1.4.73", None, "CREATE", False),
    ],
)
def test_is_cli_behind_cluster(built_in_version, current_version, version_override, operation_type_name, expected):
    from azext_edge.edge.providers.orchestration.upgrade2 import ExtensionOperation

    ext = build_ext_upgrade_state(
        built_in_version=built_in_version,
        current_version=current_version,
        version_override=version_override,
        operation_type=getattr(ExtensionOperation, operation_type_name) if operation_type_name else None,
    )
    assert ext.is_cli_behind_cluster() is expected


@pytest.mark.parametrize("bad_version", [1.4, 14073, ["1.4.73"]])
def test_stale_cli_check_is_best_effort_on_a_malformed_version(bad_version):
    ext = build_ext_upgrade_state(current_version=bad_version)
    assert ext.is_cli_behind_cluster() is False


def test_stale_cli_warning_precedes_no_op_return(
    mocked_cmd: Mock,
    mocked_responses: responses,
    mocked_logger: Mock,
    mocked_sleep: Mock,
    spy_upgrade_displays: Dict[str, Mock],
    mocked_confirm: Mock,
    mocked_upgrade_manager: Mock,
):
    from azext_edge.edge.commands_edge import upgrade_instance

    resource_group_name = generate_random_string()
    instance_name = generate_random_string()

    target_scenario = UpgradeScenario("Stale CLI: deployed version ahead of built-in target").set_extension(
        ext_type=EXTENSION_TYPE_CM, ext_vers="9.9.9"
    )
    target_scenario.set_instance_mock(
        mocked_responses=mocked_responses, instance_name=instance_name, resource_group_name=resource_group_name
    )

    assert (
        upgrade_instance(
            cmd=mocked_cmd,
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            no_progress=True,
            confirm_yes=True,
        )
        is None
    )

    warning_calls = mocked_logger.warning.call_args_list
    assert len(warning_calls) == 2
    advisory = warning_calls[0].args[0]
    assert "newer than the version built into this CLI" in advisory
    assert "No deployed version of the listed extensions will be changed" in advisory
    assert "--force" not in advisory
    assert warning_calls[0].args[1] == EXTENSION_TYPE_TO_MONIKER_MAP[EXTENSION_TYPE_CM]
    assert warning_calls[1].args[0] == DEFAULT_LOG_WARNING_MESSAGE


@pytest.mark.parametrize("ext_type", [EXTENSION_TYPE_OPS, EXTENSION_TYPE_CM])
@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"version_override": "1.0.0"}, id="downgrade"),
        pytest.param({"built_in_version": "1.5.0"}, id="upgrade"),
        pytest.param({"provisioning_state": PROVISIONING_STATE_FAILED}, id="reconcile"),
        pytest.param(
            {"provisioning_state": PROVISIONING_STATE_FAILED, "built_in_train": "preview"}, id="train-guard"
        ),
        pytest.param(
            {"provisioning_state": PROVISIONING_STATE_FAILED, "current_version": None}, id="no-installed-version"
        ),
    ],
)
def test_validate_upgrade_and_get_patch_have_same_validation_outcome(ext_type, kwargs):
    """Both entry points resolve the target through the same helper, so their validation must agree."""

    def outcome(call) -> Optional[str]:
        try:
            call()
            return None
        except ValidationError as e:
            return str(e)

    assert outcome(build_ext_upgrade_state(ext_type=ext_type, **kwargs).validate_upgrade) == outcome(
        build_ext_upgrade_state(ext_type=ext_type, **kwargs).get_patch
    )
