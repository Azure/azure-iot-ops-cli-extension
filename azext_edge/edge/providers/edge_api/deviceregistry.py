# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from .base import EdgeResourceApi
from ...common import ListableEnum


class DeviceRegistryResourceKinds(ListableEnum):
    ASSET = "asset"
    ASSETENDPOINTPROFILE = "assetendpointprofile"


DEVICEREGISTRY_API_V1 = EdgeResourceApi(
    group="deviceregistry.microsoft.com", version="v1beta1", moniker="deviceregistry"
)
