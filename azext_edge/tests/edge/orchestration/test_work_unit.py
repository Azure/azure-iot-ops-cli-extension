# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


import json
import re
from enum import Enum
from random import randint
from typing import Callable, Dict, FrozenSet, List, NamedTuple, Optional, Tuple, Type, Union
from unittest.mock import Mock

import pytest
import requests
import responses
from azure.cli.core.azclierror import InvalidArgumentValueError, ValidationError, AzureResponseError

from azext_edge.edge.common import (
    DEFAULT_BROKER,
    DEFAULT_BROKER_AUTHN,
    DEFAULT_BROKER_LISTENER,
    DEFAULT_DATAFLOW_ENDPOINT,
    DEFAULT_DATAFLOW_PROFILE,
)
from azext_edge.edge.providers.base import DEFAULT_NAMESPACE
from azext_edge.edge.providers.orchestration.common import (
    ARM_ENDPOINT,
    EXTENSION_TYPE_OPS,
    EXTENSION_TYPE_PLATFORM,
    EXTENSION_TYPE_SSC,
    OPS_EXTENSION_DEPS,
    KubernetesDistroType,
)
from azext_edge.edge.providers.orchestration.rp_namespace import RP_NAMESPACE_SET
from azext_edge.edge.providers.orchestration.work import (
    CONNECTIVITY_STATUS_CONNECTED,
    PROVISIONING_STATE_SUCCESS,
)
from azext_edge.edge.util import assemble_nargs_to_dict

from ...generators import generate_random_string, get_zeroed_subscription
from .test_template_unit import (
    EXPECTED_EXTENSION_RESOURCE_KEYS,
    EXPECTED_INSTANCE_RESOURCE_KEYS,
)

ZEROED_SUBSCRIPTION = get_zeroed_subscription()


path_pattern_base = r"^/subscriptions/[0-9a-fA-F-]+/resourcegroups/[a-zA-Z0-9]+"
STANDARD_HEADERS = {"content-type": "application/json"}


class ExpectedAPIVersion(Enum):
    CONNECTED_CLUSTER = "2024-07-15-preview"
    CLUSTER_EXTENSION = "2023-05-01"
    RESOURCE = "2024-03-01"
    SCHEMA_REGISTRY = "2024-09-01-preview"
    AUTHORIZATION = "2022-04-01"


class CallKey(Enum):
    CONNECT_RESOURCE_MANAGER = "connectResourceManager"
    GET_CLUSTER = "getCluster"
    GET_RESOURCE_PROVIDERS = "getResourceProviders"
    DEPLOY_INIT_WHATIF = "deployInitWhatIf"
    DEPLOY_INIT = "deployInit"
    GET_SCHEMA_REGISTRY = "getSchemaRegistry"
    GET_CLUSTER_EXTENSIONS = "getClusterExtensions"
    GET_SCHEMA_REGISTRY_RA = "getSchemaRegistryRoleAssignments"
    PUT_SCHEMA_REGISTRY_RA = "putSchemaRegistryRoleAssignment"
    DEPLOY_CREATE_WHATIF = "deployCreateWhatIf"
    DEPLOY_CREATE = "deployCreate"


class RequestKPIs(NamedTuple):
    method: str
    url: str
    params: dict
    path_url: str
    body_str: str


class ExceptionMeta(NamedTuple):
    exc_type: Type[Exception]
    exc_msg: Union[str, List[str]] = ""


class ServiceGenerator:
    def __init__(
        self,
        scenario: dict,
        mocked_responses: responses,
    ):
        self.scenario = scenario
        self.mocked_responses = mocked_responses
        self.call_map: Dict[CallKey, List[RequestKPIs]] = {}
        self._bootstrap()

    def _bootstrap(self):
        omit_methods: Optional[FrozenSet[str]] = self.scenario.get("omitHttpMethods")
        if not omit_methods:
            omit_methods = frozenset([])
        for method in [
            responses.GET,
            responses.HEAD,
            responses.POST,
            responses.PUT,
        ]:
            if method not in omit_methods:
                self.mocked_responses.add_callback(
                    method=method, url=re.compile(r".*"), callback=self._handle_requests
                )
        self._reset_call_map()

    def _reset_call_map(self):
        self.call_map = {}
        for key in CallKey:
            self.call_map[key] = []

    def _handle_requests(self, request: requests.PreparedRequest) -> Optional[tuple]:
        request_kpis = get_request_kpis(request)
        for handler in [self._handle_common, self._handle_init, self._handle_create]:
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

    def _handle_init(self, request_kpis: RequestKPIs):
        url_deployment_seg = r"/providers/Microsoft\.Resources/deployments/aziotops\.enablement\.[a-zA-Z0-9\.-]+"
        if request_kpis.method == responses.POST:
            if re.match(
                path_pattern_base + url_deployment_seg + r"/whatIf$",
                request_kpis.path_url,
            ):
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
                assert request_kpis.params["api-version"] == ExpectedAPIVersion.RESOURCE.value
                assert f"/resourcegroups/{self.scenario['resourceGroup']}/" in request_kpis.path_url
                assert_init_deployment_body(body_str=request_kpis.body_str, target_scenario=self.scenario)
                self.call_map[CallKey.DEPLOY_INIT].append(request_kpis)
                return (200, STANDARD_HEADERS, json.dumps({}))

    def _handle_create(self, request_kpis: RequestKPIs):
        if request_kpis.method == responses.GET:
            if request_kpis.path_url == (
                f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{self.scenario['resourceGroup']}"
                f"/providers/microsoft.deviceregistry/schemaRegistries/{self.scenario['schemaRegistry']['name']}"
            ):
                assert request_kpis.params["api-version"] == ExpectedAPIVersion.SCHEMA_REGISTRY.value
                self.call_map[CallKey.GET_SCHEMA_REGISTRY].append(request_kpis)
                return (200, STANDARD_HEADERS, json.dumps(self.scenario["schemaRegistry"]))

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

        url_deployment_seg = r"/providers/Microsoft\.Resources/deployments/aziotops\.instance\.[a-zA-Z0-9\.-]+"
        if request_kpis.method == responses.POST:
            if re.match(
                path_pattern_base + url_deployment_seg + r"/whatIf$",
                request_kpis.path_url,
            ):
                assert request_kpis.params["api-version"] == ExpectedAPIVersion.RESOURCE.value
                assert f"/resourcegroups/{self.scenario['resourceGroup']}/" in request_kpis.path_url
                assert_instance_deployment_body(body_str=request_kpis.body_str, target_scenario=self.scenario)
                self.call_map[CallKey.DEPLOY_CREATE_WHATIF].append(request_kpis)
                api_response = self.scenario["apiControl"][CallKey.DEPLOY_CREATE_WHATIF]
                return (api_response["code"], STANDARD_HEADERS, json.dumps(api_response["body"]))

        if request_kpis.method == responses.PUT:
            if re.match(
                path_pattern_base + url_deployment_seg,
                request_kpis.path_url,
            ):
                assert request_kpis.params["api-version"] == ExpectedAPIVersion.RESOURCE.value
                assert f"/resourcegroups/{self.scenario['resourceGroup']}/" in request_kpis.path_url
                assert_instance_deployment_body(body_str=request_kpis.body_str, target_scenario=self.scenario)
                self.call_map[CallKey.DEPLOY_CREATE].append(request_kpis)
                return (200, STANDARD_HEADERS, json.dumps({}))

            if request_kpis.path_url.startswith(
                f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{self.scenario['resourceGroup']}"
                f"/providers/microsoft.deviceregistry/schemaRegistries/{self.scenario['schemaRegistry']['name']}"
                f"/providers/Microsoft.Authorization/roleAssignments/"
            ):
                ops_ext_identity = self._get_extension_identity()
                assert request_kpis.params["api-version"] == ExpectedAPIVersion.AUTHORIZATION.value
                self.call_map[CallKey.PUT_SCHEMA_REGISTRY_RA].append(request_kpis)
                api_control = self.scenario["apiControl"][CallKey.PUT_SCHEMA_REGISTRY_RA]

                return (api_control["code"], STANDARD_HEADERS, json.dumps(api_control["body"]))

    def _get_extension_identity(self, extension_type: str = EXTENSION_TYPE_OPS) -> Optional[dict]:
        for ext in self.scenario["cluster"]["extensions"]["value"]:
            if ext["properties"]["extensionType"] == extension_type:
                return ext.get("identity")


def get_request_kpis(request: requests.PreparedRequest):
    return RequestKPIs(
        method=request.method,
        url=request.url,
        params=request.params,
        path_url=request.path_url.split("?")[0],
        body_str=request.body,
    )


def build_target_scenario(
    extension_config_settings: Optional[dict] = None,
    omit_extension_types: Optional[FrozenSet[str]] = None,
    omit_http_methods: Optional[FrozenSet[str]] = None,
    raises: Optional[ExceptionMeta] = None,
    **kwargs,
) -> dict:
    schema_registry_name: str = generate_random_string()
    resource_group_name = generate_random_string()

    expected_extension_types: List[str] = list(OPS_EXTENSION_DEPS)
    expected_extension_types.append(EXTENSION_TYPE_OPS)
    if omit_extension_types:
        [expected_extension_types.remove(ext_type) for ext_type in omit_extension_types]

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
    if EXTENSION_TYPE_PLATFORM in default_extensions_config:
        default_extensions_config[EXTENSION_TYPE_PLATFORM]["properties"]["configurationSettings"][
            "installCertManager"
        ] = "true"
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
            "name": generate_random_string(),
            "location": generate_random_string(),
            "properties": {
                "provisioningState": PROVISIONING_STATE_SUCCESS,
                "connectivityStatus": CONNECTIVITY_STATUS_CONNECTED,
                "totalNodeCount": 1,
            },
            "extensions": {"value": extensions_list},
        },
        "customLocation": {"name": None},
        "providerNamespace": {
            "value": [{"namespace": namespace, "registrationState": "Registered"} for namespace in RP_NAMESPACE_SET]
        },
        "trust": {"userTrust": None, "settings": None},
        "enableFaultTolerance": None,
        "ensureLatest": None,
        "schemaRegistry": {
            "id": (
                f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{resource_group_name}"
                f"/providers/microsoft.deviceregistry/schemaRegistries/{schema_registry_name}"
            ),
            "name": schema_registry_name,
            "roleAssignments": {"value": []},
        },
        "dataflow": {"profileInstances": None},
        "akri": {
            "containerRuntimeSocket": None,
            "kubernetesDistro": None,
        },
        "noProgress": True,
        "raises": raises,
        "omitHttpMethods": omit_http_methods,
        "apiControl": {
            CallKey.DEPLOY_INIT_WHATIF: {"code": 200, "body": {"status": PROVISIONING_STATE_SUCCESS}},
            CallKey.DEPLOY_CREATE_WHATIF: {"code": 200, "body": {"status": PROVISIONING_STATE_SUCCESS}},
            CallKey.PUT_SCHEMA_REGISTRY_RA: {"code": 200, "body": {}},
        },
    }
    if "cluster_properties" in kwargs:
        payload["cluster"]["properties"].update(kwargs["cluster_properties"])
        kwargs.pop("cluster_properties")
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


def assert_exception(expected_exc_meta: ExceptionMeta, call_func: Callable, call_kwargs: dict):
    expected_exc_meta: ExceptionMeta
    with pytest.raises(expected_exc_meta.exc_type) as e:
        call_func(**call_kwargs)
    exc_msg = str(e.value)
    if expected_exc_meta.exc_msg:
        if isinstance(expected_exc_meta.exc_msg, list):
            for msg_seg in expected_exc_meta.exc_msg:
                assert msg_seg in exc_msg
            return
        assert expected_exc_meta.exc_msg in exc_msg


@pytest.mark.parametrize(
    "target_scenario",
    [
        build_target_scenario(),
        build_target_scenario(
            cluster_properties={"totalNodeCount": 3},
            enableFaultTolerance=True,
        ),
        build_target_scenario(
            trust={"userTrust": True},
        ),
        build_target_scenario(
            cluster_properties={"totalNodeCount": 3},
            enableFaultTolerance=True,
            trust={"userTrust": True},
        ),
        build_target_scenario(
            cluster_properties={"connectivityStatus": "Disconnected"},
            raises=ExceptionMeta(
                exc_type=ValidationError,
                exc_msg="connectivityStatus is not Connected.",
            ),
            omit_http_methods=frozenset([responses.PUT, responses.POST]),
        ),
        build_target_scenario(
            cluster_properties={"totalNodeCount": 1},
            enableFaultTolerance=True,
            raises=ExceptionMeta(
                exc_type=ValidationError,
                exc_msg="Arc Container Storage fault tolerance enablement requires at least 3 nodes.",
            ),
            omit_http_methods=frozenset([responses.PUT, responses.POST]),
        ),
        build_target_scenario(
            apiControl={CallKey.DEPLOY_INIT_WHATIF: {"code": 200, "body": {"status": "Failed"}}},
            raises=ExceptionMeta(
                exc_type=AzureResponseError,
                exc_msg=json.dumps({"status": "Failed"}, indent=2),
            ),
            omit_http_methods=frozenset([responses.PUT]),
        ),
    ],
)
def test_iot_ops_init(
    mocked_cmd: Mock,
    mocked_responses: responses,
    mocked_sleep: Mock,
    spy_work_displays: Dict[str, Mock],
    target_scenario: dict,
):
    servgen = ServiceGenerator(scenario=target_scenario, mocked_responses=mocked_responses)
    from azext_edge.edge.commands_edge import init

    init_call_kwargs = {
        "cmd": mocked_cmd,
        "cluster_name": target_scenario["cluster"]["name"],
        "resource_group_name": target_scenario["resourceGroup"],
    }
    if target_scenario["enableFaultTolerance"]:
        init_call_kwargs["enable_fault_tolerance"] = target_scenario["enableFaultTolerance"]
    if target_scenario["trust"]["userTrust"]:
        init_call_kwargs["user_trust"] = target_scenario["trust"]["userTrust"]

    if target_scenario["noProgress"]:
        init_call_kwargs["no_progress"] = target_scenario["noProgress"]
    if target_scenario["ensureLatest"]:
        init_call_kwargs["ensure_latest"] = target_scenario["ensureLatest"]

    exc_meta: Optional[ExceptionMeta] = target_scenario.get("raises")
    if exc_meta:
        exc_meta: ExceptionMeta
        assert_exception(expected_exc_meta=exc_meta, call_func=init, call_kwargs=init_call_kwargs)
        return

    init_result = init(**init_call_kwargs)  # pylint: disable=assignment-from-no-return
    expected_call_count_map = {
        CallKey.CONNECT_RESOURCE_MANAGER: 1,
        CallKey.GET_RESOURCE_PROVIDERS: 1,
        CallKey.GET_CLUSTER: 1,
        CallKey.DEPLOY_INIT_WHATIF: 1,
        CallKey.DEPLOY_INIT: 1,
    }
    assert_call_map(expected_call_count_map, servgen.call_map)
    assert_init_displays(spy_work_displays, target_scenario)

    # TODO - @digimaun
    if target_scenario["noProgress"]:
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

    expected_advanced_config = {}
    if target_scenario["enableFaultTolerance"]:
        expected_advanced_config["edgeStorageAccelerator"] = {"faultToleranceEnabled": True}
    assert parameters["advancedConfig"]["value"] == expected_advanced_config


@pytest.mark.parametrize(
    "target_scenario",
    [
        build_target_scenario(),
        build_target_scenario(
            akri={"containerRuntimeSocket": "/var/containerd/socket", "kubernetesDistro": "K3s"},
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
            omit_http_methods=frozenset([responses.PUT, responses.POST]),
        ),
        build_target_scenario(
            extension_config_settings={
                EXTENSION_TYPE_PLATFORM: {
                    "properties": {
                        "extensionType": EXTENSION_TYPE_PLATFORM,
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
                    EXTENSION_TYPE_PLATFORM,
                    "\n\nInstance deployment will not continue. Please run 'az iot ops init'.",
                ],
            ),
            omit_http_methods=frozenset([responses.PUT, responses.POST]),
        ),
        build_target_scenario(
            omit_extension_types=frozenset([EXTENSION_TYPE_PLATFORM]),
            raises=ExceptionMeta(
                exc_type=ValidationError,
                exc_msg=(
                    "Foundational service(s) not detected on the cluster:\n\n"
                    f"{EXTENSION_TYPE_PLATFORM}"
                    "\n\nInstance deployment will not continue. Please run 'az iot ops init'."
                ),
            ),
            omit_http_methods=frozenset([responses.PUT, responses.POST]),
        ),
        build_target_scenario(
            extension_config_settings={
                EXTENSION_TYPE_PLATFORM: {
                    "properties": {
                        "extensionType": EXTENSION_TYPE_PLATFORM,
                        "provisioningState": PROVISIONING_STATE_SUCCESS,
                        "configurationSettings": {"installCertManager": "false"},
                    }
                },
            },
            raises=ExceptionMeta(
                exc_type=ValidationError,
                exc_msg=(
                    "Cluster was enabled with user-managed trust configuration, --trust-settings "
                    "arguments are required to create an instance on this cluster."
                ),
            ),
            omit_http_methods=frozenset([responses.PUT, responses.POST]),
        ),
        build_target_scenario(
            extension_config_settings={
                EXTENSION_TYPE_PLATFORM: {
                    "id": generate_random_string(),
                    "properties": {
                        "extensionType": EXTENSION_TYPE_PLATFORM,
                        "provisioningState": PROVISIONING_STATE_SUCCESS,
                        "configurationSettings": {"installCertManager": "false"},
                    },
                },
            },
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
            extension_config_settings={
                EXTENSION_TYPE_PLATFORM: {
                    "id": generate_random_string(),
                    "properties": {
                        "extensionType": EXTENSION_TYPE_PLATFORM,
                        "provisioningState": PROVISIONING_STATE_SUCCESS,
                        "configurationSettings": {"installCertManager": "false"},
                    },
                },
            },
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
            omit_http_methods=frozenset([responses.PUT, responses.POST, responses.GET, responses.HEAD]),
        ),
        build_target_scenario(
            apiControl={CallKey.PUT_SCHEMA_REGISTRY_RA: {"code": 400, "body": {"status": "Failed"}}},
            warnings=[(0, "Role assignment failed with:\nOperation returned an invalid status 'Bad Request'")],
        ),
    ],
)
def test_iot_ops_create(
    mocked_cmd: Mock,
    mocked_responses: responses,
    mocked_sleep: Mock,
    spy_work_displays: Dict[str, Mock],
    mocked_logger: Mock,
    target_scenario: dict,
):
    servgen = ServiceGenerator(scenario=target_scenario, mocked_responses=mocked_responses)
    from azext_edge.edge.commands_edge import create_instance

    create_call_kwargs = {
        "cmd": mocked_cmd,
        "cluster_name": target_scenario["cluster"]["name"],
        "resource_group_name": target_scenario["resourceGroup"],
        "instance_name": target_scenario["instance"]["name"],
        "schema_registry_resource_id": target_scenario["schemaRegistry"]["id"],
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
    if target_scenario["enableRsyncRules"] is not None:
        create_call_kwargs["enable_rsync_rules"] = bool(target_scenario["enableRsyncRules"])
    if target_scenario["instance"]["description"]:
        create_call_kwargs["instance_description"] = target_scenario["instance"]["description"]
    if target_scenario["dataflow"]["profileInstances"]:
        create_call_kwargs["dataflow_profile_instances"] = target_scenario["dataflow"]["profileInstances"]
    if target_scenario["trust"]["settings"]:
        create_call_kwargs["trust_settings"] = target_scenario["trust"]["settings"]
    if target_scenario["akri"]["containerRuntimeSocket"]:
        create_call_kwargs["container_runtime_socket"] = target_scenario["akri"]["containerRuntimeSocket"]
    if target_scenario["akri"]["kubernetesDistro"]:
        create_call_kwargs["kubernetes_distro"] = target_scenario["akri"]["kubernetesDistro"]

    if target_scenario["noProgress"]:
        create_call_kwargs["no_progress"] = target_scenario["noProgress"]

    exc_meta: Optional[ExceptionMeta] = target_scenario.get("raises")
    if exc_meta:
        exc_meta: ExceptionMeta
        assert_exception(expected_exc_meta=exc_meta, call_func=create_instance, call_kwargs=create_call_kwargs)
        return

    create_result = create_instance(**create_call_kwargs)  # pylint: disable=assignment-from-no-return

    expected_call_count_map = {
        CallKey.CONNECT_RESOURCE_MANAGER: 1,
        CallKey.GET_RESOURCE_PROVIDERS: 1,
        CallKey.GET_CLUSTER: 1,
        CallKey.GET_SCHEMA_REGISTRY: 1,
        CallKey.GET_CLUSTER_EXTENSIONS: 2,
        CallKey.GET_SCHEMA_REGISTRY_RA: 1,
        CallKey.PUT_SCHEMA_REGISTRY_RA: 1,
        CallKey.DEPLOY_CREATE_WHATIF: 1,
        CallKey.DEPLOY_CREATE: 1,
    }
    assert_call_map(expected_call_count_map, servgen.call_map)
    assert_create_displays(spy_work_displays, target_scenario)
    assert_logger(mocked_logger, target_scenario)

    # TODO - @digimaun
    if target_scenario["noProgress"]:
        assert create_result is None


def assert_logger(mocked_logger: Mock, target_scenario: dict):
    expeted_warnings: List[Tuple[int, str]] = target_scenario.get("warnings", [])
    warning_calls: List[Mock] = mocked_logger.warning.mock_calls
    for w in expeted_warnings:
        assert w[1] in warning_calls[w[0]].args[0]


def assert_create_displays(spy_work_displays: Dict[str, Mock], target_scenario: dict):
    # TODO
    pass


def assert_instance_deployment_body(body_str: str, target_scenario: dict):
    assert body_str
    body = json.loads(body_str)

    mode = body["properties"]["mode"]
    assert mode == "Incremental"

    template = body["properties"]["template"]
    for key in EXPECTED_INSTANCE_RESOURCE_KEYS:
        assert template["resources"][key]
    assert len(template["resources"]) == len(EXPECTED_INSTANCE_RESOURCE_KEYS)

    resources = template["resources"]
    parameters = body["properties"]["parameters"]

    assert parameters["clusterName"]["value"] == target_scenario["cluster"]["name"]
    assert parameters["clusterNamespace"]["value"] == target_scenario["instance"]["namespace"] or DEFAULT_NAMESPACE
    assert (
        parameters["clusterLocation"]["value"] == target_scenario["location"] or target_scenario["cluster"]["location"]
    )

    instance_name: str = target_scenario["instance"]["name"]
    instance_name_lowered = instance_name.lower()
    assert resources["aioInstance"]["name"] == instance_name_lowered
    assert resources["broker"]["name"] == f"{instance_name_lowered}/{DEFAULT_BROKER}"
    assert resources["broker_authn"]["name"] == f"{instance_name_lowered}/{DEFAULT_BROKER}/{DEFAULT_BROKER_AUTHN}"
    assert (
        resources["broker_listener"]["name"] == f"{instance_name_lowered}/{DEFAULT_BROKER}/{DEFAULT_BROKER_LISTENER}"
    )
    assert resources["dataflow_profile"]["name"] == f"{instance_name_lowered}/{DEFAULT_DATAFLOW_PROFILE}"
    assert resources["dataflow_endpoint"]["name"] == f"{instance_name_lowered}/{DEFAULT_DATAFLOW_ENDPOINT}"

    if target_scenario["instance"]["description"]:
        assert resources["aioInstance"]["properties"]["description"] == target_scenario["instance"]["description"]
    if target_scenario["instance"]["tags"]:
        assert resources["aioInstance"]["tags"] == target_scenario["instance"]["tags"]

    cl_extension_ids = set(
        [
            ext["id"]
            for ext in target_scenario["cluster"]["extensions"]["value"]
            if ext["properties"]["extensionType"] in [EXTENSION_TYPE_PLATFORM, EXTENSION_TYPE_SSC]
        ]
    )
    assert set(parameters["clExtentionIds"]["value"]) == cl_extension_ids
    assert parameters["schemaRegistryId"]["value"] == target_scenario["schemaRegistry"]["id"]
    assert parameters["deployResourceSyncRules"]["value"] == bool(target_scenario["enableRsyncRules"])

    assert (
        parameters["kubernetesDistro"]["value"] == target_scenario["akri"]["kubernetesDistro"]
        or KubernetesDistroType.k8s.value
    )

    if target_scenario["akri"]["containerRuntimeSocket"]:
        assert parameters["containerRuntimeSocket"]["value"] == target_scenario["akri"]["containerRuntimeSocket"]

    expected_profile_instances = target_scenario.get("dataflow", {}).get("profileInstances") or 1
    assert parameters["defaultDataflowinstanceCount"]["value"] == expected_profile_instances

    # @digimaun - this asserts defaults. brokerConfig should be primary tested in targets unit tests.
    assert parameters["brokerConfig"] == {
        "value": {
            "frontendReplicas": 2,
            "frontendWorkers": 2,
            "backendRedundancyFactor": 2,
            "backendWorkers": 2,
            "backendPartitions": 2,
            "memoryProfile": "Medium",
            "serviceType": "ClusterIp",
        }
    }
    expected_trust_config = {"source": "SelfSigned"}
    if target_scenario["trust"]["settings"]:
        assembled_settings = assemble_nargs_to_dict(target_scenario["trust"]["settings"])
        expected_trust_config = {"source": "CustomerManaged", "settings": assembled_settings}
    assert parameters["trustConfig"]["value"] == expected_trust_config
