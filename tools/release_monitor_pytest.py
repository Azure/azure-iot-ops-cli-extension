# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Bind released test helpers to Fairfax without changing the installed product."""

import importlib
import os


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
