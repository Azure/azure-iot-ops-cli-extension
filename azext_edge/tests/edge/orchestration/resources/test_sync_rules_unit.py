# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


import re
import json
from typing import Optional, Dict
from unittest.mock import Mock

import pytest
import responses

from azext_edge.edge.providers.orchestration.resources.sync_rules import (
    K8_BRIDGE_APP_ID,
    KUBERNETES_ARC_CONTRIBUTOR_ROLE_ID,
    ADR_PROVIDER,
    OPS_PROVIDER,
)
from azext_edge.edge.commands_edge import enable_rsync, list_rsync, disable_rsync

from ....generators import generate_random_string, generate_uuid, generate_role_def_id
from .conftest import (
    ZEROED_SUBSCRIPTION,
    append_role_assignment_endpoint,
    get_base_endpoint,
    get_mock_resource,
)
from .test_custom_locations_unit import (
    get_custom_location_endpoint,
    get_mock_custom_location_record,
)
from .test_instances_unit import get_instance_endpoint, get_mock_instance_record

RESOURCE_SYNC_RP = "Microsoft.ExtendedLocation"
RESOURCE_SYNC_API_VERSION = "2021-08-31-preview"

EXPECTED_SELECTORS = {
    ADR_PROVIDER: {
        "matchExpressions": [
            {
                "key": "management.azure.com/provider-name",
                "operator": "In",
                "values": [ADR_PROVIDER, ADR_PROVIDER.lower()],
            }
        ]
    },
    OPS_PROVIDER: {
        "matchExpressions": [
            {
                "key": "management.azure.com/provider-name",
                "operator": "In",
                "values": [OPS_PROVIDER, OPS_PROVIDER.lower()],
            }
        ]
    },
}


def get_sync_rule_endpoint(resource_group_name: str, cl_name: str, rule_name: Optional[str] = None) -> str:
    resource_path = f"/customLocations/{cl_name}/resourceSyncRules"
    if rule_name:
        resource_path += f"/{rule_name}"
    return get_base_endpoint(
        resource_group_name=resource_group_name,
        resource_path=resource_path,
        resource_provider=RESOURCE_SYNC_RP,
        api_version=RESOURCE_SYNC_API_VERSION,
    )


def get_mock_sync_rule_record(name: str, resource_group_name: str, provider: str, priority: int = 400) -> dict:
    resource = get_mock_resource(
        name=name,
        properties={
            "priority": priority,
            "provisioningState": "Succeeded",
            "selector": EXPECTED_SELECTORS[provider],
            "targetResourceGroup": f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{resource_group_name}",
        },
        resource_group_name=resource_group_name,
        qualified_type=f"{RESOURCE_SYNC_RP}/customLocations/resourceSyncRules",
    )

    return resource


def get_sp_fetch_endpoint() -> str:
    return f"https://graph.microsoft.com/v1.0/servicePrincipals(appId='{K8_BRIDGE_APP_ID}')"


@pytest.fixture
def mocked_logger(mocker):
    yield mocker.patch("azext_edge.edge.providers.orchestration.resources.sync_rules.logger", autospec=True)


@pytest.fixture
def mocked_logger_queryable(mocker):
    yield mocker.patch("azext_edge.edge.util.queryable.logger", autospec=True)


@pytest.mark.parametrize(
    "role_assignment_scenario",
    [{}, {"sp_lookup_code": 401}, {"k8_bridge_sp_oid": generate_uuid()}, {"skip_role_assignments": True}],
)
@pytest.mark.parametrize(
    "tags",
    [None, {generate_random_string(): generate_random_string(), generate_random_string(): generate_random_string()}],
)
@pytest.mark.parametrize(
    "custom_role_id",
    [None, generate_uuid()],
)
@pytest.mark.parametrize(
    "rule_name_map",
    [{}, {"adr": generate_random_string(), "ops": generate_random_string()}],
)
@pytest.mark.parametrize(
    "rule_pri_map",
    [{}, {"adr": 123, "ops": 456}],
)
def test_sync_rules_enable(
    mocked_cmd,
    mocked_logger: Mock,
    mocked_logger_queryable: Mock,
    mocked_responses: responses,
    tags: Optional[dict],
    role_assignment_scenario: dict,
    custom_role_id: Optional[str],
    rule_name_map: Dict[str, str],
    rule_pri_map: Dict[str, int],
):
    cl_name = generate_random_string()
    resource_group_name = generate_random_string()
    default_k8_bridge_sp_oid = generate_uuid()

    skip_role_assignments = role_assignment_scenario.get("skip_role_assignments")
    user_k8_bridge_sp_oid = role_assignment_scenario.get("k8_bridge_sp_oid")
    sp_lookup_code = role_assignment_scenario.get("sp_lookup_code", 200)
    target_k8_bridge_sp_oid = user_k8_bridge_sp_oid or default_k8_bridge_sp_oid

    rule_adr_pri = rule_pri_map.get("adr", 200)
    rule_ops_pri = rule_pri_map.get("ops", 400)
    rule_adr_name = rule_name_map.get("adr")
    rule_ops_name = rule_name_map.get("ops")

    # Instance fetch mock
    instance_name = generate_random_string()
    instance_endpoint = get_instance_endpoint(resource_group_name=resource_group_name, instance_name=instance_name)
    instance_record = get_mock_instance_record(
        name=instance_name,
        resource_group_name=resource_group_name,
        cl_name=cl_name,
    )
    mocked_responses.add(
        method=responses.GET,
        url=instance_endpoint,
        json=instance_record,
        status=200,
        content_type="application/json",
    )

    # Custom location fetch mock
    cl_endpoint = get_custom_location_endpoint(resource_group_name=resource_group_name, custom_location_name=cl_name)
    cl_payload = get_mock_custom_location_record(name=cl_name, resource_group_name=resource_group_name)
    mocked_responses.add(
        method=responses.GET,
        url=cl_endpoint,
        json=cl_payload,
        status=200,
        content_type="application/json",
    )

    # Role assignment fetch mock
    if not skip_role_assignments:
        fails_sp_lookup = sp_lookup_code != 200
        if not user_k8_bridge_sp_oid:
            # Fetch SP OID if not provided
            sp_get = mocked_responses.add(
                method=responses.GET,
                url=get_sp_fetch_endpoint(),
                json={"id": default_k8_bridge_sp_oid, "appId": K8_BRIDGE_APP_ID},
                status=sp_lookup_code,
                content_type="application/json",
            )
        if not fails_sp_lookup:
            ra_get_endpoint = append_role_assignment_endpoint(
                resource_endpoint=cl_endpoint, filter_query=f"principalId eq '{target_k8_bridge_sp_oid}'"
            )
            ra_get = mocked_responses.add(
                method=responses.GET,
                url=ra_get_endpoint,
                json={"value": []},
                status=200,
                content_type="application/json",
            )
            ra_put_endpoint = append_role_assignment_endpoint(resource_endpoint=cl_endpoint, ra_name=".*")
            ra_put = mocked_responses.add(
                method=responses.PUT,
                url=re.compile(ra_put_endpoint),
                json={},
                status=200,
                content_type="application/json",
            )

    expected_rule_adr_name = rule_adr_name or f"{cl_name}-adr-sync"
    expected_rule_ops_name = rule_ops_name or f"{cl_name}-aio-sync"
    adr_rule_payload = get_mock_sync_rule_record(
        name=expected_rule_adr_name, resource_group_name=resource_group_name, provider=ADR_PROVIDER
    )
    ops_rule_payload = get_mock_sync_rule_record(
        name=expected_rule_ops_name, resource_group_name=resource_group_name, provider=OPS_PROVIDER
    )
    sync_rule_adr_put = mocked_responses.add(
        method=responses.PUT,
        url=get_sync_rule_endpoint(
            resource_group_name=resource_group_name, cl_name=cl_name, rule_name=expected_rule_adr_name
        ),
        json=adr_rule_payload,
        status=200,
        content_type="application/json",
    )
    sync_rule_ops_put = mocked_responses.add(
        method=responses.PUT,
        url=get_sync_rule_endpoint(
            resource_group_name=resource_group_name, cl_name=cl_name, rule_name=expected_rule_ops_name
        ),
        json=ops_rule_payload,
        status=200,
        content_type="application/json",
    )

    result = enable_rsync(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        skip_role_assignments=skip_role_assignments,
        custom_role_id=custom_role_id,
        k8_bridge_sp_oid=user_k8_bridge_sp_oid,
        rule_adr_name=rule_adr_name,
        rule_ops_name=rule_ops_name,
        rule_adr_pri=rule_adr_pri,
        rule_ops_pri=rule_ops_pri,
        tags=tags,
        wait_sec=0.1,
    )
    assert result == [ops_rule_payload, adr_rule_payload]

    if not skip_role_assignments:
        assert_ra_flow = True
        if not user_k8_bridge_sp_oid:
            assert sp_get.call_count == 1
            mocked_logger_queryable.debug.call_args_list[0].assert_called_once_with(
                "Using aud: https://graph.microsoft.com"
            )
            if sp_lookup_code != 200:
                mocked_logger.warning.assert_called_once_with(
                    "Unable to query K8 Bridge service principal and OID not provided via parameter. "
                    "Skipping role assignment."
                )
                assert_ra_flow = False
        if assert_ra_flow:
            assert ra_get.call_count == 1
            assert ra_put.call_count == 1
            ra_put_json = json.loads(ra_put.calls[0].request.body)
            expected_role_def_id = custom_role_id or generate_role_def_id(
                role_id=KUBERNETES_ARC_CONTRIBUTOR_ROLE_ID, subscription_id=ZEROED_SUBSCRIPTION
            )
            assert ra_put_json["properties"]["roleDefinitionId"] == expected_role_def_id
            assert ra_put_json["properties"]["principalId"] == target_k8_bridge_sp_oid
            assert ra_put_json["properties"]["principalType"] == "ServicePrincipal"

    sync_rule_adr_put.call_count == 1
    sync_rule_adr_put_json = json.loads(sync_rule_adr_put.calls[0].request.body)
    assert sync_rule_adr_put_json["properties"]["targetResourceGroup"] == (
        f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{resource_group_name}"
    )
    assert sync_rule_adr_put_json["properties"]["priority"] == rule_adr_pri
    assert sync_rule_adr_put_json["properties"]["selector"] == EXPECTED_SELECTORS[ADR_PROVIDER]

    sync_rule_ops_put.call_count == 1
    sync_rule_ops_put_json = json.loads(sync_rule_ops_put.calls[0].request.body)
    assert sync_rule_ops_put_json["properties"]["targetResourceGroup"] == (
        f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{resource_group_name}"
    )
    assert sync_rule_ops_put_json["properties"]["priority"] == rule_ops_pri
    assert sync_rule_ops_put_json["properties"]["selector"] == EXPECTED_SELECTORS[OPS_PROVIDER]
    if tags:
        assert sync_rule_ops_put_json["tags"] == tags
        assert sync_rule_adr_put_json["tags"] == tags


@pytest.mark.parametrize(
    "rules_count",
    [0, 2],
)
def test_sync_rules_list(mocked_cmd, mocked_responses: responses, rules_count: int):
    cl_name = generate_random_string()
    resource_group_name = generate_random_string()

    # Instance fetch mock
    instance_name = generate_random_string()
    instance_endpoint = get_instance_endpoint(resource_group_name=resource_group_name, instance_name=instance_name)
    instance_record = get_mock_instance_record(
        name=instance_name,
        resource_group_name=resource_group_name,
        cl_name=cl_name,
    )
    mocked_responses.add(
        method=responses.GET,
        url=instance_endpoint,
        json=instance_record,
        status=200,
        content_type="application/json",
    )

    # Custom location fetch mock
    cl_endpoint = get_custom_location_endpoint(resource_group_name=resource_group_name, custom_location_name=cl_name)
    cl_payload = get_mock_custom_location_record(name=cl_name, resource_group_name=resource_group_name)
    mocked_responses.add(
        method=responses.GET,
        url=cl_endpoint,
        json=cl_payload,
        status=200,
        content_type="application/json",
    )

    rules_payload = []
    for _ in range(rules_count):
        rules_payload.append(
            get_mock_sync_rule_record(
                name=generate_random_string(),
                resource_group_name=resource_group_name,
            )
        )
    mocked_responses.add(
        method=responses.GET,
        url=get_sync_rule_endpoint(resource_group_name=resource_group_name, cl_name=cl_name),
        json={"value": rules_payload},
        status=200,
        content_type="application/json",
    )
    result = list(
        list_rsync(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )
    )
    assert result == rules_payload


@pytest.mark.parametrize(
    "rules_count",
    [0, 2],
)
def test_sync_rules_disable(mocked_cmd, mocked_logger: Mock, mocked_responses: responses, rules_count: int):
    cl_name = generate_random_string()
    resource_group_name = generate_random_string()

    # Instance fetch mock
    instance_name = generate_random_string()
    instance_endpoint = get_instance_endpoint(resource_group_name=resource_group_name, instance_name=instance_name)
    instance_record = get_mock_instance_record(
        name=instance_name,
        resource_group_name=resource_group_name,
        cl_name=cl_name,
    )
    mocked_responses.add(
        method=responses.GET,
        url=instance_endpoint,
        json=instance_record,
        status=200,
        content_type="application/json",
    )

    # Custom location fetch mock
    cl_endpoint = get_custom_location_endpoint(resource_group_name=resource_group_name, custom_location_name=cl_name)
    cl_payload = get_mock_custom_location_record(name=cl_name, resource_group_name=resource_group_name)
    mocked_responses.add(
        method=responses.GET,
        url=cl_endpoint,
        json=cl_payload,
        status=200,
        content_type="application/json",
    )

    rules_payload = []
    for i in range(rules_count):
        rules_payload.append(
            get_mock_sync_rule_record(
                name=generate_random_string(),
                resource_group_name=resource_group_name,
            )
        )
    mocked_responses.add(
        method=responses.GET,
        url=get_sync_rule_endpoint(resource_group_name=resource_group_name, cl_name=cl_name),
        json={"value": rules_payload},
        status=200,
        content_type="application/json",
    )

    sync_rule_deletes = []
    for rule in rules_payload:
        sync_rule_deletes.append(
            mocked_responses.add(
                method=responses.DELETE,
                url=get_sync_rule_endpoint(
                    resource_group_name=resource_group_name, cl_name=cl_name, rule_name=rule["name"]
                ),
                status=200,
            )
        )

    disable_rsync(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=True,
    )
    rules_payload_len = len(rules_payload)
    if not rules_payload_len:
        mocked_logger.warning.assert_called_once_with(f"No resource sync rules found for instance '{instance_name}'.")

    for i in range(rules_payload_len):
        rule = rules_payload[i]
        sync_rule_delete = sync_rule_deletes[i]
        assert sync_rule_delete.call_count == 1
