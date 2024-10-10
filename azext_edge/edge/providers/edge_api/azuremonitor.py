# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from .base import EdgeResourceApi


AZUREMONITOR_API_V1 = EdgeResourceApi(group="azuremonitor.microsoft.com", version="v1alpha1", moniker="azuremonitor")
