# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from .base import EdgeResourceApi


AKRI_API_V1B1 = EdgeResourceApi(group="akri.microsoft.com", version="v1beta1", moniker="akri")

AKRI_ACTIVE_API = AKRI_API_V1B1
