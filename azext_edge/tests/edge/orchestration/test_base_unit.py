# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from unittest.mock import Mock

import pytest
from azure.cli.core.azclierror import ValidationError
from azure.core.exceptions import HttpResponseError

from azext_edge.edge.providers.orchestration.connected_cluster import ConnectedCluster

from ...generators import generate_random_string, get_zeroed_subscription

BASE_PATH = "azext_edge.edge.providers.orchestration.base"
ZEROED_SUB = get_zeroed_subscription()


@pytest.fixture
def mocked_get_tenant_id(mocker):
    yield mocker.patch(f"{BASE_PATH}.get_tenant_id", return_value=generate_random_string())


@pytest.mark.parametrize(
    "test_scenario",
    [
        {  # fail no config map
            "failure": True,
            "config_map": None,
        },
        {  # fail config indicates diff cluster
            "failure": "cluster name",
            "config_map": {
                "apiVersion": "v1",
                "data": {
                    "AZURE_RESOURCE_NAME": "cluster2",
                    "AZURE_RESOURCE_GROUP": "rg1",
                    "AZURE_SUBSCRIPTION_ID": ZEROED_SUB,
                },
                "metadata": {
                    "name": "azure-clusterconfig",
                    "namespace": "azure-arc",
                },
            },
        },
        {  # fail config indicates diff rg
            "failure": "resource group",
            "config_map": {
                "apiVersion": "v1",
                "data": {
                    "AZURE_RESOURCE_NAME": "cluster1",
                    "AZURE_RESOURCE_GROUP": "rg2",
                    "AZURE_SUBSCRIPTION_ID": ZEROED_SUB,
                },
                "metadata": {
                    "name": "azure-clusterconfig",
                    "namespace": "azure-arc",
                },
            },
        },
        {  # fail config indicates diff sub
            "failure": "subscription Id",
            "config_map": {
                "apiVersion": "v1",
                "data": {
                    "AZURE_RESOURCE_NAME": "cluster1",
                    "AZURE_RESOURCE_GROUP": "rg1",
                    "AZURE_SUBSCRIPTION_ID": "8757c60a-a398-4c09-adaf-be328caf42d4",
                },
                "metadata": {
                    "name": "azure-clusterconfig",
                    "namespace": "azure-arc",
                },
            },
        },
        {  # success
            "failure": False,
            "config_map": {
                "apiVersion": "v1",
                "data": {
                    "AZURE_RESOURCE_NAME": "cluster1",
                    "AZURE_RESOURCE_GROUP": "rg1",
                    "AZURE_SUBSCRIPTION_ID": ZEROED_SUB,
                },
                "metadata": {
                    "name": "azure-clusterconfig",
                    "namespace": "azure-arc",
                },
            },
        },
    ],
)
def test_verify_arc_cluster_config(mocker, mocked_cmd, test_scenario):
    get_config_map_patch = mocker.patch(f"{BASE_PATH}.get_config_map", return_value=test_scenario["config_map"])
    from azext_edge.edge.providers.orchestration.base import verify_arc_cluster_config

    connected_cluster = ConnectedCluster(
        cmd=mocked_cmd,
        subscription_id=ZEROED_SUB,
        cluster_name="cluster1",
        resource_group_name="rg1",
    )

    failure = test_scenario["failure"]
    if failure:
        match_str = ""
        if isinstance(failure, str):
            match_str = failure
        with pytest.raises(ValidationError, match=rf".*{match_str}.*"):
            verify_arc_cluster_config(connected_cluster)
            get_config_map_patch.assert_called_once()
        return

    verify_arc_cluster_config(connected_cluster)
    get_config_map_patch.assert_called_once()


@pytest.mark.parametrize(
    "custom_location_name, namespace, get_cl_for_np_return_value",
    [
        ("mycl", "mynamespace", None),
        ("mycl", "mynamespace", {"name": "mycl"}),
        ("mycl", "mynamespace", {"name": "othercl"}),
    ],
)
def test_verify_custom_location_namespace(
    mocker, mocked_cmd, custom_location_name, namespace, get_cl_for_np_return_value
):
    mocked_get_custom_location_for_namespace = mocker.patch(
        "azext_edge.edge.providers.orchestration.connected_cluster.ConnectedCluster.get_custom_location_for_namespace"
    )
    mocked_get_custom_location_for_namespace.return_value = get_cl_for_np_return_value

    connected_cluster = ConnectedCluster(
        cmd=mocked_cmd,
        subscription_id=ZEROED_SUB,
        cluster_name="cluster1",
        resource_group_name="rg1",
    )

    from azext_edge.edge.providers.orchestration.base import (
        verify_custom_location_namespace,
    )

    if get_cl_for_np_return_value and get_cl_for_np_return_value["name"] != custom_location_name:
        with pytest.raises(ValidationError) as ve:
            verify_custom_location_namespace(
                connected_cluster=connected_cluster, custom_location_name=custom_location_name, namespace=namespace
            )
        assert (
            f"The intended namespace for deployment: {namespace}, is already referenced "
            f"by custom location: {get_cl_for_np_return_value['name']}" in str(ve.value)
        )
        return

    verify_custom_location_namespace(
        connected_cluster=connected_cluster, custom_location_name=custom_location_name, namespace=namespace
    )


class TestRegisterProviders:
    @pytest.fixture
    def mocked_resource_client(self, mocker) -> Mock:
        return mocker.patch("azext_edge.edge.providers.orchestration.rp_namespace.get_resource_client")

    @pytest.fixture
    def rp_constants(self):
        from azext_edge.edge.providers.orchestration.rp_namespace import (
            RP_NAMESPACE_SET,
            RP_NAMESPACE_OPTIONAL_SET,
        )

        return {
            "required": RP_NAMESPACE_SET,
            "optional": RP_NAMESPACE_OPTIONAL_SET,
            "all": RP_NAMESPACE_SET | RP_NAMESPACE_OPTIONAL_SET,
        }

    def _build_providers(self, namespaces, state: str) -> dict:
        return {ns: state for ns in namespaces}

    def _setup_client(self, mocked_resource_client, providers: dict):
        mocked_resource_client().providers.list.return_value = [
            {"namespace": ns, "registrationState": state} for ns, state in providers.items()
        ]

    def _get_registered_rps(self, mocked_resource_client) -> set:
        return {call.args[0] for call in mocked_resource_client().providers.register.call_args_list}

    @pytest.mark.parametrize("state", ["Registered", "registered", "Registering", "registering"])
    def test_skips_already_registered(self, mocked_resource_client, rp_constants, state):
        from azext_edge.edge.providers.orchestration.rp_namespace import register_providers

        self._setup_client(mocked_resource_client, self._build_providers(rp_constants["all"], state))

        result = register_providers(ZEROED_SUB)

        mocked_resource_client().providers.list.assert_called_once()
        mocked_resource_client().providers.register.assert_not_called()
        assert result == set()

    @pytest.mark.parametrize("state", ["NotRegistered", "Unregistered", ""])
    def test_registers_unregistered_rps(self, mocked_resource_client, rp_constants, state):
        from azext_edge.edge.providers.orchestration.rp_namespace import register_providers

        self._setup_client(mocked_resource_client, self._build_providers(rp_constants["all"], state))

        result = register_providers(ZEROED_SUB)

        assert mocked_resource_client().providers.register.call_count == len(rp_constants["all"])
        registered_rps = self._get_registered_rps(mocked_resource_client)
        assert registered_rps == rp_constants["all"]
        assert result == set()

    def test_required_rp_failure_raises(self, mocked_resource_client, rp_constants):
        from azext_edge.edge.providers.orchestration.rp_namespace import register_providers

        self._setup_client(mocked_resource_client, self._build_providers(rp_constants["all"], "NotRegistered"))
        mocked_resource_client().providers.register.side_effect = HttpResponseError("Permission denied")

        with pytest.raises(HttpResponseError, match="Permission denied"):
            register_providers(ZEROED_SUB)

    def test_optional_rp_failure_returns_failed_set(self, mocked_resource_client, rp_constants):
        from azext_edge.edge.providers.orchestration.rp_namespace import register_providers

        self._setup_client(mocked_resource_client, self._build_providers(rp_constants["all"], "NotRegistered"))

        def fail_optional_only(namespace):
            if namespace in rp_constants["optional"]:
                raise HttpResponseError("Permission denied")

        mocked_resource_client().providers.register.side_effect = fail_optional_only

        result = register_providers(ZEROED_SUB)

        registered_rps = self._get_registered_rps(mocked_resource_client)
        assert registered_rps == rp_constants["all"]
        assert result == rp_constants["optional"]
        assert result.isdisjoint(rp_constants["required"])

    def test_missing_rps_attempt_registration(self, mocked_resource_client, rp_constants):
        """RPs not in the providers list get empty state, triggering registration."""
        from azext_edge.edge.providers.orchestration.rp_namespace import register_providers

        self._setup_client(mocked_resource_client, {})

        result = register_providers(ZEROED_SUB)

        registered_rps = self._get_registered_rps(mocked_resource_client)
        assert registered_rps == rp_constants["all"]
        assert result == set()

    def test_missing_optional_rp_failure_returns_failed(self, mocked_resource_client, rp_constants):
        from azext_edge.edge.providers.orchestration.rp_namespace import register_providers

        self._setup_client(mocked_resource_client, self._build_providers(rp_constants["required"], "Registered"))

        def fail_optional_only(namespace):
            if namespace in rp_constants["optional"]:
                raise HttpResponseError("Permission denied")

        mocked_resource_client().providers.register.side_effect = fail_optional_only

        result = register_providers(ZEROED_SUB)

        registered_rps = self._get_registered_rps(mocked_resource_client)
        assert registered_rps == rp_constants["optional"]
        assert result == rp_constants["optional"]

    def test_single_rp_only_registers_that_rp(self, mocked_resource_client):
        from azext_edge.edge.providers.orchestration.rp_namespace import register_providers

        target_rp = "Microsoft.DeviceRegistry"
        self._setup_client(mocked_resource_client, {target_rp: "NotRegistered"})

        result = register_providers(ZEROED_SUB, resource_provider=target_rp)

        mocked_resource_client().providers.register.assert_called_once_with(target_rp)
        assert result == set()

    def test_single_rp_skips_if_registered(self, mocked_resource_client):
        from azext_edge.edge.providers.orchestration.rp_namespace import register_providers

        target_rp = "Microsoft.DeviceRegistry"
        self._setup_client(mocked_resource_client, {target_rp: "Registered"})

        result = register_providers(ZEROED_SUB, resource_provider=target_rp)

        mocked_resource_client().providers.register.assert_not_called()
        assert result == set()

    def test_single_rp_failure_raises(self, mocked_resource_client):
        from azext_edge.edge.providers.orchestration.rp_namespace import register_providers

        target_rp = "Microsoft.DeviceRegistry"
        self._setup_client(mocked_resource_client, {target_rp: "NotRegistered"})
        mocked_resource_client().providers.register.side_effect = HttpResponseError("Permission denied")

        with pytest.raises(HttpResponseError, match="Permission denied"):
            register_providers(ZEROED_SUB, resource_provider=target_rp)

    def test_single_rp_missing_attempts_registration(self, mocked_resource_client):
        from azext_edge.edge.providers.orchestration.rp_namespace import register_providers

        target_rp = "Microsoft.DeviceRegistry"
        self._setup_client(mocked_resource_client, {})

        result = register_providers(ZEROED_SUB, resource_provider=target_rp)

        mocked_resource_client().providers.register.assert_called_once_with(target_rp)
        assert result == set()

    def test_required_rps_registered_before_optional(self, mocked_resource_client, rp_constants):
        """Required RPs are processed first to fail fast if they can't be registered."""
        from azext_edge.edge.providers.orchestration.rp_namespace import register_providers

        self._setup_client(mocked_resource_client, self._build_providers(rp_constants["all"], "NotRegistered"))
        call_order = []
        mocked_resource_client().providers.register.side_effect = lambda ns: call_order.append(ns)

        register_providers(ZEROED_SUB)

        required_indices = [call_order.index(rp) for rp in rp_constants["required"]]
        optional_indices = [call_order.index(rp) for rp in rp_constants["optional"]]
        assert max(required_indices) < min(optional_indices)

    def test_subscription_id_passed_to_client(self, mocked_resource_client, rp_constants):
        from azext_edge.edge.providers.orchestration.rp_namespace import register_providers

        self._setup_client(mocked_resource_client, self._build_providers(rp_constants["all"], "Registered"))
        test_sub = "test-subscription-id-12345"

        register_providers(test_sub)

        mocked_resource_client.assert_any_call(subscription_id=test_sub)

    def test_mixed_registration_states(self, mocked_resource_client):
        """Only RPs not in Registered/Registering state trigger registration."""
        from azext_edge.edge.providers.orchestration.rp_namespace import register_providers

        providers = {
            "Microsoft.IoTOperations": "Registered",
            "Microsoft.SecretSyncController": "NotRegistered",
            "Microsoft.DeviceRegistry": "Registering",
            "Microsoft.ResourceHealth": "NotRegistered",
        }

        self._setup_client(mocked_resource_client, providers)
        result = register_providers(ZEROED_SUB)

        registered_rps = self._get_registered_rps(mocked_resource_client)
        assert registered_rps == {"Microsoft.SecretSyncController", "Microsoft.ResourceHealth"}
        assert result == set()


class TestNeedsRegistration:
    @pytest.mark.parametrize("state,expected", [
        ("Registered", False),
        ("registered", False),
        ("REGISTERED", False),
        ("Registering", False),
        ("registering", False),
        ("REGISTERING", False),
        ("NotRegistered", True),
        ("Unregistered", True),
        ("", True),
        ("Failed", True),
        ("Unknown", True),
    ])
    def test_needs_registration_states(self, state, expected):
        from azext_edge.edge.providers.orchestration.rp_namespace import _needs_registration

        assert _needs_registration(state) == expected
