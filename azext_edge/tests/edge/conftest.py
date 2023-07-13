# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import pytest


@pytest.fixture
def mocked_client(mocker):
    patched = mocker.patch("azext_edge.edge.providers.base.client", autospec=True)
    yield patched


@pytest.fixture
def mocked_config(request, mocker):
    patched = mocker.patch("azext_edge.edge.providers.base.config", autospec=True)
    current_context = getattr(request, "param", {})
    patched.list_kube_config_contexts.return_value = ([], current_context)
    yield {"param": current_context, "mock": patched}


@pytest.fixture
def mocked_urlopen(mocker):
    patched = mocker.patch("azext_edge.edge.providers.base.urlopen", autospec=True)
    yield patched
