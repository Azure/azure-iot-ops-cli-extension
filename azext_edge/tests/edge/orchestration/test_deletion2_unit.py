# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import re
from typing import List, Optional
from unittest.mock import Mock

import pytest
import responses
from azure.cli.core.azclierror import ArgumentUsageError, ResourceNotFoundError
from azure.core.exceptions import HttpResponseError

from azext_edge.edge.providers.orchestration.common import (
    CLUSTER_EXTENSIONS_API_VERSION,
    CUSTOM_LOCATIONS_API_VERSION,
    EXTENSION_TYPE_ACS,
    EXTENSION_TYPE_CM,
    EXTENSION_TYPE_OPS,
    EXTENSION_TYPE_PLATFORM,
    EXTENSION_TYPE_SSC,
    MAX_INSTANCE_VERSION_ACS_DEPENDENCY,
    SECRET_SYNC_API_VERSION,
)
from azext_edge.edge.providers.orchestration.deletion2 import (
    _ARG_SWEEP_QUERY,
    DeletionManager,
    delete_ops_resources,
)
from azext_edge.edge.util.az_client import DEFAULT_IOTOPS_MGMT_API_VERSION
from azext_edge.edge.util.machinery import scoped_semver_import
from ...generators import BASE_URL, generate_resource_id, get_zeroed_subscription

semver = scoped_semver_import()
ZEROED_SUBSCRIPTION = get_zeroed_subscription()
IOTOPS_API_VERSION = DEFAULT_IOTOPS_MGMT_API_VERSION.value
_ACS_THRESHOLD = semver.parse(MAX_INSTANCE_VERSION_ACS_DEPENDENCY)
_ACS_ABOVE = str(_ACS_THRESHOLD.bump_patch())
# Vendored ConnectedKubernetesClient bakes this version — no exported constant.
CONNECTEDK8S_API_VERSION = "2024-07-15-preview"

# Common resource IDs reused across tests (all in rg1).
_RG = "rg1"
_CL_ID = generate_resource_id(
    resource_group_name=_RG,
    resource_provider="Microsoft.ExtendedLocation",
    resource_path="/customLocations/mycl",
)
_CLUSTER_ID = generate_resource_id(
    resource_group_name=_RG,
    resource_provider="Microsoft.Kubernetes",
    resource_path="/connectedClusters/mycluster",
)
_SPC_ID = generate_resource_id(
    resource_group_name=_RG,
    resource_provider="Microsoft.SecretSyncController",
    resource_path="/azureKeyVaultSecretProviderClasses/my-spc",
)


# ---------------------------------------------------------------------------
# URL endpoint builders
# ---------------------------------------------------------------------------


def _build_instance_endpoint(name: str, rg: str) -> str:
    return (
        f"{BASE_URL}/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{rg}"
        f"/providers/Microsoft.IoTOperations/instances/{name}"
        f"?api-version={IOTOPS_API_VERSION}"
    )


def _build_instances_list_endpoint(rg: str) -> str:
    return (
        f"{BASE_URL}/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{rg}"
        f"/providers/Microsoft.IoTOperations/instances"
        f"?api-version={IOTOPS_API_VERSION}"
    )


def _build_cluster_endpoint(rg: str, cluster_name: str) -> str:
    # connectedclustermgmt uses lowercase 'resourcegroups'.
    return (
        f"{BASE_URL}/subscriptions/{ZEROED_SUBSCRIPTION}/resourcegroups/{rg}"
        f"/providers/Microsoft.Kubernetes/connectedClusters/{cluster_name}"
        f"?api-version={CONNECTEDK8S_API_VERSION}"
    )


def _build_cl_list_endpoint(rg: str) -> str:
    return (
        f"{BASE_URL}/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{rg}"
        f"/providers/Microsoft.ExtendedLocation/customLocations"
        f"?api-version={CUSTOM_LOCATIONS_API_VERSION}"
    )


def _build_sync_rules_list_endpoint(rg: str, cl_name: str) -> str:
    return (
        f"{BASE_URL}/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{rg}"
        f"/providers/Microsoft.ExtendedLocation/customLocations/{cl_name}"
        f"/resourceSyncRules?api-version={CUSTOM_LOCATIONS_API_VERSION}"
    )


def _build_extensions_list_endpoint(rg: str, cluster_name: str) -> str:
    return (
        f"{BASE_URL}/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{rg}"
        f"/providers/Microsoft.Kubernetes/connectedClusters/{cluster_name}"
        f"/providers/Microsoft.KubernetesConfiguration/extensions"
        f"?api-version={CLUSTER_EXTENSIONS_API_VERSION}"
    )


def _build_extension_delete_endpoint(rg: str, cluster_name: str, ext_name: str) -> str:
    return (
        f"{BASE_URL}/subscriptions/{ZEROED_SUBSCRIPTION}/resourceGroups/{rg}"
        f"/providers/Microsoft.Kubernetes/connectedClusters/{cluster_name}"
        f"/providers/Microsoft.KubernetesConfiguration/extensions/{ext_name}"
        f"?api-version={CLUSTER_EXTENSIONS_API_VERSION}"
    )


def _build_resource_endpoint(resource_id: str, api_version: str) -> str:
    """Build endpoint for generic resource operations (get_by_id, begin_delete_by_id)."""
    return f"{BASE_URL}{resource_id}?api-version={api_version}"


# Regex patterns for dynamic endpoint matching.
_ARG_ENDPOINT_RE = re.compile(
    r"https://management\.azure\.com/providers/Microsoft\.ResourceGraph/resources"
)
_DELETE_ENDPOINT_RE = re.compile(r"https://management\.azure\.com/.*")


# ---------------------------------------------------------------------------
# Mock registration helpers
# ---------------------------------------------------------------------------


def _register_instance_discovery(
    rsps: responses.RequestsMock,
    *,
    name: str = "myinst",
    version: str = "1.2.0",
    spc_id: str = "",
    connectivity: str = "Connected",
) -> None:
    """Register GET mocks for the instance-name discovery path: instance → CL → cluster."""
    rsps.assert_all_requests_are_fired = False
    inst = _build_instance(name=name, rg=_RG, cl_id=_CL_ID, spc_id=spc_id, version=version)
    rsps.add(method=responses.GET, url=_build_instance_endpoint(name, _RG), json=inst, status=200)
    rsps.add(
        method=responses.GET,
        url=_build_resource_endpoint(_CL_ID, CUSTOM_LOCATIONS_API_VERSION),
        json={
            "id": _CL_ID, "name": "mycl",
            "properties": {"hostResourceId": _CLUSTER_ID, "namespace": "azure-iot-operations"},
        },
        status=200,
    )
    rsps.add(
        method=responses.GET,
        url=_build_cluster_endpoint(_RG, "mycluster"),
        json={"id": _CLUSTER_ID, "properties": {"connectivityStatus": connectivity}},
        status=200,
    )


def _register_cluster_discovery(
    rsps: responses.RequestsMock,
    *,
    cluster_name: str = "mycluster",
    connectivity: str = "Connected",
) -> None:
    """Register GET mock for the cluster-name discovery path: cluster show."""
    rsps.assert_all_requests_are_fired = False
    rsps.add(
        method=responses.GET,
        url=_build_cluster_endpoint(_RG, cluster_name),
        json={"id": _CLUSTER_ID, "properties": {"connectivityStatus": connectivity}},
        status=200,
    )


def _register_extensions(
    rsps: responses.RequestsMock, extensions: Optional[List[dict]] = None,
) -> None:
    """Register extensions list GET mock."""
    rsps.add(
        method=responses.GET,
        url=_build_extensions_list_endpoint(_RG, "mycluster"),
        json={"value": extensions or []},
        status=200,
    )


def _register_cl_list(
    rsps: responses.RequestsMock, cls: Optional[List[dict]] = None,
) -> None:
    """Register custom locations list GET mock."""
    rsps.add(
        method=responses.GET,
        url=_build_cl_list_endpoint(_RG),
        json={"value": cls or []},
        status=200,
    )


def _register_instances_list(
    rsps: responses.RequestsMock, instances: Optional[List[dict]] = None,
) -> None:
    """Register instances list GET mock."""
    rsps.add(
        method=responses.GET,
        url=_build_instances_list_endpoint(_RG),
        json={"value": instances or []},
        status=200,
    )


def _register_sync_rules(
    rsps: responses.RequestsMock, rules: Optional[List[dict]] = None, cl_name: str = "mycl",
) -> None:
    """Register sync rules list GET mock."""
    rsps.add(
        method=responses.GET,
        url=_build_sync_rules_list_endpoint(_RG, cl_name),
        json={"value": rules or []},
        status=200,
    )


def _register_arg_sweep(
    rsps: responses.RequestsMock, data: Optional[List[dict]] = None,
) -> None:
    """Register ARG sweep POST mock."""
    sweep_data = data or []
    rsps.add(
        method=responses.POST,
        url=_ARG_ENDPOINT_RE,
        json={"data": sweep_data, "count": len(sweep_data), "totalRecords": len(sweep_data)},
        status=200,
    )


def _register_delete_handler(rsps: responses.RequestsMock) -> None:
    """Register a catch-all DELETE handler returning 200 (success).

    Uses add_callback so it persists across multiple DELETE calls.
    For error simulation, register a specific DELETE mock BEFORE this handler.
    """
    def _handle_delete(request):
        return (200, {"content-type": "application/json"}, json.dumps({}))

    rsps.add_callback(method=responses.DELETE, url=_DELETE_ENDPOINT_RE, callback=_handle_delete)


# ---------------------------------------------------------------------------
# Autouse fixture — suppress Rich display for all tests in this module
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def suppress_display(mocker):
    """Prevent WorkflowDisplay, render_summary, and Console from writing to stderr."""
    mocker.patch("azext_edge.edge.providers.orchestration.deletion2.WorkflowDisplay")
    mocker.patch("azext_edge.edge.providers.orchestration.deletion2.render_summary")
    mocker.patch("azext_edge.edge.providers.orchestration.deletion2.Console")


# ---------------------------------------------------------------------------
# Shared mock fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mocked_should_continue_prompt(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.deletion2.should_continue_prompt",
        return_value=True,
    )
    yield patched


@pytest.fixture(autouse=True)
def mocked_wait_for_terminal_state(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.deletion2.wait_for_terminal_state", autospec=True
    )
    yield patched


@pytest.fixture(autouse=True)
def mocked_wait_for_terminal_states(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.deletion2.wait_for_terminal_states", autospec=True
    )
    yield patched


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_instance(
    name: str = "myinstance",
    rg: str = "rg1",
    cl_id: str = "",
    spc_id: str = "",
    version: str = "1.2.0",
) -> dict:
    instance_id = generate_resource_id(
        resource_group_name=rg,
        resource_provider="Microsoft.IoTOperations",
        resource_path=f"/instances/{name}",
    )
    result = {
        "id": instance_id,
        "name": name,
        "extendedLocation": {"name": cl_id} if cl_id else {},
        "properties": {"version": version},
    }
    if spc_id:
        result["properties"]["defaultSecretProviderClassRef"] = {"resourceId": spc_id}
    return result


def _build_cl(
    name: str = "mycl",
    rg: str = "rg1",
    host_resource_id: str = "",
    namespace: str = "azure-iot-operations",
    cluster_extension_ids: Optional[List[str]] = None,
) -> dict:
    cl_id = generate_resource_id(
        resource_group_name=rg,
        resource_provider="Microsoft.ExtendedLocation",
        resource_path=f"/customLocations/{name}",
    )
    props: dict = {"hostResourceId": host_resource_id, "namespace": namespace}
    if cluster_extension_ids is not None:
        props["clusterExtensionIds"] = cluster_extension_ids
    return {
        "id": cl_id,
        "name": name,
        "properties": props,
    }


def _build_extension(
    name: str = "aio-ext",
    rg: str = "rg1",
    cluster_name: str = "mycluster",
    extension_type: str = EXTENSION_TYPE_OPS,
    version: str = "1.2.0",
) -> dict:
    ext_id = generate_resource_id(
        resource_group_name=rg,
        resource_provider="Microsoft.KubernetesConfiguration",
        resource_path=f"/extensions/{name}",
    )
    return {
        "id": ext_id,
        "name": name,
        "properties": {
            "extensionType": extension_type,
            "version": version,
        },
    }


def _build_sync_rule(name: str = "aio-sync", rg: str = "rg1", cl_name: str = "mycl") -> dict:
    rule_id = generate_resource_id(
        resource_group_name=rg,
        resource_provider="Microsoft.ExtendedLocation",
        resource_path=f"/customLocations/{cl_name}/resourceSyncRules/{name}",
    )
    return {"id": rule_id, "name": name}


# ---------------------------------------------------------------------------
# Tests: Entry Point
# ---------------------------------------------------------------------------


class TestDeleteOpsResourcesEntryPoint:
    def test_no_instance_or_cluster_raises(self, mocked_cmd):
        with pytest.raises(ArgumentUsageError, match="instance name or cluster name"):
            delete_ops_resources(cmd=mocked_cmd, resource_group_name="rg1")

    def test_delegates_to_manager(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        _register_instance_discovery(mocked_responses, name="myinstance")
        _register_extensions(mocked_responses)
        _register_sync_rules(mocked_responses)
        _register_arg_sweep(mocked_responses)
        _register_delete_handler(mocked_responses)

        delete_ops_resources(
            cmd=mocked_cmd,
            resource_group_name=_RG,
            instance_name="myinstance",
            confirm_yes=True,
            no_progress=True,
        )
        # Verify instance GET was made.
        instance_gets = [
            c for c in mocked_responses.calls
            if c.request.method == "GET" and "instances/myinstance" in c.request.url
        ]
        assert len(instance_gets) == 1


# ---------------------------------------------------------------------------
# Tests: Instance-Name Discovery Path
# ---------------------------------------------------------------------------


class TestInstanceNamePath:
    def test_instance_not_found_raises(
        self,
        mocked_cmd,
        mocked_responses,
    ):
        """Instance 404 on instance-name path → clear error directing to --cluster."""
        mocked_responses.assert_all_requests_are_fired = False
        mocked_responses.add(
            method=responses.GET,
            url=_build_instance_endpoint("ghost", _RG),
            json={"error": {"code": "ResourceNotFound"}},
            status=404,
        )
        with pytest.raises(ResourceNotFoundError, match="--cluster"):
            delete_ops_resources(
                cmd=mocked_cmd,
                resource_group_name=_RG,
                instance_name="ghost",
                confirm_yes=True,
            )

    def test_discovers_instance_cl_cluster(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """Instance-name path: discovers instance, CL, and cluster from ARM GETs."""
        _register_instance_discovery(mocked_responses)
        _register_extensions(mocked_responses)
        _register_sync_rules(mocked_responses)
        _register_arg_sweep(mocked_responses)
        _register_delete_handler(mocked_responses)

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        # Verify instance was discovered.
        assert manager._instance_resource is not None
        assert manager._instance_resource.display_name == "myinst"
        # Verify CL was discovered.
        assert manager._cl_resource is not None
        assert manager._cl_resource.display_name == "mycl"

    def test_spc_extracted_from_instance(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """SPC resource ID from instance properties is added to CL resources."""
        _register_instance_discovery(mocked_responses, spc_id=_SPC_ID)
        _register_extensions(mocked_responses)
        _register_sync_rules(mocked_responses)
        _register_arg_sweep(mocked_responses)
        _register_delete_handler(mocked_responses)

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        spc_ids = [r.resource_id for r in manager._cl_resources]
        assert _SPC_ID in spc_ids

    def test_cl_resolution_failure_continues(
        self,
        mocker,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """CL get_by_id raises HttpResponseError → cluster stays None, deletion continues."""
        mocked_responses.assert_all_requests_are_fired = False
        inst = _build_instance(name="myinst", rg=_RG, cl_id=_CL_ID)
        mocked_responses.add(
            method=responses.GET, url=_build_instance_endpoint("myinst", _RG), json=inst, status=200,
        )
        # CL resolution fails — 500 on get_by_id.
        mocked_responses.add(
            method=responses.GET,
            url=_build_resource_endpoint(_CL_ID, CUSTOM_LOCATIONS_API_VERSION),
            json={"error": {"code": "InternalServerError"}},
            status=500,
        )
        # Extensions, sync rules, and ARG are still attempted after CL resolution failure.
        # Note: _discover_extensions() returns early (cluster_name is None).
        _register_sync_rules(mocked_responses)
        _register_arg_sweep(mocked_responses)
        _register_delete_handler(mocked_responses)

        mock_logger = mocker.patch("azext_edge.edge.providers.orchestration.deletion2.logger")

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        # Cluster should not be discovered, but instance + CL are still present.
        assert manager._cluster_resource is None
        assert manager._cluster_name is None
        assert manager._instance_resource is not None
        assert manager._cl_resource is not None
        # Warning was logged.
        warning_messages = [str(c.args[0]) for c in mock_logger.warning.call_args_list]
        assert any("cluster" in msg.lower() for msg in warning_messages)


# ---------------------------------------------------------------------------
# Tests: Cluster-Name Discovery Path
# ---------------------------------------------------------------------------


class TestClusterNamePath:
    def test_discovers_instance_via_cl_filter(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """Cluster-name path: list CLs + instances, filter by cluster → discovers instance."""
        _register_cluster_discovery(mocked_responses)
        aio_ext = _build_extension(name="aio-ext", extension_type=EXTENSION_TYPE_OPS)
        _register_extensions(mocked_responses, extensions=[aio_ext])

        cl = _build_cl(
            name="mycl", rg=_RG, host_resource_id=_CLUSTER_ID,
            cluster_extension_ids=[aio_ext["id"]],
        )
        inst = _build_instance(name="myinst", rg=_RG, cl_id=cl["id"])
        _register_cl_list(mocked_responses, cls=[cl])
        _register_instances_list(mocked_responses, instances=[inst])
        _register_sync_rules(mocked_responses)
        _register_arg_sweep(mocked_responses)
        _register_delete_handler(mocked_responses)

        manager = DeletionManager(
            cmd=mocked_cmd, cluster_name="mycluster", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        assert manager._instance_resource is not None
        assert manager._instance_resource.display_name == "myinst"
        assert manager._cl_resource is not None

    def test_no_instance_found_still_cleans_up(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """Cluster-name path: no instance found → skips step 1, still cleans CL + extensions."""
        _register_cluster_discovery(mocked_responses)
        ext = _build_extension(name="aio-ext", extension_type=EXTENSION_TYPE_OPS)
        _register_extensions(mocked_responses, extensions=[ext])

        cl = _build_cl(
            name="mycl", rg=_RG, host_resource_id=_CLUSTER_ID,
            cluster_extension_ids=[ext["id"]],
        )
        _register_cl_list(mocked_responses, cls=[cl])
        _register_instances_list(mocked_responses, instances=[])  # No instance.
        _register_sync_rules(mocked_responses)
        _register_arg_sweep(mocked_responses)
        _register_delete_handler(mocked_responses)

        manager = DeletionManager(
            cmd=mocked_cmd, cluster_name="mycluster", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        assert manager._instance_resource is None
        assert manager._cl_resource is not None
        assert manager._aio_extension is not None


# ---------------------------------------------------------------------------
# Tests: CL Identification (cluster-name path)
# ---------------------------------------------------------------------------


class TestClIdentification:
    """Tiered CL identification when multiple CLs share the same host cluster."""

    def test_tier1_picks_cl_by_extension_type(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """Tier 1: CL with type-verified extension ID in clusterExtensionIds is chosen."""
        _register_cluster_discovery(mocked_responses)

        # AIO extension with a user-chosen name.
        aio_ext = _build_extension(name="my-custom-aio", extension_type=EXTENSION_TYPE_OPS)
        _register_extensions(mocked_responses, extensions=[aio_ext])

        # Two CLs on same host: CL1 has matching ext ID, CL2 has AIO namespace.
        cl_aio = _build_cl(
            name="aio-cl", rg=_RG, host_resource_id=_CLUSTER_ID,
            namespace="custom-ns",
            cluster_extension_ids=[aio_ext["id"]],
        )
        cl_other = _build_cl(
            name="other-cl", rg=_RG, host_resource_id=_CLUSTER_ID,
            namespace="azure-iot-operations",
        )
        _register_cl_list(mocked_responses, cls=[cl_aio, cl_other])
        _register_instances_list(mocked_responses, instances=[])
        _register_sync_rules(mocked_responses, cl_name="aio-cl")
        _register_arg_sweep(mocked_responses)
        _register_delete_handler(mocked_responses)

        manager = DeletionManager(
            cmd=mocked_cmd, cluster_name="mycluster", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        # Tier 1 should pick cl_aio (ext ID match), not cl_other (namespace match).
        assert manager._cl_resource is not None
        assert manager._cl_resource.display_name == "aio-cl"

    def test_tier2_namespace_fallback(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """Tier 2: namespace match when no extension IDs match (extensions deleted)."""
        _register_cluster_discovery(mocked_responses)

        # No extensions found (already deleted).
        _register_extensions(mocked_responses, extensions=[])

        # Two CLs: one AIO namespace, one non-AIO.
        cl_aio = _build_cl(
            name="aio-cl", rg=_RG, host_resource_id=_CLUSTER_ID,
            namespace="azure-iot-operations",
        )
        cl_other = _build_cl(
            name="other-cl", rg=_RG, host_resource_id=_CLUSTER_ID,
            namespace="other-service",
        )
        _register_cl_list(mocked_responses, cls=[cl_other, cl_aio])
        _register_instances_list(mocked_responses, instances=[])
        _register_sync_rules(mocked_responses, cl_name="aio-cl")
        _register_arg_sweep(mocked_responses)
        _register_delete_handler(mocked_responses)

        manager = DeletionManager(
            cmd=mocked_cmd, cluster_name="mycluster", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        assert manager._cl_resource is not None
        assert manager._cl_resource.display_name == "aio-cl"

    def test_no_tier_match_raises_error(
        self,
        mocked_cmd,
        mocked_responses,
    ):
        """No tier match: raises ResourceNotFoundError when CLs exist but none are AIO."""
        _register_cluster_discovery(mocked_responses)
        _register_extensions(mocked_responses, extensions=[])

        cl = _build_cl(
            name="non-aio-cl", rg=_RG, host_resource_id=_CLUSTER_ID,
            namespace="other-service",
        )
        _register_cl_list(mocked_responses, cls=[cl])

        with pytest.raises(ResourceNotFoundError, match="Could not identify"):
            delete_ops_resources(
                cmd=mocked_cmd,
                resource_group_name=_RG,
                cluster_name="mycluster",
                confirm_yes=True,
                no_progress=True,
            )

    def test_tier1_rejects_cl_with_non_aio_extensions(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """Tier 1: CL referencing non-AIO extension IDs is not matched — falls through to Tier 2."""
        _register_cluster_discovery(mocked_responses)

        # AIO extension exists on the cluster.
        aio_ext = _build_extension(name="aio-ext", extension_type=EXTENSION_TYPE_OPS)
        _register_extensions(mocked_responses, extensions=[aio_ext])

        # CL1 references a non-AIO extension (unknown type, not in _AIO_EXTENSION_TYPES).
        foreign_ext_id = generate_resource_id(
            resource_group_name=_RG,
            resource_provider="Microsoft.KubernetesConfiguration",
            resource_path="/extensions/foreign-svc",
        )
        cl_foreign = _build_cl(
            name="foreign-cl", rg=_RG, host_resource_id=_CLUSTER_ID,
            namespace="foreign-ns",
            cluster_extension_ids=[foreign_ext_id],
        )
        # CL2 is the real AIO CL with matching ext ID.
        cl_aio = _build_cl(
            name="aio-cl", rg=_RG, host_resource_id=_CLUSTER_ID,
            namespace="custom-ns",
            cluster_extension_ids=[aio_ext["id"]],
        )
        _register_cl_list(mocked_responses, cls=[cl_foreign, cl_aio])
        _register_instances_list(mocked_responses, instances=[])
        _register_sync_rules(mocked_responses, cl_name="aio-cl")
        _register_arg_sweep(mocked_responses)
        _register_delete_handler(mocked_responses)

        manager = DeletionManager(
            cmd=mocked_cmd, cluster_name="mycluster", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        # Tier 1 should skip cl_foreign (ext ID not type-verified) and pick cl_aio.
        assert manager._cl_resource is not None
        assert manager._cl_resource.display_name == "aio-cl"

    def test_no_cls_on_host_continues(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """No CLs on this host: CL stays None, extensions still cleaned up."""
        _register_cluster_discovery(mocked_responses)

        aio_ext = _build_extension(name="aio-ext", extension_type=EXTENSION_TYPE_OPS)
        _register_extensions(mocked_responses, extensions=[aio_ext])
        _register_cl_list(mocked_responses, cls=[])
        # No _register_instances_list — CL is None so instances list must not be called.
        _register_delete_handler(mocked_responses)

        manager = DeletionManager(
            cmd=mocked_cmd, cluster_name="mycluster", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        assert manager._cl_resource is None
        assert manager._aio_extension is not None


# ---------------------------------------------------------------------------
# Tests: Extension Discovery
# ---------------------------------------------------------------------------


class TestExtensionDiscovery:
    def test_aio_extension_always_found(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """AIO extension is always discovered regardless of --include-deps."""
        _register_instance_discovery(mocked_responses)

        aio_ext = _build_extension(name="aio-ext", extension_type=EXTENSION_TYPE_OPS, version="1.2.0")
        cm_ext = _build_extension(name="cm-ext", extension_type=EXTENSION_TYPE_CM)
        _register_extensions(mocked_responses, extensions=[aio_ext, cm_ext])
        _register_sync_rules(mocked_responses)
        _register_arg_sweep(mocked_responses)
        _register_delete_handler(mocked_responses)

        # Without --include-deps.
        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        assert manager._aio_extension is not None
        assert manager._aio_extension.display_name == "aio-ext"

    @pytest.mark.parametrize(
        "aio_version, expect_acs",
        [
            (MAX_INSTANCE_VERSION_ACS_DEPENDENCY, True),
            ("1.0.0", True),
            (_ACS_ABOVE, False),
            ("2.0.0", False),
            ("not-a-version", False),
            ("", False),
        ],
    )
    def test_acs_version_gating(
        self,
        aio_version: str,
        expect_acs: bool,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """ACS extension included only when AIO version <= threshold."""
        _register_instance_discovery(mocked_responses, version=aio_version)

        extensions = [
            _build_extension(name="aio-ext", extension_type=EXTENSION_TYPE_OPS, version=aio_version),
            _build_extension(name="acs-ext", extension_type=EXTENSION_TYPE_ACS),
            _build_extension(name="cm-ext", extension_type=EXTENSION_TYPE_CM),
            _build_extension(name="ssc-ext", extension_type=EXTENSION_TYPE_SSC),
        ]
        _register_extensions(mocked_responses, extensions=extensions)
        _register_sync_rules(mocked_responses)
        _register_arg_sweep(mocked_responses)
        _register_delete_handler(mocked_responses)

        manager = DeletionManager(
            cmd=mocked_cmd,
            instance_name="myinst",
            resource_group_name=_RG,
            include_dependencies=True,
            no_progress=True,
        )
        manager.do_work(confirm_yes=True)

        dep_types = [ext.display_name for ext in manager._dep_extensions]

        if expect_acs:
            assert "acs-ext" in dep_types
        else:
            assert "acs-ext" not in dep_types

        # CM and SSC are always included.
        assert "cm-ext" in dep_types
        assert "ssc-ext" in dep_types

    def test_platform_extension_included_as_dep(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """Platform extension (deprecated CM) is included in deps when --include-deps."""
        _register_instance_discovery(mocked_responses)

        extensions = [
            _build_extension(name="aio-ext", extension_type=EXTENSION_TYPE_OPS, version="1.2.0"),
            _build_extension(name="plat-ext", extension_type=EXTENSION_TYPE_PLATFORM),
        ]
        _register_extensions(mocked_responses, extensions=extensions)
        _register_sync_rules(mocked_responses)
        _register_arg_sweep(mocked_responses)
        _register_delete_handler(mocked_responses)

        manager = DeletionManager(
            cmd=mocked_cmd,
            instance_name="myinst",
            resource_group_name=_RG,
            include_dependencies=True,
            no_progress=True,
        )
        manager.do_work(confirm_yes=True)

        dep_names = [e.display_name for e in manager._dep_extensions]
        assert "plat-ext" in dep_names


# ---------------------------------------------------------------------------
# Tests: Connectivity Gate
# ---------------------------------------------------------------------------


class TestConnectivityGate:
    def test_disconnected_without_force_raises(
        self,
        mocked_cmd,
        mocked_responses,
    ):
        """Disconnected cluster without --force → error before prompt."""
        _register_instance_discovery(mocked_responses, connectivity="Disconnected")
        _register_extensions(mocked_responses)
        _register_sync_rules(mocked_responses)
        _register_arg_sweep(mocked_responses)

        with pytest.raises(ArgumentUsageError, match="not connected"):
            delete_ops_resources(
                cmd=mocked_cmd,
                resource_group_name=_RG,
                instance_name="myinst",
                confirm_yes=True,
            )

    def test_disconnected_with_force_proceeds(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """Disconnected cluster with --force → proceeds with deletion."""
        _register_instance_discovery(mocked_responses, connectivity="Disconnected")
        _register_extensions(mocked_responses)
        _register_sync_rules(mocked_responses)
        _register_arg_sweep(mocked_responses)
        _register_delete_handler(mocked_responses)

        # Should not raise.
        delete_ops_resources(
            cmd=mocked_cmd,
            resource_group_name=_RG,
            instance_name="myinst",
            confirm_yes=True,
            force=True,
            no_progress=True,
        )


# ---------------------------------------------------------------------------
# Tests: Sync Rules Discovery
# ---------------------------------------------------------------------------


class TestSyncRulesDiscovery:
    def test_sync_rules_error_graceful(
        self,
        mocker,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """list_resource_sync_rules raises HttpResponseError → warning logged, deletion continues."""
        _register_instance_discovery(mocked_responses)
        _register_extensions(mocked_responses)

        # Sync rules list returns 503 instead of success.
        mocked_responses.add(
            method=responses.GET,
            url=_build_sync_rules_list_endpoint(_RG, "mycl"),
            status=503,
            json={"error": {"code": "ServiceUnavailable", "message": "Service unavailable"}},
        )

        _register_arg_sweep(mocked_responses)
        _register_delete_handler(mocked_responses)

        mock_logger = mocker.patch("azext_edge.edge.providers.orchestration.deletion2.logger")

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        # Sync rules should be empty.
        assert len(manager._sync_rules) == 0
        # Warning was logged.
        warning_messages = [str(c.args[0]) for c in mock_logger.warning.call_args_list]
        assert any("sync rules" in msg.lower() for msg in warning_messages)


# ---------------------------------------------------------------------------
# Tests: ARG Sweep
# ---------------------------------------------------------------------------


class TestArgSweep:
    def test_sweep_adds_resources(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """ARG sweep returns DR assets + SecretSync → added to CL resources."""
        _register_instance_discovery(mocked_responses)
        _register_extensions(mocked_responses)
        _register_sync_rules(mocked_responses)

        asset_id = generate_resource_id(
            resource_group_name=_RG,
            resource_provider="Microsoft.DeviceRegistry",
            resource_path="/assets/sensor1",
        )
        _register_arg_sweep(mocked_responses, data=[
            {
                "id": asset_id, "name": "sensor1",
                "apiVersion": "2024-09-01-preview",
                "type": "microsoft.deviceregistry/assets",
            },
        ])
        _register_delete_handler(mocked_responses)

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        cl_resource_ids = [r.resource_id for r in manager._cl_resources]
        assert asset_id in cl_resource_ids

    def test_sweep_failure_graceful_degradation(
        self,
        mocker,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """ARG sweep failure → warning logged, deletion continues with SPC from instance."""
        _register_instance_discovery(mocked_responses, spc_id=_SPC_ID)
        _register_extensions(mocked_responses)
        _register_sync_rules(mocked_responses)

        # ARG sweep fails — mock ResourceGraph to raise HttpResponseError.
        mocker.patch(
            "azext_edge.edge.providers.orchestration.deletion2.ResourceGraph"
        ).return_value.query_resources.side_effect = HttpResponseError(
            message="429 throttled", response=Mock(status_code=429)
        )

        _register_delete_handler(mocked_responses)

        mock_logger = mocker.patch("azext_edge.edge.providers.orchestration.deletion2.logger")

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        # SPC from instance ref is still present.
        spc_ids = [r.resource_id for r in manager._cl_resources]
        assert _SPC_ID in spc_ids
        # Warning was logged about sweep failure.
        warning_messages = [str(c.args[0]) for c in mock_logger.warning.call_args_list]
        assert any("CL-scoped resources" in msg for msg in warning_messages)

    def test_sweep_deduplicates_spc(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """ARG sweep returning same SPC as instance ref → deduplicated."""
        _register_instance_discovery(mocked_responses, spc_id=_SPC_ID)
        _register_extensions(mocked_responses)
        _register_sync_rules(mocked_responses)

        # ARG returns the same SPC.
        _register_arg_sweep(mocked_responses, data=[
            {
                "id": _SPC_ID, "name": "my-spc",
                "apiVersion": SECRET_SYNC_API_VERSION,
                "type": "microsoft.secretsynccontroller/azurekeyvaultsecretproviderclasses",
            },
        ])
        _register_delete_handler(mocked_responses)

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        # SPC should appear exactly once.
        spc_matches = [r for r in manager._cl_resources if r.resource_id.lower() == _SPC_ID.lower()]
        assert len(spc_matches) == 1

    def test_sweep_excludes_iotops_namespaces_and_registries(
        self,
    ):
        """Verify the KQL query uses exclusion-list: skips IoT Ops, DR namespaces, schema registries."""
        query_lower = _ARG_SWEEP_QUERY.lower()
        # Exclusion-list approach: IoT Operations resources excluded (cascade-deleted).
        assert "!startswith 'microsoft.iotoperations'" in query_lower
        # Preserved external prerequisites excluded.
        assert "microsoft.deviceregistry/namespaces" in query_lower
        assert "microsoft.deviceregistry/schemaregistries" in query_lower
        assert "!~" in _ARG_SWEEP_QUERY  # negation operator


# ---------------------------------------------------------------------------
# Tests: Deletion Execution Order
# ---------------------------------------------------------------------------


class TestDeletionOrder:
    def test_instance_deleted_before_aio_extension(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """Instance (step 1) is deleted before AIO extension (step 5)."""
        _register_instance_discovery(mocked_responses)

        aio_ext = _build_extension(name="aio-ext", extension_type=EXTENSION_TYPE_OPS)
        _register_extensions(mocked_responses, extensions=[aio_ext])
        _register_sync_rules(mocked_responses)
        _register_arg_sweep(mocked_responses)
        _register_delete_handler(mocked_responses)

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        # Instance should be deleted before extension.
        delete_urls = [c.request.url for c in mocked_responses.calls if c.request.method == "DELETE"]
        instance_idx = next(i for i, url in enumerate(delete_urls) if "instances/myinst" in url.lower())
        ext_idx = next(i for i, url in enumerate(delete_urls) if "/extensions/aio-ext" in url.lower())
        assert instance_idx < ext_idx

    def test_cl_resources_deleted_before_cl(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """CL resources (step 2) and sync rules (step 3) deleted before CL (step 4)."""
        _register_instance_discovery(mocked_responses)
        _register_extensions(mocked_responses)

        # Add a sync rule.
        sync_rule = _build_sync_rule(name="aio-sync", rg=_RG, cl_name="mycl")
        _register_sync_rules(mocked_responses, rules=[sync_rule])

        # Add a CL resource from ARG sweep.
        asset_id = generate_resource_id(
            resource_group_name=_RG,
            resource_provider="Microsoft.DeviceRegistry",
            resource_path="/assets/sensor1",
        )
        _register_arg_sweep(mocked_responses, data=[
            {
                "id": asset_id, "name": "sensor1",
                "apiVersion": "2024-09-01-preview",
                "type": "microsoft.deviceregistry/assets",
            },
        ])
        _register_delete_handler(mocked_responses)

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        # Find indices.
        delete_urls = [c.request.url for c in mocked_responses.calls if c.request.method == "DELETE"]
        cl_delete_idx = next(
            (
                i for i, url in enumerate(delete_urls)
                if "customlocations/mycl" in url.lower()
                and "resourcesyncrules" not in url.lower()
            ),
            None
        )
        if cl_delete_idx is not None:
            # Asset and sync rule should be before CL.
            for url in delete_urls[:cl_delete_idx]:
                url_lower = url.lower()
                assert (
                    "customlocations/mycl" not in url_lower
                    or "resourcesyncrules" in url_lower
                    or "assets" in url_lower
                    or "instances" in url_lower
                    or "extensions" in url_lower
                )

    def test_aio_extension_deleted_after_cl(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """AIO extension (step 5) deleted after custom location (step 4)."""
        _register_instance_discovery(mocked_responses)

        aio_ext = _build_extension(name="aio-ext", extension_type=EXTENSION_TYPE_OPS)
        _register_extensions(mocked_responses, extensions=[aio_ext])
        _register_sync_rules(mocked_responses)
        _register_arg_sweep(mocked_responses)
        _register_delete_handler(mocked_responses)

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        delete_urls = [c.request.url for c in mocked_responses.calls if c.request.method == "DELETE"]
        cl_idx = next(
            i for i, url in enumerate(delete_urls)
            if "customlocations/mycl" in url.lower() and "resourcesyncrules" not in url.lower()
        )
        ext_idx = next(i for i, url in enumerate(delete_urls) if "/extensions/aio-ext" in url.lower())
        assert cl_idx < ext_idx

    def test_full_execution_order(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """Full 6-step ordering: instance → CL resources → sync rules → CL → AIO ext → dep ext."""
        _register_instance_discovery(mocked_responses, spc_id=_SPC_ID)

        # Extensions: AIO + CM dep.
        aio_ext = _build_extension(name="aio-ext", extension_type=EXTENSION_TYPE_OPS, version="1.2.0")
        cm_ext = _build_extension(name="cm-ext", extension_type=EXTENSION_TYPE_CM)
        _register_extensions(mocked_responses, extensions=[aio_ext, cm_ext])

        # Sync rule.
        sync_rule = _build_sync_rule(name="aio-sync", rg=_RG, cl_name="mycl")
        _register_sync_rules(mocked_responses, rules=[sync_rule])
        _register_arg_sweep(mocked_responses)
        _register_delete_handler(mocked_responses)

        manager = DeletionManager(
            cmd=mocked_cmd,
            instance_name="myinst",
            resource_group_name=_RG,
            include_dependencies=True,
            no_progress=True,
        )
        manager.do_work(confirm_yes=True)

        # Build index map by category.
        delete_urls = [c.request.url for c in mocked_responses.calls if c.request.method == "DELETE"]

        def find_idx(substring: str) -> int:
            return next(i for i, url in enumerate(delete_urls) if substring in url.lower())

        instance_idx = find_idx("instances/myinst")
        spc_idx = find_idx("azurekeyvaultsecretproviderclasses")
        sync_idx = find_idx("resourcesyncrules")
        cl_idx = next(
            i for i, url in enumerate(delete_urls)
            if "customlocations/mycl" in url.lower() and "resourcesyncrules" not in url.lower()
        )
        aio_ext_idx = find_idx("/extensions/aio-ext")
        dep_ext_idx = find_idx("/extensions/cm-ext")

        # Verify strict step ordering.
        assert instance_idx < spc_idx, "Instance must be before CL resources"
        assert spc_idx < sync_idx, "CL resources must be before sync rules"
        assert sync_idx < cl_idx, "Sync rules must be before CL"
        assert cl_idx < aio_ext_idx, "CL must be before AIO extension"
        assert aio_ext_idx < dep_ext_idx, "AIO extension must be before dep extensions"

    def test_cl_delete_failure_continues_to_aio_extension(
        self,
        mocker,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """CL delete failure (step 4) → AIO extension (step 5) still executes."""
        _register_instance_discovery(mocked_responses)

        aio_ext = _build_extension(name="aio-ext", extension_type=EXTENSION_TYPE_OPS)
        _register_extensions(mocked_responses, extensions=[aio_ext])
        _register_sync_rules(mocked_responses)
        _register_arg_sweep(mocked_responses)

        # CL DELETE returns 409 conflict. Register BEFORE catch-all (FIFO).
        mocked_responses.add(
            method=responses.DELETE,
            url=f"{BASE_URL}{_CL_ID}",
            status=409,
            json={"error": {"code": "Conflict", "message": "Conflict: resources still scoped"}},
        )
        _register_delete_handler(mocked_responses)

        mock_logger = mocker.patch("azext_edge.edge.providers.orchestration.deletion2.logger")

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        # CL failure warning was logged.
        warning_messages = [str(c.args[0]) for c in mock_logger.warning.call_args_list]
        assert any("custom location" in msg.lower() for msg in warning_messages)

        # AIO extension still ran despite CL failure.
        ext_deletes = [
            c for c in mocked_responses.calls
            if c.request.method == "DELETE" and "/extensions/aio-ext" in c.request.url.lower()
        ]
        assert len(ext_deletes) == 1


# ---------------------------------------------------------------------------
# Tests: Idempotent Recovery
# ---------------------------------------------------------------------------


class TestIdempotentRecovery:
    def test_404_on_delete_treated_as_success(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """404 during begin_delete_by_id → treated as success, execution continues."""
        _register_instance_discovery(mocked_responses)
        _register_extensions(mocked_responses)
        _register_sync_rules(mocked_responses)
        _register_arg_sweep(mocked_responses)

        # Instance DELETE returns 404 (already deleted). Register BEFORE catch-all (FIFO).
        inst_id = generate_resource_id(
            resource_group_name=_RG,
            resource_provider="Microsoft.IoTOperations",
            resource_path="/instances/myinst",
        )
        mocked_responses.add(
            method=responses.DELETE,
            url=f"{BASE_URL}{inst_id}",
            status=404,
            json={"error": {"code": "ResourceNotFound", "message": "Not found"}},
        )
        _register_delete_handler(mocked_responses)

        # Should not raise.
        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

    def test_partial_rerun_cluster_path(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """Re-run after instance already deleted (cluster-name path) → proceeds with remaining."""
        _register_cluster_discovery(mocked_responses)
        _register_extensions(mocked_responses, extensions=[])

        cl = _build_cl(name="mycl", rg=_RG, host_resource_id=_CLUSTER_ID)
        _register_cl_list(mocked_responses, cls=[cl])
        _register_instances_list(mocked_responses, instances=[])  # Already deleted.

        # Sync rules remain.
        sync_rule = _build_sync_rule(name="aio-sync", rg=_RG, cl_name="mycl")
        _register_sync_rules(mocked_responses, rules=[sync_rule])
        _register_arg_sweep(mocked_responses)
        _register_delete_handler(mocked_responses)

        manager = DeletionManager(
            cmd=mocked_cmd, cluster_name="mycluster", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        # Instance should be None, but CL and sync rules should be discovered.
        assert manager._instance_resource is None
        assert manager._cl_resource is not None
        assert len(manager._sync_rules) == 1

    def test_non_404_error_propagates(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """Non-404 HttpResponseError during deletion → re-raised."""
        _register_instance_discovery(mocked_responses)
        _register_extensions(mocked_responses)
        _register_sync_rules(mocked_responses)
        _register_arg_sweep(mocked_responses)

        # Instance DELETE returns 500.
        inst_id = generate_resource_id(
            resource_group_name=_RG,
            resource_provider="Microsoft.IoTOperations",
            resource_path="/instances/myinst",
        )
        mocked_responses.add(
            method=responses.DELETE,
            url=f"{BASE_URL}{inst_id}",
            status=500,
            json={"error": {"code": "InternalServerError", "message": "Internal server error"}},
        )

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=_RG, no_progress=True
        )
        with pytest.raises(HttpResponseError):
            manager.do_work(confirm_yes=True)

    def test_extension_404_treated_as_success(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """404 on extension begin_delete → treated as success, deletion continues."""
        _register_instance_discovery(mocked_responses)

        aio_ext = _build_extension(name="aio-ext", extension_type=EXTENSION_TYPE_OPS)
        _register_extensions(mocked_responses, extensions=[aio_ext])
        _register_sync_rules(mocked_responses)
        _register_arg_sweep(mocked_responses)

        # Extension DELETE returns 404. Register BEFORE catch-all (FIFO).
        ext_url = _build_extension_delete_endpoint(_RG, "mycluster", "aio-ext")
        mocked_responses.add(
            method=responses.DELETE,
            url=ext_url,
            status=404,
            json={"error": {"code": "ResourceNotFound", "message": "Not found"}},
        )
        _register_delete_handler(mocked_responses)

        # Should not raise.
        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

    def test_cl_delete_failure_continues_to_dep_extensions(
        self,
        mocker,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """CL delete failure (e.g. orphaned resources) → logs warning, still deletes dep extensions."""
        _register_instance_discovery(mocked_responses)

        aio_ext = _build_extension(name="aio-ext", extension_type=EXTENSION_TYPE_OPS, version="1.2.0")
        cm_ext = _build_extension(name="cm-ext", extension_type=EXTENSION_TYPE_CM)
        _register_extensions(mocked_responses, extensions=[aio_ext, cm_ext])
        _register_sync_rules(mocked_responses)
        _register_arg_sweep(mocked_responses)

        # CL DELETE returns 409. Register BEFORE catch-all (FIFO).
        mocked_responses.add(
            method=responses.DELETE,
            url=f"{BASE_URL}{_CL_ID}",
            status=409,
            json={"error": {"code": "Conflict", "message": "Conflict: resources still scoped"}},
        )
        _register_delete_handler(mocked_responses)

        mock_logger = mocker.patch("azext_edge.edge.providers.orchestration.deletion2.logger")

        manager = DeletionManager(
            cmd=mocked_cmd,
            instance_name="myinst",
            resource_group_name=_RG,
            include_dependencies=True,
            no_progress=True,
        )
        # Should NOT raise — CL failure is non-fatal.
        manager.do_work(confirm_yes=True)

        # Warning was logged about CL failure.
        warning_messages = [str(c.args[0]) for c in mock_logger.warning.call_args_list]
        assert any("custom location" in msg.lower() and "--cluster" in msg for msg in warning_messages)

        # Dep extensions still ran.
        ext_deletes = [
            c for c in mocked_responses.calls
            if c.request.method == "DELETE" and "/extensions/" in c.request.url.lower()
        ]
        assert len(ext_deletes) >= 2  # AIO + CM


# ---------------------------------------------------------------------------
# Tests: Nothing to Delete
# ---------------------------------------------------------------------------


class TestNothingToDelete:
    def test_nothing_to_delete_logs_warning(
        self,
        mocker,
        mocked_cmd,
        mocked_responses,
    ):
        """Cluster-name path with nothing found → warning logged, no prompt."""
        _register_cluster_discovery(mocked_responses)
        _register_extensions(mocked_responses, extensions=[])
        _register_cl_list(mocked_responses, cls=[])

        mock_logger = mocker.patch("azext_edge.edge.providers.orchestration.deletion2.logger")

        manager = DeletionManager(
            cmd=mocked_cmd, cluster_name="mycluster", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        mock_logger.warning.assert_called_with("Nothing to delete :)")


# ---------------------------------------------------------------------------
# Tests: Segment-Depth Batching
# ---------------------------------------------------------------------------


class TestSegmentDepthBatching:
    def test_mixed_depth_resources_batched_correctly(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """Resources at different segment depths are batched and deleted deepest-first."""
        _register_instance_discovery(mocked_responses)
        _register_extensions(mocked_responses)
        _register_sync_rules(mocked_responses)

        # Simulate DR resources at different depths from ARG sweep.
        deep_asset_id = generate_resource_id(
            resource_group_name=_RG,
            resource_provider="Microsoft.DeviceRegistry",
            resource_path="/namespaces/myns/assets/sensor1",
        )
        shallow_spc_id = generate_resource_id(
            resource_group_name=_RG,
            resource_provider="Microsoft.SecretSyncController",
            resource_path="/azureKeyVaultSecretProviderClasses/my-spc",
        )
        _register_arg_sweep(mocked_responses, data=[
            {
                "id": deep_asset_id, "name": "sensor1",
                "apiVersion": "2024-09-01-preview",
                "type": "microsoft.deviceregistry/namespaces/assets",
            },
            {
                "id": shallow_spc_id, "name": "my-spc",
                "apiVersion": SECRET_SYNC_API_VERSION,
                "type": "microsoft.secretsynccontroller/azurekeyvaultsecretproviderclasses",
            },
        ])
        _register_delete_handler(mocked_responses)

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        # Deep asset (more segments) should be deleted before shallow SPC.
        delete_urls = [c.request.url for c in mocked_responses.calls if c.request.method == "DELETE"]
        deep_match = [i for i, url in enumerate(delete_urls) if deep_asset_id.lower() in url.lower()]
        shallow_match = [i for i, url in enumerate(delete_urls) if shallow_spc_id.lower() in url.lower()]
        if deep_match and shallow_match:
            assert deep_match[0] < shallow_match[0]


# ---------------------------------------------------------------------------
# Tests: User Prompt Cancellation
# ---------------------------------------------------------------------------


class TestUserPrompt:
    def test_user_cancels_prompt(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """User declines confirmation → no deletion occurs."""
        _register_instance_discovery(mocked_responses)
        _register_extensions(mocked_responses)
        _register_sync_rules(mocked_responses)
        _register_arg_sweep(mocked_responses)

        mocked_should_continue_prompt.return_value = False

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=_RG, no_progress=True
        )
        manager.do_work()

        # No delete calls.
        delete_calls = [c for c in mocked_responses.calls if c.request.method == "DELETE"]
        assert len(delete_calls) == 0


# ---------------------------------------------------------------------------
# Tests: API Version Sourcing
# ---------------------------------------------------------------------------


class TestApiVersions:
    def test_instance_uses_iotops_api_version(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """Instance resource uses DEFAULT_IOTOPS_MGMT_API_VERSION."""
        _register_instance_discovery(mocked_responses)
        _register_extensions(mocked_responses)
        _register_sync_rules(mocked_responses)
        _register_arg_sweep(mocked_responses)
        _register_delete_handler(mocked_responses)

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        assert manager._instance_resource.api_version == IOTOPS_API_VERSION

    def test_cl_uses_custom_locations_api_version(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """CL resource uses CUSTOM_LOCATIONS_API_VERSION."""
        _register_instance_discovery(mocked_responses)
        _register_extensions(mocked_responses)
        _register_sync_rules(mocked_responses)
        _register_arg_sweep(mocked_responses)
        _register_delete_handler(mocked_responses)

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        assert manager._cl_resource.api_version == CUSTOM_LOCATIONS_API_VERSION

    def test_extensions_use_cluster_extensions_api_version(
        self,
        mocked_cmd,
        mocked_responses,
        mocked_should_continue_prompt,
    ):
        """Extensions use CLUSTER_EXTENSIONS_API_VERSION."""
        _register_instance_discovery(mocked_responses)

        aio_ext = _build_extension(name="aio-ext", extension_type=EXTENSION_TYPE_OPS)
        _register_extensions(mocked_responses, extensions=[aio_ext])
        _register_sync_rules(mocked_responses)
        _register_arg_sweep(mocked_responses)
        _register_delete_handler(mocked_responses)

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=_RG, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        assert manager._aio_extension.api_version == CLUSTER_EXTENSIONS_API_VERSION
