# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.common import DeployableAioVersions
from azext_edge.edge.providers.orchestration import (
    get_aio_version_def,
    EdgeServiceMoniker,
)
from azext_edge.edge.providers.orchestration.aio_versions import (
    v011_moniker_to_version_map,
    v011_extension_to_rp_map,
    v011_extension_to_version_map,
)


@pytest.mark.parametrize(
    "aio_version",
    [
        pytest.param(
            DeployableAioVersions.v011.value,
        ),
        pytest.param(None),
    ],
)
def test_get_aio_version_def(aio_version: str):
    version_def = get_aio_version_def(aio_version)
    if not aio_version:
        assert version_def is None
        return

    assert version_def.version == aio_version
    assert version_def.moniker_to_version_map == v011_moniker_to_version_map
    assert version_def.extension_to_rp_map == v011_extension_to_rp_map
    assert version_def.extension_to_vers_map == v011_extension_to_version_map


@pytest.mark.parametrize(
    "moniker_map,refresh",
    [
        pytest.param(
            {EdgeServiceMoniker.e4k.value: "0.9.0"},
            False,
        ),
    ],
)
def test_version_def_set_version(moniker_map, refresh):
    version_def = get_aio_version_def(DeployableAioVersions.v011.value)
    version_def.set_moniker_to_version_map(moniker_map=moniker_map, refresh_mappings=refresh)

    assert version_def.version == "custom"
    if not refresh:
        expected_moniker_to_version_map = dict(v011_moniker_to_version_map)
        expected_moniker_to_version_map.update(moniker_map)

        assert version_def.moniker_to_version_map == expected_moniker_to_version_map
        return
