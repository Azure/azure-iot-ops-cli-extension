# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


import json
import re
from enum import Enum
from random import randint
from typing import (
    Callable,
    Dict,
    FrozenSet,
    List,
    NamedTuple,
    Optional,
    Tuple,
    Type,
    Union,
)
from unittest.mock import Mock

import pytest
import requests
import responses
from azure.cli.core.azclierror import (
    AzureResponseError,
    InvalidArgumentValueError,
    ValidationError,
)

from azext_edge.edge.common import (
    DEFAULT_ARTIFACT_REGISTRY,
    DEFAULT_BROKER,
    DEFAULT_BROKER_AUTHN,
    DEFAULT_BROKER_LISTENER,
    DEFAULT_DATAFLOW_ENDPOINT,
    DEFAULT_DATAFLOW_PROFILE,
)
from azext_edge.edge.providers.base import DEFAULT_NAMESPACE
from azext_edge.edge.providers.orchestration.common import (
    ARM_ENDPOINT,
    CONTRIBUTOR_ROLE_ID,
    EXTENSION_TYPE_CM,
    EXTENSION_TYPE_OPS,
    EXTENSION_TYPE_SSC,
    OPS_EXTENSION_DEPS,
)
from azext_edge.edge.providers.orchestration.permissions import ROLE_DEF_FORMAT_STR
from azext_edge.edge.providers.orchestration.rp_namespace import (
    RP_NAMESPACE_OPTIONAL_SET,
    RP_NAMESPACE_SET,
)
from azext_edge.edge.providers.orchestration.targets import (
    InstancePhase,
    get_default_cl_name,
)
from azext_edge.edge.providers.orchestration.work import (
    PROVISIONING_STATE_SUCCESS,
    ClusterConnectStatus,
)
from azext_edge.edge.util import assemble_nargs_to_dict

from ...generators import (
    generate_random_string,
    generate_resource_id,
    get_zeroed_subscription,
)
from .resources.conftest import RequestKPIs, get_request_kpis
from .test_template_unit import EXPECTED_EXTENSION_RESOURCE_KEYS

ZEROED_SUBSCRIPTION = get_zeroed_subscription()


path_pattern_base = r"^/subscriptions/[0-9a-fA-F-]+/resourcegroups/[a-zA-Z0-9]+"
STANDARD_HEADERS = {"content-type": "application/json"}

OMIT_WRITE_METHODS = frozenset([responses.PUT, responses.POST])
OMIT_ALL_METHODS = frozenset([responses.PUT, responses.POST, responses.GET, responses.HEAD])

HEALTH_UNAVAILABLE_BASIC = {
    "code": 200,
    "body": {
        "properties": {
            "availabilityState": "Unavailable",
            "summary": "The cluster is experiencing issues.",
            "reasonType": "PlatformInitiated",
        }
    },
}

HEALTH_AVAILABLE = {
    "code": 200,
    "body": {"properties": {"availabilityState": "Available"}},
}

HEALTH_UNKNOWN = {
    "code": 200,
    "body": {"properties": {"availabilityState": "Unknown"}},
}

AUTHZ_FAILURE = {
    "code": 403,
    "body": {"error": {"code": "AuthorizationFailed", "message": "Access denied."}},
}


RESOURCE_NOT_FOUND_ERROR = {
    "code": 404,
    "body": {
        "error": {
            "code": "ResourceNotFound",
            "message": "The Resource was not found.",
        }
    },
}

UNAUTHORIZED_NAMESPACE_ERROR = {
    "code": 400,
    "body": {
        "error": {
            "code": "UnauthorizedNamespaceError",
            "message": "The namespace is not authorized for custom locations. "
            "Please enable the custom locations feature.",
        }
    },
}


class ExpectedAPIVersion(Enum):
    CONNECTED_CLUSTER = "2024-07-15-preview"
    CLUSTER_EXTENSION = "2023-05-01"
    RESOURCE = "2024-03-01"
    SCHEMA_REGISTRY = "2025-10-01"
    ADR_NAMESPACE = "2025-10-01"
    AUTHORIZATION = "2022-04-01"
    CUSTOM_LOCATION = "2021-08-31-preview"
    GRAPH = "2022-10-01"
    RESOURCE_HEALTH = "2025-05-01"


class CallKey(Enum):
    CONNECT_RESOURCE_MANAGER = "connectResourceManager"
    GET_CLUSTER = "getCluster"
    GET_RESOURCE_PROVIDERS = "getResourceProviders"
    GET_RESOURCE_HEALTH = "getResourceHealth"
    DEPLOY_INIT_WHATIF = "deployInitWhatIf"
    DEPLOY_INIT = "deployInit"
    GET_SCHEMA_REGISTRY = "getSchemaRegistry"
    GET_ADR_NAMESPACE = "getAdrNamespace"
    GET_CLUSTER_EXTENSIONS = "getClusterExtensions"
    GET_EXISTING_DEPLOYMENTS = "getExistingDeployments"
    GET_SCHEMA_REGISTRY_RA = "getSchemaRegistryRoleAssignments"
    PUT_SCHEMA_REGISTRY_RA = "putSchemaRegistryRoleAssignment"
    DEPLOY_CREATE_WHATIF = "deployCreateWhatIf"
    DEPLOY_CREATE_EXT = "deployCreateExtension"
    DEPLOY_CREATE_INSTANCE = "deployCreateInstance"
    DEPLOY_CREATE_RESOURCES = "deployCreateResources"
    CREATE_CUSTOM_LOCATION = "createCustomLocation"


CL_EXTENSION_TYPES = ["microsoft.azure.secretstore", "microsoft.iotoperations"]


class ExceptionMeta(NamedTuple):
    exc_type: Type[Exception]
    exc_msg: Optional[Union[str, List[str], re.Pattern]] = None


class ServiceGenerator:
    def __init__(self, scenario: dict, mocked_responses: responses, action: str = "init", **overrides):
        self.scenario = scenario
        self.mocked_responses = mocked_responses
        self._action = action
        self.call_map: Dict[CallKey, List[RequestKPIs]] = {}
        self._reset_call_map()
        self._bootstrap(**overrides)

    def _bootstrap(self, **kwargs):
        override_omit_http_method = kwargs.get("omit_http_methods", frozenset([]))
        omit_methods: Optional[FrozenSet[str]] = self.scenario.get("omitHttpMethods")
        if not omit_methods:
            omit_methods = frozenset([])

        omit_methods = omit_methods.union(override_omit_http_method)
        for method in [
            responses.GET,
            responses.HEAD,
            responses.POST,
            responses.PUT,
        ]:
            if method not in omit_methods:
                self.mocked_responses.add_callback(method=method, url=re.compile(r".*"), callback=self._handle_requests)
        self._reset_call_map()

    def _reset_call_map(self):
        self.call_map = {}
        for key in CallKey:
            self.call_map[key] = []

    def _handle_requests(self, request: requests.PreparedRequest) -> Optional[tuple]:
        request_kpis = get_request_kpis(request)
        for handler in [self._handle_common, self._handle_init, self._handle_cl_create, self._handle_create]:
            handler_response = handler(request_kpis)
            if handler_response:
                return handler_response

        raise RuntimeError(f"No match for {request_kpis.method} {request_kpis.url}.")

    def _handle_common(self, request_kpis: RequestKPIs) -> Optional[tuple]:
        # return (status_code, headers, body)
        if request_kpis.method == responses.HEAD:
            if request_kpis.url == ARM_ENDPOINT:
                self.call_map[CallKey.CONNECT_RESOURCE_MANAGER].append(request_kpis)
                return (200, {}, None)

        if request_kpis.method == responses.GET:
            if request_kpis.path_url == f"/subscriptions/{ZEROED_SUBSCRIPTION}/providers":
                assert request_kpis.params["api-version"] == ExpectedAPIVersion.RESOURCE.value
                self.call_map[CallKey.GET_RESOURCE_PROVIDERS].append(request_kpis)
                return (200, STANDARD_HEADERS, json.dumps(self.scenario["providerNamespace"]))

            if request_kpis.path_url == (
                f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourcegroups/{self.scenario['resourceGroup']}"
                f"/providers/Microsoft.Kubernetes/connectedClusters/{self.scenario['cluster']['name']}"
            ):
                assert request_kpis.params["api-version"] == ExpectedAPIVersion.CONNECTED_CLUSTER.value
                self.call_map[CallKey.GET_CLUSTER].append(request_kpis)
                return (200, STANDARD_HEADERS, json.dumps(self.scenario["cluster"]))

            if "/providers/Microsoft.ResourceHealth/availabilityStatuses/current" in request_kpis.path_url:
                assert request_kpis.params["api-version"] == ExpectedAPIVersion.RESOURCE_HEALTH.value
                assert (
                    request_kpis.params.get("$expand") == "recommendedactions"
                ), "Expected $expand=recommendedactions query parameter for health API call"
                self._assert_correlation_headers(request_kpis)
                self.call_map[CallKey.GET_RESOURCE_HEALTH].append(request_kpis)
                api_control = self.scenario["apiControl"][CallKey.GET_RESOURCE_HEALTH]
                return (api_control["code"], STANDARD_HEADERS, json.dumps(api_control["body"]))

    def _handle_init(self, request_kpis: RequestKPIs):
        url_deployment_seg = r"/providers/Microsoft\.Resources/deployments/aziotops\.enablement\.[a-zA-Z0-9\.-]+"
        if request_kpis.method == responses.POST:
            if re.match(
                path_pattern_base + url_deployment_seg + r"/whatIf$",
                request_kpis.path_url,
            ):
                self._assert_correlation_headers(request_kpis)
                assert request_kpis.params["api-version"] == ExpectedAPIVersion.RESOURCE.value
                assert f"/resourcegroups/{self.scenario['resourceGroup']}/" in request_kpis.path_url
                assert_init_deployment_body(body_str=request_kpis.body_str, target_scenario=self.scenario)
                self.call_map[CallKey.DEPLOY_INIT_WHATIF].append(request_kpis)
                api_control = self.scenario["apiControl"][CallKey.DEPLOY_INIT_WHATIF]
                return (api_control["code"], STANDARD_HEADERS, json.dumps(api_control["body"]))

        if request_kpis.method == responses.PUT:
            if re.match(
                path_pattern_base + url_deployment_seg,
                request_kpis.path_url,
            ):
                self._assert_correlation_headers(request_kpis)
                assert request_kpis.params["api-version"] == ExpectedAPIVersion.RESOURCE.value
                assert f"/resourcegroups/{self.scenario['resourceGroup']}/" in request_kpis.path_url
                assert_init_deployment_body(body_str=request_kpis.body_str, target_scenario=self.scenario)
                self.call_map[CallKey.DEPLOY_INIT].append(request_kpis)
                return (200, STANDARD_HEADERS, json.dumps({}))

    def _handle_cl_create(self, request_kpis: RequestKPIs):
        if request_kpis.method == responses.PUT:
            self._assert_correlation_headers(request_kpis)
            scenario_cl_name = self.scenario["customLocation"]["name"]
            scenario_namespace = self.scenario["instance"]["namespace"] or "azure-iot-operations"
            if not scenario_cl_name:
                scenario_cl_name = get_default_cl_name(
                    resource_group_name=self.scenario["resourceGroup"],
                    cluster_name=self.scenario["cluster"]["name"],
                    namespace=scenario_namespace,
                )
            if request_kpis.path_url == (
                f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{self.scenario['resourceGroup']}"
                f"/providers/Microsoft.ExtendedLocation/customLocations/{scenario_cl_name}"
            ):
                assert request_kpis.params["api-version"] == ExpectedAPIVersion.CUSTOM_LOCATION.value
                cl_payload = json.loads(request_kpis.body_str)
                assert cl_payload["properties"]["hostResourceId"] == self.scenario["cluster"]["id"]
                cl_create_call_len = len(self.call_map.get(CallKey.CREATE_CUSTOM_LOCATION, []))
                expected_ext_ids = self.scenario["cluster"]["extensions"]["value"]
                types_in_play = ["microsoft.azure.secretstore"] if not cl_create_call_len else CL_EXTENSION_TYPES
                expected_cl_ext_ids = set(
                    ext["id"] for ext in expected_ext_ids if ext["properties"]["extensionType"] in types_in_play
                )
                assert set(cl_payload["properties"]["clusterExtensionIds"]) == expected_cl_ext_ids
                self.call_map[CallKey.CREATE_CUSTOM_LOCATION].append(request_kpis)

                api_control = self.scenario["apiControl"][CallKey.CREATE_CUSTOM_LOCATION]
                status_code = api_control.get("code", 200)
                response_body = (
                    api_control.get("body") if api_control.get("body") else json.loads(request_kpis.body_str)
                )
                return (status_code, STANDARD_HEADERS, json.dumps(response_body))

    def _handle_create(self, request_kpis: RequestKPIs):
        if request_kpis.method == responses.GET:
            if request_kpis.path_url == self.scenario["schemaRegistry"]["id"]:
                api_control: dict = self.scenario["apiControl"][CallKey.GET_SCHEMA_REGISTRY]
                assert request_kpis.params["api-version"] == ExpectedAPIVersion.SCHEMA_REGISTRY.value
                self.call_map[CallKey.GET_SCHEMA_REGISTRY].append(request_kpis)
                return (
                    api_control.get("code", 200),
                    STANDARD_HEADERS,
                    json.dumps(api_control.get("body", self.scenario["schemaRegistry"])),
                )

            if request_kpis.path_url == self.scenario["adrNamespace"]["id"]:
                api_control: dict = self.scenario["apiControl"][CallKey.GET_ADR_NAMESPACE]
                assert request_kpis.params["api-version"] == ExpectedAPIVersion.ADR_NAMESPACE.value
                self.call_map[CallKey.GET_ADR_NAMESPACE].append(request_kpis)
                return (
                    api_control.get("code", 200),
                    STANDARD_HEADERS,
                    json.dumps(api_control.get("body", self.scenario["adrNamespace"])),
                )

            if request_kpis.path_url == (
                f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{self.scenario['resourceGroup']}"
                f"/providers/microsoft.deviceregistry/schemaRegistries/{self.scenario['schemaRegistry']['name']}"
                f"/providers/Microsoft.Authorization/roleAssignments"
            ):
                ops_ext_identity = self._get_extension_identity()
                assert request_kpis.params["api-version"] == ExpectedAPIVersion.AUTHORIZATION.value
                assert request_kpis.params["$filter"] == f"principalId eq '{ops_ext_identity['principalId']}'"
                self.call_map[CallKey.GET_SCHEMA_REGISTRY_RA].append(request_kpis)
                return (200, STANDARD_HEADERS, json.dumps(self.scenario["schemaRegistry"]["roleAssignments"]))

            if request_kpis.path_url == (
                f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{self.scenario['resourceGroup']}"
                f"/providers/Microsoft.Kubernetes/connectedClusters/{self.scenario['cluster']['name']}"
                f"/providers/Microsoft.KubernetesConfiguration/extensions"
            ):
                assert request_kpis.params["api-version"] == ExpectedAPIVersion.CLUSTER_EXTENSION.value
                self.call_map[CallKey.GET_CLUSTER_EXTENSIONS].append(request_kpis)
                return (200, STANDARD_HEADERS, json.dumps(self.scenario["cluster"]["extensions"]))

        if request_kpis.method == responses.PUT:
            self._assert_correlation_headers(request_kpis)
            url_resources_seg = get_deployment_path_regex("extension")
            if re.match(
                path_pattern_base + url_resources_seg,
                request_kpis.path_url,
            ):
                assert request_kpis.params["api-version"] == ExpectedAPIVersion.RESOURCE.value
                assert f"/resourcegroups/{self.scenario['resourceGroup']}/" in request_kpis.path_url
                assert_instance_deployment_body(
                    body_str=request_kpis.body_str, target_scenario=self.scenario, phase=InstancePhase.EXT
                )
                self.call_map[CallKey.DEPLOY_CREATE_EXT].append(request_kpis)
                return (200, STANDARD_HEADERS, json.dumps({}))

            url_resources_seg = get_deployment_path_regex("instance")
            if re.match(
                path_pattern_base + url_resources_seg,
                request_kpis.path_url,
            ):
                assert request_kpis.params["api-version"] == ExpectedAPIVersion.RESOURCE.value
                assert f"/resourcegroups/{self.scenario['resourceGroup']}/" in request_kpis.path_url
                assert_instance_deployment_body(
                    body_str=request_kpis.body_str, target_scenario=self.scenario, phase=InstancePhase.INSTANCE
                )
                self.call_map[CallKey.DEPLOY_CREATE_INSTANCE].append(request_kpis)
                return (200, STANDARD_HEADERS, json.dumps({}))

            url_resources_seg = get_deployment_path_regex("resources")
            if re.match(
                path_pattern_base + url_resources_seg,
                request_kpis.path_url,
            ):
                assert request_kpis.params["api-version"] == ExpectedAPIVersion.RESOURCE.value
                assert f"/resourcegroups/{self.scenario['resourceGroup']}/" in request_kpis.path_url
                assert_instance_deployment_body(
                    body_str=request_kpis.body_str, target_scenario=self.scenario, phase=InstancePhase.RESOURCES
                )
                self.call_map[CallKey.DEPLOY_CREATE_RESOURCES].append(request_kpis)
                return (200, STANDARD_HEADERS, json.dumps({}))

            if request_kpis.path_url.startswith(
                f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{self.scenario['resourceGroup']}"
                f"/providers/microsoft.deviceregistry/schemaRegistries/{self.scenario['schemaRegistry']['name']}"
                f"/providers/Microsoft.Authorization/roleAssignments/"
            ):
                ops_ext_identity = self._get_extension_identity()
                assert request_kpis.params["api-version"] == ExpectedAPIVersion.AUTHORIZATION.value
                body = json.loads(request_kpis.body_str)
                assert body["properties"]["roleDefinitionId"] == ROLE_DEF_FORMAT_STR.format(
                    subscription_id=ZEROED_SUBSCRIPTION,
                    role_id=CONTRIBUTOR_ROLE_ID,
                )
                assert body["properties"]["principalId"] == ops_ext_identity["principalId"]
                assert body["properties"]["principalType"] == "ServicePrincipal"
                self.call_map[CallKey.PUT_SCHEMA_REGISTRY_RA].append(request_kpis)
                api_control = self.scenario["apiControl"][CallKey.PUT_SCHEMA_REGISTRY_RA]

                return (api_control["code"], STANDARD_HEADERS, json.dumps(api_control["body"]))

        if request_kpis.method == responses.POST:
            if request_kpis.path_url == "/providers/Microsoft.ResourceGraph/resources":
                assert request_kpis.params["api-version"] == ExpectedAPIVersion.GRAPH.value
                self.call_map[CallKey.GET_EXISTING_DEPLOYMENTS].append(request_kpis)
                api_control = self.scenario["apiControl"][CallKey.GET_EXISTING_DEPLOYMENTS]

                return (api_control["code"], STANDARD_HEADERS, json.dumps(api_control["body"]))

    def _get_extension_identity(self, extension_type: str = EXTENSION_TYPE_OPS) -> Optional[dict]:
        for ext in self.scenario["cluster"]["extensions"]["value"]:
            if ext["properties"]["extensionType"] == extension_type:
                return ext.get("identity")

    def _assert_correlation_headers(self, request_kpis: RequestKPIs):
        """
        Assert correlation headers are present on the request.
        """
        assert request_kpis.headers.get("x-ms-correlation-request-id"), "Missing x-ms-correlation-request-id header"
        assert (
            request_kpis.headers.get("CommandName") == f"iot ops {self._action}"
        ), f"Expected CommandName 'iot ops {self._action}', got '{request_kpis.headers.get('CommandName')}'"


def get_deployment_path_regex(kind="instance") -> str:
    return r"/providers/Microsoft\.Resources/deployments/aziotops\." + kind + r"\.[a-zA-Z0-9\.-]+"


def build_target_scenario(
    extension_config_settings: Optional[dict] = None,
    omit_extension_types: Optional[FrozenSet[str]] = None,
    omit_http_methods: Optional[FrozenSet[str]] = None,
    raises: Optional[ExceptionMeta] = None,
    **kwargs,
) -> dict:
    schema_registry_name: str = generate_random_string()
    adr_namespace_name: str = generate_random_string()
    resource_group_name = generate_random_string()

    expected_extension_types: List[str] = list(OPS_EXTENSION_DEPS)
    expected_extension_types.append(EXTENSION_TYPE_OPS)
    if omit_extension_types:
        for ext_type in omit_extension_types:
            expected_extension_types.remove(ext_type)

    default_extensions_config = {
        ext_type: {
            "id": generate_random_string(),
            "properties": {
                "extensionType": ext_type,
                "provisioningState": PROVISIONING_STATE_SUCCESS,
                "configurationSettings": {},
            },
        }
        for ext_type in expected_extension_types
    }
    if EXTENSION_TYPE_OPS in default_extensions_config:
        default_extensions_config[EXTENSION_TYPE_OPS]["identity"] = {"principalId": generate_random_string()}

    if extension_config_settings:
        default_extensions_config.update(extension_config_settings)
    extensions_list = list(default_extensions_config.values())

    payload = {
        "instance": {"name": generate_random_string(), "description": None, "namespace": None, "tags": None},
        "enableRsyncRules": None,
        "location": None,
        "resourceGroup": resource_group_name,
        "cluster": {
            "id": generate_random_string(),
            "name": generate_random_string(),
            "location": generate_random_string(),
            "properties": {
                "provisioningState": PROVISIONING_STATE_SUCCESS,
                "connectivityStatus": ClusterConnectStatus.CONNECTED.value,
                "totalNodeCount": 1,
            },
            "extensions": {"value": extensions_list},
        },
        "customLocation": {"name": None},
        "providerNamespace": {
            "value": [
                {"namespace": namespace, "registrationState": "Registered"}
                for namespace in RP_NAMESPACE_SET.union(RP_NAMESPACE_OPTIONAL_SET)
            ]
        },
        "trust": {"userTrust": None, "settings": None},
        "enableFaultTolerance": None,
        "check_cluster": None,
        "ensure_latest": None,
        "schemaRegistry": {
            "id": generate_resource_id(
                resource_group_name=resource_group_name,
                resource_provider="microsoft.deviceregistry",
                resource_path=f"/schemaRegistries/{schema_registry_name}",
            ),
            "name": schema_registry_name,
            "roleAssignments": {"value": []},
        },
        "adrNamespace": {
            "id": generate_resource_id(
                resource_group_name=resource_group_name,
                resource_provider="microsoft.deviceregistry",
                resource_path=f"/namespaces/{adr_namespace_name}",
            ),
            "name": adr_namespace_name,
        },
        "dataflow": {"profileInstances": None},
        "broker": {},
        "no_progress": True,
        "no_preflight": None,
        "raises": raises,
        "omitHttpMethods": omit_http_methods,
        "apiControl": {
            CallKey.DEPLOY_INIT_WHATIF: {"code": 200, "body": {"status": PROVISIONING_STATE_SUCCESS}},
            CallKey.DEPLOY_CREATE_WHATIF: {"code": 200, "body": {"status": PROVISIONING_STATE_SUCCESS}},
            CallKey.PUT_SCHEMA_REGISTRY_RA: {"code": 200, "body": {}},
            CallKey.GET_EXISTING_DEPLOYMENTS: {"code": 200, "body": {"data": []}},
            CallKey.GET_SCHEMA_REGISTRY: {"code": 200, "body": {}},
            CallKey.GET_ADR_NAMESPACE: {"code": 200, "body": {}},
            CallKey.GET_RESOURCE_HEALTH: {"code": 200, "body": {"properties": {"availabilityState": "Available"}}},
            CallKey.CREATE_CUSTOM_LOCATION: {"code": 200, "body": {}},
        },
    }
    if "cluster_properties" in kwargs:
        payload["cluster"]["properties"].update(kwargs["cluster_properties"])
        kwargs.pop("cluster_properties")
    if "broker" in kwargs:
        payload["broker"].update(kwargs["broker"])
        kwargs.pop("broker")
    if "apiControl" in kwargs:
        for k in kwargs["apiControl"]:
            payload["apiControl"][k] = kwargs["apiControl"][k]
        kwargs.pop("apiControl")

    payload.update(**kwargs)
    return payload


def assert_call_map(expected_call_count_map: dict, call_map: dict):
    for key in call_map:
        expected_count = 0
        if key in expected_call_count_map:
            expected_count = expected_call_count_map[key]
        assert len(call_map[key]) == expected_count, f"{key} has unexpected call(s)."


def assert_exception(
    expected_exc_meta: ExceptionMeta,
    call_func: Callable,
    call_kwargs: dict,
    exclude_from_exc_msg: Optional[List[str]] = None,
):
    with pytest.raises(expected_exc_meta.exc_type) as e:
        call_func(**call_kwargs)
    exc_msg = str(e.value)
    if expected_exc_meta.exc_msg:
        if isinstance(expected_exc_meta.exc_msg, list):
            for msg_seg in expected_exc_meta.exc_msg:
                assert msg_seg in exc_msg, f"Expected '{msg_seg}' in error message: {exc_msg}"
        elif isinstance(expected_exc_meta.exc_msg, re.Pattern):
            assert expected_exc_meta.exc_msg.match(exc_msg)
        else:
            assert expected_exc_meta.exc_msg in exc_msg

    if exclude_from_exc_msg:
        for excluded_msg in exclude_from_exc_msg:
            assert excluded_msg not in exc_msg, f"'{excluded_msg}' should NOT be in error message: {exc_msg}"


@pytest.mark.parametrize(
    "target_scenario",
    [
        build_target_scenario(),
        build_target_scenario(
            trust={"userTrust": True},
        ),
        build_target_scenario(
            cluster_properties={"connectivityStatus": "Disconnected"},
            raises=ExceptionMeta(
                exc_type=ValidationError,
                exc_msg="connectivityStatus is not Connected.",
            ),
            omit_http_methods=OMIT_WRITE_METHODS,
        ),
        build_target_scenario(
            apiControl={CallKey.DEPLOY_INIT_WHATIF: {"code": 200, "body": {"status": "Failed"}}},
            raises=ExceptionMeta(
                exc_type=AzureResponseError,
                exc_msg=json.dumps({"status": "Failed"}, indent=2),
            ),
            omit_http_methods=frozenset([responses.PUT]),
        ),
        build_target_scenario(
            check_cluster=True,
        ),
        # Basic unavailable scenario
        build_target_scenario(
            apiControl={CallKey.GET_RESOURCE_HEALTH: HEALTH_UNAVAILABLE_BASIC},
            raises=ExceptionMeta(
                exc_type=ValidationError,
                exc_msg=[
                    "is currently unavailable",
                    "The cluster is experiencing issues.",
                    "PlatformInitiated",
                ],
            ),
            omit_http_methods=OMIT_WRITE_METHODS,
        ),
        # Unavailable with full details: title, resolutionETA (platform context), and recommendedActions
        build_target_scenario(
            apiControl={
                CallKey.GET_RESOURCE_HEALTH: {
                    "code": 200,
                    "body": {
                        "properties": {
                            "availabilityState": "Unavailable",
                            "title": "Degraded",
                            "summary": "The cluster is experiencing critical issues.",
                            "reasonType": "PlatformInitiated",
                            "context": "Platform",
                            "resolutionETA": "2026-01-14T00:57:02Z",
                            "recommendedActions": [
                                {
                                    "action": "Check the <action>cluster connectivity</action> status.",
                                    "actionUrl": "https://docs.microsoft.com/connectivity",
                                },
                                {
                                    "action": "Review <action>node health</action> in the portal.",
                                    "actionUrl": "https://docs.microsoft.com/node-health",
                                },
                            ],
                        }
                    },
                }
            },
            raises=ExceptionMeta(
                exc_type=ValidationError,
                exc_msg=[
                    "is currently unavailable",
                    "Status: Degraded",
                    "Summary: The cluster is experiencing critical issues.",
                    "Reason: PlatformInitiated",
                    "Expected Resolution: 2026-01-14T00:57:02Z",
                    "Recommended Actions:",
                    # XML tags should be stripped
                    "Check the cluster connectivity status.",
                    "https://docs.microsoft.com/connectivity",
                    "Review node health in the portal.",
                    "https://docs.microsoft.com/node-health",
                ],
            ),
            omit_http_methods=OMIT_WRITE_METHODS,
        ),
        # Unavailable with non-platform context - resolutionETA should NOT appear in error
        build_target_scenario(
            apiControl={
                CallKey.GET_RESOURCE_HEALTH: {
                    "code": 200,
                    "body": {
                        "properties": {
                            "availabilityState": "Unavailable",
                            "title": "User Action Required",
                            "summary": "User-initiated maintenance in progress.",
                            "reasonType": "UserInitiated",
                            "context": "Not Applicable",
                            "resolutionETA": "2026-01-14T00:57:02Z",
                        }
                    },
                }
            },
            raises=ExceptionMeta(
                exc_type=ValidationError,
                exc_msg=[
                    "is currently unavailable",
                    "Status: User Action Required",
                    "Summary: User-initiated maintenance in progress.",
                    "Reason: UserInitiated",
                ],
            ),
            exclude_from_exc_msg=["Expected Resolution:"],
            omit_http_methods=OMIT_WRITE_METHODS,
        ),
        # Cluster health unknown - should pass through
        build_target_scenario(
            apiControl={
                CallKey.GET_RESOURCE_HEALTH: {
                    "code": 200,
                    "body": {"properties": {"availabilityState": "Unknown"}},
                }
            },
        ),
        # Cluster health Available - should pass through
        build_target_scenario(
            apiControl={
                CallKey.GET_RESOURCE_HEALTH: {
                    "code": 200,
                    "body": {"properties": {"availabilityState": "Available"}},
                }
            },
        ),
        # Resource Health API failure (403) - should pass through gracefully
        build_target_scenario(
            apiControl={CallKey.GET_RESOURCE_HEALTH: AUTHZ_FAILURE},
        ),
        build_target_scenario(
            no_preflight=True,
        ),
        # Unavailable with minimal info - only summary
        build_target_scenario(
            apiControl={
                CallKey.GET_RESOURCE_HEALTH: {
                    "code": 200,
                    "body": {
                        "properties": {
                            "availabilityState": "Unavailable",
                            "summary": "Cluster unavailable.",
                        }
                    },
                }
            },
            raises=ExceptionMeta(
                exc_type=ValidationError,
                exc_msg=[
                    "is currently unavailable",
                    "Cluster unavailable.",
                ],
            ),
            omit_http_methods=OMIT_WRITE_METHODS,
        ),
        # Cluster provisioningState is not Succeeded
        build_target_scenario(
            cluster_properties={"provisioningState": "Failed"},
            raises=ExceptionMeta(
                exc_type=ValidationError,
                exc_msg="provisioningState is not Succeeded.",
            ),
            omit_http_methods=OMIT_WRITE_METHODS,
        ),
    ],
)
def test_iot_ops_init(
    mocked_cmd: Mock,
    mocked_responses: responses,
    mocked_sleep: Mock,
    spy_work_displays: Dict[str, Mock],
    mock_prechecks: Dict[str, Mock],
    mocked_config: Mock,
    mocked_verify_arc_cluster_config: Mock,
    target_scenario: dict,
):
    servgen = ServiceGenerator(scenario=target_scenario, mocked_responses=mocked_responses, action="init")
    from azext_edge.edge.commands_edge import init

    init_call_kwargs = {
        "cmd": mocked_cmd,
        "cluster_name": target_scenario["cluster"]["name"],
        "resource_group_name": target_scenario["resourceGroup"],
    }
    if target_scenario["trust"]["userTrust"]:
        init_call_kwargs["user_trust"] = target_scenario["trust"]["userTrust"]

    optional_flags = ["no_progress", "ensure_latest", "check_cluster", "no_preflight"]
    for key in optional_flags:
        if target_scenario.get(key):
            init_call_kwargs[key] = target_scenario[key]

    preflight_calls = int(not bool(target_scenario.get("no_preflight")))

    exc_meta: Optional[ExceptionMeta] = target_scenario.get("raises")
    if exc_meta:
        exc_meta: ExceptionMeta
        exclude_from_exc_msg = target_scenario.get("exclude_from_exc_msg")
        assert_exception(
            expected_exc_meta=exc_meta,
            call_func=init,
            call_kwargs=init_call_kwargs,
            exclude_from_exc_msg=exclude_from_exc_msg,
        )
        return

    init_result = init(**init_call_kwargs)  # pylint: disable=assignment-from-no-return
    expected_call_count_map = {
        CallKey.CONNECT_RESOURCE_MANAGER: 1,
        CallKey.GET_RESOURCE_PROVIDERS: preflight_calls,
        CallKey.GET_CLUSTER: 1,
        CallKey.GET_RESOURCE_HEALTH: preflight_calls,
        CallKey.DEPLOY_INIT_WHATIF: 1,
        CallKey.DEPLOY_INIT: 1,
    }
    assert_call_map(expected_call_count_map, servgen.call_map)
    assert_init_displays(spy_work_displays, target_scenario)
    assert_cluster_prechecks(mock_prechecks, target_scenario)

    # TODO - @digimaun
    if target_scenario["no_progress"]:
        assert init_result is None


def assert_init_displays(spy_work_displays: Dict[str, Mock], target_scenario: dict):
    # TODO
    pass


def assert_init_deployment_body(body_str: str, target_scenario: dict):
    assert body_str
    body = json.loads(body_str)

    mode = body["properties"]["mode"]
    assert mode == "Incremental"

    template = body["properties"]["template"]
    for key in EXPECTED_EXTENSION_RESOURCE_KEYS:
        assert template["resources"][key]
    assert len(template["resources"]) == len(EXPECTED_EXTENSION_RESOURCE_KEYS)

    parameters = body["properties"]["parameters"]
    assert parameters["clusterName"]["value"] == target_scenario["cluster"]["name"]

    expected_trust_config = {"source": "SelfSigned"}
    if target_scenario["trust"]["userTrust"]:
        expected_trust_config = {"source": "CustomerManaged"}
    assert parameters["trustConfig"]["value"] == expected_trust_config


def assert_cluster_prechecks(mock_prechecks: Dict[str, Mock], target_scenario: dict):
    check_cluster = target_scenario.get("check_cluster")

    mock_validate_prechecks = mock_prechecks["validate_cluster_prechecks"]
    mock_check_k8s_version = mock_prechecks["check_k8s_version"]
    mock_check_nodes = mock_prechecks["check_nodes"]
    mock_check_storage_classes = mock_prechecks["check_storage_classes"]

    assert mock_validate_prechecks.call_count == (1 if check_cluster else 0)
    assert mock_check_k8s_version.call_count == (1 if check_cluster else 0)
    assert mock_check_nodes.call_count == (1 if check_cluster else 0)
    assert mock_check_storage_classes.call_count == 0


@pytest.mark.parametrize(
    "target_scenario",
    [
        build_target_scenario(),
        build_target_scenario(persist_max_size="10Gi"),
        build_target_scenario(persist_max_size="10Gi", persist_pvc_sc="default"),
        build_target_scenario(
            persist_pvc_sc="default",
            raises=ExceptionMeta(
                exc_type=InvalidArgumentValueError,
                exc_msg="Provide a persist max size value to enable and customize broker disk persistence.",
            ),
            omit_http_methods=OMIT_ALL_METHODS,
        ),
        build_target_scenario(
            persist_max_size="10Gi",
            persist_mode=["retain=All", "stateStore=None"],
        ),
        build_target_scenario(instance_features=["connectors.settings.preview=Enabled"]),
        build_target_scenario(
            instance={
                "name": generate_random_string(),
                "description": generate_random_string(),
                "namespace": generate_random_string(),
                "tags": {generate_random_string(): generate_random_string()},
            },
            dataflow={"profileInstances": randint(1, 10)},
        ),
        build_target_scenario(
            cluster_properties={"connectivityStatus": "Disconnected"},
            raises=ExceptionMeta(
                exc_type=ValidationError,
                exc_msg="connectivityStatus is not Connected.",
            ),
            omit_http_methods=OMIT_WRITE_METHODS,
        ),
        build_target_scenario(
            extension_config_settings={
                EXTENSION_TYPE_CM: {
                    "properties": {
                        "extensionType": EXTENSION_TYPE_CM,
                        "provisioningState": "Failed",
                    }
                },
                EXTENSION_TYPE_SSC: {
                    "properties": {
                        "extensionType": EXTENSION_TYPE_SSC,
                        "provisioningState": "Failed",
                    }
                },
            },
            raises=ExceptionMeta(
                exc_type=ValidationError,
                exc_msg=[
                    "Foundational service(s) with non-successful provisioning state detected on the cluster:\n\n",
                    EXTENSION_TYPE_SSC,
                    EXTENSION_TYPE_CM,
                    "\n\nInstance deployment will not continue. Please run 'az iot ops init'.",
                ],
            ),
            omit_http_methods=OMIT_WRITE_METHODS,
        ),
        build_target_scenario(
            omit_extension_types=frozenset([EXTENSION_TYPE_SSC]),
            raises=ExceptionMeta(
                exc_type=ValidationError,
                exc_msg=(
                    "Foundational service(s) not detected on the cluster:\n\n"
                    f"{EXTENSION_TYPE_SSC}"
                    "\n\nInstance deployment will not continue. Please run 'az iot ops init'."
                ),
            ),
            omit_http_methods=OMIT_WRITE_METHODS,
        ),
        build_target_scenario(
            omit_extension_types=frozenset([EXTENSION_TYPE_CM]),
            raises=ExceptionMeta(
                exc_type=ValidationError,
                exc_msg=(
                    "Cluster was enabled with user-managed trust configuration, --trust-settings "
                    "arguments are required to create an instance on this cluster."
                ),
            ),
            omit_http_methods=OMIT_WRITE_METHODS,
        ),
        build_target_scenario(
            omit_extension_types=frozenset([EXTENSION_TYPE_CM]),
            trust={
                "settings": [
                    "configMapName=example-bundle",
                    "configMapKey=trust-bundle.pem",
                    "issuerKind=Issuer",
                    "issuerName=selfsigned-issuer",
                ]
            },
        ),
        build_target_scenario(
            trust={
                "settings": [
                    "configMapName=example-bundle",
                    "configMapKey=trust-bundle.pem",
                    "issuerKind=Issuer",
                    "issuerName=selfsigned-issuer",
                ]
            },
            raises=ExceptionMeta(
                exc_type=ValidationError,
                exc_msg="Cluster was enabled with system cert-manager, "
                "trust settings (--trust-settings) are not applicable to this cluster.",
            ),
            omit_http_methods=OMIT_WRITE_METHODS,
        ),
        build_target_scenario(
            omit_extension_types=frozenset([EXTENSION_TYPE_CM]),
            trust={
                "settings": [
                    "configMapName=example-bundle",
                    "configMapKey=trust-bundle.pem",
                    "issuerKind=Issuer",
                ]
            },
            raises=ExceptionMeta(
                exc_type=InvalidArgumentValueError,
                exc_msg="issuerName is a required trust setting/key.",
            ),
            omit_http_methods=OMIT_ALL_METHODS,
        ),
        build_target_scenario(
            apiControl={CallKey.PUT_SCHEMA_REGISTRY_RA: {"code": 400, "body": {"status": "Failed"}}},
            warnings=[(0, "Role assignment failed with:\nOperation returned an invalid status 'Bad Request'")],
        ),
        build_target_scenario(
            apiControl={
                CallKey.GET_EXISTING_DEPLOYMENTS: {"code": 200, "body": {"data": [{"name": "location-12345"}]}}
            },
            raises=ExceptionMeta(
                exc_type=ValidationError,
                exc_msg="IoT Operations is detected on the cluster.",
            ),
            omit_http_methods=frozenset([responses.PUT]),
        ),
        build_target_scenario(
            adrNamespace={
                "id": generate_resource_id(
                    resource_group_name=generate_random_string(),
                    resource_provider="microsoft.deviceregistry",
                    resource_path="/namespaces/mynamespace",
                ),
            },
        ),
        build_target_scenario(
            apiControl={CallKey.GET_ADR_NAMESPACE: RESOURCE_NOT_FOUND_ERROR},
            raises=ExceptionMeta(
                exc_type=AzureResponseError,
                exc_msg="The Resource was not found.",
            ),
            omit_http_methods=OMIT_WRITE_METHODS,
        ),
        build_target_scenario(
            apiControl={CallKey.GET_SCHEMA_REGISTRY: RESOURCE_NOT_FOUND_ERROR},
            raises=ExceptionMeta(
                exc_type=AzureResponseError,
                exc_msg="The Resource was not found.",
            ),
            omit_http_methods=OMIT_WRITE_METHODS,
        ),
        build_target_scenario(
            skip_sr_ra=True,
        ),
        # Basic unavailable scenario for create flow
        build_target_scenario(
            apiControl={
                CallKey.GET_RESOURCE_HEALTH: {
                    "code": 200,
                    "body": {
                        "properties": {
                            "availabilityState": "Unavailable",
                            "summary": "The cluster is experiencing issues.",
                            "reasonType": "PlatformInitiated",
                        }
                    },
                }
            },
            raises=ExceptionMeta(
                exc_type=ValidationError,
                exc_msg="is currently unavailable",
            ),
            omit_http_methods=OMIT_WRITE_METHODS,
        ),
        # Unavailable with full details in create flow
        build_target_scenario(
            apiControl={
                CallKey.GET_RESOURCE_HEALTH: {
                    "code": 200,
                    "body": {
                        "properties": {
                            "availabilityState": "Unavailable",
                            "title": "Service Degradation",
                            "summary": "Backend services are impacted.",
                            "reasonType": "PlatformInitiated",
                            "context": "Platform",
                            "resolutionETA": "2026-01-15T12:00:00Z",
                            "recommendedActions": [
                                {
                                    "action": "Wait for <action>automatic recovery</action>.",
                                    "actionUrl": "https://status.azure.com",
                                },
                            ],
                        }
                    },
                }
            },
            raises=ExceptionMeta(
                exc_type=ValidationError,
                exc_msg=[
                    "is currently unavailable",
                    "Status: Service Degradation",
                    "Expected Resolution: 2026-01-15T12:00:00Z",
                    "Wait for automatic recovery.",
                    "https://status.azure.com",
                ],
            ),
            omit_http_methods=OMIT_WRITE_METHODS,
        ),
        # Unavailable with non-platform context in create flow - no resolutionETA
        build_target_scenario(
            apiControl={
                CallKey.GET_RESOURCE_HEALTH: {
                    "code": 200,
                    "body": {
                        "properties": {
                            "availabilityState": "Unavailable",
                            "summary": "Customer-initiated action required.",
                            "reasonType": "CustomerInitiated",
                            "context": "Customer",
                            "resolutionETA": "2026-01-15T12:00:00Z",
                        }
                    },
                }
            },
            raises=ExceptionMeta(
                exc_type=ValidationError,
                exc_msg=[
                    "is currently unavailable",
                    "Customer-initiated action required.",
                ],
            ),
            exclude_from_exc_msg=["Expected Resolution:"],
            omit_http_methods=OMIT_WRITE_METHODS,
        ),
        build_target_scenario(
            no_preflight=True,
        ),
        # Unavailable with minimal info - only summary
        build_target_scenario(
            apiControl={
                CallKey.GET_RESOURCE_HEALTH: {
                    "code": 200,
                    "body": {
                        "properties": {
                            "availabilityState": "Unavailable",
                            "summary": "Cluster unavailable.",
                        }
                    },
                }
            },
            raises=ExceptionMeta(
                exc_type=ValidationError,
                exc_msg=[
                    "is currently unavailable",
                    "Cluster unavailable.",
                ],
            ),
            omit_http_methods=OMIT_WRITE_METHODS,
        ),
        # Unavailable with empty recommendedActions array - should not show "Recommended Actions:" section
        build_target_scenario(
            apiControl={
                CallKey.GET_RESOURCE_HEALTH: {
                    "code": 200,
                    "body": {
                        "properties": {
                            "availabilityState": "Unavailable",
                            "summary": "Cluster is down.",
                            "recommendedActions": [],
                        }
                    },
                }
            },
            raises=ExceptionMeta(
                exc_type=ValidationError,
                exc_msg=[
                    "is currently unavailable",
                    "Cluster is down.",
                ],
            ),
            exclude_from_exc_msg=["Recommended Actions:"],
            omit_http_methods=OMIT_WRITE_METHODS,
        ),
        build_target_scenario(
            cluster_properties={"provisioningState": "Failed"},
            raises=ExceptionMeta(
                exc_type=ValidationError,
                exc_msg="provisioningState is not Succeeded.",
            ),
            omit_http_methods=OMIT_WRITE_METHODS,
        ),
        build_target_scenario(
            extension_config_settings={
                EXTENSION_TYPE_OPS: {
                    "id": generate_random_string(),
                    "properties": {
                        "extensionType": EXTENSION_TYPE_OPS,
                        "provisioningState": PROVISIONING_STATE_SUCCESS,
                        "configurationSettings": {},
                    },
                    "identity": {},
                },
            },
            raises=ExceptionMeta(
                exc_type=ValidationError,
                exc_msg="Unable to determine the IoT Operations system-managed identity principal Id.",
            ),
        ),
        build_target_scenario(
            apiControl={CallKey.CREATE_CUSTOM_LOCATION: UNAUTHORIZED_NAMESPACE_ERROR},
            raises=ExceptionMeta(
                exc_type=ValidationError,
                exc_msg=[
                    "Custom Locations Error:",
                    "The namespace is not authorized for custom locations.",
                    "[IoT Ops explanation]",
                    "The arc custom locations feature was not enabled",
                    "The arc custom locations feature was not enabled with the correct OID",
                ],
            ),
        ),
    ],
)
def test_iot_ops_create(
    mocked_cmd: Mock,
    mocked_responses: responses,
    mocked_sleep: Mock,
    mocked_confirm: Mock,
    mocked_logger: Mock,
    mocked_feature_keys: Mock,
    spy_work_displays: Dict[str, Mock],
    target_scenario: Dict[str, Union[bool, dict]],
):
    servgen = ServiceGenerator(scenario=target_scenario, mocked_responses=mocked_responses, action="create")
    from azext_edge.edge.commands_edge import create_instance

    create_call_kwargs = {
        "cmd": mocked_cmd,
        "cluster_name": target_scenario["cluster"]["name"],
        "resource_group_name": target_scenario["resourceGroup"],
        "instance_name": target_scenario["instance"]["name"],
        "schema_registry_resource_id": target_scenario["schemaRegistry"]["id"],
        "adr_namespace_resource_id": target_scenario["adrNamespace"]["id"],
    }
    if target_scenario["instance"]["namespace"]:
        create_call_kwargs["cluster_namespace"] = target_scenario["instance"]["namespace"]
    if target_scenario["instance"]["description"]:
        create_call_kwargs["instance_description"] = target_scenario["instance"]["description"]
    if target_scenario["instance"]["tags"]:
        create_call_kwargs["tags"] = target_scenario["instance"]["tags"]
    if target_scenario["cluster"]["location"]:
        create_call_kwargs["location"] = target_scenario["cluster"]["location"]
    if target_scenario["customLocation"]["name"]:
        create_call_kwargs["custom_location_name"] = target_scenario["customLocation"]["name"]
    if target_scenario["dataflow"]["profileInstances"]:
        create_call_kwargs["dataflow_profile_instances"] = target_scenario["dataflow"]["profileInstances"]
    if target_scenario["trust"]["settings"]:
        create_call_kwargs["trust_settings"] = target_scenario["trust"]["settings"]

    instance_features = target_scenario.get("instance_features")
    if instance_features:
        create_call_kwargs["instance_features"] = instance_features

    for key in ["no_progress", "no_preflight"]:
        if target_scenario.get(key):
            create_call_kwargs[key] = target_scenario[key]

    preflight_calls = int(not bool(target_scenario.get("no_preflight")))

    # TODO: Simplify existing arg plumbing to this style for simplification
    for key in ["persist_max_size", "persist_pvc_sc", "persist_mode"]:
        if key in target_scenario:
            create_call_kwargs[key] = target_scenario[key]

    skip_sr_ra = target_scenario.get("skip_sr_ra")
    sr_ra_calls = int(not bool(skip_sr_ra))
    create_call_kwargs["skip_sr_ra"] = skip_sr_ra

    exc_meta: Optional[ExceptionMeta] = target_scenario.get("raises")
    if exc_meta:
        exc_meta: ExceptionMeta
        exclude_from_exc_msg = target_scenario.get("exclude_from_exc_msg")
        assert_exception(
            expected_exc_meta=exc_meta,
            call_func=create_instance,
            call_kwargs=create_call_kwargs,
            exclude_from_exc_msg=exclude_from_exc_msg,
        )
        return

    create_result = create_instance(**create_call_kwargs)  # pylint: disable=assignment-from-no-return

    expected_call_count_map = {
        CallKey.CONNECT_RESOURCE_MANAGER: 1,
        CallKey.GET_RESOURCE_PROVIDERS: preflight_calls,
        CallKey.GET_CLUSTER: 1,
        CallKey.GET_RESOURCE_HEALTH: preflight_calls,
        CallKey.GET_SCHEMA_REGISTRY: 1,
        CallKey.GET_ADR_NAMESPACE: 1,
        CallKey.GET_CLUSTER_EXTENSIONS: 2,
        CallKey.GET_EXISTING_DEPLOYMENTS: 1,
        CallKey.GET_SCHEMA_REGISTRY_RA: sr_ra_calls,
        CallKey.PUT_SCHEMA_REGISTRY_RA: sr_ra_calls,
        CallKey.CREATE_CUSTOM_LOCATION: 2,
        CallKey.DEPLOY_CREATE_EXT: 1,
        CallKey.DEPLOY_CREATE_INSTANCE: 1,
        CallKey.DEPLOY_CREATE_RESOURCES: 1,
    }
    assert_call_map(expected_call_count_map, servgen.call_map)
    assert_create_displays(spy_work_displays, target_scenario)
    assert_logger(mocked_logger, target_scenario)

    # TODO - @digimaun
    if target_scenario["no_progress"]:
        assert create_result is None


@pytest.mark.parametrize(
    "target_scenario",
    [
        build_target_scenario(instance_features=["connectors.settings.preview=Enabled"]),
    ],
)
def test_iot_ops_create_block_feature_config(
    mocked_cmd: Mock,
    mocker,
    mocked_responses: responses,
    mocked_sleep: Mock,
    mocked_confirm: Mock,
    spy_work_displays: Dict[str, Mock],
    target_scenario: Dict[str, Union[bool, dict]],
):
    from azext_edge.edge.commands_edge import create_instance

    create_call_kwargs = {
        "cmd": mocked_cmd,
        "cluster_name": target_scenario["cluster"]["name"],
        "resource_group_name": target_scenario["resourceGroup"],
        "instance_name": target_scenario["instance"]["name"],
        "schema_registry_resource_id": target_scenario["schemaRegistry"]["id"],
        "adr_namespace_resource_id": target_scenario["adrNamespace"]["id"],
        "instance_features": target_scenario["instance_features"],
    }

    with pytest.raises(ValidationError) as exc:
        create_instance(**create_call_kwargs)
    exc_msg = str(exc.value)
    assert "No feature keys are supported in this version of IoT Operations." == exc_msg


def assert_logger(mocked_logger: Mock, target_scenario: dict):
    expected_warnings: List[Tuple[int, str]] = target_scenario.get("warnings", [])
    warning_calls: List[Mock] = mocked_logger.warning.mock_calls
    for w in expected_warnings:
        assert w[1] in warning_calls[w[0]].args[0]


def assert_create_displays(spy_work_displays: Dict[str, Mock], target_scenario: dict):
    # TODO
    pass


def get_expected_keys_for(phase: InstancePhase) -> Tuple[set[str], set[str]]:
    ext_keys = {"cluster", "aioExtension"}
    instance_keys = ext_keys.union({"customLocation", "aioInstance"})
    resource_keys = instance_keys.union(
        {"broker", "brokerAuthn", "brokerListener", "dataflowProfile", "dataflowEndpoint", "artifactRegistryEndpoint"}
    )
    if phase == InstancePhase.EXT:
        return ext_keys, {}
    if phase == InstancePhase.INSTANCE:
        return instance_keys, ext_keys.union({"customLocation"})
    if phase == InstancePhase.RESOURCES:
        return resource_keys, ext_keys.union(instance_keys)


def assert_instance_deployment_body(body_str: str, target_scenario: dict, phase: InstancePhase):
    assert body_str
    body = json.loads(body_str)

    mode = body["properties"]["mode"]
    assert mode == "Incremental"

    template = body["properties"]["template"]

    expected_keys, readonly_keys = get_expected_keys_for(phase=phase)
    for key in expected_keys:
        assert template["resources"][key]
    assert len(template["resources"]) == len(expected_keys)

    if readonly_keys:
        for key in readonly_keys:
            assert template["resources"][key]["existing"]
            for rkey in template["resources"][key]:
                assert rkey in {"type", "apiVersion", "name", "scope", "condition", "existing"}

    parameters = body["properties"]["parameters"]
    assert parameters["clusterName"]["value"] == target_scenario["cluster"]["name"]
    assert parameters["clusterNamespace"]["value"] == target_scenario["instance"]["namespace"] or DEFAULT_NAMESPACE
    assert (
        parameters["clusterLocation"]["value"] == target_scenario["location"] or target_scenario["cluster"]["location"]
    )

    cl_extension_ids = set(
        [
            ext["id"]
            for ext in target_scenario["cluster"]["extensions"]["value"]
            if ext["properties"]["extensionType"] in [EXTENSION_TYPE_SSC]
        ]
    )
    assert set(parameters["clExtensionIds"]["value"]) == cl_extension_ids
    assert parameters["schemaRegistryId"]["value"] == target_scenario["schemaRegistry"]["id"]
    assert parameters["adrNamespaceId"]["value"] == target_scenario["adrNamespace"]["id"]

    # TODO - eventually delete.
    assert "deployResourceSyncRules" not in parameters
    assert "kubernetesDistro" not in parameters
    assert "containerRuntimeSocket" not in parameters

    expected_profile_instances = target_scenario.get("dataflow", {}).get("profileInstances") or 1
    assert parameters["defaultDataflowInstanceCount"]["value"] == expected_profile_instances

    broker_config = {
        "frontendReplicas": 2,
        "frontendWorkers": 2,
        "backendRedundancyFactor": 2,
        "backendWorkers": 2,
        "backendPartitions": 2,
        "memoryProfile": "Medium",
    }
    persistence = {}
    if "persist_max_size" in target_scenario:
        persistence = {
            "maxSize": target_scenario["persist_max_size"],
            "retain": {
                "mode": "Custom",
                "retainSettings": {
                    "dynamic": {"mode": "Enabled"},
                },
            },
            "stateStore": {"mode": "Custom", "stateStoreSettings": {"dynamic": {"mode": "Enabled"}}},
            "subscriberQueue": {"mode": "Custom", "subscriberQueueSettings": {"dynamic": {"mode": "Enabled"}}},
        }
    if "persist_pvc_sc" in target_scenario:
        persistence["persistentVolumeClaimSpec"] = {
            "storageClassName": target_scenario["persist_pvc_sc"],
            "accessModes": ["ReadWriteOncePod"],
        }
    if "persist_mode" in target_scenario:
        for kvp in target_scenario["persist_mode"]:
            key, value = kvp.split("=")
            persistence[key] = {"mode": value}

    if persistence:
        broker_config["persistence"] = persistence

    # @digimaun - this asserts defaults. brokerConfig should be primarily tested in targets unit tests.
    assert parameters["brokerConfig"] == {"value": broker_config}
    expected_trust_config = {"source": "SelfSigned"}
    if target_scenario["trust"]["settings"]:
        assembled_settings = assemble_nargs_to_dict(target_scenario["trust"]["settings"])
        expected_trust_config = {"source": "CustomerManaged", "settings": assembled_settings}
    assert parameters["trustConfig"]["value"] == expected_trust_config

    instance_name: str = target_scenario["instance"]["name"]
    instance_name_lowered = instance_name.lower()
    resources = template["resources"]

    if phase in [InstancePhase.INSTANCE]:
        assert resources["aioInstance"]["name"] == instance_name_lowered
        if target_scenario["instance"]["description"]:
            assert resources["aioInstance"]["properties"]["description"] == target_scenario["instance"]["description"]
        if target_scenario["instance"]["tags"]:
            assert resources["aioInstance"]["tags"] == target_scenario["instance"]["tags"]
        instance_features = target_scenario.get("instance_features")
        if instance_features:
            assert resources["aioInstance"]["properties"]["features"]
        else:
            # TODO: think about general 'not in' or 'not' pattern
            assert not resources["aioInstance"]["properties"]["features"]

    if phase in [InstancePhase.RESOURCES]:
        assert resources["broker"]["name"] == f"{instance_name_lowered}/{DEFAULT_BROKER}"
        assert resources["brokerAuthn"]["name"] == f"{instance_name_lowered}/{DEFAULT_BROKER}/{DEFAULT_BROKER_AUTHN}"
        assert (
            resources["brokerListener"]["name"] == f"{instance_name_lowered}/{DEFAULT_BROKER}/{DEFAULT_BROKER_LISTENER}"
        )
        assert resources["dataflowProfile"]["name"] == f"{instance_name_lowered}/{DEFAULT_DATAFLOW_PROFILE}"
        assert resources["dataflowEndpoint"]["name"] == f"{instance_name_lowered}/{DEFAULT_DATAFLOW_ENDPOINT}"
        assert resources["artifactRegistryEndpoint"]["name"] == f"{instance_name_lowered}/{DEFAULT_ARTIFACT_REGISTRY}"
