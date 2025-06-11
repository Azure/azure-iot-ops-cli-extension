# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


import json
import re
from typing import Optional
from unittest.mock import Mock

import pytest
import responses
from azure.cli.core.azclierror import InvalidArgumentValueError, ValidationError

from azext_edge.edge.commands_edge import list_instances, show_instance, update_instance
from azext_edge.edge.commands_secretsync import secretsync_enable
from azext_edge.edge.providers.orchestration.resources import Instances
from azext_edge.edge.providers.orchestration.resources.instances import (
    KEYVAULT_ROLE_ID_READER,
    KEYVAULT_ROLE_ID_SECRETS_USER,
    SERVICE_ACCOUNT_SECRETSYNC,
    get_fc_name,
    get_spc_name,
    parse_feature_kvp_nargs,
)

from ....generators import (
    generate_random_string,
    generate_resource_id,
    generate_role_def_id,
    generate_uuid,
)
from .conftest import (
    ARG_ENDPOINT,
    BASE_URL,
    ZEROED_SUBSCRIPTION,
    append_role_assignment_endpoint,
    get_base_endpoint,
    get_mock_resource,
    get_resource_id,
)
from .test_clusters_unit import get_cluster_url, get_federated_creds_url
from .test_custom_locations_unit import (
    get_custom_location_endpoint,
    get_mock_custom_location_record,
)
from .test_secretsync_spcs_unit import get_mock_spc_record, get_spc_endpoint

CONNECTED_CLUSTER_RP = "Microsoft.Kubernetes"
KEYVAULT_RP = "Microsoft.KeyVault"
KEYVAULT_API_VERSION = "2022-07-01"
UAMI_RP = "Microsoft.ManagedIdentity"
UAMI_API_VERSION = "2023-01-31"


@pytest.fixture
def mocked_get_tenant_id(mocker):
    yield mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.instances.get_tenant_id",
        return_value=generate_random_string(),
    )


def get_instance_endpoint(resource_group_name: Optional[str] = None, instance_name: Optional[str] = None) -> str:
    resource_path = "/instances"
    if instance_name:
        resource_path += f"/{instance_name}"
    return get_base_endpoint(resource_group_name=resource_group_name, resource_path=resource_path)


# TODO: Find out where this and related KV collateral belongs
def get_kv_endpoint(resource_group_name: Optional[str] = None, kv_name: Optional[str] = None) -> str:
    resource_path = "/keyvaults"
    if kv_name:
        resource_path += f"/{kv_name}"
    return get_base_endpoint(
        resource_group_name=resource_group_name,
        resource_path=resource_path,
        resource_provider=KEYVAULT_RP,
        api_version=KEYVAULT_API_VERSION,
    )


# TODO: Find out where this and related UAMI collateral belongs
def get_uami_endpoint(resource_group_name: Optional[str] = None, uami_name: Optional[str] = None) -> str:
    resource_path = "/userAssignedIdentities"
    if uami_name:
        resource_path += f"/{uami_name}"
    return get_base_endpoint(
        resource_group_name=resource_group_name,
        resource_path=resource_path,
        resource_provider=UAMI_RP,
        api_version=UAMI_API_VERSION,
    )


def get_uami_id_map(resource_group_name: str) -> dict:
    return {
        f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{resource_group_name}"
        f"/providers/Microsoft.ManagedIdentity/userAssignedIdentities/{generate_random_string()}": {
            "clientId": generate_random_string(),
            "principalId": generate_random_string(),
        }
    }


def get_mock_instance_record(
    name: str,
    resource_group_name: str,
    description: Optional[str] = None,
    tags: Optional[dict] = None,
    features: Optional[dict] = None,
    cl_name: Optional[str] = None,
    schema_registry_name: Optional[str] = None,
    version: Optional[str] = None,
    identity_map: Optional[dict] = None,
) -> dict:
    properties = {
        "provisioningState": "Succeeded",
        "schemaRegistryRef": {
            "resourceId": (
                f"/subscriptions/{ZEROED_SUBSCRIPTION}"
                f"/resourceGroups/{resource_group_name}/providers/Microsoft.DeviceRegistry"
                f"/schemaRegistries/{schema_registry_name or 'myschemaregistry'}"
            )
        },
        "version": version or "1.1.15",
    }
    if description:
        properties["description"] = description
    if features:
        properties["features"] = features

    kwargs = {}
    if cl_name:
        kwargs["custom_location_name"] = cl_name
    if identity_map:
        kwargs["identity"] = {
            "type": "UserAssigned",
            "userAssignedIdentities": identity_map,
        }

    return get_mock_resource(
        name=name,
        resource_path=f"/instances/{name}",
        properties=properties,
        resource_group_name=resource_group_name,
        tags=tags,
        **kwargs,
    )


def get_mock_cl_record(name: str, resource_group_name: str) -> dict:
    resource = get_mock_resource(
        name=name,
        properties={
            "hostResourceId": get_resource_id(
                resource_path="/connectedClusters/mycluster",
                resource_group_name=resource_group_name,
                resource_provider=CONNECTED_CLUSTER_RP,
            ),
            "namespace": "azure-iot-operations",
            "displayName": generate_random_string(),
            "provisioningState": "Succeeded",
            "clusterExtensionIds": [
                generate_random_string(),
                generate_random_string(),
            ],
            "authentication": {},
        },
        resource_group_name=resource_group_name,
    )
    resource.pop("extendedLocation")
    resource.pop("systemData")
    resource.pop("resourceGroup")
    return resource


def test_instance_show(mocked_cmd, mocked_responses: responses):
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_instance_record = get_mock_instance_record(name=instance_name, resource_group_name=resource_group_name)
    mocked_responses.add(
        method=responses.GET,
        url=get_instance_endpoint(resource_group_name=resource_group_name, instance_name=instance_name),
        json=mock_instance_record,
        status=200,
        content_type="application/json",
    )

    result = show_instance(cmd=mocked_cmd, instance_name=instance_name, resource_group_name=resource_group_name)

    assert result == mock_instance_record
    assert len(mocked_responses.calls) == 1


def test_instance_get_resource_map(mocker, mocked_cmd, mocked_responses: responses):
    cl_name = generate_random_string()
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_instance_record = get_mock_instance_record(name=instance_name, resource_group_name=resource_group_name)
    mock_cl_record = get_mock_cl_record(name=cl_name, resource_group_name=resource_group_name)

    mocked_responses.add(
        method=responses.GET,
        url=f"{BASE_URL}{mock_instance_record['extendedLocation']['name']}",
        json=mock_cl_record,
        status=200,
        content_type="application/json",
    )

    host_resource_id: str = mock_cl_record["properties"]["hostResourceId"]
    host_resource_parts = host_resource_id.split("/")

    instances = Instances(mocked_cmd)
    resource_map = instances.get_resource_map(mock_instance_record)
    assert resource_map.subscription_id == host_resource_parts[2]

    assert resource_map.connected_cluster.subscription_id == host_resource_parts[2]
    assert resource_map.connected_cluster.resource_group_name == host_resource_parts[4]
    assert resource_map.connected_cluster.cluster_name == host_resource_parts[-1]
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "resource_group_name",
    [None, generate_random_string()],
)
@pytest.mark.parametrize(
    "records",
    [0, 2],
)
def test_instance_list(mocked_cmd, mocked_responses: responses, resource_group_name: str, records: int):
    # If no resource_group_name, oh well
    mock_instance_records = {
        "value": [
            get_mock_instance_record(name=generate_random_string(), resource_group_name=resource_group_name)
            for _ in range(records)
        ]
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_instance_endpoint(resource_group_name=resource_group_name),
        json=mock_instance_records,
        status=200,
        content_type="application/json",
    )

    result = list(list_instances(cmd=mocked_cmd, resource_group_name=resource_group_name))

    assert result == mock_instance_records["value"]
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize(
    "description",
    [None, generate_random_string()],
)
@pytest.mark.parametrize(
    "tags",
    [None, {"a": "b", "c": "d"}, {}],
)
@pytest.mark.parametrize(
    "features_scenario",
    [
        {},
        {
            "inputs": ["connectors.settings.preview=Enabled"],
            "expected": {"connectors": {"settings": {"preview": "Enabled"}}},
        },
        {
            "inputs": ["connectors.settings.preview=Disabled"],
            "expected": {"connectors": {"settings": {"preview": "Disabled"}}},
        },
        {
            "inputs": ["connectors.settings.preview=Enabled", "connectors.settings.preview=Enabled"],
            "expected": {"connectors": {"settings": {"preview": "Enabled"}}},
        },
        {
            "inputs": ["connectors.settings.preview=Enabled", "connectors.settings.preview=Disabled"],
            "expected": {"connectors": {"settings": {"preview": "Disabled"}}},
        },
        {
            "inputs": ["connectors.settings.preview=Enabled", "connectors.settings.preview=Disabled"],
            "expected": {
                "connectors": {"settings": {"preview": "Disabled"}},
                "mqttBroker": {"settings": {"preview": "Enabled"}},
            },
            "initialState": {"mqttBroker": {"settings": {"preview": "Enabled"}}},
        },
    ],
)
def test_instance_update(
    mocked_cmd,
    mocked_responses: responses,
    description: Optional[str],
    tags: Optional[dict],
    features_scenario: Optional[dict],
):
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    instance_endpoint = get_instance_endpoint(resource_group_name=resource_group_name, instance_name=instance_name)

    initial_feat_state = features_scenario.get("initialState")
    initial_record = get_mock_instance_record(
        name=instance_name,
        resource_group_name=resource_group_name,
        features=initial_feat_state,
    )
    mocked_responses.add(
        method=responses.GET,
        url=instance_endpoint,
        json=initial_record,
        status=200,
        content_type="application/json",
    )
    updated_record = get_mock_instance_record(
        name=instance_name,
        resource_group_name=resource_group_name,
        description=description,
        tags=tags,
        features=features_scenario.get("expected"),
    )
    mocked_responses.add(
        method=responses.PUT,
        url=instance_endpoint,
        json=updated_record,
        status=200,
        content_type="application/json",
    )

    result = update_instance(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        tags=tags,
        instance_features=features_scenario.get("inputs"),
        instance_description=description,
        wait_sec=0,
    )
    assert len(mocked_responses.calls) == 2

    update_request = json.loads(mocked_responses.calls[1].request.body)
    if description:
        assert update_request["properties"]["description"] == description

    if tags or tags == {}:
        assert update_request["tags"] == tags

    if features_scenario:
        assert update_request["properties"]["features"] == features_scenario["expected"]

    assert update_request == updated_record
    assert result == updated_record


@pytest.mark.parametrize(
    "feature_scenario",
    [
        {"case": "No input handled."},
        {
            "case": "Single valid input handled.",
            "inputs": ["mqttBroker.mode=Stable"],
            "expected": {"mqttBroker": {"mode": "Stable"}},
        },
        {
            "case": "Multiple valid input for single component handled.",
            "inputs": ["mqttBroker.mode=Stable", "mqttBroker.settings.setting1=Enabled"],
            "expected": {"mqttBroker": {"mode": "Stable", "settings": {"setting1": "Enabled"}}},
        },
        {
            "case": "Multiple valid input for multiple components handled.",
            "inputs": ["mqttBroker.settings.setting1=Enabled", "adr.settings.setting1=Enabled"],
            "expected": {
                "mqttBroker": {"settings": {"setting1": "Enabled"}},
                "adr": {"settings": {"setting1": "Enabled"}},
            },
        },
        {
            "case": "Multiple valid input of distinct keys for multiple components handled.",
            "inputs": [
                "mqttBroker.mode=Preview",
                "mqttBroker.settings.setting1=Enabled",
                "adr.settings.setting1=Enabled",
            ],
            "expected": {
                "mqttBroker": {"mode": "Preview", "settings": {"setting1": "Enabled"}},
                "adr": {"settings": {"setting1": "Enabled"}},
            },
        },
        {
            "case": "Single invalid input.",
            "inputs": ["mqttBroker.settings.setting1=True"],
            "errors": [
                "mqttBroker.settings.setting1 has an invalid value.",
            ],
        },
        {
            "case": "Multiple invalid input with distinct reasons.",
            "inputs": ["mqttBroker.mode=True", "adr.settings.setting1=False", "adr.config.name=value"],
            "errors": [
                "mqttBroker.mode has an invalid value.",
                "adr.settings.setting1 has an invalid value.",
                "adr.config.name is invalid.",
            ],
        },
        {
            "case": "Mix of valid and invalid input to exercise only errors being raised.",
            "inputs": ["mqttBroker.settings.setting1=True", "adr.settings.setting1=Enabled", "adr.config.name=value"],
            "errors": ["mqttBroker.settings.setting1 has an invalid value.", "adr.config.name is invalid."],
        },
        {
            "case": "Strict mode constrains keys.",
            "inputs": ["connectors.settings.preview=Enabled"],
            "expected": {
                "connectors": {"settings": {"preview": "Enabled"}},
            },
            "strict": True,
        },
        {
            "case": "Strict mode constrains keys. Variant.",
            "inputs": ["connectors.settings.preview=Enabled", "connectors.settings.preview=Enabled"],
            "expected": {
                "connectors": {"settings": {"preview": "Enabled"}},
            },
            "strict": True,
        },
        {
            "case": "Strict mode constrains keys. Raise error on non-conformance.",
            "inputs": ["mqttBroker.settings.setting1=True", "adr.settings.setting1=Enabled"],
            "errors": ["Supported feature keys: connectors.settings.preview"],
            "strict": True,
        },
    ],
)
def test_parse_feature_kvp_nargs(feature_scenario: Optional[dict]):
    kwargs = {}
    strict = feature_scenario.get("strict")
    if strict:
        kwargs["strict"] = True

    errors = feature_scenario.get("errors", [])
    if errors:
        with pytest.raises(InvalidArgumentValueError) as exc:
            parse_feature_kvp_nargs(features=feature_scenario.get("inputs"), **kwargs)
        exc_str = str(exc.value)
        for e in errors:
            assert e in exc_str
        assert len(errors) == len(exc_str.split("\n")), f"Test error count mismatch:\n{exc_str}"
        return

    result = parse_feature_kvp_nargs(features=feature_scenario.get("inputs"), **kwargs)
    assert result == feature_scenario.get("expected", {}), f"Expectation failure for: {feature_scenario.get('case')}"


@pytest.mark.parametrize(
    "spc_name",
    [None, generate_random_string()],
)
@pytest.mark.parametrize(
    "skip_role_assignments",
    [None, True],
)
@pytest.mark.parametrize(
    "use_self_hosted_issuer",
    [None, True],
)
@pytest.mark.parametrize(
    "custom_role_id",
    [
        None,
        "/custom/role/id",
    ],
)
@pytest.mark.parametrize(
    "tags",
    [None, {generate_random_string(): generate_random_string(), generate_random_string(): generate_random_string()}],
)
def test_secretsync_enable(
    mocked_cmd,
    mocked_responses: responses,
    spc_name: Optional[str],
    skip_role_assignments: Optional[bool],
    use_self_hosted_issuer: Optional[bool],
    custom_role_id: Optional[str],
    tags: Optional[dict],
    mocked_get_tenant_id: Mock,
):
    oidc_issuer_def = {
        "oidcIssuerProfile": {
            "enabled": True,
            "selfHostedIssuerUrl": "https://localhost.selfHostedIssuer",
            "issuerUrl": "https://localhost.systemIssuer",
        },
        "securityProfile": {"workloadIdentity": {"enabled": True}},
    }

    resource_group_name = generate_random_string()

    # Instance fetch mock
    instance_name = generate_random_string()
    instance_endpoint = get_instance_endpoint(resource_group_name=resource_group_name, instance_name=instance_name)
    instance_record = get_mock_instance_record(
        name=instance_name,
        resource_group_name=resource_group_name,
    )
    mocked_responses.add(
        method=responses.GET,
        url=instance_endpoint,
        json=instance_record,
        status=200,
        content_type="application/json",
    )

    # KV fetch mock
    kv_name = generate_random_string()
    kv_endpoint = get_kv_endpoint(resource_group_name=resource_group_name, kv_name=kv_name)
    mocked_responses.add(
        method=responses.GET,
        url=kv_endpoint,
        json={},
        status=200,
        content_type="application/json",
    )
    keyvault_resource_id = generate_resource_id(
        resource_group_name=resource_group_name,
        resource_provider="Microsoft.KeyVault",
        resource_path=f"/keyvaults/{kv_name}",
    )

    # UAMI fetch mock
    uami_name = generate_random_string()
    uami_endpoint = get_uami_endpoint(resource_group_name=resource_group_name, uami_name=uami_name)
    uami_resource_id = generate_resource_id(
        resource_group_name=resource_group_name,
        resource_provider="Microsoft.ManagedIdentity",
        resource_path=f"/userAssignedIdentities/{uami_name}",
    )
    client_id = generate_uuid()
    principal_id = generate_uuid()
    mocked_responses.add(
        method=responses.GET,
        url=uami_endpoint,
        json={"properties": {"clientId": client_id, "principalId": principal_id}},
        status=200,
        content_type="application/json",
    )

    # Role assignment fetch mock
    # TODO: assert when role assignment exists.
    if not skip_role_assignments:
        ra_get_endpoint = append_role_assignment_endpoint(
            resource_endpoint=kv_endpoint, filter_query=f"principalId eq '{principal_id}'"
        )
        mocked_responses.add(
            method=responses.GET,
            url=ra_get_endpoint,
            json={"value": []},
            status=200,
            content_type="application/json",
        )

        ra_put_endpoint = append_role_assignment_endpoint(resource_endpoint=kv_endpoint, ra_name=".*")
        ra_put = mocked_responses.add(
            method=responses.PUT,
            url=re.compile(ra_put_endpoint),
            json={},
            status=200,
            content_type="application/json",
        )

    # Custom location fetch mock
    cl_endpoint = get_custom_location_endpoint(resource_group_name=resource_group_name, custom_location_name=".*")
    cl_payload = get_mock_custom_location_record(
        name=generate_random_string(), resource_group_name=resource_group_name
    )
    mocked_responses.add(
        method=responses.GET,
        url=re.compile(cl_endpoint),
        json=cl_payload,
        status=200,
        content_type="application/json",
    )

    # Cluster fetch mock
    cluster_location = generate_random_string()
    cluster_name = generate_random_string()
    cluster_endpoint = get_cluster_url(cluster_rg=".*", cluster_name=".*")
    mocked_responses.add(
        method=responses.GET,
        url=re.compile(cluster_endpoint),
        json={
            "id": generate_resource_id(
                resource_group_name=resource_group_name,
                resource_provider="Microsoft.Kubernetes",
                resource_path=f"/connectedClusters/{cluster_name}",
            ),
            "name": cluster_name,
            "properties": {**oidc_issuer_def},
            "location": cluster_location,
        },
        status=200,
        content_type="application/json",
    )

    # Resource Graph POST
    mocked_responses.add(
        method=responses.POST,
        url=ARG_ENDPOINT,
        json={"data": [get_mock_custom_location_record(name="cl", resource_group_name=resource_group_name)]},
        status=200,
        content_type="application/json",
    )

    # Federation fetch
    # TODO: assert when already federated.
    mocked_responses.add(
        method=responses.GET,
        url=get_federated_creds_url(uami_rg_name=resource_group_name, uami_name=uami_name),
        json={"value": []},
        status=200,
        content_type="application/json",
    )
    # Federation PUT
    if use_self_hosted_issuer:
        oidc_issuer = oidc_issuer_def["oidcIssuerProfile"].get("selfHostedIssuerUrl")
    else:
        oidc_issuer = oidc_issuer_def["oidcIssuerProfile"].get("issuerUrl")

    subject = f"system:serviceaccount:{cl_payload['properties']['namespace']}:{SERVICE_ACCOUNT_SECRETSYNC}"
    mocked_responses.add(
        method=responses.PUT,
        url=get_federated_creds_url(
            uami_rg_name=resource_group_name,
            uami_name=uami_name,
            fc_name=get_fc_name(cluster_name=cluster_name, oidc_issuer=oidc_issuer, subject=subject),
        ),
        json={},
        status=200,
        content_type="application/json",
    )

    # PUT SPC
    spc_name = spc_name or get_spc_name(
        cluster_name=cluster_name,
        resource_group_name=resource_group_name,
        instance_name=instance_name,
    )
    spc_endpoint = get_spc_endpoint(resource_group_name=resource_group_name, spc_name=spc_name)
    spc_payload = get_mock_spc_record(
        name=spc_name,
        resource_group_name=resource_group_name,
        cl_name=cl_payload["name"],
        tags=tags,
    )
    spc_create = mocked_responses.add(
        method=responses.PUT,
        url=spc_endpoint,
        json=spc_payload,
        status=200,
        content_type="application/json",
    )

    # TODO: assert when already enabled.
    result = secretsync_enable(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        mi_user_assigned=uami_resource_id,
        keyvault_resource_id=keyvault_resource_id,
        spc_name=spc_name,
        skip_role_assignments=skip_role_assignments,
        use_self_hosted_issuer=use_self_hosted_issuer,
        custom_role_id=custom_role_id,
        tags=tags,
        wait_sec=0.1,
    )
    assert result == spc_payload
    spc_create_request = json.loads(spc_create.calls[0].request.body)
    assert spc_create_request["extendedLocation"] == instance_record["extendedLocation"]
    assert spc_create_request["location"] == cluster_location
    assert spc_create_request["properties"]["clientId"] == client_id
    assert spc_create_request["properties"]["keyvaultName"] == kv_name
    assert spc_create_request["properties"]["tenantId"]
    if tags:
        assert spc_create_request["tags"] == tags

    mocked_get_tenant_id.assert_called_once()

    if not skip_role_assignments:
        role_ids = []
        if custom_role_id:
            assert len(ra_put.calls) == 1
            role_ids.append(custom_role_id)
        else:
            assert len(ra_put.calls) == 2
            role_ids.append(generate_role_def_id(role_id=KEYVAULT_ROLE_ID_SECRETS_USER))
            role_ids.append(generate_role_def_id(role_id=KEYVAULT_ROLE_ID_READER))

        for i in range(len(role_ids)):
            ra_put_request = json.loads(ra_put.calls[i].request.body)
            assert ra_put_request["properties"]["roleDefinitionId"] == role_ids[i]
            assert ra_put_request["properties"]["principalId"] == principal_id
            assert ra_put_request["properties"]["principalType"] == "ServicePrincipal"


@pytest.mark.parametrize(
    "scenario",
    [
        {
            "description": "No issuer url.",
            "profileDef": {
                "oidcIssuerProfile": {
                    "enabled": True,
                    "selfHostedIssuerUrl": "https://localhost.selfHostedIssuer",
                    "issuerUrl": None,
                },
                "securityProfile": {"workloadIdentity": {"enabled": True}},
            },
            "useSelfHostedIssuer": None,
            "error": "No issuerUrl is available. Check cluster config.",
        },
        {
            "description": "No self hosted issuer url.",
            "profileDef": {
                "oidcIssuerProfile": {
                    "enabled": True,
                    "selfHostedIssuerUrl": None,
                    "issuerUrl": "https://localhost.systemIssuer",
                },
                "securityProfile": {"workloadIdentity": {"enabled": True}},
            },
            "useSelfHostedIssuer": True,
            "error": "No selfHostedIssuerUrl is available. Check cluster config.",
        },
        {
            "description": "OIDC issuer not enabled.",
            "profileDef": {
                "oidcIssuerProfile": {
                    "enabled": False,
                },
                "securityProfile": {"workloadIdentity": {"enabled": True}},
            },
            "useSelfHostedIssuer": None,
            "error": (
                "The connected cluster '{}' is not enabled as an oidc issuer.\n"
                "Please enable with 'az connectedk8s update -n {} -g {} --enable-oidc-issuer'."
            ),
        },
        {
            "description": "Identity federation not enabled.",
            "profileDef": {
                "oidcIssuerProfile": {
                    "enabled": True,
                },
                "securityProfile": {"workloadIdentity": {"enabled": False}},
            },
            "useSelfHostedIssuer": None,
            "error": (
                "The connected cluster '{}' is not enabled for workload identity federation.\n"
                "Please enable with 'az connectedk8s update -n {} -g {} --enable-workload-identity'."
            ),
        },
        {
            "description": "Identity federation not enabled.",
            "profileDef": {
                "oidcIssuerProfile": {
                    "enabled": False,
                },
                "securityProfile": {"workloadIdentity": {"enabled": False}},
            },
            "useSelfHostedIssuer": None,
            "error": (
                "The connected cluster '{}' is not enabled as an oidc issuer or for workload identity federation.\n"
                "Please enable with 'az connectedk8s update -n {} -g {} "
                "--enable-oidc-issuer --enable-workload-identity'."
            ),
        },
    ],
)
def test_secretsync_enable_issuer_error(
    mocked_cmd,
    mocked_responses: responses,
    scenario: dict,
):
    resource_group_name = generate_random_string()

    # Instance fetch mock
    instance_name = generate_random_string()
    instance_endpoint = get_instance_endpoint(resource_group_name=resource_group_name, instance_name=instance_name)
    instance_record = get_mock_instance_record(
        name=instance_name,
        resource_group_name=resource_group_name,
    )
    mocked_responses.add(
        method=responses.GET,
        url=instance_endpoint,
        json=instance_record,
        status=200,
        content_type="application/json",
    )

    # KV fetch mock
    kv_name = generate_random_string()
    kv_endpoint = get_kv_endpoint(resource_group_name=resource_group_name, kv_name=kv_name)
    mocked_responses.add(
        method=responses.GET,
        url=kv_endpoint,
        json={},
        status=200,
        content_type="application/json",
    )
    keyvault_resource_id = generate_resource_id(
        resource_group_name=resource_group_name,
        resource_provider="Microsoft.KeyVault",
        resource_path=f"/keyvaults/{kv_name}",
    )

    # UAMI fetch mock
    uami_name = generate_random_string()
    uami_endpoint = get_uami_endpoint(resource_group_name=resource_group_name, uami_name=uami_name)
    uami_resource_id = generate_resource_id(
        resource_group_name=resource_group_name,
        resource_provider="Microsoft.ManagedIdentity",
        resource_path=f"/userAssignedIdentities/{uami_name}",
    )
    client_id = generate_uuid()
    principal_id = generate_uuid()
    mocked_responses.add(
        method=responses.GET,
        url=uami_endpoint,
        json={"properties": {"clientId": client_id, "principalId": principal_id}},
        status=200,
        content_type="application/json",
    )

    # Custom location fetch mock
    cl_endpoint = get_custom_location_endpoint(resource_group_name=resource_group_name, custom_location_name=".*")
    cl_payload = get_mock_custom_location_record(
        name=generate_random_string(), resource_group_name=resource_group_name
    )
    mocked_responses.add(
        method=responses.GET,
        url=re.compile(cl_endpoint),
        json=cl_payload,
        status=200,
        content_type="application/json",
    )

    # Cluster fetch mock
    cluster_location = generate_random_string()
    cluster_name = generate_random_string()
    cluster_endpoint = get_cluster_url(cluster_rg=".*", cluster_name=".*")
    mocked_responses.add(
        method=responses.GET,
        url=re.compile(cluster_endpoint),
        json={
            "id": generate_resource_id(
                resource_group_name=resource_group_name,
                resource_provider="Microsoft.Kubernetes",
                resource_path=f"/connectedClusters/{cluster_name}",
            ),
            "name": cluster_name,
            "properties": {**scenario["profileDef"]},
            "location": cluster_location,
        },
        status=200,
        content_type="application/json",
    )

    with pytest.raises(ValidationError) as exc:
        secretsync_enable(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            mi_user_assigned=uami_resource_id,
            keyvault_resource_id=keyvault_resource_id,
            skip_role_assignments=True,
            use_self_hosted_issuer=scenario["useSelfHostedIssuer"],
        )
    assert isinstance(exc.value, ValidationError)
    error_str: str = scenario["error"]
    error_str = error_str.format(
        cluster_name,
        cluster_name,
        resource_group_name,
    )
    assert str(exc.value) == error_str
