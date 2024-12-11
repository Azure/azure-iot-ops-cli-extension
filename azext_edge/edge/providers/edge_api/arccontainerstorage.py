# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from .base import EdgeResourceApi


ARCCONTAINERSTORAGE_API_V1 = EdgeResourceApi(
    group="arccontainerstorage.azure.net", version="v1", moniker="arccontainerstorage"
)

CONTAINERSTORAGE_API_V1 = EdgeResourceApi(
    group="containerstorage.azure.com", version="v1", moniker="containerstorage"
)
