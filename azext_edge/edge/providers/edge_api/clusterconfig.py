# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from .base import EdgeResourceApi


CLUSTER_CONFIG_API_V1 = EdgeResourceApi(
    group="clusterconfig.azure.com", version="v1", moniker="clusterconfig", label="microsoft-iotoperations"
)
