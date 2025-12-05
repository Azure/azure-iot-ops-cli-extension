# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

# TODO: @digimaun - Re-organize this test file to be more modular.

import json
import math
import re
from collections import defaultdict
from copy import deepcopy
from functools import partial
from pathlib import PurePath
from typing import List, Optional, Tuple, TypeVar
from unittest.mock import Mock, mock_open

import pytest
import requests
import responses
from azure.cli.core.azclierror import ValidationError

from azext_edge.constants import VERSION as CLI_VERSION
from azext_edge.edge.commands_edge import clone_instance
from azext_edge.edge.common import (
    DEFAULT_BROKER,
    DEFAULT_BROKER_AUTHN,
    DEFAULT_BROKER_LISTENER,
    DEFAULT_DATAFLOW_ENDPOINT,
    DEFAULT_DATAFLOW_PROFILE,
)
from azext_edge.edge.providers.orchestration.clone import (
    DEPLOYMENT_CHUNK_LEN,
    SERVICE_ACCOUNT_DATAFLOW,
    SERVICE_ACCOUNT_SCHEMA,
    SERVICE_ACCOUNT_SECRETSYNC,
    TEMPLATE_PARAMS_SET,
    CloneManager,
    InstanceRestore,
    TemplateMode,
    VersionGuru,
    default_bundle_name,
    get_fc_name,
)
from azext_edge.edge.providers.orchestration.common import (
    EXTENSION_MONIKER_ACS,
    EXTENSION_MONIKER_CM,
    EXTENSION_MONIKER_OPS,
    EXTENSION_MONIKER_PLATFORM,
    EXTENSION_MONIKER_SSC,
    EXTENSION_TYPE_ACS,
    EXTENSION_TYPE_CM,
    EXTENSION_TYPE_OPS,
    EXTENSION_TYPE_PLATFORM,
    EXTENSION_TYPE_SSC,
    SECRET_SYNC_API_VERSION,
)
from azext_edge.edge.util.az_client import (
    DeviceRegistryMgmtApiVersion,
    IoTOpsMgmtApiVersion,
)
from azext_edge.edge.util.id_tools import parse_resource_id
from azext_edge.edge.util.machinery import scoped_semver_import

from ...generators import (
    generate_random_string,
    generate_resource_id,
    generate_uuid,
    get_zeroed_subscription,
)
from ..adr.test_namespace_assets_unit import get_namespace_asset_record
from ..adr.test_namespace_devices_unit import get_namespace_device_record
from .resources.conftest import BASE_URL, get_request_kpis
from .resources.connector.akri.test_connector_templates_unit import (
    get_connector_template_endpoint,
    get_mock_connector_template_record,
)
from .resources.dataflow_endpoint.conftest import (
    get_dataflow_endpoint_endpoint,
    get_mock_dataflow_endpoint_record,
)
from .resources.registry_endpoint.test_registry_endpoints_unit import (
    get_mock_registry_endpoint_record,
    get_registry_endpoint_endpoint,
)
from .resources.test_aeps_unit import get_mock_aep_record
from .resources.test_assets_unit import get_mock_asset_record
from .resources.test_broker_authns_unit import (
    get_broker_authn_endpoint,
    get_mock_broker_authn_record,
)
from .resources.test_broker_authzs_unit import (
    get_broker_authz_endpoint,
    get_mock_broker_authz_record,
)
from .resources.test_broker_listeners_unit import (
    get_broker_listener_endpoint,
    get_mock_broker_listener_record,
)
from .resources.test_brokers_unit import (
    get_broker_endpoint,
    get_mock_broker_record,
)
from .resources.test_clusters_unit import get_cluster_url, get_federated_creds_url
from .resources.test_custom_locations_unit import (
    get_custom_location_endpoint,
    get_mock_custom_location_record,
)
from .resources.test_dataflow_profiles_unit import (
    get_dataflow_profile_endpoint,
    get_mock_dataflow_profile_record,
)
from .resources.test_dataflows_unit import (
    get_dataflow_endpoint,
    get_mock_dataflow_record,
)
from .resources.test_instances_unit import (
    get_instance_endpoint,
    get_mock_instance_record,
    get_uami_id_map,
)
from .resources.test_secretsync_spcs_unit import get_mock_spc_record, get_spc_endpoint
from .resources.test_secretsyncs_unit import (
    get_mock_secretsync_record,
    get_secretsync_endpoint,
)

ZEROED_SUBSCRIPTION = get_zeroed_subscription()


C = TypeVar("C", bound="CloneScenario")

EXT_NAME_CM = "cert-manager"
EXT_NAME_PLAT = "azure-iot-operations-platform"
EXT_NAME_SSC = "azure-secrets-store"
EXT_NAME_OPS = "azure-iot-operations"
EXT_NAME_ACS = "azure-arc-containerstorage"


EXT_NAME_TO_MONIKER = {
    EXT_NAME_CM: EXTENSION_MONIKER_CM,
    EXT_NAME_PLAT: EXTENSION_MONIKER_PLATFORM,
    EXT_NAME_ACS: EXTENSION_MONIKER_ACS,
    EXT_NAME_SSC: EXTENSION_MONIKER_SSC,
    EXT_NAME_OPS: EXTENSION_MONIKER_OPS,
}

PLURALS = [
    "authns",
    "authzs",
    "listeners",
    "dataflowEndpoints",
    "dataflowProfiles",
    "dataflows",
    "secretProviderClasss",
    "secretSyncs",
    "assetEndpointProfiles",
    "assets",
    "connectorTemplates",
    "registryEndpoints",
    "namespaceDevices",
    "namespaceAssets",
]
SINGLETONS = ["customLocation", "instance", "roleAssignments_1", "broker"]

MOCK_SR_RESOURCE_ID = generate_resource_id(
    resource_group_name=generate_random_string(),
    resource_provider="Microsoft.DeviceRegistry",
    resource_path=f"/schemaRegistries/{generate_random_string()}",
)

MOCK_NS_RESOURCE_ID = generate_resource_id(
    resource_group_name=generate_random_string(),
    resource_provider="Microsoft.DeviceRegistry",
    resource_path=f"/namespaces/{generate_random_string()}",
)


@pytest.fixture
def mock_open_write(mocker):
    m = mock_open()
    patched = mocker.patch("azext_edge.edge.providers.orchestration.clone.open", m)
    yield patched


@pytest.fixture
def mock_pathlib_path(mocker):
    patched = mocker.patch("azext_edge.edge.providers.orchestration.clone.Path")
    yield patched


def get_deploy_url(cluster_sub_id: str, cluster_rg: str, deployment_name: str, page_num: Optional[int] = 1) -> str:
    page_num = "" if not page_num else f"_{page_num}"
    return (
        f"{BASE_URL}/subscriptions/{cluster_sub_id}/resourcegroups/{cluster_rg}/providers"
        f"/Microsoft.Resources/deployments/{deployment_name}{page_num}?api-version=2024-03-01"
    )


class CloneScenario:
    def __init__(self, description: str = None):
        self.description = description
        self.resource_configs = defaultdict(list)

    def bootstrap(
        self: C,
        mocked_responses: responses,
        instance_name: str,
        resource_group_name: str,
        cluster_name: str,
        add_resources_map: Optional[dict] = None,
        instance_version: Optional[str] = None,
        instance_features: Optional[dict] = None,
    ):
        self.responses = mocked_responses
        self.instance_name = instance_name
        self.resource_group_name = resource_group_name
        self.cluster_name = cluster_name
        self.cl_name = generate_random_string()
        self.sr_name = generate_random_string()
        self.default_spc_name = generate_random_string()
        self.adr_ns_name = generate_random_string()
        self.default_broker_name = DEFAULT_BROKER
        self.default_authn_name = DEFAULT_BROKER_AUTHN
        self.default_listener_name = DEFAULT_BROKER_LISTENER
        self.default_dataflow_profile_name = DEFAULT_DATAFLOW_PROFILE
        self.default_dataflow_endpoint_name = DEFAULT_DATAFLOW_ENDPOINT
        self.arg_queries = {}
        self.add_resources_map = add_resources_map or {}
        self.spc_client_ids = []
        self.uami_ids = []
        self.client_id_uami_map = {}
        self._configure_instance(instance_version=instance_version, instance_features=instance_features)

    def _configure_instance(
        self: C, instance_version: Optional[str] = None, instance_features: Optional[dict] = None
    ) -> C:
        if not instance_version:
            instance_version = "1.1.0"
        self.api_config = VersionGuru({"properties": {"version": instance_version}}).get_api_config()

        self.add_extensions()
        self.add_custom_location(namespace=generate_random_string())
        self.add_instance(version=instance_version, features=instance_features)
        self.add_broker()
        self.add_listeners()
        self.add_authns()
        self.add_authzs()
        self.add_dataflow_profiles()
        self.add_dataflow_endpoints()
        self.add_dataflows()
        self.add_secretsync_spcs()
        self.add_secretsyncs()
        self.add_connector_templates()
        self.add_registry_endpoints()
        self.add_arg_handler()

        return self

    def wrap_cluster_deploy(
        self: C,
        content_len: int = 1,
        connectivity_status: str = "Connected",
        cred_state: Optional[dict] = None,
    ) -> Tuple[List[responses.BaseResponse], str]:
        to_cluster_resource_id = get_cluster_url(
            cluster_sub_id=generate_uuid(),
            cluster_rg=generate_random_string(),
            cluster_name=generate_random_string(),
            just_id=True,
        )
        if cred_state is None:
            cred_state = {"subjects": {SERVICE_ACCOUNT_DATAFLOW, SERVICE_ACCOUNT_SECRETSYNC}}
        cred_subjects = cred_state.get("subjects", {})
        cred_payload = {"value": []}
        id_slug = generate_uuid()
        for subject in cred_subjects:
            cred_payload["value"].append(
                {
                    "properties": {
                        "issuer": f"https://oidcdiscovery-northamerica-endpoint-abcde.z01.azurefd.net/{id_slug}/",
                        "subject": f"system:serviceaccount:azure-iot-operations:{subject}",
                        "audiences": ["api://AzureADTokenExchange"],
                    },
                }
            )

        parsed_cluster_id = parse_resource_id(to_cluster_resource_id)
        cluster_sub_id = parsed_cluster_id["subscription"]
        cluster_rg = parsed_cluster_id["resource_group"]
        cluster_name = parsed_cluster_id["name"]

        system_issuer = f"https://northamerica.oic.prod-arc.azure.com/{generate_uuid()}/{generate_uuid()}/"
        cluster_payload = {
            "id": to_cluster_resource_id,
            "name": cluster_name,
            "properties": {
                "securityProfile": {"workloadIdentity": {"enabled": True}},
                "oidcIssuerProfile": {
                    "enabled": True,
                    "issuerUrl": system_issuer,
                },
                "connectivityStatus": connectivity_status,
            },
        }
        # Always needed for connected cluster check.
        self.responses.add(
            method=responses.GET,
            url=get_cluster_url(cluster_sub_id=cluster_sub_id, cluster_rg=cluster_rg, cluster_name=cluster_name),
            json=cluster_payload,
            status=200,
        )

        deploy_responses = []
        if connectivity_status.lower() == "connected":
            if self.uami_ids:
                for uami_id in self.uami_ids:
                    parsed_uami_id = parse_resource_id(uami_id)
                    cred_url = get_federated_creds_url(
                        uami_sub_id=parsed_uami_id["subscription"],
                        uami_rg_name=parsed_uami_id["resource_group"],
                        uami_name=parsed_uami_id["name"],
                    )
                    self.responses.add(
                        method=responses.GET,
                        url=cred_url,
                        json=cred_payload,
                        status=200,
                    )

                    cred_payload_value = cred_payload["value"]
                    namespace = self.resource_configs["customLocation"]["properties"]["namespace"]
                    if cred_payload_value:
                        for subject in cred_subjects:
                            qualified_subject = f"system:serviceaccount:{namespace}:{subject}"
                            fc_name = get_fc_name(
                                cluster_name=cluster_name, oidc_issuer=system_issuer, subject=qualified_subject
                            )
                            cred_url = get_federated_creds_url(
                                uami_sub_id=parsed_uami_id["subscription"],
                                uami_rg_name=parsed_uami_id["resource_group"],
                                uami_name=parsed_uami_id["name"],
                                fc_name=fc_name,
                            )
                            self.responses.add(
                                method=responses.PUT,
                                url=cred_url,
                                json={},
                                status=200,
                            )

            deployment_name = default_bundle_name(self.instance_name)
            for i in range(content_len):
                r = self.responses.add(
                    method=responses.PUT,
                    url=get_deploy_url(
                        cluster_sub_id=cluster_sub_id,
                        cluster_rg=cluster_rg,
                        deployment_name=deployment_name,
                        page_num=i + 1 if content_len > 1 else None,
                    ),
                    json={},
                    status=200,
                    content_type="application/json",
                )
                deploy_responses.append(r)
        return deploy_responses, to_cluster_resource_id

    def add_extensions(self: C):
        extensions_endpoint = (
            f"{BASE_URL}/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{self.resource_group_name}"
            f"/providers/Microsoft.Kubernetes/connectedClusters/{self.cluster_name}/providers"
            "/Microsoft.KubernetesConfiguration/extensions?api-version=2023-05-01"
        )

        extensions = []
        extensions_name_map = {}

        if self.api_config.v2_enabled:
            extensions_to_create = [
                (EXTENSION_TYPE_CM, EXT_NAME_CM),
                (EXTENSION_TYPE_SSC, EXT_NAME_SSC),
                (EXTENSION_TYPE_OPS, EXT_NAME_OPS),
            ]
            if self.add_resources_map.get("includeContainerStorage", False):
                extensions_to_create.append((EXTENSION_TYPE_ACS, EXT_NAME_ACS))
        else:
            extensions_to_create = [
                (EXTENSION_TYPE_PLATFORM, EXT_NAME_PLAT),
                (EXTENSION_TYPE_ACS, EXT_NAME_ACS),
                (EXTENSION_TYPE_SSC, EXT_NAME_SSC),
                (EXTENSION_TYPE_OPS, EXT_NAME_OPS),
            ]

        for ext_type, ext_name in extensions_to_create:
            record_name = ext_name
            if ext_name == EXT_NAME_OPS:
                record_name = f"{ext_name}-{generate_random_string()}"
            ext = self._create_extension(ext_type=ext_type, ext_name=record_name, version="1.0.0", train="stable")
            extensions.append(ext)
            extensions_name_map[ext_name] = ext

        self.responses.add(
            method=responses.GET,
            url=extensions_endpoint,
            json={"value": extensions},
            status=200,
            content_type="application/json",
        )
        self.resource_configs["extensions"] = extensions_name_map

    def _create_extension(self, ext_type: str, ext_name: str, version: str, train: str) -> dict:
        ext = {
            "id": (
                f"/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{self.resource_group_name}"
                f"/providers/Microsoft.Kubernetes/connectedClusters/{self.cluster_name}/providers"
                f"/Microsoft.KubernetesConfiguration/extensions/{ext_name}"
            ),
            "name": ext_name,
            "type": "Microsoft.KubernetesConfiguration/extensions",
            "properties": {
                "extensionType": ext_type,
                "version": version,
                "releaseTrain": train,
                "provisioningState": "Succeeded",
                "configurationSettings": {},
            },
        }

        if ext_type == EXTENSION_TYPE_OPS:
            identity_id = generate_random_string()
            ext["identity"] = {
                "type": "SystemAssigned",
                "principalId": identity_id,
            }

        return ext

    def add_custom_location(self: C, namespace: Optional[str] = None):
        mock_cl_record = get_mock_custom_location_record(
            name=self.cl_name,
            resource_group_name=self.resource_group_name,
            cluster_name=self.cluster_name,
            namespace=namespace,
            ops_extension_name=self.resource_configs["extensions"][EXT_NAME_OPS]["name"],
        )
        self.responses.add(
            method=responses.GET,
            url=get_custom_location_endpoint(
                resource_group_name=self.resource_group_name, custom_location_name=self.cl_name
            ),
            json=mock_cl_record,
            status=200,
            content_type="application/json",
        )
        self.resource_configs["customLocation"] = mock_cl_record

    def add_instance(self: C, version: Optional[str] = None, features: Optional[dict] = None):
        optional_kwargs = {}
        identity_map = {}

        for _ in range(self.add_resources_map.get("identities", 0)):
            uami_map = get_uami_id_map(self.resource_group_name)
            self.uami_ids.append(next(iter(uami_map)))
            identity_map.update(uami_map)

        if identity_map:
            optional_kwargs["identity_map"] = identity_map

        mock_instance_record = get_mock_instance_record(
            name=self.instance_name,
            resource_group_name=self.resource_group_name,
            cl_name=self.cl_name,
            schema_registry_name=self.sr_name,
            adr_namespace_name=self.adr_ns_name,
            default_spc_name=self.default_spc_name,
            version=version,
            features=features,
            **optional_kwargs,
        )
        self.resource_configs["schemaRegistryId"] = mock_instance_record["properties"]["schemaRegistryRef"][
            "resourceId"
        ]
        if self.api_config.v2_enabled:
            self.resource_configs["adrNamespaceId"] = mock_instance_record["properties"]["adrNamespaceRef"][
                "resourceId"
            ]
        instance_fetch_by_apis = [IoTOpsMgmtApiVersion.V20251001.value]
        if not self.api_config.v2_enabled:
            instance_fetch_by_apis.append(self.api_config.iotops_mgmt_api)
        for api_version in instance_fetch_by_apis:
            self.responses.add(
                method=responses.GET,
                url=get_instance_endpoint(
                    resource_group_name=self.resource_group_name,
                    instance_name=self.instance_name,
                    api_version=api_version,
                ),
                json=mock_instance_record,
                status=200,
                content_type="application/json",
            )
        self.resource_configs["instance"] = mock_instance_record

    def add_broker(self: C):
        mock_broker_record = get_mock_broker_record(
            broker_name=self.default_broker_name,
            instance_name=self.instance_name,
            resource_group_name=self.resource_group_name,
        )
        self.responses.add(
            method=responses.GET,
            url=get_broker_endpoint(
                resource_group_name=self.resource_group_name,
                instance_name=self.instance_name,
                api_version=self.api_config.iotops_mgmt_api,
            ),
            json={"value": [mock_broker_record]},
            status=200,
            content_type="application/json",
        )
        self.resource_configs["broker"] = mock_broker_record

    def add_listeners(self: C):
        mock_listener_record = get_mock_broker_listener_record(
            listener_name=self.default_listener_name,
            broker_name=self.default_broker_name,
            instance_name=self.instance_name,
            resource_group_name=self.resource_group_name,
        )
        listeners = [mock_listener_record]
        for _ in range(self.add_resources_map.get("listeners", 0)):
            listeners.append(
                get_mock_broker_listener_record(
                    listener_name=generate_random_string(),
                    broker_name=self.default_broker_name,
                    instance_name=self.instance_name,
                    resource_group_name=self.resource_group_name,
                )
            )
        payload = {"value": listeners}

        self.responses.add(
            method=responses.GET,
            url=get_broker_listener_endpoint(
                resource_group_name=self.resource_group_name,
                instance_name=self.instance_name,
                broker_name=self.default_broker_name,
                api_version=self.api_config.iotops_mgmt_api,
            ),
            json=payload,
            status=200,
            content_type="application/json",
        )
        self.resource_configs["listeners"] = listeners

    def add_authns(self: C):
        mock_authn_record = get_mock_broker_authn_record(
            authn_name=self.default_authn_name,
            broker_name=self.default_broker_name,
            instance_name=self.instance_name,
            resource_group_name=self.resource_group_name,
        )
        authns = [mock_authn_record]
        for _ in range(self.add_resources_map.get("authns", 0)):
            authns.append(
                get_mock_broker_authn_record(
                    authn_name=generate_random_string(),
                    broker_name=self.default_broker_name,
                    instance_name=self.instance_name,
                    resource_group_name=self.resource_group_name,
                )
            )
        payload = {"value": authns}

        self.responses.add(
            method=responses.GET,
            url=get_broker_authn_endpoint(
                resource_group_name=self.resource_group_name,
                instance_name=self.instance_name,
                broker_name=self.default_broker_name,
                api_version=self.api_config.iotops_mgmt_api,
            ),
            json=payload,
            status=200,
            content_type="application/json",
        )
        self.resource_configs["authns"] = authns

    def add_authzs(self: C):
        authzs = []
        for _ in range(self.add_resources_map.get("authzs", 0)):
            authzs.append(
                get_mock_broker_authz_record(
                    authz_name=generate_random_string(),
                    broker_name=self.default_broker_name,
                    instance_name=self.instance_name,
                    resource_group_name=self.resource_group_name,
                )
            )
        payload = {"value": authzs}

        self.responses.add(
            method=responses.GET,
            url=get_broker_authz_endpoint(
                resource_group_name=self.resource_group_name,
                instance_name=self.instance_name,
                broker_name=self.default_broker_name,
                api_version=self.api_config.iotops_mgmt_api,
            ),
            json=payload,
            status=200,
            content_type="application/json",
        )
        self.resource_configs["authzs"] = payload["value"]

    def add_dataflow_profiles(self: C):
        mock_dataflow_profile_record = get_mock_dataflow_profile_record(
            profile_name=self.default_dataflow_profile_name,
            instance_name=self.instance_name,
            resource_group_name=self.resource_group_name,
        )
        profiles = [mock_dataflow_profile_record]
        for _ in range(self.add_resources_map.get("dataflowProfiles", 0)):
            profiles.append(
                get_mock_dataflow_profile_record(
                    profile_name=generate_random_string(),
                    instance_name=self.instance_name,
                    resource_group_name=self.resource_group_name,
                )
            )
        payload = {"value": profiles}

        self.responses.add(
            method=responses.GET,
            url=get_dataflow_profile_endpoint(
                resource_group_name=self.resource_group_name,
                instance_name=self.instance_name,
                api_version=self.api_config.iotops_mgmt_api,
            ),
            json=payload,
            status=200,
            content_type="application/json",
        )
        self.resource_configs["dataflowProfiles"] = profiles

    def add_dataflow_endpoints(self: C):
        mock_dataflow_endpoint_record = get_mock_dataflow_endpoint_record(
            dataflow_endpoint_name=self.default_dataflow_endpoint_name,
            instance_name=self.instance_name,
            resource_group_name=self.resource_group_name,
        )
        endpoints = [mock_dataflow_endpoint_record]
        for _ in range(self.add_resources_map.get("dataflowEndpoints", 0)):
            endpoints.append(
                get_mock_dataflow_endpoint_record(
                    dataflow_endpoint_name=generate_random_string(),
                    instance_name=self.instance_name,
                    resource_group_name=self.resource_group_name,
                )
            )
        payload = {"value": endpoints}

        self.responses.add(
            method=responses.GET,
            url=get_dataflow_endpoint_endpoint(
                resource_group_name=self.resource_group_name,
                instance_name=self.instance_name,
                api_version=self.api_config.iotops_mgmt_api,
            ),
            json=payload,
            status=200,
            content_type="application/json",
        )
        self.resource_configs["dataflowEndpoints"] = endpoints

    def add_dataflows(self: C):
        dataflows = []
        for profile in self.resource_configs["dataflowProfiles"]:
            per_profile = []
            for _ in range(self.add_resources_map.get("dataflows", 0)):
                per_profile.append(
                    get_mock_dataflow_record(
                        dataflow_name=generate_random_string(),
                        profile_name=profile["name"],
                        instance_name=self.instance_name,
                        resource_group_name=self.resource_group_name,
                    )
                )
            payload = {"value": per_profile}
            self.responses.add(
                method=responses.GET,
                url=get_dataflow_endpoint(
                    profile_name=profile["name"],
                    instance_name=self.instance_name,
                    resource_group_name=self.resource_group_name,
                    api_version=self.api_config.iotops_mgmt_api,
                ),
                json=payload,
                status=200,
                content_type="application/json",
            )
            dataflows.extend(per_profile)
        self.resource_configs["dataflows"] = dataflows

    def add_secretsync_spcs(self: C):
        spcs = []
        use_default_spc_name = self.api_config.v2_enabled
        for _ in range(self.add_resources_map.get("spcs", 0)):
            spc_name = generate_random_string()
            if use_default_spc_name:
                spc_name = self.default_spc_name
                use_default_spc_name = False
            spc = get_mock_spc_record(name=spc_name, resource_group_name=self.resource_group_name, cl_name=self.cl_name)
            self.spc_client_ids.append(spc["properties"]["clientId"])
            uami_map = get_uami_id_map(self.resource_group_name)
            uami_id = next(iter(uami_map))
            self.uami_ids.append(uami_id)
            self.client_id_uami_map[spc["properties"]["clientId"]] = uami_id

            spcs.append(spc)
        payload = {"value": spcs}

        self.responses.add(
            method=responses.GET,
            url=get_spc_endpoint(
                resource_group_name=self.resource_group_name,
            ),
            json=payload,
            status=200,
            content_type="application/json",
        )
        self.resource_configs["secretProviderClasss"] = spcs

    def add_secretsyncs(self: C):
        secretsyncs = []
        for _ in range(self.add_resources_map.get("secretsyncs", 0)):
            secretsyncs.append(
                get_mock_secretsync_record(
                    name=generate_random_string(), resource_group_name=self.resource_group_name, cl_name=self.cl_name
                )
            )
        payload = {"value": secretsyncs}

        self.responses.add(
            method=responses.GET,
            url=get_secretsync_endpoint(
                resource_group_name=self.resource_group_name,
            ),
            json=payload,
            status=200,
            content_type="application/json",
        )
        self.resource_configs["secretSyncs"] = secretsyncs

    def add_connector_templates(self: C):
        if not self.api_config.v2_enabled:
            return
        connector_templates = []
        for _ in range(self.add_resources_map.get("connectorTemplates", 0)):
            connector_templates.append(
                get_mock_connector_template_record(
                    name=generate_random_string(),
                    instance_name=self.instance_name,
                    resource_group_name=self.resource_group_name,
                    cl_name=self.cl_name,
                )
            )
        payload = {"value": connector_templates}
        self.responses.add(
            method=responses.GET,
            url=get_connector_template_endpoint(
                instance_name=self.instance_name, resource_group_name=self.resource_group_name
            ),
            json=payload,
            status=200,
            content_type="application/json",
        )
        self.resource_configs["connectorTemplates"] = connector_templates

    def add_registry_endpoints(self: C):
        if not self.api_config.v2_enabled:
            return
        registry_endpoints = []
        for _ in range(self.add_resources_map.get("registryEndpoints", 0)):
            registry_endpoints.append(
                get_mock_registry_endpoint_record(
                    registry_endpoint_name=generate_random_string(),
                    instance_name=self.instance_name,
                    resource_group_name=self.resource_group_name,
                    host="mcr.microsoft.com",
                )
            )
        payload = {"value": registry_endpoints}
        self.responses.add(
            method=responses.GET,
            url=get_registry_endpoint_endpoint(
                instance_name=self.instance_name, resource_group_name=self.resource_group_name
            ),
            json=payload,
            status=200,
            content_type="application/json",
        )
        self.resource_configs["registryEndpoints"] = registry_endpoints

    def add_arg_handler(self: C):
        def _handle_requests(request: requests.PreparedRequest) -> Optional[tuple]:
            request_kpis = get_request_kpis(request)
            if request_kpis.body_str:
                request_payload = json.loads(request_kpis.body_str)
                query = request_payload["query"]
                expected_cl_id = (
                    get_custom_location_endpoint(
                        resource_group_name=self.resource_group_name, custom_location_name=self.cl_name
                    )
                    .split(BASE_URL)[1]
                    .split("?")[0]
                )
                if '| where type =~ "Microsoft.ManagedIdentity/userAssignedIdentities"' in query:
                    self.arg_queries["uami"] = 1
                    spc_uamis = []
                    assert self.resource_configs["secretProviderClasss"]
                    expected_client_ids = ""
                    for client_id in self.spc_client_ids:
                        expected_client_ids += f'"{client_id}", '
                        spc_uamis.append({"id": self.client_id_uami_map[client_id]})
                    assert f"| where properties.clientId in~ ({expected_client_ids[:-2]})" in query
                    return request_kpis.respond_with(200, response_body={"data": spc_uamis})

                if "| where type =~ 'microsoft.deviceregistry/assetendpointprofiles'" in query:
                    self.arg_queries["assetEndpointProfiles"] = 1
                    assert f"| where extendedLocation.name =~ '{expected_cl_id}'" in query

                    aeps = []
                    for _ in range(self.add_resources_map.get("aeps", 0)):
                        aeps.append(
                            get_mock_aep_record(
                                aep_name=generate_random_string(),
                                resource_group_name=self.resource_group_name,
                            )
                        )
                    self.resource_configs["assetEndpointProfiles"] = aeps
                    return request_kpis.respond_with(200, response_body={"data": aeps})
                if "| where type =~ 'microsoft.deviceregistry/assets'" in query:
                    self.arg_queries["assets"] = 1
                    assert f"| where extendedLocation.name =~ '{expected_cl_id}'" in query

                    assets = []
                    for _ in range(self.add_resources_map.get("assets", 0)):
                        assets.append(
                            get_mock_asset_record(
                                asset_name=generate_random_string(),
                                resource_group_name=self.resource_group_name,
                            )
                        )
                    self.resource_configs["assets"] = assets
                    return request_kpis.respond_with(200, response_body={"data": assets})

                if "| where type =~ 'microsoft.deviceregistry/namespaces/devices'" in query:
                    self.arg_queries["nsDevices"] = 1
                    assert f"| where extendedLocation.name =~ '{expected_cl_id}'" in query

                    ns_devices = []
                    for _ in range(self.add_resources_map.get("nsDevices", 0)):
                        ns_devices.append(
                            get_namespace_device_record(
                                device_name=generate_random_string(),
                                namespace_name=self.adr_ns_name,
                                resource_group_name=self.resource_group_name,
                            )
                        )
                    self.resource_configs["namespaceDevices"] = ns_devices
                    return request_kpis.respond_with(200, response_body={"data": ns_devices})

                if "| where type =~ 'microsoft.deviceregistry/namespaces/assets'" in query:
                    self.arg_queries["nsAssets"] = 1
                    assert f"| where extendedLocation.name =~ '{expected_cl_id}'" in query

                    ns_assets = []
                    for _ in range(self.add_resources_map.get("nsAssets", 0)):
                        ns_assets.append(
                            get_namespace_asset_record(
                                asset_name=generate_random_string(),
                                namespace_name=self.adr_ns_name,
                                resource_group_name=self.resource_group_name,
                            )
                        )
                    self.resource_configs["namespaceAssets"] = ns_assets
                    return request_kpis.respond_with(200, response_body={"data": ns_assets})

            raise RuntimeError("Unexpected query: " + query)

        self.responses.add_callback(
            method="POST",
            url=re.compile(
                r"https://management\.azure\.com/providers/Microsoft\.ResourceGraph/resources\?api-version=2022-10-01"
            ),
            callback=_handle_requests,
        )


@pytest.mark.parametrize("add_dataflows", [0, 2])
@pytest.mark.parametrize("add_dataflow_endpoints", [0, 5])
@pytest.mark.parametrize("add_dataflow_profiles", [0, 2])
@pytest.mark.parametrize("add_authzs", [0, 5])
@pytest.mark.parametrize("add_authns", [0, 5])
@pytest.mark.parametrize("add_listeners", [2])
@pytest.mark.parametrize("add_aeps", [0, 5])
@pytest.mark.parametrize("add_assets", [0, 5])
@pytest.mark.parametrize("add_secretsyncs", [0, 5])
@pytest.mark.parametrize("add_spcs", [0, 2])
@pytest.mark.parametrize("add_identities", [0, 2])
@pytest.mark.parametrize("clone_scenario", [CloneScenario()])
def test_clone_manager(
    mocked_cmd: Mock,
    mocked_responses: responses,
    clone_scenario: CloneScenario,
    mock_open_write: Mock,
    add_listeners: int,
    add_authns: int,
    add_authzs: int,
    add_dataflow_profiles: int,
    add_dataflow_endpoints: int,
    add_dataflows: int,
    add_aeps: int,
    add_assets: int,
    add_spcs: int,
    add_secretsyncs: int,
    add_identities: int,
):
    model_cluster_name = generate_random_string()
    model_instance_name = generate_random_string()
    model_resource_group_name = generate_random_string()
    add_resources_map = {
        "listeners": add_listeners,
        "authns": add_authns,
        "authzs": add_authzs,
        "dataflowProfiles": add_dataflow_profiles,
        "dataflowEndpoints": add_dataflow_endpoints,
        "dataflows": add_dataflows,
        "aeps": add_aeps,
        "assets": add_assets,
        "spcs": add_spcs,
        "secretsyncs": add_secretsyncs,
        "identities": add_identities,
    }

    clone_scenario.bootstrap(
        mocked_responses,
        resource_group_name=model_resource_group_name,
        instance_name=model_instance_name,
        cluster_name=model_cluster_name,
        add_resources_map=add_resources_map,
    )

    clone_manager = CloneManager(
        cmd=mocked_cmd,
        resource_group_name=model_resource_group_name,
        instance_name=model_instance_name,
        no_progress=True,
    )
    clone_state = clone_manager.analyze_cluster()
    template_content = clone_state.get_content()
    content = template_content.content

    CloneAssertor(clone_scenario).assert_content(content)

    deploy_responses, to_cluster_id = clone_scenario.wrap_cluster_deploy()
    parsed_cluster_id = parse_resource_id(to_cluster_id)

    restore_client: InstanceRestore = clone_state.get_restore_client(parsed_cluster_id=parsed_cluster_id)
    restore_client.deploy()
    deploy_body_payload = json.loads(deploy_responses[0].calls[0].request.body)
    request_headers = deploy_responses[0].calls[0].request.headers

    assert request_headers["CommandName"] == "iot ops clone"
    assert request_headers["x-ms-correlation-request-id"]
    assert deploy_body_payload["properties"]["mode"] == "Incremental"
    assert deploy_body_payload["properties"]["parameters"] == {"clusterName": {"value": parsed_cluster_id["name"]}}
    assert deploy_body_payload["properties"]["template"] == content

    write_to = ["my", "clone", "path"]
    target_path = PurePath(*write_to)
    template_content.write(target_path)
    mock_open_write.assert_called_once_with(file=f"{target_path}.json", mode="w", encoding="utf8")
    mock_open_write().write.assert_called_once_with(json.dumps(content, indent=2))


@pytest.mark.parametrize("add_dataflows", [2])
@pytest.mark.parametrize("add_dataflow_endpoints", [2])
@pytest.mark.parametrize("add_aeps", [0, 5])
@pytest.mark.parametrize("add_spcs", [0, 2])
@pytest.mark.parametrize("add_connector_templates", [0, 5])
@pytest.mark.parametrize("add_registry_endpoints", [0, 5])
@pytest.mark.parametrize("add_ns_devices", [0, 5])
@pytest.mark.parametrize("add_ns_assets", [0, 5])
@pytest.mark.parametrize("include_container_storage", [False, True])
def test_clone_manager_instance_v2(
    mocked_cmd: Mock,
    mocked_responses: responses,
    add_dataflow_endpoints: int,
    add_dataflows: int,
    add_aeps: int,
    add_spcs: int,
    add_connector_templates: int,
    add_registry_endpoints: int,
    add_ns_devices: int,
    add_ns_assets: int,
    include_container_storage: bool,
):
    model_cluster_name = generate_random_string()
    model_instance_name = generate_random_string()
    model_resource_group_name = generate_random_string()
    add_resources_map = {
        "dataflowEndpoints": add_dataflow_endpoints,
        "dataflows": add_dataflows,
        "aeps": add_aeps,
        "spcs": add_spcs,
        "connectorTemplates": add_connector_templates,
        "registryEndpoints": add_registry_endpoints,
        "nsDevices": add_ns_devices,
        "nsAssets": add_ns_assets,
        "includeContainerStorage": include_container_storage,
    }

    clone_scenario = CloneScenario()
    clone_scenario.bootstrap(
        mocked_responses,
        resource_group_name=model_resource_group_name,
        instance_name=model_instance_name,
        cluster_name=model_cluster_name,
        add_resources_map=add_resources_map,
        instance_version="1.2.0",
    )

    clone_manager = CloneManager(
        cmd=mocked_cmd,
        resource_group_name=model_resource_group_name,
        instance_name=model_instance_name,
        no_progress=True,
    )
    clone_state = clone_manager.analyze_cluster()
    template_content = clone_state.get_content()
    content = template_content.content

    CloneAssertor(clone_scenario).assert_content(content)


@pytest.mark.parametrize(
    "instance_version_test",
    [
        {"version": "1.1.50"},
        {"version": "1.1.19"},
        {"version": "1.0.34"},
        {"version": "1.3.0", "error": ValidationError},
        {"version": "2.0.0", "error": ValidationError},
        {"version": "1.0.9", "error": ValidationError},
        {"version": "1.3.0", "force": True},
        {"version": "1.0.9", "force": True},
    ],
)
@pytest.mark.parametrize("clone_scenario", [CloneScenario()])
def test_clone_instance_compat(
    mocked_cmd: Mock,
    mocked_responses: responses,
    clone_scenario: CloneScenario,
    instance_version_test: dict,
):
    model_cluster_name = generate_random_string()
    model_instance_name = generate_random_string()
    model_resource_group_name = generate_random_string()

    clone_scenario.bootstrap(
        mocked_responses,
        resource_group_name=model_resource_group_name,
        instance_name=model_instance_name,
        cluster_name=model_cluster_name,
        instance_version=instance_version_test["version"],
    )

    clone = partial(
        clone_instance,
        cmd=mocked_cmd,
        resource_group_name=model_resource_group_name,
        instance_name=model_instance_name,
        no_progress=True,
        confirm_yes=True,
    )

    expected_error = instance_version_test.get("error")
    force = instance_version_test.get("force")
    if expected_error and not force:
        mocked_responses.assert_all_requests_are_fired = False
        with pytest.raises(ValidationError) as e:
            clone()
        assert "This clone client is not compatible " in str(e.value)
        return

    clone(force=force)


LOAD_VALUE = 1000


def test_clone_scale(
    mocked_cmd: Mock,
    mocked_responses: responses,
    mock_open_write: Mock,
):
    clone_scenario = CloneScenario()
    model_cluster_name = generate_random_string()
    model_instance_name = generate_random_string()
    model_resource_group_name = generate_random_string()
    add_resources_map = {
        "listeners": 2,
        "authns": LOAD_VALUE,
        "authzs": LOAD_VALUE,
        "dataflowProfiles": 4,
        "dataflowEndpoints": LOAD_VALUE,
        "dataflows": 200,  # total=len(dataflows)*(len(profiles)+1)
        "aeps": LOAD_VALUE,
        "assets": LOAD_VALUE,
        "spcs": 10,
        "secretsyncs": 10,
        "identities": 10,
    }

    clone_scenario.bootstrap(
        mocked_responses,
        resource_group_name=model_resource_group_name,
        instance_name=model_instance_name,
        cluster_name=model_cluster_name,
        add_resources_map=add_resources_map,
    )

    clone_manager = CloneManager(
        cmd=mocked_cmd,
        resource_group_name=model_resource_group_name,
        instance_name=model_instance_name,
        no_progress=True,
    )
    clone_state = clone_manager.analyze_cluster()
    template_content = clone_state.get_content()
    content = template_content.content

    CloneAssertor(clone_scenario).assert_content(content)

    # TODO: Cheap. Not exhaustive.
    split_content = template_content.get_split_content()
    aep_pages = math.ceil(add_resources_map["aeps"] / DEPLOYMENT_CHUNK_LEN)
    asset_pages = math.ceil(add_resources_map["assets"] / DEPLOYMENT_CHUNK_LEN)
    total_pages = aep_pages + asset_pages + 1

    expected_params = deepcopy(TEMPLATE_PARAMS_SET)
    # Split content for assets/AEPs doesn't need namespace-specific parameters
    expected_params.discard("adrNamespaceLocation")
    if not clone_scenario.api_config.v2_enabled:
        expected_params.discard("adrNamespaceId")

    assert len(split_content) == total_pages
    for i in range(aep_pages):
        assert set(split_content[i + 1]["parameters"].keys()) == expected_params
        assert split_content[i + 1]["resources"][0]["type"] == "microsoft.deviceregistry/assetendpointprofiles"
    for j in range(aep_pages, aep_pages + asset_pages):
        assert set(split_content[j + 1]["parameters"].keys()) == expected_params
        assert split_content[j + 1]["resources"][0]["type"] == "microsoft.deviceregistry/assets"

    deploy_responses, to_cluster_id = clone_scenario.wrap_cluster_deploy()
    parsed_cluster_id = parse_resource_id(to_cluster_id)

    restore_client: InstanceRestore = clone_state.get_restore_client(parsed_cluster_id=parsed_cluster_id)
    restore_client.deploy()
    deploy_body_payload = json.loads(deploy_responses[0].calls[0].request.body)

    assert deploy_body_payload["properties"]["mode"] == "Incremental"
    assert deploy_body_payload["properties"]["parameters"] == {"clusterName": {"value": parsed_cluster_id["name"]}}
    assert deploy_body_payload["properties"]["template"] == content

    write_to = ["my", "clone", "path"]
    target_path = PurePath(*write_to)
    template_content.write(target_path)
    mock_open_write.assert_called_once_with(file=f"{target_path}.json", mode="w", encoding="utf8")
    mock_open_write().write.assert_called_once_with(json.dumps(content, indent=2))


@pytest.mark.parametrize("instance_features", [None, {"connectors": {"settings": {"preview": "Enabled"}, "mode": ""}}])
def test_clone_instance_feature_capture(
    mocked_cmd: Mock,
    mocked_responses: responses,
    instance_features: Optional[dict],
):
    clone_scenario = CloneScenario()
    model_cluster_name = generate_random_string()
    model_instance_name = generate_random_string()
    model_resource_group_name = generate_random_string()

    clone_scenario.bootstrap(
        mocked_responses,
        resource_group_name=model_resource_group_name,
        instance_name=model_instance_name,
        cluster_name=model_cluster_name,
        instance_features=instance_features,
    )

    deploy_responses, to_cluster_id = clone_scenario.wrap_cluster_deploy()
    clone = partial(
        clone_instance,
        cmd=mocked_cmd,
        resource_group_name=model_resource_group_name,
        instance_name=model_instance_name,
        no_progress=True,
        confirm_yes=True,
        to_cluster_id=to_cluster_id,
    )
    clone()
    deploy_body_payload = json.loads(deploy_responses[0].calls[0].request.body)
    deploy_instance = deploy_body_payload["properties"]["template"]["resources"]["instance"]
    if not instance_features:
        assert "features" not in deploy_instance["properties"]
        return

    assert deploy_instance["properties"]["features"]
    for f in instance_features:
        if not instance_features[f]["mode"]:
            assert "mode" not in deploy_instance["properties"]["features"][f]


@pytest.mark.parametrize(
    "cred_state",
    [
        {"subjects": {}},
        {"subjects": {SERVICE_ACCOUNT_SECRETSYNC}},
        {"subjects": {SERVICE_ACCOUNT_DATAFLOW}},
        {"subjects": {SERVICE_ACCOUNT_SCHEMA}},
        {"subjects": {SERVICE_ACCOUNT_DATAFLOW, SERVICE_ACCOUNT_SECRETSYNC, SERVICE_ACCOUNT_SCHEMA}},
    ],
)
@pytest.mark.parametrize("cluster_state", [{"connectivityStatus": "Connected"}, {"connectivityStatus": "Disconnected"}])
def test_clone_deploy_subjects(
    mocked_cmd: Mock,
    mocked_responses: responses,
    cred_state: dict,
    cluster_state: dict,
):
    clone_scenario = CloneScenario()
    model_cluster_name = generate_random_string()
    model_instance_name = generate_random_string()
    model_resource_group_name = generate_random_string()
    add_resources_map = {
        "aeps": 2,
        "assets": 2,
        "spcs": 2,
        "secretsyncs": 2,
        "identities": 2,
    }

    clone_scenario.bootstrap(
        mocked_responses,
        resource_group_name=model_resource_group_name,
        instance_name=model_instance_name,
        cluster_name=model_cluster_name,
        add_resources_map=add_resources_map,
    )
    clone = partial(
        clone_instance,
        cmd=mocked_cmd,
        resource_group_name=model_resource_group_name,
        instance_name=model_instance_name,
        no_progress=True,
        confirm_yes=True,
    )

    connectivity_status: str = cluster_state.get("connectivityStatus", "")
    deploy_responses, to_cluster_id = clone_scenario.wrap_cluster_deploy(
        connectivity_status=connectivity_status, cred_state=cred_state
    )
    parsed_cluster_id = parse_resource_id(to_cluster_id)
    if connectivity_status.lower() != "connected":
        with pytest.raises(ValidationError) as e:
            clone(to_cluster_id=to_cluster_id)
        assert f"Cluster {parsed_cluster_id['name']} is not connected to Azure." == str(e.value)
        return

    clone(to_cluster_id=to_cluster_id)
    deploy_body_payload = json.loads(deploy_responses[0].calls[0].request.body)
    assert deploy_body_payload["properties"]["mode"] == "Incremental"

    expected_deploy_params = {
        "clusterName": {"value": parsed_cluster_id["name"]},
    }

    assert deploy_body_payload["properties"]["parameters"] == expected_deploy_params
    assert deploy_body_payload["properties"]["template"]


@pytest.mark.parametrize(
    "params_scenario",
    [
        {
            "input": [
                f"instanceName={generate_random_string()}",
                f"clusterNamespace={generate_random_string()}",
                f"customLocationName={generate_random_string()}",
                f"opsExtensionName={generate_random_string()}",
                f"schemaRegistryId={MOCK_SR_RESOURCE_ID}",
                f"adrNamespaceId={MOCK_NS_RESOURCE_ID}",
                f"resourceSlug={generate_random_string()}",
                f"location={generate_random_string()}",
                "applyRoleAssignments=true",
            ]
        },
        {
            "input": [
                f"instanceName={generate_random_string()}",
                f"customLocationName={generate_random_string()}",
                "applyRoleAssignments=false",
            ]
        },
        {"input": ["schemaRegistryId=a"], "error": (ValidationError, "Invalid resource Id 'a'.")},
        {"input": ["adrNamespaceId=b"], "error": (ValidationError, "Invalid resource Id 'b'.")},
        {
            "input": ["applyRoleAssignments=a"],
            "error": (ValidationError, "Invalid boolean string: a. Use 'true' or 'false'."),
        },
        {
            "input": ["applyRoleAssignments="],
            "error": (ValidationError, "Boolean string requires a value. Use 'true' or 'false'."),
        },
    ],
)
def test_clone_deploy_params(
    mocked_cmd: Mock,
    mocked_responses: responses,
    params_scenario: dict,
):
    clone_scenario = CloneScenario()
    model_cluster_name = generate_random_string()
    model_instance_name = generate_random_string()
    model_resource_group_name = generate_random_string()
    add_resources_map = {
        "aeps": 2,
        "assets": 2,
        "spcs": 2,
        "secretsyncs": 2,
        "identities": 2,
    }

    clone = partial(
        clone_instance,
        cmd=mocked_cmd,
        resource_group_name=model_resource_group_name,
        instance_name=model_instance_name,
        no_progress=True,
        confirm_yes=True,
    )
    params_input = params_scenario.get("input")
    expected_error, expected_error_msg = params_scenario.get("error", (None, None))
    if expected_error:
        with pytest.raises(expected_error) as e:
            clone(
                to_cluster_id=generate_resource_id(
                    resource_group_name=model_resource_group_name,
                    resource_provider="Microsoft.Kubernetes",
                    resource_path="/connectedClusters/cluster",
                ),
                to_cluster_params=params_input,
            )
        assert str(e.value) == expected_error_msg
        return

    clone_scenario.bootstrap(
        mocked_responses,
        resource_group_name=model_resource_group_name,
        instance_name=model_instance_name,
        cluster_name=model_cluster_name,
        add_resources_map=add_resources_map,
    )

    deploy_responses, to_cluster_id = clone_scenario.wrap_cluster_deploy()
    parsed_cluster_id = parse_resource_id(to_cluster_id)

    clone(to_cluster_id=to_cluster_id, to_cluster_params=params_input)
    deploy_body_payload = json.loads(deploy_responses[0].calls[0].request.body)
    assert deploy_body_payload["properties"]["mode"] == "Incremental"

    expected_deploy_params = {
        "clusterName": {"value": parsed_cluster_id["name"]},
    }
    for param in params_input:
        key, value = param.split("=")
        if key in ["schemaRegistryId", "adrNamespaceId"]:
            parsed_sr_id = parse_resource_id(value)
            value = {
                "subscription": parsed_sr_id["subscription"],
                "name": parsed_sr_id["name"],
                "resourceGroup": parsed_sr_id["resource_group"],
            }
        if key == "applyRoleAssignments":
            value = value.lower() == "true"
        expected_deploy_params[key] = {"value": value}

    assert deploy_body_payload["properties"]["parameters"] == expected_deploy_params
    assert deploy_body_payload["properties"]["template"]


@pytest.mark.parametrize("linked_base_uri", [None, f"https://{generate_uuid()}.test"])
@pytest.mark.parametrize("template_mode", [TemplateMode.NESTED, TemplateMode.LINKED])
@pytest.mark.parametrize("add_aeps", [100, LOAD_VALUE])
@pytest.mark.parametrize("add_assets", [100, LOAD_VALUE])
@pytest.mark.parametrize("clone_scenario", [CloneScenario()])
def test_clone_to_dir(
    mocked_cmd: Mock,
    mocked_responses: responses,
    clone_scenario: CloneScenario,
    mock_open_write: Mock,
    add_aeps: int,
    add_assets: int,
    template_mode: TemplateMode,
    linked_base_uri: str,
    mock_pathlib_path: Mock,
):
    model_cluster_name = generate_random_string()
    model_instance_name = generate_random_string()
    model_resource_group_name = generate_random_string()
    add_resources_map = {
        "aeps": add_aeps,
        "assets": add_assets,
    }

    clone_scenario.bootstrap(
        mocked_responses,
        resource_group_name=model_resource_group_name,
        instance_name=model_instance_name,
        cluster_name=model_cluster_name,
        add_resources_map=add_resources_map,
    )

    clone_manager = CloneManager(
        cmd=mocked_cmd,
        resource_group_name=model_resource_group_name,
        instance_name=model_instance_name,
        no_progress=True,
    )
    clone_state = clone_manager.analyze_cluster()
    template_content = clone_state.get_content()
    content = template_content.content

    CloneAssertor(clone_scenario).assert_content(content)

    write_to = ["my", "clone", "path"]
    target_path = PurePath(*write_to)
    write_kwargs = {}
    if template_mode == TemplateMode.LINKED:
        write_kwargs["linked_base_uri"] = linked_base_uri
    template_content.write(target_path, template_mode=template_mode.value, **write_kwargs)

    if template_mode == TemplateMode.NESTED:
        mock_open_write.assert_called_once_with(file=f"{target_path}.json", mode="w", encoding="utf8")
        mock_open_write().write.assert_called_once_with(json.dumps(content, indent=2))

    if template_mode == TemplateMode.LINKED:
        assert mock_pathlib_path.mock_calls[0].args == (target_path,)
        assert mock_pathlib_path.mock_calls[1].kwargs == {"exist_ok": True}
        assert mock_open_write.call_args_list[0].kwargs == {
            "file": f"{target_path}.json",
            "mode": "w",
            "encoding": "utf8",
        }
        root_content = json.loads(mock_open_write().write.call_args_list[0].args[0])
        asset_keys = [key for key in root_content["resources"] if "asset" in key]
        for key in asset_keys:
            asset_deployment = root_content["resources"][key]
            template_link = asset_deployment["properties"]["templateLink"]
            if not linked_base_uri:
                assert template_link == {"relativePath": f"path/{key.lower()}.json"}
            else:
                assert template_link == {"uri": f"{linked_base_uri}/path/{key.lower()}.json"}

        # TODO: assert linked template content
        # json.loads(mock_open_write().write.call_args_list[1].args[0])
        aep_pages = math.ceil(add_aeps / DEPLOYMENT_CHUNK_LEN)
        for i in range(aep_pages):
            assert mock_open_write.call_args_list[i + 1].kwargs == {
                "file": f"{target_path.joinpath(f'assetendpointprofiles_{i + 1}')}.json",
                "mode": "w",
                "encoding": "utf8",
            }
        asset_pages = math.ceil(add_assets / DEPLOYMENT_CHUNK_LEN)
        for i in range(asset_pages):
            assert mock_open_write.call_args_list[aep_pages + 1 + i].kwargs == {
                "file": f"{target_path.joinpath(f'assets_{i + 1}')}.json",
                "mode": "w",
                "encoding": "utf8",
            }


EXPECTED_TEMPLATE_KEYS = {
    "$schema",
    "languageVersion",
    "contentVersion",
    "metadata",
    "parameters",
    "resources",
}
EXPECTED_METADATA_KEYS = {"opsCliVersion", "clonedInstanceId"}
EXPECTED_PARAMETER_KEYS = {
    "clusterName",
    "clusterNamespace",
    "customLocationName",
    "instanceName",
    "location",
    "opsExtensionName",
    "resourceSlug",
    "schemaRegistryId",
    "applyRoleAssignments",
}


def get_expected_ext_resource_map(v2_enabled: bool) -> dict:
    base_extension = {
        "replacements": {
            "scope": "[resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName'))]",
            "apiVersion": "2023-05-01",
        }
    }

    base_map = {}
    base_ext_moniker = EXTENSION_MONIKER_CM if v2_enabled else EXTENSION_MONIKER_PLATFORM
    base_map[base_ext_moniker] = deepcopy(base_extension)

    if not v2_enabled:
        base_map[EXTENSION_MONIKER_ACS] = {
            **deepcopy(base_extension),
            "replacements": {
                **base_extension["replacements"],
                "dependsOn": [base_ext_moniker],
            },
        }

    base_map[EXTENSION_MONIKER_SSC] = {
        **deepcopy(base_extension),
        "replacements": {
            **base_extension["replacements"],
            "dependsOn": [base_ext_moniker],
        },
    }

    iot_deps = [base_ext_moniker, EXTENSION_MONIKER_SSC]
    if not v2_enabled:
        iot_deps.insert(1, EXTENSION_MONIKER_ACS)

    base_map[EXTENSION_MONIKER_OPS] = {
        **deepcopy(base_extension),
        "replacements": {
            **base_extension["replacements"],
            "name": "[parameters('opsExtensionName')]",
            "identity": {
                "type": "SystemAssigned",
            },
            "dependsOn": iot_deps,
        },
    }

    return base_map


def _replace_cl(context: dict) -> dict:
    resource_configs = context["resource_configs"]
    v2_enabled = context.get("v2_enabled", False)

    extension_ids = []
    depends_on = []

    if v2_enabled:
        if EXT_NAME_CM in resource_configs["extensions"]:
            depends_on.append(EXTENSION_MONIKER_CM)
    else:
        if EXT_NAME_PLAT in resource_configs["extensions"]:
            depends_on.append(EXTENSION_MONIKER_PLATFORM)

    if not v2_enabled and EXT_NAME_ACS in resource_configs["extensions"]:
        depends_on.append(EXTENSION_MONIKER_ACS)

    expected_ext_names = []

    if EXT_NAME_SSC in resource_configs["extensions"]:
        expected_ext_names.append(EXT_NAME_SSC)
        depends_on.append(EXTENSION_MONIKER_SSC)

    if EXT_NAME_OPS in resource_configs["extensions"]:
        expected_ext_names.append(EXT_NAME_OPS)
        depends_on.append(EXTENSION_MONIKER_OPS)

    for ext_name in expected_ext_names:
        if ext_name == EXT_NAME_OPS:
            extension_ids.append(
                (
                    "[concat(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), "
                    "'/providers/Microsoft.KubernetesConfiguration/extensions/', parameters('opsExtensionName'))]"
                )
            )
        else:
            extension_ids.append(
                (
                    "[concat(resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName')), "
                    f"'/providers/Microsoft.KubernetesConfiguration/extensions/{ext_name}')]"
                )
            )

    return {
        "apiVersion": "2021-08-31-preview",
        "location": "[parameters('location')]",
        "name": "[parameters('customLocationName')]",
        "properties": {
            "hostResourceId": "[resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName'))]",
            "namespace": "[parameters('clusterNamespace')]",
            "displayName": "[parameters('customLocationName')]",
            "clusterExtensionIds": extension_ids,
            "authentication": {},
        },
        "dependsOn": depends_on,
    }


def _replace_instance_resource(context: dict) -> dict:
    config = context["config"]
    config_type: str = config["type"]
    config_name: str = config["name"]
    type_segment = config_type.split("/")[-1].lower()

    if type_segment in ["authentications", "authorizations", "listeners"]:
        config_name = f"/default/{config_name}"
    if type_segment in ["dataflowprofiles", "dataflowendpoints", "akriconnectortemplates", "registryendpoints"]:
        config_name = f"/{config_name}"
    if type_segment in ["dataflows"]:
        profile_name = config["id"].split("/dataflowProfiles/")[-1].split("/dataflows/")[0]
        config_name = f"/{profile_name}/{config_name}"

    return {
        "apiVersion": context["instance_api"],
        "name": f"[concat(parameters('instanceName'), '{config_name}')]",
        "extendedLocation": {
            "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
            "type": "CustomLocation",
        },
    }


def _replace_instance(context: dict):
    instance = context["resource_configs"]["instance"]
    kwargs = {}
    if "identity" in instance:
        kwargs["identity"] = {"type": "UserAssigned", "userAssignedIdentities": {}}
        for identity in instance["identity"]["userAssignedIdentities"]:
            kwargs["identity"]["userAssignedIdentities"][identity] = {}

    properties = deepcopy(instance["properties"])
    properties["schemaRegistryRef"]["resourceId"] = (
        "[resourceId(parameters('schemaRegistryId').subscription, parameters('schemaRegistryId').resourceGroup, "
        "'Microsoft.DeviceRegistry/schemaRegistries', parameters('schemaRegistryId').name)]"
    )
    v2_enabled = context.get("v2_enabled", False)
    if v2_enabled:
        namespace_resource_id = properties.get("adrNamespaceRef", {}).get("resourceId")
        if namespace_resource_id:
            properties["adrNamespaceRef"]["resourceId"] = (
                "[resourceId(parameters('adrNamespaceId').subscription, "
                "parameters('adrNamespaceId').resourceGroup, "
                "'Microsoft.DeviceRegistry/namespaces', parameters('adrNamespaceId').name)]"
            )
        spc_resource_id = properties.get("defaultSecretProviderClassRef", {}).get("resourceId")
        if spc_resource_id:
            properties["defaultSecretProviderClassRef"]["resourceId"] = (
                "[resourceId('Microsoft.SecretSyncController/azureKeyVaultSecretProviderClasses', "
                f"'{parse_resource_id(spc_resource_id)['name']}')]"
            )

    payload = {
        "apiVersion": context["instance_api"],
        "location": "[parameters('location')]",
        "name": "[parameters('instanceName')]",
        "extendedLocation": {
            "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
            "type": "CustomLocation",
        },
        "properties": properties,
        "dependsOn": ["customLocation"],
        **kwargs,
    }

    return payload


def _replace_instance_broker(context: dict):
    return {
        "apiVersion": context["instance_api"],
        "name": "[concat(parameters('instanceName'), '/default')]",
        "extendedLocation": {
            "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
            "type": "CustomLocation",
        },
        "dependsOn": ["instance"],
    }


def _replace_generic_resource(context: dict, **kwargs: dict) -> dict:
    api_version = kwargs.get("api_version")
    get_api_version_callback = kwargs.get("api_version_callback")
    get_name_callback = kwargs.get("name_callback")

    payload = {
        "apiVersion": api_version or get_api_version_callback(**context),
        "location": "[parameters('location')]",
        "extendedLocation": {
            "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
            "type": "CustomLocation",
        },
    }
    if get_name_callback:
        payload["name"] = get_name_callback(**context)

    return payload


def _get_asset_api_version(**kwargs: dict) -> str:
    v2_enabled = kwargs.get("v2_enabled", False)
    if v2_enabled:
        return DeviceRegistryMgmtApiVersion.V20251001.value
    return DeviceRegistryMgmtApiVersion.V20241101.value


def _get_ns_asset_name(**kwargs: dict) -> str:
    return f"[concat(parameters('adrNamespaceId').name, '/{kwargs['config']['name']}')]"


def _replace_namespace_asset_resource(context: dict) -> dict:
    """Replacement function for namespace devices and assets."""
    api_version = _get_asset_api_version(**context)
    payload = {
        "apiVersion": api_version,
        "location": "[parameters('adrNamespaceLocation')]",
        "extendedLocation": {
            "name": (
                "[extensionResourceId(format('/subscriptions/{0}/resourceGroups/{1}', "
                "subscription().subscriptionId, parameters('clusterResourceGroup')), "
                "'Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]"
            ),
            "type": "CustomLocation",
        },
        "name": _get_ns_asset_name(**context),
    }
    return payload


_replace_asset_resource = partial(_replace_generic_resource, api_version_callback=_get_asset_api_version)
_replace_secretsync_resource = partial(_replace_generic_resource, api_version=SECRET_SYNC_API_VERSION)


def get_expected_min_resource_map(v2_enabled: bool) -> dict:
    ext_resource_map = get_expected_ext_resource_map(v2_enabled)
    return {
        **ext_resource_map,
        "customLocation": {"replacements": _replace_cl},
        "instance": {"replacements": _replace_instance},
        "roleAssignments": {},
        "broker": {"replacements": _replace_instance_broker},
        "listeners": {"replacements": _replace_instance_resource},
        "authns": {"replacements": _replace_instance_resource},
        "authzs": {"replacements": _replace_instance_resource},
        "dataflowProfiles": {"replacements": _replace_instance_resource},
        "dataflowEndpoints": {"replacements": _replace_instance_resource},
        "dataflows": {"replacements": _replace_instance_resource},
        "connectorTemplates": {"replacements": _replace_instance_resource},
        "registryEndpoints": {"replacements": _replace_instance_resource},
        "assetEndpointProfiles": {"replacements": _replace_asset_resource},
        "assets": {"replacements": _replace_asset_resource},
        "namespaceDevices": {"replacements": _replace_namespace_asset_resource},
        "namespaceAssets": {"replacements": _replace_namespace_asset_resource},
        "secretProviderClasss": {"replacements": _replace_secretsync_resource},
        "secretSyncs": {"replacements": _replace_secretsync_resource},
    }


class CloneAssertor:
    """
    Assert content correctness.
    """

    def __init__(self, clone_scenario: CloneScenario):
        self.clone_scenario = clone_scenario
        self.resource_configs = clone_scenario.resource_configs
        self.extension_name_map = {}
        self.api_config = clone_scenario.api_config
        self.expected_min_resource_map = get_expected_min_resource_map(self.api_config.v2_enabled)
        self._assert_instance_apis()

    def assert_content(self, content: dict):
        assert isinstance(content, dict), "content should be a dictionary"
        assert set(content.keys()) == EXPECTED_TEMPLATE_KEYS, "Unexpected keys in template content"

        assert (
            content["$schema"] == "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#"
        ), "Schema mismatch"
        assert content["languageVersion"] == "2.0", "Language version mismatch"
        assert content["contentVersion"] == "1.0.0.0", "Content version mismatch"

        assert isinstance(content["metadata"], dict), "Metadata key should be a dictionary"
        assert set(content["metadata"].keys()) == EXPECTED_METADATA_KEYS, "Unexpected keys in metadata content"
        assert content["metadata"]["opsCliVersion"] == CLI_VERSION, "Ops CLI version mismatch"
        assert (
            content["metadata"]["clonedInstanceId"] == self.clone_scenario.resource_configs["instance"]["id"]
        ), "Cloned instance ID mismatch"

        assert isinstance(content["parameters"], dict), "Parameters key should be a dictionary"
        expected_parameter_key_set = EXPECTED_PARAMETER_KEYS.copy()
        if self.api_config.v2_enabled:
            expected_parameter_key_set = expected_parameter_key_set.union({"adrNamespaceId", "adrNamespaceLocation"})
        assert set(content["parameters"].keys()) == expected_parameter_key_set, "Unexpected keys in parameters content"
        assert content["parameters"]["clusterName"] == {"type": "string"}
        assert content["parameters"]["clusterNamespace"] == {
            "type": "string",
            "defaultValue": self.resource_configs["customLocation"]["properties"]["namespace"],
        }
        assert content["parameters"]["customLocationName"] == {
            "type": "string",
            "defaultValue": self.resource_configs["customLocation"]["name"],
        }
        assert content["parameters"]["instanceName"] == {
            "type": "string",
            "defaultValue": self.clone_scenario.instance_name,
        }
        assert content["parameters"]["location"] == {
            "type": "string",
            "defaultValue": self.resource_configs["instance"]["location"],
        }
        assert content["parameters"]["opsExtensionName"] == {
            "type": "string",
            "defaultValue": self.resource_configs["extensions"][EXT_NAME_OPS]["name"],
        }
        assert content["parameters"]["resourceSlug"] == {
            "type": "string",
            "defaultValue": (
                "[take(uniqueString(resourceGroup().id, parameters('clusterName'), "
                "parameters('clusterNamespace')), 5)]"
            ),
        }
        parsed_sr_id = parse_resource_id(self.resource_configs["schemaRegistryId"])
        assert content["parameters"]["schemaRegistryId"] == {
            "type": "object",
            "defaultValue": {
                "subscription": parsed_sr_id["subscription"],
                "resourceGroup": parsed_sr_id["resource_group"],
                "name": parsed_sr_id["name"],
            },
        }
        assert content["parameters"]["applyRoleAssignments"] == {
            "type": "bool",
            "defaultValue": True,
        }
        if self.api_config.v2_enabled:
            parsed_ns_id = parse_resource_id(self.resource_configs["adrNamespaceId"])
            assert content["parameters"]["adrNamespaceId"] == {
                "type": "object",
                "defaultValue": {
                    "subscription": parsed_ns_id["subscription"],
                    "resourceGroup": parsed_ns_id["resource_group"],
                    "name": parsed_ns_id["name"],
                },
            }

        self._assert_resources(content)

    def _assert_instance_apis(self):
        semver = scoped_semver_import()
        parsed_version = semver.parse(self.resource_configs["instance"]["properties"]["version"])

        target_iotops_api = None
        target_adr_api = None

        if parsed_version < semver.parse("1.1.0"):
            target_iotops_api = IoTOpsMgmtApiVersion.V20241101
            target_adr_api = DeviceRegistryMgmtApiVersion.V20241101
        elif parsed_version < semver.parse("1.2.0"):
            target_iotops_api = IoTOpsMgmtApiVersion.V20250401
            target_adr_api = DeviceRegistryMgmtApiVersion.V20241101
        elif parsed_version < semver.parse("1.3.0"):
            target_iotops_api = IoTOpsMgmtApiVersion.V20251001
            target_adr_api = DeviceRegistryMgmtApiVersion.V20251001

        assert target_iotops_api.value == self.api_config.iotops_mgmt_api
        assert target_adr_api.value == self.api_config.registry_mgmt_api

    def _assert_resources(self, content: dict):
        assert isinstance(content["resources"], dict), "Resources key should be a dictionary"
        assert content["resources"], "Resources dict should not be empty"
        resource_keys = list(content["resources"].keys())
        expected_resource_keys = self._get_expected_resource_keys()
        for i in range(len(expected_resource_keys)):
            assert (
                resource_keys[i] == expected_resource_keys[i]
            ), f"Expected resource key: {expected_resource_keys[i]} at position {i}"

        resources = content["resources"]
        self._assert_extensions(resources)
        self._assert_root_components(resources)
        self._assert_role_assignments(resources)
        self._assert_deployments(resources)

    def _get_extension_check_order(self):
        if self.api_config.v2_enabled:
            # For v2: certManager, secretStore, iotOperations (and optionally containerStorage)
            return [EXT_NAME_CM, EXT_NAME_ACS, EXT_NAME_SSC, EXT_NAME_OPS]
        else:
            # For v1: platform, containerStorage, secretStore, iotOperations
            return [EXT_NAME_PLAT, EXT_NAME_ACS, EXT_NAME_SSC, EXT_NAME_OPS]

    def _assert_extensions(self, resources: dict):
        expected_ext_resource_map = {}
        base_ext_moniker = EXTENSION_MONIKER_CM if self.api_config.v2_enabled else EXTENSION_MONIKER_PLATFORM
        base_extension_config = {
            "scope": "[resourceId('Microsoft.Kubernetes/connectedClusters', parameters('clusterName'))]",
            "apiVersion": "2023-05-01",
        }

        ext_check_order = self._get_extension_check_order()
        extension_order = []

        for ext_name in ext_check_order:
            if ext_name not in self.resource_configs["extensions"]:
                continue

            ext_moniker = EXT_NAME_TO_MONIKER[ext_name]
            replacements = deepcopy(base_extension_config)

            if ext_name == EXT_NAME_ACS:
                replacements["dependsOn"] = [base_ext_moniker]
            elif ext_name == EXT_NAME_SSC:
                replacements["dependsOn"] = [base_ext_moniker]
            elif ext_name == EXT_NAME_OPS:
                replacements["name"] = "[parameters('opsExtensionName')]"
                replacements["identity"] = {"type": "SystemAssigned"}
                deps = [base_ext_moniker, EXTENSION_MONIKER_SSC]
                if not self.api_config.v2_enabled and EXT_NAME_ACS in self.resource_configs["extensions"]:
                    deps.insert(1, EXTENSION_MONIKER_ACS)
                replacements["dependsOn"] = deps

            expected_ext_resource_map[ext_moniker] = {"replacements": replacements}
            extension_order.append(self.resource_configs["extensions"][ext_name])

        for i, (key_name, expected_meta) in enumerate(expected_ext_resource_map.items()):
            extension_config = deepcopy(extension_order[i])
            clone_replacements = expected_meta.get("replacements")
            if clone_replacements:
                extension_config.update(clone_replacements)
            self._prune_resource(extension_config)

            actual_resource = resources[key_name]
            self._assert_resource_equality(
                extension_config, actual_resource, f"Extension resource mismatch for {key_name}"
            )

    def _assert_resource_equality(self, expected: dict, actual: dict, error_msg: str):
        expected_copy = deepcopy(expected)
        actual_copy = deepcopy(actual)

        if "dependsOn" in expected_copy:
            expected_copy["dependsOn"] = set(expected_copy["dependsOn"])
        if "dependsOn" in actual_copy:
            actual_copy["dependsOn"] = set(actual_copy["dependsOn"])

        assert expected_copy == actual_copy, error_msg

    def _assert_root_components(self, resources: dict):
        keys = ["customLocation", "instance", "broker"]
        for key in keys:
            component_config = deepcopy(self.resource_configs[key])
            component_config = self._handle_component_conversion(component_config, key)
            self._assert_resource_equality(component_config, resources[key], f"Root resource mismatch for {key}")

    def _handle_component_conversion(self, component_config: dict, conversion_map_key: str) -> dict:
        """
        This method is responsible for taking resources returned from APIs and converting them to the expected format.
        It does generally via callback strategy, where are arranged in the EXPECTED_ORD_MIN_RESOURCE_MAP.
        """
        component_meta: dict = self.expected_min_resource_map[conversion_map_key]
        component_replacements = component_meta.get("replacements")
        if component_replacements:
            if callable(component_replacements):
                context = {
                    "config": component_config,
                    "resource_configs": self.resource_configs,
                    "instance_api": self.api_config.iotops_mgmt_api,
                    "v2_enabled": self.api_config.v2_enabled,
                }
                component_replacements = component_replacements(context)
            component_config.update(component_replacements)
        self._prune_resource(component_config)
        return component_config

    def _assert_role_assignments(self, resources: dict):
        key = "roleAssignments_1"

        deployment = resources[key]
        self._assert_deployment_generic(
            deployment,
            key,
            resource_group="[parameters('schemaRegistryId').resourceGroup]",
            depends_on=["iotOperations"],
        )
        assert deployment["condition"] == "[parameters('applyRoleAssignments')]"
        dep_props = deployment["properties"]
        dep_props["parameters"] = {
            "clusterName": {"value": "[parameters('clusterName')]"},
            "instanceName": {"value": "[parameters('instanceName')]"},
            "principalId": {"value": "[reference('iotOperations', '2023-05-01', 'Full').identity.principalId]"},
            "schemaRegistryId": {"value": "[parameters('schemaRegistryId')]"},
        }
        template = deployment["properties"]["template"]
        assert template["$schema"] == "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#"
        assert template["contentVersion"] == "1.0.0.0"
        assert template["parameters"] == {
            "clusterName": {"type": "string"},
            "instanceName": {"type": "string"},
            "principalId": {"type": "string"},
            "schemaRegistryId": {"type": "object"},
        }
        assert isinstance(template["resources"], list), "Deployment resources key should be a list"
        assert len(template["resources"]) == 1
        sr_ra_def = template["resources"][0]
        assert sr_ra_def["type"] == "Microsoft.Authorization/roleAssignments"
        assert sr_ra_def["apiVersion"] == "2022-04-01"
        assert sr_ra_def["name"] == (
            "[guid(parameters('instanceName'), parameters('clusterName'), "
            "parameters('principalId'), resourceGroup().id)]"
        )
        assert sr_ra_def["scope"] == (
            "[resourceId(parameters('schemaRegistryId').subscription, parameters('schemaRegistryId').resourceGroup, "
            "'Microsoft.DeviceRegistry/schemaRegistries', parameters('schemaRegistryId').name)]"
        )
        assert sr_ra_def["properties"]["roleDefinitionId"] == (
            "[subscriptionResourceId('Microsoft.Authorization/roleDefinitions', "
            "'b24988ac-6180-42a0-ab88-20f7382dd24c')]"
        )
        assert sr_ra_def["properties"]["principalId"] == "[parameters('principalId')]"
        assert sr_ra_def["properties"]["principalType"] == "ServicePrincipal"

    def _assert_deployments(self, resources: dict):
        template_fetched_keys = defaultdict(list)
        for deployment_key, resource_config_key, depends_on in self._get_deployment_key_pairs():
            deployment = resources[deployment_key]
            self._assert_deployment_generic(
                deployment=deployment,
                expected_name=deployment_key,
                resource_key=resource_config_key,
                depends_on=depends_on,
            )
            template = deployment["properties"]["template"]
            assert (
                template["$schema"] == "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#"
            )
            assert template["contentVersion"] == "1.0.0.0"
            expected_parameters = {"customLocationName": {"type": "string"}}
            if resource_config_key not in [
                "namespaceDevices",
                "namespaceAssets",
                "assetEndpointProfiles",
                "assets",
                "secretProviderClasss",
                "secretSyncs",
            ]:
                expected_parameters["instanceName"] = {"type": "string"}
            else:
                if resource_config_key in ["namespaceAssets", "namespaceDevices"]:
                    expected_parameters["adrNamespaceLocation"] = {"type": "string"}
                    expected_parameters["adrNamespaceId"] = {"type": "object"}
                    expected_parameters["clusterResourceGroup"] = {"type": "string"}
                else:
                    expected_parameters["location"] = {"type": "string"}

            assert template["parameters"] == expected_parameters
            assert isinstance(template["resources"], list), "Deployment resources key should be a list"
            deployment_resources = template["resources"]
            deployment_resources_len = len(deployment_resources)

            continue_from = len(template_fetched_keys[resource_config_key])

            for i in range(deployment_resources_len):
                template_fetched_keys[resource_config_key].append(deployment_resources[i])
                model_config = deepcopy(self.resource_configs[resource_config_key][continue_from + i])
                self._handle_component_conversion(model_config, resource_config_key)
                assert model_config == deployment_resources[i]

        for key in template_fetched_keys:
            assert len(template_fetched_keys[key]) == len(
                self.resource_configs[key]
            ), f"Mismatch in resource count for {key}"

    # TODO: rewrite this function.
    def _get_deployment_key_pairs(self) -> List[Tuple[str, str, List[str]]]:
        payload = []
        dep_map = {
            "listeners": ["authns", "authzs"],
            "dataflows": ["dataflowProfiles", "dataflowEndpoints"],
            "assets": ["assetEndpointProfiles"],
            "assetEndpointProfiles": ["listeners", "instance"],
            "secretSyncs": ["secretProviderClasss"],
            "connectorTemplates": ["instance"],
            "registryEndpoints": ["instance"],
            "namespaceAssets": ["namespaceDevices"],
            "namespaceDevices": ["listeners", "instance"],
        }
        chunks_map = defaultdict(dict)

        broker_related = {"listeners", "authns", "authzs"}

        for plural in PLURALS:
            kind_len = len(self.resource_configs[plural])
            if not kind_len:
                continue
            chunks = math.ceil(kind_len / DEPLOYMENT_CHUNK_LEN)
            chunks_map[plural] = chunks

        for plural in PLURALS:
            if not self.resource_configs[plural]:
                continue
            depends_on = []
            if plural in dep_map:
                for dep in dep_map[plural]:
                    if dep == "instance":
                        depends_on.append(
                            "[resourceId('microsoft.iotoperations/instances', parameters('instanceName'))]"
                        )
                    elif dep in chunks_map:
                        # Namespace assets use cross-RG dependency on namespace devices
                        if plural == "namespaceAssets" and dep == "namespaceDevices":
                            depends_on.append(
                                "[extensionResourceId("
                                "format('/subscriptions/{0}/resourceGroups/{1}', "
                                "parameters('adrNamespaceId').subscription, "
                                "parameters('adrNamespaceId').resourceGroup), "
                                "'Microsoft.Resources/deployments', "
                                f"concat(parameters('resourceSlug'), '_{dep}_{chunks_map[dep]}'))]"
                            )
                        else:
                            depends_on.append(
                                "[resourceId('Microsoft.Resources/deployments', "
                                f"concat(parameters('resourceSlug'), '_{dep}_{chunks_map[dep]}'))]"
                            )
            elif plural in broker_related:
                depends_on.append(
                    "[resourceId('microsoft.iotoperations/instances/brokers', parameters('instanceName'), 'default')]"
                )
            else:
                depends_on.append("[resourceId('microsoft.iotoperations/instances', parameters('instanceName'))]")

            if plural in ["assets"]:
                if not self.resource_configs.get("assetEndpointProfiles"):
                    continue

            if plural in ["namespaceAssets"]:
                if not self.resource_configs.get("namespaceDevices"):
                    continue

            if plural in ["secretSyncs"]:
                if not self.resource_configs.get("secretProviderClasss"):
                    continue

            for i in range(chunks_map[plural]):
                paged_key = f"{plural}_{i + 1}"
                payload.append((paged_key, plural, depends_on))

        return payload

    def _get_expected_resource_keys(self):
        resource_keys = []

        ext_check_order = self._get_extension_check_order()
        ext_keys = []
        for ext_name in ext_check_order:
            if ext_name in self.resource_configs["extensions"]:
                ext_keys.append(EXT_NAME_TO_MONIKER[ext_name])

        enumerate_through = [*PLURALS]

        for r in enumerate_through:
            if r == "assets" and not self.resource_configs.get("assetEndpointProfiles"):
                continue
            if r == "namespaceAssets" and not self.resource_configs.get("namespaceDevices"):
                continue
            if r == "secretSyncs" and not self.resource_configs.get("secretProviderClasss"):
                continue
            kind_len = len(self.resource_configs[r])
            if not kind_len:
                continue
            chunks = math.ceil(kind_len / DEPLOYMENT_CHUNK_LEN)

            for i in range(chunks):
                paged_key = f"{r}_{i + 1}"
                resource_keys.append(paged_key)

        resource_keys = [*ext_keys, *SINGLETONS] + resource_keys

        return resource_keys

    def _assert_deployment_generic(
        self,
        deployment: dict,
        expected_name: str,
        resource_key: Optional[str] = None,
        resource_group: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
    ):
        assert deployment["type"] == "Microsoft.Resources/deployments"
        assert deployment["apiVersion"] == "2022-09-01"
        assert deployment["name"] == f"[concat(parameters('resourceSlug'), '_{expected_name}')]"
        assert deployment["properties"]["mode"] == "Incremental"

        if resource_key:
            expected_params = {
                "customLocationName": {"value": "[parameters('customLocationName')]"},
            }
            if resource_key not in [
                "namespaceDevices",
                "namespaceAssets",
                "assetEndpointProfiles",
                "assets",
                "secretProviderClasss",
                "secretSyncs",
            ]:
                expected_params["instanceName"] = {"value": "[parameters('instanceName')]"}
            else:
                if resource_key in ["namespaceDevices", "namespaceAssets"]:
                    expected_params["adrNamespaceId"] = {"value": "[parameters('adrNamespaceId')]"}
                    expected_params["adrNamespaceLocation"] = {"value": "[parameters('adrNamespaceLocation')]"}
                    expected_params["clusterResourceGroup"] = {"value": "[resourceGroup().name]"}
                else:
                    expected_params["location"] = {"value": "[parameters('location')]"}

            assert deployment["properties"]["parameters"] == expected_params

        if resource_group:
            assert deployment["resourceGroup"] == resource_group
        if depends_on:
            assert set(deployment.get("dependsOn", [])) == set(depends_on)

    def _prune_resource(self, resource: dict):
        resource.pop("id", None)
        resource.pop("systemData", None)
        if "properties" in resource:
            resource["properties"].pop("provisioningState", None)
            resource["properties"].pop("status", None)
