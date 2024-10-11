# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Iterable, Optional
from azext_edge.edge.providers.orchestration.resources.connector.opcua.certs import OpcUACerts


def add_connector_opcua_trust(
    cmd,
    instance_name: str,
    instance_resource_group: str,
    file: str,
    secret_name: Optional[str] = None,
) -> dict:
    return OpcUACerts(cmd).trust_add(
        instance_name=instance_name,
        resource_group=instance_resource_group,
        file=file,
        secret_name=secret_name,
    )
