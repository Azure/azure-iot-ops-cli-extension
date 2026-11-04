# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json

import pytest
import responses
from azure.cli.core.azclierror import ValidationError
from azure.core.exceptions import HttpResponseError, ServiceRequestError, ServiceResponseError
from azure.core.pipeline import Pipeline
from azure.core.pipeline.transport import HttpRequest, RequestsTransport
from azure.core.exceptions import ServiceResponseTimeoutError

from azext_edge.edge.providers.orchestration.mgmt_actions import MgmtActions
from azext_edge.edge.providers.orchestration.resources.instances import (
    IOTOPS_CHILD_RESOURCE_TYPES,
    SUPPORTED_CHILD_API_VERSIONS,
    Instances,
    _ChildApiNegotiationPolicy,
)
from azext_edge.edge.util.az_client import DEFAULT_IOTOPS_MGMT_API_VERSION
from . import test_mgmt_actions_unit as mgmt_cases
from ...generators import get_zeroed_subscription
from ...helpers import build_mock_cmd_for_cloud


SUBSCRIPTION = get_zeroed_subscription()
OTHER_SUBSCRIPTION = "11111111-1111-1111-1111-111111111111"
BASE_URL = "https://management.azure.com"
INSTANCE_ID = (
    f"/subscriptions/{SUBSCRIPTION}/resourceGroups/instance-rg"
    "/providers/Microsoft.IoTOperations/instances/instance"
)
CUSTOM_LOCATION_ID = (
    f"/subscriptions/{OTHER_SUBSCRIPTION}/resourceGroups/location-rg"
    "/providers/Microsoft.ExtendedLocation/customLocations/location"
)
INSTANCE = {
    "id": INSTANCE_ID,
    "name": "instance",
    "properties": {"version": "1.4.112"},
    "extendedLocation": {"name": CUSTOM_LOCATION_ID, "type": "CustomLocation"},
}
INSTANCE_URL = f"{BASE_URL}{INSTANCE_ID}?api-version={DEFAULT_IOTOPS_MGMT_API_VERSION.value}"
CAPABILITIES_URL = f"{BASE_URL}{CUSTOM_LOCATION_ID}/enabledResourceTypes?api-version=2021-08-31-preview"
PATH = "azext_edge.edge.providers.orchestration.resources.instances"


@pytest.fixture
def instances(mocked_cmd):
    return Instances(mocked_cmd)


def enabled_types(resource_types=None, api_versions=("2026-07-01",)):
    types = resource_types if resource_types is not None else IOTOPS_CHILD_RESOURCE_TYPES.values()
    return {
        "value": [{
            "properties": {
                "typesMetadata": [
                    {
                        "resourceProviderNamespace": "Microsoft.IoTOperations",
                        "resourceType": resource_type,
                        "apiVersion": api_version,
                    }
                    for resource_type in types
                    for api_version in api_versions
                ],
            },
        }],
    }


def select_api(instances, groups=("dataflow_endpoint",), instance=INSTANCE):
    instances.use_child_api("instance", "instance-rg", groups, instance=instance)
    return instances.iotops_mgmt_client


@pytest.mark.parametrize("version", ["1.3.14", "1.4.112", "1.5.30", "2.0.0", "unknown", None])
def test_selection_depends_on_capabilities_not_runtime_version(instances, mocked_responses, version):
    instance = {**INSTANCE, "properties": {"version": version}}
    mocked_responses.add(responses.GET, CAPABILITIES_URL, json=enabled_types())

    client = select_api(instances, instance=instance)

    assert client._config.api_version == "2026-07-01"
    assert len(mocked_responses.calls) == 1


def test_newest_common_supported_ga_api_and_discovery_cache(instances, mocked_responses):
    payload = enabled_types(api_versions=("2026-03-01", "2026-07-01", "2030-01-01", "2026-11-01-preview"))
    payload["value"][0]["properties"]["typesMetadata"].append({
        "resourceProviderNamespace": "Microsoft.Other", "resourceType": "instances/dataflowEndpoints",
        "apiVersion": "2026-10-01",
    })
    mocked_responses.add(responses.GET, CAPABILITIES_URL, json=payload)

    first = select_api(instances)
    second = select_api(instances, ["dataflow_graph"])

    assert first._config.api_version == "2026-07-01"
    assert first is second
    assert len(mocked_responses.calls) == 1
    assert not any(version.endswith("-preview") for version in SUPPORTED_CHILD_API_VERSIONS)


def test_workflow_uses_intersection_not_union(instances, mocked_responses):
    payload = enabled_types(api_versions=("2026-07-01",))
    newer_endpoint = enabled_types(["instances/dataflowEndpoints"], ("2026-10-01",))
    payload["value"][0]["properties"]["typesMetadata"].extend(newer_endpoint["value"][0]["properties"]["typesMetadata"])
    mocked_responses.add(responses.GET, CAPABILITIES_URL, json=payload)

    client = select_api(instances, ["dataflow_endpoint", "dataflow_graph"])

    assert client._config.api_version == "2026-07-01"


def test_capability_cache_is_isolated_between_targets(instances, mocked_responses):
    other_location = CUSTOM_LOCATION_ID.replace("/location", "/other-location")
    other_instance = {
        **INSTANCE, "id": f"{INSTANCE_ID.rsplit('/', 1)[0]}/other-instance",
        "extendedLocation": {"name": other_location, "type": "CustomLocation"},
    }
    mocked_responses.add(responses.GET, CAPABILITIES_URL, json=enabled_types())
    mocked_responses.add(
        responses.GET, CAPABILITIES_URL.replace(CUSTOM_LOCATION_ID, other_location),
        json=enabled_types(api_versions=("2026-10-01",)),
    )
    first = select_api(instances)
    instances.use_child_api("other-instance", "instance-rg", ["dataflow_endpoint"], instance=other_instance)
    assert first._config.api_version == "2026-07-01"
    assert instances.iotops_mgmt_client._config.api_version == "2026-10-01"
    assert len(mocked_responses.calls) == 2


def test_discovery_matches_resource_types_case_insensitively(instances, mocked_responses):
    payload = enabled_types()
    for metadata in payload["value"][0]["properties"]["typesMetadata"]:
        metadata["resourceProviderNamespace"] = metadata["resourceProviderNamespace"].upper()
        metadata["resourceType"] = metadata["resourceType"].upper()
    mocked_responses.add(responses.GET, CAPABILITIES_URL, json=payload)
    assert select_api(instances)._config.api_version == "2026-07-01"


@pytest.mark.parametrize("while_paging", [False, True])
@pytest.mark.parametrize("payload", [
    {"value": {}}, {"value": ""},
    None, [], False, 0, "invalid", {},
    {"value": None}, {"value": False}, {"value": 0}, {"value": "invalid"},
    {"value": [], "nextLink": False}, {"value": [], "nextLink": 0},
    {"value": [], "nextLink": []}, {"value": [], "nextLink": {}},
    {"value": [], "nextLink": " "},
])
def test_malformed_discovery_pages_discard_all_capabilities(instances, mocked_responses, payload, while_paging):
    page_url = CAPABILITIES_URL
    expected_urls = [CAPABILITIES_URL]
    if while_paging:
        page_url += "&page=2"
        first_page = enabled_types(["instances/dataflowEndpoints"])
        first_page["nextLink"] = page_url
        mocked_responses.add(responses.GET, CAPABILITIES_URL, json=first_page)
        expected_urls.append(page_url)
    mocked_responses.add(
        responses.GET, page_url, body=json.dumps(payload), content_type="application/json",
    )

    client = select_api(instances, groups=IOTOPS_CHILD_RESOURCE_TYPES)

    assert client._config.api_version == DEFAULT_IOTOPS_MGMT_API_VERSION.value
    assert instances._child_api_location is None
    assert instances._child_api_capabilities == {}
    url = f"{BASE_URL}{INSTANCE_ID}/dataflowEndpoints/child?api-version="
    mocked_responses.add(
        responses.PUT, url + "2026-10-01", status=400,
        json={"error": {"code": "MissingAzureKubernetesMapping"}},
    )
    mocked_responses.add(responses.PUT, url + "2026-07-01", status=200, json={"name": "child"})
    assert client.dataflow_endpoint.begin_create_or_update(
        resource_group_name="instance-rg", instance_name="instance", dataflow_endpoint_name="child",
        resource={"properties": {}},
    ).result()["name"] == "child"
    assert [call.request.url for call in mocked_responses.calls] == expected_urls + [
        url + "2026-10-01", url + "2026-07-01",
    ]

    mocked_responses.replace(responses.GET, CAPABILITIES_URL, json=enabled_types())
    assert select_api(instances, groups=IOTOPS_CHILD_RESOURCE_TYPES)._config.api_version == "2026-07-01"
    assert instances._child_api_location == CUSTOM_LOCATION_ID.lower()
    assert set(instances._child_api_capabilities) == {value.lower() for value in IOTOPS_CHILD_RESOURCE_TYPES.values()}
    assert mocked_responses.calls[-1].request.url == CAPABILITIES_URL


@pytest.mark.parametrize("last_link", [None, ""])
def test_valid_discovery_pages_are_combined_before_caching(instances, mocked_responses, last_link):
    second_url, third_url = CAPABILITIES_URL + "&page=2", CAPABILITIES_URL + "&page=3"
    first_page = enabled_types(["instances/dataflowEndpoints"])
    first_page["nextLink"] = second_url
    last_page = enabled_types([
        "instances/dataflowProfiles/dataflows", "instances/dataflowProfiles/dataflowGraphs",
    ])
    last_page["nextLink"] = last_link
    mocked_responses.add(responses.GET, CAPABILITIES_URL, json=first_page)
    mocked_responses.add(responses.GET, second_url, json={"value": [], "nextLink": third_url})
    mocked_responses.add(responses.GET, third_url, json=last_page)

    first = select_api(instances, groups=IOTOPS_CHILD_RESOURCE_TYPES)
    assert first._config.api_version == "2026-07-01"
    assert select_api(instances, groups=IOTOPS_CHILD_RESOURCE_TYPES) is first
    assert [call.request.url for call in mocked_responses.calls] == [CAPABILITIES_URL, second_url, third_url]


@pytest.mark.parametrize("status,body", [(200, "{"), (403, "{}"), (503, "{}")])
def test_discovery_page_failure_discards_earlier_pages(instances, mocked_responses, status, body):
    second_url = CAPABILITIES_URL + "&page=2"
    first_page = enabled_types()
    first_page["nextLink"] = second_url
    mocked_responses.add(responses.GET, CAPABILITIES_URL, json=first_page)
    mocked_responses.add(responses.GET, second_url, status=status, body=body, content_type="application/json")
    assert select_api(instances)._config.api_version == DEFAULT_IOTOPS_MGMT_API_VERSION.value
    assert instances._child_api_location is None
    assert instances._child_api_capabilities == {}
    assert [call.request.url for call in mocked_responses.calls] == [CAPABILITIES_URL, second_url]


def test_cyclic_discovery_pages_fall_back_without_caching(instances, mocked_responses):
    second_url = CAPABILITIES_URL + "&page=2"
    first_page = enabled_types()
    first_page["nextLink"] = second_url
    mocked_responses.add(responses.GET, CAPABILITIES_URL, json=first_page)
    mocked_responses.add(responses.GET, second_url, json={"value": [], "nextLink": second_url})
    assert select_api(instances)._config.api_version == DEFAULT_IOTOPS_MGMT_API_VERSION.value
    assert instances._child_api_location is None
    assert instances._child_api_capabilities == {}
    assert [call.request.url for call in mocked_responses.calls] == [CAPABILITIES_URL, second_url]


@pytest.mark.parametrize("payload", [
    enabled_types(["instances/brokers"], ("2026-10-01",)),
    enabled_types(api_versions=("2030-01-01",)),
    enabled_types(api_versions=("2026-11-01-preview",)),
])
def test_confirmed_unsupported_capabilities_fail_closed(instances, mocked_responses, payload):
    mocked_responses.add(responses.GET, CAPABILITIES_URL, json=payload)
    with pytest.raises(ValidationError, match="No CLI-supported GA API"):
        select_api(instances)
    assert [call.request.method for call in mocked_responses.calls] == ["GET"]


@pytest.mark.parametrize("location", ["", "not-an-id", INSTANCE_ID])
def test_invalid_custom_location_is_actionable(instances, location):
    with pytest.raises(ValidationError, match="extendedLocation.name"):
        instances._read_child_api_capabilities(location)


@pytest.mark.parametrize("failure", [HttpResponseError, ServiceRequestError, ServiceResponseError])
@pytest.mark.parametrize("while_paging", [False, True])
def test_discovery_failures_never_cache_partial_capabilities(instances, mocker, failure, while_paging):
    factory = mocker.patch(f"{PATH}.get_extloc_mgmt_client")
    listing = factory.return_value.custom_locations.list_enabled_resource_types

    def pages():
        yield enabled_types()["value"][0]
        raise failure("unreadable")

    if while_paging:
        listing.return_value = pages()
    else:
        listing.side_effect = failure("unreadable")
    assert select_api(instances)._config.api_version == DEFAULT_IOTOPS_MGMT_API_VERSION.value
    assert instances._child_api_location is None
    assert instances._child_api_capabilities == {}
    factory.assert_called_once_with(
        subscription_id=OTHER_SUBSCRIPTION, endpoint=f"{BASE_URL}/",
        retry_total=0, connection_timeout=5, read_timeout=5,
    )


@pytest.mark.parametrize("cloud_name,endpoint", [
    ("AzureUSGovernment", "https://management.usgovcloudapi.net"),
    ("AzureChinaCloud", "https://management.chinacloudapi.cn"),
])
def test_cross_subscription_discovery_and_child_request_use_active_cloud(
    mocked_cmd, mocked_responses, mocked_azcli_cred_get_token, cloud_name, endpoint,
):
    mocked_cmd.cli_ctx.cloud = build_mock_cmd_for_cloud(cloud_name).cli_ctx.cloud
    mocked_azcli_cred_get_token.reset_mock()
    mocked_responses.add(responses.GET, INSTANCE_URL.replace(BASE_URL, endpoint), json=INSTANCE)
    mocked_responses.add(responses.GET, CAPABILITIES_URL.replace(BASE_URL, endpoint), json=enabled_types())
    child_url = f"{endpoint}{INSTANCE_ID}/dataflowEndpoints/child?api-version=2026-07-01"
    mocked_responses.add(responses.GET, child_url, json={"name": "child"})

    instances = Instances(mocked_cmd)
    instances.use_child_api("instance", "instance-rg", ["dataflow_endpoint"])
    assert instances.iotops_mgmt_client.dataflow_endpoint.get(
        resource_group_name="instance-rg", instance_name="instance", dataflow_endpoint_name="child",
    ) == {"name": "child"}
    assert [call.request.url for call in mocked_responses.calls] == [
        INSTANCE_URL.replace(BASE_URL, endpoint), CAPABILITIES_URL.replace(BASE_URL, endpoint), child_url,
    ]
    assert mocked_azcli_cred_get_token.call_args_list
    assert all(call.args == (f"{endpoint}/.default",) for call in mocked_azcli_cred_get_token.call_args_list)


@pytest.mark.parametrize("missing", ["dataflow_endpoint", "dataflow_graph", "dataflow"])
def test_mgmt_actions_preflights_every_required_type_before_writes(mocked_cmd, mocked_responses, mocker, missing):
    mocker.patch("azext_edge.edge.providers.orchestration.mgmt_actions.WorkflowDisplay")
    fixtures = mgmt_cases.TestEnable()._make_enable_fixtures()
    mocked_responses.add(
        responses.GET, mgmt_cases._build_iotops_endpoint(fixtures["instance_name"], fixtures["rg"]),
        json=fixtures["instance_response"],
    )
    payload = enabled_types(
        [resource_type for group, resource_type in IOTOPS_CHILD_RESOURCE_TYPES.items() if group != missing],
        ("2026-10-01",),
    )
    url = f"{BASE_URL}{fixtures['cl_id']}/enabledResourceTypes?api-version=2021-08-31-preview"
    mocked_responses.add(responses.GET, url, json=payload)
    with pytest.raises(ValidationError, match="not enabled"):
        MgmtActions(mocked_cmd).enable(
            name=fixtures["instance_name"], resource_group_name=fixtures["rg"], eg_resource_id=fixtures["eg_rid"],
        )
    assert [call.request.method for call in mocked_responses.calls] == ["GET", "GET"]


@pytest.mark.parametrize("status,payload,prior_page", [
    (200, {"value": []}, False),
    (200, {}, False),
    (200, {"value": enabled_types(["instances/dataflowEndpoints"])["value"] + [
        {"properties": {"typesMetadata": False}},
    ]}, False),
    (200, {"value": enabled_types(["instances/dataflowEndpoints"])["value"] + [
        {"properties": {"typesMetadata": [{
            "resourceType": "instances/dataflowProfiles/dataflows", "apiVersion": "2026-07-01",
        }]}},
    ]}, False),
    (403, {"error": {"code": "AuthorizationFailed", "message": "Access denied"}}, False),
    (503, {"error": {"code": "ServiceUnavailable", "message": "Discovery unavailable"}}, False),
    (200, {"value": {}}, True),
    (200, {"value": ""}, True),
])
@pytest.mark.parametrize("accepted_api", ["2026-03-01", "2026-07-01", "2026-10-01"])
def test_mgmt_actions_enable_negotiates_without_discovery(
    mocked_cmd, mocked_responses, mocker, status, payload, prior_page, accepted_api,
):
    mocker.patch("azext_edge.edge.providers.orchestration.mgmt_actions.WorkflowDisplay")
    mocker.patch("azext_edge.edge.providers.orchestration.mgmt_actions.render_summary")
    mocker.patch.object(MgmtActions, "_resolve_dataflow_auth_identity", return_value="principal")
    mocker.patch.object(MgmtActions, "_setup_role_assignments", return_value={})
    helper = mgmt_cases.TestEnable()
    fixtures = helper._make_enable_fixtures()
    helper._register_enable_mocks(mocked_responses, fixtures)
    discovery_url = f"{BASE_URL}{fixtures['cl_id']}/enabledResourceTypes?api-version=2021-08-31-preview"
    if prior_page:
        first_page = enabled_types(["instances/dataflowEndpoints"])
        first_page["nextLink"] = discovery_url + "&page=2"
        mocked_responses.add(responses.GET, discovery_url, json=first_page)
        discovery_url = first_page["nextLink"]
    mocked_responses.add(responses.GET, discovery_url, json=payload, status=status)
    versions = sorted((v for v in SUPPORTED_CHILD_API_VERSIONS if v >= accepted_api), reverse=True)
    for response in list(mocked_responses.registered()):
        if response.method != "PUT" or "/Microsoft.IoTOperations/instances/" not in response.url:
            continue
        mocked_responses.remove(response)
        for api_version in versions:
            url = response.url.split("?")[0] + f"?api-version={api_version}"
            if api_version == accepted_api:
                mocked_responses.add(
                    responses.PUT, url, status=response.status, body=response.body, headers=response.headers,
                )
            else:
                mocked_responses.add(
                    responses.PUT, url, status=400,
                    json={"error": {"code": "MissingAzureKubernetesMapping", "message": "Unsupported API"}},
                )
    provider = MgmtActions(mocked_cmd)
    result = provider.enable(
        name=fixtures["instance_name"], resource_group_name=fixtures["rg"],
        eg_resource_id=fixtures["eg_rid"], wait_sec=0,
    )
    assert result["instance"]["dataflowEndpoint"]["name"] == fixtures["ep_name"]
    assert provider.instances._child_api_capabilities == {}
    puts = [
        call.request for call in mocked_responses.calls
        if call.request.method == "PUT" and "/Microsoft.IoTOperations/instances/" in call.request.url
    ]
    assert len(puts) == 3 * len(versions)
    for index in range(0, len(puts), len(versions)):
        attempts = puts[index:index + len(versions)]
        assert [request.url.split("api-version=")[1] for request in attempts] == versions
        assert all(request.body == attempts[0].body for request in attempts)


@pytest.mark.parametrize("operation", ["enable", "show", "disable"])
@pytest.mark.parametrize("api_version", ["2026-03-01", "2026-07-01", "2026-10-01"])
def test_mgmt_actions_only_enable_needs_discovery(mocked_cmd, mocked_responses, mocker, operation, api_version):
    mocker.patch("azext_edge.edge.providers.orchestration.mgmt_actions.WorkflowDisplay")
    mocker.patch("azext_edge.edge.providers.orchestration.mgmt_actions.render_summary")
    child_api = api_version if operation == "enable" else DEFAULT_IOTOPS_MGMT_API_VERSION.value
    mocker.patch.object(mgmt_cases, "IOTOPS_API_VERSION", child_api)
    if operation == "enable":
        helper = mgmt_cases.TestEnable()
        fixtures = helper._make_enable_fixtures()
        helper._register_enable_mocks(mocked_responses, fixtures)
        mocker.patch.object(MgmtActions, "_resolve_dataflow_auth_identity", return_value="principal")
        mocker.patch.object(MgmtActions, "_setup_role_assignments", return_value={})
    elif operation == "show":
        helper = mgmt_cases.TestShow()
        fixtures = helper._make_show_fixtures()
        helper._register_show_mocks(mocked_responses, fixtures)
    else:
        helper = mgmt_cases.TestDisable()
        fixtures = helper._make_disable_fixtures()
        helper._register_disable_mocks(mocked_responses, fixtures)
        mocker.patch(helper.PROMPT_TARGET, return_value=True)
    old_url = mgmt_cases._build_iotops_endpoint(fixtures["instance_name"], fixtures["rg"])
    instance = mgmt_cases._build_instance_response(
        fixtures["instance_name"], fixtures["rg"],
        version={"2026-03-01": "1.3.14", "2026-07-01": "1.4.112", "2026-10-01": "1.5.30"}[api_version],
    )
    mocked_responses.remove(responses.GET, old_url)
    mocked_responses.add(
        responses.GET, f"{old_url.split('?')[0]}?api-version={DEFAULT_IOTOPS_MGMT_API_VERSION.value}", json=instance,
    )
    location = instance["extendedLocation"]["name"]
    enabled_versions = tuple(
        version for version in ("2024-11-01", "2025-04-01", "2025-10-01", "2026-03-01", "2026-07-01", "2026-10-01")
        if version <= api_version
    )
    if operation == "enable":
        mocked_responses.add(
            responses.GET, f"{BASE_URL}{location}/enabledResourceTypes?api-version=2021-08-31-preview",
            json=enabled_types(api_versions=enabled_versions),
        )
    else:
        discovery = mocker.patch(f"{PATH}.get_extloc_mgmt_client", side_effect=AssertionError("Unexpected discovery"))
    kwargs = {"name": fixtures["instance_name"], "resource_group_name": fixtures["rg"]}
    provider = MgmtActions(mocked_cmd)
    if operation == "enable":
        result = provider.enable(**kwargs, eg_resource_id=fixtures["eg_rid"], wait_sec=0)
        assert result["instance"]["dataflowEndpoint"]["name"] == fixtures["ep_name"]
    elif operation == "show":
        result = provider.show(**kwargs)
        helper._assert_instance_all_exist(result, fixtures)
    else:
        provider.disable(**kwargs, confirm_yes=True, wait_sec=0)
    child_calls = [call.request for call in mocked_responses.calls if "/dataflow" in call.request.url]
    assert len(child_calls) == {"enable": 6, "show": 3, "disable": 5}[operation]
    assert all(call.url.endswith(f"?api-version={child_api}") for call in child_calls)
    if operation != "enable":
        discovery.assert_not_called()
        assert not any("/enabledResourceTypes" in call.request.url for call in mocked_responses.calls)


@pytest.mark.parametrize("status,code", [
    (400, "InvalidRequest"),
    (401, "Unauthorized"),
    (403, "AuthorizationFailed"),
    (409, "Conflict"),
    (500, "MissingAzureKubernetesMapping"),
    (400, None),
])
def test_negotiation_does_not_downgrade_unrelated_failures(instances, mocked_responses, status, code):
    mocked_responses.add(responses.GET, CAPABILITIES_URL, status=403, json={"error": {"code": "AuthorizationFailed"}})
    client = select_api(instances)
    client._config.retry_policy.total_retries = 0
    url = f"{BASE_URL}{INSTANCE_ID}/dataflowEndpoints/child?api-version={DEFAULT_IOTOPS_MGMT_API_VERSION.value}"
    mocked_responses.add(responses.PUT, url, status=status, json={"error": {"code": code, "message": "Failure"}})
    with pytest.raises(HttpResponseError):
        client.dataflow_endpoint.begin_create_or_update(
            resource_group_name="instance-rg", instance_name="instance", dataflow_endpoint_name="child",
            resource={"properties": {}},
        )
    assert [call.request.url for call in mocked_responses.calls] == [CAPABILITIES_URL, url]


@pytest.mark.parametrize("status", [400, 404])
def test_negotiation_exhaustion_remains_an_error(instances, mocked_responses, status):
    mocked_responses.add(responses.GET, CAPABILITIES_URL, json={"value": []})
    client = select_api(instances)
    versions = sorted(SUPPORTED_CHILD_API_VERSIONS, reverse=True)
    url = f"{BASE_URL}{INSTANCE_ID}/dataflowEndpoints/child?api-version="
    for version in versions:
        mocked_responses.add(
            responses.PUT, url + version, status=status,
            json={"error": {"code": "MissingAzureKubernetesMapping", "message": "Unsupported API"}},
        )
    with pytest.raises(HttpResponseError, match="MissingAzureKubernetesMapping"):
        client.dataflow_endpoint.begin_create_or_update(
            resource_group_name="instance-rg", instance_name="instance", dataflow_endpoint_name="child",
            resource={"properties": {}},
        )
    assert [call.request.url for call in mocked_responses.calls] == [CAPABILITIES_URL] + [url + v for v in versions]


@pytest.mark.parametrize("method,status,path,payload", [
    ("GET", 400, "/dataflowEndpoints/child", {"error": {"code": "MissingAzureKubernetesMapping"}}),
    ("DELETE", 400, "/dataflowEndpoints/child", {"error": {"code": "MissingAzureKubernetesMapping"}}),
    ("PUT", 400, "", {"error": {"code": "MissingAzureKubernetesMapping"}}),
    ("PUT", 202, "/dataflowEndpoints/child", {"status": "Accepted"}),
    ("PUT", 400, "/dataflowEndpoints/child", []),
    ("PUT", 400, "/dataflowEndpoints/child", {"error": "Malformed error"}),
])
def test_negotiation_preserves_non_rejected_or_non_child_operations(mocked_responses, method, status, path, payload):
    request = HttpRequest(
        method, f"{BASE_URL}{INSTANCE_ID}{path}?api-version={DEFAULT_IOTOPS_MGMT_API_VERSION.value}",
    )
    request.set_json_body({"properties": {}})
    mocked_responses.add(method, request.url, status=status, json=payload)
    with Pipeline(transport=RequestsTransport(), policies=[_ChildApiNegotiationPolicy()]) as pipeline:
        result = pipeline.run(request, retry_total=0)
    assert result.http_response.status_code == status
    assert len(mocked_responses.calls) == 1
    assert request.url.endswith(f"?api-version={DEFAULT_IOTOPS_MGMT_API_VERSION.value}")


@pytest.mark.parametrize("failure", [ServiceRequestError, ServiceResponseError])
@pytest.mark.parametrize("after_mapping_rejection", [False, True])
def test_negotiation_adds_no_transport_retries(mocker, mocked_responses, failure, after_mapping_rejection):
    error = failure("Interrupted")
    request = HttpRequest("PUT", f"{BASE_URL}{INSTANCE_ID}/dataflowEndpoints/child?api-version=2026-10-01")
    request.set_json_body({"properties": {}})
    transport = RequestsTransport()
    original_send = transport.send

    def send_or_fail(request, **kwargs):
        if after_mapping_rejection and request.url.endswith("api-version=2026-10-01"):
            return original_send(request, **kwargs)
        raise error

    if after_mapping_rejection:
        mocked_responses.add(
            responses.PUT, request.url, status=400,
            json={"error": {"code": "MissingAzureKubernetesMapping"}},
        )
    send = mocker.patch.object(transport, "send", side_effect=send_or_fail)
    with Pipeline(transport=transport, policies=[_ChildApiNegotiationPolicy()]) as pipeline:
        with pytest.raises(failure) as raised:
            pipeline.run(request, retry_total=10, retry_connect=0, retry_read=0)
    assert raised.value is error
    assert send.call_count == (2 if after_mapping_rejection else 1)
    expected_api = "2026-07-01" if after_mapping_rejection else "2026-10-01"
    assert request.url.endswith(f"api-version={expected_api}")


@pytest.mark.parametrize("bad_version", [123, "invalid", "2026-7-01", None, ["2026-07-01"]])
def test_malformed_metadata_falls_back_without_caching(instances, mocked_responses, bad_version):
    payload = enabled_types()
    payload["value"][0]["properties"]["typesMetadata"][-1]["apiVersion"] = bad_version
    mocked_responses.add(responses.GET, CAPABILITIES_URL, json=payload)
    client = select_api(instances)
    assert instances._child_api_location is None
    assert instances._child_api_capabilities == {}
    url = f"{BASE_URL}{INSTANCE_ID}/dataflowEndpoints/child?api-version="
    mocked_responses.add(
        responses.PUT, url + "2026-10-01", status=400,
        json={"error": {"code": "MissingAzureKubernetesMapping"}},
    )
    mocked_responses.add(responses.PUT, url + "2026-07-01", status=200, json={"name": "child"})
    assert client.dataflow_endpoint.begin_create_or_update(
        resource_group_name="instance-rg", instance_name="instance", dataflow_endpoint_name="child",
        resource={"properties": {}},
    ).result()["name"] == "child"
    assert [call.request.url for call in mocked_responses.calls] == [
        CAPABILITIES_URL, url + "2026-10-01", url + "2026-07-01",
    ]


@pytest.mark.parametrize("malformed", [
    None,
    {},
    {"properties": None},
    {"properties": False},
    {"properties": {}},
    {"properties": {"typesMetadata": False}},
    {"properties": {"typesMetadata": None}},
    {"properties": {"typesMetadata": {}}},
    {"properties": {"typesMetadata": ""}},
    {"properties": {"typesMetadata": [None]}},
    {"properties": {"typesMetadata": [{}]}},
    {"properties": {"typesMetadata": [{
        "resourceType": "instances/dataflowProfiles/dataflows", "apiVersion": "2026-07-01",
    }]}},
    {"properties": {"typesMetadata": [{"resourceProviderNamespace": False}]}},
    {"properties": {"typesMetadata": [{"resourceProviderNamespace": " "}]}},
])
def test_mixed_malformed_discovery_discards_partial_capabilities(instances, mocked_responses, malformed):
    payload = enabled_types(["instances/dataflowEndpoints"])
    payload["value"].append(malformed)
    mocked_responses.add(responses.GET, CAPABILITIES_URL, json=payload)

    client = select_api(instances, groups=IOTOPS_CHILD_RESOURCE_TYPES)

    assert instances._child_api_location is None
    assert instances._child_api_capabilities == {}
    url = f"{BASE_URL}{INSTANCE_ID}/dataflowEndpoints/child?api-version="
    mocked_responses.add(
        responses.PUT, url + "2026-10-01", status=400,
        json={"error": {"code": "MissingAzureKubernetesMapping"}},
    )
    mocked_responses.add(responses.PUT, url + "2026-07-01", status=200, json={"name": "child"})
    assert client.dataflow_endpoint.begin_create_or_update(
        resource_group_name="instance-rg", instance_name="instance", dataflow_endpoint_name="child",
        resource={"properties": {}},
    ).result()["name"] == "child"
    assert [call.request.url for call in mocked_responses.calls] == [
        CAPABILITIES_URL, url + "2026-10-01", url + "2026-07-01",
    ]


def test_negotiation_does_not_reset_elapsed_timeout(mocked_responses, mocker):
    request = HttpRequest("PUT", f"{BASE_URL}{INSTANCE_ID}/dataflowEndpoints/child?api-version=2026-10-01")
    request.set_json_body({"properties": {}})
    mocked_responses.add(
        responses.PUT, request.url, status=400, json={"error": {"code": "MissingAzureKubernetesMapping"}},
    )
    clock = mocker.Mock()
    clock.time.side_effect = [0, 2, 2, 2]
    mocker.patch("azure.core.pipeline.policies._retry.time", clock)
    with Pipeline(transport=RequestsTransport(), policies=[_ChildApiNegotiationPolicy()]) as pipeline:
        with pytest.raises(ServiceResponseTimeoutError):
            pipeline.run(request, timeout=1, retry_total=0)
    assert len(mocked_responses.calls) == 1


def test_negotiation_does_not_replenish_consumed_status_retries(mocked_responses):
    url = f"{BASE_URL}{INSTANCE_ID}/dataflowEndpoints/child?api-version="
    request = HttpRequest("PUT", url + "2026-10-01")
    request.set_json_body({"properties": {}})
    mocked_responses.add(responses.PUT, url + "2026-10-01", status=503, headers={"Retry-After": "0"})
    mocked_responses.add(
        responses.PUT, url + "2026-10-01", status=400,
        json={"error": {"code": "MissingAzureKubernetesMapping"}},
    )
    mocked_responses.add(responses.PUT, url + "2026-07-01", status=503, headers={"Retry-After": "0"})
    with Pipeline(transport=RequestsTransport(), policies=[_ChildApiNegotiationPolicy()]) as pipeline:
        result = pipeline.run(request, retry_total=10, retry_status=1)
    assert result.http_response.status_code == 503
    assert [call.request.url for call in mocked_responses.calls] == [
        url + "2026-10-01", url + "2026-10-01", url + "2026-07-01",
    ]


@pytest.mark.parametrize("retry_total", [0, 1])
def test_negotiation_preserves_sdk_retry_budget(instances, mocked_responses, retry_total):
    mocked_responses.add(responses.GET, CAPABILITIES_URL, json={"value": []})
    client = select_api(instances)
    url = f"{BASE_URL}{INSTANCE_ID}/dataflowEndpoints/child?api-version="
    mocked_responses.add(
        responses.PUT, url + DEFAULT_IOTOPS_MGMT_API_VERSION.value, status=400,
        json={"error": {"code": "MissingAzureKubernetesMapping"}},
    )
    mocked_responses.add(
        responses.PUT, url + "2026-07-01", status=503, headers={"Retry-After": "0"},
        json={"error": {"code": "ServiceUnavailable"}},
    )
    if retry_total:
        mocked_responses.add(
            responses.PUT, url + "2026-07-01", status=200,
            json={"name": "child", "properties": {"provisioningState": "Succeeded"}},
        )
        assert client.dataflow_endpoint.begin_create_or_update(
            resource_group_name="instance-rg", instance_name="instance", dataflow_endpoint_name="child",
            resource={"properties": {}}, retry_total=retry_total,
        ).result()["name"] == "child"
    else:
        with pytest.raises(HttpResponseError, match="ServiceUnavailable"):
            client.dataflow_endpoint.begin_create_or_update(
                resource_group_name="instance-rg", instance_name="instance", dataflow_endpoint_name="child",
                resource={"properties": {}}, retry_total=retry_total,
            )
    assert [call.request.url for call in mocked_responses.calls] == [
        CAPABILITIES_URL, url + DEFAULT_IOTOPS_MGMT_API_VERSION.value,
    ] + [url + "2026-07-01"] * (1 + retry_total)


@pytest.mark.parametrize("cloud_name,endpoint", [
    ("AzureUSGovernment", "https://management.usgovcloudapi.net"),
    ("AzureChinaCloud", "https://management.chinacloudapi.cn"),
])
def test_negotiated_put_preserves_cloud_subscription_and_payload(
    mocked_cmd, mocked_responses, mocked_azcli_cred_get_token, cloud_name, endpoint,
):
    mocked_cmd.cli_ctx.cloud = build_mock_cmd_for_cloud(cloud_name).cli_ctx.cloud
    mocked_azcli_cred_get_token.reset_mock()
    capability_url = CAPABILITIES_URL.replace(BASE_URL, endpoint)
    mocked_responses.add(
        responses.GET, capability_url, status=403, json={"error": {"code": "AuthorizationFailed"}},
    )
    child_url = f"{endpoint}{INSTANCE_ID}/dataflowEndpoints/child?api-version="
    mocked_responses.add(
        responses.PUT, child_url + DEFAULT_IOTOPS_MGMT_API_VERSION.value, status=400,
        json={"error": {"code": "MissingAzureKubernetesMapping"}},
    )
    mocked_responses.add(
        responses.PUT, child_url + "2026-07-01", status=200,
        json={"name": "child", "properties": {"provisioningState": "Succeeded"}},
    )
    client = select_api(Instances(mocked_cmd))
    payload = {"properties": {"endpointType": "Mqtt"}}
    result = client.dataflow_endpoint.begin_create_or_update(
        resource_group_name="instance-rg", instance_name="instance", dataflow_endpoint_name="child", resource=payload,
    ).result()
    assert result["name"] == "child"
    assert [call.request.url for call in mocked_responses.calls] == [
        capability_url, child_url + DEFAULT_IOTOPS_MGMT_API_VERSION.value, child_url + "2026-07-01",
    ]
    assert all(
        json.loads(call.request.body) == payload for call in mocked_responses.calls if call.request.method == "PUT"
    )
    assert mocked_azcli_cred_get_token.call_args_list
    assert all(call.args == (f"{endpoint}/.default",) for call in mocked_azcli_cred_get_token.call_args_list)
