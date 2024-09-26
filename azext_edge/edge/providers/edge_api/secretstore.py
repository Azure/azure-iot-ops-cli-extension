# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from .base import EdgeResourceApi


SECRETSYNC_API_V1 = EdgeResourceApi(
    group="secret-sync.x-k8s.io",
    version="v1alpha1",
    moniker="secretsync",
)

SECRETSTORE_API_V1 = EdgeResourceApi(
    group="secrets-store.csi.x-k8s.io",
    version="v1",
    moniker="secretstore",
)
