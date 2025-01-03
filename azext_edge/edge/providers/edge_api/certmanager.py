# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from .base import EdgeResourceApi


CERTMANAGER_API_V1 = EdgeResourceApi(group="cert-manager.io", version="v1", moniker="certmanager")

TRUSTMANAGER_API_V1 = EdgeResourceApi(group="trust.cert-manager.io", version="v1alpha1", moniker="certmanager")
