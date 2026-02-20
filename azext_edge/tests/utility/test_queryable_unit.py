# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from unittest.mock import MagicMock

import pytest


MODULE_PATH = "azext_edge.edge.util.queryable"


@pytest.fixture
def mock_get_subscription_id(mocker):
    """Mock the CLI get_subscription_id to return a predictable value."""
    return mocker.patch(
        "azure.cli.core.commands.client_factory.get_subscription_id",
        return_value="default-sub-id",
    )


@pytest.fixture
def mock_resource_graph(mocker):
    """Mock ResourceGraph so Queryable.__init__ doesn't need a real CLI context."""
    return mocker.patch(f"{MODULE_PATH}.ResourceGraph")


@pytest.fixture
def mock_get_resource_client(mocker):
    """Mock get_resource_client used by the lazy resource_client property."""
    return mocker.patch(f"{MODULE_PATH}.get_resource_client")


@pytest.fixture
def mock_cmd():
    """Minimal mock cmd object with cli_ctx."""
    cmd = MagicMock()
    cmd.cli_ctx = MagicMock()
    return cmd


@pytest.fixture
def queryable_deps(mock_get_subscription_id, mock_resource_graph, mock_get_resource_client, mock_cmd):
    """Bundle all Queryable dependencies for convenience."""
    return {
        "get_subscription_id": mock_get_subscription_id,
        "resource_graph": mock_resource_graph,
        "get_resource_client": mock_get_resource_client,
        "cmd": mock_cmd,
    }


class TestQueryableInit:
    """Tests for Queryable.__init__ with the new subscription_id param."""

    def test_default_subscription_from_cli(self, queryable_deps):
        """When no subscription_id is passed, default_subscription_id comes from the CLI."""
        from azext_edge.edge.util.queryable import Queryable

        q = Queryable(cmd=queryable_deps["cmd"])

        assert q.default_subscription_id == "default-sub-id"
        assert q.subscriptions == ["default-sub-id"]

    def test_explicit_subscription_id(self, queryable_deps):
        """When subscription_id is passed, it becomes the default and populates subscriptions."""
        from azext_edge.edge.util.queryable import Queryable

        q = Queryable(cmd=queryable_deps["cmd"], subscription_id="explicit-sub")

        assert q.default_subscription_id == "explicit-sub"
        assert q.subscriptions == ["explicit-sub"]

    def test_subscriptions_list_takes_precedence(self, queryable_deps):
        """When subscriptions list is passed, it is used as-is (backward compat)."""
        from azext_edge.edge.util.queryable import Queryable

        q = Queryable(cmd=queryable_deps["cmd"], subscriptions=["sub-a", "sub-b"])

        # default_subscription_id still comes from CLI since subscription_id wasn't passed
        assert q.default_subscription_id == "default-sub-id"
        assert q.subscriptions == ["sub-a", "sub-b"]

    def test_subscription_id_with_subscriptions_list(self, queryable_deps):
        """When both subscription_id and subscriptions are passed, both are respected."""
        from azext_edge.edge.util.queryable import Queryable

        q = Queryable(cmd=queryable_deps["cmd"], subscription_id="explicit-sub", subscriptions=["sub-x"])

        assert q.default_subscription_id == "explicit-sub"
        assert q.subscriptions == ["sub-x"]

    def test_resource_graph_initialized_with_subscriptions(self, queryable_deps):
        """ResourceGraph is created with the resolved subscriptions list."""
        from azext_edge.edge.util.queryable import Queryable

        Queryable(cmd=queryable_deps["cmd"], subscription_id="my-sub")

        queryable_deps["resource_graph"].assert_called_once_with(
            cmd=queryable_deps["cmd"],
            subscriptions=["my-sub"],
        )


class TestQueryableResourceClientLazy:
    """Tests for the lazy resource_client cached_property."""

    def test_resource_client_not_created_on_init(self, queryable_deps):
        """get_resource_client is NOT called during __init__."""
        from azext_edge.edge.util.queryable import Queryable

        Queryable(cmd=queryable_deps["cmd"])

        queryable_deps["get_resource_client"].assert_not_called()

    def test_resource_client_created_on_first_access(self, queryable_deps):
        """get_resource_client is called on first property access."""
        from azext_edge.edge.util.queryable import Queryable

        q = Queryable(cmd=queryable_deps["cmd"])
        _ = q.resource_client

        queryable_deps["get_resource_client"].assert_called_once_with(
            subscription_id="default-sub-id",
        )

    def test_resource_client_cached(self, queryable_deps):
        """Subsequent accesses return the same client instance (cached)."""
        from azext_edge.edge.util.queryable import Queryable

        q = Queryable(cmd=queryable_deps["cmd"])
        client1 = q.resource_client
        client2 = q.resource_client

        assert client1 is client2
        queryable_deps["get_resource_client"].assert_called_once()


class TestQueryableQuery:
    """Tests for query and _process_query_result."""

    def test_query_returns_data(self, queryable_deps):
        """query() delegates to resource_graph and returns data."""
        from azext_edge.edge.util.queryable import Queryable

        q = Queryable(cmd=queryable_deps["cmd"])
        q.resource_graph.query_resources.return_value = {"data": [{"id": "r1"}, {"id": "r2"}]}

        result = q.query("some query")

        assert result == [{"id": "r1"}, {"id": "r2"}]

    def test_query_first(self, queryable_deps):
        """query(first=True) returns only the first result."""
        from azext_edge.edge.util.queryable import Queryable

        q = Queryable(cmd=queryable_deps["cmd"])
        q.resource_graph.query_resources.return_value = {"data": [{"id": "r1"}, {"id": "r2"}]}

        result = q.query("some query", first=True)

        assert result == {"id": "r1"}

    def test_query_empty_data(self, queryable_deps):
        """query() with empty data returns empty list."""
        from azext_edge.edge.util.queryable import Queryable

        q = Queryable(cmd=queryable_deps["cmd"])
        q.resource_graph.query_resources.return_value = {"data": []}

        result = q.query("some query")

        assert result == []

    def test_query_first_empty_data(self, queryable_deps):
        """query(first=True) with empty data falls through to returning the empty list."""
        from azext_edge.edge.util.queryable import Queryable

        q = Queryable(cmd=queryable_deps["cmd"])
        q.resource_graph.query_resources.return_value = {"data": []}

        result = q.query("some query", first=True)

        assert result == []

    def test_query_no_data_key(self, queryable_deps):
        """query() returns None when result has no 'data' key."""
        from azext_edge.edge.util.queryable import Queryable

        q = Queryable(cmd=queryable_deps["cmd"])
        q.resource_graph.query_resources.return_value = {}

        result = q.query("some query")

        assert result is None


class TestQueryableGetResourceGroup:
    """Tests for get_resource_group (exercises lazy resource_client)."""

    def test_get_resource_group(self, queryable_deps):
        """get_resource_group delegates to resource_client.resource_groups.get."""
        from azext_edge.edge.util.queryable import Queryable

        q = Queryable(cmd=queryable_deps["cmd"])
        q.get_resource_group("my-rg")

        queryable_deps["get_resource_client"].return_value.resource_groups.get.assert_called_once_with(
            resource_group_name="my-rg",
        )


class TestQueryableBackwardCompat:
    """Verify existing callers using subscriptions= still work."""

    def test_old_style_subscriptions_param(self, queryable_deps):
        """Callers passing subscriptions=[subscription_id] if subscription_id else None still work."""
        from azext_edge.edge.util.queryable import Queryable

        # Simulate old-style: subscription_id provided
        sub_id = "legacy-sub"
        q = Queryable(cmd=queryable_deps["cmd"], subscriptions=[sub_id] if sub_id else None)

        assert q.subscriptions == ["legacy-sub"]
        assert q.default_subscription_id == "default-sub-id"  # unchanged — old behavior

    def test_old_style_subscriptions_none(self, queryable_deps):
        """Callers passing subscriptions=None still get default behavior."""
        from azext_edge.edge.util.queryable import Queryable

        q = Queryable(cmd=queryable_deps["cmd"], subscriptions=None)

        assert q.subscriptions == ["default-sub-id"]
        assert q.default_subscription_id == "default-sub-id"
