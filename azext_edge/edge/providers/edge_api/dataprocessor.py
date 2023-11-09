# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from .base import EdgeResourceApi
from ...common import ListableEnum


class DataProcessorResourceKinds(ListableEnum):
    DATASET = "dataset"
    INSTANCE = "instance"
    PIPELINE = "pipeline"


DATA_PROCESSOR_API_V1 = EdgeResourceApi(
    group="dataprocessor.iotoperations.azure.com", version="v1", moniker="dataprocessor"
)
