# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from .base import EdgeResourceApi, EdgeApiManager
from .certmanager import CERTMANAGER_API_V1, TRUSTMANAGER_API_V1
from .clusterconfig import CLUSTER_CONFIG_API_V1, CLUSTER_CONFIG_API_V1B1, CLUSTERCONFIG_ACTIVE_API
from .mq import MQ_ACTIVE_API, MQTT_BROKER_API_V1, MQTT_BROKER_API_V1B1, MqResourceKinds
from .keyvault import KEYVAULT_API_V1, KeyVaultResourceKinds
from .deviceregistry import (
    DEVICEREGISTRY_API_V1,
    DEVICEREGISTRY_API_V1B1,
    DEVICEREGISTRY_ACTIVE_API,
    DeviceRegistryResourceKinds,
)
from .dataflow import DATAFLOW_API_V1, DATAFLOW_API_V1B1, DATAFLOW_ACTIVE_API, DataflowResourceKinds
from .meta import META_API_V1, META_API_V1B1, META_ACTIVE_API, MetaResourceKinds
from .arccontainerstorage import ARCCONTAINERSTORAGE_API_V1, CONTAINERSTORAGE_API_V1
from .secretstore import SECRETSYNC_API_V1, SECRETSTORE_API_V1
from .azuremonitor import AZUREMONITOR_API_V1
from .akri import AKRI_API_V1B1, AKRI_ACTIVE_API

__all__ = [
    "AKRI_API_V1B1",
    "AKRI_ACTIVE_API",
    "ARCCONTAINERSTORAGE_API_V1",
    "AZUREMONITOR_API_V1",
    "CERTMANAGER_API_V1",
    "CLUSTER_CONFIG_API_V1",
    "CLUSTER_CONFIG_API_V1B1",
    "CLUSTERCONFIG_ACTIVE_API",
    "CONTAINERSTORAGE_API_V1",
    "EdgeResourceApi",
    "EdgeApiManager",
    "MqResourceKinds",
    "MQ_ACTIVE_API",
    "MQTT_BROKER_API_V1",
    "MQTT_BROKER_API_V1B1",
    "KeyVaultResourceKinds",
    "KEYVAULT_API_V1",
    "DeviceRegistryResourceKinds",
    "DEVICEREGISTRY_ACTIVE_API",
    "DEVICEREGISTRY_API_V1",
    "DEVICEREGISTRY_API_V1B1",
    "DATAFLOW_ACTIVE_API",
    "DATAFLOW_API_V1",
    "DATAFLOW_API_V1B1",
    "DataflowResourceKinds",
    "META_API_V1",
    "META_ACTIVE_API",
    "META_API_V1B1",
    "MetaResourceKinds",
    "SECRETSYNC_API_V1",
    "SECRETSTORE_API_V1",
    "TRUSTMANAGER_API_V1",
]
