# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from .base import EdgeResourceApi
from ...common import ListableEnum


class DeviceRegistryResourceKinds(ListableEnum):
    ASSET = "asset"
    ASSETENDPOINTPROFILE = "assetendpointprofile"


DEVICEREGISTRY_API_V1 = EdgeResourceApi(
    group="deviceregistry.microsoft.com", version="v1beta2", moniker="deviceregistry"
)
