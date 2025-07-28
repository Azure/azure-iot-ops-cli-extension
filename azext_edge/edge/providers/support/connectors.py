# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from functools import partial

from knack.log import get_logger

from .base import (
    DAY_IN_SECONDS,
    process_config_maps,
    process_daemonsets,
    process_deployments,
    process_services,
    process_v1_pods,
    process_replicasets,
)
from .common import NAME_LABEL_FORMAT

logger = get_logger(__name__)

SIMULATOR_PREFIX = "opcplc-"
OPC_PREFIX = "aio-opc-"
OPC_APP_LABEL = "app in (aio-opc-supervisor, aio-opc-admission-controller)"
OPC_NAME_LABEL = NAME_LABEL_FORMAT.format(label="aio-opc-opcua-connector, opcplc")
OPC_NAME_VAR_LABEL = "name in (aio-opc-asset-discovery)"
CONNECTORS_DIRECTORY_PATH = "connectors"
# The prefix for connectors, will use common labels once they are available
AIO_ONVIF_PREFIX = "aio-onvif"
AIO_MEDIA_PREFIX = "aio-media"

# TODO: once this label is stabled, we can remove the other labels
OPCUA_NAME_LABEL = NAME_LABEL_FORMAT.format(label="microsoft-iotoperations-opcuabroker")


def fetch_pods(since_seconds: int = DAY_IN_SECONDS):
    connector_pods = []
    opcua_pod_name_labels = [
        OPC_APP_LABEL,
        OPC_NAME_LABEL,
        OPC_NAME_VAR_LABEL,
    ]

    # opcua connector pods
    for pod_name_label in opcua_pod_name_labels:
        connector_pods.extend(
            process_v1_pods(
                directory_path=CONNECTORS_DIRECTORY_PATH,
                label_selector=pod_name_label,
                since_seconds=since_seconds,
                include_metrics=True,
            )
        )

    connector_pods.extend(
        process_v1_pods(
            directory_path=CONNECTORS_DIRECTORY_PATH,
            label_selector=OPCUA_NAME_LABEL,
            since_seconds=since_seconds,
            include_metrics=True,
        )
    )

    # onvif connector pods
    connector_pods.extend(
        process_v1_pods(
            directory_path=CONNECTORS_DIRECTORY_PATH,
            prefix_names=[AIO_ONVIF_PREFIX],
            since_seconds=since_seconds,
            include_metrics=True,
        )
    )

    # media connector pods
    connector_pods.extend(
        process_v1_pods(
            directory_path=CONNECTORS_DIRECTORY_PATH,
            prefix_names=[AIO_MEDIA_PREFIX],
            since_seconds=since_seconds,
            include_metrics=True,
        )
    )
    return connector_pods


def fetch_deployments():
    processed = process_deployments(
        directory_path=CONNECTORS_DIRECTORY_PATH, prefix_names=[OPC_PREFIX, SIMULATOR_PREFIX]
    )
    processed.extend(process_deployments(directory_path=CONNECTORS_DIRECTORY_PATH, label_selector=OPC_NAME_LABEL))
    processed.extend(process_deployments(directory_path=CONNECTORS_DIRECTORY_PATH, label_selector=OPCUA_NAME_LABEL))
    return processed


def fetch_replicasets():
    processed = process_replicasets(directory_path=CONNECTORS_DIRECTORY_PATH, label_selector=OPC_APP_LABEL)
    processed.extend(process_replicasets(directory_path=CONNECTORS_DIRECTORY_PATH, label_selector=OPC_NAME_LABEL))
    processed.extend(process_replicasets(directory_path=CONNECTORS_DIRECTORY_PATH, label_selector=OPCUA_NAME_LABEL))
    return processed


def fetch_services():
    # opcua services
    processed = process_services(directory_path=CONNECTORS_DIRECTORY_PATH, label_selector=OPC_APP_LABEL)
    processed.extend(process_services(directory_path=CONNECTORS_DIRECTORY_PATH, prefix_names=[SIMULATOR_PREFIX]))
    processed.extend(process_services(directory_path=CONNECTORS_DIRECTORY_PATH, label_selector=OPCUA_NAME_LABEL))

    # onvif services
    processed.extend(
        process_services(
            directory_path=CONNECTORS_DIRECTORY_PATH,
            prefix_names=[AIO_ONVIF_PREFIX],
        )
    )

    # media services
    processed.extend(
        process_services(
            directory_path=CONNECTORS_DIRECTORY_PATH,
            prefix_names=[AIO_MEDIA_PREFIX],
        )
    )
    return processed


def fetch_configmaps():
    return process_config_maps(
        directory_path=CONNECTORS_DIRECTORY_PATH,
        label_selector=OPCUA_NAME_LABEL,
    )


def fetch_daemonsets():
    processed = process_daemonsets(
        directory_path=CONNECTORS_DIRECTORY_PATH,
        field_selector="metadata.name==aio-opc-asset-discovery",
    )
    processed.extend(
        process_daemonsets(
            directory_path=CONNECTORS_DIRECTORY_PATH,
            label_selector=OPCUA_NAME_LABEL,
        )
    )
    return processed


support_runtime_elements = {
    "daemonsets": fetch_daemonsets,
    "configmaps": fetch_configmaps,
    "deployments": fetch_deployments,
    "replicasets": fetch_replicasets,
    "services": fetch_services,
}


def prepare_bundle(
    log_age_seconds: int = DAY_IN_SECONDS,
) -> dict:
    connectors_to_run = {}

    connectors_to_run["pods"] = partial(fetch_pods, since_seconds=log_age_seconds)
    connectors_to_run.update(support_runtime_elements)

    return connectors_to_run
