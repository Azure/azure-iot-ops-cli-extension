# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from .base import EdgeResourceApi


OPENSERVICEMESH_CONFIG_API_V1 = EdgeResourceApi(
    group="config.openservicemesh.io",
    version="v1alpha2",
    moniker="openservicemesh",
)

OPENSERVICEMESH_POLICY_API_V1 = EdgeResourceApi(
    group="policy.openservicemesh.io",
    version="v1alpha1",
    moniker="openservicemesh",
)
