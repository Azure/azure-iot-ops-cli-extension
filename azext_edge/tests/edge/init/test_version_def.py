# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.common import DeployablePasVersions
from azext_edge.edge.providers.orchestration import (
    get_pas_version_def,
    EdgeServiceMoniker,
)
from azext_edge.edge.providers.orchestration.pas_versions import (
    v012_moniker_to_version_map,
    v012_extension_to_rp_map,
    v012_extension_to_version_map,
)


@pytest.mark.parametrize(
    "aio_version",
    [
        pytest.param(
            DeployablePasVersions.v012.value,
        ),
        pytest.param(None),
    ],
)
def test_get_aio_version_def(aio_version: str):
    version_def = get_pas_version_def(aio_version)
    if not aio_version:
        assert version_def is None
        return

    assert version_def.version == aio_version
    assert version_def.moniker_to_version_map == v012_moniker_to_version_map
    assert version_def.extension_to_rp_map == v012_extension_to_rp_map
    assert version_def.extension_to_vers_map == v012_extension_to_version_map


@pytest.mark.parametrize(
    "moniker_map,refresh,expected_set_mappings",
    [
        pytest.param(
            {EdgeServiceMoniker.e4k.value: "0.9.0"},
            False,
            {
                "extension_to_vers_map": v012_extension_to_version_map,
                "extension_to_rp_map": v012_extension_to_rp_map,
            },
        ),
        pytest.param(
            {EdgeServiceMoniker.e4k.value: "1.0.0"},
            True,
            {
                "moniker_to_version_map": {"e4k": "1.0.0"},
                "extension_to_vers_map": {"microsoft.alicesprings.dataplane": "1.0.0"},
                "extension_to_rp_map": {"microsoft.alicesprings.dataplane": "microsoft.alicespringsdataplane"},
            },
        ),
    ],
)
def test_version_def_set_version(moniker_map, refresh, expected_set_mappings):
    version_def = get_pas_version_def(DeployablePasVersions.v012.value)
    version_def.set_moniker_to_version_map(moniker_map=moniker_map, refresh_mappings=refresh)

    assert version_def.version == "custom"
    assert version_def.extension_to_vers_map == expected_set_mappings["extension_to_vers_map"]
    assert version_def.extension_to_rp_map == expected_set_mappings["extension_to_rp_map"]

    if not refresh:
        expected_moniker_to_version_map = dict(v012_moniker_to_version_map)
        expected_moniker_to_version_map.update(moniker_map)

        assert version_def.moniker_to_version_map == expected_moniker_to_version_map
        return

    assert version_def.moniker_to_version_map == expected_set_mappings["moniker_to_version_map"]
