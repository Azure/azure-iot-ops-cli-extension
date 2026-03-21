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
    DISCOVEREDASSET = "discoveredasset"
    DISCOVEREDASSETENDPOINTPROFILE = "discoveredassetendpointprofile"
    DEVICE = "device"
    DISCOVEREDDEVICE = "discovereddevice"


DEVICEREGISTRY_API_V1 = EdgeResourceApi(
    group="deviceregistry.microsoft.com", version="v1", moniker="deviceregistry"
)

DEVICEREGISTRY_API_V1B1 = EdgeResourceApi(
    group="deviceregistry.microsoft.com", version="v1beta1", moniker="deviceregistry"
)

NAMESPACED_DEVICEREGISTRY_API_V1 = EdgeResourceApi(
    group="namespaces.deviceregistry.microsoft.com", version="v1", moniker="deviceregistry"
)

NAMESPACED_DEVICEREGISTRY_API_V1B1 = EdgeResourceApi(
    group="namespaces.deviceregistry.microsoft.com", version="v1beta1", moniker="deviceregistry"
)

DEVICEREGISTRY_ACTIVE_API = NAMESPACED_DEVICEREGISTRY_API_V1
