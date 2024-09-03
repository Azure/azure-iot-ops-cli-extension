# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from .base import EdgeResourceApi
from ...common import ListableEnum


class AkriResourceKinds(ListableEnum):
    INSTANCE = "instance"
    CONFIGURATION = "configuration"


AKRI_API_V0 = EdgeResourceApi(group="akri.sh", version="v0", moniker="akri", label="microsoft-iotoperations-akri")
