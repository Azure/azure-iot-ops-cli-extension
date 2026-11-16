# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Bind released test helpers to Fairfax without changing the installed product."""

import importlib
import os


FAIRFAX_TEST_SOURCE = "40ca69187cb8a04e1ea92f5d759c3f4a0a1c868a"
PUBLIC_V2_TEST_SOURCE = "0b555d6e535f7e212db7aa8b79436d652507e96b"
PUBLIC_V3_TEST_SOURCE = "16e6e1d64ffe266970596d0b66cf8ff464b8c85a"
FAIRFAX_EXCLUSIONS = {
    "edge/adr/test_asset_endpoint_profiles_int.py::test_asset_endpoint_lifecycle":
        "Fairfax does not expose Microsoft.DeviceRegistry/assetEndpointProfiles at API 2026-04-01.",
    "edge/adr/test_asset_lifecycle_int.py::test_asset_lifecycle":
        "Fairfax does not expose classic Microsoft.DeviceRegistry/assets at API 2026-04-01.",
    "edge/adr/test_asset_lifecycle_int.py::test_asset_sub_point_lifecycle":
        "Fairfax does not expose classic Microsoft.DeviceRegistry/assets at API 2026-04-01.",
    "edge/orchestration/resources/test_instance_int.py::test_aio_instance":
        "This instance test requires classic ADR assetEndpointProfiles, unavailable in Fairfax at API 2026-04-01.",
}
LEGACY_ADR_MINIMAL_DEVICE_EXCLUSIONS = {
    "edge/adr/test_namespace_devices_int.py::test_namespace_device_lifecycle_operations":
        "Frozen CLI sends properties: {} on minimal ns device create, which Microsoft.DeviceRegistry "
        "rejects with HTTP 500; fixed in CLI >= 2.11.0 (PR #941).",
}


def exclusions_for(cloud, source):
    if cloud == "AzureUSGovernment" and source == FAIRFAX_TEST_SOURCE:
        return FAIRFAX_EXCLUSIONS
    if cloud == "AzureCloud" and source in (PUBLIC_V2_TEST_SOURCE, PUBLIC_V3_TEST_SOURCE):
        return LEGACY_ADR_MINIMAL_DEVICE_EXCLUSIONS
    return {}


def pytest_collection_modifyitems(items):
    exclusions = exclusions_for(
        os.environ.get("azext_edge_cloud"),
        os.environ.get("AZEXT_OPS_RELEASE_TEST_SOURCE"),
    )
    if not exclusions:
        return
    import pytest

    for item in items:
        path = item.path.as_posix().rsplit("azext_edge/tests/", 1)[-1]
        reason = exclusions.get(f"{path}::{item.originalname or item.name}")
        if reason:
            item.add_marker(pytest.mark.skip(reason=reason))


def pytest_configure():
    cloud = os.environ["azext_edge_cloud"]
    if cloud == "AzureCloud":
        return
    if cloud != "AzureUSGovernment":
        raise ValueError("Released AIO monitoring supports only public Azure and Fairfax.")
    checks = importlib.import_module("azext_edge.tests.runtime_checks")
    catalog = checks.get_runtime_catalog

    def cloud_catalog(cloud_name=None):
        if cloud_name is not None and cloud_name != cloud:
            raise ValueError("The released test helper requested a different cloud.")
        return catalog(cloud)

    # Older released helpers omit the cloud argument. Bind their imported alias
    # in every pytest worker; leave the product's catalog and assertions unchanged.
    checks.get_runtime_catalog = cloud_catalog
