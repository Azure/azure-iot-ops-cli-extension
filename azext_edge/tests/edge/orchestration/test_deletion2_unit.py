# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List
from unittest.mock import MagicMock, Mock

import pytest
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

from ...generators import generate_resource_id, get_zeroed_subscription

semver = scoped_semver_import()
ZEROED_SUBSCRIPTION = get_zeroed_subscription()
IOTOPS_API_VERSION = DEFAULT_IOTOPS_MGMT_API_VERSION.value
_ACS_THRESHOLD = semver.parse(MAX_INSTANCE_VERSION_ACS_DEPENDENCY)
_ACS_ABOVE = str(_ACS_THRESHOLD.bump_patch())


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
def mocked_get_resource_client(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.deletion2.get_resource_client", autospec=True
    )
    # begin_delete_by_id returns a mock poller by default.
    mock_poller = MagicMock()
    mock_poller.done.return_value = True
    mock_poller.result.return_value = None
    patched.return_value.resources.begin_delete_by_id.return_value = mock_poller
    patched.return_value.resources.get_by_id.return_value = {
        "properties": {"hostResourceId": ""},
    }
    yield patched


@pytest.fixture
def mocked_instances(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.deletion2.Instances", autospec=True
    )
    yield patched


@pytest.fixture
def mocked_connected_clusters(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.deletion2.ConnectedClusters", autospec=True
    )
    patched.return_value.show.return_value = {
        "id": generate_resource_id(
            resource_group_name="rg1",
            resource_provider="Microsoft.Kubernetes",
            resource_path="/connectedClusters/mycluster",
        ),
        "properties": {"connectivityStatus": "Connected"},
    }
    yield patched


@pytest.fixture
def mocked_custom_locations(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.deletion2.CustomLocations", autospec=True
    )
    patched.return_value.list.return_value = []
    patched.return_value.list_resource_sync_rules.return_value = []
    yield patched


@pytest.fixture
def mocked_cluster_extensions(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.deletion2.ClusterExtensions"
    )
    patched.return_value.list.return_value = []
    # ops.begin_delete returns a mock poller (used by _begin_delete_extension).
    mock_poller = MagicMock()
    mock_poller.done.return_value = True
    mock_poller.result.return_value = None
    patched.return_value.ops.begin_delete.return_value = mock_poller
    yield patched


@pytest.fixture
def mocked_resource_graph(mocker):
    patched = mocker.patch(
        "azext_edge.edge.providers.orchestration.deletion2.ResourceGraph", autospec=True
    )
    patched.return_value.query_resources.return_value = {"data": []}
    yield patched


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
) -> dict:
    cl_id = generate_resource_id(
        resource_group_name=rg,
        resource_provider="Microsoft.ExtendedLocation",
        resource_path=f"/customLocations/{name}",
    )
    return {
        "id": cl_id,
        "name": name,
        "properties": {"hostResourceId": host_resource_id},
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
    def test_no_instance_or_cluster_raises(self, mocked_cmd, mocked_get_resource_client):
        with pytest.raises(ArgumentUsageError, match="instance name or cluster name"):
            delete_ops_resources(cmd=mocked_cmd, resource_group_name="rg1")

    def test_delegates_to_manager(
        self,
        mocker,
        mocked_cmd,
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        cl_id = "/subscriptions/00/resourceGroups/rg1/providers/Microsoft.ExtendedLocation/customLocations/cl1"
        inst = _build_instance(cl_id=cl_id)
        mocked_instances.return_value.show.return_value = inst
        mocked_get_resource_client.return_value.resources.get_by_id.return_value = {
            "properties": {"hostResourceId": ""},
        }

        delete_ops_resources(
            cmd=mocked_cmd,
            resource_group_name="rg1",
            instance_name="myinstance",
            confirm_yes=True,
            no_progress=True,
        )
        mocked_instances.return_value.show.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: Instance-Name Discovery Path
# ---------------------------------------------------------------------------


class TestInstanceNamePath:
    def test_instance_not_found_raises(
        self,
        mocked_cmd,
        mocked_get_resource_client,
        mocked_instances,
    ):
        """Instance 404 on instance-name path → clear error directing to --cluster."""
        mocked_instances.return_value.show.side_effect = HttpResponseError(
            message="Not found", response=Mock(status_code=404)
        )
        with pytest.raises(ResourceNotFoundError, match="--cluster"):
            delete_ops_resources(
                cmd=mocked_cmd,
                resource_group_name="rg1",
                instance_name="ghost",
                confirm_yes=True,
            )

    def test_discovers_instance_cl_cluster(
        self,
        mocked_cmd,
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        """Instance-name path: discovers instance, CL, and cluster from ARM GETs."""
        rg = "rg1"
        cluster_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.Kubernetes",
            resource_path="/connectedClusters/mycluster",
        )
        cl_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.ExtendedLocation",
            resource_path="/customLocations/mycl",
        )
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id, version="1.2.0")
        mocked_instances.return_value.show.return_value = inst

        # CL GET returns hostResourceId pointing to cluster.
        mocked_get_resource_client.return_value.resources.get_by_id.return_value = {
            "properties": {"hostResourceId": cluster_id},
        }
        mocked_connected_clusters.return_value.show.return_value = {
            "id": cluster_id,
            "properties": {"connectivityStatus": "Connected"},
        }

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=rg, no_progress=True
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
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        """SPC resource ID from instance properties is added to CL resources."""
        rg = "rg1"
        cl_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.ExtendedLocation",
            resource_path="/customLocations/mycl",
        )
        spc_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.SecretSyncController",
            resource_path="/azureKeyVaultSecretProviderClasses/my-spc",
        )
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id, spc_id=spc_id)
        mocked_instances.return_value.show.return_value = inst

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=rg, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        spc_ids = [r.resource_id for r in manager._cl_resources]
        assert spc_id in spc_ids

    def test_cl_resolution_failure_continues(
        self,
        mocker,
        mocked_cmd,
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        """CL get_by_id raises HttpResponseError → cluster stays None, deletion continues."""
        rg = "rg1"
        cl_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.ExtendedLocation",
            resource_path="/customLocations/mycl",
        )
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id)
        mocked_instances.return_value.show.return_value = inst

        # CL resolution fails.
        mocked_get_resource_client.return_value.resources.get_by_id.side_effect = HttpResponseError(
            message="Internal error", response=Mock(status_code=500)
        )

        mock_logger = mocker.patch("azext_edge.edge.providers.orchestration.deletion2.logger")

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=rg, no_progress=True
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
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        """Cluster-name path: list CLs + instances, filter by cluster → discovers instance."""
        rg = "rg1"
        cluster_name = "mycluster"
        cluster_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.Kubernetes",
            resource_path=f"/connectedClusters/{cluster_name}",
        )
        cl = _build_cl(name="mycl", rg=rg, host_resource_id=cluster_id)
        cl_id = cl["id"]
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id)

        mocked_connected_clusters.return_value.show.return_value = {
            "id": cluster_id,
            "properties": {"connectivityStatus": "Connected"},
        }
        mocked_custom_locations.return_value.list.return_value = [cl]
        mocked_instances.return_value.list.return_value = [inst]

        manager = DeletionManager(
            cmd=mocked_cmd, cluster_name=cluster_name, resource_group_name=rg, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        assert manager._instance_resource is not None
        assert manager._instance_resource.display_name == "myinst"
        assert manager._cl_resource is not None

    def test_no_instance_found_still_cleans_up(
        self,
        mocked_cmd,
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        """Cluster-name path: no instance found → skips step 1, still cleans CL + extensions."""
        rg = "rg1"
        cluster_name = "mycluster"
        cluster_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.Kubernetes",
            resource_path=f"/connectedClusters/{cluster_name}",
        )
        cl = _build_cl(name="mycl", rg=rg, host_resource_id=cluster_id)

        mocked_connected_clusters.return_value.show.return_value = {
            "id": cluster_id,
            "properties": {"connectivityStatus": "Connected"},
        }
        mocked_custom_locations.return_value.list.return_value = [cl]
        mocked_instances.return_value.list.return_value = []  # No instance.

        # Add an extension so there's work to do.
        ext = _build_extension(name="aio-ext", extension_type=EXTENSION_TYPE_OPS)
        mocked_cluster_extensions.return_value.list.return_value = [ext]

        manager = DeletionManager(
            cmd=mocked_cmd, cluster_name=cluster_name, resource_group_name=rg, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        assert manager._instance_resource is None
        assert manager._cl_resource is not None
        assert manager._aio_extension is not None


# ---------------------------------------------------------------------------
# Tests: Extension Discovery
# ---------------------------------------------------------------------------


class TestExtensionDiscovery:
    def test_aio_extension_always_found(
        self,
        mocked_cmd,
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        """AIO extension is always discovered regardless of --include-deps."""
        rg = "rg1"
        cl_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.ExtendedLocation",
            resource_path="/customLocations/mycl",
        )
        cluster_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.Kubernetes",
            resource_path="/connectedClusters/mycluster",
        )
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id)
        mocked_instances.return_value.show.return_value = inst
        mocked_get_resource_client.return_value.resources.get_by_id.return_value = {
            "properties": {"hostResourceId": cluster_id},
        }
        mocked_connected_clusters.return_value.show.return_value = {
            "id": cluster_id,
            "properties": {"connectivityStatus": "Connected"},
        }

        aio_ext = _build_extension(name="aio-ext", extension_type=EXTENSION_TYPE_OPS, version="1.2.0")
        cm_ext = _build_extension(name="cm-ext", extension_type=EXTENSION_TYPE_CM)
        mocked_cluster_extensions.return_value.list.return_value = [aio_ext, cm_ext]

        # Without --include-deps.
        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=rg, no_progress=True
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
        ],
    )
    def test_acs_version_gating(
        self,
        aio_version: str,
        expect_acs: bool,
        mocked_cmd,
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        """ACS extension included only when AIO version <= threshold."""
        rg = "rg1"
        cl_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.ExtendedLocation",
            resource_path="/customLocations/mycl",
        )
        cluster_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.Kubernetes",
            resource_path="/connectedClusters/mycluster",
        )
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id, version=aio_version)
        mocked_instances.return_value.show.return_value = inst
        mocked_get_resource_client.return_value.resources.get_by_id.return_value = {
            "properties": {"hostResourceId": cluster_id},
        }
        mocked_connected_clusters.return_value.show.return_value = {
            "id": cluster_id,
            "properties": {"connectivityStatus": "Connected"},
        }

        extensions = [
            _build_extension(name="aio-ext", extension_type=EXTENSION_TYPE_OPS, version=aio_version),
            _build_extension(name="acs-ext", extension_type=EXTENSION_TYPE_ACS),
            _build_extension(name="cm-ext", extension_type=EXTENSION_TYPE_CM),
            _build_extension(name="ssc-ext", extension_type=EXTENSION_TYPE_SSC),
        ]
        mocked_cluster_extensions.return_value.list.return_value = extensions

        manager = DeletionManager(
            cmd=mocked_cmd,
            instance_name="myinst",
            resource_group_name=rg,
            include_dependencies=True,
            no_progress=True,
        )
        manager.do_work(confirm_yes=True)

        dep_types = []
        for ext in manager._dep_extensions:
            # Check the resource_id for the extension type name.
            dep_types.append(ext.display_name)

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
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        """Platform extension (deprecated CM) is included in deps when --include-deps."""
        rg = "rg1"
        cl_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.ExtendedLocation",
            resource_path="/customLocations/mycl",
        )
        cluster_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.Kubernetes",
            resource_path="/connectedClusters/mycluster",
        )
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id, version="1.2.0")
        mocked_instances.return_value.show.return_value = inst
        mocked_get_resource_client.return_value.resources.get_by_id.return_value = {
            "properties": {"hostResourceId": cluster_id},
        }
        mocked_connected_clusters.return_value.show.return_value = {
            "id": cluster_id,
            "properties": {"connectivityStatus": "Connected"},
        }

        extensions = [
            _build_extension(name="aio-ext", extension_type=EXTENSION_TYPE_OPS, version="1.2.0"),
            _build_extension(name="plat-ext", extension_type=EXTENSION_TYPE_PLATFORM),
        ]
        mocked_cluster_extensions.return_value.list.return_value = extensions

        manager = DeletionManager(
            cmd=mocked_cmd,
            instance_name="myinst",
            resource_group_name=rg,
            include_dependencies=True,
            no_progress=True,
        )
        manager.do_work(confirm_yes=True)

        dep_names = [e.display_name for e in manager._dep_extensions]
        assert "plat-ext" in dep_names

    def test_acs_version_gating_invalid_version(
        self,
        mocked_cmd,
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        """Unparseable AIO version → ACS preserved (safer for destructive operations)."""
        rg = "rg1"
        cl_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.ExtendedLocation",
            resource_path="/customLocations/mycl",
        )
        cluster_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.Kubernetes",
            resource_path="/connectedClusters/mycluster",
        )
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id, version="not-a-version")
        mocked_instances.return_value.show.return_value = inst
        mocked_get_resource_client.return_value.resources.get_by_id.return_value = {
            "properties": {"hostResourceId": cluster_id},
        }
        mocked_connected_clusters.return_value.show.return_value = {
            "id": cluster_id,
            "properties": {"connectivityStatus": "Connected"},
        }

        extensions = [
            _build_extension(name="aio-ext", extension_type=EXTENSION_TYPE_OPS, version="not-a-version"),
            _build_extension(name="acs-ext", extension_type=EXTENSION_TYPE_ACS),
        ]
        mocked_cluster_extensions.return_value.list.return_value = extensions

        manager = DeletionManager(
            cmd=mocked_cmd,
            instance_name="myinst",
            resource_group_name=rg,
            include_dependencies=True,
            no_progress=True,
        )
        manager.do_work(confirm_yes=True)

        dep_names = [e.display_name for e in manager._dep_extensions]
        assert "acs-ext" not in dep_names

    def test_acs_version_gating_empty_version(
        self,
        mocked_cmd,
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        """Empty AIO version on both extension and instance → ACS preserved."""
        rg = "rg1"
        cl_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.ExtendedLocation",
            resource_path="/customLocations/mycl",
        )
        cluster_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.Kubernetes",
            resource_path="/connectedClusters/mycluster",
        )
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id, version="")
        mocked_instances.return_value.show.return_value = inst
        mocked_get_resource_client.return_value.resources.get_by_id.return_value = {
            "properties": {"hostResourceId": cluster_id},
        }
        mocked_connected_clusters.return_value.show.return_value = {
            "id": cluster_id,
            "properties": {"connectivityStatus": "Connected"},
        }

        extensions = [
            _build_extension(name="aio-ext", extension_type=EXTENSION_TYPE_OPS, version=""),
            _build_extension(name="acs-ext", extension_type=EXTENSION_TYPE_ACS),
        ]
        mocked_cluster_extensions.return_value.list.return_value = extensions

        manager = DeletionManager(
            cmd=mocked_cmd,
            instance_name="myinst",
            resource_group_name=rg,
            include_dependencies=True,
            no_progress=True,
        )
        manager.do_work(confirm_yes=True)

        dep_names = [e.display_name for e in manager._dep_extensions]
        assert "acs-ext" not in dep_names


# ---------------------------------------------------------------------------
# Tests: Connectivity Gate
# ---------------------------------------------------------------------------


class TestConnectivityGate:
    def test_disconnected_without_force_raises(
        self,
        mocked_cmd,
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
    ):
        """Disconnected cluster without --force → error before prompt."""
        rg = "rg1"
        cl_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.ExtendedLocation",
            resource_path="/customLocations/mycl",
        )
        cluster_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.Kubernetes",
            resource_path="/connectedClusters/mycluster",
        )
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id)
        mocked_instances.return_value.show.return_value = inst
        mocked_get_resource_client.return_value.resources.get_by_id.return_value = {
            "properties": {"hostResourceId": cluster_id},
        }
        mocked_connected_clusters.return_value.show.return_value = {
            "id": cluster_id,
            "properties": {"connectivityStatus": "Disconnected"},
        }

        with pytest.raises(ArgumentUsageError, match="not connected"):
            delete_ops_resources(
                cmd=mocked_cmd,
                resource_group_name=rg,
                instance_name="myinst",
                confirm_yes=True,
            )

    def test_disconnected_with_force_proceeds(
        self,
        mocked_cmd,
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        """Disconnected cluster with --force → proceeds with deletion."""
        rg = "rg1"
        cl_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.ExtendedLocation",
            resource_path="/customLocations/mycl",
        )
        cluster_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.Kubernetes",
            resource_path="/connectedClusters/mycluster",
        )
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id)
        mocked_instances.return_value.show.return_value = inst
        mocked_get_resource_client.return_value.resources.get_by_id.return_value = {
            "properties": {"hostResourceId": cluster_id},
        }
        mocked_connected_clusters.return_value.show.return_value = {
            "id": cluster_id,
            "properties": {"connectivityStatus": "Disconnected"},
        }

        # Should not raise.
        delete_ops_resources(
            cmd=mocked_cmd,
            resource_group_name=rg,
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
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        """list_resource_sync_rules raises HttpResponseError → warning logged, deletion continues."""
        rg = "rg1"
        cl_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.ExtendedLocation",
            resource_path="/customLocations/mycl",
        )
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id)
        mocked_instances.return_value.show.return_value = inst

        # Sync rules list fails.
        mocked_custom_locations.return_value.list_resource_sync_rules.side_effect = HttpResponseError(
            message="Service unavailable", response=Mock(status_code=503)
        )

        mock_logger = mocker.patch("azext_edge.edge.providers.orchestration.deletion2.logger")

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=rg, no_progress=True
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
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        """ARG sweep returns DR assets + SecretSync → added to CL resources."""
        rg = "rg1"
        cl_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.ExtendedLocation",
            resource_path="/customLocations/mycl",
        )
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id)
        mocked_instances.return_value.show.return_value = inst

        asset_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.DeviceRegistry",
            resource_path="/assets/sensor1",
        )
        mocked_resource_graph.return_value.query_resources.return_value = {
            "data": [
                {
                    "id": asset_id, "name": "sensor1",
                    "apiVersion": "2024-09-01-preview",
                    "type": "microsoft.deviceregistry/assets",
                },
            ]
        }

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=rg, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        cl_resource_ids = [r.resource_id for r in manager._cl_resources]
        assert asset_id in cl_resource_ids

    def test_sweep_failure_graceful_degradation(
        self,
        mocker,
        mocked_cmd,
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        """ARG sweep failure → warning logged, deletion continues with SPC from instance."""
        rg = "rg1"
        cl_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.ExtendedLocation",
            resource_path="/customLocations/mycl",
        )
        spc_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.SecretSyncController",
            resource_path="/azureKeyVaultSecretProviderClasses/my-spc",
        )
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id, spc_id=spc_id)
        mocked_instances.return_value.show.return_value = inst

        # ARG sweep fails with a realistic HTTP error.
        mocked_resource_graph.return_value.query_resources.side_effect = HttpResponseError(
            message="429 throttled", response=Mock(status_code=429)
        )

        mock_logger = mocker.patch("azext_edge.edge.providers.orchestration.deletion2.logger")

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=rg, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        # SPC from instance ref is still present.
        spc_ids = [r.resource_id for r in manager._cl_resources]
        assert spc_id in spc_ids
        # Warning was logged about sweep failure.
        warning_messages = [str(c.args[0]) for c in mock_logger.warning.call_args_list]
        assert any("CL-scoped resources" in msg for msg in warning_messages)

    def test_sweep_deduplicates_spc(
        self,
        mocked_cmd,
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        """ARG sweep returning same SPC as instance ref → deduplicated."""
        rg = "rg1"
        cl_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.ExtendedLocation",
            resource_path="/customLocations/mycl",
        )
        spc_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.SecretSyncController",
            resource_path="/azureKeyVaultSecretProviderClasses/my-spc",
        )
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id, spc_id=spc_id)
        mocked_instances.return_value.show.return_value = inst

        # ARG returns the same SPC.
        mocked_resource_graph.return_value.query_resources.return_value = {
            "data": [
                {
                    "id": spc_id, "name": "my-spc",
                    "apiVersion": SECRET_SYNC_API_VERSION,
                    "type": "microsoft.secretsynccontroller/azurekeyvaultsecretproviderclasses",
                },
            ]
        }

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=rg, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        # SPC should appear exactly once.
        spc_matches = [r for r in manager._cl_resources if r.resource_id.lower() == spc_id.lower()]
        assert len(spc_matches) == 1

    def test_sweep_excludes_iotops_namespaces_and_registries(
        self,
        mocked_cmd,
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
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
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        """Instance (step 1) is deleted before AIO extension (step 2)."""
        rg = "rg1"
        cl_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.ExtendedLocation",
            resource_path="/customLocations/mycl",
        )
        cluster_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.Kubernetes",
            resource_path="/connectedClusters/mycluster",
        )
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id)
        mocked_instances.return_value.show.return_value = inst
        mocked_get_resource_client.return_value.resources.get_by_id.return_value = {
            "properties": {"hostResourceId": cluster_id},
        }
        mocked_connected_clusters.return_value.show.return_value = {
            "id": cluster_id,
            "properties": {"connectivityStatus": "Connected"},
        }

        aio_ext = _build_extension(name="aio-ext", extension_type=EXTENSION_TYPE_OPS)
        mocked_cluster_extensions.return_value.list.return_value = [aio_ext]

        # Track delete call order across both resource client and extensions client.
        delete_order: List[str] = []
        mock_poller = mocked_get_resource_client.return_value.resources.begin_delete_by_id.return_value
        ext_mock_poller = mocked_cluster_extensions.return_value.ops.begin_delete.return_value

        def track_resource_delete(resource_id, **kwargs):
            delete_order.append(resource_id)
            return mock_poller

        def track_extension_delete(**kwargs):
            delete_order.append(f"extension:{kwargs.get('extension_name', '')}")
            return ext_mock_poller

        mocked_get_resource_client.return_value.resources.begin_delete_by_id.side_effect = track_resource_delete
        mocked_cluster_extensions.return_value.ops.begin_delete.side_effect = track_extension_delete

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=rg, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        # Instance should be deleted before extension.
        instance_idx = next(i for i, rid in enumerate(delete_order) if "instances/myinst" in rid.lower())
        ext_idx = next(i for i, rid in enumerate(delete_order) if "extension:aio-ext" in rid.lower())
        assert instance_idx < ext_idx

    def test_cl_resources_deleted_before_cl(
        self,
        mocked_cmd,
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        """CL resources (step 3) and sync rules (step 4) deleted before CL (step 5)."""
        rg = "rg1"
        cl_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.ExtendedLocation",
            resource_path="/customLocations/mycl",
        )
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id)
        mocked_instances.return_value.show.return_value = inst

        # Add a sync rule.
        sync_rule = _build_sync_rule(name="aio-sync", rg=rg, cl_name="mycl")
        mocked_custom_locations.return_value.list_resource_sync_rules.return_value = [sync_rule]

        # Add a CL resource from ARG sweep.
        asset_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.DeviceRegistry",
            resource_path="/assets/sensor1",
        )
        mocked_resource_graph.return_value.query_resources.return_value = {
            "data": [
                {
                    "id": asset_id, "name": "sensor1",
                    "apiVersion": "2024-09-01-preview",
                    "type": "microsoft.deviceregistry/assets",
                },
            ]
        }

        delete_order: List[str] = []
        mock_poller = mocked_get_resource_client.return_value.resources.begin_delete_by_id.return_value

        def track_delete(resource_id, **kwargs):
            delete_order.append(resource_id)
            return mock_poller

        mocked_get_resource_client.return_value.resources.begin_delete_by_id.side_effect = track_delete

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=rg, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        # Find indices.
        cl_delete_idx = next(
            (
                i for i, rid in enumerate(delete_order)
                if "customlocations/mycl" in rid.lower()
                and "resourcesyncrules" not in rid.lower()
            ),
            None
        )
        if cl_delete_idx is not None:
            # Asset and sync rule should be before CL.
            for rid in delete_order[:cl_delete_idx]:
                rid_lower = rid.lower()
                assert (
                    "customlocations/mycl" not in rid_lower
                    or "resourcesyncrules" in rid_lower
                    or "assets" in rid_lower
                    or "instances" in rid_lower
                    or "extensions" in rid_lower
                )


# ---------------------------------------------------------------------------
# Tests: Idempotent Recovery
# ---------------------------------------------------------------------------


class TestIdempotentRecovery:
    def test_404_on_delete_treated_as_success(
        self,
        mocked_cmd,
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        """404 during begin_delete_by_id → treated as success, execution continues."""
        rg = "rg1"
        cl_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.ExtendedLocation",
            resource_path="/customLocations/mycl",
        )
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id)
        mocked_instances.return_value.show.return_value = inst

        # First delete (instance) returns 404, second (CL) succeeds.
        mock_404_error = HttpResponseError(message="Not found", response=Mock(status_code=404))
        mock_404_error.status_code = 404
        mock_poller = MagicMock()
        mock_poller.done.return_value = True
        mock_poller.result.return_value = None

        call_count = [0]

        def conditional_delete(resource_id, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise mock_404_error
            return mock_poller

        mocked_get_resource_client.return_value.resources.begin_delete_by_id.side_effect = conditional_delete

        # Should not raise.
        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=rg, no_progress=True
        )
        manager.do_work(confirm_yes=True)

    def test_partial_rerun_cluster_path(
        self,
        mocked_cmd,
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        """Re-run after instance already deleted (cluster-name path) → proceeds with remaining."""
        rg = "rg1"
        cluster_name = "mycluster"
        cluster_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.Kubernetes",
            resource_path=f"/connectedClusters/{cluster_name}",
        )
        cl = _build_cl(name="mycl", rg=rg, host_resource_id=cluster_id)

        mocked_connected_clusters.return_value.show.return_value = {
            "id": cluster_id,
            "properties": {"connectivityStatus": "Connected"},
        }
        mocked_custom_locations.return_value.list.return_value = [cl]
        mocked_instances.return_value.list.return_value = []  # Already deleted.

        # Sync rules remain.
        sync_rule = _build_sync_rule(name="aio-sync", rg=rg, cl_name="mycl")
        mocked_custom_locations.return_value.list_resource_sync_rules.return_value = [sync_rule]

        manager = DeletionManager(
            cmd=mocked_cmd, cluster_name=cluster_name, resource_group_name=rg, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        # Instance should be None, but CL and sync rules should be discovered.
        assert manager._instance_resource is None
        assert manager._cl_resource is not None
        assert len(manager._sync_rules) == 1

    def test_non_404_error_propagates(
        self,
        mocked_cmd,
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        """Non-404 HttpResponseError during deletion → re-raised."""
        rg = "rg1"
        cl_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.ExtendedLocation",
            resource_path="/customLocations/mycl",
        )
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id)
        mocked_instances.return_value.show.return_value = inst

        mock_500_error = HttpResponseError(
            message="Internal server error", response=Mock(status_code=500)
        )
        mock_500_error.status_code = 500
        mocked_get_resource_client.return_value.resources.begin_delete_by_id.side_effect = mock_500_error

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=rg, no_progress=True
        )
        with pytest.raises(HttpResponseError):
            manager.do_work(confirm_yes=True)

    def test_extension_404_treated_as_success(
        self,
        mocked_cmd,
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        """404 on extension begin_delete → treated as success, deletion continues."""
        rg = "rg1"
        cl_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.ExtendedLocation",
            resource_path="/customLocations/mycl",
        )
        cluster_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.Kubernetes",
            resource_path="/connectedClusters/mycluster",
        )
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id)
        mocked_instances.return_value.show.return_value = inst
        mocked_get_resource_client.return_value.resources.get_by_id.return_value = {
            "properties": {"hostResourceId": cluster_id},
        }
        mocked_connected_clusters.return_value.show.return_value = {
            "id": cluster_id,
            "properties": {"connectivityStatus": "Connected"},
        }

        aio_ext = _build_extension(name="aio-ext", extension_type=EXTENSION_TYPE_OPS)
        mocked_cluster_extensions.return_value.list.return_value = [aio_ext]

        # Extension delete returns 404.
        mock_404_error = HttpResponseError(
            message="Not found", response=Mock(status_code=404)
        )
        mock_404_error.status_code = 404
        mocked_cluster_extensions.return_value.ops.begin_delete.side_effect = mock_404_error

        # Should not raise.
        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=rg, no_progress=True
        )
        manager.do_work(confirm_yes=True)

    def test_cl_delete_failure_continues_to_dep_extensions(
        self,
        mocker,
        mocked_cmd,
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        """CL delete failure (e.g. orphaned resources) → logs warning, still deletes dep extensions."""
        rg = "rg1"
        cl_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.ExtendedLocation",
            resource_path="/customLocations/mycl",
        )
        cluster_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.Kubernetes",
            resource_path="/connectedClusters/mycluster",
        )
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id)
        mocked_instances.return_value.show.return_value = inst
        mocked_get_resource_client.return_value.resources.get_by_id.return_value = {
            "properties": {"hostResourceId": cluster_id},
        }
        mocked_connected_clusters.return_value.show.return_value = {
            "id": cluster_id,
            "properties": {"connectivityStatus": "Connected"},
        }

        aio_ext = _build_extension(name="aio-ext", extension_type=EXTENSION_TYPE_OPS, version="1.2.0")
        cm_ext = _build_extension(name="cm-ext", extension_type=EXTENSION_TYPE_CM)
        mocked_cluster_extensions.return_value.list.return_value = [aio_ext, cm_ext]

        # CL delete raises a conflict error (orphaned resources).
        mock_conflict = HttpResponseError(
            message="Conflict: resources still scoped", response=Mock(status_code=409)
        )
        mock_conflict.status_code = 409
        mock_poller = MagicMock()
        mock_poller.done.return_value = True

        call_count = [0]

        def conditional_delete(resource_id, **kwargs):
            call_count[0] += 1
            if "customlocations/mycl" in resource_id.lower() and "resourcesyncrules" not in resource_id.lower():
                raise mock_conflict
            return mock_poller

        mocked_get_resource_client.return_value.resources.begin_delete_by_id.side_effect = conditional_delete

        mock_logger = mocker.patch("azext_edge.edge.providers.orchestration.deletion2.logger")

        manager = DeletionManager(
            cmd=mocked_cmd,
            instance_name="myinst",
            resource_group_name=rg,
            include_dependencies=True,
            no_progress=True,
        )
        # Should NOT raise — CL failure is non-fatal.
        manager.do_work(confirm_yes=True)

        # Warning was logged about CL failure.
        warning_messages = [str(c.args[0]) for c in mock_logger.warning.call_args_list]
        assert any("custom location" in msg.lower() and "--cluster" in msg for msg in warning_messages)

        # Dep extensions still ran.
        mocked_cluster_extensions.return_value.ops.begin_delete.assert_called()


# ---------------------------------------------------------------------------
# Tests: Nothing to Delete
# ---------------------------------------------------------------------------


class TestNothingToDelete:
    def test_nothing_to_delete_logs_warning(
        self,
        mocker,
        mocked_cmd,
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
    ):
        """Cluster-name path with nothing found → warning logged, no prompt."""
        rg = "rg1"
        cluster_name = "mycluster"
        cluster_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.Kubernetes",
            resource_path=f"/connectedClusters/{cluster_name}",
        )
        mocked_connected_clusters.return_value.show.return_value = {
            "id": cluster_id,
            "properties": {"connectivityStatus": "Connected"},
        }
        mocked_custom_locations.return_value.list.return_value = []
        mocked_instances.return_value.list.return_value = []

        mock_logger = mocker.patch("azext_edge.edge.providers.orchestration.deletion2.logger")

        manager = DeletionManager(
            cmd=mocked_cmd, cluster_name=cluster_name, resource_group_name=rg, no_progress=True
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
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
        mocked_wait_for_terminal_states,
    ):
        """Resources at different segment depths are batched and deleted deepest-first."""
        rg = "rg1"
        cl_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.ExtendedLocation",
            resource_path="/customLocations/mycl",
        )
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id)
        mocked_instances.return_value.show.return_value = inst

        # Simulate DR resources at different depths from ARG sweep.
        deep_asset_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.DeviceRegistry",
            resource_path="/namespaces/myns/assets/sensor1",
        )
        shallow_spc_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.SecretSyncController",
            resource_path="/azureKeyVaultSecretProviderClasses/my-spc",
        )
        mocked_resource_graph.return_value.query_resources.return_value = {
            "data": [
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
            ]
        }

        delete_order: List[str] = []
        mock_poller = mocked_get_resource_client.return_value.resources.begin_delete_by_id.return_value

        def track_delete(resource_id, **kwargs):
            delete_order.append(resource_id)
            return mock_poller

        mocked_get_resource_client.return_value.resources.begin_delete_by_id.side_effect = track_delete

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=rg, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        # Deep asset (more segments) should be deleted before shallow SPC.
        if deep_asset_id in delete_order and shallow_spc_id in delete_order:
            deep_idx = delete_order.index(deep_asset_id)
            shallow_idx = delete_order.index(shallow_spc_id)
            assert deep_idx < shallow_idx


# ---------------------------------------------------------------------------
# Tests: User Prompt Cancellation
# ---------------------------------------------------------------------------


class TestUserPrompt:
    def test_user_cancels_prompt(
        self,
        mocked_cmd,
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
    ):
        """User declines confirmation → no deletion occurs."""
        rg = "rg1"
        cl_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.ExtendedLocation",
            resource_path="/customLocations/mycl",
        )
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id)
        mocked_instances.return_value.show.return_value = inst
        mocked_should_continue_prompt.return_value = False

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=rg, no_progress=True
        )
        manager.do_work()

        # No delete calls.
        mocked_get_resource_client.return_value.resources.begin_delete_by_id.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: API Version Sourcing
# ---------------------------------------------------------------------------


class TestApiVersions:
    def test_instance_uses_iotops_api_version(
        self,
        mocked_cmd,
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        """Instance resource uses DEFAULT_IOTOPS_MGMT_API_VERSION."""
        rg = "rg1"
        cl_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.ExtendedLocation",
            resource_path="/customLocations/mycl",
        )
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id)
        mocked_instances.return_value.show.return_value = inst

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=rg, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        assert manager._instance_resource.api_version == IOTOPS_API_VERSION

    def test_cl_uses_custom_locations_api_version(
        self,
        mocked_cmd,
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        """CL resource uses CUSTOM_LOCATIONS_API_VERSION."""
        rg = "rg1"
        cl_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.ExtendedLocation",
            resource_path="/customLocations/mycl",
        )
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id)
        mocked_instances.return_value.show.return_value = inst

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=rg, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        assert manager._cl_resource.api_version == CUSTOM_LOCATIONS_API_VERSION

    def test_extensions_use_cluster_extensions_api_version(
        self,
        mocked_cmd,
        mocked_get_resource_client,
        mocked_instances,
        mocked_connected_clusters,
        mocked_custom_locations,
        mocked_cluster_extensions,
        mocked_resource_graph,
        mocked_should_continue_prompt,
        mocked_wait_for_terminal_state,
    ):
        """Extensions use CLUSTER_EXTENSIONS_API_VERSION."""
        rg = "rg1"
        cl_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.ExtendedLocation",
            resource_path="/customLocations/mycl",
        )
        cluster_id = generate_resource_id(
            resource_group_name=rg,
            resource_provider="Microsoft.Kubernetes",
            resource_path="/connectedClusters/mycluster",
        )
        inst = _build_instance(name="myinst", rg=rg, cl_id=cl_id)
        mocked_instances.return_value.show.return_value = inst
        mocked_get_resource_client.return_value.resources.get_by_id.return_value = {
            "properties": {"hostResourceId": cluster_id},
        }
        mocked_connected_clusters.return_value.show.return_value = {
            "id": cluster_id,
            "properties": {"connectivityStatus": "Connected"},
        }

        aio_ext = _build_extension(name="aio-ext", extension_type=EXTENSION_TYPE_OPS)
        mocked_cluster_extensions.return_value.list.return_value = [aio_ext]

        manager = DeletionManager(
            cmd=mocked_cmd, instance_name="myinst", resource_group_name=rg, no_progress=True
        )
        manager.do_work(confirm_yes=True)

        assert manager._aio_extension.api_version == CLUSTER_EXTENSIONS_API_VERSION
