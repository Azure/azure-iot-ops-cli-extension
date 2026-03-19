# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from .akri import AKRI_ACTIVE_API, AKRI_API_V1, AkriResourceKinds
from .arccontainerstorage import ARCCONTAINERSTORAGE_API_V1, CONTAINERSTORAGE_API_V1
from .azuremonitor import AZUREMONITOR_API_V1
from .base import EdgeApiManager, EdgeResourceApi
from .certmanager import CERTMANAGER_API_V1, TRUSTMANAGER_API_V1
from .clusterconfig import CLUSTER_CONFIG_API_V1, CLUSTERCONFIG_ACTIVE_API
from .dataflow import DATAFLOW_ACTIVE_API, DATAFLOW_API_V1, DATAFLOW_API_V1B1, DataflowResourceKinds
from .deviceregistry import (
    DEVICEREGISTRY_ACTIVE_API,
    DEVICEREGISTRY_API_V1,
    DEVICEREGISTRY_API_V1B1,
    NAMESPACED_DEVICEREGISTRY_API_V1,
    NAMESPACED_DEVICEREGISTRY_API_V1B1,
    DeviceRegistryResourceKinds,
)
from .meso import MesoResourceKinds
from .keyvault import KEYVAULT_API_V1, KeyVaultResourceKinds
from .meta import META_ACTIVE_API, META_API_V1, META_API_V1B1, MetaResourceKinds
from .mq import MQ_ACTIVE_API, MQTT_BROKER_API_V1, MQTT_BROKER_API_V1B1, MqResourceKinds
from .secretstore import SECRETSTORE_API_V1, SECRETSYNC_API_V1

__all__ = [
    "AKRI_API_V1",
    "AKRI_ACTIVE_API",
    "AkriResourceKinds",
    "ARCCONTAINERSTORAGE_API_V1",
    "AZUREMONITOR_API_V1",
    "CERTMANAGER_API_V1",
    "CLUSTER_CONFIG_API_V1",
    "CLUSTERCONFIG_ACTIVE_API",
    "CONTAINERSTORAGE_API_V1",
    "EdgeResourceApi",
    "EdgeApiManager",
    "MesoResourceKinds",
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
    "NAMESPACED_DEVICEREGISTRY_API_V1",
    "NAMESPACED_DEVICEREGISTRY_API_V1B1",
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
