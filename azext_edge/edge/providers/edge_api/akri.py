# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from ...common import ListableEnum
from .base import EdgeResourceApi


class AkriResourceKinds(ListableEnum):
    CONNECTOR = "connector"
    CONNECTORTEMPLATE = "connectortemplate"
    DISCOVERYHANDLER = "discoveryhandler"


AKRI_API_V1B1 = EdgeResourceApi(group="akri.microsoft.com", version="v1beta1", moniker="akri")
AKRI_API_V1 = EdgeResourceApi(group="akri.iotoperations.azure.com", version="v1", moniker="akri")

AKRI_ACTIVE_API = AKRI_API_V1
