# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from .base import EdgeResourceApi
from ...common import ListableEnum


class DataflowResourceKinds(ListableEnum):
    DATAFLOWENDPOINT = "dataflowendpoint"
    DATAFLOWPROFILE = "dataflowprofile"
    DATAFLOW = "dataflow"


DATAFLOW_API_V1B1 = EdgeResourceApi(
    group="connectivity.iotoperations.azure.com", version="v1beta1", moniker="dataflow", label="microsoft-iotoperations-dataflows"
)
