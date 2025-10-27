# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import re
from unittest.mock import Mock

import pytest
import responses
from azure.cli.core.azclierror import AzureResponseError

from azext_edge.edge.commands_edge import enable_rsync
from azext_edge.edge.providers.orchestration.resources.sync_rules import K8_BRIDGE_APP_ID
from azext_edge.edge.providers.orchestration.common import KUBERNETES_ARC_CONTRIBUTOR_ROLE_ID

from ....generators import generate_random_string, generate_role_def_id, generate_uuid
from .conftest import ZEROED_SUBSCRIPTION, append_role_assignment_endpoint
from .test_custom_locations_unit import get_custom_location_endpoint, get_mock_custom_location_record
from .test_instances_unit import get_instance_endpoint, get_mock_instance_record


def get_sp_fetch_endpoint() -> str:
    return f"https://graph.microsoft.com/v1.0/servicePrincipals(appId='{K8_BRIDGE_APP_ID}')"


@pytest.fixture
def mocked_logger(mocker):
    yield mocker.patch("azext_edge.edge.providers.orchestration.resources.sync_rules.logger", autospec=True)


@pytest.fixture
def setup_base_mocks(mocked_responses):
    def _setup(instance_name: str, resource_group_name: str, cl_name: str):
        instance_endpoint = get_instance_endpoint(resource_group_name=resource_group_name, instance_name=instance_name)
        mocked_responses.add(
            method=responses.GET,
            url=instance_endpoint,
            json=get_mock_instance_record(
                name=instance_name,
                resource_group_name=resource_group_name,
                cl_name=cl_name,
            ),
            status=200,
        )

        cl_endpoint = get_custom_location_endpoint(
            resource_group_name=resource_group_name, custom_location_name=cl_name
        )
        cl_payload = get_mock_custom_location_record(name=cl_name, resource_group_name=resource_group_name)
        mocked_responses.add(
            method=responses.GET,
            url=cl_endpoint,
            json=cl_payload,
            status=200,
        )
        return cl_endpoint, cl_payload

    return _setup


@pytest.mark.parametrize(
    "sp_scenario",
    [
        {"sp_lookup_code": 200, "expect_ra": True},
        {"sp_lookup_code": 401, "expect_ra": False},
        {"sp_lookup_code": 404, "expect_ra": False},
        {"k8_bridge_sp_oid": generate_uuid(), "expect_ra": True},
    ],
)
@pytest.mark.parametrize("use_custom_role", [False, True])
def test_sync_rules_enable(
    mocked_cmd,
    mocked_logger: Mock,
    mocked_responses: responses,
    setup_base_mocks,
    sp_scenario: dict,
    use_custom_role: bool,
):
    """Test sync rules enablement across SP lookup and role assignment scenarios."""
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    cl_name = generate_random_string()

    default_k8_bridge_sp_oid = generate_uuid()
    user_k8_bridge_sp_oid = sp_scenario.get("k8_bridge_sp_oid")
    sp_lookup_code = sp_scenario.get("sp_lookup_code", 200)
    expect_ra = sp_scenario.get("expect_ra", True)
    target_k8_bridge_sp_oid = user_k8_bridge_sp_oid or default_k8_bridge_sp_oid

    custom_role_id = (
        generate_role_def_id(role_id=generate_uuid(), subscription_id=ZEROED_SUBSCRIPTION) if use_custom_role else None
    )

    cl_endpoint, cl_payload = setup_base_mocks(instance_name, resource_group_name, cl_name)

    if not user_k8_bridge_sp_oid:
        sp_get = mocked_responses.add(
            method=responses.GET,
            url=get_sp_fetch_endpoint(),
            json={"id": default_k8_bridge_sp_oid, "appId": K8_BRIDGE_APP_ID} if sp_lookup_code == 200 else {},
            status=sp_lookup_code,
        )

    if expect_ra:
        expected_role_def_id = custom_role_id or generate_role_def_id(
            role_id=KUBERNETES_ARC_CONTRIBUTOR_ROLE_ID, subscription_id=ZEROED_SUBSCRIPTION
        )

        ra_get_endpoint = append_role_assignment_endpoint(
            resource_endpoint=cl_endpoint, filter_query=f"principalId eq '{target_k8_bridge_sp_oid}'"
        )
        ra_get = mocked_responses.add(
            method=responses.GET,
            url=ra_get_endpoint,
            json={"value": []},
            status=200,
        )

        ra_put_endpoint = append_role_assignment_endpoint(cl_endpoint, ".*")
        ra_put = mocked_responses.add(
            method=responses.PUT,
            url=re.compile(ra_put_endpoint),
            json={
                "id": generate_uuid(),
                "properties": {"principalId": target_k8_bridge_sp_oid, "roleDefinitionId": expected_role_def_id},
            },
            status=200,
        )

    result = enable_rsync(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        custom_role_id=custom_role_id,
        k8_bridge_sp_oid=user_k8_bridge_sp_oid,
    )

    if not user_k8_bridge_sp_oid:
        assert sp_get.call_count == 1
        if sp_lookup_code != 200:
            mocked_logger.warning.assert_called_once()
            assert result is None
            return

    if expect_ra:
        assert ra_get.call_count == 1
        assert ra_put.call_count == 1
        ra_put_json = json.loads(ra_put.calls[0].request.body)
        assert ra_put_json["properties"]["roleDefinitionId"] == expected_role_def_id
        assert ra_put_json["properties"]["principalId"] == target_k8_bridge_sp_oid
        assert ra_put_json["properties"]["principalType"] == "ServicePrincipal"
        assert result is not None
        mocked_logger.info.assert_called_with(
            "Role assignment %s for K8 Bridge service principal on custom location '%s'.",
            "successfully created",
            cl_payload["name"],
        )


@pytest.mark.parametrize("existing_ra", [False, True])
def test_sync_rules_enable_existing_assignment(
    mocked_cmd,
    mocked_logger: Mock,
    mocked_responses: responses,
    setup_base_mocks,
    existing_ra: bool,
):
    """Test sync rules enablement behavior with existing role assignments."""
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    cl_name = generate_random_string()
    k8_bridge_sp_oid = generate_uuid()

    cl_endpoint, cl_payload = setup_base_mocks(instance_name, resource_group_name, cl_name)

    expected_role_def_id = generate_role_def_id(
        role_id=KUBERNETES_ARC_CONTRIBUTOR_ROLE_ID, subscription_id=ZEROED_SUBSCRIPTION
    )

    ra_get_endpoint = append_role_assignment_endpoint(
        resource_endpoint=cl_endpoint, filter_query=f"principalId eq '{k8_bridge_sp_oid}'"
    )
    ra_get = mocked_responses.add(
        method=responses.GET,
        url=ra_get_endpoint,
        json={
            "value": (
                [
                    {
                        "id": generate_uuid(),
                        "properties": {
                            "principalId": k8_bridge_sp_oid,
                            "roleDefinitionId": expected_role_def_id,
                        },
                    }
                ]
                if existing_ra
                else []
            )
        },
        status=200,
    )

    if not existing_ra:
        ra_put_endpoint = append_role_assignment_endpoint(cl_endpoint, ".*")
        ra_put = mocked_responses.add(
            method=responses.PUT,
            url=re.compile(ra_put_endpoint),
            json={
                "id": generate_uuid(),
                "properties": {"principalId": k8_bridge_sp_oid, "roleDefinitionId": expected_role_def_id},
            },
            status=200,
        )

    result = enable_rsync(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        k8_bridge_sp_oid=k8_bridge_sp_oid,
    )

    assert ra_get.call_count == 1

    if existing_ra:
        assert result is None
        mocked_logger.info.assert_called_with(
            "Role assignment %s for K8 Bridge service principal on custom location '%s'.",
            "already exists",
            cl_payload["name"],
        )
    else:
        assert ra_put.call_count == 1
        assert result is not None
        mocked_logger.info.assert_called_with(
            "Role assignment %s for K8 Bridge service principal on custom location '%s'.",
            "successfully created",
            cl_payload["name"],
        )


def test_sync_rules_enable_role_assignment_error(
    mocked_cmd,
    mocked_responses: responses,
    setup_base_mocks,
):
    """Test sync rules enablement when role assignment creation fails."""
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    cl_name = generate_random_string()
    k8_bridge_sp_oid = generate_uuid()

    cl_endpoint, cl_payload = setup_base_mocks(instance_name, resource_group_name, cl_name)

    mocked_responses.add(
        method=responses.GET,
        url=append_role_assignment_endpoint(
            resource_endpoint=cl_endpoint, filter_query=f"principalId eq '{k8_bridge_sp_oid}'"
        ),
        json={"value": []},
        status=200,
    )

    mocked_responses.add(
        method=responses.PUT,
        url=re.compile(append_role_assignment_endpoint(cl_endpoint, ".*")),
        json={"error": {"message": "Forbidden"}},
        status=403,
    )

    with pytest.raises(AzureResponseError) as exc_info:
        enable_rsync(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            k8_bridge_sp_oid=k8_bridge_sp_oid,
        )

    error_msg = str(exc_info.value)
    assert all(
        text in error_msg
        for text in ["K8 Bridge", K8_BRIDGE_APP_ID, "Azure Kubernetes Service Arc Contributor Role", cl_payload["id"]]
    )
